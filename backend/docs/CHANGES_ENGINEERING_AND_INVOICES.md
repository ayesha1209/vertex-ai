# Engineering Quotation/TDS Rework + Commercial/Tax Invoice Support

Session changelog covering three related pieces of work. Scope: **engineering**
document generation and **invoice-family** documents only. Chemical
Quotation/COA/TDS/MSDS/Proforma Invoice (`vertex_prompts.py`,
`reference_structures.py`, `reference_templates_generated.py`) were **not**
touched.

## 1. Bug fix — AI generation was completely broken

**File:** `backend/app/services/document_generation/openai_client.py`

The app is configured for `OPENAI_MODEL=gpt-5-mini-2025-08-07`, but every call
passed `temperature=0.3`. GPT-5 models only support the default temperature
(1) and reject any other value, so **every** document generation call
(chemical and engineering alike) failed with:

```
openai.BadRequestError: Unsupported value: 'temperature' does not support 0.3
with this model. Only the default (1) value is supported.
```

Fix: `complete()` now tries the requested temperature first, and on a
`BadRequestError` whose message mentions `temperature`, retries the same
call without the parameter. No behavior change for models that do support
custom temperature.

## 2. Engineering Quotation + Technical Data Sheet rework

**Files:** `backend/app/prompts/engineering_prompts.py` (primary),
`backend/app/services/document_generation/response_parser.py` (1-line),
`backend/app/services/document_generation/assembler.py` (1-line),
`frontend/src/routes/DocumentsListPage.tsx` (copy fix)

### Why

The engineering template (`ENGINEERING_QUOTATION_REFERENCE`,
`ENGINEERING_TDS_CONTENT_GUIDE`) was a straight copy of the chemical
template with "Vertex Engineering" branding swapped in, never adapted to how
real Vertex Engineering quotations actually look. Compared against 4 real
sample quotations in `docs/Merged Quotation.pdf`:

- Real quotes use a plain **Buyer / Seller / Price Basis / Payment Terms /
  Delivery Time / Quotation Validity / Currency** header — never GST, Ship To,
  or a Bank Details box.
- Real Technical Data Sheets are **`Parameter | Specification` tables**
  (grouped into categories like Electrical/Mechanical/Environmental/Standards
  for complex products), plus Key Features and Typical Applications bullet
  lists — not the loose bullet-point "Technical Description" prose the app
  was generating.
- Only the motors/heavy-freight sample includes a Weight & Volume section;
  the other 3 (relays, PLCs, breakers) don't. The app forced it on every
  quotation regardless of product size.
- None of the (USD/export) samples show an "Amount in Words" line — that's
  an India/GST-invoice convention.

### What changed

**`ENGINEERING_QUOTATION_REFERENCE`**
- Header block rewritten: `Buyer | Seller | Price Basis | Payment Terms |
  Delivery Time | Quotation Validity | Currency`, with `Quotation No` and
  `Date` kept in the same table positions as before so the existing
  quotation-number/date quick-edit injection (`_inject_quotation_no`,
  `_inject_date` in `assembler.py`) keeps working unmodified.
- The old Section 2 (Delivery & Bank Details box) is **removed entirely** —
  no bank details on an engineering quotation. `_force_bank_details` in
  `assembler.py` is keyed to `class="delivery-table"`, so it now becomes a
  harmless no-op for engineering (no code change needed there).
- Items table headers renamed for fidelity (`Sr. No.` / `Total Price`); same
  `// Make: ... // HSN: ...` description mechanics as before (unchanged, so
  `_inject_hsn_in_items`/`_apply_make_in_quotation_items` still work).
- "Amount in Words" is now **conditional**: included only for INR/local
  quotes, omitted for USD/export quotes.
- Weight & Packing Details is now **conditional**: only generated for
  bulky/heavy items (motors, panels, large assemblies — signaled by
  Dimensional/Packing data), omitted entirely for small components (relays,
  sensors, switches, PLCs, connectors).

**`ENGINEERING_TDS_CONTENT_GUIDE`**
- Rewritten from bullet-prose rules to tabular rules: one or more
  `Parameter|Specification` pipe tables per product (grouped by category for
  complex products), followed by `## Key Features` and
  `## Typical Applications` bullet lists.
