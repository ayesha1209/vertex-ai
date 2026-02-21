"""
Export service: wrap TipTap HTML with print CSS and generate DOCX/PDF.
HTML → DOCX and HTML → PDF independently (no DOCX→PDF).
"""

import io
import re
from re import Match
from typing import Optional

from app.services.export.print_css import EXPORT_PRINT_CSS

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


def wrap_html_for_export(body_html: str) -> str:
    """
    Wrap TipTap/editor HTML in a full document with the export print CSS.
    Single source for both DOCX and PDF. Normalizes page-break divs.
    """
    body_html = _normalize_body(body_html)
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
        return f'<table style="{_TABLE_INLINE}" {rest}>'.replace("  ", " ").strip()
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
    """
    full_html = wrap_html_for_export(html)
    pdf_bytes: Optional[bytes] = _pdf_weasyprint(full_html)
    if pdf_bytes is not None:
        return pdf_bytes
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
