"""
Export service: wrap TipTap HTML with print CSS and generate DOCX/PDF.
HTML → DOCX and HTML → PDF independently (no DOCX→PDF).
"""

import base64
import io
import logging
import os
import re
from pathlib import Path
from re import Match
from typing import Optional

from app.services.export.print_css import EXPORT_PRINT_CSS

logger = logging.getLogger(__name__)

# Logo paths
_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets" / "logos"
_HEADER_LOGO = _ASSETS_DIR / "header_logo.png"
_FOOTER_LOGO = _ASSETS_DIR / "footer_logo.png"
# Engineering header: try newest asset first, then legacy name (same folder as chemical logos).
_ENGINEERING_LOGO_CANDIDATES: tuple[str, ...] = (
    "vertexengg-removebg-preview.png",
    "header_logo_engineering.png",
)
_ICON_LOCATION = _ASSETS_DIR / "location.png"
_ICON_PHONE = _ASSETS_DIR / "phone.png"
_ICON_EMAIL = _ASSETS_DIR / "mail.png"
_SIGNATURE_IMG = _ASSETS_DIR / "IMG-20260316-WA0003-removebg-preview.png"

# Signature image loaded once at import time — embedded as base64 so it survives production deploys
# and is injected at PDF export time (not stored in HTML, so TipTap edits can't strip it).
def _load_sig_tag() -> str:
    try:
        if _SIGNATURE_IMG.exists():
            b64 = base64.b64encode(_SIGNATURE_IMG.read_bytes()).decode()
            return (
                f'<img src="data:image/png;base64,{b64}" '
                f'style="height:65px; width:auto;" />'
            )
    except Exception:
        pass
    return ""

_SIG_TAG = _load_sig_tag()


def _is_engineering_pdf(product_type: Optional[str]) -> bool:
    return (product_type or "").strip().lower() == "engineering"


def _engineering_header_logo_path() -> Optional[Path]:
    """First existing engineering logo file under assets/logos."""
    for name in _ENGINEERING_LOGO_CANDIDATES:
        p = _ASSETS_DIR / name
        if p.is_file():
            return p
    return None


def _header_logo_path(product_type: Optional[str]) -> Path:
    """Chemical default logo; engineering uses dedicated asset when present."""
    if _is_engineering_pdf(product_type):
        eng = _engineering_header_logo_path()
        if eng is not None:
            return eng
    return _HEADER_LOGO


def _get_logo_base64(path: Path) -> str:
    """Read logo file and return base64 encoded data URI."""
    if not path.exists():
        return ""
    try:
        with open(path, "rb") as f:
            data = f.read()
        ext = path.suffix.lower().replace(".", "")
        if ext == "jpg":
            ext = "jpeg"
        return f"data:image/{ext};base64,{base64.b64encode(data).decode()}"
    except Exception:
        return ""


# Inline table style when style attr is missing (xhtml2pdf fallback).
# Match print_css: light borders, compact, export-quality.
_TABLE_INLINE = (
    "border-collapse: collapse; table-layout: fixed; width: 100%; "
    "margin: 6px 0; font-size: 11px; border: 1px solid #d0d0d0;"
)
_PAGE_BREAK_INLINE = "page-break-after: always;"


