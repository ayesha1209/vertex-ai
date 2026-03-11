import asyncio
import json
import uuid
from datetime import datetime as dt
from queue import Empty, Queue
from typing import Any, List

from bson import ObjectId
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pymongo.errors import PyMongoError

from app.db.mongo import TERMS_DOC_ID, documents_collection, now_local, terms_collection, to_object_id
from app.schemas.document import (
    BatchSummary,
    BulkDeleteRequest,
    DocumentInDB,
    DocumentSummary,
    GenerateBatchRequest,
    GenerateBatchResponse,
    GenerateRowRequest,
    GenerateRowResponse,
    ListBatchesResponse,
    ListDocumentsResponse,
    RowPreview,
    TermsResponse,
    TermsUpdateRequest,
    UploadPreviewResponse,
    UpdateDocumentRequest,
)
from app.prompts.vertex_prompts import DEFAULT_TERMS
from app.services.document_generation import generate_documents_for_row
from app.services.export import html_to_pdf
from app.utils.excel_parser import parse_excel_to_previews

# In-memory job store: job_id -> {"status": "running"|"done", "queue": Queue}
_job_store: dict[str, dict[str, Any]] = {}
# Max events to keep per job so late-joining clients get something
_JOB_QUEUE_MAX = 500


def _run_batch_sync(job_id: str, rows: list[RowPreview]) -> None:
    """Run in thread: generate docs for each row, push to job queue."""
    store = _job_store.get(job_id)
    if not store or store["status"] == "done":
        return
    q: Queue = store["queue"]
    try:
        for row in rows:
            docs_to_insert = generate_documents_for_row(row)
            now = now_local()
            for doc in docs_to_insert:
                mongo_doc = {
                    "buyer_name": doc.buyer_name,
                    "product_name": doc.product_name,
                    "product_type": doc.product_type,
                    "doc_type": doc.doc_type,
                    "html_content": doc.html_content,
                    "created_at": now,
                    "updated_at": now,
                    "employee_name": getattr(doc, "employee_name", None),
                    "letterhead": getattr(doc, "letterhead", None),
                    "batch_id": getattr(doc, "batch_id", None),
                    "quotation_no": getattr(doc, "quotation_no", None),
                    "company_name": getattr(doc, "company_name", None),
                    "local_export": getattr(doc, "local_export", None),
                }
                result = documents_collection.insert_one(mongo_doc)
                inserted = documents_collection.find_one({"_id": result.inserted_id})
                if inserted:
                    summary = DocumentSummary(
                        id=str(inserted["_id"]),
                        buyer_name=inserted["buyer_name"],
                        product_name=inserted["product_name"],
                        product_type=inserted["product_type"],
                        doc_type=inserted["doc_type"],
                        created_at=inserted["created_at"],
                        updated_at=inserted["updated_at"],
                        employee_name=inserted.get("employee_name"),
                        batch_id=inserted.get("batch_id"),
                    )
                    try:
                        q.put_nowait(summary.model_dump(mode="json"))
                    except Exception:
                        pass
    except Exception:
        pass
    finally:
        store["status"] = "done"
        try:
            q.put_nowait("done")
        except Exception:
            pass


router = APIRouter(prefix="/api", tags=["documents"])


