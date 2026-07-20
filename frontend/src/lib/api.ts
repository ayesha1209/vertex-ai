import type {
  DocumentInDB,
  DocumentSummary,
  GenerateRowResponse,
  ListBatchesResponse,
  ListDocumentsResponse,
  RowPreview,
  TermsResponse,
  UploadPreviewResponse
} from "./types";

// In dev, use relative /api so Vite proxy forwards to backend (avoids CORS and "Failed to fetch")
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "/api" : "http://localhost:8000/api");

/** Turn browser "Failed to fetch" / network errors into a clear message. */
function normalizeNetworkError(err: unknown, context = "request"): Error {
  const msg = err instanceof Error ? err.message : String(err);
  if (
    /failed to fetch|network request failed|load failed|network error/i.test(msg) ||
    (err instanceof TypeError && msg === "Failed to fetch")
  ) {
    return new Error(
      "Network error. Check your connection and that the server is running, then try again."
    );
  }
  return err instanceof Error ? err : new Error(String(err));
}

/** Parse JSON or text from response; never throw on parse. */
async function getResponseDetail(res: Response): Promise<{ detail?: string }> {
  const text = await res.text();
  try {
    const j = JSON.parse(text) as { detail?: string };
    return j;
  } catch {
    return { detail: text.slice(0, 200) || res.statusText };
  }
}

export async function uploadPreview(file: File): Promise<UploadPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/upload-preview`, {
      method: "POST",
      body: formData,
    });
  } catch (e) {
    throw normalizeNetworkError(e, "upload");
  }

  if (!res.ok) {
    const error = await getResponseDetail(res);
    const detail: string =
      typeof error?.detail === "string" ? error.detail : "Upload failed. Please try again.";

    if (res.status === 413) {
      throw new Error(detail || "File is too large. Use a smaller Excel/CSV (max 5 MB).");
    }
    if (res.status === 400) {
      throw new Error(detail || "Invalid file or columns. Need 'Buyer Name' and 'Product name'.");
    }
    if (res.status === 503) {
      throw new Error(detail || "Server is busy. Please try again in a moment.");
    }
    if (res.status >= 500) {
      throw new Error(detail || "Server error. Please try again later.");
    }
    throw new Error(detail);
  }

  try {
    return (await res.json()) as UploadPreviewResponse;
  } catch {
    throw new Error("Invalid response from server. Please try again.");
  }
}

export async function generateRow(
  row: RowPreview
): Promise<GenerateRowResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/generate-row`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ row }),
    });
  } catch (e) {
    throw normalizeNetworkError(e);
  }

  if (!res.ok) {
    const error = await res.json().catch(() => null);
    const detail: unknown = error?.detail;

    const baseMessage =
      typeof detail === "string"
        ? detail
        : "Failed to generate documents. Please try again.";

    if (res.status === 400) {
      throw new Error(baseMessage);
    }

    if (res.status === 503) {
      throw new Error(
        baseMessage ||
          "Server is busy generating other documents. Please try again shortly.",
      );
    }

    if (res.status >= 500) {
      throw new Error(
        baseMessage ||
          "Server error while generating documents. Please try again later.",
      );
    }

    throw new Error(baseMessage);
  }

  return res.json();
}

export async function generateBatch(
  rows: RowPreview[],
): Promise<{ job_id: string }> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/generate-batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows }),
    });
  } catch (e) {
    throw normalizeNetworkError(e);
  }

  if (!res.ok) {
    const error = await res.json().catch(() => null);
    const detail: unknown = error?.detail;

    const baseMessage =
      typeof detail === "string"
        ? detail
        : "Failed to start generation. Please try again.";

    if (res.status === 400) {
      // e.g. no rows provided
      throw new Error(baseMessage);
    }

    if (res.status === 503) {
      // Our “server busy” case
      throw new Error(
        baseMessage ||
          "Server is busy (another user may be generating). Please try again in a moment.",
      );
    }

    if (res.status >= 500) {
      throw new Error(
        baseMessage ||
          "Server error while starting batch. Please try again later.",
      );
    }

    throw new Error(baseMessage);
  }

  return res.json();
}

