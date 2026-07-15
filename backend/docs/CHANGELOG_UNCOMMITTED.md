# Changelog — all uncommitted changes (working tree vs. `main`)

This repo is on branch `main`, up to date with `origin/main` (no divergent
commits) — everything below is **uncommitted working-tree state**: modified
tracked files plus new untracked files. This document covers the full diff.

For full detail on the engineering-quotation/TDS rework and the new
invoice document types, see
[`CHANGES_ENGINEERING_AND_INVOICES.md`](./CHANGES_ENGINEERING_AND_INVOICES.md) —
summarized briefly in section 5 here, not repeated in full.

---

## 1. Authentication (admin login)

A single shared admin password protects `/admin/*` and the shipment-tracking
API. No per-user accounts — whoever knows the password is "admin".

**Flow:** `POST /api/auth/login` with `{password}` → verified against
`AUTH_PASSWORD` (env var) → sets an `HttpOnly` cookie (`vertex_session`)
whose value is a **fixed HMAC** of the password (`hmac.new(AUTH_PASSWORD,
b"vertex-admin-session", sha256)`), not a random per-login session token.
Every request re-derives that same HMAC and compares it to the cookie —
there's no server-side session store, so the cookie value never changes and
never expires server-side (only the 7-day cookie `max_age` expires it
client-side).

**Files:**
- `backend/app/core/auth.py` — `verify_password`, `_session_value` (the HMAC),
  `verify_session`, `require_admin(request)` (raises 401 if the cookie is
  missing/invalid).
- `backend/app/routes/auth.py` — `POST /api/auth/login`, `POST
  /api/auth/logout`, `GET /api/auth/check`.
- `backend/app/routes/admin.py` — every shipment-tracking route calls
  `require_admin(request)` directly (not via FastAPI `Depends` — the `Depends`
  import is present but unused for this purpose).
- Frontend: `context/AuthContext.tsx` (`AuthProvider`, seeds
  `isAuthenticated` from `GET /api/auth/check` on mount), `routes/LoginPage.tsx`
  (password form), `App.tsx` (`RequireAuth` wrapper gating `/admin` and
  `/admin/shipment/:shipmentId`), `components/layout/Header.tsx` (Admin /
  Admin Login nav link based on auth state).

**New env vars:** `AUTH_PASSWORD` (required — login always fails if unset),
`JWT_SECRET` (declared in `config.py`, **not referenced anywhere else** —
dead leftover from an earlier JWT-based design; the actual scheme is the
HMAC cookie above, not JWT).

**Known gaps:**
- Neither `AUTH_PASSWORD` nor `JWT_SECRET` (nor any of the email vars below)
  were added to `backend/.env.example` — a fresh environment setup won't know
  these exist.
