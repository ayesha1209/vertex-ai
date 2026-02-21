"""
Parse AI response into sections and convert to clean HTML for PDF/DOCX.
We control formatting: inline styles only (PDF-engine safe), semantic tags, table headers.
"""

import re
from html import escape

# Section markers in output order: Quotation → TDS → COA → MSDS
MARKER_QUOTATION = "# QUOTATION"
MARKER_TDS = "# TECHNICAL DATA SHEET (TDS)"
MARKER_COA = "# CERTIFICATE OF ANALYSIS (COA)"
MARKER_MSDS = "# MATERIAL SAFETY DATA SHEET (MSDS)"

# Consistent 10pt, border #444, professional look; table-layout:fixed + max-width so cells wrap in PDF
_B = "1px solid #444"
_STYLE_TABLE = f"border-collapse: collapse; table-layout: fixed; width: 100%; max-width: 100%; margin: 4px 0; font-size: 10pt; border: {_B}; line-height: 1.3;"
_STYLE_TH = f"border: {_B}; padding: 4px 6px; text-align: left; font-weight: bold; background: #f2f2f2; vertical-align: top; font-size: 10pt; line-height: 1.3; word-wrap: break-word; overflow-wrap: break-word; max-width: 100%;"
_STYLE_TD = f"border: {_B}; padding: 4px 6px; text-align: left; vertical-align: top; font-size: 10pt; line-height: 1.3; word-wrap: break-word; overflow-wrap: break-word; max-width: 100%;"
_STYLE_TD_LABEL = f"border: {_B}; padding: 4px 6px; text-align: left; vertical-align: top; font-size: 10pt; line-height: 1.3; font-weight: bold; word-wrap: break-word; overflow-wrap: break-word; max-width: 100%;"
# Quotation: same 10pt, clean table format, slightly tighter padding
_STYLE_TABLE_COMPACT = f"border-collapse: collapse; table-layout: fixed; width: 100%; max-width: 100%; margin: 4px 0; font-size: 10pt; border: {_B}; line-height: 1.3;"
_STYLE_TH_COMPACT = f"border: {_B}; padding: 3px 6px; text-align: left; font-weight: bold; background: #f2f2f2; vertical-align: top; font-size: 10pt; line-height: 1.3; word-wrap: break-word; overflow-wrap: break-word; max-width: 100%;"
_STYLE_TD_COMPACT = f"border: {_B}; padding: 3px 6px; text-align: left; vertical-align: top; font-size: 10pt; line-height: 1.3; word-wrap: break-word; overflow-wrap: break-word; max-width: 100%;"
_STYLE_TD_LABEL_COMPACT = f"border: {_B}; padding: 3px 6px; text-align: left; vertical-align: top; font-size: 10pt; line-height: 1.3; font-weight: bold; word-wrap: break-word; overflow-wrap: break-word; max-width: 100%;"
_STYLE_HR = "border: none; border-top: 1px solid #444; margin: 6px 0 8px 0;"
_STYLE_H1 = "font-size: 14pt; font-weight: bold; margin: 6px 0 4px 0; text-align: center; line-height: 1.2; page-break-after: avoid; text-transform: uppercase; letter-spacing: 0.04em;"
_STYLE_H1_QUOTATION = "font-size: 14pt; font-weight: bold; margin: 0 0 8px 0; text-align: center; line-height: 1.2; page-break-after: avoid; text-transform: uppercase; letter-spacing: 0.04em;"
_STYLE_H1_SECTION = "font-size: 14pt; font-weight: bold; margin: 8px 0 4px 0; text-align: center; line-height: 1.2; page-break-after: avoid; text-transform: uppercase; letter-spacing: 0.04em;"
_STYLE_H2 = "font-size: 11pt; font-weight: bold; margin: 6px 0 4px 0; line-height: 1.25; page-break-after: avoid; text-transform: uppercase; letter-spacing: 0.03em;"
_STYLE_H3 = "font-size: 10.5pt; font-weight: bold; margin: 5px 0 3px 0; line-height: 1.25; page-break-after: avoid; letter-spacing: 0.02em;"
_STYLE_P = "margin: 3px 0 5px 0; line-height: 1.35; font-size: 10pt;"
_STYLE_P_BOLD = "margin: 3px 0 5px 0; font-weight: bold; line-height: 1.35; font-size: 10pt;"
# COA conclusion block: minimal margin so it stays with table on same page
_STYLE_P_COA_CONCLUSION = "margin: 0 0 2px 0; line-height: 1.3; font-size: 10pt;"
_STYLE_P_BOLD_COA_CONCLUSION = "margin: 0 0 2px 0; font-weight: bold; line-height: 1.3; font-size: 10pt;"
_STYLE_UL = "margin: 3px 0 4px 0; padding-left: 1.35em;"
_STYLE_UL_SUB = "margin: 1px 0 2px 0; padding-left: 1.5em; list-style-type: circle;"
_STYLE_LI = "margin: 1px 0; line-height: 1.35;"
_STYLE_LI_SUB = "margin: 1px 0; line-height: 1.35;"

