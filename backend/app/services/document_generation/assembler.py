"""Assemble parsed sections into separate Quotation, TDS, COA, and MSDS documents."""

import re
from html import escape
from app.schemas.document import DocumentCreate, DocumentType, ProductType
from app.services.document_generation.response_parser import PAGE_BREAK, text_to_html

QUOTATION_WRAPPER = '<div class="quotation-page">'
QUOTATION_WRAPPER_END = "</div>"

_H1_STYLE = "font-weight:bold;text-align:center;text-transform:uppercase;letter-spacing:0.04em;"

# Titles for each doc type (used to strip duplicates and prepend a clean heading)
_DOC_TITLES = {
    "tds": "TECHNICAL DATA SHEET (TDS)",
    "coa": "CERTIFICATE OF ANALYSIS (COA)",
    "msds": "MATERIAL SAFETY DATA SHEET (MSDS)",
}

# Patterns that match title lines the AI repeats (e.g. "# TECHNICAL DATA SHEET (TDS)" or just "TECHNICAL DATA SHEET (TDS)")
_TITLE_STRIP_PATTERNS = [
    re.compile(r"^\s*#\s*TECHNICAL DATA SHEET\s*\(TDS\)(?:\s*-\s*[^\n]*)?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*#\s*CERTIFICATE OF ANALYSIS\s*\(COA\)(?:\s*-\s*[^\n]*)?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*#\s*MATERIAL SAFETY DATA SHEET\s*\(MSDS\)(?:\s*-\s*[^\n]*)?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*TECHNICAL DATA SHEET\s*\(TDS\)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*CERTIFICATE OF ANALYSIS\s*\(COA\)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*MATERIAL SAFETY DATA SHEET\s*\(MSDS\)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*FULL TECHNICAL DATA SHEET\s*\(TDS\)\s*$", re.IGNORECASE | re.MULTILINE),
]

# "Section N:" prefix pattern — strip from MSDS/TDS headings
_SECTION_PREFIX = re.compile(r"^Section\s+\d+\s*:\s*", re.IGNORECASE)


def _clean_doc_text(text: str) -> str:
    """Strip duplicate title lines and 'Section N:' prefixes from TDS/COA/MSDS text before HTML conversion."""
    for pat in _TITLE_STRIP_PATTERNS:
        text = pat.sub("", text)
    # Remove "Section N:" prefix from heading lines (e.g. "Section 1: Identification" -> "Identification")
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if _SECTION_PREFIX.match(stripped):
            cleaned.append(_SECTION_PREFIX.sub("", stripped))
        else:
            cleaned.append(line)
    return "\n".join(cleaned)


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


def _split_sections_with_product_name(
    text: str, pattern: str, default_product: str
) -> list[tuple[str, str]]:
    """
    Split text by pattern and return (section_text, product_name) per section.
    Product name is taken from the first line after the pattern, e.g. "# TDS (TDS) - Caustic Soda" -> "Caustic Soda".
    """
    # Match optional " - ProductName" on same line (capture product name)
    pattern_with_name = pattern + r"(?:\s*-\s*([^\n]+))?"
    matches = list(re.finditer(pattern_with_name, text, re.IGNORECASE))
    if not matches:
        return [(text.strip(), default_product)] if text.strip() else []
    if len(matches) == 1 and not matches[0].group(1):
        return [(text.strip(), default_product)] if text.strip() else []

    result: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        name_group = match.group(1)
        product_name = (name_group.strip() if name_group else default_product) or default_product
        result.append((section_text, product_name))
    return result


