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

from app.db.mongo import TERMS_DOC_ID, documents_collection, manual_documents_collection, now_local, terms_collection, to_object_id
from app.schemas.document import (
    BatchSummary,
    BulkDeleteRequest,
    CreateManualDocumentRequest,
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


def _strip_signatory_from_terms(text: str) -> str:
    """Remove AUTHORIZED SIGNATORY / Place & Date block from terms. Terms page must not show signatory."""
    if not text or not text.strip():
        return text
    upper = text.upper()
    idx = upper.find("AUTHORIZED SIGNATORY")
    if idx == -1:
        idx = upper.find("AUTHORIZED SIGNED")
    if idx != -1:
        # Keep only content before the signatory block; trim trailing newlines/spaces
        text = text[:idx].rstrip()
    return text
from app.services.export import html_to_pdf
from app.utils.excel_parser import parse_excel_to_previews

# In-memory job store: job_id -> {"status": "running"|"done", "queue": Queue, "cancelled": bool}
_job_store: dict[str, dict[str, Any]] = {}
# Max events to keep per job so late-joining clients get something
_JOB_QUEUE_MAX = 500


def _run_batch_sync(job_id: str, rows: list[RowPreview]) -> None:
    """Run in thread: generate docs for each row, push to job queue. Stops if job is cancelled."""
    store = _job_store.get(job_id)
    if not store or store["status"] == "done":
        return
    q: Queue = store["queue"]
    total_rows = len(rows)
    inserted_count = 0
    try:
        for row_idx, row in enumerate(rows):
            if store.get("cancelled"):
                break
            row_label = f"{getattr(row, 'buyer_name', '?')}/{getattr(row, 'product_name', '?')}"
            try:
                docs_to_insert = generate_documents_for_row(row)
            except Exception as gen_err:
                try:
                    q.put_nowait({"error": f"Generation failed for {row_label}: {gen_err}"})
                except Exception:
                    pass
                continue
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
                    "quantity": getattr(doc, "quantity", None),
                    "unit": getattr(doc, "unit", None),
                    "country": getattr(doc, "country", None),
                    "port": getattr(doc, "port", None),
                    "incoterm": getattr(doc, "incoterm", None),
                    "payment_terms": getattr(doc, "payment_terms", None),
                    "remarks": getattr(doc, "remarks", None),
                }
                try:
                    result = documents_collection.insert_one(mongo_doc)
                    inserted = documents_collection.find_one({"_id": result.inserted_id})
                except Exception as db_err:
                    try:
                        q.put_nowait({"error": f"DB insert failed for {doc.doc_type} ({row_label}): {db_err}"})
                    except Exception:
                        pass
                    continue
                if inserted:
                    inserted_count += 1
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
    except Exception as e:
        try:
            q.put_nowait({"error": f"Batch failed: {e}"})
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
        quantity=doc.get("quantity"),
        unit=doc.get("unit"),
        country=doc.get("country"),
        port=doc.get("port"),
        incoterm=doc.get("incoterm"),
        payment_terms=doc.get("payment_terms"),
        remarks=doc.get("remarks"),
    )


@router.post("/documents/manual", response_model=DocumentInDB)
async def create_manual_document(payload: CreateManualDocumentRequest) -> DocumentInDB:
    """Create a blank document manually (no AI). Returns DocumentInDB for redirect to editor."""
    from datetime import timezone
    now = dt.now(timezone.utc)
    batch_id = f"manual-{uuid.uuid4()}"
    letterhead = (payload.letterhead or "").strip().lower() or None
    local_export = (payload.local_export or "").strip().lower() or None
    mongo_doc = {
        "buyer_name": payload.buyer_name,
        "product_name": payload.product_name,
        "product_type": payload.product_type,
        "doc_type": payload.doc_type,
        "html_content": payload.html_content,
        "letterhead": letterhead if letterhead in ("india", "dubai") else None,
        "local_export": local_export,
        "batch_id": batch_id,
        "created_at": now,
        "updated_at": now,
        "employee_name": None,
        "quotation_no": None,
        "company_name": None,
        "quantity": None,
        "unit": None,
        "country": None,
        "port": None,
        "incoterm": None,
        "payment_terms": None,
        "remarks": None,
    }
    result = manual_documents_collection.insert_one(mongo_doc)
    inserted = manual_documents_collection.find_one({"_id": result.inserted_id})
    if not inserted:
        raise HTTPException(status_code=500, detail="Failed to create document")
    return _serialize_mongo_doc(inserted)


