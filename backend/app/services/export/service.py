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
_ICON_LOCATION = _ASSETS_DIR / "location.png"
_ICON_PHONE = _ASSETS_DIR / "phone.png"
_ICON_EMAIL = _ASSETS_DIR / "mail.png"


def _get_logo_base64(path: Path) -> str:
    """Read logo file and return base64 encoded data URI."""
    abs_path = path.resolve()
    logger.info(f">>> [EXPORT] Loading logo path={path!r} resolved={abs_path!r} exists={path.exists()}")
    if not path.exists():
        logger.warning(f">>> [EXPORT] Logo file NOT FOUND: {path} (cwd={os.getcwd()!r})")
        return ""
    try:
        with open(path, "rb") as f:
            data = f.read()
        file_size = len(data)
        ext = path.suffix.lower().replace(".", "")
        if ext == "jpg":
            ext = "jpeg"
        result = f"data:image/{ext};base64,{base64.b64encode(data).decode()}"
        logger.info(f">>> [EXPORT] Logo loaded path={path.name} file_size={file_size} base64_len={len(result)}")
        return result
    except Exception as e:
        logger.error(f">>> [EXPORT] Error loading logo path={path}: {e}", exc_info=True)
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
    # 3) Restore terms-sig-wrapper on the div that contains TERMS & CONDITIONS (and AUTHORIZED) but lost the class
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


def _get_header_footer_css() -> str:
    """Generate CSS for header and footer."""
    logger.info(">>> Generating header/footer CSS")
    
    return """
    @page {
        size: A4 portrait;
        margin: 2cm 1cm 2cm 1cm;
    }
    """


def _header_footer_vars(letterhead: Optional[str] = None) -> tuple[str, str, str, str, str]:
    """Return (header_phone, header_web, footer_address, footer_mobile, footer_web) for given letterhead. Dubai vs India."""
    letterhead = (letterhead or "").strip().lower()
    if letterhead == "dubai":
        return (
            "Mobile no : 971 525261658",
            "vertexchemical.in",
            "DSO-IFZA, IFZA Properties, Dubai Silicon Oasis",
            "Mobile no : 971 525261658",
            "Web: vertexchemical.in",
        )
    # India (default)
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
    logger.info(f">>> Header logo base64 starts with: {header_logo[:50] if header_logo else 'EMPTY'}...")
    
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
            <td style="width:150px; border:none; border-left:1px solid #999; padding:2px 2px 2px 10px; vertical-align:middle;">
                <p style="font-size:8px; color:#333; text-align:right; margin:0; padding:0;"><b>Phone:</b> +91 8866335159</p>
                <p style="font-size:8px; color:#333; text-align:right; margin:0; padding:0;"><b>Web:</b> vertexchemical.in</p>
            </td>
        </tr>
    </table>
</div>
'''


def _get_footer_html() -> str:
    """Generate footer HTML for PDF using xhtml2pdf pdf:template."""
    footer_logo = _get_logo_base64(_FOOTER_LOGO)
    logger.info(f">>> Footer logo base64 starts with: {footer_logo[:50] if footer_logo else 'EMPTY'}...")
    
    return f'''
<div id="footer_content" style="display:none;">
    <table style="width:100%; border:none; border-collapse:collapse; border-top:3px solid #333;">
        <tr>
            <td style="width:55px; border:none; padding:5px 2px 2px 2px; vertical-align:middle;">
                <img src="{footer_logo}" style="width:50px; height:auto;"/>
            </td>
            <td style="border:none; padding:5px 2px 2px 10px; vertical-align:middle;">
                <p style="font-size:7px; color:#555; margin:0; padding:0;">206/5, Signet Hub, Akshar Chowk, Vadodara-390020 &nbsp;|&nbsp; +91 99095 51658 &nbsp;|&nbsp; sales@vertexchemical.in</p>
            </td>
        </tr>
    </table>