PAGE_BREAK = '<div style="page-break-after: always;"></div>'

SECTION_HR = '<hr style="border: none; border-top: 1px solid #444; margin: 6px 0 8px 0;"/>'


def _normalize_spacing(text: str) -> str:
    """Correct spacing issues for print: collapse multiple spaces, no leading/trailing per line."""
    lines = text.splitlines()
    out = []
    for line in lines:
        out.append(re.sub(r" +", " ", line).strip())
    return "\n".join(out)


def _merge_label_value_lines(text: str) -> str:
    """
    When AI outputs label on one line and value on the next (causing broken tables),
    merge into pipe-separated rows: "Label|Value".
    """
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # Candidate label: ends with : and short; not a heading
        is_label = (
            stripped.endswith(":")
            and len(stripped) <= 55
            and not stripped.startswith("#")
            and "|" not in stripped
        )
        if is_label and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            # Value line: non-empty, no pipe, not a section marker or heading
            if (
                next_line
                and "|" not in next_line
                and not next_line.startswith("#")
                and next_line not in ("---", "—", "---TABLE---")
                and not next_line.startswith("•")
            ):
                label = stripped.rstrip(":").strip()
                out.append(f"{label}|{next_line}")
                i += 2
                continue
        out.append(line)
        i += 1
    return "\n".join(out)


# Quotation block class names (order must match AI reference: meta, parties, terms, items, totals, bank, signature)
_QUOTATION_TABLE_CLASSES = [
    "invoice-meta",
    "invoice-parties",
    "invoice-terms",
    "invoice-items",
    "invoice-totals",
    "invoice-bank",
    "invoice-signature",
]


