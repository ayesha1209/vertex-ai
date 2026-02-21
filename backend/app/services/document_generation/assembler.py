"""Assemble parsed sections into one combined HTML document."""

from app.schemas.document import DocumentCreate, DocumentType, ProductType
from app.services.document_generation.response_parser import PAGE_BREAK, SECTION_HR, text_to_html

QUOTATION_WRAPPER = '<div class="quotation-page">'
QUOTATION_WRAPPER_END = "</div>"


def assemble_combined_document(
    quotation_text: str,
    tds_text: str,
    coa_text: str,
    msds_text: str,
    buyer_name: str,
    product_name: str,
    product_type: ProductType,
) -> DocumentCreate:
    """Combine four sections (Quotation → TDS → COA → MSDS) with page breaks. Quotation wrapped for one-page compact layout."""
    q = text_to_html(quotation_text, compact=True)
    q = QUOTATION_WRAPPER + q + QUOTATION_WRAPPER_END
    t = text_to_html(tds_text)
    c = text_to_html(coa_text)
    c = '<div class="coa-section">' + c + "</div>"
    m = text_to_html(msds_text)
    combined = q + PAGE_BREAK + SECTION_HR + t + PAGE_BREAK + SECTION_HR + c + PAGE_BREAK + SECTION_HR + m
    return DocumentCreate(
        buyer_name=buyer_name,
        product_name=product_name,
        product_type=product_type,
        doc_type=DocumentType.combined,
        html_content=combined,
    )
