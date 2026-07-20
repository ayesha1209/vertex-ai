"""Email sending endpoints."""

import asyncio
import html
import io
import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.mongo import documents_collection
from app.services.email_service import send_email
from app.services.export import html_to_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email", tags=["email"])

_ALLOWED_DOC_TYPES = {
    "quotation", "tds", "coa", "msds",
    "proforma_invoice", "invoice", "commercial_invoice", "tax_invoice",
}


# ── Shared models ──────────────────────────────────────────────────────────────

class SendResult(BaseModel):
    email: str
    buyer_name: str
    product_name: str
    status: str
    reason: Optional[str] = None


class SendBatchResponse(BaseModel):
    results: list[SendResult]
    sent: int
    failed: int


# ── /senders ───────────────────────────────────────────────────────────────────

@router.get("/senders")
def get_senders() -> dict:
    """Return configured sender email addresses."""
    return {"senders": get_settings().SENDER_EMAILS}


# ── /batch-email (lets the UI pre-fill / know whether a batch has a stored email) ──

@router.get("/batch-email/{batch_id}")
def get_batch_email(batch_id: str) -> dict:
    """Return the stored buyer email for a batch, if any of its documents have one
    (populated from the original Excel's 'Email id' column). Lets the Send Email
    button auto-fill a recipient instead of always asking the user to type one."""
    doc = documents_collection.find_one(
        {"batch_id": batch_id, "email_id": {"$exists": True, "$nin": [None, ""]}}
    )
    return {"email": (doc.get("email_id") if doc else None)}


# ── /send-batch (used by GeneratePage modal + the batch documents page) ────────

class SendBatchRequest(BaseModel):
    batch_id: str
    sender_email: str
    doc_types: list[str] = ["quotation"]
    subject: Optional[str] = None
    # Explicit recipient override — when set, all selected documents for this batch
    # are sent to this one address regardless of any per-document stored email_id
    # (needed when the batch has no stored email, or the user wants to redirect it).
    recipient_email: Optional[str] = None
    message: Optional[str] = None


@router.post("/send-batch", response_model=SendBatchResponse)
async def send_batch_emails(payload: SendBatchRequest) -> SendBatchResponse:
    settings = get_settings()

    if payload.sender_email not in settings.SENDER_EMAILS:
        raise HTTPException(status_code=400, detail="Sender email not in configured list.")

    requested_types = {t.lower().strip() for t in payload.doc_types}
    invalid = requested_types - _ALLOWED_DOC_TYPES
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid doc types: {invalid}")

    docs = list(documents_collection.find({"batch_id": payload.batch_id}))
    if not docs:
        raise HTTPException(status_code=404, detail="No documents found for this batch.")

    matching_docs = [d for d in docs if d.get("doc_type") in requested_types]
    if not matching_docs:
        raise HTTPException(status_code=400, detail="None of the selected document types exist in this batch.")

    override_email = (payload.recipient_email or "").strip()
    by_email: dict[str, list] = {}
    if override_email:
        by_email[override_email] = matching_docs
    else:
        for doc in matching_docs:
            email = (doc.get("email_id") or "").strip()
            if email:
                by_email.setdefault(email, []).append(doc)

    if not by_email:
        raise HTTPException(
            status_code=400,
            detail="No recipient email — enter one, or make sure the 'Email id' column was filled in your Excel.",
        )

    return await _send_to_groups(
        by_email, payload.sender_email,
        subject_template=payload.subject, message_template=payload.message,
    )


# ── /preview-from-excel ────────────────────────────────────────────────────────

class PreviewRow(BaseModel):
    buyer_name: str
    email: str
    product_name: str
    batch_id: Optional[str] = None
    doc_count: int = 0
    has_email: bool = False
    has_docs: bool = False