def _serialize_mongo_doc(doc: Any) -> DocumentInDB:
    return DocumentInDB(
        id=str(doc["_id"]),
        buyer_name=doc["buyer_name"],
        product_name=doc["product_name"],
        product_type=doc["product_type"],
        doc_type=doc["doc_type"],
        html_content=doc["html_content"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        employee_name=doc.get("employee_name"),
        letterhead=doc.get("letterhead"),
        batch_id=doc.get("batch_id"),
        quotation_no=doc.get("quotation_no"),
        company_name=doc.get("company_name"),
        local_export=doc.get("local_export"),
    )


@router.post("/upload-preview", response_model=UploadPreviewResponse)
async def upload_preview(file: UploadFile = File(...)) -> UploadPreviewResponse:
    """Upload Excel/CSV and return a clean preview of rows to the frontend."""
    previews: List[RowPreview] = parse_excel_to_previews(file)
    return UploadPreviewResponse(rows=previews)


@router.post("/generate-batch", response_model=GenerateBatchResponse)
async def generate_batch(payload: GenerateBatchRequest) -> GenerateBatchResponse:
    """Start batch generation. Returns job_id. Use GET /jobs/{job_id}/stream for SSE progress."""
    if not payload.rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No rows provided")
    job_id = str(uuid.uuid4())
    q: Queue = Queue(maxsize=_JOB_QUEUE_MAX)
    _job_store[job_id] = {"status": "running", "queue": q}
    asyncio.get_event_loop().run_in_executor(
        None,
        _run_batch_sync,
        job_id,
        payload.rows,
    )
    return GenerateBatchResponse(job_id=job_id)


@router.get("/jobs/{job_id}/stream")
async def job_stream(job_id: str) -> StreamingResponse:
    """SSE stream: events 'document' (with doc payload) and 'done'."""
    if job_id not in _job_store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    store = _job_store[job_id]
    q: Queue = store["queue"]

    async def event_gen() -> Any:
        if store["status"] == "done":
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        while True:
            try:
                item = q.get_nowait()
            except Empty:
                if store["status"] == "done":
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return
                await asyncio.sleep(0.25)
                continue
            if item == "done":
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            yield f"data: {json.dumps({'type': 'document', 'doc': item})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/jobs/{job_id}/status")
async def job_status(job_id: str) -> dict[str, Any]:
    """Return job status (running | done). For late-joining clients."""
    if job_id not in _job_store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return {"job_id": job_id, "status": _job_store[job_id]["status"]}


@router.post("/generate-row", response_model=GenerateRowResponse)
async def generate_row(payload: GenerateRowRequest) -> GenerateRowResponse:
    """Generate quotation + COA/CoC for a single row using OpenAI."""
    row = payload.row
    docs_to_insert = generate_documents_for_row(row)

    now = now_local()
    mongo_docs = []
    for doc in docs_to_insert:
        mongo_docs.append(
            {
                "buyer_name": doc.buyer_name,
                "product_name": doc.product_name,
                "product_type": doc.product_type,
                "doc_type": doc.doc_type,
                "html_content": doc.html_content,
                "created_at": now,
                "updated_at": now,
                "employee_name": getattr(doc, "employee_name", None),
                "letterhead": getattr(doc, "letterhead", None),
                "batch_id": getattr(doc, "batch_id", None),
                "quotation_no": getattr(doc, "quotation_no", None),
                "company_name": getattr(doc, "company_name", None),
                "local_export": getattr(doc, "local_export", None),
            }
        )

    result = documents_collection.insert_many(mongo_docs)
    inserted_ids = result.inserted_ids
    stored_docs = documents_collection.find({"_id": {"$in": inserted_ids}})

    return GenerateRowResponse(
        documents=[_serialize_mongo_doc(d) for d in stored_docs],
    )


def _handle_mongo_error(exc: Exception) -> None:
    """Raise HTTP 503 with a clear message when MongoDB fails."""
    msg = str(exc)
    if "SSL" in msg or "handshake" in msg or "ServerSelectionTimeout" in msg:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable. MongoDB connection or SSL failed. Check MONGODB_URI and network.",
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Database error: {msg[:200]}",
    ) from exc