def _flush_table(
    table_rows: list[str],
    html_lines: list[str],
    compact: bool = False,
    table_index: int | None = None,
) -> None:
    if not table_rows:
        return
    col_counts = [len([c for c in row.split("|") if c.strip()]) for row in table_rows]
    two_col_kv = len(col_counts) > 0 and all(n == 2 for n in col_counts)
    st_table = _STYLE_TABLE_COMPACT if compact else _STYLE_TABLE
    st_th = _STYLE_TH_COMPACT if compact else _STYLE_TH
    st_td = _STYLE_TD_COMPACT if compact else _STYLE_TD
    st_td_label = _STYLE_TD_LABEL_COMPACT if compact else _STYLE_TD_LABEL
    # Block class for quotation (one-page invoice)
    block_class = ""
    if compact and table_index is not None and 0 <= table_index < len(_QUOTATION_TABLE_CLASSES):
        block_class = f' class="{_QUOTATION_TABLE_CLASSES[table_index]}"'
    # Two-column label|value tables: constrain columns so value cell wraps (no overflow)
    if compact and two_col_kv:
        block_class = (block_class.rstrip('"') + ' label-value"') if block_class else ' class="label-value"'
    is_items_table = compact and table_index == 3
    ncols = len([c for c in table_rows[0].split("|") if c.strip()]) if table_rows else 0
    # Right-align last 3 columns (Unit Price, Unit, Amount) in line-items table
    numeric_start_col = max(0, ncols - 3) if is_items_table and ncols >= 3 else -1
    # Signature block: detect by content so we never render it as a table (avoids PDF overflow)
    def _is_signature_block() -> bool:
        if not compact or not table_rows:
            return False
        first_cell = (table_rows[0].split("|")[0].strip() if "|" in table_rows[0] else "").lower()
        if first_cell == "name of signatory":
            return True
        for row in table_rows:
            if "|" in row:
                left = row.split("|")[0].strip().lower()
                if left == "declaration":
                    return True
        return False

    if _is_signature_block():
        # Stacked block with inline styles so PDF engine keeps content on page
        block_style = "margin-top:8px;padding:8px 10px;border:1px solid #d0d0d0;border-radius:2px;max-width:100%;"
        row_style = "margin-bottom:6px;"
        label_style = "font-weight:bold;font-size:11px;margin:0 0 1px 0;display:block;"
        value_style = "font-size:11px;line-height:1.35;margin:0 0 4px 0;display:block;width:100%;max-width:100%;word-wrap:break-word;overflow-wrap:break-word;"
        html_lines.append(f'<div class="invoice-signature-block" style="{block_style}">')
        for row in table_rows:
            parts = [c.strip() for c in row.split("|")]
            if not parts:
                continue
            label_text = escape(parts[0])
            value_text = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
            value_text = escape(value_text)
            html_lines.append(f'<div class="invoice-sig-row" style="{row_style}">')
            html_lines.append(f'<div class="invoice-sig-label" style="{label_style}">{label_text}</div>')
            if label_text.lower() == "declaration":
                html_lines.append(f'<p class="invoice-sig-value invoice-sig-declaration" style="{value_style}">{value_text}</p>')
            else:
                html_lines.append(f'<div class="invoice-sig-value" style="{value_style}">{value_text}</div>')
            html_lines.append("</div>")
        html_lines.append("</div>")
        return
    html_lines.append(f'<table style="{st_table}"{block_class}>')
    # Fixed column widths for 2-col label-value so value column wraps inside page
    if compact and two_col_kv and ncols == 2:
        html_lines.append('<colgroup><col style="width:28%"/><col style="width:72%"/></colgroup>')
    for row_idx, row in enumerate(table_rows):
        cells = [c.strip() for c in row.split("|")]
        cells = [escape(c) for c in cells if c is not None]
        if not cells:
            continue
        tag = "th" if row_idx == 0 else "td"
        parts = []
        for col_idx, c in enumerate(cells):
            if row_idx == 0:
                style = st_th
            elif two_col_kv and col_idx == 0:
                style = st_td_label
            else:
                style = st_td
            num_class = ' class="numeric"' if numeric_start_col >= 0 and col_idx >= numeric_start_col else ""
            parts.append(f'<{tag} style="{style}"{num_class}>{c}</{tag}>')
        html_lines.append("<tr>" + "".join(parts) + "</tr>")
    html_lines.append("</table>")


