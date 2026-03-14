"""
Parse AI response into sections and convert to clean HTML for PDF/DOCX.
We control formatting: inline styles only (PDF-engine safe), semantic tags, table headers.
"""

import logging
import re
from html import escape

logger = logging.getLogger(__name__)

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
_STYLE_UL = ""
_STYLE_LI = ""
_STYLE_LI_SUB = ""

PAGE_BREAK = '<div style="page-break-after:always;"></div>'


def _normalize_spacing(text: str) -> str:
    """Correct spacing issues for print: collapse multiple spaces, no leading/trailing per line."""
    lines = text.splitlines()
    out = []
    for line in lines:
        out.append(re.sub(r" +", " ", line).strip())
    return "\n".join(out)


# Quotation table types
_Q_TABLE_CUSTOMER = 0
_Q_TABLE_DELIVERY = 1
_Q_TABLE_ITEMS = 2
_Q_TABLE_TOTALS = 3


def _detect_table_type(table_rows: list[str]) -> int:
    """Detect quotation table type based on content."""
    if not table_rows:
        return -1
    
    first_row = table_rows[0].lower()
    
    # Items table: starts with "No." header
    if first_row.startswith("no.") or first_row.startswith("no|"):
        return _Q_TABLE_ITEMS
    
    # Totals table: contains "Total Amount"
    if "total amount" in first_row.lower():
        return _Q_TABLE_TOTALS
    
    # Customer table: contains "Bill To"
    if "bill to" in first_row.lower():
        return _Q_TABLE_CUSTOMER
    
    # Delivery table: contains "Delivery" as first cell
    if first_row.startswith("delivery"):
        return _Q_TABLE_DELIVERY
    
    return -1


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
    else:
        label_cols = set()

    # Add class for each table type to apply CSS styles
    if table_type == _Q_TABLE_CUSTOMER:
        table_class = ' class="customer-table"'
    elif table_type == _Q_TABLE_DELIVERY:
        table_class = ' class="delivery-table"'
    elif table_type == _Q_TABLE_ITEMS:
        table_class = ' class="items-table"'
    elif table_type == _Q_TABLE_TOTALS:
        table_class = ' class="totals-table"'
    else:
        table_class = ''
    html_lines.append(f'<table{table_class} style="{_Q_TABLE}">')
    
    # Add colgroup for items table to control column widths
    if table_type == _Q_TABLE_ITEMS:
        html_lines.append('<colgroup><col style="width:6%"/><col style="width:40%"/><col style="width:14%"/><col style="width:20%"/><col style="width:20%"/></colgroup>')

    for row_idx, row in enumerate(table_rows):
        # Split by pipe and keep all cells (including empty ones)
        raw_cells = row.split("|")
        cells = [c.strip() for c in raw_cells]
        
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

        # Items table: first row is header
        is_header = table_type == _Q_TABLE_ITEMS and row_idx == 0
        
        html_lines.append("<tr>")
        for col_idx, c in enumerate(cells):
            # Handle description - force line breaks before Make: and HSN:
            # Apply to column 1 (Description) of items table
            if table_type == _Q_TABLE_ITEMS and col_idx == 1 and row_idx > 0:
                import re
                # Clean up: remove // separators and extra spaces
                text = re.sub(r'\s*//\s*', ' ', c)
                text = re.sub(r'\s+', ' ', text).strip()
                
                # Split into parts: Product Name, Make:..., HSN:...
                make_match = re.search(r'Make\s*:', text, re.IGNORECASE)
                hsn_match = re.search(r'HSN\s*:', text, re.IGNORECASE)
                
                parts = []
                if make_match:
                    product_name = text[:make_match.start()].strip()
                    if product_name:
                        parts.append(escape(product_name))
                    
                    if hsn_match and hsn_match.start() > make_match.start():
                        make_part = text[make_match.start():hsn_match.start()].strip()
                        hsn_part = text[hsn_match.start():].strip()
                        parts.append(escape(make_part))
                        parts.append(escape(hsn_part))
                    else:
                        make_part = text[make_match.start():].strip()
                        parts.append(escape(make_part))
                else:
                    parts.append(escape(text))
                
                cell_content = "<br/>".join(parts) if parts else "&nbsp;"
            else:
                cell_content = escape(c) if c else "&nbsp;"
            
            # All cells use <td> to prevent TipTap from converting to <th>
            # Use inline styles for header appearance
            if is_header:
                # Items table header: gray background, bold, with column widths
                col_widths = ["6%", "40%", "14%", "20%", "20%"]
                width_style = f"width:{col_widths[col_idx]};" if col_idx < len(col_widths) else ""
                nowrap = "white-space:nowrap;" if col_idx == 0 else ""
                style = f"border:{_B};{width_style}{nowrap}text-align:left;font-weight:bold;vertical-align:top;background-color:#BBBBBB;"
                if col_idx >= 2:  # Right-align numeric headers
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
                # Right-align numeric columns in items table
                if table_type == _Q_TABLE_ITEMS and col_idx >= 2:
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

    # Non-quotation tables (TDS/COA/MSDS)
    col_counts = [len([c for c in row.split("|") if c.strip()]) for row in table_rows]
    two_col_kv = len(col_counts) > 0 and all(n == 2 for n in col_counts)
    
    html_lines.append(f'<table style="{_STYLE_TABLE}">')
    for row_idx, row in enumerate(table_rows):
        cells = [c.strip() for c in row.split("|")]
        cells = [c for c in cells if c is not None]
        if not cells:
            continue
        is_header_row = row_idx == 0
        tag = "th" if is_header_row else "td"
        parts = []
        for col_idx, c in enumerate(cells):
            c = escape(c)
            if is_header_row:
                style = _STYLE_TH
            elif two_col_kv and col_idx == 0:
                style = _STYLE_TD_LABEL
            else:
                style = _STYLE_TD
            parts.append(f'<{tag} style="{style}">{c}</{tag}>')
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

    html_lines.append('<div class="terms-sig-wrapper" style="page-break-before:avoid !important; page-break-inside:avoid !important; margin-top:0; padding-top:0;">')
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
        html_lines.append('<td style="width:40%; border:none !important; padding:0; text-align:right; vertical-align:top;"><div class="signatory-block" style="text-align:right; margin-top:0; page-break-before:avoid !important;">')
        for ln in signature_lines:
            parts = [p.strip() for p in ln.split("|") if p.strip()]
            for part in parts:
                html_lines.append(f"<p style=\"text-align:right; margin:2px 0; display:block;\"><strong>{escape(part)}</strong></p>")
            if not parts:
                html_lines.append(f"<p style=\"text-align:right; margin:2px 0; display:block;\"><strong>{escape(ln)}</strong></p>")
        html_lines.append("</div></td></tr></table>")
    elif terms_lower:
        html_lines.append('<div class="terms-section" style="width:100%;">')
        for ln in terms_lower:
            html_lines.append(f"<p style=\"margin:2px 0; display:block;\">{escape(ln)}</p>")
        html_lines.append("</div>")
    elif signature_lines:
        html_lines.append('<div class="signatory-block" style="text-align:right; margin-top:4px; page-break-before:avoid !important;">')
        for ln in signature_lines:
            parts = [p.strip() for p in ln.split("|") if p.strip()]
            for part in parts:
                html_lines.append(f"<p style=\"text-align:right; margin:2px 0; display:block;\"><strong>{escape(part)}</strong></p>")
            if not parts:
                html_lines.append(f"<p style=\"text-align:right; margin:2px 0; display:block;\"><strong>{escape(ln)}</strong></p>")
        html_lines.append("</div>")
    html_lines.append("</div>")
    return i


