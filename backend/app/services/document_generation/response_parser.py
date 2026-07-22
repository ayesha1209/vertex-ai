"""
Parse AI response into sections and convert to clean HTML for PDF/DOCX.
We control formatting: inline styles only (PDF-engine safe), semantic tags, table headers.
"""

import logging
import re
from html import escape

logger = logging.getLogger(__name__)


def _render_signature_lines(html_lines: list, signature_lines: list) -> None:
    """Append signature text lines to html_lines (image injected at PDF export time)."""
    for ln in signature_lines:
        parts = [p.strip() for p in ln.split("|") if p.strip()]
        for part in parts:
            html_lines.append(f"<p style=\"text-align:right; margin:2px 0; display:block;\"><strong>{escape(part)}</strong></p>")
        if not parts:
            html_lines.append(f"<p style=\"text-align:right; margin:2px 0; display:block;\"><strong>{escape(ln)}</strong></p>")


# Section markers in output order: Quotation → TDS → COA → MSDS
MARKER_QUOTATION = "# QUOTATION"
MARKER_TDS = "# TECHNICAL DATA SHEET (TDS)"
MARKER_COA = "# CERTIFICATE OF ANALYSIS (COA)"
MARKER_MSDS = "# MATERIAL SAFETY DATA SHEET (MSDS)"

# Border style
_B = "1px solid #333"

# Non-quotation tables: full inline styles for TDS/COA/MSDS
_STYLE_TABLE = f"border-collapse:collapse;table-layout:fixed;width:100%;border:{_B};"
_STYLE_TH = f"border:{_B};padding:4px 6px;text-align:left;font-weight:bold;background:#f2f2f2;vertical-align:top;"
_STYLE_TD = f"border:{_B};padding:4px 6px;text-align:left;vertical-align:top;"
_STYLE_TD_LABEL = f"border:{_B};padding:4px 6px;text-align:left;vertical-align:top;font-weight:bold;"

# Quotation tables: inline styles that survive export normalization
_Q_TABLE = f"border-collapse:collapse;width:100%;border:{_B};"
_Q_TH = f"border:{_B};text-align:left;font-weight:bold;background:#bbb;vertical-align:top;"
_Q_TD = f"border:{_B};text-align:left;vertical-align:top;"
_Q_TD_LABEL = f"border:{_B};text-align:left;vertical-align:top;font-weight:bold;"
_Q_TD_BOLD = f"border:{_B};text-align:left;vertical-align:top;font-weight:bold;"

_STYLE_HR = "border:none;border-top:1px solid #444;"
_STYLE_H1 = "font-weight:bold;text-align:center;text-transform:uppercase;letter-spacing:0.04em;"
_STYLE_H2 = "font-weight:bold;text-transform:uppercase;letter-spacing:0.03em;"
# Section subheadings (e.g. Identification of the Substance): bold, slightly larger
_STYLE_H2_SECTION = "font-weight:bold;font-size:12px;letter-spacing:0.02em;margin:8px 0 4px 0;"
_STYLE_H3 = "font-weight:bold;letter-spacing:0.02em;"
_STYLE_P = ""
_STYLE_P_BOLD = "font-weight:bold;"
_STYLE_P_COA_CONCLUSION = ""
_STYLE_P_BOLD_COA_CONCLUSION = "font-weight:bold;"
# TDS / technical description: visible bullets and spacing (PDF engines honor list-style on ul/li)
_STYLE_UL = (
    "margin:4px 0 8px 0;padding-left:1.35em;list-style-type:disc;"
    "list-style-position:outside;"
)
_STYLE_LI = "margin:3px 0;line-height:1.4;display:list-item;"
_STYLE_LI_SUB = "margin:2px 0;line-height:1.35;list-style-type:circle;display:list-item;"

PAGE_BREAK = '<div style="page-break-after:always;"></div>'


def _normalize_spacing(text: str) -> str:
    """Correct spacing issues for print: collapse multiple spaces, no leading/trailing per line."""
    lines = text.splitlines()
    out = []
    for line in lines:
        out.append(re.sub(r" +", " ", line).strip())
    return "\n".join(out)


def _inline_bold_md(text: str) -> str:
    """Turn **bold** into <strong> after escaping non-bold segments."""
    if "**" not in text:
        return escape(text)
    parts = text.split("**")
    out: list[str] = []
    for i, segment in enumerate(parts):
        if not segment:
            continue
        if i % 2 == 1:
            out.append(f"<strong>{escape(segment)}</strong>")
        else:
            out.append(escape(segment))
    return "".join(out)


# Quotation table types
_Q_TABLE_CUSTOMER = 0
_Q_TABLE_DELIVERY = 1
_Q_TABLE_ITEMS = 2
_Q_TABLE_TOTALS = 3
_Q_TABLE_WEIGHT_PACKING = 4

# Content signatures used to identify a quotation table by its first row's
# text when the table can't be identified some other way (e.g. by CSS class).
# Shared with invoice_generator.py's content-based extraction fallback (used
# when a quotation's table CSS classes were stripped, e.g. by a TipTap
# re-save) so the two stay in sync — a table this module can classify should
# always be findable by invoice_generator.py too.
CUSTOMER_TABLE_SIGNATURES = ("bill to", "buyer")
TOTALS_TABLE_SIGNATURES = ("total amount",)
ITEMS_TABLE_SIGNATURES = ("description of goods", "unit price", "part number")


