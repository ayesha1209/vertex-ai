"""Build Proforma Invoice, Invoice, Commercial Invoice, and Tax Invoice
documents from a Quotation's data.

All four share one box layout (Supplier / Ship To / Bill To / Bank Details /
Freight / logistics boxes, 5-column item table, IGST 18% for domestic sales)
— only the heading and a couple of labels differ per type. Values (buyer,
products, HSN, amounts, etc.) are extracted out of the quotation's own HTML
via regex rather than relabeling it in place, since this box layout is
structurally different from the Quotation.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Optional

from app.services.document_generation.response_parser import (
    CUSTOMER_TABLE_SIGNATURES,
    ITEMS_TABLE_SIGNATURES,
    TOTALS_TABLE_SIGNATURES,
)


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


# ---------------------------------------------------------------------------
# Shared Supplier / Bank blocks and extraction helpers
# ---------------------------------------------------------------------------

_SUPPLIER_BLOCK = (
    "Vertex Chemical Corporation<br/>"
    "206/5, Signet Hub, Opp. Zydus Hospital, Akshar Chowk,<br/>"
    "Vadodara-390020 Gujarat, India<br/>"
    "Ph. +91 8866335159<br/>"
    "IEC CODE: BKUPV2349L<br/>"
    "GSTIN/UIN: 24BKUPV2349L1ZB"
)

_BANK_BLOCK = (
    "Account Name: Vertex Chemical Corporation<br/>"
    "A/C No.: 50200115602188<br/>"
    "Bank Name &amp; Branch: HDFC Bank, Vasna Road Branch<br/>"
    "IFSC: HDFC0001712<br/>"
    "SWIFT: HDFCINBBXXX"
)


def _cell_text(cell_html: str) -> str:
    """Strip tags (keeping <br/> as a line break) and unescape entities from a table cell."""
    text = re.sub(r"<br\s*/?>", "\n", cell_html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def _iter_tables(html: str) -> list[str]:
    """Return the inner body of every <table> in the document, in order."""
    return [m.group(1) for m in re.finditer(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)]


def _table_first_row_text(table_body: str) -> str:
    m = re.search(r"<tr[^>]*>(.*?)</tr>", table_body, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    tds = re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.DOTALL | re.IGNORECASE)
    return " ".join(_cell_text(t) for t in tds)


def _extract_table_body(
    html: str, table_class: str, content_signatures: tuple[str, ...] = ()
) -> Optional[str]:
    """Find a table's inner body by CSS class first; if the class isn't present
    (the quotation may have been re-saved through the TipTap editor, whose
    ProseMirror serialization strips custom table classes entirely on save —
    confirmed by comparing a never-edited quotation's HTML against an edited
    one), fall back to matching the first row's text against known content
    signatures for that table type, mirroring how response_parser.py's own
    _detect_table_type sniffs tables by content rather than by class."""
    m = re.search(
        rf'<table[^>]*class="[^"]*{table_class}[^"]*"[^>]*>(.*?)</table>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1)
    if not content_signatures:
        return None
    for body in _iter_tables(html):
        first_row = _table_first_row_text(body).lower()
        if any(sig in first_row for sig in content_signatures):
            return body
    return None


def _extract_label_value_table(
    html: str, table_class: str, content_signatures: tuple[str, ...] = ()
) -> dict[str, str]:
    """Extract label->value pairs from a 2- or 4-column label|value quotation table."""
    body = _extract_table_body(html, table_class, content_signatures)
    values: dict[str, str] = {}
    if not body:
        return values
    for row_m in re.finditer(r"<tr[^>]*>(.*?)</tr>", body, re.DOTALL | re.IGNORECASE):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row_m.group(1), re.DOTALL | re.IGNORECASE)
        texts = [_cell_text(t) for t in tds]
        if len(texts) >= 2 and texts[0]:
            values[texts[0].strip().lower().rstrip(":")] = texts[1]
        if len(texts) >= 4 and texts[2]:
            values[texts[2].strip().lower().rstrip(":")] = texts[3]
    return values


def _extract_item_rows(html: str) -> list[dict[str, str]]:
    """Extract item rows (Product, HSN, Qty/Unit, Unit Price, Amount) from the quotation's items-table."""
    body = _extract_table_body(html, "items-table", ITEMS_TABLE_SIGNATURES)
    items: list[dict[str, str]] = []
    if not body:
        return items
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.DOTALL | re.IGNORECASE)
    for row in rows[1:]:  # skip header row
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(tds) < 5:
            continue
        desc_lines = [_cell_text(p) for p in re.split(r"<br\s*/?>", tds[1], flags=re.IGNORECASE)]
        product = desc_lines[0] if desc_lines else ""
        hsn = ""
        for line in desc_lines[1:]:
            m = re.match(r"HSN\s*:\s*(.+)", line, re.IGNORECASE)
            if m:
                hsn = m.group(1).strip()
        items.append(
            {
                "product": product,
                "hsn": hsn,
                "qty_unit": _cell_text(tds[2]),
                "unit_price": _cell_text(tds[3]),
                "amount": _cell_text(tds[4]),
            }
        )
    return items


