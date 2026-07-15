"""Admin routes: shipment document tracking (protected by session cookie)."""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from app.core.auth import require_admin
from app.db.mongo import documents_collection, shipment_tracking_collection, now_local

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "shipment_docs")
os.makedirs(UPLOAD_DIR, exist_ok=True)

DOC_TYPES = ["pi", "tax_invoice", "pl", "receipt_tt_copy", "bank_receipt", "bl_copy", "custom_copy"]

DOC_TYPE_LABELS = {
    "pi": "Proforma Invoice (PI)",
    "tax_invoice": "Tax Invoice",
    "pl": "P/L (Packing List)",
    "receipt_tt_copy": "Receipt (TT Copy)",
    "bank_receipt": "Bank Receipt",
    "bl_copy": "BL Copy",
    "custom_copy": "Custom Copy",
}

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB per file


def _empty_docs() -> dict:
    return {
        dt: {"uploaded": False, "filename": None, "file_path": None, "uploaded_at": None}
        for dt in DOC_TYPES
    }


def _serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    # Convert datetime objects to ISO strings
    for key in ("created_at", "updated_at"):
        if isinstance(doc.get(key), datetime):
            doc[key] = doc[key].isoformat()
    for dt_key in DOC_TYPES:
        slot = doc.get("docs", {}).get(dt_key, {})
        if isinstance(slot.get("uploaded_at"), datetime):
            slot["uploaded_at"] = slot["uploaded_at"].isoformat()
    return doc


class ShipmentCreateRequest(BaseModel):
    batch_id: Optional[str] = None   # auto-generated for manual/skip entries
    quotation_no: Optional[str] = None
    buyer_name: str
    product_name: str


class ShipmentSummary(BaseModel):
    id: str
    batch_id: str
    quotation_no: Optional[str] = None
    buyer_name: str
    product_name: str
    created_at: str
    updated_at: str
    all_uploaded: bool
    docs: dict


# ------------------------------------------------------------------
# List all shipment tracking records (latest first)
# ------------------------------------------------------------------
@router.get("/api/admin/shipments")
async def list_shipments(
    request: Request,
    skip: int = 0,
    limit: int = 50,
) -> dict:
    require_admin(request)
    try:
        total = shipment_tracking_collection.count_documents({})
        cursor = shipment_tracking_collection.find({}).sort("created_at", -1).skip(skip).limit(limit)
        items = [_serialize(d) for d in cursor]
        return {"shipments": items, "total": total}
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Create a new shipment tracking record for a batch
# ------------------------------------------------------------------
@router.post("/api/admin/shipments")
async def create_shipment(payload: ShipmentCreateRequest, request: Request) -> dict:
    require_admin(request)
    # Use provided batch_id or generate a unique one for manual/skip entries
    batch_id = payload.batch_id or f"admin-{uuid.uuid4().hex}"

    # Check if a record already exists for this batch (only meaningful for linked batches)
    if payload.batch_id:
        existing = shipment_tracking_collection.find_one({"batch_id": payload.batch_id})
        if existing:
            return _serialize(existing)

    now = now_local()
    doc: dict[str, Any] = {
        "batch_id": batch_id,
        "quotation_no": payload.quotation_no,
        "buyer_name": payload.buyer_name,
        "product_name": payload.product_name,
        "created_at": now,
        "updated_at": now,
        "all_uploaded": False,
        "docs": _empty_docs(),
    }
    result = shipment_tracking_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


