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
        <div className="flex items-center gap-2">
          <Link to="/documents" className="btn-ghost btn-sm">
            ← Back to Dashboard
          </Link>
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