/** SSE stream URL - use same origin in dev (proxied), else full backend URL */
export async function checkDatabaseHealth(): Promise<{ ok: boolean; message?: string; error?: string }> {
  const res = await fetch(`${API_BASE_URL}/health/db`);
  const data = await res.json().catch(() => ({}));
  return data;
}

export async function getTerms(): Promise<TermsResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/terms`);
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const msg =
      (typeof err?.detail === "string" && err.detail) ||
      "Failed to load terms. Please try again.";
    throw new Error(msg);
  }
  return res.json();
}

export async function updateTerms(payload: { chemical?: string; engineering?: string }): Promise<TermsResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/terms`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const msg =
      (typeof err?.detail === "string" && err.detail) ||
      "Failed to update terms. Please try again.";
    throw new Error(msg);
  }
  return res.json();
}

export function getJobStreamUrl(jobId: string): string {
  const base = import.meta.env.VITE_API_BASE_URL;
  if (base) {
    const host = base.replace(/\/api\/?$/, "");
    return `${host}/api/jobs/${jobId}/stream`;
  }
  return `/api/jobs/${jobId}/stream`;
}

/** Request backend to stop generating; in-progress row may still finish, then stream ends. */
export async function cancelJob(jobId: string): Promise<{ job_id: string; cancelled: boolean }> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/jobs/${jobId}/cancel`, { method: "POST" });
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string })?.detail ?? "Failed to cancel job");
  }
  return res.json();
}

export async function listDocuments(params?: {
  q?: string;
  buyer?: string;
  product?: string;
  doc_type?: string;
  product_type?: "chemical" | "engineering";
  batch_id?: string;
  from_date?: string;
  to_date?: string;
  skip?: number;
  limit?: number;
  manual?: boolean;
}): Promise<ListDocumentsResponse> {
  const usp = new URLSearchParams();
  if (params?.q?.trim()) usp.set("q", params.q.trim());
  if (params?.buyer) usp.set("buyer", params.buyer);
  if (params?.product) usp.set("product", params.product);
  if (params?.doc_type) usp.set("doc_type", params.doc_type);
  if (params?.product_type) usp.set("product_type", params.product_type);
  if (params?.batch_id) usp.set("batch_id", params.batch_id);
  if (params?.from_date) usp.set("from_date", params.from_date);
  if (params?.to_date) usp.set("to_date", params.to_date);
  if (params?.skip != null) usp.set("skip", String(params.skip));
  if (params?.limit != null) usp.set("limit", String(params.limit));
  if (params?.manual) usp.set("manual", "true");

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/documents?${usp.toString()}`);
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const d = err?.detail;
    const msg =
      (typeof d === "string" && d) ||
      (Array.isArray(d) && d[0]?.msg) ||
      "Failed to list documents. Please try again.";
    throw new Error(msg);
  }
  return res.json();
}

export async function listBatches(params?: {
  q?: string;
  product_type?: "chemical" | "engineering";
  from_date?: string;
  to_date?: string;
  entered_by?: string;
  skip?: number;
  limit?: number;
}): Promise<ListBatchesResponse> {
  const usp = new URLSearchParams();
  if (params?.q?.trim()) usp.set("q", params.q.trim());
  if (params?.product_type) usp.set("product_type", params.product_type);
  if (params?.from_date) usp.set("from_date", params.from_date);
  if (params?.to_date) usp.set("to_date", params.to_date);
  if (params?.entered_by?.trim()) usp.set("entered_by", params.entered_by.trim());
  if (params?.skip != null) usp.set("skip", String(params.skip));
  if (params?.limit != null) usp.set("limit", String(params.limit));
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/documents/batches?${usp.toString()}`);
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const msg =
      (typeof err?.detail === "string" && err.detail) ||
      "Failed to list batches. Please try again.";
    throw new Error(msg);
  }
  return res.json();
}

export async function getEnteredByOptions(): Promise<string[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/documents/batches/entered-by`);
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (e) {
    throw normalizeNetworkError(e);
  }
}