def _restore_quotation_format(html: str) -> str:
    """
    Restore structure/classes that the editor may strip on save, so PDF/DOCX match pre-edit format.
    - Re-apply items-table / totals-table to quotation tables.
    - Re-apply terms-sig-wrapper to the terms block div if missing.
    """
    if not html or not html.strip():
        return html
    # 1) Restore items-table: first table that has quotation columns (Description of Goods, Unit Price) but no class
    for m in re.finditer(r"<table(\s[^>]*)?>", html):
        tag = m.group(0)
        if "class=" in tag:
            continue
        start = m.end()
        end = min(start + 1200, len(html))
        chunk = html[start:end]
        if ("Description of Goods" in chunk or "Quantity" in chunk) and "Unit Price" in chunk:
            new_tag = "<table class=\"items-table\" " + (m.group(1) or "").lstrip()
            if not new_tag.endswith(">"):
                new_tag = new_tag.rstrip() + ">"
            html = html[: m.start()] + new_tag + html[m.end() :]
            break
    # 1b) Restore colgroup for items-table if missing (TipTap strips it)
    items_m = re.search(r'<table[^>]*class="[^"]*items-table[^"]*"[^>]*>', html)
    if items_m:
        after_tag = items_m.end()
        if "<colgroup" not in html[after_tag : after_tag + 120]:
            colgroup = '<colgroup><col style="width:6%"/><col style="width:40%"/><col style="width:14%"/><col style="width:20%"/><col style="width:20%"/></colgroup>'
            html = html[:after_tag] + colgroup + html[after_tag:]
    # 1c) weight-packing-table: NetWeight & GrossWeight header
    for m in re.finditer(r"<table(\s[^>]*)?>", html):
        tag = m.group(0)
        if "class=" in tag:
            continue
        start = m.end()
        end = min(start + 1200, len(html))
        chunk = html[start:end]
        if "Net Weight" in chunk and "Gross Weight" in chunk and "Packing" in chunk:
            new_tag = "<table class=\"weight-packing-table\" " + (m.group(1) or "").lstrip()
            if not new_tag.endswith(">"):
                new_tag = new_tag.rstrip() + ">"
            html = html[: m.start()] + new_tag + html[m.end() :]
            break
    # 2) Restore totals-table: first table containing "Total Amount" without that class
    pos = html.find("Total Amount")
    if pos != -1:
        look = html[:pos].rfind("<table")
        if look != -1:
            tag_end = html.find(">", look)
            if tag_end != -1 and "totals-table" not in html[look:tag_end] and "class=" not in html[look:tag_end]:
                after = look + 6
                insert = ' class="totals-table"'
                if html[after : after + 1] not in (" ", ">"):
                    insert = " " + insert
                html = html[:after] + insert + html[after:]
    # 3a) Restore customer-table: table containing "Bill To" or "Buyer"
    if "customer-table" not in html:
        for m in re.finditer(r"<table(\s[^>]*)?>", html):
            tag = m.group(0)
            if "class=" in tag:
                continue
            start = m.end()
            chunk = html[start : min(start + 600, len(html))]
            if "Bill To" in chunk or "Buyer" in chunk:
                after = m.start() + 6
                insert = ' class="customer-table"'
                if html[after : after + 1] not in (" ", ">"):
                    insert = " " + insert
                html = html[:after] + insert + html[after:]
                break
    # 3b) Restore delivery-table: table containing "Delivery" / "Port" / "Payment"
    if "delivery-table" not in html:
        for m in re.finditer(r"<table(\s[^>]*)?>", html):
            tag = m.group(0)
            if "class=" in tag:
                continue
            start = m.end()
            chunk = html[start : min(start + 600, len(html))]
            if ("Delivery" in chunk or "Port" in chunk or "Payment" in chunk) and "Description of Goods" not in chunk:
                after = m.start() + 6
                insert = ' class="delivery-table"'
                if html[after : after + 1] not in (" ", ">"):
                    insert = " " + insert
                html = html[:after] + insert + html[after:]
                break
    # 3c) Restore terms-sig-wrapper on the div that contains TERMS & CONDITIONS (and AUTHORIZED) but lost the class
    if "terms-sig-wrapper" not in html and "TERMS & CONDITIONS" in html and "AUTHORIZED" in html.upper():
        pos = html.find("TERMS & CONDITIONS")
        if pos != -1:
            look_back = html[:pos]
            last_div = look_back.rfind("<div")
            if last_div != -1:
                tag_end = html.find(">", last_div)
                if tag_end != -1 and "terms-sig-wrapper" not in html[last_div:tag_end]:
                    after_div = last_div + 4
                    insert = ' class="terms-sig-wrapper"'
                    if html[after_div : after_div + 1] not in (" ", ">"):
                        insert = " " + insert
                    html = html[:after_div] + insert + html[after_div:]
    # 4) Ensure terms-sig-table class (and borderless style) on the table that holds 13-15 + signatory.
    # After edit, TipTap may output <table class="..."> so we must merge in terms-sig-table, not skip.
    if "TERMS & CONDITIONS" in html:
        tc_pos = html.find("TERMS & CONDITIONS")
        if tc_pos != -1:
            search_start = tc_pos
            for tm in re.finditer(r"<table(\s[^>]*)?>", html[search_start:]):
                abs_start = search_start + tm.start()
                tag = tm.group(0)
                if "items-table" in tag or "totals-table" in tag:
                    continue
                tag_end_abs = search_start + tm.end()
                peek = html[tag_end_abs : tag_end_abs + 600]
                if "AUTHORIZED" in peek.upper() or "13." in peek:
                    rest = (tm.group(1) or "").strip()
                    if "terms-sig-table" in tag:
                        # Already has class; ensure inline border-none is on the table
                        if "border:none" not in tag and "border: none" not in tag:
                            style_attr = ' style="width:100%;border:none !important;border-collapse:collapse;margin:0;page-break-inside:avoid !important;"'
                            if ' style="' in tag:
                                html = html[:abs_start] + tag.replace(' style="', style_attr + ' style="') + html[tag_end_abs:]
                            else:
                                html = html[:tag_end_abs] + style_attr + html[tag_end_abs:]
                        break
                    # Add or merge class and style
                    borderless_style = 'style="width:100%;border:none !important;border-collapse:collapse;margin:0;page-break-inside:avoid !important;"'
                    if "class=" in tag:
                        # Merge terms-sig-table into existing class
                        new_tag = re.sub(
                            r'\bclass="([^"]*)"',
                            lambda m: 'class="' + m.group(1).strip() + ' terms-sig-table"' if "terms-sig-table" not in m.group(1) else m.group(0),
                            tag,
                            count=1,
                        )
                        if "border:none" not in new_tag and "border: none" not in new_tag:
                            if ' style="' in new_tag:
                                new_tag = re.sub(r'\s*style="[^"]*"', " " + borderless_style, new_tag, count=1)
                            else:
                                new_tag = new_tag[:-1] + " " + borderless_style + ">"
                        html = html[:abs_start] + new_tag + html[tag_end_abs:]
                    else:
                        insert = ' class="terms-sig-table" ' + borderless_style
                        if html[abs_start + 6 : abs_start + 7] not in (" ", ">"):
                            insert = " " + insert
                        html = html[: abs_start + 6] + insert + html[tag_end_abs:]
                    break
    return html


# Unicode subscript/superscript digits often render as black boxes in PDF (font lacks glyphs).
# Replace with HTML <sub>/<sup> so the engine uses normal digits in subscript/superscript position.
_SUBSCRIPT_DIGITS = "\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089"  # ₀₁₂₃₄₅₆₇₈₉
_SUPERSCRIPT_DIGITS = "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"  # ⁰¹²³⁴⁵⁶⁷⁸⁹

# Unicode rupee (U+20B9) often renders as a black square in PDF when the font lacks the glyph.
# Replaced with RUPEE_SYMBOL_FOR_EXPORT in PDF/DOCX. Use "Rs. " to avoid the box; change if you add a font that supports ₹.
RUPEE_SYMBOL_FOR_EXPORT = "Rs. "
RUPEESYM = "\u20b9"
# HTML entities for rupee (in case content was saved as entity)
RUPEESYM_ENTITY_DEC = "&#8377;"
RUPEESYM_ENTITY_HEX = "&#x20b9;"


def _replace_rupee_for_export(html: str) -> str:
    """Replace Unicode rupee (and HTML entities) with RUPEE_SYMBOL_FOR_EXPORT so PDF/DOCX show 'Rs.' not a black box."""
    html = html.replace(RUPEESYM, RUPEE_SYMBOL_FOR_EXPORT)
    html = html.replace(RUPEESYM_ENTITY_DEC, RUPEE_SYMBOL_FOR_EXPORT)
    html = html.replace(RUPEESYM_ENTITY_HEX, RUPEE_SYMBOL_FOR_EXPORT)
    return html


