"""
Professional PDF/DOCX formatting: we control layout. AI gives content; we render it.
Builds print-ready HTML with inline styles (xhtml2pdf-safe) and clear structure.
"""

import re


# Inline styles (xhtml2pdf-safe): export-quality, light borders, compact
STYLE_TABLE = "border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 11px; border: 1px solid #d0d0d0;"
STYLE_TH = "border: 1px solid #d0d0d0; padding: 5px 8px; text-align: left; font-weight: 600; background: #f0f0f0; vertical-align: top;"
STYLE_TD = "border: 1px solid #d0d0d0; padding: 5px 8px; text-align: left; vertical-align: top;"
STYLE_HR = "border: none; border-top: 1px solid #d0d0d0; margin: 8px 0;"
STYLE_H1 = "font-size: 18px; font-weight: bold; margin: 0 0 10px 0; text-align: center; page-break-after: avoid;"
STYLE_H2 = "font-size: 13px; font-weight: bold; margin: 8px 0 4px 0; page-break-after: avoid;"
STYLE_P = "margin: 2px 0 4px 0; line-height: 1.35; font-size: 11px;"
STYLE_P_BOLD = "margin: 2px 0 4px 0; font-weight: 600; line-height: 1.35; font-size: 11px;"
STYLE_UL = "margin: 4px 0 6px 0; padding-left: 1.25em;"
STYLE_LI = "margin: 1px 0; line-height: 1.35;"
STYLE_PAGE_BREAK = "page-break-after: always;"
STYLE_SECTION = "margin-bottom: 12px;"


def _wrap_print_document(body_html: str) -> str:
    """Wrap body in full HTML with print-optimized CSS (A4, export-quality)."""
    return f"""<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta charset="UTF-8"/>
<style type="text/css">
  @page {{ size: A4 portrait; margin: 1.25cm; }}
  body {{
    font-family: Inter, "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 11px;
    line-height: 1.35;
    color: #1a1a1a;
    margin: 0;
    padding: 0;
  }}
  table {{ border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 11px; border: 1px solid #d0d0d0; }}
  th, td {{ border: 1px solid #d0d0d0; padding: 5px 8px; text-align: left; vertical-align: top; }}
  th {{ font-weight: 600; background: #f0f0f0; }}
  h1 {{ font-size: 18px; font-weight: bold; margin: 0 0 10px 0; text-align: center; page-break-after: avoid; }}
  h2 {{ font-size: 13px; font-weight: bold; margin: 8px 0 4px 0; page-break-after: avoid; }}
  p {{ margin: 2px 0 4px 0; line-height: 1.35; font-size: 11px; }}
  ul {{ margin: 4px 0 6px 0; padding-left: 1.25em; }}
  li {{ margin: 1px 0; line-height: 1.35; }}
  hr {{ border: none; border-top: 1px solid #d0d0d0; margin: 8px 0; }}
  .page-break {{ page-break-after: always; }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""


def _ensure_inline_styles(html: str) -> str:
    """Ensure tables have inline styles; preserve existing class for quotation blocks."""
    def add_style(match: re.Match) -> str:
        full = match.group(0)
        if 'style="' in full.lower():
            return full
        # Insert style after <table (preserve class and other attrs)
        return full.replace("<table", f'<table style="{STYLE_TABLE}"', 1)
    html = re.sub(r"<table(?:\s+[^>]*)?>", add_style, html, flags=re.IGNORECASE)
    return html


def normalize_body_for_pdf(body_html: str) -> str:
    """
    Normalize document HTML for best PDF/DOCX output.
    Ensures page-break divs and tables have inline styles.
    """
    body_html = re.sub(
        r'<div\s+style="page-break-after:\s*always;?\s*"></div>',
        f'<div style="{STYLE_PAGE_BREAK}"></div>',
        body_html,
        flags=re.IGNORECASE,
    )
    body_html = _ensure_inline_styles(body_html)
    return body_html


def build_print_ready_html(body_html: str) -> str:
    """Build full print-ready HTML for PDF or DOCX. We control formatting."""
    body_html = normalize_body_for_pdf(body_html)
    return _wrap_print_document(body_html)
