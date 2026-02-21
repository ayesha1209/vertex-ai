"""
Print-layout for DOCX and PDF export.
Export-quality, corporate style: A4 portrait, clear hierarchy, compact one-page invoice.
Single source of truth for typography, spacing, and table design.
"""

# Font hierarchy: Main 18–20px, Section 13–14px, Labels 11px semi-bold, Values 11px regular
# Using pt for print: 18–20px ≈ 14–15pt, 13–14px ≈ 10–11pt, 11px ≈ 8.5pt
EXPORT_PRINT_CSS = """
  @page {
    size: A4 portrait;
    margin: 1.25cm;
  }
  * {
    box-sizing: border-box;
  }
  body {
    font-family: Inter, "Helvetica Neue", Helvetica, Arial, sans-serif !important;
    font-size: 11px !important;
    line-height: 1.35 !important;
    color: #1a1a1a !important;
    margin: 0 !important;
    padding: 0 !important;
    max-width: 100% !important;
    overflow-x: hidden !important;
  }
  /* Main document title (TDS, COA, MSDS) */
  h1 {
    font-size: 18px !important;
    font-weight: bold !important;
    margin: 0 0 10px 0 !important;
    line-height: 1.2 !important;
    text-align: center !important;
    letter-spacing: 0.02em !important;
    page-break-after: avoid !important;
  }
  h2 {
    font-size: 13px !important;
    font-weight: bold !important;
    margin: 8px 0 4px 0 !important;
    line-height: 1.25 !important;
    letter-spacing: 0.02em !important;
    page-break-after: avoid !important;
  }
  h3 {
    font-size: 12px !important;
    font-weight: bold !important;
    margin: 6px 0 3px 0 !important;
    line-height: 1.25 !important;
    page-break-after: avoid !important;
  }
  h4, h5, h6 {
    font-size: 11px !important;
    font-weight: bold !important;
    margin: 4px 0 2px 0 !important;
    line-height: 1.3 !important;
    page-break-after: avoid !important;
  }
  p {
    font-size: 11px !important;
    margin: 2px 0 4px 0 !important;
    line-height: 1.35 !important;
  }
  p:first-child { margin-top: 0 !important; }
  ul, ol {
    font-size: 11px !important;
    margin: 4px 0 6px 0 !important;
    padding-left: 1.25em !important;
  }
  li { margin: 1px 0 !important; line-height: 1.35 !important; }
  strong, b, .doc-label { font-weight: 600 !important; }
  sub { font-size: 0.75em !important; line-height: 0 !important; vertical-align: sub !important; }
  sup { font-size: 0.75em !important; line-height: 0 !important; vertical-align: super !important; }

  /* Global table: fixed layout so columns don't overflow; content wraps inside cells */
  table {
    border-collapse: collapse !important;
    table-layout: fixed !important;
    width: 100% !important;
    max-width: 100% !important;
    margin: 6px 0 !important;
    font-size: 11px !important;
    line-height: 1.3 !important;
    page-break-inside: auto !important;
    border: 1px solid #d0d0d0 !important;
  }
  tr { page-break-inside: avoid !important; }
  th, td {
    border: 1px solid #d0d0d0 !important;
    padding: 5px 8px !important;
    font-size: 11px !important;
    line-height: 1.3 !important;
    text-align: left !important;
    vertical-align: top !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    word-break: break-word !important;
    max-width: 100% !important;
    min-width: 0 !important;
  }
  th {
    font-weight: 600 !important;
    background: #f0f0f0 !important;
  }
  hr {
    border: none !important;
    border-top: 1px solid #d0d0d0 !important;
    margin: 8px 0 !important;
  }
  .page-break { page-break-after: always !important; }
  /* COA: keep on one page; conclusion (For: / Quality Control / Authorized Signatory) with table */
  .coa-section {
    font-size: 11px !important;
  }
  .coa-section h1 { margin: 0 0 6px 0 !important; }
  .coa-section h2 { margin: 6px 0 3px 0 !important; }
  .coa-section table { margin: 4px 0 !important; }
  .coa-section hr { margin: 4px 0 !important; }
  .coa-conclusion {
    page-break-inside: avoid !important;
    page-break-before: avoid !important;
    break-inside: avoid !important;
    margin-top: 4px !important;
    margin-bottom: 0 !important;
  }
  .coa-conclusion p {
    margin: 0 0 2px 0 !important;
    font-size: 10px !important;
    line-height: 1.3 !important;
  }
  .section-block {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
    orphans: 3 !important;
    widows: 2 !important;
  }
  .section-block h3, .section-block h2 { page-break-after: avoid !important; }
  p, li { orphans: 2 !important; widows: 2 !important; }

  /* ========== QUOTATION – one page, compact ========== */
  .quotation-page {
    font-size: 11px !important;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1.3 !important;
    page-break-inside: avoid !important;
    max-width: 100%;
  }
  /* Header block: title + quotation meta */
  .quotation-page h1 {
    font-size: 18px !important;
    font-weight: bold !important;
    margin: 0 0 8px 0 !important;
    text-align: center !important;
    letter-spacing: 0.03em !important;
  }
  .quotation-page h2 {
    font-size: 13px !important;
    font-weight: bold !important;
    margin: 6px 0 3px 0 !important;
  }
  .quotation-page .invoice-meta {
    margin-bottom: 6px !important;
    border: 1px solid #d0d0d0 !important;
    border-radius: 2px !important;
  }
  .quotation-page .invoice-parties {
    display: table !important;
    width: 100% !important;
    table-layout: fixed !important;
    margin: 6px 0 !important;
    border: 1px solid #d0d0d0 !important;
    border-radius: 2px !important;
  }
  .quotation-page .invoice-terms {
    margin: 6px 0 !important;
    border: 1px solid #d0d0d0 !important;
    border-radius: 2px !important;
  }
  .quotation-page .invoice-items {
    margin: 6px 0 !important;
    border: 1px solid #d0d0d0 !important;
    border-radius: 2px !important;
  }
  .quotation-page .invoice-items th {
    background: #e8e8e8 !important;
  }
  .quotation-page .invoice-items td.numeric,
  .quotation-page .invoice-items th.numeric {
    text-align: right !important;
  }
  .quotation-page .invoice-totals {
    margin: 6px 0 !important;
    border: 1px solid #d0d0d0 !important;
    border-radius: 2px !important;
  }
  .quotation-page .invoice-totals td:first-child {
    font-weight: 600 !important;
  }
  .quotation-page .invoice-totals tr:last-child td {
    border-bottom: 1px solid #d0d0d0 !important;
  }
  .quotation-page .invoice-bank {
    margin: 6px 0 !important;
    border: 1px solid #d0d0d0 !important;
    border-radius: 2px !important;
  }
  /* Signature block: stacked label/value (no table) — avoids any PDF table overflow */
  .quotation-page .invoice-signature-block {
    margin-top: 8px !important;
    padding: 8px 10px !important;
    border: 1px solid #d0d0d0 !important;
    border-radius: 2px !important;
    max-width: 100% !important;
  }
  .quotation-page .invoice-sig-row {
    margin-bottom: 6px !important;
  }
  .quotation-page .invoice-sig-row:last-child { margin-bottom: 0 !important; }
  .quotation-page .invoice-sig-label {
    font-weight: 600 !important;
    font-size: 11px !important;
    margin: 0 0 1px 0 !important;
  }
  .quotation-page .invoice-sig-value {
    font-size: 11px !important;
    line-height: 1.35 !important;
    margin: 0 0 4px 0 !important;
    max-width: 100% !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
  }
  .quotation-page .invoice-sig-declaration {
    margin: 0 !important;
    line-height: 1.4 !important;
  }
  .quotation-page table {
    margin: 0 !important;
    font-size: 11px !important;
    border: none !important;
    table-layout: fixed !important;
    max-width: 100% !important;
  }
  .quotation-page th,
  .quotation-page td {
    padding: 4px 6px !important;
    font-size: 11px !important;
    border: 1px solid #d0d0d0 !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
    word-break: break-word !important;
    max-width: 100% !important;
    min-width: 0 !important;
  }
  /* Label-value tables: narrow label column so value column wraps inside page */
  .quotation-page table.label-value col:nth-child(1) { width: 28% !important; }
  .quotation-page table.label-value col:nth-child(2) { width: 72% !important; }
  .quotation-page th {
    background: #f0f0f0 !important;
    font-weight: 600 !important;
  }
  .quotation-page td[data-label="true"] {
    font-weight: 600 !important;
  }
  .quotation-page p {
    margin: 2px 0 3px 0 !important;
    font-size: 11px !important;
  }
  .ProseMirror, .tiptap {
    font-size: inherit !important;
    margin: 0 !important;
    padding: 0 !important;
  }
"""
