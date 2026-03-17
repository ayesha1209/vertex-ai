"""Build user prompt for document generation from row data."""

from datetime import datetime

from app.prompts.vertex_prompts import USER_PROMPT_TEMPLATE
from app.schemas.document import RowPreview
from app.utils.quotation_number import generate_quotation_no


def _format_date(date_str: str | None) -> str:
    """Convert ISO date (YYYY-MM-DD) to DD/MM/YYYY for the prompt.

    Falls back to returning the raw string if parsing fails so the AI still
    receives whatever value was in the Excel sheet.
    """
    if not date_str:
        return ""
    raw = date_str.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw  # return as-is if unrecognised format


def build_user_prompt(row: RowPreview) -> str:
    """Build prompt with all enquiry fields. Use Excel value when provided; empty → AI generates with smart defaults."""
    quotation_no = (row.quotation_no or "").strip() or generate_quotation_no(row.company_name)
    company_name = (row.company_name or "").strip() or ""
    local_export = (row.local_export or "").strip() or ""
    quotation_date = _format_date(row.date)
    return USER_PROMPT_TEMPLATE.format(
        company_name=company_name,
        quotation_no=quotation_no,
        buyer_name=row.buyer_name or "",
        address=(row.address or "").strip() or "",
        country=(row.country or "").strip() or "",
        email_id=(row.email_id or "").strip() or "",
        contact_no=(row.contact_no or "").strip() or "",
        product_name=row.product_name or "",
        manufacturer_name=(row.manufacturer_name or "").strip() or company_name,
        product_description=(row.product_description or "").strip() or "",
        hsn_code=(row.hsn_code or "").strip() or "",
        cas_no=(row.cas_no or "").strip() or "",
        quantity=(row.quantity or "").strip() or "",
        unit=(row.unit or "").strip() or "",
        packing=(row.packing or row.type_of_packing or "").strip() or "",
        price=(row.price or "").strip() or "",
        price_fob_cif=(row.price_fob_cif or "").strip() or "",
        port_of_loading=(row.port_of_loading or row.port or "").strip() or "",
        port_of_unloading=(row.port_of_unloading or "").strip() or "",
        incoterm=(row.incoterm or "").strip() or "",
        payment_terms=(row.payment_terms or "").strip() or "",
        remarks=(row.remarks or "").strip() or "",
        local_export=local_export or "(use Export if country not India else Local)",
        quotation_date=quotation_date,
    )
