"""
Production document export: TipTap HTML → DOCX and HTML → PDF.
Single source of truth: same HTML input for both; no DOCX→PDF conversion.
Uses only pip-installable libs; Render-free-tier compatible.
"""

from app.services.export.service import (
    html_to_docx,
    html_to_pdf,
    wrap_html_for_export,
)

__all__ = ["html_to_docx", "html_to_pdf", "wrap_html_for_export"]