def _strip_currency_row_from_quotation(html: str) -> str:
    """Remove the 'Currency' / 'Currency USD' row from the delivery table if present (user requested no such row)."""
    # Match delivery-table and remove one <tr>...</tr> whose first <td> contains "Currency"
    pattern = re.compile(
        r'(<table[^>]*class="[^"]*delivery-table[^"]*"[^>]*>.*?)'
        r'<tr[^>]*>\s*<td[^>]*>[^<]*Currency[^<]*</td>.*?</tr>\s*',
        re.DOTALL | re.IGNORECASE,
    )
    return pattern.sub(r"\1", html)


def _normalize_unicode_sub_superscript(html: str) -> str:
    """Replace Unicode subscript/superscript digits with <sub>N</sub> / <sup>N</sup> for PDF-safe rendering."""
    result = html
    for i, char in enumerate(_SUBSCRIPT_DIGITS):
        result = result.replace(char, f"<sub>{i}</sub>")
    for i, char in enumerate(_SUPERSCRIPT_DIGITS):
        result = result.replace(char, f"<sup>{i}</sup>")
    return result


def _normalize_declaration_spacing(html: str) -> str:
    """Fix declaration/signatory text where spaces were dropped or typos (so PDF shows correct text)."""
    replacements = (
        ("describedand", "described and"),
        ("particularsare", "particulars are"),
        ("AuthorizeSignatory", "Authorized Signatory"),
        ("Authorize Signatory", "Authorized Signatory"),
        ("Authorize Signator", "Authorized Signatory"),
    )
    result = html
    for old, new in replacements:
        result = result.replace(old, new)
    return result


def _normalize_place_and_date_to_date(html: str) -> str:
    """Replace 'Place & Date: Place, DD/MM/YYYY' with 'Date: DD/MM/YYYY' (show date only)."""
    # Match "Place & Date:" or "Place &amp; Date:" then optional place and comma, then capture date
    pattern = re.compile(
        r"Place\s*&\s*(?:amp;)?\s*Date\s*:\s*([^<]+?)(?=<|$)",
        re.IGNORECASE,
    )

    def _repl(m: Match) -> str:
        rest = (m.group(1) or "").strip()
        if "," in rest:
            # "Mumbai, 26/03/2026" -> take part after last comma
            date_part = rest.rsplit(",", 1)[-1].strip()
        else:
            date_part = rest
        return f"Date: {date_part}" if date_part else "Date:"

    return pattern.sub(_repl, html)


def _get_header_footer_css() -> str:
    """Generate CSS for header and footer."""
    return """
    @page {
        size: A4 portrait;
        margin: 2cm 1cm 2cm 1cm;
    }
    """


def _header_footer_vars(
    letterhead: Optional[str] = None,
    product_type: Optional[str] = None,
) -> tuple[str, str, str, str, str]:
    """Return (header_phone, header_web, footer_address, footer_mobile, footer_web) for given letterhead. Dubai vs India."""
    letterhead = (letterhead or "").strip().lower()
    eng = _is_engineering_pdf(product_type)
    if letterhead == "dubai":
        if eng:
            return (
                "Mobile no : 971 525261658",
                "vertexengineerings.ae",
                "DSO-IFZA, IFZA Properties, Dubai Silicon Oasis",
                "Mobile no : 971 525261658",
                "Web: vertexengineerings.ae",
            )
        return (
            "Mobile no : 971 525261658",
            "vertexchemical.in",
            "DSO-IFZA, IFZA Properties, Dubai Silicon Oasis",
            "Mobile no : 971 525261658",
            "Web: vertexchemical.in",
        )
    # India (default)
    if eng:
        return (
            "+91 8866335159",
            "www.vertexengineerings.in",
            "206/5, Signet Hub, Akshar Chowk, Vadodara-390020",
            "+91 99095 51658",
            "Web: www.vertexengineerings.in",
        )
    return (
        "+91 8866335159",
        "vertexchemical.in",
        "206/5, Signet Hub, Akshar Chowk, Vadodara-390020",
        "+91 99095 51658",
        "Web: vertexchemical.in",
    )


def _get_header_html() -> str:
    """Generate header HTML for PDF using xhtml2pdf pdf:template."""
    header_logo = _get_logo_base64(_HEADER_LOGO)
    return f'''
<div id="header_content" style="display:none;">
    <table style="width:100%; border:none; border-collapse:collapse; border-bottom:2px solid #333;">
        <tr>
            <td style="width:60px; border:none; padding:2px; vertical-align:middle;">
                <img src="{header_logo}" style="width:55px; height:auto;"/>
            </td>
            <td style="border:none; padding:2px 8px; vertical-align:middle;">
                <p style="font-size:14px; font-weight:bold; color:#1a5276; margin:0; padding:0;">VERTEX CHEMICAL</p>
                <p style="font-size:7px; color:#666; letter-spacing:0.5px; margin:0; padding:0;">YOUR PARTNER FOR QUALITY CHEMICALS, GLOBALLY</p>
            </td>
            <td style="width:150px; border:none; padding:2px 2px 2px 10px; vertical-align:middle;">
                <p style="font-size:8px; color:#333; text-align:right; margin:0; padding:0;"><b>Phone:</b> +91 8866335159</p>
                <p style="font-size:8px; color:#333; text-align:right; margin:0; padding:0;"><b>Web:</b> vertexchemical.in</p>
            </td>
        </tr>
    </table>
</div>
'''


def _get_footer_html() -> str:
    """Generate footer HTML for PDF using xhtml2pdf pdf:template (separator line only, no logo)."""
    return '''
<div id="footer_content" style="display:none;">
    <div style="border-top:3px solid #333; width:100%;"></div>
</div>
'''


def _normalize_quotation_spacing(html: str) -> str:
    """Remove stray spacer paragraphs between quotation tables so spacing is CSS-controlled and consistent."""
    # Remove <p><br/></p> or <p>&nbsp;</p> that appear between </table> and <table>
    html = re.sub(
        r"(</table>)\s*(?:<p[^>]*>\s*(?:<br\s*/?>|&nbsp;)\s*</p>\s*)+(<table|<div|<h[1-6])",
        r"\1\n\2",
        html,
        flags=re.IGNORECASE,
    )
    # Remove leading spacers before the first table in .quotation-page
    html = re.sub(
        r'(class="quotation-page"[^>]*>)\s*(?:<p[^>]*>\s*(?:<br\s*/?>|&nbsp;)\s*</p>\s*)+',
        r"\1\n",
        html,
        flags=re.IGNORECASE,
    )
    return html


