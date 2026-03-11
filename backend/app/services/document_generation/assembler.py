"""Assemble parsed sections into separate Quotation, TDS, COA, and MSDS documents."""

import re
from html import escape
from app.schemas.document import DocumentCreate, DocumentType, ProductType
from app.services.document_generation.response_parser import PAGE_BREAK, text_to_html

QUOTATION_WRAPPER = '<div class="quotation-page">'
QUOTATION_WRAPPER_END = "</div>"


def _fix_description_line_breaks(html: str) -> str:
    """Post-process HTML to ensure Make: and HSN: are on separate lines in item descriptions."""
    # Find all td cells and fix any that contain // Make: or // HSN:
    def fix_cell(match):
        content = match.group(1)
        # If it contains // or Make:/HSN: without line breaks, fix it
        if '//' in content or ('Make:' in content and '<br' not in content.lower()):
            # Remove // and clean up
            text = re.sub(r'\s*//\s*', ' ', content)
            text = re.sub(r'&lt;br/?&gt;', ' ', text)  # Remove escaped br tags
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Find Make: and HSN: positions
            make_match = re.search(r'Make\s*:', text, re.IGNORECASE)
            hsn_match = re.search(r'HSN\s*:', text, re.IGNORECASE)
            
            if make_match:
                parts = []
                product_name = text[:make_match.start()].strip()
                if product_name:
                    parts.append(product_name)
                
                if hsn_match and hsn_match.start() > make_match.start():
                    make_part = text[make_match.start():hsn_match.start()].strip()
                    hsn_part = text[hsn_match.start():].strip()
                    parts.append(make_part)
                    parts.append(hsn_part)
                else:
                    make_part = text[make_match.start():].strip()
                    parts.append(make_part)
                
                return f'<td{match.group(0).split("<td")[1].split(">")[0]}>{"<br/>".join(parts)}</td>'
        
        return match.group(0)
    
    # Match td cells
    html = re.sub(r'<td[^>]*>([^<]*(?://|Make:)[^<]*)</td>', fix_cell, html, flags=re.IGNORECASE)
    return html


def _split_multi_product_sections(text: str, pattern: str) -> list[str]:
    """Split text containing multiple product sections (e.g., multiple TDS) into separate sections."""
    matches = list(re.finditer(pattern, text, re.IGNORECASE))
    if len(matches) <= 1:
        return [text] if text.strip() else []
    
    sections = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.append(text[start:end].strip())
    return sections


def _ensure_currency_in_totals(html: str, local_export: str | None) -> str:
    """Ensure Total/Amount column header and total row use ₹ (rupee) for LOCAL and $ for EXPORT."""
    if not local_export:
        return html
    is_local = str(local_export).strip().lower() == "local"
    # Post-process: in totals table and items header, align currency symbol
    if is_local:
        # Replace $ with ₹ (rupee symbol) in header/total context
        html = re.sub(r"Amount\s*\(\s*\$\s*\)", "Amount (₹)", html, flags=re.IGNORECASE)
        html = re.sub(r"Amount\s*\(\s*Rs\.?\s*\)", "Amount (₹)", html, flags=re.IGNORECASE)
        # In totals table row, replace leading $ or Rs. with ₹
        html = re.sub(r"(totals-table[^>]*>.*?<td[^>]*>\s*)\$", r"\1₹", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"(totals-table[^>]*>.*?<td[^>]*>\s*)Rs\.?", r"\1₹", html, flags=re.DOTALL | re.IGNORECASE)
    else:
        html = re.sub(r"Amount\s*\(\s*Rs\.?\s*\)", "Amount ($)", html, flags=re.IGNORECASE)
        html = re.sub(r"Amount\s*\(\s*₹\s*\)", "Amount ($)", html, flags=re.IGNORECASE)
    return html


