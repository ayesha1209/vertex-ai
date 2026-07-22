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
    re.compile(
        r"^\s*#\s*TECHNICAL DESCRIPTION(?:\s*-\s*[^\n]*)?\s*$", re.IGNORECASE | re.MULTILINE
    ),
    re.compile(r"^\s*TECHNICAL DESCRIPTION\s*$", re.IGNORECASE | re.MULTILINE),
]

# "Section N:" prefix — replace with "## " so parser renders as bold, slightly larger subheading
_SECTION_PREFIX = re.compile(r"^Section\s+\d+\s*:\s*", re.IGNORECASE)


def _strip_engineering_tds_commercial_lines(text: str) -> str:
    """Remove commercial/boilerplate lines sometimes echoed into engineering tech text."""
    out_lines: list[str] = []
    skip_prefixes = (
        "supplier:",
        "manufacturer:",
        "hsn code:",
        "hsn:",
        "quantity:",
        "qty:",
        "intended use:",
        "company/supplier:",
        "buyer:",
        "local/export:",
        "quotation no:",
        "export to",
    )
    for line in text.splitlines():
        low = line.strip().lower()
        if not low:
            out_lines.append(line)
            continue
        if any(low.startswith(p) for p in skip_prefixes):
            continue
        # Markdown-style horizontal rule / table separator line pasted as plain text
        if re.match(r"^[-:\s]+$", low) and len(low) >= 4:
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def _clean_doc_text(text: str) -> str:
    """Strip duplicate title lines; convert 'Section N: Title' to '## Title' for bold larger heading."""
    for pat in _TITLE_STRIP_PATTERNS:
        text = pat.sub("", text)
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if _SECTION_PREFIX.match(stripped):
            title_only = _SECTION_PREFIX.sub("", stripped)
            cleaned.append("## " + title_only)
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


# Fixed bank details — always overwrite whatever the AI generated
_BANK_DETAIL_VALUES = {
    "account name":       "VERTEX CHEMICAL CORPORATION",
    "a/c no":             "50200115602188",
    "account no":         "50200115602188",
    "account number":     "50200115602188",
    "bank name":          "HDFC Bank, Vasna Road Branch",
    "bank name & branch": "HDFC Bank, Vasna Road Branch",
    "branch":             "Vasna Road Branch",
    "ifsc":               "HDFC0001712",
    "ifsc code":          "HDFC0001712",
    "swift":              "HDFCINBBXXX",
    "swift code":         "HDFCINBBXXX",
    "customer id":        "347711727 (VASAVA VISHALKUMAR)",
}


# Default Make when Manufacturer / Excel field is empty
_MAKE_VERTEX_CHEMICAL = "Vertex Chemical"
_MAKE_VERTEX_ENGINEERING = "Vertex Engineering"