- Manufacturer/Model/Part Number are now explicitly **allowed as rows inside
  the table** (they identify the product) — still excluding Buyer name,
  Supplier address, HSN, Quantity, pricing, and payment terms from this
  section.

**Internal marker vs. visible heading:** the internal section marker stays
`# TECHNICAL DESCRIPTION` (required — `response_parser.py`'s
`split_four_sections` regex matches `TECHNICAL DESCRIPTION` but not a bare
`TECHNICAL DATA SHEET` without `(TDS)`). Only the **visible PDF heading**
changed, in `assembler.py`, from `TECHNICAL DESCRIPTION` to
`TECHNICAL DATA SHEET`.

**`response_parser.py`:** added `first_row.startswith("buyer")` alongside
the existing `"bill to"` check in `_detect_table_type`, so the new header
table is still classified as the customer/header table type (bold label
columns) via content-sniffing.

**Verified live:** generated a small component (selector switch) — header
renders correctly with no GST/bank box, Weight & Packing correctly omitted,
TDS renders as a proper `Parameter | Specification` table (Manufacturer,
Model, Part Number, ratings, etc.) followed by Key Features and Typical
Applications. Quotation-number injection into the new header table confirmed
working.

## 3. Invoice-family documents — Proforma Invoice, Invoice, Commercial Invoice, Tax Invoice (unified)

**Files:** `backend/app/schemas/document.py`,
`backend/app/services/invoice_generator.py`,
`backend/app/routes/documents.py`,
`frontend/src/lib/types.ts`, `frontend/src/components/ui/DocTypeIcon.tsx`,
`frontend/src/routes/InvoicesPage.tsx`

### Why

The app only ever generated two invoice-family documents, both weak: a
generic **"Invoice"** (always titled "INVOICE" regardless of local/export)
and a **Proforma Invoice** that was really just the Quotation's own HTML
with the heading and a couple of labels swapped — both inherited the
Quotation's Bill To/Ship To/Delivery&Bank box layout, not a real invoice
layout. Real Vertex Chemical sample documents (`docs/Commercial
Invoices.pdf`, `docs/Tax Invoices.pdf`, `docs/Proforma Invoices.pdf`) show
what these should actually look like: a Supplier / Ship To / Bill To / Bank
Details / Freight box layout, structurally different from the Quotation.

Initially, Commercial Invoice, Tax Invoice, and Proforma Invoice were each
built to match their *own* sample's exact layout (Proforma Invoice's sample
happens to use Consignee/Buyer's-Order-No boxes and a 7-column item table
with HSN as its own column and a 9%+9% SGST/CGST split, while Commercial/Tax
Invoice use Ship-To/Bill-To/Freight boxes, a 5-column item table, and a flat
18% IGST). Per explicit direction, this was then **consolidated**: Proforma
Invoice and the generic Invoice were changed to share the exact same visual
layout as Commercial/Tax Invoice (same boxes, same 5-column item table, same
IGST 18% tax treatment) — only the heading and the invoice-number label
differ per type now. The underlying data (buyer, products, HSN, amounts)
comes from the same extraction logic regardless of type.

### What changed

- `DocumentType` enum gained `commercial_invoice` and `tax_invoice`
  (`schemas/document.py`); `proforma_invoice`/`invoice` already existed.
