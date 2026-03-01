import type {
  DocumentInDB,
  DocumentSummary,
  GenerateRowResponse,
  ListDocumentsResponse,
  RowPreview,
  UploadPreviewResponse
} from "./types";

// In dev, use relative /api so Vite proxy forwards to backend (avoids CORS and "Failed to fetch")
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "/api" : "http://localhost:8000/api");

export async function uploadPreview(file: File): Promise<UploadPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/upload-preview`, {
    method: "POST",
    body: formData
  });
  if (!res.ok) {
    const error = await res.json().catch(() => null);
    throw new Error(error?.detail || "Failed to upload file");
  }
  return res.json();
}

export async function generateRow(
  row: RowPreview
): Promise<GenerateRowResponse> {
  const res = await fetch(`${API_BASE_URL}/generate-row`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ row })
  });
  if (!res.ok) {
    const error = await res.json().catch(() => null);
    throw new Error(error?.detail || "Failed to generate documents");
  }
  return res.json();
}

export async function generateBatch(rows: RowPreview[]): Promise<{ job_id: string }> {
  const res = await fetch(`${API_BASE_URL}/generate-batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => null);
    throw new Error(error?.detail || "Failed to start generation");
  }
  return res.json();
}

/** SSE stream URL - use same origin in dev (proxied), else full backend URL */
export async function checkDatabaseHealth(): Promise<{ ok: boolean; message?: string; error?: string }> {
  const res = await fetch(`${API_BASE_URL}/health/db`);
  const data = await res.json().catch(() => ({}));
  return data;
}

export function getJobStreamUrl(jobId: string): string {
  const base = import.meta.env.VITE_API_BASE_URL;
  if (base) {
    const host = base.replace(/\/api\/?$/, "");
    return `${host}/api/jobs/${jobId}/stream`;
  }
  return `/api/jobs/${jobId}/stream`;
}

export async function listDocuments(params?: {
  q?: string;
  buyer?: string;
  product?: string;
  doc_type?: string;
  product_type?: "chemical" | "engineering";
  from_date?: string;
  to_date?: string;
  skip?: number;
  limit?: number;
}): Promise<ListDocumentsResponse> {
  const usp = new URLSearchParams();
  if (params?.q?.trim()) usp.set("q", params.q.trim());
  if (params?.buyer) usp.set("buyer", params.buyer);
  if (params?.product) usp.set("product", params.product);
  if (params?.doc_type) usp.set("doc_type", params.doc_type);
  if (params?.product_type) usp.set("product_type", params.product_type);
  if (params?.from_date) usp.set("from_date", params.from_date);
  if (params?.to_date) usp.set("to_date", params.to_date);
  if (params?.skip != null) usp.set("skip", String(params.skip));
  if (params?.limit != null) usp.set("limit", String(params.limit));

  const res = await fetch(`${API_BASE_URL}/documents?${usp.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const d = err?.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? d[0]?.msg : null;
    throw new Error(msg || "Failed to list documents");
  }
  return res.json();
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    if (res.status === 404) throw new Error("Document not found");
    throw new Error("Failed to delete document");
  }
}

export async function deleteDocuments(ids: string[]): Promise<{ deleted: number }> {
  const res = await fetch(`${API_BASE_URL}/documents`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
  if (!res.ok) throw new Error("Failed to delete documents");
  return res.json();
}

export async function getDocument(id: string): Promise<DocumentInDB> {
  const res = await fetch(`${API_BASE_URL}/documents/${id}`);
  if (!res.ok) {
    throw new Error("Failed to fetch document");
  }
  return res.json();
}

export async function updateDocument(
  id: string,
  html_content: string
): Promise<DocumentInDB> {
  const res = await fetch(`${API_BASE_URL}/documents/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ html_content })
  });
  if (!res.ok) {
    const error = await res.json().catch(() => null);
    throw new Error(error?.detail || "Failed to update document");
  }
  return res.json();
}

/** Save document as PDF file (opens save dialog). */
export async function savePdf(id: string): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/documents/${encodeURIComponent(id)}/pdf`
  );
  if (!res.ok) {
    throw new Error("Failed to get PDF");
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition");
  let filename = "document.pdf";
  if (disposition) {
    const match = disposition.match(/filename="(.+?)"/i);
    if (match?.[1]) {
      filename = match[1];
    }
  }
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

/** Save multiple documents as PDFs (one after another, with short delay). */
export async function saveAllPdf(ids: string[]): Promise<void> {
  for (const id of ids) {
    // eslint-disable-next-line no-await-in-loop
    await savePdf(id);
    // eslint-disable-next-line no-await-in-loop
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