def _detect_table_type(table_rows: list[str]) -> int:
    """Detect quotation table type based on content."""
    if not table_rows:
        return -1

    first_row = table_rows[0].lower()

    # Weight & packing (engineering): header also says "Part Number" — must run before items
    if (
        "net weight" in first_row
        and "gross weight" in first_row
        and ("packing" in first_row or "packing dimensions" in first_row)
    ):
        return _Q_TABLE_WEIGHT_PACKING

    # Items table: chemical No.|... or engineering Sr.|... / Part Number column
    if (
        first_row.startswith("no.")
        or first_row.startswith("no|")
        or first_row.startswith("sr.")
        or first_row.startswith("sr|")
        or any(sig in first_row for sig in ITEMS_TABLE_SIGNATURES)
    ):
        return _Q_TABLE_ITEMS

    # Totals table: contains "Total Amount"
    if any(sig in first_row for sig in TOTALS_TABLE_SIGNATURES):
        return _Q_TABLE_TOTALS

    # Customer table: contains "Bill To" (chemical) or starts with "Buyer" (engineering header block)
    if any(sig in first_row for sig in CUSTOMER_TABLE_SIGNATURES):
        return _Q_TABLE_CUSTOMER

    # Delivery table: contains "Delivery" as first cell
    if first_row.startswith("delivery"):
        return _Q_TABLE_DELIVERY

    return -1


def _strip_leading_trailing_empty_pipe_segments(cells: list[str]) -> list[str]:
    """Remove empty columns from leading/trailing pipes (e.g. |A|B| -> not 4 cols)."""
    while cells and cells[0].strip() == "":
        cells = cells[1:]
    while cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.strip() for c in cells]


def _is_markdown_table_separator_row(cells: list[str]) -> bool:
    """Skip markdown-style separator rows like | --- | --- |."""
    if len(cells) == 1 and cells[0].strip() and re.match(r"^[-:\s]+$", cells[0].strip()):
        return True
    if len(cells) < 2:
        return False
    for c in cells:
        t = c.strip()
        if not t:
            continue
        if not re.match(r"^[-:\s]+$", t):
            return False
    return True


def _parse_weight_total_gross_two_column(cells: list[str]) -> tuple[str, str]:
    """Split Total Gross Weight into label + value for a two-cell summary row."""
    ext = list(cells) + [""] * max(0, 5 - len(cells))
    c0 = ext[0].strip()
    c1 = ext[1].strip()
    m = re.match(r"(?i)(total\s+gross\s+weight\s*:)\s*(.+)$", c0)
    if m and m.group(2).strip():
        return (m.group(1).strip(), m.group(2).strip())
    if re.search(r"(?i)total\s+gross\s+weight", c0):
        if c1:
            return ("Total Gross Weight:", c1)
        m2 = re.search(r"(?i)total\s+gross\s+weight\s*:\s*(.+)", c0)
        if m2 and m2.group(1).strip():
            return ("Total Gross Weight:", m2.group(1).strip())
    return ("Total Gross Weight:", c1 or "—")


def _bullet_text_after_marker(stripped: str) -> str | None:
    """If line starts with • (or common unicode bullets), return text after marker."""
    if not stripped:
        return None
    s = stripped.lstrip("\ufeff")
    if not s:
        return None
    if s[0] in ("•", "\u2022", "\u25cf", "\u25e6", "\u2043"):
        return s[1:].strip()
    return None


