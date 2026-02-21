import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageLayout } from "../components/ui/PageLayout";
import { FileUpload } from "../components/upload/FileUpload";
import { uploadPreview } from "../lib/api";
import { setStoredPreviewRows } from "../hooks/useJobStream";

export function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const navigate = useNavigate();

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    setSuccess(false);
    try {
      const res = await uploadPreview(file);
      setStoredPreviewRows(res.rows);
      setSuccess(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleViewPreview = () => navigate("/preview");

  return (
    <PageLayout
      step="Step 1 of 3"
      title="Upload your file"
      subtitle="Upload an enquiry Excel (.xlsx) or CSV. Required: Buyer Name, Product name. Other columns (Company, Quotation no, HSN, CAS, Qty, Unit, etc.) are optional — use Excel value when present, or leave empty for AI to generate."
    >
      {/* Centered upload card — cloud-style layout */}
      <div className="flex min-h-[420px] flex-col items-center justify-center sm:min-h-[480px]">
        <div className="w-full max-w-xl">
          <div className="card-elevated p-6 sm:p-8">
            {!success ? (
              <>
                <FileUpload onFileSelected={setFile} disabled={uploading} />

                {file && (
                  <div className="mt-4 flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-slate-50/80 px-4 py-3">
                    <p className="flex items-center gap-2 text-sm text-slate-700">
                      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-teal-100 text-teal-600">
                        <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 20 20" aria-hidden>
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                      </span>
                      <span className="font-medium">{file.name}</span>
                    </p>
                    <button
                      type="button"
                      onClick={handleUpload}
                      disabled={uploading}
                      className="btn-primary btn-sm"
                    >
                      {uploading ? (
                        <>
                          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" aria-hidden />
                          Uploading…
                        </>
                      ) : (
                        "Upload"
                      )}
                    </button>
                  </div>
                )}

                {!file && (
                  <p className="mt-4 text-center text-xs text-slate-500">
                    Select a file above, then click Upload to continue.
                  </p>
                )}

                {error && (
                  <div className="mt-4 alert-error" role="alert">
                    {error}
                  </div>
                )}
              </>
            ) : (
              /* Success state — clear feedback */
              <div className="flex flex-col items-center py-4 text-center">
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600" aria-hidden>
                  <svg className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <h2 className="text-lg font-semibold text-slate-800">File uploaded successfully</h2>
                <p className="mt-1 text-sm text-slate-500">Your file is ready. Continue to preview and generate documents.</p>
                <button
                  type="button"
                  onClick={handleViewPreview}
                  className="btn-primary mt-6"
                >
                  View preview
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </PageLayout>
  );
}
