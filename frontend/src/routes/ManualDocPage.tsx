import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { createManualDocument, listDocuments, deleteDocument, deleteDocuments } from "../lib/api";
import { DashboardLayout } from "../components/layout/DashboardLayout";
import { ConfirmModal } from "../components/ui/ConfirmModal";
import type { DocumentSummary } from "../lib/types";

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

function parseDateSafe(s: string | null | undefined): number | null {
  if (s == null || String(s).trim() === "") return null;
  const d = new Date(String(s).trim());
  return Number.isNaN(d.getTime()) ? null : d.getTime();
}

export function ManualDocPage() {
  const navigate = useNavigate();

  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [letterhead, setLetterhead] = useState<"india" | "dubai">("india");
  const [productType, setProductType] = useState<"chemical" | "engineering">("chemical");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleteSelectedModalOpen, setDeleteSelectedModalOpen] = useState(false);
  const [deleteSelectedLoading, setDeleteSelectedLoading] = useState(false);

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

  const fromTs = parseDateSafe(dateFrom || null);
  const toTs = parseDateSafe(dateTo || null);
  const filteredDocs = useMemo(() => {
    if (fromTs == null && toTs == null) return docs;
    return docs.filter((d) => {
      const t = parseUtc(d.created_at).getTime();
      if (fromTs != null && t < fromTs) return false;
      if (toTs != null && t > toTs) return false;
      return true;
    });
  }, [docs, fromTs, toTs]);

  const toggleSelectOne = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const toggleSelectAll = (checked: boolean) => {
    if (checked) setSelectedIds(new Set(filteredDocs.map((d) => d.id)));
    else setSelectedIds(new Set());
  };
  const allSelected = filteredDocs.length > 0 && filteredDocs.every((d) => selectedIds.has(d.id));

  const handleDeleteSelected = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    setDeleteSelectedLoading(true);
    setDeleteSelectedModalOpen(false);
    try {
      await deleteDocuments(ids);
      setDocs((prev) => prev.filter((d) => !selectedIds.has(d.id)));
      setTotal((t) => Math.max(0, t - ids.length));
      setSelectedIds(new Set());
    } catch {
      alert("Failed to delete some documents.");
    } finally {
      setDeleteSelectedLoading(false);
    }
  };

  const handleCreate = () => {
    if (creating) return;
    setCreateModalOpen(true);
  };

  const handleCreateConfirm = async () => {
    if (creating) return;
    setCreating(true);
    try {
      // Map letterhead to sensible Local/Export default:
      // India → local (INR), Dubai → export (USD).
      const localExport = letterhead === "india" ? "local" : "export";
      const doc = await createManualDocument({
        buyer_name: "—",
        product_name: "Manual Document",
        doc_type: "quotation",
        product_type: productType,
        letterhead,
        local_export: localExport,
        html_content: "",
      });
      setCreateModalOpen(false);
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
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-slate-500">
            {dateFrom || dateTo
              ? `${filteredDocs.length} of ${total} document${total !== 1 ? "s" : ""}`
              : `${total} document${total !== 1 ? "s" : ""}`}
          </span>
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 shadow-sm">
            <svg className="h-3.5 w-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="h-8 min-w-0 rounded border border-slate-200 bg-slate-50/50 px-2 text-xs text-slate-700 focus:border-teal-400 focus:outline-none focus:ring-1 focus:ring-teal-400"
              aria-label="From date"
            />
            <span className="text-slate-300 text-xs">–</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="h-8 min-w-0 rounded border border-slate-200 bg-slate-50/50 px-2 text-xs text-slate-700 focus:border-teal-400 focus:outline-none focus:ring-1 focus:ring-teal-400"
              aria-label="To date"
            />
            {(dateFrom || dateTo) && (
              <button
                type="button"
                onClick={() => { setDateFrom(""); setDateTo(""); }}
                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                aria-label="Clear date filter"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {selectedIds.size > 0 && (
            <button
              type="button"
              onClick={() => setDeleteSelectedModalOpen(true)}
              disabled={deleteSelectedLoading}
              className="btn-outline btn-sm border-red-200 text-red-700 hover:bg-red-50"
            >
              Delete selected ({selectedIds.size})
            </button>
          )}
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
      </div>

      {listError && (
        <div className="mb-4 alert-error" role="alert">{listError}</div>
      )}

      {/* Create modal */}
      {createModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget && !creating) setCreateModalOpen(false);
          }}
        >
          <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
            <div className="border-b border-slate-100 px-6 py-4">
              <h2 className="text-base font-semibold text-slate-800">New manual document</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Choose the letterhead and product type for this quotation. You can set the
                document name inside the editor when you save.
              </p>
            </div>
            <div className="flex flex-col gap-4 px-6 py-5 text-sm">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-slate-600">Letterhead</span>
                <select
                  className="select select-sm"
                  value={letterhead}
                  onChange={(e) =>
                    setLetterhead(e.target.value === "dubai" ? "dubai" : "india")
                  }
                >
                  <option value="india">India</option>
                  <option value="dubai">Dubai</option>
                </select>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-slate-600">Product type</span>
                <select
                  className="select select-sm"
                  value={productType}
                  onChange={(e) =>
                    setProductType(
                      e.target.value === "engineering" ? "engineering" : "chemical",
                    )
                  }
                >
                  <option value="chemical">Chemical</option>
                  <option value="engineering">Engineering</option>
                </select>
              </label>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-6 py-4">
              <button
                type="button"
                className="btn-ghost btn-sm"
                onClick={() => !creating && setCreateModalOpen(false)}
                disabled={creating}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary btn-sm"
                onClick={handleCreateConfirm}
                disabled={creating}
              >
                {creating ? "Opening…" : "Create & open"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="w-10 px-3 py-3 text-center">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={(e) => toggleSelectAll(e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                    aria-label="Select all visible rows"
                  />
                </th>
                <th className="px-4 py-3">Document Name</th>
                <th className="px-4 py-3">Created by</th>
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
                        Create your first document
                      </button>
                    </div>
                  </td>
                </tr>
              )}
              {!loading && filteredDocs.length === 0 && docs.length > 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-500">No documents in this date range.</td>
                </tr>
              )}
              {!loading && filteredDocs.map((doc) => (
                <tr key={doc.id} className="border-b border-slate-100 transition-colors hover:bg-slate-50/60 last:border-0">
                  <td className="px-3 py-2 text-center align-middle">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(doc.id)}
                      onChange={() => toggleSelectOne(doc.id)}
                      className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                      aria-label={`Select ${doc.product_name || "document"}`}
                    />
                  </td>
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

      <ConfirmModal
        open={deleteSelectedModalOpen}
        title="Delete selected documents?"
        message={`${selectedIds.size} document(s) will be permanently deleted. This cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        loading={deleteSelectedLoading}
        onCancel={() => !deleteSelectedLoading && setDeleteSelectedModalOpen(false)}
        onConfirm={handleDeleteSelected}
      />
    </DashboardLayout>
  );
}