export async function deleteBatch(batchId: string): Promise<{ deleted: number }> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/documents/batches/${encodeURIComponent(batchId)}`, {
      method: "DELETE",
    });
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const msg = err?.detail ?? "Failed to delete batch";
    throw new Error(typeof msg === "string" ? msg : "Failed to delete batch");
  }
  return res.json();
}

export async function deleteDocument(id: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    if (res.status === 404) throw new Error("Document not found");
    throw new Error("Failed to delete document");
  }
}

export async function deleteDocuments(ids: string[]): Promise<{ deleted: number }> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/documents`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const msg =
      (typeof err?.detail === "string" && err.detail) ||
      "Failed to delete documents. Please try again.";
    throw new Error(msg);
  }
  return res.json();
}

export async function getDocument(id: string): Promise<DocumentInDB> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/documents/${id}`);
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    if (res.status === 404) {
      throw new Error("Document not found.");
    }
    const err = await res.json().catch(() => null);
    const msg =
      (typeof err?.detail === "string" && err.detail) ||
      "Failed to fetch document. Please try again.";
    throw new Error(msg);
  }
  return res.json();
}

export async function updateDocument(
  id: string,
  html_content: string,
  meta?: { product_name?: string; employee_name?: string }
): Promise<DocumentInDB> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/documents/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html_content, ...meta })
    });
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    const error = await res.json().catch(() => null);
    throw new Error(error?.detail || "Failed to update document");
  }
  return res.json();
}

export async function createManualDocument(payload: {
  buyer_name: string;
  product_name: string;
  doc_type: string;
  product_type: string;
  letterhead: string;
  local_export: string;
  html_content: string;
}): Promise<DocumentInDB> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/documents/manual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || "Failed to create document");
  }
  return res.json();
}

/** List existing proforma invoices and invoices for a batch. */
export async function listBatchInvoices(batchId: string): Promise<ListDocumentsResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/documents/batch/${encodeURIComponent(batchId)}/invoices`);
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const msg =
      (typeof err?.detail === "string" && err.detail) ||
      "Failed to load invoices. Please try again.";
    throw new Error(msg);
  }
  return res.json();
}

/** Generate (or re-generate) Proforma Invoice + Invoice from the batch quotation. */
export async function generateBatchInvoices(batchId: string): Promise<ListDocumentsResponse> {
  let res: Response;
  try {
    res = await fetch(
      `${API_BASE_URL}/documents/batch/${encodeURIComponent(batchId)}/invoices/generate`,
      { method: "POST" },
    );
  } catch (e) {
    throw normalizeNetworkError(e);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const detail: unknown = err?.detail;
    const baseMessage =
      typeof detail === "string" ? detail : "Failed to generate invoices. Please try again.";
    if (res.status === 404) throw new Error(baseMessage);
    if (res.status === 400) throw new Error(baseMessage);
    if (res.status >= 500) throw new Error(baseMessage || "Server error. Please try again later.");
    throw new Error(baseMessage);
  }
  return res.json();
}

/** Save document as PDF file (triggers browser download). Optional seq overrides quotation number. */
export async function savePdf(id: string, seq?: number): Promise<void> {
  let pdfUrl = `${API_BASE_URL}/documents/${encodeURIComponent(id)}/pdf`;
  if (seq != null) {
    pdfUrl += `?seq=${seq}`;
  }

  // Direct link to the PDF endpoint. The backend sets
  // Content-Disposition: attachment, so the browser downloads instead of
  // navigating. This bypasses all blob/createObjectURL reliability issues.
  const a = document.createElement("a");
  a.href = pdfUrl;
  a.target = "_blank";
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => document.body.removeChild(a), 100);
}