</div>
'''


def _prepare_body_for_export(html: str) -> str:
    """Run body normalization steps that are independent of currency/local_export."""
    body = _restore_quotation_format(html)
    body = _strip_currency_row_from_quotation(body)
    body = _normalize_body(body)
    return body


def _ensure_dollar_prefix_in_export(html: str) -> str:
    """
    When export is selected, prepend $ to amount cells that have no currency symbol,
    so PDF shows e.g. '$9,250.00' instead of '9,250.00'. Only touches totals and items-table.
    """
    out = html
    # Totals table: Total Amount cell — if the value is just a number, prepend $
    out = re.sub(
        r"(Total\s+Amount\s*</td>\s*<td[^>]*>)(\s*)(?![\$₹]|Rs\.)(\d[\d,]*\.?\d*)",
        r"\1\2$\3",
        out,
        flags=re.IGNORECASE,
    )
    # Items table: Unit Price / Unit Amount columns — amounts like 185,000.00 or 9250.00 (no symbol)
    match = re.search(
        r'<table[^>]*class="[^"]*items-table[^"]*"[^>]*>(.*?)</table>',
        out,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        block = match.group(1)
        # Prepend $ to <td> that contains only a number (with optional commas and .xx) and no symbol
        new_block = re.sub(
            r"(<td[^>]*>)(\s*)(?![\$₹]|Rs\.)(\d[\d,]*\.\d{2})\s*</td>",
            r"\1\2$\3</td>",
            block,
        )
        out = out[: match.start(1)] + new_block + out[match.end(1) :]
    return out


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
        logger.info(f">>> [EXPORT] Currency: local_export={local_export!r} -> using Rs. (local)")
        return _replace_rupee_for_export(html)

    # EXPORT: convert rupee to $ and ensure $ appears where amounts have no symbol.
    logger.info(f">>> [EXPORT] Currency: local_export={local_export!r} -> using $ (export)")
    out = html.replace(RUPEESYM, "$")
    out = out.replace(RUPEESYM_ENTITY_DEC, "$")
    out = out.replace(RUPEESYM_ENTITY_HEX, "$")
    out = re.sub(r"\bRs\.?\s*", "$", out, flags=re.IGNORECASE)
    out = _ensure_dollar_prefix_in_export(out)
    return out


def _header_footer_tables(
    letterhead: Optional[str],
    header_logo: str,
    footer_logo: str,
) -> tuple[str, str]:
    """Build header and footer table HTML. Logo sizes and contact cell tuned to avoid truncation (e.g. website URL)."""
    logger.info(f">>> [EXPORT] _header_footer_tables letterhead={letterhead!r} header_logo_len={len(header_logo)} footer_logo_len={len(footer_logo)}")
    h_phone, h_web, footer_address, footer_mobile, footer_web = _header_footer_vars(letterhead)
    header_table = f'''<table class="hf-table">
<tr>
<td style="width:60px; padding:2px 4px; vertical-align:middle;">
<img src="{header_logo}" width="55" height="50"/>
</td>
<td style="padding:2px 8px; vertical-align:middle; text-align:left; line-height:1.25;">
<b style="font-size:11pt; color:#1a5276; line-height:1.25;">VERTEX CHEMICAL</b><br/>
<span style="font-size:5.5pt; color:#666; letter-spacing:0.3pt; line-height:1.25;">YOUR PARTNER FOR QUALITY CHEMICALS, GLOBALLY</span>
</td>
<td style="width:34%; padding:2px 8px; vertical-align:middle; text-align:right; border-left:1px solid #999 !important; word-wrap:break-word; overflow-wrap:break-word; white-space:normal; line-height:1.35;">
<span style="font-size:7pt; color:#333;"><b>Phone:</b> {h_phone}</span><br/>
<span style="font-size:7pt; color:#333;"><b>Web:</b> {h_web}</span>
</td>
</tr>
</table>
<hr class="hf-line hf-line-header"/>'''

    footer_table = f'''<hr class="hf-line hf-line-footer"/>
