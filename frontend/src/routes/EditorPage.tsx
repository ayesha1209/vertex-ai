import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getDocument, savePdf, updateDocument } from "../lib/api";
import type { DocumentInDB } from "../lib/types";
import { VertexEditor } from "../components/editor/VertexEditor";
import { PageLayout } from "../components/ui/PageLayout";

export function EditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<DocumentInDB | null>(null);
  const [currentHtml, setCurrentHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleDownloadPdf = async () => {
    if (!doc || downloadingPdf) return;
    setDownloadingPdf(true);
    try {
      await savePdf(doc.id);
    } finally {
      setDownloadingPdf(false);
    }
  };

  useEffect(() => {
    const fetchDoc = async () => {
      if (!id) return;
      setLoading(true);
      setError(null);
      try {
        const d = await getDocument(id);
        setDoc(d);
        setCurrentHtml(d.html_content);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to load document");
      } finally {
        setLoading(false);
      }
    };
    fetchDoc();
  }, [id]);

  const handleSave = async () => {
    if (!id || currentHtml == null) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await updateDocument(id, currentHtml);
      setDoc(updated);
      setSuccess("Document saved successfully.");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save document");
    } finally {
      setSaving(false);
    }
  };

  if (!id) {
    return <div className="page-container text-sm text-slate-600">Missing document id.</div>;
  }

  return (
    <PageLayout
      title={doc ? `Edit ${doc.doc_type.toUpperCase()} – ${doc.buyer_name} / ${doc.product_name}` : "Edit document"}
      subtitle={doc ? "Word-like editor with tables, bullets, and text formatting." : undefined}
      toolbar={
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-ghost" onClick={() => navigate("/documents")}>← Back</button>
          <button type="button" className="btn-outline" disabled={!doc || downloadingPdf} onClick={handleDownloadPdf}>{downloadingPdf ? "Saving…" : "PDF"}</button>
          <button type="button" className="btn-primary" onClick={handleSave} disabled={saving || !doc}>{saving ? "Saving…" : "Save"}</button>
        </div>
      }
    >
      {loading && <div className="alert-info flex items-center gap-2" role="status"><div className="h-4 w-4 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" aria-hidden />Loading document…</div>}
      {error && <div className="mb-4 alert-error" role="alert">{error}</div>}
      {success && <div className="mb-4 alert-success" role="status">{success}</div>}
      {doc && (
        <div className="card-elevated overflow-hidden p-4 sm:p-6">
          <VertexEditor initialHtml={doc.html_content} onChange={(html) => setCurrentHtml(html)} />
        </div>
      )}
    </PageLayout>
  );
}