- **`invoice_generator.py`**: one function, `build_invoice_document
  (quotation_html, doc_type, ...)`, handles all four types
  (`proforma_invoice` | `invoice` | `commercial_invoice` | `tax_invoice`).
  It extracts buyer name/address, item rows (product/HSN/qty/unit
  price/amount), and totals out of the quotation's
  `customer-table`/`items-table`/`totals-table` via regex helpers
  (`_extract_label_value_table`, `_extract_item_rows`), then renders the
  Supplier/Ship To/Bill To/Bank Details/Freight box layout with:
  - Fixed Vertex Chemical Corporation supplier block + bank details (same
    constants already used in `vertex_prompts.py`'s compliance rules).
  - A `_TITLES`/`_NO_LABELS` lookup keyed by `doc_type` for the only two
    things that differ per type: the `<h1>` heading text and whether the
    invoice-number box says "Proforma Invoice No.:" or "Invoice No.:".
  - IGST 18% computed and added for domestic (local) sales, uniformly
    across all four types; nothing added for export sales.
  - "Currency (In Words)" carried over from the quotation's own Amount in
    Words when it still matches the total; dropped (not shown wrong) once
    GST changes the total, since there's no number-to-words conversion
    available here.
  - The old `transform_quotation_to_invoice` (relabel-the-quotation-in-place
    approach) and the earlier per-type `build_proforma_invoice`/
    `build_commercial_or_tax_invoice` functions were removed — superseded by
    the single unified builder.
- **`documents.py`**: `generate_batch_invoices` now creates **three**
  documents per batch — Proforma Invoice, Invoice, and either Commercial
  Invoice (export) or Tax Invoice (domestic), based on the quotation's
  `local_export` flag — all three via `build_invoice_document`.
  `list_batch_invoices` and the batch-delete-before-regenerate query both
  extended to the new `_INVOICE_DOC_TYPES` list. PDF download filenames
  extended with `CI_.../TAX_...` patterns matching the existing
  `QF_/PI_/INV_` convention.
- **Frontend**: `DocumentType` union, `DocTypeIcon` (new teal/fuchsia
  icons), and `InvoicesPage` copy updated to know about the two new types.
  No new quick-edit "change number" support for any of the four (previously
  only Quotation had it) — they use a single merged label+value cell rather
  than the label|value adjacent `<td>` pair the injection regex expects.

**Verified**: unit-tested `build_invoice_document` for all four `doc_type`
values against the same synthetic quotation HTML — confirmed all four
render the identical box layout and identical IGST 18% math
(₹16,28,000 subtotal → ₹2,93,040 IGST → ₹19,21,040 total, matching a real
sample exactly), differing only in heading (`PROFORMA INVOICE` /
`INVOICE` / `COMMERCIAL INVOICE` / `TAX INVOICE`) and invoice-number label.
Confirmed via backend logs that a live batch-invoice generation + PDF
download succeeded end-to-end through the running app.

### 3a. Field-completeness pass — fields missing from the real sample were added back

After unifying the layout, a field-by-field audit against the real
Commercial/Tax Invoice PDF samples turned up several fields that existed in
the samples but weren't in the built layout:

- **Item table** was missing a separate **Unit** column — the real samples
  show `Item | Description of Goods | Quantity | Unit Price | Unit |
  Amount` (6 columns); the built version only had 5, with quantity and unit
  combined into one cell. Reintroduced `_split_qty_unit()` to split the
  quotation's combined `"22 MT"` cell into separate Quantity/Unit columns.
- **Logistics box** was missing **Port of Loading**, **Relevant Location**,
  and **Final Place of Delivery** — all present as their own labeled cells
  in the real samples (often blank in practice, which the samples
  themselves also show — these aren't fabricated when there's no data
  source for them). The logistics box is now a proper 4-column, 4-row grid
  matching the real sample's shape; **Port of Discharge** and **Final
  Place of Delivery** both fall back to the same stored `port` field since
  the app only persists one generic port value on the document record (no
  separate loading/discharge ports are captured at that point).
- **Ship To vs. Bill To** were being collapsed into one identical value.
  The quotation's own `customer-table` already tracks `Bill To` and `Ship
  To` as separate rows (occasionally a different consignee — e.g. a
  freight/warehouse company — vs. the invoiced buyer, as in one of the real
  Tax Invoice samples), so these are now read independently, falling back
  to the same value when the quotation only has one.
- **Buyer's GSTIN** was dropped entirely during unification. Re-added under
  the Bill To box (`customer.get("gst no")`, skipped when "N/A") — legally
  relevant on a domestic Tax Invoice and present in every real domestic
  sample.

**Verified**: re-tested against a domestic Tax Invoice scenario mirroring
the real "Head Star Global" sample exactly, including the Ship To
(Conex Terminal, a different consignee) vs. Bill To (Head Star Global,
with its GSTIN) distinction — output reproduces the real sample's
₹20,35,000 → +₹3,66,300 IGST → **₹24,01,300** total exactly, with the
6-column item table (Unit = "MT" in its own column) and the full 4-row
logistics grid.

## 4. Quotation print/PDF styling polish

**Files:** `backend/app/services/export/print_css.py`

The in-browser TipTap editor already tints the customer-table/delivery-table
label columns (1st/3rd) light gray (`#f9f9f9`) for visual hierarchy, but the
PDF/DOCX export CSS explicitly forced those cells to plain white with
`!important` — so the exported/printed Quotation looked flatter than the
editor preview. Added the same `#f9f9f9` label tint to
`.customer-table td:nth-child(odd)` / `.delivery-table td:nth-child(odd)` in
the print CSS, and bumped the spacing between the Quotation's stacked table
sections from `4px` to `6px` margin for a cleaner, more separated look.
Verified against a real quotation's exported PDF — label columns (Bill To,
GST No, Quotation No, Account Name, IFSC, etc.) now show the tint.

