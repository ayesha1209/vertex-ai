"""
Print-layout for DOCX and PDF export.
Export-quality, corporate style: A4 portrait, clear hierarchy, compact one-page invoice.
Single source of truth for typography, spacing, and table design.
"""

EXPORT_PRINT_CSS = """
  @page {
    size: A4 portrait;
    margin: 1cm;
  }
  * {
    box-sizing: border-box;
  }
  body {
    /* DejaVu Sans / Liberation Sans support ₹ (rupee); fallback to Arial */
    font-family: "DejaVu Sans", "Liberation Sans", Arial, Helvetica, sans-serif !important;
    font-size: 11px !important;
    line-height: 1.35 !important;
    color: #1a1a1a !important;
    margin: 0 !important;
    padding: 0 !important;
    max-width: 100% !important;
  }
  h1 {
    font-size: 16px !important;
    font-weight: bold !important;
    margin: 0 0 10px 0 !important;
    line-height: 1.2 !important;
    text-align: center !important;
  }
  h2 {
    font-size: 12px !important;
    font-weight: bold !important;
    margin: 8px 0 4px 0 !important;
    line-height: 1.25 !important;
  }
  h3 {
    font-size: 11px !important;
    font-weight: bold !important;
    margin: 6px 0 3px 0 !important;
    line-height: 1.25 !important;
  }
  .section-heading {
    font-size: 12px !important;
    font-weight: bold !important;
    margin: 8px 0 4px 0 !important;
    line-height: 1.25 !important;
  }
  p {
    font-size: 10px !important;
    margin: 2px 0 !important;
    line-height: 1.35 !important;
  }
  ul, ol {
    font-size: 10px !important;
    margin: 3px 0 !important;
    padding-left: 1.2em !important;
  }
  li {
    margin: 2px 0 !important;
    line-height: 1.35 !important;
  }
  strong, b {
    font-weight: 600 !important;
  }
  
  /* Tables */
  table {
    border-collapse: collapse !important;
    width: 100% !important;
    max-width: 100% !important;
    margin: 5px 0 !important;
    font-size: 10px !important;
    line-height: 1.3 !important;
  }
  th, td {
    border: 1px solid #333 !important;
    padding: 4px 6px !important;
    font-size: 10px !important;
    line-height: 1.3 !important;
    text-align: left !important;
    vertical-align: top !important;
    word-wrap: break-word !important;
    overflow-wrap: break-word !important;
  }
  /* Default backgrounds - inline styles will override */
  td {
    background: white;
    background-color: white;
  }
  th {
    font-weight: bold;
    background: #BBBBBB;
    background-color: #BBBBBB;
  }
  b, strong {
    font-weight: bold !important;
  }
  hr {
    border: none !important;
    border-top: 1px solid #333 !important;
    margin: 8px 0 !important;
  }
  
  .page-break {
    page-break-after: always !important;
  }
  
  /* COA section */
  .coa-section {
    font-size: 11px !important;
  }
  .coa-conclusion {
    page-break-inside: avoid !important;
    margin-top: 6px !important;
  }
  .section-block {
    page-break-inside: avoid !important;
  }
  
  /* Quotation page wrapper */
  .quotation-page {
    font-size: 10px !important;
    line-height: 1.2 !important;
  }
  .quotation-page h1 {
    font-size: 16px !important;
    margin: 0 0 4px 0 !important;
  }
  .quotation-page table {
    margin: 4px 0 !important;
    width: 100% !important;
  }
  .quotation-page th,
  .quotation-page td {
    padding: 3px 5px !important;
    font-size: 10px !important;
  }
  /* Quotation tables - inline styles control backgrounds */
  .quotation-page td {
    background-color: #ffffff;
  }
  .quotation-page th {
    background: #BBBBBB;
    background-color: #BBBBBB;
    font-weight: bold;
  }
  .quotation-page p {
    font-size: 9px !important;
    margin: 1px 0 !important;
    line-height: 1.2 !important;
  }
  /* Terms and conditions - larger font */
  .terms-section {
    font-size: 10px !important;
  }
  .terms-section p {
    font-size: 10px !important;
    margin: 2px 0 !important;
    line-height: 1.3 !important;
  }
  /* ── Items table ── */
  .items-table {
    table-layout: fixed !important;
  }
  .items-table td:nth-child(1),
  .items-table th:nth-child(1) {
    width: 6% !important;
    white-space: nowrap !important;
  }
  .items-table td:nth-child(2),
  .items-table th:nth-child(2) {
    width: 40% !important;
  }
  .items-table td:nth-child(3),
  .items-table th:nth-child(3) {
    width: 14% !important;
    text-align: right !important;
  }
  .items-table td:nth-child(4),
  .items-table th:nth-child(4) {
    width: 20% !important;
    text-align: right !important;
  }
  .items-table td:nth-child(5),
  .items-table th:nth-child(5) {
    width: 20% !important;
    text-align: right !important;
  }
  .items-table tr:first-child td,
  .items-table thead td,
  .items-table thead th {
    background: #BBBBBB !important;
    background-color: #BBBBBB !important;
    font-weight: bold !important;
  }
  /* ── Totals table ── */
  .totals-table td:first-child {
    font-weight: bold !important;
  }
  .totals-table td:last-child {
    text-align: right !important;
    font-weight: bold !important;
  }
  /* ── Customer table: label columns (1st, 3rd) ── */
  .customer-table td:nth-child(odd) {
    font-weight: bold !important;
    background: #BBBBBB !important;
    background-color: #BBBBBB !important;
  }
  .customer-table td:nth-child(even) {
    background: #ffffff !important;
    background-color: #ffffff !important;
  }
  /* ── Delivery table: label columns (1st, 3rd) ── */
  .delivery-table td:nth-child(odd) {
    font-weight: bold !important;
    background: #BBBBBB !important;
    background-color: #BBBBBB !important;
  }
  .delivery-table td:nth-child(even) {
    background: #ffffff !important;
    background-color: #ffffff !important;
  }
  /* Terms + signatory: allow flow; no extra space before block */
  .terms-sig-wrapper {
    page-break-before: avoid !important;
    margin-top: 0 !important;
    padding-top: 0 !important;
  }
  .signatory-block {
    page-break-before: avoid !important;
  }
  .terms-sig-table,
  .terms-sig-table tr,
  .terms-sig-table td,
  .terms-sig-table th,
  .quotation-page .terms-sig-table,
  .quotation-page .terms-sig-table tr,
  .quotation-page .terms-sig-table td,
  .quotation-page .terms-sig-table th {
    border: none !important;
    border-width: 0 !important;
    border-style: none !important;
    background: none !important;
    background-color: transparent !important;
  }
  .terms-sig-table {
    page-break-inside: avoid !important;
    margin-left: 0 !important;
    margin-right: 0 !important;
  }
  .terms-sig-table td,
  .quotation-page .terms-sig-table td {
    padding: 0 !important;
  }
  .terms-sig-table td:first-child {
    padding-left: 0 !important;
    padding-right: 12px !important;
  }
  .terms-sig-table td:last-child {
    padding: 0 !important;
  }
  .terms-sig-table .terms-left-col {
    padding-left: 0 !important;
    margin-left: 0 !important;
  }
  .terms-section p {
    display: block !important;
  }
"""