def assemble_separate_documents(
    quotation_text: str,
    tds_text: str,
    coa_text: str,
    msds_text: str,
    buyer_name: str,
    product_name: str,
    product_type: ProductType,
    *,
    batch_id: str,
    employee_name: str | None = None,
    letterhead: str | None = None,
    quotation_no: str | None = None,
    company_name: str | None = None,
    local_export: str | None = None,
    terms_html: str | None = None,
) -> list[DocumentCreate]:
    """Build four separate documents: Quotation, TDS, COA, MSDS. Each gets batch_id and optional terms appended."""
    terms_block = ("<div class=\"terms-and-conditions\">" + terms_html + "</div>") if terms_html else ""

    def wrap_section(section_html: str, terms: str) -> str:
        if terms:
            return section_html + PAGE_BREAK + terms
        return section_html

    # Quotation (single)
    q_html = text_to_html(quotation_text, compact=True)
    q_html = _fix_description_line_breaks(q_html)
    q_html = QUOTATION_WRAPPER + q_html + QUOTATION_WRAPPER_END
    q_html = _ensure_currency_in_totals(q_html, local_export)
    q_html = wrap_section(q_html, terms_block)

    # TDS (all sections with page breaks)
    tds_parts: list[str] = []
    tds_pattern = r"#\s*TECHNICAL DATA SHEET\s*\(TDS\)"
    tds_sections = _split_multi_product_sections(tds_text, tds_pattern)
    for tds_sec in tds_sections:
        if tds_sec.strip():
            tds_parts.append(text_to_html(tds_sec))
    tds_html = (PAGE_BREAK.join(tds_parts) + PAGE_BREAK + terms_block) if terms_block else PAGE_BREAK.join(tds_parts)

    # COA
    coa_parts = []
    coa_pattern = r"#\s*CERTIFICATE OF ANALYSIS\s*\(COA\)"
    coa_sections = _split_multi_product_sections(coa_text, coa_pattern)
    for coa_sec in coa_sections:
        if coa_sec.strip():
            coa_parts.append('<div class="coa-section">' + text_to_html(coa_sec) + "</div>")
    coa_html = (PAGE_BREAK.join(coa_parts) + PAGE_BREAK + terms_block) if terms_block else PAGE_BREAK.join(coa_parts)

    # MSDS
    msds_parts = []
    msds_pattern = r"#\s*MATERIAL SAFETY DATA SHEET\s*\(MSDS\)"
    msds_sections = _split_multi_product_sections(msds_text, msds_pattern)
    for msds_sec in msds_sections:
        if msds_sec.strip():
            msds_parts.append(text_to_html(msds_sec))
    msds_html = (PAGE_BREAK.join(msds_parts) + PAGE_BREAK + terms_block) if terms_block else PAGE_BREAK.join(msds_parts)

    letterhead_val = letterhead.strip().lower() if (letterhead and isinstance(letterhead, str)) else None
    local_export_val = local_export.strip().lower() if (local_export and isinstance(local_export, str)) else None
    common = {
        "buyer_name": buyer_name,
        "product_name": product_name,
        "product_type": product_type,
        "batch_id": batch_id,
        "employee_name": employee_name,
        "letterhead": letterhead_val if letterhead_val in ("dubai", "india") else None,
        "local_export": local_export_val,
    }
    return [
        DocumentCreate(
            **common,
            doc_type=DocumentType.quotation,
            html_content=q_html,
            quotation_no=quotation_no,
            company_name=company_name,
        ),
        DocumentCreate(
            **common,
            doc_type=DocumentType.tds,
            html_content=tds_html if tds_parts else "<p>No TDS content.</p>",
        ),
        DocumentCreate(
            **common,
            doc_type=DocumentType.coa,
            html_content=coa_html if coa_parts else "<p>No COA content.</p>",
        ),
        DocumentCreate(
            **common,
            doc_type=DocumentType.msds,
            html_content=msds_html if msds_parts else "<p>No MSDS content.</p>",
        ),
    ]