- No brute-force protection/rate limiting on login.
- Cookie is `secure=False` by design (comment: "internal tool — no HTTPS
  required") — correct for an internal deployment, not for public internet.
- Anyone who captures the cookie value can replay it indefinitely until the
  password changes (no expiry/rotation server-side).

---

## 2. Email Sending

Two entry points, both sending generated documents as PDF attachments via
Microsoft Graph (client-credentials / app-only OAuth, not per-user mailbox
login):

1. **Right after generation** (`GeneratePage.tsx`) — once a batch finishes,
   a "Send Emails" button opens `SendEmailModal` for that `batch_id`; pick a
   sender + doc types, `POST /api/email/send-batch`.
2. **Standalone bulk flow** (`routes/EmailSendPage.tsx`, new route
   `/send-emails`) — upload the same kind of Excel used for generation
   (needs Buyer Name/Product Name/Email id columns); backend matches each
   row to its most recent generated batch (`POST
   /api/email/preview-from-excel`); review/select, then `POST
   /api/email/send-from-list`.

**Files:**
- `backend/app/routes/email.py` — `GET /senders` (returns the configured
  `SENDER_EMAILS` allowlist), `POST /send-batch`, `POST
  /preview-from-excel`, `POST /send-from-list`, shared `_send_to_groups`
  helper (renders each doc to PDF via the existing `html_to_pdf`, sends via
  `email_service.send_email`, aggregates per-recipient sent/failed results
  without aborting the whole batch on one failure).
- `backend/app/services/email_service.py` — MSAL client-credentials token
  acquisition + Microsoft Graph `sendMail` call.
- Frontend: `components/SendEmailModal.tsx`, `routes/EmailSendPage.tsx`
  (4-step wizard: upload → preview → sending → done).

**New env vars:** `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET` (Azure
AD app registration), `SENDER_EMAILS` (comma-separated allowlist). **Not
added to `.env.example`.**

**New dependencies:** `msal`, `httpx` (`backend/requirements.txt`).

**Known gaps:**
- Email subject/body is **hardcoded** ("Quotation – {product} | Vertex
  Chemical Corporation", "Please find attached our quotation...") regardless
  of which doc types were actually selected (e.g. sending only TDS/COA/MSDS
  still says "quotation") and regardless of business line (always says
  "Vertex Chemical Corporation" even for engineering batches).
- `preview-from-excel` and `admin.py`'s batch search both insert
  user-supplied buyer/product strings **directly into a MongoDB `$regex`**
  without `re.escape()` — a name containing regex metacharacters (`(`, `.`,
  `*`, etc.) can throw a Mongo error or mismatch. Worth fixing before this
  is exposed to untrusted input.
- `_get_access_token()` re-authenticates with Azure AD **per recipient**
  (a new `ConfidentialClientApplication` is constructed per call, so MSAL's
  built-in token cache is never reused) — wasteful/slow for large batches,
  not a correctness bug.
- No attachment size guard before base64-encoding into the Graph JSON
  payload (Graph's `sendMail` JSON approach has a size ceiling); large PDF
  batches could fail with a generic per-recipient error.
- If `SENDER_EMAILS` is unset, the whole feature is inert (no senders to
  pick, Send button stays disabled) with no explicit "not configured"
  message.
- `EmailSendPage.tsx` talks to the backend via raw `fetch` with its own
  locally-computed API base URL, bypassing the shared `lib/api.ts` helpers
  that `SendEmailModal` uses — inconsistent, not broken.

---

## 3. Shipment Tracking / Admin Dashboard

After logging in, `/admin` (`AdminDashboard.tsx`) lists tracked shipments —
one row per buyer/product shipment, each requiring 7 fixed document types
before it's "Complete": PI, Tax Invoice, P/L, TT Copy, Bank Receipt, BL Copy,
Custom Copy. Add a shipment by linking an existing generated quotation batch,
or manually (buyer/product/quotation-no with no link, or fully blank). Click
"Manage" → `/admin/shipment/:id` (`ShipmentPage.tsx`) to upload/replace/
view/download each of the 7 slots independently. Delete removes the DB
record and its uploaded files from disk.

**Files:**
- `backend/app/routes/admin.py` — `DOC_TYPES` (the fixed 7-slot schema),
  `GET/POST /api/admin/shipments`, `GET /api/admin/shipments/{id}`, `POST
  /api/admin/shipments/{id}/upload/{doc_type}` (20 MB size cap, replaces any
  previous file for that slot), `GET
  /api/admin/shipments/{id}/files/{doc_type}` (view/download), `DELETE
  /api/admin/shipments/{id}`, `GET /api/admin/batches` (searchable/paginated
  list of real generated-batch quotations for the "link a quotation" tab —
  excludes manual-doc-feature batches).
- `backend/app/db/mongo.py` — new `shipment_tracking_collection`.
- Frontend: `routes/AdminDashboard.tsx` (list + 3-tab "add shipment" modal:
  Select Quotation / Add Manually / Skip Quotation, debounced server-side
  search, "Load more" pagination), `routes/ShipmentPage.tsx` (per-shipment
  detail, `DocCard` per doc-type slot).

**Known gaps:**
- No index on `shipment_tracking` for `batch_id`/`created_at` — fine at
  small scale, a scaling concern later.
- `POST .../upload/{doc_type}` validates size only, not file type/content —
  the `accept=".pdf,.png,..."` restriction is client-side only; any file
  type can be uploaded via a direct API call.
- Partial delete failures (file removal `OSError`) are silently swallowed —
  the DB record is still deleted, which can leave orphaned files on disk.
- `DOC_TYPE_LABELS` in `admin.py` is defined but unused server-side — the
  same labels are duplicated independently in both frontend pages.
- 401-session-expiry handling is inconsistent: `ShipmentPage.tsx` redirects
  to `/login` on a 401, `AdminDashboard.tsx` does not (just shows a generic
  error) — `RequireAuth` still catches it on next navigation, so not a hard
  bug, just an inconsistent UX moment.
- Same un-escaped `$regex` concern as email.py's search, for the `q`/
  `entered_by` filters on `GET /api/admin/batches`.

---

## 4. Quotation number format change + PDF sequence override

Unrelated to the three features above — a document-numbering change that
affects **all** auto-generated quotation/invoice numbers globally.

- `backend/app/utils/quotation_number.py`: old format `[COMPANY
  CODE]/[SEQ]/[YY]/[MM]` (e.g. `AK/01/25/155`) → new fixed format
  `VERT/[SEQ]/[YEAR]` (e.g. `VERT/001/2026`), plus a new `build_quotation_no
  (seq: int)` helper.
- `documents.py`'s existing `GET /documents/{id}/pdf?seq=N` endpoint (see
  the other changelog for the invoice-related parts of this file) uses
  `build_quotation_no` to let a user override the printed sequence number at
  download time, regexing it into the "Quotation/Proforma Invoice/Invoice
  No" cell.
- Frontend: `EditorPage.tsx` adds a "Select Document Number" modal (for
  `quotation`/`proforma_invoice`/`invoice` doc types) — type a sequence
  1–9999, preview `VERT/{seq}/{year}`, then `savePdf(doc.id, pdfSeq)`.
  `lib/api.ts`'s `savePdf`/`saveAllPdf` gained an optional `seq` param.

**Status:** self-contained, working. No known gaps identified beyond the
1–9999 sequence range being a hard UI limit.

---

## 5. Engineering Quotation/TDS rework + Commercial/Tax/Proforma Invoice (this session)

Covered in full in
[`CHANGES_ENGINEERING_AND_INVOICES.md`](./CHANGES_ENGINEERING_AND_INVOICES.md).
Summary:
- Fixed a bug blocking **all** AI document generation (hardcoded
  `temperature=0.3` incompatible with the configured GPT-5 model).
- Reworked the engineering Quotation header (Buyer/Seller/Price
  Basis/Payment Terms/Delivery Time/Validity/Currency — dropped the
  chemical-cloned GST/Ship-To/Bank-box layout) and TDS (now a proper
  `Parameter | Specification` Technical Data Sheet instead of bullet prose),
  with Weight & Packing made conditional on product size.
- Added two new document types the app never produced: **Commercial
  Invoice** (export) and **Tax Invoice** (domestic, IGST 18%), built fresh
  from the quotation's data rather than relabeling it.
- **Proforma Invoice** and the generic **Invoice** were also rebuilt fresh
  from the quotation's data, and — per explicit direction — unified to share
  the exact same Supplier/Ship-To/Bill-To/Bank-Details/Freight box layout
  and IGST 18% tax treatment as Commercial/Tax Invoice, via one shared
  `build_invoice_document()` function; only the heading and invoice-number
  label differ per type now.
- Chemical Quotation/COA/TDS/MSDS were explicitly left untouched.

---

## 6. Chemical document data-quality fixes (unrelated small fixes bundled in this tree)

- `backend/app/prompts/reference_templates_generated.py` +
  `backend/app/prompts/vertex_prompts.py`: COA/TDS/MSDS purity/assay values
  were hardcoded to `≥ 99.0%`/`≥ 99%` regardless of the actual product;
  changed to a `[Purity Specification]` placeholder plus a new mandatory
  prompt rule telling the model to fill it with the product's actual
  purity (from the Desc field, then grade — AR/LR/Technical/Industrial —
  then industry-standard defaults), explicitly flagged as "a compliance
  error" if wrong.
- `backend/app/services/document_generation/generator.py` (+1 line): passes
  `date=row.date` through to document assembly — a previously-dropped
  user-supplied Excel date now actually reaches the generated document
  instead of being silently discarded in favor of today's date.

---

## 7. Misc / plumbing

- `backend/main.py`: registers the three new routers (`auth_router`,
  `admin_router`, `email_router`).
- `backend/.env.example`: `OPENAI_MODEL` bumped to `gpt-5-mini-2025-08-07`
  (matches the model the temperature-bug fix above targets). Does **not**
  yet include the new auth/email env vars — see gaps above.
- `backend/.python-version`: `3.12.7` → `3.12.10` (patch bump, incidental).
- `frontend/src/App.tsx`: restructured to extract `AppRoutes()` so
  `useAuth()` can run inside the Router context; wraps the app in
  `<AuthProvider>`.
- `frontend/src/components/editor/VertexEditor.tsx`: unrelated editor fix —
  preserves/restores TipTap cursor position across a debounced content
  recalculation that previously reset it (with bounds-clamping + try/catch).

---

## Summary: working vs. needs attention

| Area | Status | Key gaps |
|---|---|---|
| Authentication | Working | `.env.example` not updated; dead `JWT_SECRET`; no rate limiting |
| Email Sending | Working, fragile | Hardcoded subject/body; unescaped regex; per-recipient token refetch; no size guard |
| Shipment Tracking / Admin | Working | No DB indexes; client-side-only file-type check; inconsistent 401 handling |
| Quotation number format + seq override | Working | None found |
| Engineering Quotation/TDS + new invoice types | Working, verified | See other changelog |
| Purity/date prompt fixes | Working | None found |