@router.get("/documents", response_model=ListDocumentsResponse)
async def list_documents(
    q: str | None = None,
    buyer: str | None = None,
    product: str | None = None,
    doc_type: str | None = None,
    product_type: str | None = None,
    batch_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> ListDocumentsResponse:
    """List documents with optional filters and pagination. Use 'q' to search buyer or product.
    product_type: 'chemical' | 'engineering'. batch_id: list all docs in a batch. from_date/to_date: ISO date (YYYY-MM-DD)."""
    query: dict[str, Any] = {}
    if q and q.strip():
        q_regex = {"$regex": q.strip(), "$options": "i"}
        query["$or"] = [
            {"buyer_name": q_regex},
            {"product_name": q_regex},
        ]
    else:
        if buyer:
            query["buyer_name"] = {"$regex": buyer, "$options": "i"}
        if product:
            query["product_name"] = {"$regex": product, "$options": "i"}
    if doc_type:
        query["doc_type"] = doc_type
    if product_type and product_type in ("chemical", "engineering"):
        query["product_type"] = product_type
    if batch_id and batch_id.strip():
        query["batch_id"] = batch_id.strip()
    if from_date or to_date:
        date_filter: dict[str, Any] = {}
        if from_date:
            try:
                start = dt.fromisoformat(from_date.strip() + "T00:00:00+00:00")
                date_filter["$gte"] = start
            except ValueError:
                pass
        if to_date:
            try:
                end = dt.fromisoformat(to_date.strip() + "T23:59:59.999999+00:00")
                date_filter["$lte"] = end
            except ValueError:
                pass
        if date_filter:
            query["created_at"] = date_filter

    try:
        total = documents_collection.count_documents(query)
        cursor = (
            documents_collection.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(min(limit, 100))
        )
        summaries: List[DocumentSummary] = []
        for d in cursor:
            summaries.append(
                DocumentSummary(
                    id=str(d["_id"]),
                    buyer_name=d["buyer_name"],
                    product_name=d["product_name"],
                    product_type=d["product_type"],
                    doc_type=d["doc_type"],
                    created_at=d["created_at"],
                    updated_at=d["updated_at"],
                    employee_name=d.get("employee_name"),
                    batch_id=d.get("batch_id"),
                )
            )
        return ListDocumentsResponse(documents=summaries, total=total)
    except PyMongoError as e:
        # Return 200 with empty list so the app still loads; frontend can show warning
        return ListDocumentsResponse(
            documents=[],
            total=0,
            warning="Database unavailable. Check MongoDB connection and SSL. Fix MONGODB_URI and restart.",
        )
    except HTTPException:
        raise
    except Exception as e:
        return ListDocumentsResponse(
            documents=[],
            total=0,
            warning=f"Database error: {str(e)[:150]}",
        )


@router.get("/documents/batches", response_model=ListBatchesResponse)
async def list_batches(
    q: str | None = None,
    product_type: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> ListBatchesResponse:
    """List one row per batch for dashboard. Only documents with batch_id are grouped."""
    match_query: dict[str, Any] = {"batch_id": {"$exists": True, "$nin": [None, ""]}}
    if product_type and product_type in ("chemical", "engineering"):
        match_query["product_type"] = product_type
    if from_date or to_date:
        date_filter: dict[str, Any] = {}
        if from_date:
            try:
                start = dt.fromisoformat(from_date.strip() + "T00:00:00+00:00")
                date_filter["$gte"] = start
            except ValueError:
                pass
        if to_date:
            try:
                end = dt.fromisoformat(to_date.strip() + "T23:59:59.999999+00:00")
                date_filter["$lte"] = end
            except ValueError:
                pass
        if date_filter:
            match_query["created_at"] = date_filter
    if q and q.strip():
        q_regex = {"$regex": q.strip(), "$options": "i"}
        match_query = {"$and": [match_query, {"$or": [{"buyer_name": q_regex}, {"product_name": q_regex}]}]}

    pipeline_count: List[dict[str, Any]] = [
        {"$match": match_query},
        {"$group": {"_id": "$batch_id"}},
        {"$count": "total"},
    ]
    pipeline_list: List[dict[str, Any]] = [
        {"$match": match_query},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$batch_id",
            "buyer_name": {"$first": "$buyer_name"},
            "product_name": {"$first": "$product_name"},
            "product_type": {"$first": "$product_type"},
            "employee_name": {"$first": "$employee_name"},
            "created_at": {"$first": "$created_at"},
        }},
        {"$sort": {"created_at": -1}},
        {"$skip": skip},
        {"$limit": min(limit, 100)},
    ]
    try:
        total_result = list(documents_collection.aggregate(pipeline_count))
        total = total_result[0]["total"] if total_result else 0
        cursor = documents_collection.aggregate(pipeline_list)
        batches: List[BatchSummary] = []
        for d in cursor:
            batches.append(
                BatchSummary(
                    batch_id=str(d["_id"]),
                    buyer_name=d.get("buyer_name") or "",
                    product_name=d.get("product_name") or "",
                    product_type=d.get("product_type") or "chemical",
                    employee_name=d.get("employee_name"),
                    created_at=d.get("created_at") or dt.now(),
                )
            )
        return ListBatchesResponse(batches=batches, total=total)
    except PyMongoError:
        return ListBatchesResponse(
            batches=[],
            total=0,
            warning="Database unavailable. Check MongoDB connection.",
        )
    except Exception as e:
        return ListBatchesResponse(
            batches=[],
            total=0,
            warning=f"Database error: {str(e)[:150]}",
        )


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: str) -> None:
    """Delete a single document by id."""
    try:
        oid = to_object_id(doc_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id")
    result = documents_collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.delete("/documents", status_code=status.HTTP_200_OK)
async def delete_documents_bulk(payload: BulkDeleteRequest) -> dict[str, int]:
    """Delete multiple documents by ids. Returns deleted count."""
    if not payload.ids:
        return {"deleted": 0}
    oids = []
    for id_str in payload.ids:
        try:
            oids.append(to_object_id(id_str))
        except ValueError:
            continue
    if not oids:
        return {"deleted": 0}
    result = documents_collection.delete_many({"_id": {"$in": oids}})
    return {"deleted": result.deleted_count}


@router.get("/documents/{doc_id}", response_model=DocumentInDB)
async def get_document(doc_id: str) -> DocumentInDB:
    oid: ObjectId
    try:
        oid = to_object_id(doc_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id")

    doc = documents_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _serialize_mongo_doc(doc)


@router.get("/terms", response_model=TermsResponse)
async def get_terms() -> TermsResponse:
    """Get editable Terms and Conditions for Chemical and Engineering. When DB has none, returns default from prompt."""
    try:
        doc = terms_collection.find_one({"_id": TERMS_DOC_ID})
    except Exception:
        return TermsResponse(chemical=DEFAULT_TERMS, engineering=DEFAULT_TERMS)
    if not doc:
        return TermsResponse(chemical=DEFAULT_TERMS, engineering=DEFAULT_TERMS)
    chemical = (doc.get("chemical") or "").strip()
    engineering = (doc.get("engineering") or "").strip()
    return TermsResponse(
        chemical=chemical or DEFAULT_TERMS,
        engineering=engineering or DEFAULT_TERMS,
    )


@router.put("/terms", response_model=TermsResponse)
async def update_terms(payload: TermsUpdateRequest) -> TermsResponse:
    """Update Terms and Conditions. Changes apply to all newly generated documents."""
    try:
        doc = terms_collection.find_one({"_id": TERMS_DOC_ID}) or {"chemical": "", "engineering": ""}
        if not isinstance(doc, dict):
            doc = {"chemical": "", "engineering": ""}
        updates = {}
        if payload.chemical is not None:
            updates["chemical"] = payload.chemical.strip()
        if payload.engineering is not None:
            updates["engineering"] = payload.engineering.strip()
        doc = {**doc, **updates, "_id": TERMS_DOC_ID}
        doc.setdefault("chemical", "")
        doc.setdefault("engineering", "")
        terms_collection.replace_one({"_id": TERMS_DOC_ID}, doc, upsert=True)
        return TermsResponse(
            chemical=doc.get("chemical", ""),
            engineering=doc.get("engineering", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.put("/documents/{doc_id}", response_model=DocumentInDB)
async def update_document(doc_id: str, payload: UpdateDocumentRequest) -> DocumentInDB:
    oid: ObjectId
    try:
        oid = to_object_id(doc_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id")

    res = documents_collection.find_one_and_update(
        {"_id": oid},
        {
            "$set": {
                "html_content": payload.html_content,
                "updated_at": now_local(),
            }
        },
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _serialize_mongo_doc(res)


def _sanitize_filename(s: str, max_len: int = 80) -> str:
    """Remove special chars, replace spaces with underscore."""
    import re
    s = re.sub(r'[<>:"/\\|?*]', '', str(s or ""))
    s = s.replace(" ", "_").replace(",", "_")
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:max_len]


@router.get("/documents/{doc_id}/pdf")
async def get_pdf(doc_id: str) -> Response:
    """Return document as PDF file. Filename by doc_type: QF_* for quotation, TDS_*, COA_*, MSDS_*."""
    import re
    from datetime import datetime

    oid: ObjectId
    try:
        oid = to_object_id(doc_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id")

    doc = documents_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    html = doc["html_content"]
    letterhead = doc.get("letterhead")
    try:
        pdf_bytes = html_to_pdf(html, letterhead=letterhead)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"PDF generation failed: {e}")

    buyer = _sanitize_filename(doc.get("buyer_name", "") or "Document")
    product = _sanitize_filename(doc.get("product_name", "") or "Document")
    doc_type = doc.get("doc_type", "document")

    if doc_type == "quotation":
        qno = _sanitize_filename(doc.get("quotation_no") or "Q", 30)
        company = _sanitize_filename(doc.get("company_name") or "Company", 30)
        filename = f"QF_{qno}_{company}_{buyer}_{product}.pdf"
    elif doc_type == "tds":
        filename = f"TDS_{product}.pdf"
    elif doc_type == "coa":
        filename = f"COA_{product}.pdf"
    elif doc_type == "msds":
        filename = f"MSDS_{product}.pdf"
    else:
        date_str = datetime.now().strftime("%d%m%Y")
        filename = f"{buyer}_{product}_{date_str}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

