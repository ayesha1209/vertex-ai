"""Transform a Quotation's HTML into a Proforma Invoice or Invoice.

All changes are done via regex on the HTML so no AI call is needed.
For local-export invoices the GST rows (CGST @9% + SGST @9%) are injected
into the totals table automatically.
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_numeric_amount(cell_html: str) -> Optional[float]:
    """Strip HTML tags, currency symbols and commas, then parse as float."""
    text = re.sub(r"<[^>]+>", "", cell_html).strip()
    text = re.sub(r"[₹$€£]", "", text)
    text = re.sub(r"\bRs\.?\s*", "", text, flags=re.IGNORECASE)
    text = text.replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _fmt(n: float) -> str:
    return f"{n:,.2f}"


_BORDER = "1px solid #333"
_TD_LABEL = f"border:{_BORDER};text-align:left;vertical-align:top;background-color:#ffffff;"
_TD_VALUE = f"border:{_BORDER};text-align:right;vertical-align:top;background-color:#ffffff;"


def _inject_gst_rows(html: str) -> str:
    """Add CGST @9% + SGST @9% + Grand Total rows to the totals-table."""
    m = re.search(
        r"(<table[^>]*class=\"[^\"]*totals-table[^\"]*\"[^>]*>)(.*?)(</table>)",
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return html

    before, body, after_tag = m.group(1), m.group(2), m.group(3)

    # Locate Total Amount row and extract value from its last <td>
    total_row_m = re.search(
        r"<tr[^>]*>((?:(?!</tr>).)*?Total\s+Amount(?:(?!</tr>).)*?)</tr>",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if not total_row_m:
        return html

    tds = list(
        re.finditer(r"<td[^>]*>(.*?)</td>", total_row_m.group(1), re.DOTALL | re.IGNORECASE)
    )
    if not tds:
        return html

    amount = _extract_numeric_amount(tds[-1].group(1))
    if amount is None:
        return html

    cgst = round(amount * 0.09, 2)
    sgst = round(amount * 0.09, 2)
    grand = round(amount + cgst + sgst, 2)

    new_rows = (
        f'<tr>'
        f'<td style="{_TD_LABEL}">CGST @9%</td>'
        f'<td style="{_TD_VALUE}">{_fmt(cgst)}</td>'
        f'</tr>\n'
        f'<tr>'
        f'<td style="{_TD_LABEL}">SGST @9%</td>'
        f'<td style="{_TD_VALUE}">{_fmt(sgst)}</td>'
        f'</tr>\n'
        f'<tr>'
        f'<td style="{_TD_LABEL}font-weight:bold;"><strong><b>Grand Total (incl. GST)</b></strong></td>'
        f'<td style="{_TD_VALUE}font-weight:bold;"><strong><b>{_fmt(grand)}</b></strong></td>'
        f'</tr>'
    )

    # Insert before "Amount in Words" row (or at end of body if not found)
    words_m = re.search(
        r"(<tr[^>]*>(?:(?!</tr>).)*?Amount\s+in\s+Words(?:(?!</tr>).)*?</tr>)",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if words_m:
        body = body[: words_m.start()] + new_rows + "\n" + body[words_m.start() :]
    else:
        body = body + "\n" + new_rows

    return html[: m.start()] + before + body + after_tag + html[m.end() :]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transform_quotation_to_invoice(
    html: str,
    doc_type: str,
    local_export: Optional[str] = None,
) -> str:
    """Return a new HTML document derived from a quotation.

    doc_type    : "proforma_invoice" | "invoice"
    local_export: "local" | "export" | None
                  When "local" and doc_type is "invoice", CGST/SGST rows are
                  inserted into the totals table.
    """
    if doc_type == "proforma_invoice":
        heading = "PROFORMA INVOICE"
        no_label = "Proforma Invoice No"
        date_label = "Proforma Invoice Date"
    else:
        heading = "INVOICE"
        no_label = "Invoice No"
        date_label = "Invoice Date"

    # 1. Replace heading inside <h1>
    html = re.sub(
        r"(<h1[^>]*>)\s*QUOTATION\s*(</h1>)",
        rf"\g<1>{heading}\g<2>",
        html,
        flags=re.IGNORECASE,
    )

    # 2. Replace "Quotation No" label in any <td> cell
    html = re.sub(
        r"(<td[^>]*>)(\s*)Quotation\s+No(\s*)(</td>)",
        rf"\g<1>\g<2>{no_label}\g<3>\g<4>",
        html,
        flags=re.IGNORECASE,
    )

    # 3. Replace "Quotation Date" label in any <td> cell
    html = re.sub(
        r"(<td[^>]*>)(\s*)Quotation\s+Date(\s*)(</td>)",
        rf"\g<1>\g<2>{date_label}\g<3>\g<4>",
        html,
        flags=re.IGNORECASE,
    )

    # 4. Inject GST for local invoices
    if doc_type == "invoice" and (local_export or "").strip().lower() == "local":
        html = _inject_gst_rows(html)

    return html