def text_to_html(text: str, compact: bool = False, multi_product: bool = False) -> str:
    """
    Convert AI text to clean HTML. Inline styles only for best PDF/DOCX output.
    Preserves: tables (| and ---TABLE---), horizontal rules (---), bullets, headings.
    If compact=True (for quotation), uses smaller fonts and tight padding for one-page layout.
    If multi_product=True (quotation with multiple products), terms are full width and signatory after 15.
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
                        "TECHNICAL DATA" in u or "TECHNICAL DATA SHEET" in u
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
                
                logger.info(f">>> Quotation terms: {len(terms_lines)} lines, signature: {len(signature_lines)} lines")
                
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
                html_lines.append('<div class="terms-sig-wrapper" style="page-break-before:avoid !important; page-break-inside:avoid !important; margin-top:0; padding-top:0;">')
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
                    html_lines.append('<td style="width:40%; border:none !important; padding:0; text-align:right; vertical-align:top;"><div class="signatory-block" style="text-align:right; margin-top:0; page-break-before:avoid !important;">')
                    for ln in signature_lines:
                        parts = [p.strip() for p in ln.split("|") if p.strip()]
                        for part in parts:
                            html_lines.append(f"<p style=\"text-align:right; margin:2px 0; display:block;\"><strong>{escape(part)}</strong></p>")
                        if not parts:
                            html_lines.append(f"<p style=\"text-align:right; margin:2px 0; display:block;\"><strong>{escape(ln)}</strong></p>")
                    html_lines.append("</div></td></tr></table>")
                elif terms_lower:
                    html_lines.append('<div class="terms-section" style="width:100%;">')
                    for ln in terms_lower:
                        html_lines.append(f"<p style=\"margin:2px 0; display:block;\">{escape(ln)}</p>")
                    html_lines.append("</div>")
                elif signature_lines:
                    html_lines.append('<div class="signatory-block" style="text-align:right; margin-top:4px; page-break-before:avoid !important;">')
                    for ln in signature_lines:
                        parts = [p.strip() for p in ln.split("|") if p.strip()]
                        for part in parts:
                            html_lines.append(f"<p style=\"text-align:right; margin:2px 0; display:block;\"><strong>{escape(part)}</strong></p>")
                        if not parts:
                            html_lines.append(f"<p style=\"text-align:right; margin:2px 0; display:block;\"><strong>{escape(ln)}</strong></p>")
                    html_lines.append("</div>")
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
            html_lines.append(f'<li style="{_STYLE_LI_SUB}">{escape(content)}</li>')
            i += 1
            continue
        # Bullets
        if stripped.startswith("•"):
            content = stripped.lstrip("•").strip()
            if not in_ul:
                html_lines.append(f'<ul style="{_STYLE_UL}">')
                in_ul = True
            html_lines.append(f'<li style="{_STYLE_LI}">{escape(content)}</li>')
            i += 1
            continue
        else:
            close_ul()

        if not stripped:
            close_coa_conclusion()
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
            html_lines.append(f'<p style="{bold_style}">{escape(stripped)}</p>')
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
            html_lines.append(f'<p style="{p_style}">{escape(stripped)}</p>')
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
    
    # Find all TDS sections (may have product name suffix like "# TECHNICAL DATA SHEET (TDS) - ProductName")
    tds_pattern = r"#\s*TECHNICAL DATA SHEET\s*\(TDS\)(?:\s*-\s*[^\n]*)?"
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