def text_to_html(text: str, compact: bool = False) -> str:
    """
    Convert AI text to clean HTML. Inline styles only for best PDF/DOCX output.
    Preserves: tables (| and ---TABLE---), horizontal rules (---), bullets, headings.
    If compact=True (for quotation), uses smaller fonts and tight padding for one-page layout.
    """
    text = _normalize_spacing(text)
    text = _merge_label_value_lines(text)
    lines = text.splitlines()
    html_lines: list[str] = []
    in_table = False
    table_rows: list[str] = []
    in_ul = False
    in_section_block = False  # TDS/MSDS numbered section: keep heading with content (avoid page break between)
    in_coa_conclusion = False  # COA: Conclusion / For: / Quality Control / Authorized Signatory — keep on one page
    table_counter = 0  # for quotation block classes (invoice-meta, invoice-parties, ...)

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
    while i < len(lines):
        line = lines[i].rstrip("\n")
        stripped = line.strip()

        # Horizontal rule
        if stripped in ("---", "—", "___", "__________"):
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

        # Sub-bullet (o followed by space/tab) — indent under previous bullet
        if stripped.startswith("o ") or stripped.startswith("o\t"):
            content = stripped[1:].strip()
            if not in_ul:
                html_lines.append(f'<ul style="{_STYLE_UL}">')
                in_ul = True
            html_lines.append(f'<li style="{_STYLE_LI_SUB}; margin-left: 1em;">{escape(content)}</li>')
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
            blank_style = "margin: 0; line-height: 0.2;" if compact else "margin: 1px 0; line-height: 0.35;"
            html_lines.append(f"<p style=\"{blank_style}\"><br/></p>")
            i += 1
            continue

        # Skip section markers (=== SECTION X: ... ===) - these are structural guides for AI
        if stripped.startswith("=== SECTION") and stripped.endswith("==="):
            i += 1
            continue

        # Headings and paragraphs (quotation/doc hierarchy)
        if stripped.startswith("# "):
            title_text = stripped[2:].strip()
            # Big clear heading for the 3 doc sections (TDS, COA, MSDS)
            if "TECHNICAL DATA SHEET" in title_text or "CERTIFICATE OF ANALYSIS" in title_text or "MATERIAL SAFETY DATA SHEET" in title_text:
                html_lines.append(f'<h1 style="{_STYLE_H1_SECTION}">{escape(title_text)}</h1>')
            else:
                html_lines.append(f'<h1 style="{_STYLE_H1}">{escape(title_text)}</h1>')
        elif stripped.upper() == "QUOTATION":
            html_lines.append(f'<h1 class="quotation-title" style="{_STYLE_H1_QUOTATION}">{escape(stripped)}</h1>')
        elif stripped.rstrip(":") in ("Supplier", "Bill To", "Ship To", "Delivery", "Declaration") or stripped.startswith("BANK DETAIL"):
            html_lines.append(f'<h2 style="{_STYLE_H2}">{escape(stripped)}</h2>')
        elif stripped.lower().rstrip(":") == "conclusion":
            close_section_block()
            if not in_coa_conclusion:
                html_lines.append('<div class="coa-conclusion">')
                in_coa_conclusion = True
            html_lines.append(f'<p style="{_STYLE_P_BOLD_COA_CONCLUSION}">{escape(stripped)}</p>')
        elif stripped.endswith(":") and len(stripped) < 80:
            bold_style = _STYLE_P_BOLD_COA_CONCLUSION if in_coa_conclusion else _STYLE_P_BOLD
            html_lines.append(f'<p style="{bold_style}">{escape(stripped)}</p>')
        elif (
            "Certificate of Analysis" in stripped
            or "Technical Data Sheet" in stripped
            or "Material Safety Data Sheet" in stripped
            or stripped.startswith("Section ")
        ):
            if stripped.startswith("Section "):
                close_section_block()
                html_lines.append('<div class="section-block" style="page-break-inside: avoid; break-inside: avoid;">')
                in_section_block = True
            html_lines.append(f'<h2 style="{_STYLE_H2}">{escape(stripped)}</h2>')
        elif re.match(r"^\d+\.\s", stripped):
            close_section_block()
            html_lines.append('<div class="section-block" style="page-break-inside: avoid; break-inside: avoid;">')
            in_section_block = True
            html_lines.append(f'<h3 style="{_STYLE_H3}">{escape(stripped)}</h3>')
        else:
            p_style = _STYLE_P_COA_CONCLUSION if in_coa_conclusion else _STYLE_P
            html_lines.append(f'<p style="{p_style}">{escape(stripped)}</p>')
        i += 1

    close_coa_conclusion()
    close_ul()
    close_section_block()
    return "\n".join(html_lines)


def split_four_sections(full_text: str) -> tuple[str, str, str, str]:
    """Split AI output into 4 sections in order: Quotation, TDS, COA, MSDS.
    Quotation: marker dropped so QUOTATION is the title. TDS/COA/MSDS: keep marker so section heading renders as big H1."""
    def find(m: str) -> int:
        i = full_text.find(m)
        return i if i >= 0 else len(full_text)

    i_q = find(MARKER_QUOTATION)
    i_tds = find(MARKER_TDS)
    i_coa = find(MARKER_COA)
    i_msds = find(MARKER_MSDS)

    def drop_marker(s: str) -> str:
        s = s.strip()
        if s.startswith("#"):
            s = s.split("\n", 1)[-1].strip() if "\n" in s else ""
        return s

    quotation = drop_marker(full_text[i_q:i_tds])
    # Keep # marker for TDS, COA, MSDS so each section has a clear big heading
    tds = full_text[i_tds:i_coa].strip()
    coa = full_text[i_coa:i_msds].strip()
    msds = full_text[i_msds:].strip()
    return quotation, tds, coa, msds
