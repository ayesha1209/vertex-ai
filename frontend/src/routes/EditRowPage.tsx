import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { DashboardLayout } from "../components/layout/DashboardLayout";
import { listDocuments, generateBatch } from "../lib/api";
import { useActiveJob } from "../context/ActiveJobContext";
import { ConfirmModal } from "../components/ui/ConfirmModal";
import type { RowPreview } from "../lib/types";

/* ─── helpers ─── */
function Field({
  label,
  hint,
  className,
  children,
}: {
  label: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`flex flex-col gap-1.5${className ? ` ${className}` : ""}`}>
      <span className="text-xs font-semibold text-slate-700">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-slate-400">{hint}</span>}
    </label>
  );
}

const inputCls =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm transition-colors focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-400/30 placeholder:text-slate-300";
const selectCls =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-400/30";
const textareaCls =
  "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm resize-y min-h-[72px] focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-400/30 placeholder:text-slate-300";

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3 mt-6 flex items-center gap-3 first:mt-0">
      <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400">{children}</p>
      <div className="h-px flex-1 bg-slate-100" />
    </div>
  );
}

/* Product tag manager */
function ProductTagEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const products = value
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);

  const remove = (idx: number) => {
    const next = products.filter((_, i) => i !== idx).join(", ");
    onChange(next);
  };

  const [adding, setAdding] = useState(false);
  const [addVal, setAddVal] = useState("");

  const commitAdd = () => {
    const trimmed = addVal.trim();
    if (trimmed) {
      const next = [...products, trimmed].join(", ");
      onChange(next);
    }
    setAddVal("");
    setAdding(false);
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2 rounded-lg border border-slate-200 bg-slate-50 p-2.5 min-h-[44px]">
        {products.length === 0 && (
          <span className="text-xs text-slate-400 italic self-center">No products — add below</span>
        )}
        {products.map((p, i) => (
          <span
            key={i}
            className="group flex items-center gap-1 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-medium text-slate-700 shadow-sm"
          >
            {p}
            <button
              type="button"
              onClick={() => remove(i)}
              className="ml-0.5 rounded-full p-0.5 text-slate-300 transition-colors hover:bg-red-50 hover:text-red-500 focus:outline-none"
              aria-label={`Remove ${p}`}
            >
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </span>
        ))}
      </div>

      {adding ? (
        <div className="flex gap-2">
          <input
            autoFocus
            type="text"
            value={addVal}
            onChange={(e) => setAddVal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") { e.preventDefault(); commitAdd(); }
              if (e.key === "Escape") { setAdding(false); setAddVal(""); }
            }}
            placeholder="Product name…"
            className={`${inputCls} flex-1`}
          />
          <button type="button" onClick={commitAdd} className="btn-primary btn-sm px-4">Add</button>
          <button type="button" onClick={() => { setAdding(false); setAddVal(""); }} className="btn-outline btn-sm px-3">Cancel</button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-xs text-slate-500 transition-colors hover:border-teal-400 hover:text-teal-600"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Add product
        </button>
      )}
    </div>
  );
}

