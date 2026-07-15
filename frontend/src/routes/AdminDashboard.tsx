import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listShipments, listAdminBatches, createShipment, deleteShipment, type AdminBatch, type Shipment } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { DashboardLayout } from "../components/layout/DashboardLayout";

const DOC_TYPE_LABELS: Record<string, string> = {
  pi: "PI",
  tax_invoice: "Tax Invoice",
  pl: "P/L",
  receipt_tt_copy: "TT Copy",
  bank_receipt: "Bank Receipt",
  bl_copy: "BL Copy",
  custom_copy: "Custom Copy",
};
const DOC_TYPES = Object.keys(DOC_TYPE_LABELS);
const BATCH_PAGE_SIZE = 30;

type AddMode = "select" | "manual" | "skip";

function StatusBadge({ allUploaded }: { allUploaded: boolean }) {
  if (allUploaded) {
    return (
      <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200">
        Complete
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-amber-200">
      Pending
    </span>
  );
}

export function AdminDashboard() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [addModal, setAddModal] = useState(false);
  const [addMode, setAddMode] = useState<AddMode>("select");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // "Select Quotation" mode — server-side search + pagination
  const [batches, setBatches] = useState<AdminBatch[]>([]);
  const [batchTotal, setBatchTotal] = useState(0);
  const [batchesLoading, setBatchesLoading] = useState(false);
  const [batchLoadingMore, setBatchLoadingMore] = useState(false);
  const [batchSearch, setBatchSearch] = useState("");
  const [enteredBy, setEnteredBy] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [debouncedEnteredBy, setDebouncedEnteredBy] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // "Add Manually" / "Skip Quotation" form fields
  const [manualBuyer, setManualBuyer] = useState("");
  const [manualProduct, setManualProduct] = useState("");
  const [manualQuotationNo, setManualQuotationNo] = useState("");

  // Delete inline confirmation
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  // ── Debounce search ──────────────────────────────────────────────
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQ(batchSearch);
      setDebouncedEnteredBy(enteredBy);
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [batchSearch, enteredBy]);

  // ── Fetch first page (select mode only) ─────────────────────────
  const fetchBatches = useCallback(async (q: string, entered_by: string) => {
    setBatchesLoading(true);
    setAddError(null);
    setBatches([]);
    try {
      const res = await listAdminBatches({ q: q || undefined, entered_by: entered_by || undefined, skip: 0, limit: BATCH_PAGE_SIZE });
      setBatches(res.batches);
      setBatchTotal(res.total);
    } catch {
      setAddError("Failed to load quotations");
    } finally {
      setBatchesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (addModal && addMode === "select") fetchBatches(debouncedQ, debouncedEnteredBy);
  }, [addModal, addMode, debouncedQ, debouncedEnteredBy, fetchBatches]);

  const loadMore = async () => {
    if (batchLoadingMore) return;
    setBatchLoadingMore(true);
    try {
      const res = await listAdminBatches({
        q: debouncedQ || undefined,
        entered_by: debouncedEnteredBy || undefined,
        skip: batches.length,
        limit: BATCH_PAGE_SIZE,
      });
      setBatches(prev => [...prev, ...res.batches]);
      setBatchTotal(res.total);
    } catch { /* ignore */ }
    finally { setBatchLoadingMore(false); }
  };

  // ── Shipments list ───────────────────────────────────────────────
  const fetchShipments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listShipments();
      setShipments(res.shipments);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchShipments(); }, [fetchShipments]);

  // ── Open modal ───────────────────────────────────────────────────
  const openAddModal = () => {
    setAddModal(true);
    setAddMode("select");
    setAddError(null);
    setBatchSearch(""); setEnteredBy(""); setDebouncedQ(""); setDebouncedEnteredBy("");
    setBatches([]); setBatchTotal(0);
    setManualBuyer(""); setManualProduct(""); setManualQuotationNo("");
  };

  const switchMode = (m: AddMode) => {
    setAddMode(m);
    setAddError(null);
    setManualBuyer(""); setManualProduct(""); setManualQuotationNo("");
  };

  // ── Add handlers ─────────────────────────────────────────────────
  const handleAddBatch = async (batch: AdminBatch) => {
    setAdding(true);
    setAddError(null);
    try {
      const shipment = await createShipment({
        batch_id: batch.batch_id,
        quotation_no: batch.quotation_no,
        buyer_name: batch.buyer_name,
        product_name: batch.product_name,
      });
      setAddModal(false);
      navigate(`/admin/shipment/${shipment.id}`);
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Failed to add");
    } finally {
      setAdding(false);
    }
  };

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualBuyer.trim() || !manualProduct.trim()) return;
    setAdding(true);
    setAddError(null);
    try {
      const shipment = await createShipment({
        buyer_name: manualBuyer.trim(),
        product_name: manualProduct.trim(),
        quotation_no: addMode === "manual" && manualQuotationNo.trim() ? manualQuotationNo.trim() : undefined,
      });
      setAddModal(false);
      navigate(`/admin/shipment/${shipment.id}`);
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Failed to add");
    } finally {
      setAdding(false);
    }
  };

  // ── Delete ───────────────────────────────────────────────────────
  const handleDelete = async (id: string) => {
    setDeleting(true);
    try {
      await deleteShipment(id);
      setShipments(prev => prev.filter(s => s.id !== id));
      setTotal(prev => prev - 1);
      setConfirmDeleteId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete");
    } finally {
      setDeleting(false);
    }
  };

  const handleLogout = () => { logout(); navigate("/"); };

  const trackedBatchIds = new Set(shipments.map(s => s.batch_id));
  const hasMore = batches.length < batchTotal;

  // ── Tab helpers ──────────────────────────────────────────────────
  const tabs: { key: AddMode; label: string; desc: string }[] = [
    { key: "select",  label: "Select Quotation", desc: "Pick from generated quotations" },
    { key: "manual",  label: "Add Manually",     desc: "Enter details + quotation no" },
    { key: "skip",    label: "Skip Quotation",   desc: "Track without a quotation no" },
  ];

  return (
    <DashboardLayout title="Admin Dashboard" subtitle="Shipment document tracking">
      <div className="space-y-4">

        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-800">Shipment Tracking ({total})</h2>
            <p className="text-sm text-slate-500">Track 7 required documents per quotation.</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={openAddModal}
              className="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-700"
            >
              <span>+</span> Add Quotation
            </button>
            <button type="button" onClick={handleLogout} className="btn-ghost btn-sm">Logout</button>
          </div>
        </div>

        {error && <div className="alert-error">{error}</div>}

        {loading ? (
          <div className="flex min-h-[200px] items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
          </div>
        ) : shipments.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 py-14 text-center">
            <p className="text-sm font-medium text-slate-700">No shipments tracked yet</p>
            <p className="mt-1 text-xs text-slate-500">Click "+ Add Quotation" to start tracking documents.</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600">Buyer / Product</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600">Quotation No</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 hidden sm:table-cell">Documents</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600">Status</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-600">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {shipments.map((s) => {
                  const uploaded = DOC_TYPES.filter(dt => s.docs?.[dt]?.uploaded).length;
                  const confirming = confirmDeleteId === s.id;
                  return (
                    <tr key={s.id} className={confirming ? "bg-red-50" : "hover:bg-slate-50"}>
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-800">{s.buyer_name}</p>
                        <p className="text-xs text-slate-500">{s.product_name}</p>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{s.quotation_no || "—"}</td>
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <div className="flex flex-wrap gap-1">
                          {DOC_TYPES.map(dt => (
                            <span
                              key={dt}
                              className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${s.docs?.[dt]?.uploaded ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-400"}`}
                              title={DOC_TYPE_LABELS[dt]}
                            >
                              {DOC_TYPE_LABELS[dt]}
                            </span>
                          ))}
                        </div>
                        <p className="mt-1 text-xs text-slate-400">{uploaded}/7 uploaded</p>
                      </td>
                      <td className="px-4 py-3"><StatusBadge allUploaded={s.all_uploaded} /></td>
                      <td className="px-4 py-3 text-right">
                        {confirming ? (
                          <div className="flex items-center justify-end gap-2">
                            <span className="text-xs text-red-600 font-medium">Delete?</span>
                            <button type="button" disabled={deleting} onClick={() => handleDelete(s.id)}
                              className="rounded-md bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-60">
                              {deleting ? "…" : "Yes"}
                            </button>
                            <button type="button" onClick={() => setConfirmDeleteId(null)}
                              className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200">
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center justify-end gap-2">
                            <Link to={`/admin/shipment/${s.id}`}
                              className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-200">
                              Manage
                            </Link>
                            <button type="button" onClick={() => setConfirmDeleteId(s.id)}
                              className="rounded-lg px-2 py-1.5 text-xs font-medium text-red-400 hover:bg-red-50 hover:text-red-600"
                              title="Delete entry">
                              ✕
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Add modal ── */}
        {addModal && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
            onClick={(e) => { if (e.target === e.currentTarget) setAddModal(false); }}
          >
            <div className="w-full max-w-2xl rounded-2xl bg-white shadow-2xl flex flex-col max-h-[85vh]">

              {/* Modal header */}
              <div className="border-b border-slate-100 px-6 py-4 flex items-center justify-between shrink-0">
                <h2 className="text-base font-semibold text-slate-800">Add Shipment to Track</h2>
                <button type="button" onClick={() => setAddModal(false)}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                  aria-label="Close">
                  ✕
                </button>
              </div>

              {/* Mode tabs */}
              <div className="px-6 pt-4 pb-0 shrink-0">
                <div className="grid grid-cols-3 gap-2">
                  {tabs.map(t => (
                    <button
                      key={t.key}
                      type="button"
                      onClick={() => switchMode(t.key)}
                      className={`rounded-xl border px-3 py-3 text-left transition-colors ${
                        addMode === t.key
                          ? "border-teal-500 bg-teal-50 ring-1 ring-teal-400"
                          : "border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white"
                      }`}
                    >
                      <p className={`text-xs font-semibold ${addMode === t.key ? "text-teal-700" : "text-slate-700"}`}>
                        {t.label}
                      </p>
                      <p className="mt-0.5 text-[11px] text-slate-500 leading-tight">{t.desc}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* ── Tab: Select Quotation ── */}
              {addMode === "select" && (
                <>
                  <div className="px-4 pt-3 pb-2 shrink-0 space-y-2">
                    <div className="relative">
                      <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
                      </svg>
                      <input
                        type="text"
                        autoFocus
                        placeholder="Search by buyer, product or quotation no…"
                        value={batchSearch}
                        onChange={(e) => setBatchSearch(e.target.value)}
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-8 text-sm placeholder-slate-400 focus:border-teal-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-teal-400"
                      />
                      {batchSearch && (
                        <button type="button" onClick={() => setBatchSearch("")}
                          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">✕</button>
                      )}
                    </div>
                    <div className="relative">
                      <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0zM12 14a7 7 0 0 0-7 7h14a7 7 0 0 0-7-7z" />
                      </svg>
                      <input
                        type="text"
                        placeholder="Filter by person who entered (employee name)…"
                        value={enteredBy}
                        onChange={(e) => setEnteredBy(e.target.value)}
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-8 text-sm placeholder-slate-400 focus:border-teal-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-teal-400"
                      />
                      {enteredBy && (
                        <button type="button" onClick={() => setEnteredBy("")}
                          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">✕</button>
                      )}
                    </div>
                  </div>

                  <div className="overflow-y-auto flex-1 px-2 pb-2">
                    {addError && <div className="mx-2 my-2 alert-error">{addError}</div>}
                    {batchesLoading ? (
                      <div className="flex items-center justify-center py-14">
                        <div className="h-6 w-6 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
                      </div>
                    ) : batches.length === 0 ? (
                      <div className="py-12 text-center">
                        <p className="text-sm text-slate-500">
                          {batchSearch || enteredBy ? "No quotations match the current filters." : "No quotations found."}
                        </p>
                        {(batchSearch || enteredBy) && (
                          <button type="button" onClick={() => { setBatchSearch(""); setEnteredBy(""); }}
                            className="mt-2 text-xs text-teal-600 hover:underline">
                            Clear filters
                          </button>
                        )}
                      </div>
                    ) : (
                      <>
                        <table className="min-w-full text-sm">
                          <thead className="sticky top-0 bg-white shadow-[0_1px_0_0_#e2e8f0]">
                            <tr>
                              <th className="px-4 py-2 text-left text-xs font-semibold text-slate-600">Buyer / Product</th>
                              <th className="px-4 py-2 text-left text-xs font-semibold text-slate-600">Quotation No</th>
                              <th className="px-4 py-2 text-left text-xs font-semibold text-slate-600 hidden sm:table-cell">Entered by</th>
                              <th className="px-4 py-2 w-28" />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {batches.map((b) => {
                              const alreadyTracked = trackedBatchIds.has(b.batch_id);
                              return (
                                <tr key={b.batch_id} className={alreadyTracked ? "opacity-50" : "hover:bg-slate-50"}>
                                  <td className="px-4 py-2.5">
                                    <p className="font-medium text-slate-800 leading-tight">{b.buyer_name}</p>
                                    <p className="text-xs text-slate-500 leading-tight mt-0.5">{b.product_name}</p>
                                  </td>
                                  <td className="px-4 py-2.5 text-slate-600 font-mono text-xs">{b.quotation_no || "—"}</td>
                                  <td className="px-4 py-2.5 text-slate-500 text-xs hidden sm:table-cell">{b.employee_name || "—"}</td>
                                  <td className="px-4 py-2.5 text-right">
                                    {alreadyTracked ? (
                                      <span className="text-xs text-slate-400 italic">Already tracked</span>
                                    ) : (
                                      <button type="button" disabled={adding} onClick={() => handleAddBatch(b)}
                                        className="rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-teal-700 disabled:opacity-60 whitespace-nowrap">
                                        {adding ? "Adding…" : "+ Add"}
                                      </button>
                                    )}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                        {hasMore && (
                          <div className="flex justify-center py-3">
                            <button type="button" onClick={loadMore} disabled={batchLoadingMore}
                              className="rounded-lg border border-slate-200 bg-white px-4 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60">
                              {batchLoadingMore ? "Loading…" : `Load more (${batchTotal - batches.length} remaining)`}
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>

                  <div className="border-t border-slate-100 px-6 py-3 flex items-center justify-between shrink-0">
                    <span className="text-xs text-slate-400">
                      {batchesLoading ? "…" : `${batches.length} of ${batchTotal} result${batchTotal !== 1 ? "s" : ""}`}
                    </span>
                    <button type="button" onClick={() => setAddModal(false)} className="btn-ghost btn-sm">Close</button>
                  </div>
                </>
              )}

              {/* ── Tab: Add Manually / Skip Quotation ── */}
              {(addMode === "manual" || addMode === "skip") && (
                <form onSubmit={handleManualSubmit} className="flex flex-col flex-1 overflow-y-auto">
                  <div className="flex-1 px-6 py-5 space-y-4">
                    {addError && <div className="alert-error">{addError}</div>}

                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Buyer Name <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="text"
                        autoFocus
                        required
                        value={manualBuyer}
                        onChange={(e) => setManualBuyer(e.target.value)}
                        placeholder="e.g. Acme Corp"
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm placeholder-slate-400 focus:border-teal-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-teal-400"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">
                        Product Name <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="text"
                        required
                        value={manualProduct}
                        onChange={(e) => setManualProduct(e.target.value)}
                        placeholder="e.g. Industrial Valves"
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm placeholder-slate-400 focus:border-teal-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-teal-400"
                      />
                    </div>

                    {addMode === "manual" && (
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">
                          Quotation No <span className="text-slate-400">(optional)</span>
                        </label>
                        <input
                          type="text"
                          value={manualQuotationNo}
                          onChange={(e) => setManualQuotationNo(e.target.value)}
                          placeholder="e.g. VERT/001/2026"
                          className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm placeholder-slate-400 focus:border-teal-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-teal-400"
                        />
                      </div>
                    )}

                    {addMode === "skip" && (
                      <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-700">
                        No quotation number will be linked. You can still upload all 7 shipment documents.
                      </p>
                    )}
                  </div>

                  <div className="border-t border-slate-100 px-6 py-3 flex items-center justify-between shrink-0">
                    <button type="button" onClick={() => setAddModal(false)} className="btn-ghost btn-sm">Cancel</button>
                    <button
                      type="submit"
                      disabled={adding || !manualBuyer.trim() || !manualProduct.trim()}
                      className="rounded-lg bg-teal-600 px-5 py-2 text-sm font-medium text-white hover:bg-teal-700 disabled:opacity-60"
                    >
                      {adding ? "Creating…" : "Create & Track"}
                    </button>
                  </div>
                </form>
              )}

            </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}