def _flush_quotation_table(
    table_rows: list[str],
    html_lines: list[str],
    table_index: int,
) -> None:
    """Render quotation table with proper column widths based on table type."""
    if not table_rows:
        return

    # Detect table type from content instead of relying on index
    detected_type = _detect_table_type(table_rows)
    table_type = detected_type if detected_type >= 0 else table_index

    # Determine label columns
    if table_type == _Q_TABLE_CUSTOMER:
        label_cols = {0, 2}
    elif table_type == _Q_TABLE_DELIVERY:
        label_cols = {0, 2}
    elif table_type == _Q_TABLE_ITEMS:
        label_cols = set()
    elif table_type == _Q_TABLE_TOTALS:
        label_cols = {0}
    elif table_type == _Q_TABLE_WEIGHT_PACKING:
        label_cols = set()
    else:
        label_cols = set()

    items_ncols = 5
    if table_type == _Q_TABLE_ITEMS and table_rows:
        items_ncols = max(5, len(table_rows[0].split("|")))

    # Add class for each table type to apply CSS styles. The 6-column items table (Sr/Desc/
    # Part/Qty/Price/Amount) gets its own modifier class — print_css.py's plain .items-table
    # nth-child width rules are tuned for the 5-column layout and would force the first 5
    # columns to 100% width, pushing the 6th (Amount) column outside the table entirely.
    if table_type == _Q_TABLE_CUSTOMER:
        table_class = ' class="customer-table"'
    elif table_type == _Q_TABLE_DELIVERY:
        table_class = ' class="delivery-table"'
    elif table_type == _Q_TABLE_ITEMS:
        table_class = ' class="items-table items-table-6col"' if items_ncols >= 6 else ' class="items-table"'
    elif table_type == _Q_TABLE_TOTALS:
        table_class = ' class="totals-table"'
    elif table_type == _Q_TABLE_WEIGHT_PACKING:
        table_class = ' class="weight-packing-table"'
    else:
        table_class = ''
    html_lines.append(f'<table{table_class} style="{_Q_TABLE}">')

    # Add colgroup for items table to control column widths (5 columns = chemical style; 6 = Sr/Desc/Part/Qty/Price/Amount)
    if table_type == _Q_TABLE_ITEMS:
        if items_ncols >= 6:
            html_lines.append(
                '<colgroup><col style="width:6%"/><col style="width:35%"/><col style="width:14%"/>'
                '<col style="width:11%"/><col style="width:17%"/><col style="width:17%"/></colgroup>'
            )
        else:
            html_lines.append(
                '<colgroup><col style="width:6%"/><col style="width:40%"/><col style="width:14%"/>'
                '<col style="width:20%"/><col style="width:20%"/></colgroup>'
            )
    elif table_type == _Q_TABLE_WEIGHT_PACKING:
        html_lines.append(
            '<colgroup><col style="width:18%"/><col style="width:11%"/><col style="width:11%"/>'
            '<col style="width:28%"/><col style="width:32%"/></colgroup>'
        )

    num_start_items = 3 if items_ncols >= 6 else 2

    for row_idx, row in enumerate(table_rows):
        # Split by pipe; drop leading/trailing empty columns (fixes |Col|Col| ghost columns)
        raw_cells = row.split("|")
        cells = [c.strip() for c in raw_cells]
        cells = _strip_leading_trailing_empty_pipe_segments(cells)
        if _is_markdown_table_separator_row(cells):
            continue

        if table_type == _Q_TABLE_ITEMS:
            while len(cells) < items_ncols:
                cells.append("")
            cells = cells[:items_ncols]
        elif table_type == _Q_TABLE_WEIGHT_PACKING:
            while len(cells) < 5:
                cells.append("")
            cells = cells[:5]

        # For 4-column tables, ensure we have exactly 4 cells
        if table_type in (_Q_TABLE_CUSTOMER, _Q_TABLE_DELIVERY):
            while len(cells) < 4:
                cells.append("")
            cells = cells[:4]
            # Do not include Currency / Currency USD row in delivery table (user requested removal)
            if table_type == _Q_TABLE_DELIVERY and cells[0].strip().lower().startswith("currency"):
                continue
        
        if not any(cells):
            continue

        is_header = (table_type == _Q_TABLE_ITEMS and row_idx == 0) or (
            table_type == _Q_TABLE_WEIGHT_PACKING and row_idx == 0
        )
        row_joined = " ".join(cells).lower()
        is_weight_total_row = (
            table_type == _Q_TABLE_WEIGHT_PACKING
            and row_idx > 0
            and "total gross weight" in row_joined
        )

        # Total Gross Weight: one row with exactly two cells (colspan 3 + 2), not five narrow columns
        if is_weight_total_row:
            lbl, val = _parse_weight_total_gross_two_column(cells)
            lbl_html = _inline_bold_md(lbl)
            val_html = _inline_bold_md(val)
            td_base = f"border:{_B};vertical-align:middle;font-weight:bold;background-color:#ffffff;"
            html_lines.append("<tr>")
            html_lines.append(
                f'<td colspan="3" style="{td_base}text-align:left;">'
                f"<strong><b>{lbl_html}</b></strong></td>"
                f'<td colspan="2" style="{td_base}text-align:right;">'
                f"<strong><b>{val_html}</b></strong></td>"
            )
            html_lines.append("</tr>")
            continue

        html_lines.append("<tr>")
        for col_idx, c in enumerate(cells):
            # Handle description - force line breaks before Make: and HSN:
            # Apply to column 1 (Description) of items table
            if table_type == _Q_TABLE_ITEMS and col_idx == 1 and row_idx > 0:
                # Clean up: remove // separators and extra spaces
                text = re.sub(r"\s*//\s*", " ", c)
                text = re.sub(r"\s+", " ", text).strip()

                # Split into parts: Product Name, Make:..., HSN:...
                make_match = re.search(r"Make\s*:", text, re.IGNORECASE)
                hsn_match = re.search(r"HSN\s*:", text, re.IGNORECASE)

                parts = []
                if make_match:
                    product_name = text[: make_match.start()].strip()
                    if product_name:
                        parts.append(_inline_bold_md(product_name))

                    if hsn_match and hsn_match.start() > make_match.start():
                        make_part = text[make_match.start() : hsn_match.start()].strip()
                        hsn_part = text[hsn_match.start() :].strip()
                        parts.append(_inline_bold_md(make_part))
                        parts.append(_inline_bold_md(hsn_part))
                    else:
                        make_part = text[make_match.start() :].strip()
                        parts.append(_inline_bold_md(make_part))
                else:
                    parts.append(_inline_bold_md(text))

                cell_content = "<br/>".join(parts) if parts else "&nbsp;"
            else:
                cell_content = _inline_bold_md(c) if c else "&nbsp;"
            
            # All cells use <td> to prevent TipTap from converting to <th>
            # Use inline styles for header appearance
            if is_header:
                if table_type == _Q_TABLE_WEIGHT_PACKING:
                    col_widths = ["18%", "11%", "11%", "28%", "32%"]
                    width_style = f"width:{col_widths[col_idx]};" if col_idx < len(col_widths) else ""
                    nowrap = "white-space:nowrap;" if col_idx == 0 else ""
                    style = f"border:{_B};{width_style}{nowrap}text-align:left;font-weight:bold;vertical-align:top;background-color:#BBBBBB;"
                    if col_idx in (1, 2):
                        style = style.replace("text-align:left;", "text-align:right;")
                    html_lines.append(f'<td bgcolor="#BBBBBB" style="{style}"><b>{cell_content}</b></td>')
                else:
                    # Items table header: gray background, bold, with column widths
                    col_widths = (
                        ["6%", "35%", "14%", "11%", "17%", "17%"]
                        if items_ncols >= 6
                        else ["6%", "40%", "14%", "20%", "20%"]
                    )
                    width_style = f"width:{col_widths[col_idx]};" if col_idx < len(col_widths) else ""
                    nowrap = "white-space:nowrap;" if col_idx == 0 else ""
                    style = f"border:{_B};{width_style}{nowrap}text-align:left;font-weight:bold;vertical-align:top;background-color:#BBBBBB;"
                    if col_idx >= num_start_items:  # Right-align numeric headers
                        style = style.replace("text-align:left;", "text-align:right;")
                    html_lines.append(f'<td bgcolor="#BBBBBB" style="{style}"><b>{cell_content}</b></td>')
            else:
                # Use bold style for Total Amount row (first row of totals table)
                is_total_row = table_type == _Q_TABLE_TOTALS and row_idx == 0
                # Check if this is the "Total Amount" label cell
                is_total_amount_label = table_type == _Q_TABLE_TOTALS and "Total Amount" in str(c)

                if is_total_row or is_total_amount_label:
                    style = f"border:{_B};text-align:left;vertical-align:top;font-weight:bold;background-color:#ffffff;"
                    cell_content = f"<strong><b>{cell_content}</b></strong>"
                else:
                    # Explicitly set white background for all non-header cells
                    base_style = _Q_TD_LABEL if col_idx in label_cols else _Q_TD
                    style = base_style + "background-color:#ffffff;"
                if table_type == _Q_TABLE_ITEMS and col_idx == 0:
                    style += "white-space:nowrap;"
                if table_type == _Q_TABLE_WEIGHT_PACKING and col_idx == 0:
                    style += "white-space:nowrap;"
                # Right-align numeric columns in items table
                if table_type == _Q_TABLE_ITEMS and col_idx >= num_start_items:
                    style += "text-align:right;"
                # Net / gross weight columns
                if table_type == _Q_TABLE_WEIGHT_PACKING and col_idx in (1, 2):
                    style += "text-align:right;"
                # Right-align value column in totals
                if table_type == _Q_TABLE_TOTALS and col_idx == 1:
                    style += "text-align:right;"
                html_lines.append(f'<td style="{style}">{cell_content}</td>')
        html_lines.append("</tr>")
    
    html_lines.append("</table>")


