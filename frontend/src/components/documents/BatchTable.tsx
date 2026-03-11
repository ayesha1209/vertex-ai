import { useNavigate } from "react-router-dom";
import type { BatchSummary } from "../../lib/types";

function formatTime(dateStr: string): string {
  const date = new Date(dateStr);
  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = date.getMinutes().toString().padStart(2, "0");
  return `${hours}:${minutes}`;
}

interface BatchTableProps {
  batches: BatchSummary[];
  loading?: boolean;
}

export function BatchTable({ batches = [], loading }: BatchTableProps) {
  const navigate = useNavigate();

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
                    colSpan={6}
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
                      {new Date(batch.created_at).toLocaleDateString()}
                    </td>
                    <td className="hidden px-6 py-4 text-slate-500 sm:table-cell">
                      {formatTime(batch.created_at)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-right sm:px-6 sm:py-4">
                      <span className="inline-flex rounded-lg bg-teal-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-teal-700">
                        View
                      </span>
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