def _split_qty_unit(qty_unit: str) -> tuple[str, str]:
    """Split a combined "500 Kg" / "4 Container" cell into (quantity, unit)."""
    m = re.match(r"^\s*([\d,.]+)\s*(.*)$", qty_unit.strip())
    if not m:
        return qty_unit.strip(), ""
    return m.group(1).strip(), m.group(2).strip()


def _ci_cell(label: str, value: str = "", *, colspan: int = 1) -> str:
    """Render one logistics/header-style <td>: bold label, optional value below."""
    colspan_attr = f' colspan="{colspan}"' if colspan != 1 else ""
    body = f"<strong>{label}</strong>" + (f"<br/>{value}" if value else "") if (label or value) else ""
    return f'<td style="{_TD_LABEL}"{colspan_attr}>{body}</td>'


def _logistics_row(cells: list[tuple[str, str, int]]) -> str:
    """Render one logistics-table row from (label, value, colspan) tuples.
    The table is a fixed 4-column grid — raises if a row's colspans don't sum
    to 4, so a miscounted row fails loudly instead of silently misaligning
    columns in the rendered PDF."""
    total_span = sum(c[2] for c in cells)
    if total_span != 4:
        raise ValueError(f"logistics row colspans sum to {total_span}, expected 4: {cells}")
    return "<tr>" + "".join(_ci_cell(label, value, colspan=span) for label, value, span in cells) + "</tr>"


_TITLES = {
    "proforma_invoice": "PROFORMA INVOICE",
    "invoice": "INVOICE",
    "commercial_invoice": "COMMERCIAL INVOICE",
    "tax_invoice": "TAX INVOICE",
}
_NO_LABELS = {
    "proforma_invoice": "Proforma Invoice No.:",
    "invoice": "Invoice No.:",
    "commercial_invoice": "Invoice No.:",
    "tax_invoice": "Invoice No.:",
}


def extract_quotation_data(quotation_html: str) -> dict:
    """Extract everything build_invoice_document needs out of a quotation's
    HTML, once. Building multiple invoice-family documents from the same
    quotation (Proforma Invoice + Invoice + Commercial/Tax Invoice, as
    generate_batch_invoices does per batch) should call this once and pass
    the result to build_invoice_document via extracted=..., rather than
    letting each call independently re-scan the same HTML for the same
    tables."""
    return {
        "customer": _extract_label_value_table(quotation_html, "customer-table", CUSTOMER_TABLE_SIGNATURES),
        "totals": _extract_label_value_table(quotation_html, "totals-table", TOTALS_TABLE_SIGNATURES),
        "items": _extract_item_rows(quotation_html),
    }


