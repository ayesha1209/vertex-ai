import asyncio
import json
import logging
import time
import uuid
from datetime import datetime as dt, timedelta
from queue import Empty, Queue
from typing import Any, List

from bson import ObjectId
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pymongo.errors import PyMongoError

from app.db.mongo import TERMS_DOC_ID, documents_collection, jobs_collection, manual_documents_collection, now_local, terms_collection, to_object_id

logger = logging.getLogger(__name__)
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
from app.services.export import html_to_pdf
from app.services.invoice_generator import build_invoice_document, extract_quotation_data
from app.utils.excel_parser import parse_excel_to_previews
from app.utils.memory import release_memory


def _strip_signatory_from_terms(text: str) -> str:
    """Remove AUTHORIZED SIGNATORY / Place & Date block from terms. Terms page must not show signatory."""
    if not text or not text.strip():
        return text
    upper = text.upper()
    idx = upper.find("AUTHORIZED SIGNATORY")
    if idx == -1:
        idx = upper.find("AUTHORIZED SIGNED")
    if idx != -1:
        text = text[:idx].rstrip()
    return text


# ---------------------------------------------------------------------------
# In-memory job store and batch queue
# job_id -> {"status": "queued"|"running"|"done", "queue": Queue, "rows": list[dict],
#            "started": asyncio.Event, "cancelled": bool, "finished_at": float|None, ...}
# Workers pull from _pending_batch_queue (max 2 concurrent); everyone can submit (up to cap).
# ---------------------------------------------------------------------------
_job_store: dict[str, dict[str, Any]] = {}
# Max events buffered per job so late-joining clients get something
_JOB_QUEUE_MAX = 500
# Jobs are kept for this many seconds after finishing, then evicted
_JOB_TTL_SECONDS = 300  # 5 minutes

# Concurrency limiters — prevent simultaneous heavy operations from exhausting RAM
# PDF generation: at most 3 concurrent (WeasyPrint is ~40-80 MB each)
_PDF_SEMAPHORE = asyncio.Semaphore(3)
# Batch generation: 2 workers process queue; no 503 for "busy", only when store is full
_BATCH_SEMAPHORE = asyncio.Semaphore(2)
# Upload/parse: at most 3 concurrent pandas loads
_UPLOAD_SEMAPHORE = asyncio.Semaphore(3)

# Pending batch jobs: (job_id,) put when user submits; 2 workers pull and run
_pending_batch_queue: asyncio.Queue[str] = asyncio.Queue()
_batch_worker_tasks: list[asyncio.Task[Any]] = []
_worker_shutdown = asyncio.Event()

# Max jobs in store (queued + running + recently done). Prevents unbounded memory.
_JOB_STORE_MAX_SIZE = 50

# ---------------------------------------------------------------------------
# Durable job status in MongoDB, alongside the in-memory store above.
#
# The in-memory store remains the fast path for the live SSE event stream (which is
# inherently tied to this one process's Queue) — this durable layer exists so that
# status/cancel/stream requests that land on a process that DIDN'T create the job
# (this process restarted, or a different instance handled the request) get an honest
# "interrupted" answer instead of a bare, unexplained 404 or a job that looks stuck
# "running" forever. It does not resume in-flight generation after a restart — the
# rows already inserted into `documents_collection` before a crash are not lost, but
# any row not yet started when the process died still needs to be resubmitted.
# ---------------------------------------------------------------------------


def _job_persist(job_id: str, **fields: Any) -> None:
    """Best-effort durable status write. Never raises — a Mongo hiccup shouldn't break
    the in-memory-tracked generation flow, which remains authoritative for this process."""
    try:
        jobs_collection.update_one(
            {"_id": job_id},
            {"$set": {**fields, "updated_at": now_local()}, "$setOnInsert": {"created_at": now_local()}},
            upsert=True,
        )
    except Exception:
        logger.exception("Failed to persist job status for %s (fields=%r)", job_id, fields)