def _ensure_signatory_block_no_split(html: str) -> str:
    """Ensure the signatory-block (stamp image + AUTHORIZED SIGNATORY + Date) can never
    be split mid-block across a page break.

    xhtml2pdf does not reliably honor page-break-inside:avoid on a plain <div> — only on
    <table> (mapped to a KeepTogether-wrapped reportlab Table). Documents generated before
    this was known still store a bare standalone signatory-block div, so at export time we
    re-wrap it in a single-cell table (the same mechanism already used for the terms-sig-table
    split case, which reliably stays together). A signatory-block already inside a <td> (the
    split case) is left alone — it's already reliably kept together."""
    def _fix(m: re.Match) -> str:
        inner = m.group(1)
        preceding = html[max(0, m.start() - 150) : m.start()]
        if "<td" in preceding:
            return m.group(0)  # already inside a table cell
        return (
            '<table class="terms-sig-table" style="width:100%;border:none !important;'
            "border-collapse:collapse;margin:0;page-break-inside:avoid !important;\">"
            '<tr style="border:none !important;vertical-align:top;">'
            '<td style="border:none !important;padding:0;text-align:right;vertical-align:top;">'
            f'<div class="signatory-block" style="text-align:right;margin-top:0;">{inner}</div>'
            "</td></tr></table>"
        )
    return re.sub(
        r'<div class="[^"]*\bsignatory-block\b[^"]*"[^>]*>(.*?)</div>',
        _fix,
        html,
        flags=re.DOTALL,
    )


def _force_terms_sig_borders_off(html: str) -> str:
    """Force border:none on the terms/signatory table (13-15 + AUTHORIZED SIGNATORY).
    Uses multiple strategies to find the table; strips ALL border properties and injects border:none !important.
    Also zeroes padding/margin so 13-15 aligns with 1-12 above."""
    _NOBORDER_TABLE = (
        "border:none !important;border-width:0 !important;border-style:none !important;"
        "border-collapse:collapse !important;border-spacing:0 !important;"
        "margin:0 !important;padding:0 !important;"
    )
    _NOBORDER_CELL = (
        "border:none !important;border-width:0 !important;border-style:none !important;"
        "padding:0 !important;"
    )

    def _strip_border_props(style_val: str) -> str:
        """Remove all border-* and padding/margin properties from an inline style value."""
        return re.sub(
            r"\s*(?:border(?:-width|-style|-color|-collapse|-spacing)?|padding|margin)\s*:\s*[^;]+;?",
            "", style_val, flags=re.IGNORECASE,
        ).strip().strip(";")

    def _inject_table(tag: str) -> str:
        if 'style="' in tag:
            style_m = re.search(r'style="([^"]*)"', tag)
            if style_m:
                cleaned = _strip_border_props(style_m.group(1))
                new_style = _NOBORDER_TABLE + ((";" + cleaned) if cleaned else "")
                tag = re.sub(r'style="[^"]*"', f'style="{new_style}"', tag, count=1)
        else:
            tag = tag[:-1] + f' style="{_NOBORDER_TABLE}">'
        # Ensure cellpadding/cellspacing attributes for xhtml2pdf
        if "cellpadding" not in tag:
            tag = tag.replace("<table", '<table cellpadding="0"', 1)
        if "cellspacing" not in tag:
            tag = tag.replace("<table", '<table cellspacing="0"', 1)
        return tag

    def _inject_cell(tag: str) -> str:
        if 'style="' in tag:
            style_m = re.search(r'style="([^"]*)"', tag)
            if style_m:
                cleaned = _strip_border_props(style_m.group(1))
                new_style = _NOBORDER_CELL + ((";" + cleaned) if cleaned else "")
                return re.sub(r'style="[^"]*"', f'style="{new_style}"', tag, count=1)
        return tag[:-1] + f' style="{_NOBORDER_CELL}">'

    # Find table start position
    tbl_start = -1

    # Strategy 1: find by class
    cls_m = re.search(r'<table[^>]*class="[^"]*terms-sig-table[^"]*"', html, re.IGNORECASE)
    if cls_m:
        tbl_start = cls_m.start()

    # Strategy 2: find by content — any table containing "AUTHORIZED" and "13." or similar
    if tbl_start < 0:
        for tm in re.finditer(r"<table[^>]*>", html):
            tag = tm.group(0)
            if "items-table" in tag or "totals-table" in tag or "customer-table" in tag or "delivery-table" in tag:
                continue
            end_tbl = html.find("</table>", tm.end())
            if end_tbl == -1:
                continue
            body = html[tm.end():end_tbl]
            body_upper = body.upper()
            if "AUTHORIZED" in body_upper and ("13." in body or "CLAIMS" in body_upper):
                tbl_start = tm.start()
                break

    if tbl_start < 0:
        return html

    end_table = html.find("</table>", tbl_start + 1)
    if end_table == -1:
        return html
    end_table += len("</table>")
    chunk = html[tbl_start:end_table]

    chunk = re.sub(r"<table[^>]*>", lambda m: _inject_table(m.group(0)), chunk, flags=re.IGNORECASE)
    chunk = re.sub(r"<t[dhr][^>]*>", lambda m: _inject_cell(m.group(0)), chunk, flags=re.IGNORECASE)
    chunk = re.sub(r"<tbody[^>]*>", lambda m: _inject_cell(m.group(0)), chunk, flags=re.IGNORECASE)
    return html[:tbl_start] + chunk + html[end_table:]