# ------------------------------------------------------------------
# Get a single shipment tracking record
# ------------------------------------------------------------------
@router.get("/api/admin/shipments/{shipment_id}")
async def get_shipment(shipment_id: str, request: Request) -> dict:
    require_admin(request)
    try:
        oid = ObjectId(shipment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    doc = shipment_tracking_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return _serialize(doc)


# ------------------------------------------------------------------
# Upload a file for a doc type slot
# ------------------------------------------------------------------
@router.post("/api/admin/shipments/{shipment_id}/upload/{doc_type}")
async def upload_shipment_doc(
    shipment_id: str,
    doc_type: str,
    request: Request,
    file: UploadFile = File(...),
) -> dict:
    require_admin(request)
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid doc_type. Must be one of: {', '.join(DOC_TYPES)}")
    try:
        oid = ObjectId(shipment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid shipment id")

    doc = shipment_tracking_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Shipment not found")

    # Read file content (enforce size limit)
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    # Remove previous file if exists
    existing_path = (doc.get("docs") or {}).get(doc_type, {}).get("file_path")
    if existing_path and os.path.isfile(existing_path):
        try:
            os.remove(existing_path)
        except OSError:
            pass

    # Save new file
    ext = os.path.splitext(file.filename or "")[1] or ".pdf"
    safe_name = f"{shipment_id}_{doc_type}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    now = now_local()
    slot = {
        "uploaded": True,
        "filename": file.filename or safe_name,
        "file_path": file_path,
        "uploaded_at": now,
    }
    update_key = f"docs.{doc_type}"

    # Recalculate all_uploaded after this update
    updated_docs = dict(doc.get("docs") or {})
    updated_docs[doc_type] = slot
    all_uploaded = all(updated_docs.get(dt, {}).get("uploaded", False) for dt in DOC_TYPES)

    shipment_tracking_collection.update_one(
        {"_id": oid},
        {"$set": {update_key: slot, "all_uploaded": all_uploaded, "updated_at": now}},
    )
    return {"ok": True, "doc_type": doc_type, "filename": file.filename, "all_uploaded": all_uploaded}


# ------------------------------------------------------------------
# Download a file for a doc type slot
# ------------------------------------------------------------------
@router.get("/api/admin/shipments/{shipment_id}/files/{doc_type}")
async def download_shipment_doc(shipment_id: str, doc_type: str, request: Request) -> FileResponse:
    require_admin(request)
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail="Invalid doc_type")
    try:
        oid = ObjectId(shipment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    doc = shipment_tracking_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Shipment not found")
    slot = (doc.get("docs") or {}).get(doc_type, {})
    file_path = slot.get("file_path")
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not uploaded yet")
    return FileResponse(file_path, filename=slot.get("filename") or os.path.basename(file_path))


# ------------------------------------------------------------------
# Delete a shipment tracking record (and all uploaded files on disk)
# ------------------------------------------------------------------
@router.delete("/api/admin/shipments/{shipment_id}")
async def delete_shipment(shipment_id: str, request: Request) -> dict:
    require_admin(request)
    try:
        oid = ObjectId(shipment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")
    doc = shipment_tracking_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Shipment not found")

    # Remove all uploaded files from disk
    for dt in DOC_TYPES:
        slot = (doc.get("docs") or {}).get(dt, {})
        file_path = slot.get("file_path")
        if file_path and os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass

    shipment_tracking_collection.delete_one({"_id": oid})
    return {"ok": True}


# ------------------------------------------------------------------
# List all quotation batches (for the admin to select from)
# Supports: q (buyer/product/quotation_no), entered_by (employee), pagination
# ------------------------------------------------------------------
@router.get("/api/admin/batches")
async def list_admin_batches(
    request: Request,
    q: Optional[str] = None,           # searches buyer_name, product_name, quotation_no
    entered_by: Optional[str] = None,  # filters by employee_name
    skip: int = 0,
    limit: int = 100,
) -> dict:
    require_admin(request)
    try:
        # Build match conditions as a list, then combine with $and
        conditions: List[dict[str, Any]] = [
            {"batch_id": {"$exists": True, "$nin": [None, ""]}},
            {"doc_type": "quotation"},
            {"batch_id": {"$not": {"$regex": "^manual-"}}},
        ]

        if entered_by and entered_by.strip():
            conditions.append({"employee_name": {"$regex": entered_by.strip(), "$options": "i"}})

        if q and q.strip():
            q_regex = {"$regex": q.strip(), "$options": "i"}
            conditions.append({"$or": [
                {"buyer_name": q_regex},
                {"product_name": q_regex},
                {"quotation_no": q_regex},
            ]})

        match_stage: dict[str, Any] = {"$and": conditions}

        # Count pipeline (group first to deduplicate by batch_id, then count)
        count_pipeline: List[dict[str, Any]] = [
            {"$match": match_stage},
            {"$group": {"_id": "$batch_id"}},
            {"$count": "total"},
        ]

        # Data pipeline: group by batch_id, sort, paginate
        data_pipeline: List[dict[str, Any]] = [
            {"$match": match_stage},
            {"$sort": {"created_at": -1}},
            {"$group": {
                "_id": "$batch_id",
                "buyer_name": {"$first": "$buyer_name"},
                "product_name": {"$first": "$product_name"},
                "quotation_no": {"$first": "$quotation_no"},
                "company_name": {"$first": "$company_name"},
                "employee_name": {"$first": "$employee_name"},
                "created_at": {"$first": "$created_at"},
            }},
            {"$sort": {"created_at": -1}},
            {"$skip": max(0, skip)},
            {"$limit": min(limit, 200)},
        ]

        count_result = list(documents_collection.aggregate(count_pipeline))
        total = count_result[0]["total"] if count_result else 0

        cursor = documents_collection.aggregate(data_pipeline)
        batches = []
        for d in cursor:
            batches.append({
                "batch_id": str(d["_id"]),
                "buyer_name": d.get("buyer_name") or "",
                "product_name": d.get("product_name") or "",
                "quotation_no": d.get("quotation_no"),
                "company_name": d.get("company_name"),
                "employee_name": d.get("employee_name"),
                "created_at": d["created_at"].isoformat() if isinstance(d.get("created_at"), datetime) else str(d.get("created_at", "")),
            })
        return {"batches": batches, "total": total}
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=str(e))