/** Save multiple documents as PDFs (one after another, with short delay). */
export async function saveAllPdf(ids: string[], seq?: number): Promise<void> {
  for (const id of ids) {
    // eslint-disable-next-line no-await-in-loop
    await savePdf(id, seq);
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

// ---------------------------------------------------------------------------
// Email API
// ---------------------------------------------------------------------------

export async function getSenderEmails(): Promise<string[]> {
  const res = await fetch(`${API_BASE_URL}/email/senders`);
  if (!res.ok) throw new Error("Failed to load sender emails");
  const data = await res.json();
  return Array.isArray(data.senders) ? data.senders : [];
}

/** Look up the stored buyer email for a batch (from the original Excel's
 * "Email id" column), if any of its documents have one. Returns null if none
 * is stored, so the caller can ask the user to type one in instead. */
export async function getBatchEmail(batchId: string): Promise<string | null> {
  const res = await fetch(`${API_BASE_URL}/email/batch-email/${batchId}`);
  if (!res.ok) return null;
  const data = await res.json();
  return data.email ?? null;
}

export interface EmailSendResult {
  email: string;
  buyer_name: string;
  status: "sent" | "error";
  reason?: string;
}

export interface SendBatchEmailsResponse {
  results: EmailSendResult[];
  sent: number;
  failed: number;
}

export async function sendBatchEmails(payload: {
  batch_id: string;
  sender_email: string;
  doc_types: string[];
  subject?: string;
  recipient_email?: string;
  message?: string;
}): Promise<SendBatchEmailsResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/email/send-batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    throw normalizeNetworkError(e, "send-email");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || "Failed to send emails");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Auth API (cookie-based — no tokens needed)
// ---------------------------------------------------------------------------

export async function adminLogin(password: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || "Login failed");
  }
}

// ---------------------------------------------------------------------------
// Admin shipment tracking API (cookies sent automatically)
// ---------------------------------------------------------------------------

const _adminOpts: RequestInit = { credentials: "include" };

export interface ListBatchesParams {
  q?: string;
  entered_by?: string;
  skip?: number;
  limit?: number;
}

export async function listAdminBatches(params?: ListBatchesParams): Promise<{ batches: AdminBatch[]; total: number }> {
  const p = new URLSearchParams();
  if (params?.q) p.set("q", params.q);
  if (params?.entered_by) p.set("entered_by", params.entered_by);
  if (params?.skip != null) p.set("skip", String(params.skip));
  if (params?.limit != null) p.set("limit", String(params.limit));
  const qs = p.toString();
  const res = await fetch(`${API_BASE_URL}/admin/batches${qs ? `?${qs}` : ""}`, _adminOpts);
  if (!res.ok) throw new Error("Failed to load batches");
  return res.json();
}

export async function listShipments(skip = 0, limit = 50): Promise<{ shipments: Shipment[]; total: number }> {
  const res = await fetch(`${API_BASE_URL}/admin/shipments?skip=${skip}&limit=${limit}`, _adminOpts);
  if (!res.ok) throw new Error("Failed to load shipments");
  return res.json();
}

export async function createShipment(payload: { batch_id?: string; quotation_no?: string; buyer_name: string; product_name: string }): Promise<Shipment> {
  const res = await fetch(`${API_BASE_URL}/admin/shipments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || "Failed to create shipment");
  }
  return res.json();
}

export async function getShipment(shipmentId: string): Promise<Shipment> {
  const res = await fetch(`${API_BASE_URL}/admin/shipments/${shipmentId}`, _adminOpts);
  if (!res.ok) throw new Error("Shipment not found");
  return res.json();
}

export async function uploadShipmentDoc(shipmentId: string, docType: string, file: File): Promise<{ ok: boolean; doc_type: string; filename: string; all_uploaded: boolean }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE_URL}/admin/shipments/${shipmentId}/upload/${docType}`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || "Upload failed");
  }
  return res.json();
}

export function getShipmentDocUrl(shipmentId: string, docType: string): string {
  return `${API_BASE_URL}/admin/shipments/${shipmentId}/files/${docType}`;
}

export async function deleteShipment(shipmentId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/admin/shipments/${shipmentId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || "Failed to delete shipment");
  }
}

// ---------------------------------------------------------------------------
// Admin types
// ---------------------------------------------------------------------------

export interface AdminBatch {
  batch_id: string;
  buyer_name: string;
  product_name: string;
  quotation_no?: string;
  company_name?: string;
  employee_name?: string;
  created_at: string;
}

export interface ShipmentDocSlot {
  uploaded: boolean;
  filename?: string;
  file_path?: string;
  uploaded_at?: string;
}

export interface Shipment {
  id: string;
  batch_id: string;
  quotation_no?: string;
  buyer_name: string;
  product_name: string;
  created_at: string;
  updated_at: string;
  all_uploaded: boolean;
  docs: Record<string, ShipmentDocSlot>;
}

