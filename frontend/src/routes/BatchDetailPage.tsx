import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { DashboardLayout } from "../components/layout/DashboardLayout";
import { DocumentTable } from "../components/documents/DocumentTable";
import { ConfirmModal } from "../components/ui/ConfirmModal";
import { listDocuments, deleteDocument } from "../lib/api";
import type { DocumentSummary } from "../lib/types";

const DOC_TYPE_ORDER = ["quotation", "tds", "coa", "msds"] as const;

export function BatchDetailPage() {
  const { batchId } = useParams<{ batchId: string }>();
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const fetchBatch = useCallback(async () => {
    if (!batchId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await listDocuments({ batch_id: batchId, limit: 20 });
      const sorted = [...(res.documents || [])].sort(
        (a, b) => DOC_TYPE_ORDER.indexOf(a.doc_type as typeof DOC_TYPE_ORDER[number]) - DOC_TYPE_ORDER.indexOf(b.doc_type as typeof DOC_TYPE_ORDER[number])
      );
      setDocuments(sorted);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load batch");
    } finally {
      setLoading(false);
    }
  }, [batchId]);

  useEffect(() => {
    fetchBatch();
  }, [fetchBatch]);

  const handleDeleteConfirm = async () => {
    if (!deleteId) return;
    const wasOnlyOne = documents.length === 1;
    setDeleteLoading(true);
    setError(null);
    try {
      await deleteDocument(deleteId);
      setDocuments((prev) => prev.filter((d) => d.id !== deleteId));
      setDeleteId(null);
      if (wasOnlyOne) navigate("/documents");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleteLoading(false);
    }
  };

  if (!batchId) {
    return (
      <DashboardLayout title="Batch" subtitle="Missing batch id.">
        <p className="text-slate-600">No batch selected.</p>
      </DashboardLayout>
    );
  }

  const firstDoc = documents[0];
  const title = firstDoc ? `${firstDoc.buyer_name} – ${firstDoc.product_name}` : "Batch documents";

  return (
    <DashboardLayout
      title="Batch"
      subtitle={title}
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link to="/documents" className="btn-ghost btn-sm">
            ← Back to Dashboard
          </Link>

          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/documents/batch/${batchId}/edit-row`}
              className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-100 focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:ring-offset-1"
            >
              <svg
                className="h-4 w-4 shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
                aria-hidden
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
              Edit Row &amp; Regenerate
            </Link>
            <Link
              to={`/documents/batch/${batchId}/invoices`}
              className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-700 transition-colors hover:bg-indigo-100 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1"
            >
              <svg
                className="h-4 w-4 shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
                aria-hidden
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"
                />
              </svg>
              Invoices
            </Link>
          </div>
        </div>

        {error && (
          <div className="alert-error" role="alert">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex min-h-[200px] items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" aria-hidden />
          </div>
        ) : documents.length === 0 ? (
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-8 text-center text-slate-600">
            No documents found for this batch.
          </p>
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