/* ─── main page ─── */
export function EditRowPage() {
  const { batchId } = useParams<{ batchId: string }>();
  const navigate = useNavigate();
  const { setActiveJobId } = useActiveJob();

  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [row, setRow] = useState<RowPreview>({
    id: 0,
    buyer_name: "",
    product_name: "",
  });

  const set = (field: keyof RowPreview, value: string) =>
    setRow((prev) => ({ ...prev, [field]: value || null }));

  const fetchData = useCallback(async () => {
    if (!batchId) return;
    setLoadingData(true);
    setLoadError(null);
    try {
      const res = await listDocuments({ batch_id: batchId, limit: 20 });
      const docs = res.documents || [];
      if (docs.length === 0) throw new Error("No documents found for this batch.");
      // Use the first doc (quotation preferably) to seed the row
      const seed =
        docs.find((d) => d.doc_type === "quotation") ?? docs[0];
      // We cast to any here to access extended fields if backend returns them
      const d = seed as typeof seed & {
        company_name?: string;
        letterhead?: string;
        local_export?: string;
        quotation_no?: string;
        quantity?: string;
        unit?: string;
        country?: string;
        port?: string;
        incoterm?: string;
        payment_terms?: string;
        remarks?: string;
      };
      setRow({
        id: 0,
        buyer_name: d.buyer_name ?? "",
        product_name: d.product_name ?? "",
        employee_name: d.employee_name ?? null,
        company_name: d.company_name ?? null,
        letterhead: d.letterhead ?? null,
        local_export: d.local_export ?? null,
        quotation_no: d.quotation_no ?? null,
        quantity: d.quantity ?? null,
        unit: d.unit ?? null,
        country: d.country ?? null,
        port: d.port ?? null,
        incoterm: d.incoterm ?? null,
        payment_terms: d.payment_terms ?? null,
        remarks: d.remarks ?? null,
        // Fields not in DocumentSummary; user can fill in
        date: null,
        address: null,
        buyer_enquir_ref_no: null,
        transportation: null,
        type_of_packing: null,
        email_id: null,
        contact_no: null,
        manufacturer_name: null,
        product_description: null,
        hsn_code: null,
        cas_no: null,
        price: null,
        price_fob_cif: null,
        port_of_loading: d.port ?? null,
        port_of_unloading: null,
        unloading_country: null,
        doc_types: null,
        department: null,
        product_type: (d as { product_type?: "chemical" | "engineering" }).product_type ?? null,
        attachment: null,
        dimensional: null,
        technical_specification: null,
      });
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : "Failed to load batch data.");
    } finally {
      setLoadingData(false);
    }
  }, [batchId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRegenerate = async () => {
    setConfirmOpen(false);
    setGenerating(true);
    setGenError(null);
    try {
      const { job_id } = await generateBatch([row]);
      setActiveJobId(job_id);
      navigate(`/generate?job=${job_id}`);
    } catch (e: unknown) {
      setGenError(e instanceof Error ? e.message : "Failed to start regeneration.");
    } finally {
      setGenerating(false);
    }
  };

  const f = (field: keyof RowPreview) => String(row[field] ?? "");

  if (!batchId) {
    return (
      <DashboardLayout title="Edit Row" subtitle="Missing batch id.">
        <p className="text-slate-600">No batch selected.</p>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      title="Edit Row & Regenerate"
      subtitle="Modify the row data and regenerate documents for this batch."
    >
      <div className="space-y-5">
        {/* Back + action bar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link to={`/documents/batch/${batchId}`} className="btn-ghost btn-sm">
            ← Back to batch
          </Link>
          <button
            type="button"
            onClick={() => setConfirmOpen(true)}
            disabled={generating || loadingData || !row.buyer_name || !row.product_name}
            className="btn-primary flex items-center gap-2"
          >
            {generating ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Regenerating…
              </>
            ) : (
              <>
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Regenerate documents
              </>
            )}
          </button>
        </div>

        {/* Info banner */}
        <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p>
            Data is pre-filled from the original batch. Edit what you need — particularly the
            <strong className="mx-1">Products</strong> list (remove unwanted products) — then click
            <strong className="ml-1">Regenerate documents</strong>. This creates a new batch and does not affect the existing one.
          </p>
        </div>

        {loadError && (
          <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
            <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            {loadError}
          </div>
        )}
        {genError && (
          <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
            <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            {genError}
          </div>
        )}

        {loadingData ? (
          <div className="flex min-h-[200px] items-center justify-center rounded-xl border border-slate-200 bg-white">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
          </div>
        ) : (
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            {/* Products — top & most important */}
            <SectionTitle>Products to generate</SectionTitle>
            <div className="mb-1">
              <Field
                label="Product list"
                hint="Remove products you don't want regenerated. Add new ones if needed."
              >
                <ProductTagEditor
                  value={f("product_name")}
                  onChange={(v) => setRow((prev) => ({ ...prev, product_name: v }))}
                />
              </Field>
            </div>

            {/* Identification */}
            <SectionTitle>Identification</SectionTitle>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Buyer name *">
                <input className={inputCls} value={f("buyer_name")} onChange={(e) => set("buyer_name", e.target.value)} placeholder="Company or person name" />
              </Field>
              <Field label="Company / Supplier">
                <input className={inputCls} value={f("company_name")} onChange={(e) => set("company_name", e.target.value)} placeholder="Supplier company name" />
              </Field>
              <Field label="Employee name">
                <input className={inputCls} value={f("employee_name")} onChange={(e) => set("employee_name", e.target.value)} placeholder="Who entered this row" />
              </Field>
              <Field label="Quotation no" hint="Leave blank to auto-generate">
                <input className={inputCls} value={f("quotation_no")} onChange={(e) => set("quotation_no", e.target.value)} placeholder="Auto-generated if blank" />
              </Field>
              <Field label="Date" hint="DD/MM/YYYY format">
                <input className={inputCls} value={f("date")} onChange={(e) => set("date", e.target.value)} placeholder="e.g. 15/03/2026" />
              </Field>
              <Field label="Buyer ref no">
                <input className={inputCls} value={f("buyer_enquir_ref_no")} onChange={(e) => set("buyer_enquir_ref_no", e.target.value)} />
              </Field>
              <Field label="Address" className="sm:col-span-2 lg:col-span-3">
                <textarea className={textareaCls} value={f("address")} onChange={(e) => set("address", e.target.value)} placeholder="Full address" />
              </Field>
            </div>

            {/* Settings */}
            <SectionTitle>Document settings</SectionTitle>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Letterhead">
                <select className={selectCls} value={f("letterhead")} onChange={(e) => set("letterhead", e.target.value)}>
                  <option value="">— Not set</option>
                  <option value="india">India</option>
                  <option value="dubai">Dubai</option>
                </select>
              </Field>
              <Field label="Local / Export">
                <select className={selectCls} value={f("local_export")} onChange={(e) => set("local_export", e.target.value)}>
                  <option value="">— Not set</option>
                  <option value="local">Local (₹ INR)</option>
                  <option value="export">Export ($ USD)</option>
                </select>
              </Field>
              <Field label="Product type" hint="Overrides keyword detection">
                <select className={selectCls} value={f("product_type")} onChange={(e) => set("product_type", e.target.value)}>
                  <option value="">— Auto (keywords)</option>
                  <option value="chemical">Chemical</option>
                  <option value="engineering">Engineering</option>
                </select>
              </Field>
              <Field label="Docs to generate" hint="e.g. q,tds — leave empty for all">
                <input className={inputCls} value={f("doc_types")} onChange={(e) => set("doc_types", e.target.value)} placeholder="q,tds,coa,msds (all if blank)" />
              </Field>
            </div>

            {/* Product details */}
            <SectionTitle>Product details</SectionTitle>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Manufacturer">
                <input className={inputCls} value={f("manufacturer_name")} onChange={(e) => set("manufacturer_name", e.target.value)} />
              </Field>
              <Field label="Product description">
                <textarea className={textareaCls} value={f("product_description")} onChange={(e) => set("product_description", e.target.value)} />
              </Field>
              <Field label="HSN code" hint="Leave blank to auto-generate">
                <input className={inputCls} value={f("hsn_code")} onChange={(e) => set("hsn_code", e.target.value)} placeholder="Auto-generated if blank" />
              </Field>
              <Field label="CAS no">
                <input className={inputCls} value={f("cas_no")} onChange={(e) => set("cas_no", e.target.value)} />
              </Field>
              <Field label="Quantity">
                <input className={inputCls} value={f("quantity")} onChange={(e) => set("quantity", e.target.value)} placeholder="e.g. 100" />
              </Field>
              <Field label="Unit">
                <input className={inputCls} value={f("unit")} onChange={(e) => set("unit", e.target.value)} placeholder="e.g. MT, kg, L" />
              </Field>
              <Field label="Packing">
                <input className={inputCls} value={f("type_of_packing")} onChange={(e) => set("type_of_packing", e.target.value)} />
              </Field>
              <Field label="Price" hint="AI generates if blank">
                <input className={inputCls} value={f("price")} onChange={(e) => set("price", e.target.value)} placeholder="Unit price" />
              </Field>
              <Field label="Price FOB/CIF">
                <input className={inputCls} value={f("price_fob_cif")} onChange={(e) => set("price_fob_cif", e.target.value)} />
              </Field>
            </div>

            {/* Shipping */}
            <SectionTitle>Shipping & Terms</SectionTitle>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Country">
                <input className={inputCls} value={f("country")} onChange={(e) => set("country", e.target.value)} />
              </Field>
              <Field label="Port of loading">
                <input className={inputCls} value={f("port_of_loading")} onChange={(e) => set("port_of_loading", e.target.value)} />
              </Field>
              <Field label="Port of unloading">
                <input className={inputCls} value={f("port_of_unloading")} onChange={(e) => set("port_of_unloading", e.target.value)} />
              </Field>
              <Field label="Unloading country">
                <input className={inputCls} value={f("unloading_country")} onChange={(e) => set("unloading_country", e.target.value)} />
              </Field>
              <Field label="Incoterm">
                <input className={inputCls} value={f("incoterm")} onChange={(e) => set("incoterm", e.target.value)} placeholder="e.g. CIF, FOB" />
              </Field>
              <Field label="Payment terms">
                <input className={inputCls} value={f("payment_terms")} onChange={(e) => set("payment_terms", e.target.value)} />
              </Field>
              <Field label="Transport mode">
                <input className={inputCls} value={f("transportation")} onChange={(e) => set("transportation", e.target.value)} />
              </Field>
              <Field label="Email">
                <input className={inputCls} type="email" value={f("email_id")} onChange={(e) => set("email_id", e.target.value)} />
              </Field>
              <Field label="Contact no">
                <input className={inputCls} value={f("contact_no")} onChange={(e) => set("contact_no", e.target.value)} />
              </Field>
              <Field label="Remarks" className="sm:col-span-2 lg:col-span-3">
                <textarea className={textareaCls} value={f("remarks")} onChange={(e) => set("remarks", e.target.value)} />
              </Field>
            </div>

            {/* Bottom CTA */}
            <div className="mt-8 flex items-center justify-end gap-3 border-t border-slate-100 pt-5">
              <Link to={`/documents/batch/${batchId}`} className="btn-outline btn-sm">
                Cancel
              </Link>
              <button
                type="button"
                onClick={() => setConfirmOpen(true)}
                disabled={generating || !row.buyer_name || !row.product_name}
                className="btn-primary flex items-center gap-2"
              >
                {generating ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Regenerating…
                  </>
                ) : (
                  <>
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    Regenerate documents
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>

      <ConfirmModal
        open={confirmOpen}
        title="Regenerate documents?"
        message={`This will start a new batch with the updated row data. ${
          row.product_name
            ? `Products: ${row.product_name.split(",").map((p) => p.trim()).filter(Boolean).join(", ")}.`
            : ""
        } The original batch remains unchanged.`}
        confirmLabel="Regenerate"
        cancelLabel="Cancel"
        variant="default"
        loading={generating}
        onConfirm={handleRegenerate}
        onCancel={() => !generating && setConfirmOpen(false)}
      />
    </DashboardLayout>
  );
}
