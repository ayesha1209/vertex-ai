import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useActiveJob } from "../context/ActiveJobContext";
import { PageLayout } from "../components/ui/PageLayout";
import { generateBatch } from "../lib/api";
import { getStoredPreviewRows, setStoredPreviewRows } from "../hooks/useJobStream";
import type { RowPreview } from "../lib/types";

function parseDateSafe(s: string | null | undefined): number | null {
  if (s == null || String(s).trim() === "") return null;
  const d = new Date(String(s).trim());
  return Number.isNaN(d.getTime()) ? null : d.getTime();
}

function fmtDisplayDate(s: string | null | undefined) {
  if (!s) return null;
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString(undefined, { dateStyle: "medium" });
}

function Pill({ label, color }: { label: string; color: "teal" | "amber" | "slate" }) {
  const cls = {
    teal: "bg-teal-50 text-teal-700 border border-teal-200",
    amber: "bg-amber-50 text-amber-700 border border-amber-200",
    slate: "bg-slate-100 text-slate-600 border border-slate-200",
  }[color];
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${cls}`}>
      {label}
    </span>
  );
}

function FieldInput({
  label,
  value,
  onChange,
  multiline = false,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      {multiline ? (
        <textarea
          className="min-h-[60px] resize-y rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800 shadow-sm focus:border-teal-400 focus:outline-none focus:ring-1 focus:ring-teal-400"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
        />
      ) : (
        <input
          type={type}
          className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-800 shadow-sm focus:border-teal-400 focus:outline-none focus:ring-1 focus:ring-teal-400"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
        />
      )}
    </label>
  );
}

function FieldSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      <select
        className="h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-800 shadow-sm focus:border-teal-400 focus:outline-none focus:ring-1 focus:ring-teal-400"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function ExpandedRowEditor({
  row,
  onChange,
}: {
  row: RowPreview;
  onChange: (field: keyof RowPreview, value: string) => void;
}) {
  const f = (field: keyof RowPreview) => String(row[field] ?? "");
  return (
    <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-5">
      <div className="mx-auto max-w-5xl space-y-4">
        {/* Section: Identification */}
        <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400">Identification</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <FieldInput label="Buyer name" value={f("buyer_name")} onChange={(v) => onChange("buyer_name", v)} multiline />
          <FieldInput label="Product(s)" value={f("product_name")} onChange={(v) => onChange("product_name", v)} multiline placeholder="Comma-separated for multiple" />
          <FieldInput label="Company / Supplier" value={f("company_name")} onChange={(v) => onChange("company_name", v)} />
          <FieldInput label="Employee name" value={f("employee_name")} onChange={(v) => onChange("employee_name", v)} />
          <FieldInput label="Quotation no" value={f("quotation_no")} onChange={(v) => onChange("quotation_no", v)} placeholder="Auto-generated if blank" />
          <FieldInput label="Date" value={f("date")} onChange={(v) => onChange("date", v)} placeholder="DD/MM/YYYY" />
          <FieldInput label="Buyer ref no" value={f("buyer_enquir_ref_no")} onChange={(v) => onChange("buyer_enquir_ref_no", v)} />
          <FieldInput label="Address" value={f("address")} onChange={(v) => onChange("address", v)} multiline />
        </div>

        {/* Section: Settings */}
        <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400">Settings</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <FieldSelect
            label="Letterhead"
            value={f("letterhead")}
            onChange={(v) => onChange("letterhead", v)}
            options={[
              { value: "", label: "— Not set" },
              { value: "india", label: "India" },
              { value: "dubai", label: "Dubai" },
            ]}
          />
          <FieldSelect
            label="Local / Export"
            value={f("local_export")}
            onChange={(v) => onChange("local_export", v)}
            options={[
              { value: "", label: "— Not set" },
              { value: "local", label: "Local (₹ INR)" },
              { value: "export", label: "Export ($ USD)" },
            ]}
          />
          <FieldInput
            label="Docs to generate"
            value={f("doc_types")}
            onChange={(v) => onChange("doc_types", v)}
            placeholder="q,tds,coa,msds (empty = all)"
          />
        </div>

        {/* Section: Product details */}
        <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400">Product details</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <FieldInput label="Manufacturer" value={f("manufacturer_name")} onChange={(v) => onChange("manufacturer_name", v)} />
          <FieldInput label="Product description" value={f("product_description")} onChange={(v) => onChange("product_description", v)} multiline />
          <FieldInput label="HSN code" value={f("hsn_code")} onChange={(v) => onChange("hsn_code", v)} placeholder="Auto-generated if blank" />
          <FieldInput label="CAS no" value={f("cas_no")} onChange={(v) => onChange("cas_no", v)} />
          <FieldInput label="Quantity" value={f("quantity")} onChange={(v) => onChange("quantity", v)} />
          <FieldInput label="Unit" value={f("unit")} onChange={(v) => onChange("unit", v)} placeholder="e.g. MT, kg" />
          <FieldInput label="Packing" value={f("type_of_packing")} onChange={(v) => onChange("type_of_packing", v)} />
          <FieldInput label="Price" value={f("price")} onChange={(v) => onChange("price", v)} placeholder="Unit price (AI generates if blank)" />
          <FieldInput label="Price FOB/CIF" value={f("price_fob_cif")} onChange={(v) => onChange("price_fob_cif", v)} />
        </div>

        {/* Section: Shipping */}
        <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400">Shipping & Terms</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <FieldInput label="Country" value={f("country")} onChange={(v) => onChange("country", v)} />
          <FieldInput label="Port of loading" value={f("port_of_loading")} onChange={(v) => onChange("port_of_loading", v)} />
          <FieldInput label="Port of unloading" value={f("port_of_unloading")} onChange={(v) => onChange("port_of_unloading", v)} />
          <FieldInput label="Unloading country" value={f("unloading_country")} onChange={(v) => onChange("unloading_country", v)} />
          <FieldInput label="Incoterm" value={f("incoterm")} onChange={(v) => onChange("incoterm", v)} />
          <FieldInput label="Payment terms" value={f("payment_terms")} onChange={(v) => onChange("payment_terms", v)} />
          <FieldInput label="Transport mode" value={f("transportation")} onChange={(v) => onChange("transportation", v)} />
          <FieldInput label="Email" value={f("email_id")} onChange={(v) => onChange("email_id", v)} />
          <FieldInput label="Contact no" value={f("contact_no")} onChange={(v) => onChange("contact_no", v)} />
          <FieldInput label="Remarks" value={f("remarks")} onChange={(v) => onChange("remarks", v)} multiline />
        </div>
      </div>
    </div>
  );
}

export function PreviewPage() {
  const { setActiveJobId } = useActiveJob();
  const [rows, setRows] = useState<RowPreview[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedRowId, setExpandedRowId] = useState<number | null>(null);
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
      r.id === rowId ? { ...r, [field]: value || null } : r
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
          ? `${filteredRows.length} of ${rows.length} row(s) in date range.`
          : `${rows.length} row(s) from Excel. Review, expand to edit, then generate.`
      }
      toolbar={
        <div className="flex flex-wrap items-center gap-3">
          {/* Date filter */}
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs shadow-sm">
            <svg className="h-3.5 w-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span className="font-medium text-slate-500">Filter</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="h-7 rounded border border-slate-200 px-1.5 text-xs text-slate-700 focus:border-teal-400 focus:outline-none"
              aria-label="From date"
            />
            <span className="text-slate-300">→</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="h-7 rounded border border-slate-200 px-1.5 text-xs text-slate-700 focus:border-teal-400 focus:outline-none"
              aria-label="To date"
            />
            {(dateFrom || dateTo) && (
              <button
                type="button"
                onClick={() => { setDateFrom(""); setDateTo(""); }}
                className="ml-1 text-slate-400 hover:text-slate-600"
                aria-label="Clear date filter"
              >
                ✕
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={() => startGeneration(rowsToGenerate)}
            disabled={loading || rowsToGenerate.length === 0}
            className="btn-primary flex items-center gap-2"
          >
            {loading ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 3l14 9-14 9V3z" />
              </svg>
            )}
            {loading ? "Starting…" : `Generate selected (${rowsToGenerate.length})`}
          </button>
          <button
            type="button"
            onClick={() => startGeneration(filteredRows)}
            disabled={loading}
            className="btn-outline"
          >
            Generate all ({filteredRows.length})
          </button>
        </div>
      }
    >
      {error && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
          <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          {error}
        </div>
      )}

      <div className="card overflow-hidden p-0">
        {/* Table header */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="w-10 px-4 py-3 text-center">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={(e) => toggleAll(e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                    aria-label="Select all"
                  />
                </th>
                <th className="w-8 px-2 py-3 text-xs font-semibold text-slate-500">#</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Buyer</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Product(s)</th>
                <th className="w-[90px] px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Date</th>
                <th className="w-[120px] px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Settings</th>
                <th className="w-[120px] px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Docs</th>
                <th className="w-[80px] px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Edit</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((row, idx) => {
                const isExpanded = expandedRowId === row.id;
                const isSelected = selected.has(row.id);
                const products = (row.product_name || "").split(",").map((p) => p.trim()).filter(Boolean);
                const lhLabel = row.letterhead === "dubai" ? "Dubai" : row.letterhead === "india" ? "India" : null;
                const leLabel = row.local_export === "local" ? "Local" : row.local_export === "export" ? "Export" : null;

                return (
                  <>
                    <tr
                      key={row.id}
                      className={`transition-colors ${isExpanded ? "bg-teal-50/40" : isSelected ? "bg-teal-50/20" : "hover:bg-slate-50/60"} ${idx !== filteredRows.length - 1 || isExpanded ? "border-b border-slate-100" : ""}`}
                    >
                      <td className="px-4 py-3 text-center align-middle">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleOne(row.id)}
                          className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                          aria-label={`Select row ${idx + 1}`}
                        />
                      </td>
                      <td className="px-2 py-3 text-center text-xs text-slate-400 align-middle">{idx + 1}</td>
                      <td className="px-4 py-3 align-middle">
                        <span className="font-medium text-slate-800">{row.buyer_name || "—"}</span>
                        {row.company_name && (
                          <p className="text-[11px] text-slate-400">{row.company_name}</p>
                        )}
                      </td>
                      <td className="px-4 py-3 align-middle">
                        {products.length > 1 ? (
                          <div className="flex flex-wrap gap-1">
                            {products.map((p, pi) => (
                              <span key={pi} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">
                                {p}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-slate-700">{row.product_name || "—"}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 align-middle text-xs text-slate-500">
                        {fmtDisplayDate(row.date) ?? <span className="text-slate-300">—</span>}
                      </td>
                      <td className="px-4 py-3 align-middle">
                        <div className="flex flex-wrap gap-1">
                          {lhLabel && <Pill label={lhLabel} color="teal" />}
                          {leLabel && <Pill label={leLabel} color={leLabel === "Local" ? "amber" : "slate"} />}
                        </div>
                      </td>
                      <td className="px-4 py-3 align-middle">
                        {row.doc_types ? (
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-mono text-slate-600">
                            {row.doc_types}
                          </span>
                        ) : (
                          <span className="text-[11px] text-slate-400">All</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right align-middle">
                        <button
                          type="button"
                          onClick={() => setExpandedRowId(isExpanded ? null : row.id)}
                          className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors ${
                            isExpanded
                              ? "border-teal-300 bg-teal-50 text-teal-700 hover:bg-teal-100"
                              : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-800"
                          }`}
                          aria-expanded={isExpanded}
                        >
                          {isExpanded ? "Close" : "Edit"}
                          <svg
                            className={`h-3.5 w-3.5 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2.5}
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${row.id}-expand`}>
                        <td colSpan={8} className="p-0">
                          <ExpandedRowEditor
                            row={row}
                            onChange={(field, value) => handleCellChange(row.id, field, value)}
                          />
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>

        {filteredRows.length === 0 && rows.length > 0 && (
          <p className="px-4 py-10 text-center text-sm text-slate-500">
            No rows match the selected date range.
          </p>
        )}
      </div>
    </PageLayout>
  );
}