def _reconcile_orphaned_jobs() -> None:
    """On worker startup, mark any job left "queued"/"running" in Mongo from a previous
    process lifetime as "interrupted" — a crash/restart mid-batch otherwise leaves it
    looking permanently "running" to anyone who queries status later."""
    try:
        jobs_collection.update_many(
            {"status": {"$in": ["queued", "running"]}},
            {"$set": {"status": "interrupted", "updated_at": now_local()}},
        )
    except Exception:
        logger.exception("Failed to reconcile orphaned jobs on startup")

# Max upload file size: 5 MB
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Max rows per upload preview and per batch to avoid OOM
_MAX_ROWS_PREVIEW = 500
_MAX_ROWS_PER_BATCH = 150


def _parse_date_range(from_date: str | None, to_date: str | None) -> tuple[dt | None, dt | None]:
    """Parse from_date and to_date (YYYY-MM-DD). Return (start_utc, end_utc_exclusive) for MongoDB.
    Inclusive of both days: start = from_date 00:00:00 UTC, end = to_date+1 00:00:00 UTC (use $lt).
    If from_date > to_date, swap so the range always makes sense.
    """
    def parse(s: str) -> dt | None:
        s = s.strip()
        if not s:
            return None
        try:
            return dt.fromisoformat(s + "T00:00:00+00:00")
        except ValueError:
            return None

    start_d = parse(from_date) if from_date else None
    end_d = parse(to_date) if to_date else None
    if start_d is not None and end_d is not None and start_d > end_d:
        start_d, end_d = end_d, start_d
    if start_d is None and end_d is None:
        return (None, None)
    # Inclusive end of day: use start of next day as exclusive end
    if end_d is not None:
        end_exclusive = end_d + timedelta(days=1)
    else:
        end_exclusive = None
    return (start_d, end_exclusive)


def _evict_old_jobs() -> None:
    """Remove finished jobs older than _JOB_TTL_SECONDS from _job_store."""
    now = time.monotonic()
    to_delete = [
        jid for jid, s in list(_job_store.items())
        if s.get("status") == "done" and s.get("finished_at") is not None
        and (now - s["finished_at"]) > _JOB_TTL_SECONDS
    ]
    for jid in to_delete:
        _job_store.pop(jid, None)