def _flush_table(
    table_rows: list[str],
    html_lines: list[str],
    compact: bool = False,
    table_index: int | None = None,
) -> None:
    """Flush accumulated table rows as HTML table."""
    if not table_rows:
        return
    
    if compact and table_index is not None:
        _flush_quotation_table(table_rows, html_lines, table_index)
        return

    # Non-quotation tables (TDS/COA/MSDS engineering technical specs)
    processed_rows: list[list[str]] = []
    for row in table_rows:
        raw = [c.strip() for c in row.split("|")]
        cells = _strip_leading_trailing_empty_pipe_segments(raw)
        if not cells:
            continue
        if _is_markdown_table_separator_row(cells):
            continue
        processed_rows.append(cells)

    if not processed_rows:
        return

    col_counts = [len(r) for r in processed_rows]
    two_col_kv = len(col_counts) > 0 and all(n == 2 for n in col_counts)
    
    html_lines.append(f'<table style="{_STYLE_TABLE}">')
    if two_col_kv:
        html_lines.append(
            '<colgroup><col style="width:38%"/><col style="width:62%"/></colgroup>'
        )
    for row_idx, cells in enumerate(processed_rows):
        is_header_row = row_idx == 0
        tag = "th" if is_header_row else "td"
        parts = []
        for col_idx, c in enumerate(cells):
            c_html = _inline_bold_md(c)
            if is_header_row:
                style = _STYLE_TH
            elif two_col_kv and col_idx == 0:
                style = _STYLE_TD_LABEL
            else:
                style = _STYLE_TD
            parts.append(f'<{tag} style="{style}">{c_html}</{tag}>')
        html_lines.append("<tr>" + "".join(parts) + "</tr>")
    html_lines.append("</table>")


