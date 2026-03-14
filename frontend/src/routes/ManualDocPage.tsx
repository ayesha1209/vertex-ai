import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { createManualDocument, listDocuments, deleteDocument } from "../lib/api";
import { DashboardLayout } from "../components/layout/DashboardLayout";
import type { DocumentSummary } from "../lib/types";

type DocType = "quotation" | "tds" | "coa" | "msds";
type ProductType = "chemical" | "engineering";

const DOC_TYPE_LABELS: Record<string, string> = {
  quotation: "Quotation",
  tds: "TDS",
  coa: "COA",
  msds: "MSDS",
  combined: "Combined",
};

function parseUtc(s: string): Date {
  if (!s.endsWith("Z") && !/[-+]\d{2}:?\d{2}$/.test(s)) return new Date(s + "Z");
  return new Date(s);
}
function fmtDate(s: string) {
  return parseUtc(s).toLocaleDateString(undefined, { dateStyle: "medium" });
}
function fmtTime(s: string) {
  return parseUtc(s).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}

// ── Create form state ─────────────────────────────────────────────────────────
interface FormState {
  buyerName: string;
  productName: string;
  docType: DocType;
  productType: ProductType;
  letterhead: "india" | "dubai";
  localExport: "local" | "export";
}

const DEFAULT_FORM: FormState = {
  buyerName: "",
  productName: "",
  docType: "quotation",
  productType: "chemical",
  letterhead: "india",
  localExport: "export",
};

export function ManualDocPage() {
  const navigate = useNavigate();

  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const res = await listDocuments({ manual: true, limit: 100 });
      // Sort newest first
      const sorted = [...res.documents].sort(
        (a, b) => parseUtc(b.created_at).getTime() - parseUtc(a.created_at).getTime()
      );
      setDocs(sorted);
      setTotal(res.total);
    } catch (e: unknown) {
      setListError(e instanceof Error ? e.message : "Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  const handleCreate = async () => {
    if (!form.buyerName.trim() || !form.productName.trim()) {
      setFormError("Buyer name and product/title are required.");
      return;
    }
    setCreating(true);
    setFormError(null);
    try {
      const doc = await createManualDocument({
        buyer_name: form.buyerName.trim(),
        product_name: form.productName.trim(),
        doc_type: form.docType,
        product_type: form.productType,
        letterhead: form.letterhead,
        local_export: form.localExport,
        html_content: "",
      });
      navigate(`/documents/${doc.id}`);
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : "Failed to create document");
      setCreating(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("Delete this document?")) return;
    setDeletingId(id);
    try {
      await deleteDocument(id);
      setDocs((prev) => prev.filter((d) => d.id !== id));
      setTotal((t) => Math.max(0, t - 1));
    } catch {
      alert("Failed to delete document.");
    } finally {
      setDeletingId(null);
    }
  };

  const openModal = () => { setForm(DEFAULT_FORM); setFormError(null); setModalOpen(true); };
  const closeModal = () => { if (!creating) setModalOpen(false); };

  return (
    <DashboardLayout title="Manual Documents" subtitle="Create and manage documents without AI generation">
      {/* Header bar */}
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <span className="text-sm text-slate-500">{total} document{total !== 1 ? "s" : ""}</span>
        </div>
        <button
          type="button"
          onClick={openModal}
          className="btn-primary btn-sm flex items-center gap-1.5"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New Document
        </button>
      </div>

      {/* Error */}
      {listError && (
        <div className="mb-4 alert-error" role="alert">{listError}</div>
      )}

      {/* Table */}
      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">Buyer</th>
              <th className="px-4 py-3">Product / Title</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Created</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-slate-400">Loading…</td>
              </tr>
            )}
            {!loading && docs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center">
                  <div className="flex flex-col items-center gap-3 text-slate-400">
                    <svg className="h-10 w-10 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <p className="text-sm font-medium">No manual documents yet</p>
                    <button type="button" onClick={openModal} className="btn-primary btn-sm">+ Create your first document</button>
                  </div>
                </td>
              </tr>
            )}
            {!loading && docs.map((doc) => (
              <tr key={doc.id} className="border-b border-slate-100 transition-colors hover:bg-slate-50/60 last:border-0">
                <td className="px-4 py-3 font-medium text-slate-800">{doc.buyer_name}</td>
                <td className="px-4 py-3 text-slate-600">{doc.product_name}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600 capitalize">
                    {DOC_TYPE_LABELS[doc.doc_type] ?? doc.doc_type}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-500 text-xs">
                  {fmtDate(doc.created_at)}<br />
                  <span className="text-slate-400">{fmtTime(doc.created_at)}</span>
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => navigate(`/documents/${doc.id}`)}
                      className="btn-outline btn-xs"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(doc.id)}
                      disabled={deletingId === doc.id}
                      className="btn-danger btn-xs"
                    >
                      {deletingId === doc.id ? "…" : "Delete"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Create modal */}
      {modalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={(e) => { if (e.target === e.currentTarget) closeModal(); }}
        >
          <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
            {/* Modal header */}
            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
              <h2 className="text-base font-semibold text-slate-800">New Manual Document</h2>
              <button
                type="button"
                onClick={closeModal}
                disabled={creating}
                className="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal body */}
            <div className="flex flex-col gap-4 px-6 py-5">
              {formError && (
                <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{formError}</div>
              )}

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-slate-600">Buyer Name <span className="text-red-500">*</span></span>
                <input
                  className="input input-sm"
                  type="text"
                  placeholder="e.g. ACME Corporation"
                  value={form.buyerName}
                  onChange={e => setForm(f => ({ ...f, buyerName: e.target.value }))}
                  autoFocus
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-slate-600">Product / Title <span className="text-red-500">*</span></span>
                <input
                  className="input input-sm"
                  type="text"
                  placeholder="e.g. Sodium Carbonate"
                  value={form.productName}
                  onChange={e => setForm(f => ({ ...f, productName: e.target.value }))}
                />
              </label>

              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold text-slate-600">Document Type</span>
                  <select className="input input-sm" value={form.docType} onChange={e => setForm(f => ({ ...f, docType: e.target.value as DocType }))}>
                    <option value="quotation">Quotation</option>
                    <option value="tds">TDS</option>
                    <option value="coa">COA</option>
                    <option value="msds">MSDS</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold text-slate-600">Product Type</span>
                  <select className="input input-sm" value={form.productType} onChange={e => setForm(f => ({ ...f, productType: e.target.value as ProductType }))}>
                    <option value="chemical">Chemical</option>
                    <option value="engineering">Engineering</option>
                  </select>
                </label>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold text-slate-600">Letterhead</span>
                  <select className="input input-sm" value={form.letterhead} onChange={e => setForm(f => ({ ...f, letterhead: e.target.value as "india" | "dubai" }))}>
                    <option value="india">India</option>
                    <option value="dubai">Dubai</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold text-slate-600">Local / Export</span>
                  <select className="input input-sm" value={form.localExport} onChange={e => setForm(f => ({ ...f, localExport: e.target.value as "local" | "export" }))}>
                    <option value="export">Export ($)</option>
                    <option value="local">Local (Rs.)</option>
                  </select>
                </label>
              </div>
            </div>

            {/* Modal footer */}
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-6 py-4">
              <button type="button" onClick={closeModal} disabled={creating} className="btn-ghost btn-sm">Cancel</button>
              <button type="button" onClick={handleCreate} disabled={creating} className="btn-primary btn-sm">
                {creating ? "Creating…" : "Create & Open Editor"}
              </button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
