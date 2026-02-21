import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useActiveJob } from "../context/ActiveJobContext";
import { PageLayout } from "../components/ui/PageLayout";
import { generateBatch } from "../lib/api";
import { getStoredPreviewRows, setStoredPreviewRows } from "../hooks/useJobStream";
import type { RowPreview } from "../lib/types";

/** Parse date string (YYYY-MM-DD, DD/MM/YYYY, or ISO) to timestamp for comparison; null if invalid. */
function parseDateSafe(s: string | null | undefined): number | null {
  if (s == null || String(s).trim() === "") return null;
  const str = String(s).trim();
  const d = new Date(str);
  if (Number.isNaN(d.getTime())) return null;
  return d.getTime();
}

export function PreviewPage() {
  const { setActiveJobId } = useActiveJob();
  const [rows, setRows] = useState<RowPreview[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const loadedRef = useRef(false);

  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    const stored = getStoredPreviewRows();
    if (Array.isArray(stored) && stored.length > 0) {
      setRows(stored as RowPreview[]);
      setSelected(new Set(stored.map((r: RowPreview) => r.id)));
    } else {
      navigate("/", { replace: true });
    }
  }, [navigate]);

  const fromTs = parseDateSafe(dateFrom || null);
  const toTs = parseDateSafe(dateTo || null);
  const filteredRows = useMemo(() => {
    if (fromTs == null && toTs == null) return rows;
    return rows.filter((r) => {
      const t = parseDateSafe(r.date ?? null);
      if (t == null) return true;
      if (fromTs != null && t < fromTs) return false;
      if (toTs != null && t > toTs) return false;
      return true;
    });
  }, [rows, fromTs, toTs]);

  const toggleOne = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = (checked: boolean) => {
    if (checked) setSelected(new Set(filteredRows.map((r) => r.id)));
    else setSelected(new Set());
  };

  const handleCellChange = (rowId: number, field: keyof RowPreview, value: string) => {
    const updated = rows.map((r) =>
      r.id === rowId ? { ...r, [field]: value } : r
    );
    setRows(updated);
    setStoredPreviewRows(updated);
  };

  const rowsToGenerate = filteredRows.filter((r) => selected.has(r.id));
  const allSelected = filteredRows.length > 0 && filteredRows.every((r) => selected.has(r.id));

  const startGeneration = async (which: RowPreview[]) => {
    if (which.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const { job_id } = await generateBatch(which);
      setActiveJobId(job_id);
      navigate(`/generate?job=${job_id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to start generation");
    } finally {
      setLoading(false);
    }
  };

  if (rows.length === 0) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center page-container">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" aria-hidden />
        <span className="sr-only">Loading preview…</span>
      </div>
    );
  }

  return (
    <PageLayout
      step="Step 2 of 3"
      title="Preview rows"
      subtitle={
        dateFrom || dateTo
          ? `${filteredRows.length} of ${rows.length} row(s) in date range. Select rows and generate.`
          : `${rows.length} row(s). Filter by date (optional), select which to generate, then "Generate selected" or "Generate all in range".`
      }
      toolbar={
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-wrap items-center gap-2 rounded border border-slate-200 bg-slate-50/50 px-3 py-2">
            <span className="text-sm font-medium text-slate-600">Date filter</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="input max-w-[140px] text-sm"
              aria-label="From date"
            />
            <span className="text-slate-400">to</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="input max-w-[140px] text-sm"
              aria-label="To date"
            />
          </div>
          <button
            type="button"
            onClick={() => startGeneration(rowsToGenerate)}
            disabled={loading || rowsToGenerate.length === 0}
            className="btn-primary"
          >
            {loading ? "Starting…" : `Generate selected (${rowsToGenerate.length})`}
          </button>
          <button
            type="button"
            onClick={() => startGeneration(filteredRows)}
            disabled={loading}
            className="btn-outline"
          >
            Generate all in range ({filteredRows.length})
          </button>
        </div>
      }
    >
      {error && (
        <div className="mb-4 alert-error" role="alert">
          {error}
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="overflow-x-auto" role="region" aria-label="Preview table">
          <table className="min-w-max w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50/80">
              <tr>
                <th className="w-12 shrink-0 px-3 py-3.5">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={(e) => toggleAll(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                      aria-label="Select all visible rows"
                    />
                  </label>
                </th>
                <th className="min-w-[120px] px-3 py-3.5 font-medium text-slate-700">Buyer</th>
                <th className="min-w-[140px] px-3 py-3.5 font-medium text-slate-700">Product</th>
                <th className="hidden min-w-[110px] px-3 py-3.5 font-medium text-slate-700 sm:table-cell">Date</th>
                <th className="hidden min-w-[140px] px-3 py-3.5 font-medium text-slate-700 sm:table-cell">Company</th>
                <th className="hidden min-w-[120px] px-3 py-3.5 font-medium text-slate-700 sm:table-cell">Quotation no</th>
                <th className="hidden min-w-[80px] px-3 py-3.5 font-medium text-slate-700 md:table-cell">Qty</th>
                <th className="hidden min-w-[70px] px-3 py-3.5 font-medium text-slate-700 md:table-cell">Unit</th>
                <th className="hidden min-w-[100px] px-3 py-3.5 font-medium text-slate-700 lg:table-cell">Country</th>
                <th className="hidden min-w-[90px] px-3 py-3.5 font-medium text-slate-700 lg:table-cell">Port</th>
                <th className="hidden min-w-[100px] px-3 py-3.5 font-medium text-slate-700 xl:table-cell">Incoterm</th>
                <th className="hidden min-w-[100px] px-3 py-3.5 font-medium text-slate-700 xl:table-cell">Payment</th>
                <th className="hidden min-w-[100px] px-3 py-3.5 font-medium text-slate-700 xl:table-cell">Remarks</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredRows.map((row, idx) => (
                <tr
                  key={row.id}
                  className={
                    selected.has(row.id)
                      ? "bg-teal-50/50"
                      : "hover:bg-slate-50/80 transition-colors"
                  }
                >
                  <td className="px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={selected.has(row.id)}
                      onChange={() => toggleOne(row.id)}
                      className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                      aria-label={`Select row ${idx + 1}`}
                    />
                  </td>
                  <td className="min-w-[120px] px-3 py-2.5">
                    <input
                      className="input min-h-[36px] w-full min-w-0 text-sm"
                      value={row.buyer_name ?? ""}
                      onChange={(e) => handleCellChange(row.id, "buyer_name", e.target.value)}
                      title={row.buyer_name ?? ""}
                      aria-label={`Buyer row ${idx + 1}`}
                    />
                  </td>
                  <td className="min-w-[140px] px-3 py-2.5">
                    <input
                      className="input min-h-[36px] w-full min-w-0 text-sm"
                      value={row.product_name ?? ""}
                      onChange={(e) => handleCellChange(row.id, "product_name", e.target.value)}
                      title={row.product_name ?? ""}
                      aria-label={`Product row ${idx + 1}`}
                    />
                  </td>
                  <td className="hidden min-w-[110px] px-3 py-2.5 text-slate-700 sm:table-cell" aria-label={`Date row ${idx + 1}`}>
                    {row.date ?? "—"}
                  </td>
                  <td className="hidden min-w-[140px] px-3 py-2.5 sm:table-cell">
                    <input
                      className="input min-h-[36px] w-full min-w-0 text-sm"
                      value={row.company_name ?? ""}
                      onChange={(e) => handleCellChange(row.id, "company_name", e.target.value)}
                      title={row.company_name ?? ""}
                      placeholder="Company"
                    />
                  </td>
                  <td className="hidden min-w-[120px] px-3 py-2.5 sm:table-cell">
                    <input
                      className="input min-h-[36px] w-full min-w-0 text-sm"
                      value={row.quotation_no ?? ""}
                      onChange={(e) => handleCellChange(row.id, "quotation_no", e.target.value)}
                      title={row.quotation_no ?? ""}
                      placeholder="Auto if empty"
                    />
                  </td>
                  <td className="hidden min-w-[80px] px-3 py-2.5 md:table-cell">
                    <input
                      className="input min-h-[36px] w-full min-w-0 text-sm"
                      value={(row.quantity as string) ?? ""}
                      onChange={(e) => handleCellChange(row.id, "quantity", e.target.value)}
                    />
                  </td>
                  <td className="hidden min-w-[70px] px-3 py-2.5 md:table-cell">
                    <input
                      className="input min-h-[36px] w-full min-w-0 text-sm"
                      value={(row.unit as string) ?? ""}
                      onChange={(e) => handleCellChange(row.id, "unit", e.target.value)}
                    />
                  </td>
                  <td className="hidden min-w-[100px] px-3 py-2.5 lg:table-cell">
                    <input
                      className="input min-h-[36px] w-full min-w-0 text-sm"
                      value={(row.country as string) ?? ""}
                      onChange={(e) => handleCellChange(row.id, "country", e.target.value)}
                      title={(row.country as string) ?? ""}
                    />
                  </td>
                  <td className="hidden min-w-[90px] px-3 py-2.5 lg:table-cell">
                    <input
                      className="input min-h-[36px] w-full min-w-0 text-sm"
                      value={(row.port as string) ?? ""}
                      onChange={(e) => handleCellChange(row.id, "port", e.target.value)}
                      title={(row.port as string) ?? ""}
                    />
                  </td>
                  <td className="hidden min-w-[100px] px-3 py-2.5 xl:table-cell">
                    <input
                      className="input min-h-[36px] w-full min-w-0 text-sm"
                      value={(row.incoterm as string) ?? ""}
                      onChange={(e) => handleCellChange(row.id, "incoterm", e.target.value)}
                      title={(row.incoterm as string) ?? ""}
                    />
                  </td>
                  <td className="hidden min-w-[100px] px-3 py-2.5 xl:table-cell">
                    <input
                      className="input min-h-[36px] w-full min-w-0 text-sm"
                      value={(row.payment_terms as string) ?? ""}
                      onChange={(e) => handleCellChange(row.id, "payment_terms", e.target.value)}
                      title={(row.payment_terms as string) ?? ""}
                    />
                  </td>
                  <td className="hidden min-w-[100px] px-3 py-2.5 xl:table-cell">
                    <input
                      className="input min-h-[36px] w-full min-w-0 text-sm"
                      value={(row.remarks as string) ?? ""}
                      onChange={(e) => handleCellChange(row.id, "remarks", e.target.value)}
                      title={(row.remarks as string) ?? ""}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </PageLayout>
  );
}