def _render_terms_block(
    lines: list[str], start_idx: int, html_lines: list[str], multi_product: bool = False
) -> int:
    """Render the TERMS block. Multi-product: all terms full width, signatory after 15. Else: 13–15 left, signatory right."""
    i = start_idx + 1  # Skip ---TERMSBLOCK---
    terms_lines = []
    signature_lines = []
    in_signature = False

    while i < len(lines):
        line = lines[i].strip()
        if line == "---TERMSBLOCK---" or line == "---TERMS---":
            i += 1
            break
        is_sig_like = "AUTHORIZED" in line.upper() or ("PLACE" in line.upper() and "DATE" in line.upper())
        if "AUTHORIZED SIGNATORY" in line.upper() or is_sig_like:
            in_signature = True
            signature_lines.append(line)
        elif in_signature:
            if line:
                signature_lines.append(line)
        else:
            if line:
                terms_lines.append(line)
        i += 1

    if multi_product:
        terms_upper = terms_lines
        terms_lower = []
    else:
        split_idx = None
        for idx, ln in enumerate(terms_lines):
            if re.match(r"^\s*13\.", ln.strip()):
                split_idx = idx
                break
        terms_upper = terms_lines[:split_idx] if split_idx is not None else terms_lines
        terms_lower = terms_lines[split_idx:] if split_idx is not None else []

    # No page-break-inside:avoid here — the wrapper holds the ENTIRE terms list plus
    # the signature table, and marking that whole (unbounded-length) block unbreakable
    # pushed it to a fresh, mostly-blank page and could overflow past the xhtml2pdf
    # content frame. Only the small terms-sig-table/signatory-block tail needs to stay
    # together; the terms text itself paginates fine like any other paragraph flow.
    html_lines.append('<div class="terms-sig-wrapper" style="page-break-before:avoid !important; margin-top:0; padding-top:0;">')
    html_lines.append('<div class="terms-section terms-upper" style="width:100%; page-break-after:avoid !important;">')
    for ln in terms_upper:
        if ln.startswith("TERMS"):
            html_lines.append(f"<p style=\"margin:2px 0; display:block;\"><strong>{escape(ln)}</strong></p>")
        else:
            html_lines.append(f"<p style=\"margin:2px 0; display:block;\">{escape(ln)}</p>")
    html_lines.append("</div>")
    if terms_lower and signature_lines:
        html_lines.append('<table class="terms-sig-table" style="width:100%; border:none !important; border-collapse:collapse; margin:0; margin-top:0; page-break-inside:avoid !important;">')
        html_lines.append('<tr style="border:none !important; vertical-align:top;">')
        html_lines.append('<td class="terms-section terms-left-col" style="width:60%; border:none !important; padding:0 12px 0 0 !important; padding-left:0 !important; margin:0; vertical-align:top;"><div class="terms-section" style="display:block; padding-left:0; margin-left:0;">')
        for ln in terms_lower:
            html_lines.append(f"<p style=\"margin:2px 0; display:block;\">{escape(ln)}</p>")
        html_lines.append("</div></td>")
        html_lines.append('<td style="width:40%; border:none !important; padding:0; text-align:right; vertical-align:top;"><div class="signatory-block" style="text-align:right; margin-top:0; page-break-before:avoid !important; page-break-inside:avoid !important;">')
        _render_signature_lines(html_lines, signature_lines)
        html_lines.append("</div></td></tr></table>")
    elif terms_lower:
        html_lines.append('<div class="terms-section" style="width:100%;">')
        for ln in terms_lower:
            html_lines.append(f"<p style=\"margin:2px 0; display:block;\">{escape(ln)}</p>")
        html_lines.append("</div>")
    elif signature_lines:
        # A plain div isn't reliably kept together by xhtml2pdf's page-break-inside;
        # a single-cell table is (same mechanism as the terms-sig-table split case
        # above), so the stamp/heading/date can't be split across a page break.
        html_lines.append('<table class="terms-sig-table" style="width:100%; border:none !important; border-collapse:collapse; margin:0; margin-top:4px; page-break-inside:avoid !important;">')
        html_lines.append('<tr style="border:none !important; vertical-align:top;">')
        html_lines.append('<td style="border:none !important; padding:0; text-align:right; vertical-align:top;"><div class="signatory-block" style="text-align:right; margin-top:0;">')
        _render_signature_lines(html_lines, signature_lines)
        html_lines.append("</div></td></tr></table>")
    html_lines.append("</div>")
    return i