<table class="hf-table">
<tr>
<td style="width:45px; padding:3px 4px; vertical-align:middle;">
<img src="{footer_logo}" width="40" height="36"/>
</td>
<td style="width:33%; padding:3px 6px; vertical-align:middle; text-align:left; word-wrap:break-word; overflow-wrap:break-word;">
<p style="font-size:6pt; color:#555; margin:0; padding:0; line-height:1.3;">{footer_address}</p>
</td>
<td style="width:34%; padding:3px 6px; vertical-align:middle; text-align:center;">
<p style="font-size:6pt; color:#555; margin:0; padding:0; line-height:1.3;">{footer_mobile}</p>
</td>
<td style="width:33%; padding:3px 6px; vertical-align:middle; text-align:right; word-wrap:break-word; overflow-wrap:break-word;">
<p style="font-size:6pt; color:#555; margin:0; padding:0; line-height:1.3;">{footer_web}</p>
</td>
</tr>
</table>'''
    return header_table, footer_table


def wrap_html_for_export(
    body_html: str,
    include_header_footer: bool = False,
    letterhead: Optional[str] = None,
    prepared_body: Optional[str] = None,
) -> str:
    """
    Wrap TipTap/editor HTML in a full document with the export print CSS.
    Single source for both DOCX and PDF. Normalizes page-break divs.
    letterhead: "dubai" | "india" | None for chemical header/footer address and phone.
    prepared_body: if set, use this as body (already normalized + currency applied); skip _prepare_body and rupee replacement.
    """
    env_info = os.environ.get("ENV", "unknown")
    logger.info(
        f">>> [EXPORT] wrap_html_for_export include_header_footer={include_header_footer} letterhead={letterhead!r} "
        f"prepared_body={prepared_body is not None} env={env_info} cwd={os.getcwd()!r}"
    )
    if prepared_body is not None:
        body_html = prepared_body
        logger.info(f">>> [EXPORT] Using prepared_body length={len(body_html)}")
    else:
        body_html = _prepare_body_for_export(body_html)
        # For DOCX and generic HTML export we keep legacy behaviour: treat rupee as Rs.
        body_html = _replace_rupee_for_export(body_html)
        logger.info(f">>> [EXPORT] Body prepared (no prepared_body) length={len(body_html)}")

    if include_header_footer:
        logger.info(">>> [EXPORT] Including header and footer on EVERY page (xhtml2pdf path)")
        header_logo = _get_logo_base64(_HEADER_LOGO)
        footer_logo = _get_logo_base64(_FOOTER_LOGO)
        icon_location = _get_logo_base64(_ICON_LOCATION)
        icon_phone = _get_logo_base64(_ICON_PHONE)
        icon_email = _get_logo_base64(_ICON_EMAIL)

        logger.info(
            f">>> [EXPORT] Logos: header_len={len(header_logo)} footer_len={len(footer_logo)} "
            f"header_empty={not header_logo} footer_empty={not footer_logo}"
        )
        header_table, footer_table = _header_footer_tables(letterhead, header_logo, footer_logo)
        logger.info(f">>> [EXPORT] header_table len={len(header_table)} footer_table len={len(footer_table)}")

        # xhtml2pdf approach: use @page with static frames
        logger.info(">>> [EXPORT] Using xhtml2pdf static frame approach")
        
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
        left: 50pt; width: 495pt; top: 100pt; height: 680pt;
    }}
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
        
        logger.info(
            f">>> [EXPORT] Full HTML built: total_len={len(full_html)} body_len={len(body_html)} "
            f"has_header_content={'header_content' in full_html} has_footer_content={'footer_content' in full_html} "
            f"has_frame={'@frame' in full_html}"
        )
        # Log first 300 chars of style block to verify @page/@frame in production
        style_start = full_html.find("@page")
        if style_start != -1:
            logger.info(f">>> [EXPORT] @page block snippet: ...{full_html[style_start:style_start + 400]!r}...")
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


def _build_full_html_for_weasyprint(body_html: str, letterhead: Optional[str] = None) -> str:
    """
    Build full HTML for WeasyPrint with running header/footer so they appear on every page
    in @page margin boxes (no -pdf-frame-content; WeasyPrint uses position: running()).
    Avoids header/footer being rendered as large blocks in the main flow.
    """
    logger.info(f">>> [EXPORT] _build_full_html_for_weasyprint body_len={len(body_html)} letterhead={letterhead!r}")
    header_logo = _get_logo_base64(_HEADER_LOGO)
    footer_logo = _get_logo_base64(_FOOTER_LOGO)
    logger.info(f">>> [EXPORT] WeasyPrint logos: header_len={len(header_logo)} footer_len={len(footer_logo)}")
    header_table, footer_table = _header_footer_tables(letterhead, header_logo, footer_logo)
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
    """Apply print-layout normalization: Unicode sub/superscript, declaration spacing, then styles, page-breaks, tables."""
    html = _normalize_unicode_sub_superscript(html)
    html = _normalize_declaration_spacing(html)
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
        # Preserve class attribute if present
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


def html_to_pdf(html: str, letterhead: Optional[str] = None, local_export: Optional[str] = None) -> bytes:
    """
    Generate PDF from TipTap HTML. Prefer WeasyPrint; fallback to xhtml2pdf.
    A4, fixed margins, stable tables, page-break control.
    Includes header and footer on every page.
    letterhead: "dubai" | "india" | None.
    local_export: "local" | "export" for currency normalization (Rs vs $).
    """
    env_info = os.environ.get("ENV", "unknown")
    logger.info(
        f">>> [EXPORT] html_to_pdf entry letterhead={letterhead!r} local_export={local_export!r} "
        f"env={env_info} input_html_len={len(html)}"
    )
    body_html = _prepare_body_for_export(html)
    logger.info(f">>> [EXPORT] After prepare body_html len={len(body_html)}")
    body_html = _normalize_currency_for_export(body_html, local_export)
    logger.info(f">>> [EXPORT] After currency body_html len={len(body_html)} (export=$ local=Rs)")

    full_html_weasy = _build_full_html_for_weasyprint(body_html, letterhead)
    logger.info(f">>> [EXPORT] WeasyPrint full_html len={len(full_html_weasy)} attempting WeasyPrint...")
    pdf_bytes: Optional[bytes] = _pdf_weasyprint(full_html_weasy)
    if pdf_bytes is not None:
        logger.info(f">>> [EXPORT] PDF generated using WeasyPrint size={len(pdf_bytes)}")
        return pdf_bytes
    logger.info(">>> [EXPORT] WeasyPrint failed, falling back to xhtml2pdf (using same body with correct currency)")
    full_html = wrap_html_for_export(
        html, include_header_footer=True, letterhead=letterhead, prepared_body=body_html
    )
    logger.info(f">>> [EXPORT] xhtml2pdf full_html len={len(full_html)}")
    return _pdf_xhtml2pdf(full_html)


def _pdf_weasyprint(html: str) -> Optional[bytes]:
    """Use WeasyPrint if available (best quality). Returns None on failure."""
    try:
        from weasyprint import HTML
        logger.info(">>> [EXPORT] WeasyPrint imported successfully")

        out = io.BytesIO()
        HTML(string=html).write_pdf(out)
        result = out.getvalue()
        logger.info(f">>> [EXPORT] WeasyPrint PDF generated successfully size={len(result)}")
        return result
    except Exception as e:
        logger.warning(
            f">>> [EXPORT] WeasyPrint failed: type={type(e).__name__} msg={e!r}",
            exc_info=True,
        )
        return None


def _pdf_xhtml2pdf(html: str) -> bytes:
    """Fallback: xhtml2pdf (pure Python, no system libs). Works on Render free tier."""
    from xhtml2pdf import pisa
    logger.info(f">>> [EXPORT] xhtml2pdf input html_len={len(html)} has_header={'header_content' in html} has_footer={'footer_content' in html}")

    out = io.BytesIO()
    err = pisa.CreatePDF(html, dest=out, encoding="utf-8")
    if err.err:
        logger.error(f">>> [EXPORT] xhtml2pdf error: {err.err}")
        raise RuntimeError("PDF generation failed")
    pdf_size = len(out.getvalue())
    logger.info(f">>> [EXPORT] xhtml2pdf PDF generated successfully size={pdf_size}")
    return out.getvalue()