@router.post("/preview-from-excel", response_model=list[PreviewRow])
async def preview_from_excel(file: UploadFile = File(...)) -> list[PreviewRow]:
    """Parse Excel and match each row to the most recent generated batch."""
    content = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(content), dtype=str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read Excel file: {e}")

    df.columns = [str(c).strip() for c in df.columns]

    def _find_col(*candidates: str) -> Optional[str]:
        lower = {c.lower(): c for c in df.columns}
        for c in candidates:
            if c.lower() in lower:
                return lower[c.lower()]
        return None

    col_buyer = _find_col("Buyer Name", "buyer name", "buyer")
    col_product = _find_col("Product Name", "product name", "product")
    col_email = _find_col("Email id", "Email Id", "email id", "email", "Email")

    if not col_buyer or not col_product:
        raise HTTPException(
            status_code=400,
            detail="Excel must have 'Buyer Name' and 'Product Name' columns.",
        )

    rows: list[PreviewRow] = []
    seen: set[tuple[str, str]] = set()

    for _, row in df.iterrows():
        buyer = str(row.get(col_buyer) or "").strip()
        product = str(row.get(col_product) or "").strip()
        email = str(row.get(col_email) or "").strip() if col_email else ""

        if not buyer or not product or buyer.lower() == "nan" or product.lower() == "nan":
            continue

        key = (buyer.lower(), product.lower())
        if key in seen:
            continue
        seen.add(key)

        email = "" if email.lower() in ("nan", "none", "") else email
        has_email = bool(email and "@" in email)

        # Find most recent batch for this buyer+product
        match = documents_collection.find_one(
            {
                "buyer_name": {"$regex": f"^{buyer}$", "$options": "i"},
                "product_name": {"$regex": product[:30], "$options": "i"},
                "batch_id": {"$exists": True, "$not": {"$regex": "^manual-"}},
            },
            sort=[("created_at", -1)],
        )

        batch_id = match.get("batch_id") if match else None
        doc_count = (
            documents_collection.count_documents({"batch_id": batch_id}) if batch_id else 0
        )

        rows.append(PreviewRow(
            buyer_name=buyer,
            email=email,
            product_name=product,
            batch_id=batch_id,
            doc_count=doc_count,
            has_email=has_email,
            has_docs=bool(batch_id),
        ))

    if not rows:
        raise HTTPException(status_code=400, detail="No valid rows found in Excel.")

    return rows


# ── /send-from-list ────────────────────────────────────────────────────────────

class SendListRow(BaseModel):
    buyer_name: str
    email: str
    product_name: str
    batch_id: str
    # Per-recipient overrides — when set, take priority over the batch-wide
    # subject/message for this row only (lets the UI customize one buyer's
    # email without affecting the rest of the send).
    subject: Optional[str] = None
    message: Optional[str] = None
    # Per-recipient doc-type override — when set, takes priority over the batch-wide
    # doc_types for this row only (lets the UI attach different documents per buyer).
    doc_types: Optional[list[str]] = None


class SendFromListRequest(BaseModel):
    rows: list[SendListRow]
    sender_email: str
    doc_types: list[str] = ["quotation"]
    subject: Optional[str] = None
    message: Optional[str] = None


@router.post("/send-from-list", response_model=SendBatchResponse)
async def send_from_list(payload: SendFromListRequest) -> SendBatchResponse:
    settings = get_settings()

    if payload.sender_email not in settings.SENDER_EMAILS:
        raise HTTPException(status_code=400, detail="Sender email not in configured list.")

    requested_types = {t.lower().strip() for t in payload.doc_types}
    invalid = requested_types - _ALLOWED_DOC_TYPES
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid doc types: {invalid}")

    if not payload.rows:
        raise HTTPException(status_code=400, detail="No rows provided.")

    # Build email → docs map (one batch per row; each row is one buyer)
    by_email: dict[str, list] = {}
    meta: dict[str, dict] = {}

    for r in payload.rows:
        email = r.email.strip()
        if not email:
            continue
        if r.doc_types:
            row_types = {t.lower().strip() for t in r.doc_types}
            invalid_row = row_types - _ALLOWED_DOC_TYPES
            if invalid_row:
                raise HTTPException(status_code=400, detail=f"Invalid doc types: {invalid_row}")
        else:
            row_types = requested_types
        docs = list(documents_collection.find({
            "batch_id": r.batch_id,
            "doc_type": {"$in": list(row_types)},
        }))
        if docs:
            by_email[email] = docs
            meta[email] = {
                "buyer_name": r.buyer_name,
                "product_name": r.product_name,
                "subject": r.subject,
                "message": r.message,
            }

    if not by_email:
        raise HTTPException(status_code=400, detail="No documents found for the selected rows.")

    return await _send_to_groups(
        by_email, payload.sender_email, meta=meta,
        subject_template=payload.subject, message_template=payload.message,
    )