def _inject_signature_image(html: str, *, manual_document: bool = False) -> str:
    """Inject the authorized-signatory stamp image at PDF export time.

    - Generated docs: place the image just before ``AUTHORIZED SIGNATORY`` when that text exists.
    - Manual docs: if that phrase is missing, append the signature block at the **end** of the
      document so PDFs still show the stamp (TipTap may not include signatory wording).
    """
    sig_tag = _SIG_TAG
    if not sig_tag:
        sig_tag = _load_sig_tag()
    if not sig_tag:
        return html

    upper = html.upper()
    auth_pos = upper.find("AUTHORIZED SIGNATORY")

    if auth_pos != -1:
        nearby = html[max(0, auth_pos - 500) : auth_pos]
        if "<img" in nearby.lower():
            return html
        sig_block = (
            f'<div style="text-align:right; display:block; width:100%;">'
            f"{sig_tag}"
            f"</div>"
        )
        p_pos = html.rfind("<p", 0, auth_pos)
        if p_pos == -1:
            return html[:auth_pos] + sig_block + html[auth_pos:]
        return html[:p_pos] + sig_block + html[p_pos:]

    if manual_document:
        tail = html[-1200:] if len(html) > 1200 else html
        if "height:65px" in tail and "width:auto" in tail:
            return html
        sig_footer = (
            '<div style="text-align:right; display:block; width:100%; margin-top:28px; '
            'padding-top:14px; border-top:1px solid #ccc;">'
            f"{sig_tag}"
            '<p style="font-size:9pt; color:#333; margin:8px 0 0 0;">Authorized Signatory</p>'
            "</div>"
        )
        return html + sig_footer

    return html


def _prepare_body_for_export(html: str) -> str:
    """Run body normalization steps that are independent of currency/local_export.
    Note: signature injection is done AFTER currency normalization in html_to_pdf
    to prevent the currency regex from corrupting the base64 image data."""
    body = _restore_quotation_format(html)
    body = _strip_currency_row_from_quotation(body)
    body = _normalize_body(body)
    body = _normalize_quotation_spacing(body)
    body = _force_terms_sig_borders_off(body)
    body = _ensure_signatory_block_no_split(body)
    return body


# Items table currency columns: Unit Price=index 3, Unit Amount=index 4 (0-based)
_ITEMS_CURRENCY_COLS = {3, 4}
# A bare number in a table cell (with optional commas/decimals)
_BARE_NUM_RE = re.compile(r"^\d[\d,]*(?:\.\d{1,2})?$")


def _prefix_bare_number_in_cell(cell_inner: str, prefix: str) -> str:
    """If cell_inner (stripped of bold tags) is a bare number with no currency symbol, return it prefixed.
    Otherwise return unchanged."""
    stripped = re.sub(r"\s*</?(?:strong|b)>\s*", "", cell_inner).strip()
    if re.match(r"^[\$₹]|^Rs\.", stripped, re.IGNORECASE):
        return cell_inner  # already has a currency symbol
    if not _BARE_NUM_RE.match(stripped):
        return cell_inner  # not a plain number
    return cell_inner.replace(stripped, prefix + stripped, 1)


def _apply_currency_to_items_table(table_html: str, prefix: str) -> str:
    """Apply currency prefix ONLY to Unit Price (col 3) and Unit Amount (col 4) in each data row."""
    result: list[str] = []
    pos = 0
    for row_m in re.finditer(r"(<tr[^>]*>)(.*?)(</tr>)", table_html, re.DOTALL | re.IGNORECASE):
        result.append(table_html[pos:row_m.start()])
        pos = row_m.end()
        row_open, row_body, row_close = row_m.group(1), row_m.group(2), row_m.group(3)
        # Skip header rows
        if re.search(r"Unit\s*Price|Unit\s*Amount|Description\s*of\s*Goods", row_body, re.IGNORECASE):
            result.append(row_m.group(0))
            continue
        # Find all td cells in this row
        td_list = list(re.finditer(r"(<td[^>]*>)(.*?)(</td>)", row_body, re.DOTALL | re.IGNORECASE))
        if not td_list:
            result.append(row_m.group(0))
            continue
        # Build new row_body applying currency only at target indices
        new_body = row_body
        # Process in reverse so earlier positions stay valid
        for col_idx in sorted(_ITEMS_CURRENCY_COLS, reverse=True):
            if col_idx >= len(td_list):
                continue
            td_m = td_list[col_idx]
            new_inner = _prefix_bare_number_in_cell(td_m.group(2), prefix)
            if new_inner != td_m.group(2):
                new_body = (
                    new_body[: td_m.start(2)]
                    + new_inner
                    + new_body[td_m.end(2):]
                )
                # Reparse since string changed
                td_list = list(re.finditer(r"(<td[^>]*>)(.*?)(</td>)", new_body, re.DOTALL | re.IGNORECASE))
        result.append(row_open + new_body + row_close)
    result.append(table_html[pos:])
    return "".join(result)


def _apply_currency_to_totals_table(table_html: str, prefix: str) -> str:
    """Apply currency prefix to the LAST cell in each totals-table row (the value cell)."""
    result: list[str] = []
    pos = 0
    for row_m in re.finditer(r"(<tr[^>]*>)(.*?)(</tr>)", table_html, re.DOTALL | re.IGNORECASE):
        result.append(table_html[pos:row_m.start()])
        pos = row_m.end()
        row_open, row_body, row_close = row_m.group(1), row_m.group(2), row_m.group(3)
        td_list = list(re.finditer(r"(<td[^>]*>)(.*?)(</td>)", row_body, re.DOTALL | re.IGNORECASE))
        if not td_list:
            result.append(row_m.group(0))
            continue
        last = td_list[-1]
        new_inner = _prefix_bare_number_in_cell(last.group(2), prefix)
        if new_inner != last.group(2):
            row_body = row_body[: last.start(2)] + new_inner + row_body[last.end(2):]
        result.append(row_open + row_body + row_close)
    result.append(table_html[pos:])
    return "".join(result)


