"""Assemble parsed sections into one combined HTML document."""

import re
from html import escape
from app.schemas.document import DocumentCreate, DocumentType, ProductType
from app.services.document_generation.response_parser import PAGE_BREAK, SECTION_HR, text_to_html

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


def assemble_combined_document(
    quotation_text: str,
    tds_text: str,
    coa_text: str,
    msds_text: str,
    buyer_name: str,
    product_name: str,
    product_type: ProductType,
) -> DocumentCreate:
    """Combine sections with page breaks. Handles multiple products:
    - One quotation with all items
    - Separate TDS/COA/MSDS for each product, each on new page
    """
    # Quotation (single, with all line items)
    q = text_to_html(quotation_text, compact=True)
    # Post-process to ensure line breaks in item descriptions
    q = _fix_description_line_breaks(q)
    q = QUOTATION_WRAPPER + q + QUOTATION_WRAPPER_END
    
    parts = [q]
    
    # Split TDS sections if multiple products
    tds_pattern = r"#\s*TECHNICAL DATA SHEET\s*\(TDS\)"
    tds_sections = _split_multi_product_sections(tds_text, tds_pattern)
    for tds_sec in tds_sections:
        if tds_sec.strip():
            parts.append(PAGE_BREAK + SECTION_HR + text_to_html(tds_sec))
    
    # Split COA sections if multiple products
    coa_pattern = r"#\s*CERTIFICATE OF ANALYSIS\s*\(COA\)"
    coa_sections = _split_multi_product_sections(coa_text, coa_pattern)
    for coa_sec in coa_sections:
        if coa_sec.strip():
            parts.append(PAGE_BREAK + SECTION_HR + '<div class="coa-section">' + text_to_html(coa_sec) + "</div>")
    
    # Split MSDS sections if multiple products
    msds_pattern = r"#\s*MATERIAL SAFETY DATA SHEET\s*\(MSDS\)"
    msds_sections = _split_multi_product_sections(msds_text, msds_pattern)
    for msds_sec in msds_sections:
        if msds_sec.strip():
            parts.append(PAGE_BREAK + SECTION_HR + text_to_html(msds_sec))
    
    combined = "".join(parts)
    return DocumentCreate(
        buyer_name=buyer_name,
        product_name=product_name,
        product_type=product_type,
        doc_type=DocumentType.combined,
        html_content=combined,
    )