def _ensure_currency_in_totals(html: str, local_export: str | None) -> str:
    """Ensure quotation uses ₹ (rupee) and Rs for LOCAL, $ and USD for EXPORT in headers, items table, totals and delivery currency row."""
    if not local_export:
        return html
    is_local = str(local_export).strip().lower() == "local"

    if is_local:
        # Headers: Unit Price / Unit Amount / Amount (…) → rupee
        html = re.sub(r"Unit\s+Price\s*\(\s*\$\s*\)", "Unit Price (₹)", html, flags=re.IGNORECASE)
        html = re.sub(r"Unit\s+Price\s*\(\s*Rs\.?\s*\)", "Unit Price (₹)", html, flags=re.IGNORECASE)
        html = re.sub(r"Unit\s+Amount\s*\(\s*\$\s*\)", "Unit Amount (₹)", html, flags=re.IGNORECASE)
        html = re.sub(r"Unit\s+Amount\s*\(\s*Rs\.?\s*\)", "Unit Amount (₹)", html, flags=re.IGNORECASE)
        html = re.sub(r"Amount\s*\(\s*\$\s*\)", "Amount (₹)", html, flags=re.IGNORECASE)
        html = re.sub(r"Amount\s*\(\s*Rs\.?\s*\)", "Amount (₹)", html, flags=re.IGNORECASE)
        # Totals table: leading $ or Rs. → ₹
        html = re.sub(r"(totals-table[^>]*>.*?<td[^>]*>\s*)\$", r"\1₹", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"(totals-table[^>]*>.*?<td[^>]*>\s*)Rs\.?", r"\1₹", html, flags=re.DOTALL | re.IGNORECASE)
        # Items table: prices (symbol + number) → ₹
        html = _replace_currency_in_items_table(html, to_rupee=True)
        # Delivery table Currency cell: show ₹
        html = re.sub(
            r"(delivery-table[^>]*>.*?Currency[^<]*</td>\s*<td[^>]*>)[^<]*",
            r"\1₹",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
    else:
        # Export: headers and totals → $
        html = re.sub(r"Unit\s+Price\s*\(\s*Rs\.?\s*\)", "Unit Price ($)", html, flags=re.IGNORECASE)
        html = re.sub(r"Unit\s+Price\s*\(\s*₹\s*\)", "Unit Price ($)", html, flags=re.IGNORECASE)
        html = re.sub(r"Unit\s+Amount\s*\(\s*Rs\.?\s*\)", "Unit Amount ($)", html, flags=re.IGNORECASE)
        html = re.sub(r"Unit\s+Amount\s*\(\s*₹\s*\)", "Unit Amount ($)", html, flags=re.IGNORECASE)
        html = re.sub(r"Amount\s*\(\s*Rs\.?\s*\)", "Amount ($)", html, flags=re.IGNORECASE)
        html = re.sub(r"Amount\s*\(\s*₹\s*\)", "Amount ($)", html, flags=re.IGNORECASE)
        html = re.sub(r"(totals-table[^>]*>.*?<td[^>]*>\s*)₹\s*", r"\1$", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"(totals-table[^>]*>.*?<td[^>]*>\s*)Rs\.?\s*", r"\1$", html, flags=re.DOTALL | re.IGNORECASE)
        html = _replace_currency_in_items_table(html, to_rupee=False)
        html = re.sub(
            r"(delivery-table[^>]*>.*?Currency[^<]*</td>\s*<td[^>]*>)[^<]*",
            r"\1$",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
    return html


def _replace_currency_in_items_table(html: str, to_rupee: bool) -> str:
    """Replace currency symbols in items-table body (Unit Price and Unit Amount columns)."""
    # Match the items-table block (from class="items-table" to closing </table>)
    match = re.search(
        r'(<table[^>]*class="[^"]*items-table[^"]*"[^>]*>.*?)</table>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return html
    block = match.group(1)
    if to_rupee:
        # $123 or $1,234.56 → ₹123 / ₹1,234.56; Rs.123 or Rs 123 → ₹123
        block = re.sub(r"\$(\d)", r"₹\1", block)
        block = re.sub(r"Rs\.?\s*(\d)", r"₹\1", block, flags=re.IGNORECASE)
    else:
        # ₹123 or Rs.123 → $123
        block = re.sub(r"₹\s*(\d)", r"$\1", block)
        block = re.sub(r"Rs\.?\s*(\d)", r"$\1", block, flags=re.IGNORECASE)
    return html[: match.start()] + block + "</table>" + html[match.end() :]


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
) -> list[DocumentCreate]:
    """Build four separate documents: Quotation, TDS, COA, MSDS. Terms are only in Quotation (from AI output, not appended)."""
    # Quotation: do not append terms here — the AI-generated quotation already includes TERMS & CONDITIONS once (from prompt).
    # Multi-product: signatory after 15. Single-product: 13–15 left, signatory right.
    multi_product = "," in (product_name or "").strip()
    q_html = text_to_html(quotation_text, compact=True, multi_product=multi_product)
    q_html = _fix_description_line_breaks(q_html)
    # Always ensure the QUOTATION heading is present (AI sometimes includes it, sometimes not)
    if not re.search(r"<h1[^>]*>\s*QUOTATION\s*</h1>", q_html, re.IGNORECASE):
        q_heading = '<h1 style="font-weight:bold;text-align:center;text-transform:uppercase;letter-spacing:0.04em;">QUOTATION</h1>'
        q_html = q_heading + q_html
    q_html = QUOTATION_WRAPPER + q_html + QUOTATION_WRAPPER_END
    q_html = _ensure_currency_in_totals(q_html, local_export)

    letterhead_val = letterhead.strip().lower() if (letterhead and isinstance(letterhead, str)) else None
    local_export_val = local_export.strip().lower() if (local_export and isinstance(local_export, str)) else None
    common_base = {
        "buyer_name": buyer_name,
        "product_type": product_type,
        "batch_id": batch_id,
        "employee_name": employee_name,
        "letterhead": letterhead_val if letterhead_val in ("dubai", "india") else None,
        "local_export": local_export_val,
    }

    # One Quotation (covers all products)
    out: list[DocumentCreate] = [
        DocumentCreate(
            **common_base,
            product_name=product_name,
            doc_type=DocumentType.quotation,
            html_content=q_html,
            quotation_no=quotation_no,
            company_name=company_name,
        ),
    ]

    def _build_doc(doc_type_key: str, raw_text: str, sec_product: str, is_coa: bool = False) -> DocumentCreate:
        """Clean text, convert to HTML, prepend single heading."""
        cleaned = _clean_doc_text(raw_text)
        body_html = text_to_html(cleaned)
        title = _DOC_TITLES[doc_type_key]
        heading = f'<h1 style="{_H1_STYLE}">{title}</h1>'
        # Strip any remaining duplicate <h1> that matches this doc's title
        body_html = re.sub(
            rf'<h1[^>]*>\s*{re.escape(title)}\s*</h1>',
            "",
            body_html,
            flags=re.IGNORECASE,
        )
        full_html = heading + "\n" + body_html
        if is_coa:
            full_html = '<div class="coa-section">' + full_html + "</div>"
        dt = {"tds": DocumentType.tds, "coa": DocumentType.coa, "msds": DocumentType.msds}[doc_type_key]
        return DocumentCreate(**common_base, product_name=sec_product, doc_type=dt, html_content=full_html)

    # TDS: one document per product (section)
    tds_pattern = r"#\s*TECHNICAL DATA SHEET\s*\(TDS\)"
    tds_sections_with_name = _split_sections_with_product_name(tds_text, tds_pattern, product_name)
    for tds_sec, sec_product in tds_sections_with_name:
        if tds_sec.strip():
            out.append(_build_doc("tds", tds_sec, sec_product))
    if not any(s[0].strip() for s in tds_sections_with_name):
        out.append(
            DocumentCreate(**common_base, product_name=product_name, doc_type=DocumentType.tds, html_content="<p>No TDS content.</p>")
        )

    # COA: one document per product (section)
    coa_pattern = r"#\s*CERTIFICATE OF ANALYSIS\s*\(COA\)"
    coa_sections_with_name = _split_sections_with_product_name(coa_text, coa_pattern, product_name)
    for coa_sec, sec_product in coa_sections_with_name:
        if coa_sec.strip():
            out.append(_build_doc("coa", coa_sec, sec_product, is_coa=True))
    if not any(s[0].strip() for s in coa_sections_with_name):
        out.append(
            DocumentCreate(**common_base, product_name=product_name, doc_type=DocumentType.coa, html_content="<p>No COA content.</p>")
        )

    # MSDS: one document per product (section)
    msds_pattern = r"#\s*MATERIAL SAFETY DATA SHEET\s*\(MSDS\)"
    msds_sections_with_name = _split_sections_with_product_name(msds_text, msds_pattern, product_name)
    for msds_sec, sec_product in msds_sections_with_name:
        if msds_sec.strip():
            out.append(_build_doc("msds", msds_sec, sec_product))
    if not any(s[0].strip() for s in msds_sections_with_name):
        out.append(
            DocumentCreate(**common_base, product_name=product_name, doc_type=DocumentType.msds, html_content="<p>No MSDS content.</p>")
        )

    return out
