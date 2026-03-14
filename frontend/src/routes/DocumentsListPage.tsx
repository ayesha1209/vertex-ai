import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { DashboardLayout } from "../components/layout/DashboardLayout";
import { GenerationProgressCard } from "../components/dashboard/GenerationProgressCard";
import { SearchInput } from "../components/ui/SearchInput";
import { ConfirmModal } from "../components/ui/ConfirmModal";
import { BatchTable } from "../components/documents/BatchTable";
import { DocumentPagination } from "../components/documents/DocumentPagination";
import {
  listBatches,
  listDocuments,
  saveAllPdf,
  checkDatabaseHealth,
  deleteBatch,
} from "../lib/api";
import { useActiveJob } from "../context/ActiveJobContext";
import { useJobStream, getActiveJobId } from "../hooks/useJobStream";
import type { BatchSummary } from "../lib/types";

const PAGE_SIZE = 20;

type ProductTypeFilter = "all" | "chemical" | "engineering";

function getProductTypeFromPath(pathname: string): ProductTypeFilter {
  if (pathname === "/documents/engineering") return "engineering";
  if (pathname === "/documents/chemical") return "chemical";
  return "all";
}

export function DocumentsListPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const productTypeFilter = useMemo(
    () => getProductTypeFromPath(location.pathname),
    [location.pathname]
  );

  const [batches, setBatches] = useState<BatchSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [appliedFromDate, setAppliedFromDate] = useState("");
  const [appliedToDate, setAppliedToDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingAllPdf, setSavingAllPdf] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dbWarning, setDbWarning] = useState<string | null>(null);
  const [dbCheckResult, setDbCheckResult] = useState<{ ok: boolean; message?: string; error?: string } | null>(null);
  const [dbCheckLoading, setDbCheckLoading] = useState(false);
  const [selectedBatchIds, setSelectedBatchIds] = useState<Set<string>>(new Set());
  const [confirmDeleteBatchIds, setConfirmDeleteBatchIds] = useState<string[] | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const { activeJobId, setActiveJobId } = useActiveJob();
  const jobId = activeJobId ?? getActiveJobId();
  const onJobDone = useCallback(() => setActiveJobId(null), [setActiveJobId]);
  const [jobStream] = useJobStream(jobId, onJobDone);
  const prevJobStatusRef = useRef<string>(jobStream.status);

  const fetchBatches = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setError(null);
    setDbWarning(null);
    try {
      const res = await listBatches({
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: search || undefined,
        product_type: productTypeFilter === "all" ? undefined : productTypeFilter,
        from_date: appliedFromDate.trim() || undefined,
        to_date: appliedToDate.trim() || undefined,
      });
      setBatches(Array.isArray(res.batches) ? res.batches : []);
      setTotal(typeof res.total === "number" ? res.total : 0);
      if (res.warning) setDbWarning(res.warning);
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "Cannot reach server. Is the backend running on port 8000?"
      );
    } finally {
      setLoading(false);
    }
  }, [page, search, productTypeFilter, appliedFromDate, appliedToDate]);

  useEffect(() => setPage(1), [productTypeFilter]);
  useEffect(() => {
    fetchBatches(true);
  }, [fetchBatches]);
  useEffect(() => {
    const prev = prevJobStatusRef.current;
    prevJobStatusRef.current = jobStream.status;
    if ((prev === "connecting" || prev === "streaming") && jobStream.status === "done") {
      fetchBatches(false);
    }
  }, [jobStream.status, fetchBatches]);

  // While generation is in progress, poll so new batches appear
  const isJobActive = jobId && (jobStream.status === "connecting" || jobStream.status === "streaming");
  useEffect(() => {
    if (!isJobActive) return;
    const interval = setInterval(() => fetchBatches(false), 4000);
    return () => clearInterval(interval);
  }, [isJobActive, fetchBatches]);

  const handleSearch = () => {
    setSearch(searchInput.trim());
    setPage(1);
  };

  const applyDateFilter = () => {
    setAppliedFromDate(fromDate);
    setAppliedToDate(toDate);
    setPage(1);
  };

  const handleSelectOne = (batchId: string, checked: boolean) => {
    setSelectedBatchIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(batchId);
      else next.delete(batchId);
      return next;
    });
  };

  const handleSelectAll = (checked: boolean) => {
    setSelectedBatchIds(checked ? new Set(batches.map((b) => b.batch_id)) : new Set());
  };

  const handleDeleteBatch = (batchId: string) => setConfirmDeleteBatchIds([batchId]);

  const handleBulkDeleteClick = () => {
    if (selectedBatchIds.size > 0) setConfirmDeleteBatchIds(Array.from(selectedBatchIds));
  };

  const handleDeleteBatchConfirm = async () => {
    const ids = confirmDeleteBatchIds;
    if (!ids || ids.length === 0) return;
    setDeleteLoading(true);
    setError(null);
    try {
      for (const batchId of ids) {
        await deleteBatch(batchId);
      }
      setBatches((prev) => prev.filter((b) => !ids.includes(b.batch_id)));
      setTotal((t) => Math.max(0, t - ids.length));
      setSelectedBatchIds(new Set());
      setConfirmDeleteBatchIds(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete batch(es)");
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleSaveAllPdf = async () => {
    if (total === 0) return;
    setSavingAllPdf(true);
    setError(null);
    try {
      const res = await listDocuments({ limit: 2000 });
      const docs = Array.isArray(res.documents) ? res.documents : [];
      if (docs.length > 0) await saveAllPdf(docs.map((d) => d.id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save all PDF failed");
    } finally {
      setSavingAllPdf(false);
    }
  };

  const dashboardSubtitle =
    productTypeFilter === "engineering"
      ? "Engineering batches. Click a row to open Quotation, TDS, COA, MSDS."
      : productTypeFilter === "chemical"
        ? "Chemical batches. Click a row to open Quotation, TDS, COA, MSDS."
        : "Batches. Click a row to open documents (Quotation, TDS, COA, MSDS).";

  const showJobBanner = Boolean(jobId && jobStream && (jobStream.status === "connecting" || jobStream.status === "streaming"));
  const jobDocuments = (jobStream && ("documents" in jobStream) && Array.isArray(jobStream.documents)) ? jobStream.documents : [];
  const jobDocumentCount = jobDocuments.length;

  return (
    <DashboardLayout title="Documents" subtitle={dashboardSubtitle}>
      {/* Toolbar: row 1 = pills + search; row 2 = date + Apply left, Refresh + PDF right */}
      <div className="mb-6 sm:mb-8">
        <div className="card flex flex-col gap-4 px-4 py-4 sm:gap-5 sm:px-6 sm:py-5">
          <div className="flex min-w-0 flex-wrap items-center gap-4">
            <div className="pill-group shrink-0" role="tablist" aria-label="Document type">
              <NavLink to="/documents" className={({ isActive }) => `pill ${isActive ? "pill-active" : "hover:text-slate-800"}`}>All</NavLink>
              <NavLink to="/documents/engineering" className={({ isActive }) => `pill ${isActive ? "pill-active" : "hover:text-slate-800"}`}>Engineering</NavLink>
              <NavLink to="/documents/chemical" className={({ isActive }) => `pill ${isActive ? "pill-active" : "hover:text-slate-800"}`}>Chemical</NavLink>
            </div>
            <div className="flex min-w-[200px] flex-1 items-stretch gap-2">
              <SearchInput placeholder="Search buyer or product…" value={searchInput} onChange={(e) => setSearchInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleSearch()} className="min-w-0 flex-1 search-input-dashboard" />
              <button type="button" onClick={handleSearch} className="btn-primary btn-sm min-h-[2.5rem] shrink-0 px-4">Search</button>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-1.5 text-sm text-slate-500">
                <span className="shrink-0">From</span>
                <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="input input-sm h-9 w-28 rounded-lg border-slate-200/90 bg-slate-50/50 sm:w-32" />
              </label>
              <label className="flex items-center gap-1.5 text-sm text-slate-500">
                <span className="shrink-0">To</span>
                <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="input input-sm h-9 w-28 rounded-lg border-slate-200/90 bg-slate-50/50 sm:w-32" />
              </label>
              <button type="button" onClick={applyDateFilter} className="btn-outline btn-sm">Apply</button>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => fetchBatches(true)} disabled={loading} className="btn-ghost btn-sm">{loading ? "Loading…" : "Refresh"}</button>
              {selectedBatchIds.size > 0 && (
                <button type="button" onClick={handleBulkDeleteClick} className="btn-danger btn-sm">
                  Delete ({selectedBatchIds.size})
                </button>
              )}
              <button type="button" onClick={handleSaveAllPdf} disabled={savingAllPdf || total === 0} className="btn-primary btn-sm">{savingAllPdf ? "Saving…" : "PDF (all)"}</button>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-4 alert-error" role="alert">
          {error}
        </div>
      )}

      {dbWarning && (
        <div className="mb-4 alert-warning" role="alert">
          <p className="font-medium">Database unavailable.</p>
          <p className="mt-1">{dbWarning}</p>
          <p className="mt-1">List is empty until MongoDB is connected.</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={async () => {
                setDbCheckLoading(true);
                setDbCheckResult(null);
                try {
                  const res = await checkDatabaseHealth();
                  setDbCheckResult(res);
                } catch {
                  setDbCheckResult({ ok: false, error: "Request failed. Is the backend running?" });
                } finally {
                  setDbCheckLoading(false);
                }
              }}
              disabled={dbCheckLoading}
              className="btn-outline btn-sm"
            >
              {dbCheckLoading ? "Checking…" : "Check connection"}
            </button>
          </div>
          {dbCheckResult && (
            <p
              className={`mt-2 rounded-lg border px-3 py-2 text-sm font-mono ${
                dbCheckResult.ok
                  ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                  : "border-red-200 bg-red-50 text-red-800"
              }`}
            >
              {dbCheckResult.ok ? dbCheckResult.message ?? "OK" : dbCheckResult.error ?? "Failed"}
            </p>
          )}
        </div>
      )}

      {showJobBanner && (
        <GenerationProgressCard
          documentCount={jobDocumentCount}
          isStreaming={jobStream.status === "streaming"}
          documents={jobDocuments}
        />
      )}

      <BatchTable
        batches={batches}
        selectedBatchIds={selectedBatchIds}
        onSelectOne={handleSelectOne}
        onSelectAll={handleSelectAll}
        loading={loading}
        onDelete={handleDeleteBatch}
      />

      <DocumentPagination
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        onPageChange={setPage}
      />

      <ConfirmModal
        open={confirmDeleteBatchIds !== null && confirmDeleteBatchIds.length > 0}
        title={confirmDeleteBatchIds?.length === 1 ? "Delete batch?" : `Delete ${confirmDeleteBatchIds?.length ?? 0} batches?`}
        message={
          confirmDeleteBatchIds?.length === 1
            ? "This will permanently delete all documents in this batch (Quotation, TDS, COA, MSDS). This cannot be undone."
            : `This will permanently delete all documents in ${confirmDeleteBatchIds?.length ?? 0} batches. This cannot be undone.`
        }
        confirmLabel="Delete"
        variant="danger"
        loading={deleteLoading}
        onConfirm={handleDeleteBatchConfirm}
        onCancel={() => setConfirmDeleteBatchIds(null)}
      />
    </DashboardLayout>
  );
}