def _ensure_dollar_prefix_in_export(html: str) -> str:
    """Prepend $ to bare-number cells in items-table (cols 3,4) and totals-table (last col)."""
    def _fix_table(m: re.Match, is_items: bool) -> str:
        before, body, after = m.group(1), m.group(2), m.group(3)
        if is_items:
            body = _apply_currency_to_items_table(body, "$")
        else:
            body = _apply_currency_to_totals_table(body, "$")
        return before + body + after

    html = re.sub(
        r'(<table[^>]*class="[^"]*items-table[^"]*"[^>]*>)(.*?)(</table>)',
        lambda m: _fix_table(m, True),
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    html = re.sub(
        r'(<table[^>]*class="[^"]*totals-table[^"]*"[^>]*>)(.*?)(</table>)',
        lambda m: _fix_table(m, False),
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return html


def _ensure_rupee_prefix_in_local(html: str) -> str:
    """For local quotations: replace stray $ with Rs. and prepend Rs. to bare numbers in items/totals tables."""
    # First normalise any stray $ → Rs. in both tables
    for tbl_cls in ("totals-table", "items-table"):
        html = re.sub(
            rf'(<table[^>]*class="[^"]*{tbl_cls}[^"]*"[^>]*>)(.*?)(</table>)',
            lambda m: m.group(1) + re.sub(r"\$\s*(\d)", r"Rs. \1", m.group(2)) + m.group(3),
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

    def _fix_table(m: re.Match, is_items: bool) -> str:
        before, body, after = m.group(1), m.group(2), m.group(3)
        if is_items:
            body = _apply_currency_to_items_table(body, "Rs. ")
        else:
            body = _apply_currency_to_totals_table(body, "Rs. ")
        return before + body + after

    html = re.sub(
        r'(<table[^>]*class="[^"]*items-table[^"]*"[^>]*>)(.*?)(</table>)',
        lambda m: _fix_table(m, True),
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    html = re.sub(
        r'(<table[^>]*class="[^"]*totals-table[^"]*"[^>]*>)(.*?)(</table>)',
        lambda m: _fix_table(m, False),
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return html


def _normalize_currency_for_export(html: str, local_export: Optional[str] = None) -> str:
    """
    Normalize currency symbols for PDF/DOCX export.
    - LOCAL: Rupee symbol/HTML entities → 'Rs. ' (avoid missing-glyph boxes).
    - EXPORT: Any rupee symbol/HTML entity or 'Rs.' prefix → '$'; also prepend $ to amounts that have no symbol.
    If local_export is not provided, default to legacy behaviour (treat as LOCAL).
    """
    flag = (local_export or "").strip().lower()
    # Legacy/default: behave like LOCAL (₹ → Rs.)
    if not flag or flag == "local":
        out = _replace_rupee_for_export(html)
        out = _ensure_rupee_prefix_in_local(out)
        return out

    # EXPORT: convert rupee to $ and ensure $ appears where amounts have no symbol.
    out = html.replace(RUPEESYM, "$")
    out = out.replace(RUPEESYM_ENTITY_DEC, "$")
    out = out.replace(RUPEESYM_ENTITY_HEX, "$")
    out = re.sub(r"\bRs\.?\s*", "$", out, flags=re.IGNORECASE)
    out = _ensure_dollar_prefix_in_export(out)
    return out


def _header_branding(product_type: Optional[str]) -> tuple[str, str]:
    """Company line and tagline for PDF header."""
    if _is_engineering_pdf(product_type):
        return (
            "VERTEX ENGINEERING",
            "INDUSTRIAL ELECTRICAL, INSTRUMENTATION & AUTOMATION SOLUTIONS",
        )
    return (
        "VERTEX CHEMICAL",
        "YOUR PARTNER FOR QUALITY CHEMICALS, GLOBALLY",
    )


def _header_footer_tables(
    letterhead: Optional[str],
    header_logo: str,
    footer_logo: str,
    product_type: Optional[str] = None,
) -> tuple[str, str]:
    """Build header and footer table HTML."""
    h_phone, h_web, _footer_address, _footer_mobile, _footer_web = _header_footer_vars(
        letterhead, product_type=product_type
    )
    company_line, tagline = _header_branding(product_type)
    logo_cell = (
        f'<img src="{header_logo}" width="55" height="50"/>'
        if header_logo
        else '<span style="display:inline-block;width:55px;height:50px;"></span>'
    )
    header_table = f'''<table class="hf-table">
<tr>
<td style="width:60px; padding:2px 4px; vertical-align:middle;">
{logo_cell}
</td>
<td style="padding:2px 8px; vertical-align:middle; text-align:left; line-height:1.25;">
<b style="font-size:11pt; color:#1a5276; line-height:1.25;">{company_line}</b><br/>
<span style="font-size:5.5pt; color:#666; letter-spacing:0.3pt; line-height:1.25;">{tagline}</span>
</td>
<td style="width:34%; padding:2px 8px; vertical-align:middle; text-align:right; word-wrap:break-word; overflow-wrap:break-word; white-space:normal; line-height:1.35;">
<span style="font-size:7pt; color:#333;"><b>Phone:</b> {h_phone}</span><br/>
<span style="font-size:7pt; color:#333;"><b>Web:</b> {h_web}</span>
</td>
</tr>
</table>
<hr class="hf-line hf-line-header"/>'''

    footer_table = '''<hr class="hf-line hf-line-footer"/>
'''
    return header_table, footer_table


def wrap_html_for_export(
    body_html: str,
    include_header_footer: bool = False,
    letterhead: Optional[str] = None,
    prepared_body: Optional[str] = None,
    product_type: Optional[str] = None,
) -> str:
    """
    Wrap TipTap/editor HTML in a full document with the export print CSS.
    Single source for both DOCX and PDF. Normalizes page-break divs.
    letterhead: "dubai" | "india" | None for chemical header/footer address and phone.
    prepared_body: if set, use this as body (already normalized + currency applied); skip _prepare_body and rupee replacement.
    product_type: "engineering" uses engineering logo and Vertex Engineering branding in PDF header when present.
    """
    if prepared_body is not None:
        body_html = prepared_body
    else:
        body_html = _prepare_body_for_export(body_html)
        # For DOCX and generic HTML export we keep legacy behaviour: treat rupee as Rs.
        body_html = _replace_rupee_for_export(body_html)

    if include_header_footer:
        header_logo = _get_logo_base64(_header_logo_path(product_type))
        footer_logo = _get_logo_base64(_FOOTER_LOGO)
        icon_location = _get_logo_base64(_ICON_LOCATION)
        icon_phone = _get_logo_base64(_ICON_PHONE)
        icon_email = _get_logo_base64(_ICON_EMAIL)

        header_table, footer_table = _header_footer_tables(
            letterhead, header_logo, footer_logo, product_type=product_type
        )

        # xhtml2pdf approach: use @page with static frames
        
        # xhtml2pdf requires:
        # 1. Static frames with -pdf-frame-content pointing to element IDs
        # 2. Content frame WITHOUT -pdf-frame-content for main content flow
        # 3. Using absolute positioning (pt units work best)
        # A4 = 595pt x 842pt
        
        # Remove @page from EXPORT_PRINT_CSS to avoid conflict with our @page definition
        css_without_page = re.sub(r'@page\s*\{[^}]*\}', '', EXPORT_PRINT_CSS)
        
        full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<style type="text/css">
@page {{
    size: a4 portrait;
    @frame header_frame {{
        -pdf-frame-content: header_content;
        left: 50pt; width: 495pt; top: 30pt; height: 60pt;
    }}
    @frame content_frame {{
        left: 50pt; width: 495pt; top: 100pt; height: 675pt;
    }}
    /* 15pt gap (was 10pt) between content_frame's bottom (775pt) and here — a modest
       safety margin against an unbreakable block barely overflowing into the footer
       band, without sacrificing much usable page height (the real overflow risk is
       already fixed at the source: the terms-sig-wrapper is no longer one giant
       unbreakable block, see response_parser.py). */
    @frame footer_frame {{
        -pdf-frame-content: footer_content;
        left: 50pt; width: 495pt; top: 790pt; height: 45pt;
    }}
}}

/* Override styles for header/footer tables */
#header_content, #footer_content {{
    border: none !important;
    background: none !important;
}}
#header_content table, #footer_content table,
#header_content tr, #footer_content tr,
#header_content td, #footer_content td,
#header_content th, #footer_content th,
.hf-table, .hf-table tr, .hf-table td, .hf-table th {{
    border: none !important;
    background: none !important;
    background-color: transparent !important;
}}
/* Header/footer separator line */
.hf-line {{
    width: 100%;
    height: 0;
}}

{css_without_page}
</style>
</head>
<body>
<div id="header_content">
{header_table}
</div>

<div id="footer_content">
{footer_table}
</div>

{body_html}
</body>
</html>"""
        return full_html
    
    return f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta charset="UTF-8"/>
<style type="text/css">
{EXPORT_PRINT_CSS}
</style>
</head>
<body>
{body_html}
</body>
</html>"""


def _build_full_html_for_weasyprint(
    body_html: str,
    letterhead: Optional[str] = None,
    product_type: Optional[str] = None,
) -> str:
    """
    Build full HTML for WeasyPrint with running header/footer so they appear on every page
    in @page margin boxes (no -pdf-frame-content; WeasyPrint uses position: running()).
    Avoids header/footer being rendered as large blocks in the main flow.
    """
    header_logo = _get_logo_base64(_header_logo_path(product_type))
    footer_logo = _get_logo_base64(_FOOTER_LOGO)
    header_table, footer_table = _header_footer_tables(
        letterhead, header_logo, footer_logo, product_type=product_type
    )
    css_without_page = re.sub(r'@page\s*\{[^}]*\}', '', EXPORT_PRINT_CSS)
    # margin-top 90pt: header takes ~55pt, leaves ~35pt gap before content (matches local).
    # margin-bottom 65pt: footer takes ~40pt, leaves ~25pt gap after content.
    # margin-left/right 50pt: standard A4 side margins.
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<style type="text/css">
@page {{
  size: A4 portrait;
  margin-top: 90pt;
  margin-bottom: 65pt;
  margin-left: 50pt;
  margin-right: 50pt;
  @top-center {{
    content: element(header);
    vertical-align: bottom;
    width: 100%;
  }}
  @bottom-center {{
    content: element(footer);
    vertical-align: top;
    width: 100%;
  }}
}}

/* ── Running header/footer ── */
.run-header {{
  position: running(header);
  width: 100%;
  box-sizing: border-box;
}}
.run-footer {{
  position: running(footer);
  width: 100%;
  box-sizing: border-box;
}}

/* ── Reset ONLY border/background on header/footer elements ── */
/* Do NOT touch padding/margin — let inline styles control spacing */
#header_content, #footer_content {{
  border: none !important;
  background: none !important;
  background-color: transparent !important;
  box-sizing: border-box;
}}
.hf-table,
.hf-table tr,
.hf-table td,
.hf-table th {{
  border: none !important;
  background: none !important;
  background-color: transparent !important;
}}
.hf-table td {{
  padding: 2px 6px !important;
  font-size: 7pt !important;
  line-height: 1.3 !important;
  vertical-align: middle !important;
}}
.hf-table {{
  width: 100% !important;
  table-layout: fixed !important;
  border-collapse: collapse !important;
  margin: 0 !important;
}}
.hf-table img {{
  max-width: 55px !important;
  max-height: 50px !important;
  width: 55px !important;
  height: 50px !important;
  object-fit: contain !important;
  display: block !important;
}}
#footer_content .hf-table img {{
  max-width: 40px !important;
  max-height: 36px !important;
  width: 40px !important;
  height: 36px !important;
}}

