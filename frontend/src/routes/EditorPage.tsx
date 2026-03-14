import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getDocument, savePdf, updateDocument } from "../lib/api";
import type { DocumentInDB } from "../lib/types";
import { VertexEditor } from "../components/editor/VertexEditor";
import { PageLayout } from "../components/ui/PageLayout";

const IS_MANUAL = (doc: DocumentInDB) =>
  (doc.batch_id ?? "").startsWith("manual-");

const IS_UNNAMED = (doc: DocumentInDB) =>
  IS_MANUAL(doc) && (doc.product_name === "Manual Document" || !doc.product_name?.trim());

export function EditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<DocumentInDB | null>(null);
  const [currentHtml, setCurrentHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Name modal state (shown on first save of a manual doc)
  const [nameModal, setNameModal] = useState(false);
  const [docTitle, setDocTitle] = useState("");
  const [createdBy, setCreatedBy] = useState("");
  const pendingSaveRef = useRef(false);

  const handleDownloadPdf = () => {
    if (!doc) return;
    savePdf(doc.id);
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

  const doSave = async (meta?: { product_name?: string; employee_name?: string }) => {
    if (!id) {
      setError("Cannot save: document ID is missing.");
      return;
    }
    if (currentHtml == null) {
      setError("Cannot save: editor content not loaded yet. Try clicking the editor first.");
      return;
    }
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await updateDocument(id, currentHtml, meta);
      setDoc((prev) =>
        prev ? { ...prev, updated_at: updated.updated_at, product_name: updated.product_name, employee_name: updated.employee_name } : updated
      );
      setSuccess("Document saved.");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save document");
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    if (!doc) return;
    // First save of an unnamed manual doc → show name modal
    if (IS_UNNAMED(doc) && !pendingSaveRef.current) {
      setDocTitle("");
      setCreatedBy("");
      setNameModal(true);
      return;
    }
    await doSave();
  };

  const handleNameConfirm = async () => {
    pendingSaveRef.current = true;
    setNameModal(false);
    await doSave({
      product_name: docTitle.trim() || "Untitled",
      employee_name: createdBy.trim() || undefined,
    });
  };

  if (!id) {
    return <div className="page-container text-sm text-slate-600">Missing document id.</div>;
  }

  const pageTitle = doc
    ? IS_MANUAL(doc)
      ? `${doc.product_name === "Manual Document" ? "Untitled" : doc.product_name}`
      : `Edit ${doc.doc_type.toUpperCase()} – ${doc.buyer_name} / ${doc.product_name}`
    : "Edit document";

  return (
    <PageLayout
      title={pageTitle}
      subtitle={doc ? "Word-like editor with tables, bullets, and text formatting." : undefined}
      toolbar={
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-ghost" onClick={() => navigate(IS_MANUAL(doc!) ? "/manual" : "/documents")}>← Back</button>
          <button type="button" className="btn-outline" disabled={!doc} onClick={handleDownloadPdf}>PDF</button>
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

      {/* Name modal — shown on first save of unnamed manual doc */}
      {nameModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setNameModal(false); }}
        >
          <div className="w-full max-w-sm rounded-xl bg-white shadow-xl">
            <div className="border-b border-slate-100 px-6 py-4">
              <h2 className="text-base font-semibold text-slate-800">Save Document</h2>
              <p className="mt-0.5 text-xs text-slate-500">Give this document a name before saving.</p>
            </div>
            <div className="flex flex-col gap-4 px-6 py-5">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-slate-600">Document Name <span className="text-red-500">*</span></span>
                <input
                  className="input input-sm"
                  type="text"
                  placeholder="e.g. Offer Letter – April 2026"
                  value={docTitle}
                  onChange={(e) => setDocTitle(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && docTitle.trim() && handleNameConfirm()}
                  autoFocus
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-slate-600">Created by</span>
                <input
                  className="input input-sm"
                  type="text"
                  placeholder="Your name (optional)"
                  value={createdBy}
                  onChange={(e) => setCreatedBy(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && docTitle.trim() && handleNameConfirm()}
                />
              </label>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-6 py-4">
              <button type="button" onClick={() => setNameModal(false)} className="btn-ghost btn-sm">Cancel</button>
              <button
                type="button"
                onClick={handleNameConfirm}
                disabled={!docTitle.trim()}
                className="btn-primary btn-sm"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}