async def _batch_worker() -> None:
    """One of 2 workers: pull job_id from queue, run batch in executor, then loop."""
    while not _worker_shutdown.is_set():
        try:
            job_id = await asyncio.wait_for(_pending_batch_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        store = _job_store.get(job_id)
        if not store or store.get("status") != "queued":
            continue
        store["status"] = "running"
        _job_persist(job_id, status="running")
        started_ev = store.get("started")
        if started_ev is not None:
            started_ev.set()
        if store.get("cancelled"):
            try:
                store["queue"].put_nowait("done")
            except Exception:
                pass
            store["status"] = "done"
            store["finished_at"] = time.monotonic()
            _job_persist(job_id, status="done", cancelled=True)
            continue
        rows_data = store.get("rows") or []
        try:
            rows = [RowPreview(**r) for r in rows_data]
        except Exception:
            rows = []
        # Free memory: drop serialized rows from store once we have the list
        try:
            del store["rows"]
        except KeyError:
            pass
        if not rows:
            try:
                store["queue"].put_nowait("done")
            except Exception:
                pass
            store["status"] = "done"
            store["finished_at"] = time.monotonic()
            _job_persist(job_id, status="done")
            continue
        try:
            async with _BATCH_SEMAPHORE:
                await asyncio.get_event_loop().run_in_executor(
                    None, _run_batch_sync, job_id, rows
                )
        except Exception:
            try:
                store["queue"].put_nowait("done")
            except Exception:
                pass
        finally:
            store["status"] = "done"
            store["finished_at"] = time.monotonic()
            _job_persist(job_id, status="done")


def start_batch_workers() -> None:
    """Start 2 background workers that process the batch queue. Call from app lifespan."""
    _worker_shutdown.clear()
    _reconcile_orphaned_jobs()
    for _ in range(2):
        t = asyncio.create_task(_batch_worker())
        _batch_worker_tasks.append(t)


async def stop_batch_workers() -> None:
    """Signal workers to stop and cancel their tasks. Call from app lifespan shutdown."""
    _worker_shutdown.set()
    for t in _batch_worker_tasks:
        t.cancel()
    if _batch_worker_tasks:
        await asyncio.gather(*_batch_worker_tasks, return_exceptions=True)
    _batch_worker_tasks.clear()


def _run_batch_sync(job_id: str, rows: list[RowPreview]) -> None:
    """Run in thread: generate docs for each row, push to job queue. Stops if job is cancelled."""
    store = _job_store.get(job_id)
    if not store or store["status"] == "done":
        return
    q: Queue = store["queue"]
    total_rows = len(rows)
    inserted_count = 0
    # Send a start event so the frontend knows the total before any docs arrive
    try:
        q.put_nowait({"type": "start", "total_rows": total_rows})
    except Exception:
        pass
    try:
        for row_idx, row in enumerate(rows):
            if store.get("cancelled"):
                break
            row_label = f"{getattr(row, 'buyer_name', '?')}/{getattr(row, 'product_name', '?')}"
            # Notify frontend which row is being processed
            try:
                q.put_nowait({
                    "type": "row_start",
                    "row_index": row_idx,
                    "total_rows": total_rows,
                    "buyer_name": getattr(row, "buyer_name", "") or "",
                    "product_name": getattr(row, "product_name", "") or "",
                })
            except Exception:
                pass
            try:
                docs_to_insert = generate_documents_for_row(row)
            except Exception as gen_err:
                try:
                    q.put_nowait({"error": f"Generation failed for {row_label}: {gen_err}"})
                except Exception:
                    pass
                continue
            finally:
                # Row generation goes through pandas/OpenAI/prompt-building, which
                # fragments the native heap; trim per row so a long batch doesn't
                # creep the process toward the instance's memory ceiling.
                release_memory()
            row_batch_id = getattr(docs_to_insert[0], "batch_id", None) if docs_to_insert else None
            if row_batch_id:
                # So a client that lost the live SSE stream (reconnect, or this process
                # restarted) can still recover this row's results via the existing
                # GET /documents?batch_id=... endpoint instead of getting nothing back.
                try:
                    jobs_collection.update_one({"_id": job_id}, {"$addToSet": {"batch_ids": row_batch_id}})
                except Exception:
                    logger.exception("Failed to record batch_id %s for job %s", row_batch_id, job_id)
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
                    "email_id": getattr(row, "email_id", None),
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
            _job_persist(job_id, processed_count=row_idx + 1, total_rows=total_rows)
    except Exception as e:
        try:
            q.put_nowait({"error": f"Batch failed: {e}"})
        except Exception:
            pass
    finally:
        store["status"] = "done"
        store["finished_at"] = time.monotonic()
        _job_persist(job_id, status="done", cancelled=bool(store.get("cancelled")), inserted_count=inserted_count)
        try:
            q.put_nowait("done")
        except Exception:
            pass
        _evict_old_jobs()


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
async def upload_preview(request: Request, file: UploadFile = File(...)) -> UploadPreviewResponse:
    """Upload Excel/CSV and return a clean preview of rows to the frontend."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    async with _UPLOAD_SEMAPHORE:
        try:
            previews = parse_excel_to_previews(file, max_rows=_MAX_ROWS_PREVIEW)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error reading file: {str(exc)[:200]}",
            ) from exc
        finally:
            # pandas/openpyxl decompress and hold the whole workbook in native
            # memory; trim it back so repeated uploads don't ratchet up RSS.
            release_memory()
    return UploadPreviewResponse(rows=previews)


@router.post("/generate-batch", response_model=GenerateBatchResponse)
async def generate_batch(payload: GenerateBatchRequest) -> GenerateBatchResponse:
    """Queue batch generation. Returns job_id immediately. Use GET /jobs/{job_id}/stream for SSE.
    Jobs are processed in order (max 2 concurrent). 503 only when queue/store is full."""
    if not payload.rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No rows provided")
    if len(payload.rows) > _MAX_ROWS_PER_BATCH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many rows. Maximum {_MAX_ROWS_PER_BATCH} per batch. Split your file or select fewer rows.",
        )

    _evict_old_jobs()

    if len(_job_store) >= _JOB_STORE_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Too many generation jobs in queue. Please try again in a few minutes.",
        )

    job_id = str(uuid.uuid4())
    q: Queue = Queue(maxsize=_JOB_QUEUE_MAX)
    started_ev = asyncio.Event()
    _job_store[job_id] = {
        "status": "queued",
        "queue": q,
        "started": started_ev,
        "rows": [r.model_dump() for r in payload.rows],
        "cancelled": False,
        "finished_at": None,
        "total_rows": len(payload.rows),
    }
    _job_persist(job_id, status="queued", total_rows=len(payload.rows), processed_count=0, cancelled=False)

    await _pending_batch_queue.put(job_id)
    return GenerateBatchResponse(job_id=job_id)


@router.get("/jobs/{job_id}/stream")
async def job_stream(job_id: str) -> StreamingResponse:
    """SSE stream: events 'document' (with doc payload) and 'done'.
    Note: the live stream itself is in-memory per process. If this process doesn't own the
    job (it restarted, or a different instance received the request), fall back to the
    Mongo-persisted status: a job already "done" gets a synthetic 'done' event with the
    batch_ids it produced (so the client can still fetch results via GET /documents), and
    anything else gets an honest "interrupted" message instead of a bare, unexplained 404.
    """
    if job_id not in _job_store:
        try:
            persisted = jobs_collection.find_one({"_id": job_id})
        except Exception:
            logger.exception("Failed to look up persisted job %s", job_id)
            persisted = None
        if persisted is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found or expired. Start generation again from the Preview page.",
            )

        async def fallback_gen() -> Any:
            if persisted.get("status") == "done":
                yield f"data: {json.dumps({'type': 'done', 'batch_ids': persisted.get('batch_ids', [])})}\n\n"
            else:
                yield (
                    "data: "
                    + json.dumps({
                        "type": "error",
                        "message": "This job was interrupted (the server restarted mid-batch). Please start generation again.",
                    })
                    + "\n\n"
                )
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            fallback_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    store = _job_store[job_id]
    q: Queue = store["queue"]
    started_ev = store.get("started")

    async def event_gen() -> Any:
        try:
            if store["status"] == "done":
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            # If job is still queued, tell client and wait until a worker starts it (or it finishes/dies)
            if store.get("status") == "queued" and started_ev is not None:
                yield f"data: {json.dumps({'type': 'queued', 'message': 'Waiting in queue…'})}\n\n"
                try:
                    await asyncio.wait_for(started_ev.wait(), timeout=120.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Queue wait timed out'})}\n\n"
                    return
                if store.get("status") == "done":
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
                # If item already has a 'type' field it's a control event (start, row_start, error)
                if isinstance(item, dict) and "type" in item:
                    yield f"data: {json.dumps(item)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'document', 'doc': item})}\n\n"
        finally:
            # Once the client stream ends (done or disconnected), schedule cleanup
            # after TTL so any reconnecting client can still get 404 gracefully.
            store["finished_at"] = store.get("finished_at") or time.monotonic()
            _evict_old_jobs()

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
    if job_id in _job_store:
        _job_store[job_id]["cancelled"] = True
        _job_persist(job_id, cancelled=True)
        return {"job_id": job_id, "cancelled": True}
    # Not owned by this process (restarted, or a different instance) — still record the
    # cancel intent durably, even though nothing here can actually stop generation that's
    # running elsewhere or already dead.
    try:
        result = jobs_collection.update_one(
            {"_id": job_id}, {"$set": {"cancelled": True, "updated_at": now_local()}}
        )
    except Exception as exc:
        logger.exception("Failed to persist cancel for job %s", job_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return {"job_id": job_id, "cancelled": True}


@router.get("/jobs/{job_id}/status")
async def job_status(job_id: str) -> dict[str, Any]:
    """Return job status (queued | running | done | interrupted). Falls back to the
    Mongo-persisted record for late-joining clients or a process that didn't create the job."""
    if job_id in _job_store:
        return {"job_id": job_id, "status": _job_store[job_id]["status"]}
    try:
        persisted = jobs_collection.find_one({"_id": job_id})
    except Exception:
        logger.exception("Failed to look up persisted job %s", job_id)
        persisted = None
    if persisted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    status_val = persisted.get("status")
    if status_val in ("queued", "running"):
        # This process has no memory of it, so whichever process owned it is gone.
        status_val = "interrupted"
    return {
        "job_id": job_id,
        "status": status_val,
        "processed_count": persisted.get("processed_count"),
        "total_rows": persisted.get("total_rows"),
        "batch_ids": persisted.get("batch_ids", []),
    }


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
    date_start_utc, date_end_exclusive_utc = _parse_date_range(from_date, to_date)
    if date_start_utc is not None or date_end_exclusive_utc is not None:
        date_filter: dict[str, Any] = {}
        if date_start_utc is not None:
            date_filter["$gte"] = date_start_utc
        if date_end_exclusive_utc is not None:
            date_filter["$lt"] = date_end_exclusive_utc
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


@router.get("/documents/batches/entered-by")
async def list_batches_entered_by() -> list[str]:
    """Return distinct 'entered by' (employee_name) values for dashboard filter dropdown."""
    try:
        pipeline: List[dict[str, Any]] = [
            {"$match": {"$and": [
                {"batch_id": {"$exists": True, "$nin": [None, ""]}},
                {"batch_id": {"$not": {"$regex": "^manual-"}}},
            ]}},
            {"$group": {"_id": "$employee_name"}},
            {"$match": {"_id": {"$nin": [None, ""]}}},
            {"$sort": {"_id": 1}},
            {"$project": {"_id": 0, "name": "$_id"}},
        ]
        cursor = documents_collection.aggregate(pipeline)
        return [str(d.get("name", "")) for d in cursor if d.get("name")]
    except PyMongoError:
        return []


@router.get("/documents/batches", response_model=ListBatchesResponse)
async def list_batches(
    q: str | None = None,
    product_type: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    entered_by: str | None = None,
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
    if entered_by and entered_by.strip():
        match_query["employee_name"] = entered_by.strip()
    date_start_utc, date_end_exclusive_utc = _parse_date_range(from_date, to_date)
    if date_start_utc is not None or date_end_exclusive_utc is not None:
        date_filter: dict[str, Any] = {}
        if date_start_utc is not None:
            date_filter["$gte"] = date_start_utc
        if date_end_exclusive_utc is not None:
            date_filter["$lt"] = date_end_exclusive_utc
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
        # Sort ascending by _id (insertion order) so the quotation — always inserted first —
        # is picked by $first. This ensures multi-product batches show the full comma-separated
        # product list from the quotation rather than a single-product TDS/COA name.
        {"$sort": {"_id": 1}},
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


_INVOICE_DOC_TYPES = ["proforma_invoice", "invoice", "commercial_invoice", "tax_invoice"]


@router.get("/documents/batch/{batch_id}/invoices", response_model=ListDocumentsResponse)
async def list_batch_invoices(batch_id: str) -> ListDocumentsResponse:
    """Return proforma invoices, invoices, commercial invoices and tax invoices that belong to a batch."""
    if not batch_id or not batch_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch id required")
    try:
        cursor = documents_collection.find(
            {"batch_id": batch_id.strip(), "doc_type": {"$in": _INVOICE_DOC_TYPES}},
            sort=[("doc_type", 1), ("created_at", 1)],
        )
        docs: List[DocumentSummary] = []
        for d in cursor:
            docs.append(
                DocumentSummary(
                    id=str(d["_id"]),
                    buyer_name=d.get("buyer_name", ""),
                    product_name=d.get("product_name", ""),
                    product_type=d.get("product_type", "chemical"),
                    doc_type=d.get("doc_type", "invoice"),
                    created_at=d.get("created_at", dt.now()),
                    updated_at=d.get("updated_at", dt.now()),
                    employee_name=d.get("employee_name"),
                    batch_id=d.get("batch_id"),
                )
            )
        return ListDocumentsResponse(documents=docs, total=len(docs))
    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database error: {e}",
        ) from e


@router.post("/documents/batch/{batch_id}/invoices/generate", response_model=ListDocumentsResponse)
async def generate_batch_invoices(batch_id: str) -> ListDocumentsResponse:
    """Generate (or re-generate) Proforma Invoice + Invoice + Commercial/Tax Invoice for a batch.

    Finds the quotation for the batch, derives all document variants from it,
    persists them, and returns them. Existing invoice-family docs for this
    batch are replaced. Commercial Invoice is generated for export sales,
    Tax Invoice for domestic/GST sales (based on the quotation's local_export).
    """
    if not batch_id or not batch_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch id required")

    batch_id = batch_id.strip()

    # Find the quotation for this batch
    quotation = documents_collection.find_one(
        {"batch_id": batch_id, "doc_type": "quotation"},
        sort=[("created_at", 1)],
    )
    if not quotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No quotation found for this batch. Generate the batch documents first.",
        )

    source_html: str = quotation.get("html_content") or ""
    if not source_html.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quotation HTML is empty; cannot generate invoices.",
        )

    local_export: str | None = quotation.get("local_export")
    is_local = (local_export or "").strip().lower() == "local"

    # Build all HTML variants — same box layout for all four, via build_invoice_document.
    # Extract the quotation's data once and reuse it across all 3 calls rather than
    # letting each one independently re-scan the same source_html for the same tables.
    common_invoice_kwargs: dict[str, Any] = dict(
        invoice_no=quotation.get("quotation_no"),
        buyer_name=quotation.get("buyer_name"),
        country=quotation.get("country"),
        port=quotation.get("port"),
        incoterm=quotation.get("incoterm"),
        payment_terms=quotation.get("payment_terms"),
    )
    extracted = extract_quotation_data(source_html)
    ci_or_tax_type = "tax_invoice" if is_local else "commercial_invoice"

    # Delete existing invoice-family docs for this batch
    documents_collection.delete_many(
        {"batch_id": batch_id, "doc_type": {"$in": _INVOICE_DOC_TYPES}}
    )

    now = now_local()
    common: dict[str, Any] = {
        k: quotation.get(k)
        for k in (
            "buyer_name", "product_name", "product_type", "employee_name",
            "letterhead", "quotation_no", "company_name", "local_export",
            "quantity", "unit", "country", "port", "incoterm",
            "payment_terms", "remarks",
        )
    }
    common["batch_id"] = batch_id
    common["created_at"] = now
    common["updated_at"] = now

    docs_to_insert = [
        {
            **common,
            "doc_type": dt,
            "html_content": build_invoice_document(
                source_html, dt, local_export, extracted=extracted, **common_invoice_kwargs
            ),
        }
        for dt in ("proforma_invoice", "invoice", ci_or_tax_type)
    ]

    result = documents_collection.insert_many(docs_to_insert)
    inserted_ids = result.inserted_ids

    created: List[DocumentSummary] = []
    for oid, d in zip(inserted_ids, docs_to_insert):
        created.append(
            DocumentSummary(
                id=str(oid),
                buyer_name=d.get("buyer_name", ""),
                product_name=d.get("product_name", ""),
                product_type=d.get("product_type", "chemical"),
                doc_type=d.get("doc_type", "invoice"),
                created_at=now,
                updated_at=now,
                employee_name=d.get("employee_name"),
                batch_id=batch_id,
            )
        )
    return ListDocumentsResponse(documents=created, total=len(created))


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
async def get_pdf(doc_id: str, seq: int | None = None) -> Response:
    """Return document as PDF file. Optional ?seq=N overrides the quotation/invoice number with VERT/N/YEAR."""
    import re
    from datetime import datetime
    from app.utils.quotation_number import build_quotation_no

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

    # If caller supplies a sequence number, replace the quotation/invoice number in HTML
    if seq is not None and 1 <= seq <= 9999:
        new_qno = build_quotation_no(seq)
        # Quotation layout: label and value are adjacent <td> cells —
        # <td>Quotation No</td><td>VALUE</td>
        html = re.sub(
            r"(<td[^>]*>\s*(?:Quotation|Proforma\s+Invoice|Invoice)\s+No\s*</td>\s*<td[^>]*>)[^<]*(</td>)",
            rf"\g<1>{new_qno}\g<2>",
            html,
            flags=re.IGNORECASE,
        )
        # Invoice-family layout (build_invoice_document): label and value are
        # combined in one <td> — <td><strong>Proforma Invoice No.:</strong><br/>VALUE</td>
        html = re.sub(
            r"(<strong>\s*(?:Proforma\s+Invoice|Invoice)\s+No\.?:?\s*</strong>\s*<br\s*/?>\s*)[^<]*(</td>)",
            rf"\g<1>{new_qno}\g<2>",
            html,
            flags=re.IGNORECASE,
        )
    letterhead = doc.get("letterhead")
    local_export = doc.get("local_export")
    product_type = doc.get("product_type")
    try:
        async with _PDF_SEMAPHORE:
            pdf_bytes = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: html_to_pdf(
                    html,
                    letterhead=letterhead,
                    local_export=local_export,
                    product_type=product_type,
                    manual_document=(which == "manual_documents"),
                ),
            )
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
        elif doc_type == "proforma_invoice":
            qno_raw = doc.get("quotation_no") or _extract_quotation_no_from_html(html) or "PI"
            qno = _sanitize_filename(qno_raw, 30)
            company = _sanitize_filename(doc.get("company_name") or "Company", 30)
            filename = f"PI_{qno}_{company}_{buyer}_{product}.pdf"
        elif doc_type == "invoice":
            qno_raw = doc.get("quotation_no") or _extract_quotation_no_from_html(html) or "INV"
            qno = _sanitize_filename(qno_raw, 30)
            company = _sanitize_filename(doc.get("company_name") or "Company", 30)
            filename = f"INV_{qno}_{company}_{buyer}_{product}.pdf"
        elif doc_type == "commercial_invoice":
            qno_raw = doc.get("quotation_no") or "CI"
            qno = _sanitize_filename(qno_raw, 30)
            company = _sanitize_filename(doc.get("company_name") or "Company", 30)
            filename = f"CI_{qno}_{company}_{buyer}_{product}.pdf"
        elif doc_type == "tax_invoice":
            qno_raw = doc.get("quotation_no") or "TAX"
            qno = _sanitize_filename(qno_raw, 30)
            company = _sanitize_filename(doc.get("company_name") or "Company", 30)
            filename = f"TAX_{qno}_{company}_{buyer}_{product}.pdf"
        else:
            date_str = datetime.now().strftime("%d%m%Y")
            filename = f"{buyer}_{product}_{date_str}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