def text_to_html(
    text: str,
    compact: bool = False,
    multi_product: bool = False,
    tight_spacing: bool = False,
) -> str:
    """
    Convert AI text to clean HTML. Inline styles only for best PDF/DOCX output.
    Preserves: tables (| and ---TABLE---), horizontal rules (---), bullets, headings.
    If compact=True (for quotation), uses smaller fonts and tight padding for one-page layout.
    If multi_product=True (quotation with multiple products), terms are full width and signatory after 15.
    If tight_spacing=True (e.g. engineering technical description), blank lines are skipped (no empty paragraphs).
    """
    text = _normalize_spacing(text)
    lines = text.splitlines()
    html_lines: list[str] = []
    in_table = False
    table_rows: list[str] = []
    in_ul = False
    in_section_block = False
    in_coa_conclusion = False
    table_counter = 0

    def close_section_block() -> None:
        nonlocal in_section_block
        if in_section_block:
            html_lines.append("</div>")
            in_section_block = False

    def close_coa_conclusion() -> None:
        nonlocal in_coa_conclusion
        if in_coa_conclusion:
            html_lines.append("</div>")
            in_coa_conclusion = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False

    i = 0
    has_content = False  # Track if we've added any real content yet
    
    while i < len(lines):
        line = lines[i].rstrip("\n")
        stripped = line.strip()

        # Skip section markers
        if stripped.startswith("=== SECTION") and stripped.endswith("==="):
            i += 1
            continue

        # Terms block - detect by marker OR by "TERMS & CONDITIONS:" text
        if stripped in ("---TERMS---", "---TERMSBLOCK---") or stripped.startswith("TERMS & CONDITIONS"):
            close_ul()
            if stripped.startswith("TERMS & CONDITIONS"):
                # Collect all terms and signature lines (like pre–editable-terms behaviour: one block, no new page)
                terms_lines: list[str] = [stripped]
                signature_lines: list[str] = []
                in_sig = False
                i += 1
                # Only break on # when it starts the next document section (TDS/COA/MSDS), not on e.g. "# AUTHORIZED"
                def _is_next_section_header(line: str) -> bool:
                    if not line.startswith("#"):
                        return False
                    u = line.upper()
                    return (
                        "TECHNICAL DATA" in u or "TECHNICAL DATA SHEET" in u or "TECHNICAL DESCRIPTION" in u
                        or "CERTIFICATE OF ANALYSIS" in u or " COA " in u or u.strip().startswith("# COA")
                        or "MATERIAL SAFETY" in u or "MSDS" in u
                        or ("SECTION" in u and "===" in line)
                    )
                while i < len(lines):
                    ln = lines[i].strip()
                    if ln == "---TERMSBLOCK---" or ln == "---TERMS---":
                        i += 1
                        break
                    if _is_next_section_header(ln):
                        break
                    # Do not break on "|" for signatory-like lines (e.g. "Authorized Signatory | Place & Date | Hamburg")
                    # so they are not rendered as a pipe table row; we collect and render them stacked.
                    is_sig_like = "AUTHORIZED" in ln.upper() or ("PLACE" in ln.upper() and "DATE" in ln.upper())
                    if "|" in ln and not in_sig and not is_sig_like:
                        break
                    if "AUTHORIZED SIGNATORY" in ln.upper() or is_sig_like:
                        in_sig = True
                        signature_lines.append(ln)
                    elif in_sig:
                        if ln:
                            signature_lines.append(ln)
                    else:
                        if ln:
                            terms_lines.append(ln)
                    i += 1
                
                # Multi-product: all terms full width, signatory after 15. Single-product: 13–15 left, signatory right.
                if multi_product:
                    terms_upper = terms_lines
                    terms_lower = []
                else:
                    split_idx = None
                    for idx, ln in enumerate(terms_lines):
                        if re.match(r"^\s*13\.", ln.strip()):
                            split_idx = idx
                            break
                    terms_upper = terms_lines[:split_idx] if split_idx is not None else terms_lines
                    terms_lower = terms_lines[split_idx:] if split_idx is not None else []
                # No page-break-inside:avoid here — the wrapper holds the ENTIRE terms list plus
                # the signature table, and marking that whole (unbounded-length) block unbreakable
                # pushed it to a fresh, mostly-blank page and could overflow past the xhtml2pdf
                # content frame. Only the small terms-sig-table/signatory-block tail needs to stay
                # together; the terms text itself paginates fine like any other paragraph flow.
                html_lines.append('<div class="terms-sig-wrapper" style="page-break-before:avoid !important; margin-top:0; padding-top:0;">')
                html_lines.append('<div class="terms-section terms-upper" style="width:100%; page-break-after:avoid !important;">')
                for ln in terms_upper:
                    if ln.startswith("TERMS"):
                        html_lines.append(f"<p style=\"margin:2px 0; display:block;\"><strong>{escape(ln)}</strong></p>")
                    else:
                        html_lines.append(f"<p style=\"margin:2px 0; display:block;\">{escape(ln)}</p>")
                html_lines.append("</div>")
                if terms_lower and signature_lines:
                    # 13–15 left, signatory right; zero left padding so 13,14,15 align with 1–12
                    html_lines.append('<table class="terms-sig-table" style="width:100%; border:none !important; border-collapse:collapse; margin:0; margin-top:0; page-break-inside:avoid !important;">')
                    html_lines.append('<tr style="border:none !important; vertical-align:top;">')
                    html_lines.append('<td class="terms-section terms-left-col" style="width:60%; border:none !important; padding:0 12px 0 0 !important; padding-left:0 !important; margin:0; vertical-align:top;"><div class="terms-section" style="display:block; padding-left:0; margin-left:0;">')
                    for ln in terms_lower:
                        html_lines.append(f"<p style=\"margin:2px 0; display:block;\">{escape(ln)}</p>")
                    html_lines.append("</div></td>")
                    html_lines.append('<td style="width:40%; border:none !important; padding:0; text-align:right; vertical-align:top;"><div class="signatory-block" style="text-align:right; margin-top:0; page-break-before:avoid !important; page-break-inside:avoid !important;">')
                    _render_signature_lines(html_lines, signature_lines)
                    html_lines.append("</div></td></tr></table>")
                elif terms_lower:
                    html_lines.append('<div class="terms-section" style="width:100%;">')
                    for ln in terms_lower:
                        html_lines.append(f"<p style=\"margin:2px 0; display:block;\">{escape(ln)}</p>")
                    html_lines.append("</div>")
                elif signature_lines:
                    # A plain div isn't reliably kept together by xhtml2pdf's
                    # page-break-inside; a single-cell table is (same mechanism as
                    # the terms-sig-table split case above), so the stamp/heading/
                    # date can't be split across a page break.
                    html_lines.append('<table class="terms-sig-table" style="width:100%; border:none !important; border-collapse:collapse; margin:0; margin-top:4px; page-break-inside:avoid !important;">')
                    html_lines.append('<tr style="border:none !important; vertical-align:top;">')
                    html_lines.append('<td style="border:none !important; padding:0; text-align:right; vertical-align:top;"><div class="signatory-block" style="text-align:right; margin-top:0;">')
                    _render_signature_lines(html_lines, signature_lines)
                    html_lines.append("</div></td></tr></table>")
                html_lines.append("</div>")
            else:
                i = _render_terms_block(lines, i, html_lines, multi_product)
            continue
        
        # Skip signature block markers (handled in terms block)
        if stripped == "---SIGNATURE---":
            i += 1
            continue

        # Horizontal rule - skip if at the very beginning (no content yet)
        if stripped in ("---", "—", "___", "__________"):
            if has_content:
                close_ul()
                close_section_block()
                html_lines.append(f'<hr style="{_STYLE_HR}"/>')
            i += 1
            continue

        if stripped == "<table>":
            close_ul()
            in_table = True
            table_rows = []
            i += 1
            continue
        if stripped == "</table>":
            _flush_table(table_rows, html_lines, compact, table_index=table_counter if compact else None)
            if compact:
                table_counter += 1
            in_table = False
            table_rows = []
            i += 1
            continue
        if stripped == "---TABLE---":
            _flush_table(table_rows, html_lines, compact, table_index=table_counter if compact else None)
            if compact:
                table_counter += 1
            in_table = False
            table_rows = []
            i += 1
            continue
        if in_table:
            if stripped:
                table_rows.append(stripped)
            i += 1
            continue

        # Pipe table (consecutive lines with |)
        if "|" in stripped and not stripped.startswith("#"):
            close_ul()
            table_rows = [stripped]
            i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                if not nxt or nxt == "---TABLE---" or nxt in ("---", "—"):
                    break
                if "|" in nxt:
                    table_rows.append(nxt)
                    i += 1
                else:
                    break
            _flush_table(table_rows, html_lines, compact, table_index=table_counter if compact else None)
            if compact:
                table_counter += 1
            table_rows = []
            continue

        # Sub-bullet
        if stripped.startswith("o ") or stripped.startswith("o\t"):
            content = stripped[1:].strip()
            if not in_ul:
                html_lines.append(f'<ul style="{_STYLE_UL}">')
                in_ul = True
            html_lines.append(f'<li style="{_STYLE_LI_SUB}">{_inline_bold_md(content)}</li>')
            i += 1
            continue
        # Bullets (• and common unicode bullets; tab/space after marker OK)
        bullet_rest = _bullet_text_after_marker(stripped)
        if bullet_rest is not None:
            if not in_ul:
                html_lines.append(f'<ul style="{_STYLE_UL}">')
                in_ul = True
            html_lines.append(f'<li style="{_STYLE_LI}">{_inline_bold_md(bullet_rest)}</li>')
            i += 1
            continue
        # Markdown-style hyphen bullets (- item) — not horizontal rule ---
        if stripped.startswith("- ") and len(stripped) > 2:
            content = stripped[2:].strip()
            if not in_ul:
                html_lines.append(f'<ul style="{_STYLE_UL}">')
                in_ul = True
            html_lines.append(f'<li style="{_STYLE_LI}">{_inline_bold_md(content)}</li>')
            i += 1
            continue
        else:
            close_ul()

        if not stripped:
            close_coa_conclusion()
            if not tight_spacing:
                html_lines.append("<p><br/></p>")
            i += 1
            continue

        # Headings and paragraphs
        if stripped.startswith("## "):
            title_text = stripped[3:].strip()
            html_lines.append(f'<h2 class="section-heading" style="{_STYLE_H2_SECTION}">{escape(title_text)}</h2>')
            has_content = True
        elif stripped.startswith("# "):
            title_text = stripped[2:].strip()
            html_lines.append(f'<h1 style="{_STYLE_H1}">{escape(title_text)}</h1>')
            has_content = True
        elif stripped.upper() == "QUOTATION":
            html_lines.append(f'<h1 style="{_STYLE_H1}">{escape(stripped)}</h1>')
            has_content = True
        elif stripped.rstrip(":") in ("Supplier", "Bill To", "Ship To", "Delivery", "Declaration") or stripped.startswith("BANK DETAIL"):
            html_lines.append(f'<h2 style="{_STYLE_H2}">{escape(stripped)}</h2>')
            has_content = True
        elif stripped.lower().rstrip(":") == "conclusion":
            close_section_block()
            if not in_coa_conclusion:
                html_lines.append('<div class="coa-conclusion">')
                in_coa_conclusion = True
            html_lines.append(f'<p style="{_STYLE_P_BOLD_COA_CONCLUSION}">{escape(stripped)}</p>')
            has_content = True
        elif stripped.endswith(":") and len(stripped) < 80:
            bold_style = _STYLE_P_BOLD_COA_CONCLUSION if in_coa_conclusion else _STYLE_P_BOLD
            html_lines.append(f'<p style="{bold_style}">{_inline_bold_md(stripped)}</p>')
            has_content = True
        elif (
            "Certificate of Analysis" in stripped
            or "Technical Data Sheet" in stripped
            or "Material Safety Data Sheet" in stripped
            or stripped.startswith("Section ")
        ):
            if stripped.startswith("Section "):
                close_section_block()
                html_lines.append('<div class="section-block">')
                in_section_block = True
            html_lines.append(f'<h2 style="{_STYLE_H2}">{escape(stripped)}</h2>')
            has_content = True
        elif re.match(r"^\d+\.\s", stripped):
            close_section_block()
            html_lines.append('<div class="section-block">')
            in_section_block = True
            html_lines.append(f'<h3 style="{_STYLE_H3}">{escape(stripped)}</h3>')
            has_content = True
        else:
            p_style = _STYLE_P_COA_CONCLUSION if in_coa_conclusion else _STYLE_P
            html_lines.append(f'<p style="{p_style}">{_inline_bold_md(stripped)}</p>')
            has_content = True
        i += 1

    close_coa_conclusion()
    close_ul()
    close_section_block()
    return "\n".join(html_lines)