def _find_doc_by_id(oid: ObjectId) -> tuple[Any, str | None]:
    """Return (doc, 'documents'|'manual_documents') or (None, None)."""
    doc = documents_collection.find_one({"_id": oid})
    if doc:
        return doc, "documents"
    doc = manual_documents_collection.find_one({"_id": oid})
    if doc:
        return doc, "manual_documents"
    return None, None


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
    _job_store[job_id] = {"status": "running", "queue": q, "cancelled": False}
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


@router.post("/jobs/{job_id}/cancel")
async def job_cancel(job_id: str) -> dict[str, Any]:
    """Mark job as cancelled. The running batch will stop after the current row; stream will receive 'done'."""
    if job_id not in _job_store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _job_store[job_id]["cancelled"] = True
    return {"job_id": job_id, "cancelled": True}


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
                "quantity": getattr(doc, "quantity", None),
                "unit": getattr(doc, "unit", None),
                "country": getattr(doc, "country", None),
                "port": getattr(doc, "port", None),
                "incoterm": getattr(doc, "incoterm", None),
                "payment_terms": getattr(doc, "payment_terms", None),
                "remarks": getattr(doc, "remarks", None),
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
    manual: bool = False,
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
    if manual:
        # Manual docs: only from manual_documents collection (separate dashboard)
        query_manual_coll = {k: v for k, v in query.items() if k != "batch_id"}
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
            if manual:
                query_manual_coll["created_at"] = date_filter

    try:
        if manual:
            # Manual docs dashboard: only manual_documents collection
            total = manual_documents_collection.count_documents(query_manual_coll)
            cursor = (
                manual_documents_collection.find(query_manual_coll)
                .sort("created_at", -1)
                .skip(skip)
                .limit(min(limit, 100))
            )
            summaries = [
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
                for d in cursor
            ]
            return ListDocumentsResponse(documents=summaries, total=total)
        collection = documents_collection
        total = collection.count_documents(query)
        cursor = (
            collection.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(min(limit, 100))
        )
        summaries = [
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
            for d in cursor
        ]
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
    """List one row per batch for dashboard. Only non-manual batches (manual docs have their own dashboard)."""
    match_query: dict[str, Any] = {
        "batch_id": {"$exists": True, "$nin": [None, ""]},
        "$and": [{"batch_id": {"$not": {"$regex": "^manual-"}}}],
    }
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
            "letterhead": {"$first": "$letterhead"},
            "local_export": {"$first": "$local_export"},
            "company_name": {"$first": "$company_name"},
            "quantity": {"$first": "$quantity"},
            "unit": {"$first": "$unit"},
            "country": {"$first": "$country"},
            "port": {"$first": "$port"},
            "incoterm": {"$first": "$incoterm"},
            "payment_terms": {"$first": "$payment_terms"},
            "remarks": {"$first": "$remarks"},
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
                    letterhead=d.get("letterhead"),
                    local_export=d.get("local_export"),
                    company_name=d.get("company_name"),
                    quantity=d.get("quantity"),
                    unit=d.get("unit"),
                    country=d.get("country"),
                    port=d.get("port"),
                    incoterm=d.get("incoterm"),
                    payment_terms=d.get("payment_terms"),
                    remarks=d.get("remarks"),
                )
            )
        return ListBatchesResponse(batches=batches, total=total)
    except PyMongoError as e:
        return ListBatchesResponse(
            batches=[],
            total=0,
            warning=f"Database unavailable: {str(e)[:200]}",
        )
    except Exception as e:
        return ListBatchesResponse(
            batches=[],
            total=0,
            warning=f"Database error: {str(e)[:200]}",
        )