def build_invoice_document(
    quotation_html: str,
    doc_type: str,
    local_export: Optional[str] = None,
    invoice_no: Optional[str] = None,
    invoice_date: Optional[str] = None,
    buyer_name: Optional[str] = None,
    country: Optional[str] = None,
    port: Optional[str] = None,
    incoterm: Optional[str] = None,
    payment_terms: Optional[str] = None,
    *,
    extracted: Optional[dict] = None,
) -> str:
    """Build a Proforma Invoice, Invoice, Commercial Invoice, or Tax Invoice
    from a quotation's data.

    doc_type: "proforma_invoice" | "invoice" | "commercial_invoice" (export
    sale) | "tax_invoice" (domestic/GST sale). All four share the same
    Supplier / Ship To / Bill To / Bank Details / Freight box layout and the
    same IGST 18% domestic-tax treatment — only the heading and the invoice
    number label differ per type. This renders a fresh document from data
    extracted out of the quotation rather than relabeling the quotation's
    own HTML in place, since this box layout is structurally different from
    the Quotation.

    extracted: pass the result of extract_quotation_data(quotation_html) when
    building more than one invoice-family document from the same quotation,
    to avoid re-parsing the same HTML per call. Extracted fresh when omitted.
    """
    is_local = (local_export or "").strip().lower() == "local"
    currency_symbol = "₹" if is_local else "$"

    data = extracted if extracted is not None else extract_quotation_data(quotation_html)
    customer = data["customer"]
    totals = data["totals"]
    items = data["items"]

    # Ship To and Bill To are usually the same buyer, but the quotation's own
    # customer-table already tracks them as separate rows (occasionally a
    # freight/warehouse consignee differs from the invoiced buyer in the real
    # samples) — read them independently rather than forcing one value.
    # "bill to"/"ship to" are the chemical header's labels; engineering's header
    # labels the same row just "buyer" — check all three rather than assuming
    # one wording (mirrors the "quotation date"/"date" fallback below).
    bill_to_name = (
        buyer_name or customer.get("bill to") or customer.get("buyer") or customer.get("ship to") or ""
    )
    ship_to_name = customer.get("ship to") or bill_to_name
    # Engineering quotations don't capture a street address at all (their header
    # block is Buyer/Seller/Price Basis/... with no Address row) — fall back to
    # the buyer's country (already known from the row data) rather than leave the
    # line fully blank.
    buyer_address = customer.get("address") or country or ""
    buyer_gst = customer.get("gst no") or ""
    buyer_gst_line = (
        f"<br/>GSTIN/UIN: {buyer_gst}" if buyer_gst and buyer_gst.upper() != "N/A" else ""
    )
    used_invoice_no = (invoice_no or customer.get("quotation no") or "").strip()
    # Chemical quotations label this row "Quotation Date"; engineering quotations
    # label it just "Date" — check both keys rather than assuming one wording.
    used_date = (
        invoice_date or customer.get("quotation date") or customer.get("date") or ""
    ).strip()
    amount_in_words = totals.get("amount in words", "")

    title = _TITLES[doc_type]
    no_label = _NO_LABELS[doc_type]

    subtotal = 0.0
    item_rows_html = ""
    for idx, it in enumerate(items, start=1):
        amt = _extract_numeric_amount(it["amount"]) or 0.0
        subtotal += amt
        desc_html = it["product"] + (f'<br/>HSN: {it["hsn"]}' if it["hsn"] else "")
        qty_val, unit_val = _split_qty_unit(it["qty_unit"])
        item_rows_html += (
            "<tr>"
            f'<td style="{_TD_LABEL}">{idx}.</td>'
            f'<td style="{_TD_LABEL}">{desc_html}</td>'
            f'<td style="{_TD_VALUE}">{qty_val}</td>'
            f'<td style="{_TD_VALUE}">{it["unit_price"]}</td>'
            f'<td style="{_TD_LABEL}">{unit_val}</td>'
            f'<td style="{_TD_VALUE}">{it["amount"]}</td>'
            "</tr>"
        )

    # GST applies to domestic sales only — IGST 18% (matches the majority of
    # real Vertex Chemical commercial/tax invoices seen for domestic buyers).
    tax_row_html = ""
    grand_total = subtotal
    if is_local and subtotal > 0:
        igst = round(subtotal * 0.18, 2)
        grand_total = subtotal + igst
        tax_row_html = (
            "<tr>"
            f'<td style="{_TD_LABEL}" colspan="5">IGST 18%</td>'
            f'<td style="{_TD_VALUE}">{currency_symbol}{_fmt(igst)}</td>'
            "</tr>"
        )
    total_amount_display = (
        f"{currency_symbol}{_fmt(grand_total)}" if subtotal > 0 else (totals.get("total amount") or "")
    )
    # The quotation's "Amount in Words" describes the pre-tax subtotal; once GST is
    # added on top the words no longer match the grand total, so drop it rather than
    # show a wrong figure (we don't have a number-to-words conversion available here).
    if tax_row_html:
        amount_in_words = ""

    transport_mode = "By Road" if is_local else "By Sea"
    transaction_currency = "INR" if is_local else "USD"
    country_of_destination = "India" if is_local else (country or "")
    # Final Place of Delivery and Port of Discharge often show the same value in
    # the real samples (a port name, or the destination itself) — we only have
    # one "port" field on the stored quotation, so both reuse it.
    final_place_of_delivery = port or country_of_destination

    # (label, value, colspan) per row — each row's colspans must sum to 4;
    # _logistics_row raises immediately if a row is miscounted rather than
    # silently misaligning columns in the rendered PDF.
    logistics_rows = [
        [
            ("Freight Forwarder:", "", 1),
            ("Country of Origin", "INDIA", 1),
            ("Country of Destination:", country_of_destination, 2),
        ],
        [
            ("Transport Mode:", transport_mode, 1),
            ("Port of Loading:", "", 1),
            ("Terms of Delivery:", incoterm or "", 1),
            ("Relevant Location:", "", 1),
        ],
        [
            ("Final Place of Delivery:", final_place_of_delivery, 1),
            ("Port of Discharge:", port or "", 1),
            ("Terms of Payment:", payment_terms or "", 2),
        ],
        [
            ("", "", 3),
            ("Transaction Currency:", transaction_currency, 1),
        ],
    ]
    logistics_html = "".join(_logistics_row(row) for row in logistics_rows)

    return f"""<div class="invoice-family-page">
<h1 style="font-weight:bold;text-align:center;text-transform:uppercase;letter-spacing:0.04em;">{title}</h1>
<table class="ci-header-table" style="border-collapse:collapse;width:100%;border:{_BORDER};">
<tr>
<td style="{_TD_LABEL}width:50%;"><strong>Supplier</strong><br/>{_SUPPLIER_BLOCK}</td>
<td style="{_TD_LABEL}width:25%;"><strong>{no_label}</strong><br/>{used_invoice_no}</td>
<td style="{_TD_LABEL}width:25%;"><strong>Invoice Date</strong><br/>{used_date}</td>
</tr>
</table>
<table class="ci-parties-table" style="border-collapse:collapse;width:100%;border:{_BORDER};">
<tr>
<td style="{_TD_LABEL}width:50%;"><strong>Ship To:</strong><br/>{ship_to_name}<br/>{buyer_address}</td>
<td style="{_TD_LABEL}width:50%;"><strong>Bill To:</strong><br/>{bill_to_name}<br/>{buyer_address}{buyer_gst_line}</td>
</tr>
<tr>
<td style="{_TD_LABEL}" colspan="2"><strong>Bank Details:</strong><br/>{_BANK_BLOCK}</td>
</tr>
</table>
<table class="ci-logistics-table" style="border-collapse:collapse;width:100%;border:{_BORDER};table-layout:fixed;">
<colgroup><col style="width:25%"/><col style="width:25%"/><col style="width:25%"/><col style="width:25%"/></colgroup>
{logistics_html}
</table>
<table class="items-table" style="border-collapse:collapse;width:100%;border:{_BORDER};">
<tr>
<td style="{_TD_LABEL}background-color:#BBBBBB;"><strong>Item</strong></td>
<td style="{_TD_LABEL}background-color:#BBBBBB;"><strong>Description of Goods</strong></td>
<td style="{_TD_VALUE}background-color:#BBBBBB;"><strong>Quantity</strong></td>
<td style="{_TD_VALUE}background-color:#BBBBBB;"><strong>Unit Price</strong></td>
<td style="{_TD_LABEL}background-color:#BBBBBB;"><strong>Unit</strong></td>
<td style="{_TD_VALUE}background-color:#BBBBBB;"><strong>Amount</strong></td>
</tr>
{item_rows_html}
{tax_row_html}
<tr>
<td style="{_TD_LABEL}font-weight:bold;" colspan="5"><strong><b>TOTAL AMOUNT</b></strong></td>
<td style="{_TD_VALUE}font-weight:bold;"><strong><b>{total_amount_display}</b></strong></td>
</tr>
</table>
<table class="ci-footer-table" style="border-collapse:collapse;width:100%;border:{_BORDER};">
<tr><td style="{_TD_LABEL}"><strong>Currency (In Words):</strong> {amount_in_words}</td></tr>
</table>
<table class="declaration-sig-table" style="border-collapse:collapse;width:100%;border:{_BORDER};">
<tr>
<td style="{_TD_LABEL}width:65%;vertical-align:top;">
<strong>Declaration:</strong><br/>
We declare that this invoice shows the actual price of the goods described that no other invoice will be issued and that all particulars are true and correct.
</td>
<td style="{_TD_LABEL}width:35%;vertical-align:top;text-align:right;">
<p>AUTHORIZED SIGNATORY</p>
</td>
</tr>
</table>
</div>"""
