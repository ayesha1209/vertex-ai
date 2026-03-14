import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import type { BatchSummary } from "../../lib/types";

/** Parse API timestamp as UTC when no timezone suffix (backend stores UTC). */
function parseUtc(dateStr: string): Date {
  const s = dateStr.trim();
  if (!s.endsWith("Z") && !/[-+]\d{2}:?\d{2}$/.test(s)) return new Date(s + "Z");
  return new Date(s);
}

/** Format time in user's local timezone (API sends UTC). */
function formatTime(dateStr: string): string {
  return parseUtc(dateStr).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}

interface BatchTableProps {
  batches: BatchSummary[];
  selectedBatchIds: Set<string>;
  onSelectOne: (batchId: string, checked: boolean) => void;
  onSelectAll: (checked: boolean) => void;
  loading?: boolean;
  onDelete?: (batchId: string) => void;
}

export function BatchTable({
  batches = [],
  selectedBatchIds = new Set(),
  onSelectOne,
  onSelectAll,
  loading,
  onDelete,
}: BatchTableProps) {
  const navigate = useNavigate();
  const allSelected = batches.length > 0 && batches.every((b) => selectedBatchIds.has(b.batch_id));
  const someSelected = selectedBatchIds.size > 0;
  const selectAllRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = someSelected && !allSelected;
  }, [someSelected, allSelected]);

  const handleDelete = (e: React.MouseEvent, batchId: string) => {
    e.stopPropagation();
    onDelete?.(batchId);
  };

  return (
    <div className="card overflow-hidden">
      {loading ? (
        <div
          className="flex min-h-[200px] items-center justify-center p-6 sm:min-h-[280px] sm:p-12"
          role="status"
        >
          <div
            className="h-8 w-8 animate-spin rounded-full border-2 border-teal-500 border-t-transparent"
            aria-hidden
          />
          <span className="sr-only">Loading batches…</span>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm" role="table">
            <thead>
              <tr className="bg-slate-50/70">
                <th className="w-11 px-3 py-3 sm:px-6 sm:py-4" onClick={(e) => e.stopPropagation()}>
                  <label className="flex items-center">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      checked={allSelected}
                      onChange={(e) => onSelectAll(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                      aria-label="Select all batches"
                    />
                  </label>
                </th>
                <th className="min-w-[100px] px-3 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 sm:min-w-[140px] sm:px-6 sm:py-4">
                  Buyer
                </th>
                <th className="min-w-[100px] px-3 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 sm:min-w-[140px] sm:px-6 sm:py-4">
                  Product
                </th>
                <th className="w-[120px] px-3 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 sm:px-6 sm:py-4">
                  Entered by
                </th>
                <th className="hidden w-[100px] px-6 py-4 text-xs font-semibold uppercase tracking-wide text-slate-500 sm:table-cell">
                  Date
                </th>
                <th className="hidden w-[80px] px-6 py-4 text-xs font-semibold uppercase tracking-wide text-slate-500 sm:table-cell">
                  Time
                </th>
                <th className="w-[1%] whitespace-nowrap px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-500 sm:px-6 sm:py-4">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {batches.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-4 py-12 text-center text-slate-500 sm:px-6 sm:py-16"
                  >
                    No batches found. Generate documents from Upload to see batches here.
                  </td>
                </tr>
              ) : (
                batches.map((batch) => (
                  <tr
                    key={batch.batch_id}
                    role="button"
                    tabIndex={0}
                    onClick={() => navigate(`/documents/batch/${batch.batch_id}`)}
                    onKeyDown={(e) =>
                      e.key === "Enter" &&
                      navigate(`/documents/batch/${batch.batch_id}`)
                    }
                    className="group cursor-pointer transition-all duration-150 [&:not(:last-child)]:border-b [&:not(:last-child)]:border-slate-100 hover:bg-slate-50/80 focus:bg-slate-50/70"
                    aria-label={`View documents for ${batch.buyer_name} ${batch.product_name}`}
                  >
                    <td className="px-3 py-3 sm:px-6 sm:py-4" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedBatchIds.has(batch.batch_id)}
                        onChange={(e) => onSelectOne(batch.batch_id, e.target.checked)}
                        className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                        aria-label={`Select ${batch.buyer_name} ${batch.product_name}`}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </td>
                    <td className="px-3 py-3 font-medium text-slate-800 sm:px-6 sm:py-4">
                      {batch.buyer_name}
                    </td>
                    <td className="px-3 py-3 text-slate-700 sm:px-6 sm:py-4">
                      {batch.product_name}
                    </td>
                    <td className="px-3 py-3 text-slate-600 sm:px-6 sm:py-4">
                      {batch.employee_name ?? "—"}
                    </td>
                    <td className="hidden px-6 py-4 text-slate-500 sm:table-cell">
                      {parseUtc(batch.created_at).toLocaleDateString(undefined, { dateStyle: "short" })}
                    </td>
                    <td className="hidden px-6 py-4 text-slate-500 sm:table-cell">
                      {formatTime(batch.created_at)}
                    </td>
                    <td
                      className="whitespace-nowrap px-3 py-3 text-right sm:px-6 sm:py-4"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex items-center justify-end gap-2">
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={() => navigate(`/documents/batch/${batch.batch_id}`)}
                          onKeyDown={(e) => e.key === "Enter" && navigate(`/documents/batch/${batch.batch_id}`)}
                          className="inline-flex rounded-lg bg-teal-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-teal-700"
                        >
                          View
                        </span>
                        {onDelete && (
                          <button
                            type="button"
                            onClick={(e) => handleDelete(e, batch.batch_id)}
                            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-50 hover:text-red-600"
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