def split_four_sections(full_text: str) -> tuple[str, str, str, str]:
    """Split AI output into 4 sections in order: Quotation, TDS, COA, MSDS.
    Quotation: marker dropped so QUOTATION is the title. TDS/COA/MSDS: keep marker so section heading renders as big H1.
    For multiple products, all TDS sections are combined, all COA sections combined, all MSDS sections combined."""
    import re
    
    def drop_marker(s: str) -> str:
        s = s.strip()
        if s.startswith("#"):
            s = s.split("\n", 1)[-1].strip() if "\n" in s else ""
        return s
    
    # Find quotation section
    q_match = re.search(r"#\s*QUOTATION\b", full_text, re.IGNORECASE)
    q_start = q_match.start() if q_match else 0
    
    # TDS sections: chemical marker OR engineering "TECHNICAL DESCRIPTION"
    tds_pattern = (
        r"#\s*(?:TECHNICAL DATA SHEET\s*\(TDS\)|TECHNICAL DESCRIPTION)(?:\s*-\s*[^\n]*)?"
    )
    tds_matches = list(re.finditer(tds_pattern, full_text, re.IGNORECASE))
    
    # Find all COA sections
    coa_pattern = r"#\s*CERTIFICATE OF ANALYSIS\s*\(COA\)(?:\s*-\s*[^\n]*)?"
    coa_matches = list(re.finditer(coa_pattern, full_text, re.IGNORECASE))
    
    # Find all MSDS sections
    msds_pattern = r"#\s*MATERIAL SAFETY DATA SHEET\s*\(MSDS\)(?:\s*-\s*[^\n]*)?"
    msds_matches = list(re.finditer(msds_pattern, full_text, re.IGNORECASE))
    
    # Get first TDS position for quotation end
    first_tds = tds_matches[0].start() if tds_matches else len(full_text)
    
    # Extract quotation (from QUOTATION marker to first TDS)
    quotation = drop_marker(full_text[q_start:first_tds])
    
    # Collect all document sections
    all_sections = []
    for m in tds_matches:
        all_sections.append(("tds", m.start(), m.group()))
    for m in coa_matches:
        all_sections.append(("coa", m.start(), m.group()))
    for m in msds_matches:
        all_sections.append(("msds", m.start(), m.group()))
    
    # Sort by position
    all_sections.sort(key=lambda x: x[1])
    
    # Extract content for each section
    tds_parts = []
    coa_parts = []
    msds_parts = []
    
    for idx, (sec_type, start, marker) in enumerate(all_sections):
        # Find end (next section start or end of text)
        end = all_sections[idx + 1][1] if idx + 1 < len(all_sections) else len(full_text)
        content = full_text[start:end].strip()
        
        if sec_type == "tds":
            tds_parts.append(content)
        elif sec_type == "coa":
            coa_parts.append(content)
        elif sec_type == "msds":
            msds_parts.append(content)
    
    # Join multiple sections with page breaks
    tds = "\n\n".join(tds_parts)
    coa = "\n\n".join(coa_parts)
    msds = "\n\n".join(msds_parts)
    
    return quotation, tds, coa, msds
