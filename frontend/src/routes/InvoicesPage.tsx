import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DashboardLayout } from "../components/layout/DashboardLayout";
import { DocumentTable } from "../components/documents/DocumentTable";
import { ConfirmModal } from "../components/ui/ConfirmModal";
import { listBatchInvoices, generateBatchInvoices, deleteDocument } from "../lib/api";
import type { DocumentSummary } from "../lib/types";

export function InvoicesPage() {
  const { batchId } = useParams<{ batchId: string }>();

  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const fetchInvoices = useCallback(async () => {
    if (!batchId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await listBatchInvoices(batchId);
      setDocuments(res.documents ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load invoices");
    } finally {
      setLoading(false);
    }
  }, [batchId]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const handleGenerate = async () => {
    if (!batchId) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await generateBatchInvoices(batchId);
      setDocuments(res.documents ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to generate invoices");
    } finally {
      setGenerating(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteId) return;
    setDeleteLoading(true);
    setError(null);
    try {
      await deleteDocument(deleteId);
      setDocuments((prev) => prev.filter((d) => d.id !== deleteId));
      setDeleteId(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleteLoading(false);
    }
  };

  if (!batchId) {
    return (
      <DashboardLayout title="Invoices" subtitle="Missing batch id.">
        <p className="text-slate-600">No batch selected.</p>
      </DashboardLayout>
    );
  }

  const firstDoc = documents[0];
  const subtitle = firstDoc
    ? `${firstDoc.buyer_name} – ${firstDoc.product_name}`
    : "Proforma Invoice, Invoice & Commercial/Tax Invoice";

  const hasInvoices = documents.length > 0;

  return (
    <DashboardLayout title="Invoices" subtitle={subtitle}>
      <div className="space-y-4">
        {/* Breadcrumb */}
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/documents" className="btn-ghost btn-sm">
            ← Dashboard
          </Link>
          <span className="text-slate-400">/</span>
          <Link to={`/documents/batch/${batchId}`} className="btn-ghost btn-sm">
            Batch Documents
          </Link>
        </div>

        {/* Error */}
        {error && (
          <div className="alert-error" role="alert">
            {error}
          </div>
        )}

        {/* Header row */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-800">
              Proforma Invoice, Invoice &amp; Commercial/Tax Invoice
            </h2>
            <p className="mt-0.5 text-sm text-slate-500">
              Derived from the quotation — same content, updated headings and numbers.
              {hasInvoices && " Re-generate to refresh from the latest quotation."}
            </p>
          </div>

          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating || loading}
            className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-teal-700 focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-1 disabled:cursor-wait disabled:opacity-70"
          >
            {generating ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" aria-hidden />
                Generating…
              </>
            ) : hasInvoices ? (
              "Regenerate"
            ) : (
              "Generate Invoices"
            )}
          </button>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex min-h-[200px] items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" aria-hidden />
          </div>
        ) : !hasInvoices ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 py-14 text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-100">
              <svg
                className="h-7 w-7 text-indigo-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
                aria-hidden
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"
                />
              </svg>
            </div>
            <p className="mb-1 text-sm font-medium text-slate-700">No invoices generated yet</p>
            <p className="mb-5 text-xs text-slate-500">
              Click &ldquo;Generate Invoices&rdquo; to create the Proforma Invoice, Invoice, and
              Commercial Invoice/Tax Invoice from the batch quotation.
            </p>
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating}
              className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-teal-700 disabled:opacity-70"
            >
              {generating ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" aria-hidden />
                  Generating…
                </>
              ) : (
                "Generate Invoices"
              )}
            </button>
          </div>
        ) : (
          <DocumentTable
            documents={documents}
            showBatchLink={false}
            onDelete={(id) => setDeleteId(id)}
            loading={false}
          />
        )}

        <ConfirmModal
          open={deleteId !== null}
          title="Delete document?"
          message="This document will be permanently deleted. This cannot be undone."
          confirmLabel="Delete"
          variant="danger"
          loading={deleteLoading}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteId(null)}
        />
      </div>
    </DashboardLayout>
  );
}