# ── Shared send helper ─────────────────────────────────────────────────────────

async def _send_to_groups(
    by_email: dict[str, list],
    sender_email: str,
    meta: Optional[dict[str, dict]] = None,
    subject_template: Optional[str] = None,
    message_template: Optional[str] = None,
) -> SendBatchResponse:
    results: list[SendResult] = []

    for buyer_email, buyer_docs in by_email.items():
        row_meta = (meta or {}).get(buyer_email, {})
        buyer_name = row_meta.get("buyer_name") or buyer_docs[0].get("buyer_name", "")
        product_name = row_meta.get("product_name") or buyer_docs[0].get("product_name", "")
        # A per-row subject/message (set via the per-recipient editor) wins over
        # the batch-wide template for this recipient only.
        row_subject_template = row_meta.get("subject") or subject_template
        row_message_template = row_meta.get("message") or message_template

        attachments: list[dict] = []
        for doc in buyer_docs:
            try:
                pdf_bytes: bytes = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda d=doc: html_to_pdf(
                        d["html_content"],
                        letterhead=d.get("letterhead"),
                        local_export=d.get("local_export"),
                        product_type=d.get("product_type"),
                    ),
                )
                doc_type = doc.get("doc_type", "document").upper()
                safe = product_name[:40].replace("/", "-").replace(" ", "_")
                attachments.append({"name": f"{doc_type}_{safe}.pdf", "bytes": pdf_bytes})
            except Exception as e:
                logger.warning("PDF failed for doc %s: %s", doc.get("_id"), e)

        if not attachments:
            results.append(SendResult(
                email=buyer_email, buyer_name=buyer_name, product_name=product_name,
                status="error", reason="PDF generation failed.",
            ))
            continue

        # Custom subject: {product_name}/{buyer_name} placeholders get filled in per
        # recipient; falls back to the original default when none was provided.
        if row_subject_template and row_subject_template.strip():
            subject = row_subject_template.replace("{product_name}", product_name).replace(
                "{buyer_name}", buyer_name
            )
        else:
            subject = f"Quotation – {product_name} | Vertex Chemical Corporation"

        # Custom message body: same {product_name}/{buyer_name} placeholders as the
        # subject. Plain text typed in the UI, so we escape it and turn newlines into
        # <br/> before wrapping in the same styling div. Falls back to the original
        # hardcoded body (with signature) when none was provided.
        if row_message_template and row_message_template.strip():
            filled = row_message_template.replace("{product_name}", product_name).replace(
                "{buyer_name}", buyer_name
            )
            message_body = html.escape(filled).replace("\n", "<br/>")
        else:
            message_body = (
                f"Dear {buyer_name},<br/><br/>"
                f"Please find attached our quotation for <strong>{html.escape(product_name)}</strong>.<br/><br/>"
                f"We look forward to your valued business. Please feel free to contact us for any queries.<br/><br/>"
                f"Best regards,<br/><strong>Vertex Chemical Corporation</strong><br/>{sender_email}"
            )
        body_html = (
            f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#333;">'
            f"<p>{message_body}</p>"
            f"</div>"
        )

        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda be=buyer_email, bh=body_html: send_email(
                    sender=sender_email, to=be, subject=subject,
                    body_html=bh, attachments=attachments,
                ),
            )
            results.append(SendResult(
                email=buyer_email, buyer_name=buyer_name, product_name=product_name, status="sent",
            ))
        except Exception as e:
            logger.error("Email to %s failed: %s", buyer_email, e)
            results.append(SendResult(
                email=buyer_email, buyer_name=buyer_name, product_name=product_name,
                status="error", reason=str(e)[:200],
            ))

    sent = sum(1 for r in results if r.status == "sent")
    return SendBatchResponse(results=results, sent=sent, failed=len(results) - sent)
