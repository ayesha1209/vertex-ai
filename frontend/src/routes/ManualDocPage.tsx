import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { createManualDocument, listDocuments, deleteDocument } from "../lib/api";
import { DashboardLayout } from "../components/layout/DashboardLayout";
import type { DocumentSummary } from "../lib/types";

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

export function ManualDocPage() {
  const navigate = useNavigate();

  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const res = await listDocuments({ manual: true, limit: 100 });
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
    if (creating) return;
    setCreating(true);
    try {
      const doc = await createManualDocument({
        buyer_name: "—",
        product_name: "Manual Document",
        doc_type: "quotation",
        product_type: "chemical",
        letterhead: "india",
        local_export: "export",
        html_content: "",
      });
      navigate(`/documents/${doc.id}`);
    } catch {
      setCreating(false);
      alert("Failed to create document. Please try again.");
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

  return (
    <DashboardLayout title="Manual Documents" subtitle="Write and format documents directly — no AI generation">
      {/* Header bar */}
      <div className="mb-6 flex items-center justify-between gap-4">
        <span className="text-sm text-slate-500">{total} document{total !== 1 ? "s" : ""}</span>
        <button
          type="button"
          onClick={handleCreate}
          disabled={creating}
          className="btn-primary btn-sm flex items-center gap-1.5"
        >
          {creating ? (
            <>
              <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Opening…
            </>
          ) : (
            <>
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              New Document
            </>
          )}
        </button>
      </div>

      {listError && (
        <div className="mb-4 alert-error" role="alert">{listError}</div>
      )}

      {/* Table */}
      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Document Name</th>
                <th className="px-4 py-3">Created by</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Date</th>
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
                      <p className="text-sm font-medium">No documents yet</p>
                      <button type="button" onClick={handleCreate} disabled={creating} className="btn-primary btn-sm">
                        + Create your first document
                      </button>
                    </div>
                  </td>
                </tr>
              )}
              {!loading && docs.map((doc) => (
                <tr key={doc.id} className="border-b border-slate-100 transition-colors hover:bg-slate-50/60 last:border-0">
                  <td className="px-4 py-3 font-medium text-slate-800">
                    {!doc.product_name || doc.product_name === "Manual Document"
                      ? <span className="text-slate-400 italic">Untitled</span>
                      : doc.product_name}
                  </td>
                  <td className="px-4 py-3 text-slate-600 text-sm">
                    {doc.employee_name
                      ? doc.employee_name
                      : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600 capitalize">
                      {DOC_TYPE_LABELS[doc.doc_type] ?? doc.doc_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">
                    {fmtDate(doc.created_at)}
                    <span className="ml-1.5 text-slate-400">{fmtTime(doc.created_at)}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => navigate(`/documents/${doc.id}`)}
                        className="btn-outline btn-xs"
                      >
                        Open
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
    </DashboardLayout>
  );
}