/* Footer paragraphs — override generic p rule */
#footer_content p,
#header_content p {{
  margin: 0 !important;
  padding: 0 !important;
}}

/* Separator lines in header/footer — override the generic hr rule */
.hf-line {{
  height: 0 !important;
  padding: 0 !important;
  margin: 2px 0 !important;
}}
.hf-line-header {{
  border: none !important;
  border-bottom: 2px solid #333 !important;
}}
.hf-line-footer {{
  border: none !important;
  border-top: 2px solid #333 !important;
}}

/* ── Gap between header and body content ── */
.quotation-page {{
  padding-top: 8pt !important;
}}

{css_without_page}
</style>
</head>
<body>
<div id="header_content" class="run-header">
{header_table}
</div>
<div id="footer_content" class="run-footer">
{footer_table}
</div>
<div class="quotation-page">
{body_html}
</div>
</body>
</html>"""


def _normalize_inline_styles(html: str) -> str:
    """Strip inline font-size, margin, padding so print CSS controls typography and spacing."""
    def reduce_style(m: Match) -> str:
        style = m.group(1) or ""
        # Remove properties that we want to control via print CSS
        for prop in (
            r"font-size\s*:\s*[^;]+;?",
            r"margin\s*:\s*[^;]+;?",
            r"margin-[^:]+:\s*[^;]+;?",
            r"padding\s*:\s*[^;]+;?",
            r"padding-[^:]+:\s*[^;]+;?",
            r"line-height\s*:\s*[^;]+;?",
        ):
            style = re.sub(prop, "", style, flags=re.IGNORECASE)
        style = re.sub(r";+", ";", style).strip("; ").strip()
        if not style:
            return ""
        return f' style="{style}"'
    html = re.sub(r'\s+style="([^"]*)"', reduce_style, html)
    return html


def _normalize_body(html: str) -> str:
    """Apply print-layout normalization: Unicode sub/superscript, declaration spacing, place&date→date, then styles, page-breaks, tables."""
    html = _normalize_unicode_sub_superscript(html)
    html = _normalize_declaration_spacing(html)
    html = _normalize_place_and_date_to_date(html)
    html = _normalize_inline_styles(html)
    html = re.sub(
        r'<div\s+style="[^"]*page-break[^"]*"[^>]*>\s*</div>',
        f'<div class="page-break" style="{_PAGE_BREAK_INLINE}"></div>',
        html,
        flags=re.IGNORECASE,
    )
    def _table_repl(m: Match) -> str:
        rest = (m.group(1) or "").strip()
        if "style=" in rest:
            return m.group(0)
        if "terms-sig-table" in rest:
            return m.group(0)
        # Skip the terms/signatory table by checking content after <table>
        after_pos = m.end()
        close_tbl = html.find("</table>", after_pos)
        if close_tbl > 0:
            inner = html[after_pos:close_tbl]
            inner_upper = inner.upper()
            if "AUTHORIZED" in inner_upper and ("13." in inner or "CLAIMS" in inner_upper):
                return m.group(0)
        if rest:
            return f'<table {rest} style="{_TABLE_INLINE}">'.replace("  ", " ").strip()
        return f'<table style="{_TABLE_INLINE}">'
    html = re.sub(r"<table(\s[^>]*)?>", _table_repl, html)
    return html


def html_to_docx(html: str, title: str = "Document") -> bytes:
    """
    Generate DOCX from TipTap HTML. Preserves tables, alignment, fonts, spacing.
    Uses html2docx (pure Python). Same HTML input as PDF for consistency.
    """
    from html2docx import html2docx

    full_html = wrap_html_for_export(html)
    docx_buffer = html2docx(full_html, title=title)
    return docx_buffer.getvalue()


def _sanitize_html_for_pdf(html: str) -> str:
    """Remove attributes that break WeasyPrint/xhtml2pdf (e.g. int(None) on empty width/colspan)."""
    if not html:
        return html
    out = html
    out = re.sub(r'\s+(width|height|colspan|rowspan)\s*=\s*""', "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s+(width|height|colspan|rowspan)\s*=\s*''", "", out, flags=re.IGNORECASE)
    # Empty image src causes ReportLab/xhtml2pdf errors
    out = re.sub(
        r"<img([^>]*)\ssrc\s*=\s*(?:\"\"|'')\s*",
        r"<img\1 ",
        out,
        flags=re.IGNORECASE,
    )
    return out


def html_to_pdf(
    html: str,
    letterhead: Optional[str] = None,
    local_export: Optional[str] = None,
    product_type: Optional[str] = None,
    manual_document: bool = False,
) -> bytes:
    """
    Generate PDF from TipTap HTML. Prefer WeasyPrint; fallback to xhtml2pdf.
    A4, fixed margins, stable tables, page-break control.
    Includes header and footer on every page.
    letterhead: "dubai" | "india" | None.
    local_export: "local" | "export" for currency normalization (Rs vs $).
    product_type: "engineering" selects engineering letterhead (logo, name, web URLs).
    manual_document: when True, append signature image at end of body if no AUTHORIZED SIGNATORY block.
    """
    html = _sanitize_html_for_pdf(html)
    body_html = _prepare_body_for_export(html)
    body_html = _normalize_currency_for_export(body_html, local_export)
    # Inject signature AFTER currency normalization so the base64 image data
    # is never processed by the Rs→$ regex (which would corrupt the base64).
    body_html = _inject_signature_image(body_html, manual_document=manual_document)

    full_html_weasy = _sanitize_html_for_pdf(
        _build_full_html_for_weasyprint(body_html, letterhead, product_type=product_type)
    )
    pdf_bytes: Optional[bytes] = _pdf_weasyprint(full_html_weasy)
    if pdf_bytes is not None:
        return pdf_bytes
    full_html = _sanitize_html_for_pdf(
        wrap_html_for_export(
            html,
            include_header_footer=True,
            letterhead=letterhead,
            prepared_body=body_html,
            product_type=product_type,
        )
    )
    return _pdf_xhtml2pdf(full_html)


def _pdf_weasyprint(html: str) -> Optional[bytes]:
    """Use WeasyPrint if available (best quality). Returns None on failure."""
    try:
        from weasyprint import HTML
        out = io.BytesIO()
        HTML(string=html).write_pdf(out)
        return out.getvalue()
    except Exception:
        return None


def _pdf_xhtml2pdf(html: str) -> bytes:
    """Fallback: xhtml2pdf (pure Python, no system libs). Works on Render free tier."""
    from xhtml2pdf import pisa
    out = io.BytesIO()
    err = pisa.CreatePDF(html, dest=out, encoding="utf-8")
    if err.err:
        raise RuntimeError("PDF generation failed")
    return out.getvalue()