def _replace_make_in_items_table(html: str, make_display: str) -> str:
    """Set every Make: line in the items-table to the same escaped text (stops at HTML tags)."""
    safe = escape((make_display or "").strip())
    if not safe:
        return html
    match = re.search(
        r'<table[^>]*class="[^"]*items-table[^"]*"[^>]*>.*?</table>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return html
    block = match.group(0)
    new_block = re.sub(
        r"Make\s*:\s*[^<]*",
        "Make: " + safe,
        block,
        flags=re.IGNORECASE,
    )
    if new_block == block:
        return html
    return html[: match.start()] + new_block + html[match.end() :]


def _replace_make_in_items_rows(html: str, makes: list[str], default_make: str) -> str:
    """One Make per data row (multi-product), in order; pads with last or default."""
    match = re.search(
        r'(<table[^>]*class="[^"]*items-table[^"]*"[^>]*>)(.*?)(</table>)',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return html
    open_tag, inner, close = match.group(1), match.group(2), match.group(3)
    rows = re.findall(r"<tr[^>]*>.*?</tr>", inner, flags=re.DOTALL | re.IGNORECASE)
    if len(rows) < 2:
        return html
    def_m = (default_make or "").strip()
    padded: list[str] = []
    for i in range(len(rows) - 1):
        if i < len(makes) and makes[i].strip():
            padded.append(makes[i].strip())
        elif padded:
            padded.append(padded[-1])
        else:
            padded.append(def_m)
    new_rows = [rows[0]]
    for idx, row in enumerate(rows[1:]):
        make_text = padded[idx] if idx < len(padded) else def_m
        safe = escape(make_text)
        new_row = re.sub(
            r"Make\s*:\s*[^<]*",
            "Make: " + safe,
            row,
            count=1,
            flags=re.IGNORECASE,
        )
        new_rows.append(new_row)
    new_inner = "".join(new_rows)
    return html[: match.start()] + open_tag + new_inner + close + html[match.end() :]


def _apply_make_in_quotation_items(
    html: str,
    product_type: ProductType,
    manufacturer_name: str | None,
    product_name: str | None,
) -> str:
    """
    Make in items table:
    - Empty Manufacturer → default Vertex Chemical / Vertex Engineering.
    - Single Manufacturer string → that Make on every line (commas allowed if one product).
    - Comma-separated Manufacturer + comma-separated Product → one Make per row, same order.
    """
    default = (
        _MAKE_VERTEX_ENGINEERING
        if product_type == ProductType.engineering
        else _MAKE_VERTEX_CHEMICAL
    )
    mfr = (manufacturer_name or "").strip()
    if not mfr:
        if product_type == ProductType.engineering:
            return _force_make_vertex_engineering(html)
        return _force_make_vertex_chemicals(html)

    multi_product = "," in (product_name or "").strip()
    if multi_product and "," in mfr:
        parts = [p.strip() for p in mfr.split(",") if p.strip()]
        if not parts:
            return _replace_make_in_items_table(html, default)
        return _replace_make_in_items_rows(html, parts, default)
    return _replace_make_in_items_table(html, mfr)


def _inject_date(html: str, date: str | None) -> str:
    """Replace the date value cell next to 'Quotation Date' / 'Date' in the customer table."""
    if not date or not str(date).strip():
        return html
    safe = escape(str(date).strip())
    pattern = re.compile(
        r"(<td[^>]*>\s*(?:Quotation\s+)?Date\s*</td>\s*<td[^>]*>)([^<]*)(</td>)",
        re.IGNORECASE,
    )
    result = pattern.sub(rf"\g<1>{safe}\g<3>", html)
    return result


def _inject_quotation_no(html: str, quotation_no: str | None) -> str:
    """Replace the value cell next to 'Quotation No' in the customer table with the given number.
    Ensures the quotation never shows '-' or N/A when we have a generated number.
    """
    if not quotation_no or not str(quotation_no).strip():
        return html
    safe = escape(str(quotation_no).strip())
    # Customer table: label cell "Quotation No" followed by value cell; replace value cell content
    pattern = re.compile(
        r"(<td[^>]*>\s*Quotation\s+No\s*</td>\s*<td[^>]*>)([^<]*)(</td>)",
        re.IGNORECASE,
    )
    return pattern.sub(rf"\g<1>{safe}\g<3>", html)


def _inject_hsn_in_items(html: str, hsn_code: str | None, product_name: str) -> str:
    """When HSN is provided and single product, replace HSN value in items table with it.
    Ensures Excel-provided HSN is used exactly and not altered by the model.
    """
    if not hsn_code or not str(hsn_code).strip():
        return html
    # Only inject when single product (no comma); multi-product would need per-row HSN
    if "," in (product_name or "").strip():
        return html
    safe = escape(str(hsn_code).strip())
    # Within items-table only, replace "HSN: anything" with "HSN: {safe}"
    pattern = re.compile(
        r"(<table[^>]*class=[^>]*items-table[^>]*>)(.*?)(</table>)",
        re.DOTALL | re.IGNORECASE,
    )
    return pattern.sub(
        lambda m: m.group(1)
        + re.sub(r"HSN\s*:\s*[^<]*", "HSN: " + safe, m.group(2), flags=re.IGNORECASE)
        + m.group(3),
        html,
    )


def _force_make_vertex_engineering(html: str) -> str:
    """In the items-table, replace any Make: ... with Make: Vertex Engineering."""
    match = re.search(
        r'<table[^>]*class="[^"]*items-table[^"]*"[^>]*>.*?</table>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return html
    block = match.group(0)
    new_block = re.sub(
        r"Make\s*:\s*[^<]*",
        "Make: " + _MAKE_VERTEX_ENGINEERING,
        block,
        flags=re.IGNORECASE,
    )
    if new_block == block:
        return html
    return html[: match.start()] + new_block + html[match.end() :]


def _strip_engineering_quotation_brand_block(html: str) -> str:
    """Remove redundant standalone Brand heading/lines; Make + HSN belong in the items table only."""
    # Subsection titles the model sometimes adds after the items/totals tables
    html = re.sub(
        r'<h[23][^>]*>\s*Brand\s*:?\s*</h[23]>\s*',
        "",
        html,
        flags=re.IGNORECASE,
    )
    # Short paragraph that only repeats brand (e.g. "Brand: Vertex Engineering")
    html = re.sub(
        r'<p[^>]*>\s*Brand\s*:\s*[^<]{0,160}</p>\s*',
        "",
        html,
        flags=re.IGNORECASE,
        count=6,
    )
    # Bold label line "Brand:" with nothing useful after
    html = re.sub(
        r'<p[^>]*>\s*Brand\s*:\s*</p>\s*',
        "",
        html,
        flags=re.IGNORECASE,
    )
    return html


def _force_make_vertex_chemicals(html: str) -> str:
    """In the items-table, replace any Make: ... with Make: Vertex Chemical.
    Stops at HTML tags (<br/>, </td>, etc.) so line breaks are preserved."""
    match = re.search(
        r'<table[^>]*class="[^"]*items-table[^"]*"[^>]*>.*?</table>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return html
    block = match.group(0)
    # Stop match at < (HTML tag) so <br/> between Make and HSN lines is preserved
    new_block = re.sub(
        r"Make\s*:\s*[^<]*",
        "Make: " + _MAKE_VERTEX_CHEMICAL,
        block,
        flags=re.IGNORECASE,
    )
    if new_block == block:
        return html
    return html[: match.start()] + new_block + html[match.end() :]


def _bank_detail_values(product_type: ProductType) -> dict[str, str]:
    """Bank constants; engineering uses Vertex Engineering as account name."""
    d = dict(_BANK_DETAIL_VALUES)
    if product_type == ProductType.engineering:
        d["account name"] = "VERTEX ENGINEERING"
    return d


def _force_bank_details(html: str, product_type: ProductType = ProductType.chemical) -> str:
    """In the delivery-table, overwrite bank-detail value cells with fixed constants.
    The table has 4 columns per row: DeliveryLabel | DeliveryValue | BankLabel | BankValue.
    We identify rows by BankLabel text and replace BankValue with the constant."""
    bank_vals = _bank_detail_values(product_type)

    def _process_delivery_table(m: re.Match) -> str:
        before, body, after = m.group(1), m.group(2), m.group(3)

        def _fix_row(row_m: re.Match) -> str:
            row = row_m.group(0)
            tds = list(re.finditer(r"(<td[^>]*>)(.*?)(</td>)", row, re.DOTALL | re.IGNORECASE))
            if len(tds) < 4:
                return row
            label_td = tds[2]
            value_td = tds[3]
            label_text = re.sub(r"<[^>]+>", "", label_td.group(2)).strip().lower().rstrip(":")
            fixed_val = bank_vals.get(label_text)
            if fixed_val is None:
                return row
            # Replace value cell content with fixed value
            new_value_inner = label_td.group(1).replace(label_td.group(1), value_td.group(1)) + fixed_val + value_td.group(3)
            row = row[: value_td.start()] + value_td.group(1) + fixed_val + value_td.group(3) + row[value_td.end():]
            return row

        body = re.sub(r"<tr[^>]*>.*?</tr>", _fix_row, body, flags=re.DOTALL | re.IGNORECASE)
        return before + body + after

    html = re.sub(
        r'(<table[^>]*class="[^"]*delivery-table[^"]*"[^>]*>)(.*?)(</table>)',
        _process_delivery_table,
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return html


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
    hsn_code: str | None = None,
    quantity: str | None = None,
    unit: str | None = None,
    country: str | None = None,
    port: str | None = None,
    incoterm: str | None = None,
    payment_terms: str | None = None,
    remarks: str | None = None,
    manufacturer_name: str | None = None,
    date: str | None = None,
) -> list[DocumentCreate]:
    """Build four separate documents: Quotation, TDS, COA, MSDS. Terms are only in Quotation (from AI output, not appended)."""
    # Quotation: do not append terms here — the AI-generated quotation already includes TERMS & CONDITIONS once (from prompt).
    # Multi-product: signatory after 15. Single-product: 13–15 left, signatory right.
    multi_product = "," in (product_name or "").strip()
    q_html = text_to_html(quotation_text, compact=True, multi_product=multi_product)
    q_html = _fix_description_line_breaks(q_html)
    # Always ensure exactly one QUOTATION heading is present. The AI sometimes includes its
    # own leading <h1> (occasionally with markdown/formatting quirks that don't match a strict
    # "QUOTATION"-only regex, e.g. "**QUOTATION**"), and multi-product generation can leave a
    # stray marker line so TWO leading <h1> blocks stack up — strip ALL leading headings (and
    # any blank-paragraph filler between them) rather than just the first, so a near-miss or a
    # stacked duplicate can never survive as two headings.
    q_heading = '<h1 style="font-weight:bold;text-align:center;text-transform:uppercase;letter-spacing:0.04em;">QUOTATION</h1>'
    while True:
        leading_heading = re.match(
            r"\s*(?:<h1[^>]*>.*?</h1>|<p[^>]*>\s*(?:<br\s*/?>|&nbsp;)?\s*</p>)",
            q_html, re.IGNORECASE | re.DOTALL,
        )
        if not leading_heading:
            break
        q_html = q_html[leading_heading.end():]
    q_html = q_heading + q_html
    q_html = QUOTATION_WRAPPER + q_html + QUOTATION_WRAPPER_END
    q_html = _force_bank_details(q_html, product_type=product_type)
    q_html = _apply_make_in_quotation_items(
        q_html, product_type, manufacturer_name, product_name
    )
    if product_type == ProductType.engineering:
        q_html = _strip_engineering_quotation_brand_block(q_html)
    q_html = _ensure_currency_in_totals(q_html, local_export)
    if quotation_no:
        q_html = _inject_quotation_no(q_html, quotation_no)
    if date:
        q_html = _inject_date(q_html, date)
    hsn_stripped = str(hsn_code).strip() if hsn_code else ""
    if hsn_stripped:
        q_html = _inject_hsn_in_items(q_html, hsn_stripped, product_name)

    letterhead_val = letterhead.strip().lower() if (letterhead and isinstance(letterhead, str)) else None
    local_export_val = local_export.strip().lower() if (local_export and isinstance(local_export, str)) else None
    common_base = {
        "buyer_name": buyer_name,
        "product_type": product_type,
        "batch_id": batch_id,
        "employee_name": employee_name,
        "letterhead": letterhead_val if letterhead_val in ("dubai", "india") else None,
        "local_export": local_export_val,
        "quantity": quantity,
        "unit": unit,
        "country": country,
        "port": port,
        "incoterm": incoterm,
        "payment_terms": payment_terms,
        "remarks": remarks,
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
        raw_use = raw_text
        if doc_type_key == "tds" and product_type == ProductType.engineering:
            raw_use = _strip_engineering_tds_commercial_lines(raw_use)
        cleaned = _clean_doc_text(raw_use)
        body_html = text_to_html(
            cleaned,
            tight_spacing=(doc_type_key == "tds" and product_type == ProductType.engineering),
        )
        if doc_type_key == "tds" and product_type == ProductType.engineering:
            pname = escape((sec_product or product_name or "Product").strip())
            heading = (
                f'<h1 class="engineering-tech-title" style="{_H1_STYLE}">{pname}</h1>'
                f'<h2 class="engineering-tech-subtitle" style="font-weight:bold;text-align:center;text-transform:uppercase;letter-spacing:0.04em;font-size:12pt;margin:6px 0 12px 0;">TECHNICAL DATA SHEET</h2>'
            )
            body_html = re.sub(
                rf'<h1[^>]*>\s*{re.escape(pname)}\s*</h1>',
                "",
                body_html,
                flags=re.IGNORECASE,
                count=1,
            )
        else:
            title = _DOC_TITLES[doc_type_key]
            heading = f'<h1 style="{_H1_STYLE}">{title}</h1>'
            body_html = re.sub(
                rf'<h1[^>]*>\s*{re.escape(title)}\s*</h1>',
                "",
                body_html,
                flags=re.IGNORECASE,
            )
        full_html = heading + "\n" + body_html
        if is_coa:
            full_html = '<div class="coa-section">' + full_html + "</div>"
        elif doc_type_key == "tds" and product_type == ProductType.engineering:
            full_html = '<div class="engineering-tech-doc">' + full_html + "</div>"
        dt = {"tds": DocumentType.tds, "coa": DocumentType.coa, "msds": DocumentType.msds}[doc_type_key]
        return DocumentCreate(**common_base, product_name=sec_product, doc_type=dt, html_content=full_html)

    # TDS: one document per product (section) — chemical TDS or engineering TECHNICAL DESCRIPTION
    tds_pattern = r"#\s*(?:TECHNICAL DATA SHEET\s*\(TDS\)|TECHNICAL DESCRIPTION)"
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
