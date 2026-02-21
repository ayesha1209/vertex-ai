import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import type { DocumentSummary } from "../../lib/types";
import { savePdf } from "../../lib/api";
import { DocTypeIcon } from "../ui/DocTypeIcon";

function PdfIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
    </svg>
  );
}

interface DocumentTableProps {
  documents: DocumentSummary[];
  selectedIds: Set<string>;
  onSelectOne: (id: string, checked: boolean) => void;
  onSelectAll: (checked: boolean) => void;
  onDelete: (id: string) => void;
  loading?: boolean;
}

export function DocumentTable({
  documents = [],
  selectedIds,
  onSelectOne,
  onSelectAll,
  onDelete,
  loading,
}: DocumentTableProps) {
  const safeDocs = Array.isArray(documents) ? documents : [];
  const allSelected = safeDocs.length > 0 && safeDocs.every((d) => d && selectedIds.has(d.id));
  const someSelected = selectedIds.size > 0;
  const selectAllRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = selectAllRef.current;
    if (el) el.indeterminate = someSelected && !allSelected;
  }, [someSelected, allSelected]);

  return (
    <div className="card overflow-hidden">
      {loading ? (
        <div className="flex min-h-[200px] items-center justify-center p-6 sm:min-h-[280px] sm:p-12" role="status">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" aria-hidden />
          <span className="sr-only">Loading documents…</span>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm" role="table">
            <thead>
              <tr className="bg-slate-50/70">
                <th className="w-11 px-3 py-3 sm:px-6 sm:py-4">
                  <label className="flex items-center">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      checked={allSelected}
                      onChange={(e) => onSelectAll(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                      aria-label="Select all documents"
                    />
                  </label>
                </th>
                <th className="w-[100px] px-3 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 sm:px-6 sm:py-4">Type</th>
                <th className="min-w-[100px] px-3 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 sm:min-w-[140px] sm:px-6 sm:py-4">Buyer</th>
                <th className="min-w-[100px] px-3 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 sm:min-w-[140px] sm:px-6 sm:py-4">Product</th>
                <th className="hidden w-[100px] px-6 py-4 text-xs font-semibold uppercase tracking-wide text-slate-500 sm:table-cell">Date</th>
                <th className="w-[1%] whitespace-nowrap px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-500 sm:px-6 sm:py-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {safeDocs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-slate-500 sm:px-6 sm:py-16">
                    No documents found.
                  </td>
                </tr>
              ) : (
                safeDocs.map((doc) => {
                  if (!doc || !doc.id) return null;
                  return (
                    <tr
                      key={doc.id}
                      className="group transition-all duration-150 hover:bg-slate-50/80 [&:not(:last-child)]:border-b [&:not(:last-child)]:border-slate-100"
                    >
                      <td className="px-3 py-3 sm:px-6 sm:py-4">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(doc.id)}
                          onChange={(e) => onSelectOne(doc.id, e.target.checked)}
                          className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                          aria-label={`Select ${doc.buyer_name} ${doc.product_name}`}
                        />
                      </td>
                      <td className="px-3 py-3 sm:px-6 sm:py-4">
                        <div className="flex items-center gap-2.5">
                          <DocTypeIcon type={doc.doc_type} className="h-7 w-7" />
                          <span className="text-xs font-medium uppercase text-slate-600">{doc.doc_type}</span>
                        </div>
                      </td>
                      <td className="px-3 py-3 font-medium text-slate-800 sm:px-6 sm:py-4">{doc.buyer_name}</td>
                      <td className="px-3 py-3 text-slate-700 sm:px-6 sm:py-4">{doc.product_name}</td>
                      <td className="hidden px-6 py-4 text-slate-500 sm:table-cell">
                        {new Date(doc.created_at).toLocaleDateString()}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 sm:px-6 sm:py-4">
                        <div className="flex flex-nowrap items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => savePdf(doc.id)}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200/80 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 shadow-[0_1px_2px_rgb(0_0_0_/0.04)] transition-colors hover:bg-slate-50 hover:text-slate-800 focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1"
                            title="PDF"
                            aria-label="PDF"
                          >
                            <PdfIcon className="h-3.5 w-3.5 shrink-0" />
                            <span>PDF</span>
                          </button>
                          <Link
                            to={`/documents/${doc.id}`}
                            className="inline-flex items-center rounded-lg bg-teal-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-teal-700 focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1"
                          >
                            Edit
                          </Link>
                          <button
                            type="button"
                            onClick={() => onDelete(doc.id)}
                            className="rounded-lg px-2.5 py-2 text-xs font-medium text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-1"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