## 5. Declaration + signature box (invoice-family documents)

**File:** `backend/app/services/invoice_generator.py`

The real samples show the Declaration text and the authorized-signatory
stamp side by side in a two-column box, not stacked. `build_invoice_document`'s
footer now renders a `declaration-sig-table` (deliberately **not** named
`terms-sig-table` — that class is forced borderless/transparent in
`print_css.py` for the Quotation's own terms section, which would strip
this box's visible border) with Declaration on the left and literal
`AUTHORIZED SIGNATORY` text on the right. The existing
`_inject_signature_image` (in `services/export/service.py`) already
searches the whole document for that exact phrase and inserts the real
signature stamp image just before it at PDF-export time — reusing that
existing mechanism instead of building a new one means the stamp appears
automatically, with no changes needed anywhere else.

**Verified** across all four document types, using real batches already in
the database (not synthetic data): Proforma Invoice, Invoice, Commercial
Invoice, and Tax Invoice all render the Declaration/signature box correctly
with the actual stamp image. Also checked a 3-item multi-product domestic
batch (Toluene/Xylene/Hexane) — all three item rows extract correctly, IGST
18% is computed on the sum of all three items (₹88,25,000 subtotal →
₹15,88,500 IGST → ₹1,04,13,500 total), and the signature box still renders
correctly alongside the longer item table.

## 6. Extraction resilience — quotations edited in the TipTap editor

**File:** `backend/app/services/invoice_generator.py`

While verifying the Declaration/signature fix against a *real* batch already
in the database, the Commercial Invoice came out with an **empty item
table** and blank Invoice Date/Ship-To/Bill-To, even though the source
Quotation clearly had that data. Root cause: that quotation had been opened
and saved in the TipTap editor at least once (`updated_at` differed from
`created_at`), and comparing its HTML against a never-edited quotation's
HTML showed TipTap/ProseMirror's serialization **strips the custom
`customer-table`/`items-table`/`totals-table` CSS classes entirely** on
save, replacing them with generic `<table style="min-width:100px;">`
markup. `build_invoice_document`'s extraction was keyed purely on those CSS
classes, so it silently found nothing for any quotation that had ever been
edited and re-saved — likely a large fraction of real quotations. This
class-stripping was also confirmed to affect other already-existing
class-dependent backend logic in the same way (currency normalization,
Make/HSN injection, bank-detail injection in `assembler.py` all key off the
same CSS classes) — the root cause is fixed at the frontend in section 7
below; this section covers the belt-and-suspenders backend fallback.

**Fix:** `_extract_table_body` now falls back to content-based table
detection — mirroring how `response_parser.py`'s own `_detect_table_type`
already sniffs tables by their first row's text rather than relying solely
on class names — when the expected CSS class isn't found: it scans every
`<table>` in the document and picks the first whose header row contains a
known signature (`"bill to"` for the customer table, `"total amount"` for
totals, `"description of goods"`/`"unit price"` for the items table). This
stays in place even after the frontend fix (section 7) as a safety net for
any already-edited quotations saved before that fix went in.

**Verified**: re-tested against the exact real (edited) quotation that
exposed the bug — Invoice Date, Ship To/Bill To, the item row (UREA 46%,
2,500 MT, $670.00, $16,75,000.00), and Currency (In Words) now all populate
correctly in the regenerated Commercial Invoice PDF, alongside the working
Declaration/signature box from section 5.

## 7. Root-cause fix — TipTap silently drops custom classes on save

**Files:** `frontend/src/components/editor/VertexEditor.tsx`,
`frontend/src/components/editor/PreservedSectionDiv.ts` (new)

Section 6 fixed the *symptom* for this session's new code; this fixes the
actual *cause*, so the same class of bug stops affecting every other
class-dependent feature in the app (currency normalization, Make/HSN
injection, bank-detail injection in `assembler.py` — all already silently
broken for any previously-edited quotation, not something this session
introduced).

TipTap's default `Table` extension (`@tiptap/extension-table`) doesn't
declare `class` as a recognized node attribute, so ProseMirror drops it
during parse — confirmed the *exact* mechanism by which this happens is
identical to a bug the codebase had already hit and fixed once before, for
a different element: `TermsSigWrapper.ts` exists specifically because
"TipTap's default schema strips unknown divs" (its own comment) stripped
the `terms-sig-wrapper` div. That fix was never extended to cover the
quotation's table classes or the COA/engineering-TDS wrapper divs, which
remained vulnerable to the exact same failure mode.

**Fix:**
- `VertexEditor.tsx`: `Table` extended (`Table.extend({ addAttributes... })`)
  to add `class` as a persisted attribute (parsed from and rendered back to
  the `class` HTML attribute) — covers `customer-table`, `items-table`,
  `totals-table`, `delivery-table`, and `weight-packing-table` uniformly,
  since it's on the Table node itself rather than any one specific class.
- New `PreservedSectionDiv.ts`: generalizes the same fix pattern as
  `TermsSigWrapper.ts` into an allow-list of preserved wrapper-div classes
  (`coa-section`, `engineering-tech-doc`) instead of one hardcoded class per
  file, so future wrapper classes can be added in one place.

**Verified headlessly** (no browser needed — `@tiptap/html`'s
`generateJSON`/`generateHTML` run on Node via `zeed-dom`), reproducing the
exact parse→edit→serialize round-trip `VertexEditor.tsx` performs:
- Confirmed the bug reproduces with the plain `Table` extension (class
  dropped, cells collapse to generic `<table><colgroup>...<td colspan="1"
  rowspan="1">` markup — an exact match for what was found in the real
  database document in section 6).
- Confirmed `customer-table`, `items-table`, `coa-section`,
  `engineering-tech-doc`, and `terms-sig-wrapper` (regression-checked, since
  it was already working) **all** survive the round-trip correctly with the
  fix in place.

## 8. High-effort code review + fixes

Ran a full 7-angle code review (line-by-line diff scan, removed-behavior
audit, cross-file caller/callee tracing, reuse, simplification, efficiency,
altitude/design-depth — conventions skipped, no CLAUDE.md in this repo) over
this session's diff, verified each candidate directly against the current
code, then fixed everything that survived verification:

**Correctness bugs fixed:**
- **Engineering invoices always had a blank Invoice Date.** The engineering
  Quotation header labels that row just "Date" (not "Quotation Date" like
  chemical's), so the dict lookup key never matched. `used_date` now checks
  `"quotation date"` and `"date"`.
- **Engineering invoices always had a blank buyer address.** The engineering
  header never captures a street address at all (by design, matching the
  real samples). `buyer_address` now falls back to the buyer's `country`
  (already known from the row data) instead of leaving the line fully blank.
- **Engineering invoices could get a completely empty Bill To name** if the
  `buyer_name` param wasn't supplied — the lookup chain checked `"bill
  to"`/`"ship to"` but not `"buyer"` (the engineering header's own label).
  Found by testing the fix above, not by the review agents. Now checks all
  three keys.
- **The customer-table content-signature fallback didn't recognize
  engineering's "Buyer" header row** — `response_parser.py`'s own table-type
  detector was updated to accept it in section 2, but `invoice_generator.py`'s
  independent copy of the same signatures wasn't. Fixed by centralizing both
  in one place (see reuse fix below) instead of just patching the symptom.
- **The `?seq=` custom-invoice-number override silently did nothing on all
  four invoice-family document types.** The regex expected the Quotation's
  two-adjacent-`<td>` label/value layout; `build_invoice_document`'s actual
  output combines label and value in one `<td>`. Added a second regex
  pattern matching that shape. Verified live: `?seq=77` now correctly
  produces `Invoice No.: VERT/077/2026` in the downloaded PDF, where it
  previously left the stored number unchanged with no error.
- **Commercial Invoice / Tax Invoice were missing the number-picker UI**
  entirely (`EditorPage.tsx`'s `needsNumber` whitelist was never extended
  when those two types were added) — added them.
- **`PRESERVED_CLASSES` (section 7) didn't cover `quotation-page`**, the
  highest-traffic wrapper class — matters specifically on the xhtml2pdf
  fallback rendering path (used when WeasyPrint is unavailable), which,
  unlike WeasyPrint, doesn't re-wrap content in a fresh `quotation-page` div
  at render time. Added it, plus `invoice-family-page` pre-emptively (no
  print CSS depends on it yet, but this avoids the same class of bug
  recurring silently when one is added later).

**Reuse:** `invoice_generator.py` had its own independently-maintained copy
of "detect a quotation table by its first row's content" — the exact
mechanism that had already drifted out of sync with `response_parser.py`'s
version (the direct cause of the "buyer" bug above). Centralized as
`CUSTOMER_TABLE_SIGNATURES`/`TOTALS_TABLE_SIGNATURES`/`ITEMS_TABLE_SIGNATURES`
in `response_parser.py`, imported by `invoice_generator.py`, so the two
can't drift apart again.

**Efficiency:** building the 3 invoice-family documents for one batch
(Proforma Invoice, Invoice, Commercial/Tax Invoice) independently re-parsed
the same quotation HTML for the same tables up to 9 times. Added
`extract_quotation_data()` — called once per batch in `documents.py`,
passed into `build_invoice_document(..., extracted=...)` for all 3 calls.

**Simplification:**
- `documents.py`'s three near-identical build+dict-wrap sequences
  (`pi_html`/`inv_html`/`ci_or_tax_html` → `pi_doc`/`inv_doc`/`ci_doc`, each
  variable used exactly once) collapsed into a single loop over the 3 doc
  types — this fell out naturally from the efficiency fix above.
- The logistics table's four `<tr>` blocks with hand-counted, inconsistent
  colspans (nothing enforced they actually summed to 4 per row) replaced
  with a data-driven `(label, value, colspan)` list rendered by a small
  `_logistics_row()` helper that raises immediately if a row's colspans
  don't sum to 4 — a future added field can't silently misalign columns.

**Not fixed (assessed and found to be non-issues on closer inspection):**
one review angle flagged that the new `ci-header-table`/`ci-parties-table`/
etc. tables "rely solely on inline `style`, with no class-based CSS backing,
so they'd visually degrade if ever edited." Traced the actual CSS cascade:
`print_css.py` has an unscoped `th, td { border/padding !important }` rule
that applies regardless of class, and these tables never had label-tinting
inline styles to lose in the first place (only plain white backgrounds,
invisible either way) — the concern didn't hold up once verified, so no
change was made there.

## Explicitly out of scope

- Chemical Quotation, COA, TDS, MSDS — untouched.
- DOCX download — `html_to_docx` exists in `services/export/service.py` but
  no route exposes it for *any* document type; this is a pre-existing gap
  unrelated to this work and was left alone per explicit direction.
- The unrelated, already-uncommitted auth/email/shipment-tracking work in
  this repo (`app/core/auth.py`, `app/routes/admin.py`, `app/routes/auth.py`,
  `app/routes/email.py`, `AdminDashboard.tsx`, `ShipmentPage.tsx`, etc.) —
  pre-existing local changes not part of this session, not covered here.
