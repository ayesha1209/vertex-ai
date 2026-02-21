"""
Export service: wrap TipTap HTML with print CSS and generate DOCX/PDF.
HTML → DOCX and HTML → PDF independently (no DOCX→PDF).
"""

import base64
import io
import logging
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
    logger.info(f">>> Loading logo from: {path}")
    if not path.exists():
        logger.warning(f">>> Logo file NOT FOUND: {path}")
        return ""
    try:
        with open(path, "rb") as f:
            data = f.read()
        ext = path.suffix.lower().replace(".", "")
        if ext == "jpg":
            ext = "jpeg"
        result = f"data:image/{ext};base64,{base64.b64encode(data).decode()}"
        logger.info(f">>> Logo loaded successfully, base64 length: {len(result)}")
        return result
    except Exception as e:
        logger.error(f">>> Error loading logo: {e}")
        return ""


# Inline table style when style attr is missing (xhtml2pdf fallback).
# Match print_css: light borders, compact, export-quality.
_TABLE_INLINE = (
    "border-collapse: collapse; table-layout: fixed; width: 100%; "
    "margin: 6px 0; font-size: 11px; border: 1px solid #d0d0d0;"
)
_PAGE_BREAK_INLINE = "page-break-after: always;"

# Unicode subscript/superscript digits often render as black boxes in PDF (font lacks glyphs).
# Replace with HTML <sub>/<sup> so the engine uses normal digits in subscript/superscript position.
_SUBSCRIPT_DIGITS = "\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089"  # ₀₁₂₃₄₅₆₇₈₉
_SUPERSCRIPT_DIGITS = "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"  # ⁰¹²³⁴⁵⁶⁷⁸⁹


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


def wrap_html_for_export(body_html: str, include_header_footer: bool = False) -> str:
    """
    Wrap TipTap/editor HTML in a full document with the export print CSS.
    Single source for both DOCX and PDF. Normalizes page-break divs.
    """
    logger.info(f">>> wrap_html_for_export called, include_header_footer={include_header_footer}")
    body_html = _normalize_body(body_html)
    
    if include_header_footer:
        logger.info(">>> Including header and footer on EVERY page")
        header_logo = _get_logo_base64(_HEADER_LOGO)
        footer_logo = _get_logo_base64(_FOOTER_LOGO)
        icon_location = _get_logo_base64(_ICON_LOCATION)
        icon_phone = _get_logo_base64(_ICON_PHONE)
        icon_email = _get_logo_base64(_ICON_EMAIL)
        
        logger.info(f">>> Header logo loaded: {len(header_logo)} chars")
        logger.info(f">>> Footer logo loaded: {len(footer_logo)} chars")
        
        # xhtml2pdf approach: use @page with static frames
        # The key is to define frames in CSS and reference content by id
        
        header_table = f'''<table class="hf-table" style="width:100%; border:none !important; border-collapse:collapse; background:none !important;">
<tr style="border:none !important; background:none !important;">
<td style="width:65px; padding:2px; vertical-align:middle; border:none !important; background:none !important;">
<img src="{header_logo}" width="55"/>
</td>
<td style="padding:2px 8px; vertical-align:middle; text-align:left; border:none !important; background:none !important;">
<b style="font-size:14px; color:#1a5276;">VERTEX CHEMICAL</b><br/>
<span style="font-size:7px; color:#666;">YOUR PARTNER FOR QUALITY CHEMICALS, GLOBALLY</span>
</td>
<td style="width:145px; border:none !important; border-left:1px solid #999 !important; padding:2px 2px 2px 10px; vertical-align:middle; text-align:right; background:none !important;">
<span style="font-size:8px; color:#333;"><b>Phone:</b> +91 8866335159</span><br/>
<span style="font-size:8px; color:#333;"><b>Web:</b> vertexchemical.in</span>
</td>
</tr>
</table>
<hr class="hf-line" style="border:none; border-bottom:2px solid #333; margin:3px 0 0 0; padding:0;"/>'''

        footer_table = f'''<hr class="hf-line" style="border:none; border-top:2px solid #333; margin:0 0 3px 0; padding:0;"/>
<table class="hf-table" style="width:100%; border:none !important; border-collapse:collapse; background:none !important;">
<tr style="border:none !important; background:none !important;">
<td style="width:45px; padding:2px; vertical-align:middle; border:none !important; background:none !important;">
<img src="{footer_logo}" width="40"/>
</td>
<td style="padding:2px 8px; vertical-align:middle; text-align:left; border:none !important; background:none !important;">
<img src="{icon_location}" width="12" height="12" style="vertical-align:middle;"/> <span style="font-size:8px; color:#555;">206/5, Signet Hub, Akshar Chowk, Vadodara-390020</span>
</td>
<td style="padding:2px 8px; vertical-align:middle; text-align:center; border:none !important; background:none !important;">
<img src="{icon_phone}" width="12" height="12" style="vertical-align:middle;"/>&nbsp;&nbsp;<span style="font-size:8px; color:#555;">+91 99095 51658</span>
</td>
<td style="padding:2px 8px; vertical-align:middle; text-align:right; border:none !important; background:none !important;">
<img src="{icon_email}" width="12" height="12" style="vertical-align:middle;"/>&nbsp;&nbsp;<span style="font-size:8px; color:#555;">sales@vertexchemical.in</span>
</td>
</tr>
</table>'''

        logger.info(">>> Using xhtml2pdf static frame approach")
        
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
        
        logger.info(f">>> Full HTML length: {len(full_html)}")
        logger.info(f">>> HTML contains 'header_content': {'header_content' in full_html}")
        logger.info(f">>> HTML contains 'footer_content': {'footer_content' in full_html}")
        logger.info(f">>> HTML contains '@frame': {'@frame' in full_html}")
        
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


def html_to_pdf(html: str) -> bytes:
    """
    Generate PDF from TipTap HTML. Prefer WeasyPrint; fallback to xhtml2pdf.
    A4, fixed margins, stable tables, page-break control.
    Includes header and footer on every page.
    """
    logger.info(">>> html_to_pdf called")
    full_html = wrap_html_for_export(html, include_header_footer=True)
    
    pdf_bytes: Optional[bytes] = _pdf_weasyprint(full_html)
    if pdf_bytes is not None:
        logger.info(">>> PDF generated using WeasyPrint")
        return pdf_bytes
    logger.info(">>> WeasyPrint failed, using xhtml2pdf")
    return _pdf_xhtml2pdf(full_html)


def _pdf_weasyprint(html: str) -> Optional[bytes]:
    """Use WeasyPrint if available (best quality). Returns None on failure."""
    try:
        from weasyprint import HTML
        logger.info(">>> WeasyPrint imported successfully")

        out = io.BytesIO()
        HTML(string=html).write_pdf(out)
        logger.info(">>> WeasyPrint PDF generated successfully")
        return out.getvalue()
    except Exception as e:
        logger.warning(f">>> WeasyPrint failed: {e}")
        return None


def _pdf_xhtml2pdf(html: str) -> bytes:
    """Fallback: xhtml2pdf (pure Python, no system libs). Works on Render free tier."""
    from xhtml2pdf import pisa
    logger.info(">>> Using xhtml2pdf for PDF generation")

    out = io.BytesIO()
    err = pisa.CreatePDF(html, dest=out, encoding="utf-8")
    if err.err:
        logger.error(f">>> xhtml2pdf error: {err.err}")
        raise RuntimeError("PDF generation failed")
    logger.info(">>> xhtml2pdf PDF generated successfully")
    return out.getvalue()
