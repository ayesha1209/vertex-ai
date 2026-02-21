# Document Export Architecture

## Single source of truth

- **TipTap HTML** is the only source for export. Stored in MongoDB as `html_content`.
- **No DOCX → PDF conversion.** Both are generated independently:
  - **HTML → DOCX** (html2docx)
  - **HTML → PDF** (WeasyPrint, fallback xhtml2pdf)

Same HTML input → consistent layout and content in both formats.

## Pipeline

1. **Wrap:** `wrap_html_for_export(html)` wraps body HTML in a full document with the **print CSS** (`app/services/export/print_css.py`).
2. **Normalize:** Page-break divs and tables get stable inline styles for engines that need them (e.g. xhtml2pdf).
3. **DOCX:** `html_to_docx(html, title)` → full HTML → html2docx → bytes.
4. **PDF:** `html_to_pdf(html)` → full HTML → WeasyPrint (or xhtml2pdf) → bytes.

## Print CSS (normalization layer)

In `print_css.py` we define a **single print-layout normalization** so DOCX and PDF look consistent and professional:

- **Font hierarchy:** body 10pt, h1 14pt, h2 11.5pt, h3 10.5pt, h4–h6 10pt; all headings bold with compact margins.
- **Spacing:** Tight, consistent vertical rhythm (e.g. p margin 0.25em 0 0.4em, lists 0.3em 0).
- **Tables:** Dense layout – 9.5pt font, 4px 6px cell padding, 1px borders, 6px margin; `table-layout: fixed`, `page-break-inside: avoid` on rows.
- **Override editor styling:** Rules use `!important` so TipTap inline font-size/margin don’t override. Export service also strips inline `font-size`, `margin`, `padding`, `line-height` from body content so the stylesheet fully controls typography and spacing.

This gives consistent font scale, heading hierarchy, and table density in both formats.

## FastAPI

- `GET /api/documents/{id}/download.docx` – returns DOCX file (Content-Disposition: attachment).
- `GET /api/documents/{id}/download.pdf` – returns PDF file (attachment).

Both use the same `html_content` and the same export service; no shared state between the two calls.

## Dependencies (pip only, Render free tier)

| Use        | Library     | Notes                                      |
|-----------|-------------|--------------------------------------------|
| HTML→DOCX | html2docx   | Pure Python, no system binaries            |
| HTML→PDF  | WeasyPrint  | Best quality; may need cairo/pango on host |
| Fallback  | xhtml2pdf   | Pure Python; used if WeasyPrint unavailable |

If `pip install weasyprint` fails (e.g. missing system libs), remove it from `requirements.txt`; the app will use xhtml2pdf only.

## Performance

- No external document APIs; all work in-process.
- WeasyPrint/xhtml2pdf run in the request thread; for very large documents consider a background job and polling.
- Keep HTML reasonable in size (e.g. limit embedded images or link them by URL).

## OpenAI usage

- AI should output **structured content** (or plain text with markers/tables), not layout HTML.
- The app converts that content to HTML (e.g. via `response_parser.text_to_html`) and stores it. Export then uses that stored HTML only. This keeps token usage lower and layout under our control.