@router.delete("/documents/batches/{batch_id}", status_code=status.HTTP_200_OK)
async def delete_batch(batch_id: str) -> dict[str, int]:
    """Delete all documents in a batch. Returns deleted count."""
    if not batch_id or not batch_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch id required")
    try:
        result = documents_collection.delete_many({"batch_id": batch_id.strip()})
        return {"deleted": result.deleted_count}
    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error",
        ) from e


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: str) -> None:
    """Delete a single document by id (checks both documents and manual_documents)."""
    try:
        oid = to_object_id(doc_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id")
    result = documents_collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        result = manual_documents_collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.delete("/documents", status_code=status.HTTP_200_OK)
async def delete_documents_bulk(payload: BulkDeleteRequest) -> dict[str, int]:
    """Delete multiple documents by ids (checks both collections). Returns deleted count."""
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
    r1 = documents_collection.delete_many({"_id": {"$in": oids}})
    r2 = manual_documents_collection.delete_many({"_id": {"$in": oids}})
    return {"deleted": r1.deleted_count + r2.deleted_count}


@router.get("/documents/{doc_id}", response_model=DocumentInDB)
async def get_document(doc_id: str) -> DocumentInDB:
    oid: ObjectId
    try:
        oid = to_object_id(doc_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id")

    doc, _ = _find_doc_by_id(oid)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _serialize_mongo_doc(doc)


@router.get("/terms", response_model=TermsResponse)
async def get_terms() -> TermsResponse:
    """Get editable Terms and Conditions for Chemical and Engineering. Signatory block is stripped for the Terms page."""
    try:
        doc = terms_collection.find_one({"_id": TERMS_DOC_ID})
    except Exception:
        return TermsResponse(
            chemical=_strip_signatory_from_terms(DEFAULT_TERMS),
            engineering=_strip_signatory_from_terms(DEFAULT_TERMS),
        )
    if not doc:
        return TermsResponse(
            chemical=_strip_signatory_from_terms(DEFAULT_TERMS),
            engineering=_strip_signatory_from_terms(DEFAULT_TERMS),
        )
    chemical = (doc.get("chemical") or "").strip()
    engineering = (doc.get("engineering") or "").strip()
    return TermsResponse(
        chemical=_strip_signatory_from_terms(chemical or DEFAULT_TERMS),
        engineering=_strip_signatory_from_terms(engineering or DEFAULT_TERMS),
    )


@router.put("/terms", response_model=TermsResponse)
async def update_terms(payload: TermsUpdateRequest) -> TermsResponse:
    """Update Terms and Conditions. Signatory block is stripped so it is not stored or shown on Terms page."""
    try:
        doc = terms_collection.find_one({"_id": TERMS_DOC_ID}) or {"chemical": "", "engineering": ""}
        if not isinstance(doc, dict):
            doc = {"chemical": "", "engineering": ""}
        updates = {}
        if payload.chemical is not None:
            updates["chemical"] = _strip_signatory_from_terms(payload.chemical.strip())
        if payload.engineering is not None:
            updates["engineering"] = _strip_signatory_from_terms(payload.engineering.strip())
        doc = {**doc, **updates, "_id": TERMS_DOC_ID}
        doc.setdefault("chemical", "")
        doc.setdefault("engineering", "")
        terms_collection.replace_one({"_id": TERMS_DOC_ID}, doc, upsert=True)
        return TermsResponse(
            chemical=_strip_signatory_from_terms(doc.get("chemical", "")),
            engineering=_strip_signatory_from_terms(doc.get("engineering", "")),
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

    set_fields: dict = {"html_content": payload.html_content, "updated_at": now_local()}
    if payload.product_name is not None:
        set_fields["product_name"] = payload.product_name.strip() or "Manual Document"
    if payload.employee_name is not None:
        set_fields["employee_name"] = payload.employee_name.strip() or None

    _, which = _find_doc_by_id(oid)
    if not which:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    coll = manual_documents_collection if which == "manual_documents" else documents_collection
    res = coll.find_one_and_update(
        {"_id": oid},
        {"$set": set_fields},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _serialize_mongo_doc(res)


def _sanitize_filename(s: str, max_len: int = 80) -> str:
    """Remove special/non-ASCII chars, replace spaces with underscore."""
    import re
    s = re.sub(r'[^\x20-\x7E]', '', str(s or ""))  # keep only printable ASCII
    s = re.sub(r'[<>:"/\\|?*]', '', s)
    s = s.replace(" ", "_").replace(",", "_")
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:max_len] or "Document"


def _extract_quotation_no_from_html(html: str) -> str | None:
    """Try to extract quotation number from document HTML (e.g. Quotation No|AC/001/26/03 or table cell)."""
    if not html:
        return None
    import re
    # Pattern: "Quotation No" then optional pipes/tags/spaces then value (e.g. AC/001/26/03)
    m = re.search(
        r"Quotation\s+No[\s|</>td=:\-]*([A-Za-z0-9/_-]{3,})",
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return None


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

    doc, which = _find_doc_by_id(oid)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    html = doc.get("html_content") or ""
    if not html.strip():
        html = "<p>&nbsp;</p>"
    letterhead = doc.get("letterhead")
    local_export = doc.get("local_export")
    try:
        pdf_bytes = html_to_pdf(html, letterhead=letterhead, local_export=local_export)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"PDF generation failed: {e}")

    product = _sanitize_filename(doc.get("product_name", "") or "Document")

    if which == "manual_documents":
        filename = f"{product}.pdf"
    else:
        buyer = _sanitize_filename(doc.get("buyer_name", "") or "Document")
        doc_type = doc.get("doc_type", "document")
        if doc_type == "quotation":
            qno_raw = doc.get("quotation_no") or _extract_quotation_no_from_html(html) or "Q"
            qno = _sanitize_filename(qno_raw, 30)
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

