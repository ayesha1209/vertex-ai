import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useActiveJob } from "../context/ActiveJobContext";
import { useJobStream, getActiveJobId } from "../hooks/useJobStream";
import { PageLayout } from "../components/ui/PageLayout";
import { DocumentPagination } from "../components/documents/DocumentPagination";
import { DocTypeIcon } from "../components/ui/DocTypeIcon";

const GENERATE_PAGE_SIZE = 10;

export function GeneratePage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setActiveJobId } = useActiveJob();
  const jobId = searchParams.get("job") || getActiveJobId();
  const streamState = useJobStream(jobId, () => setActiveJobId(null));

  const [currentPage, setCurrentPage] = useState(1);

  const docs = streamState.status === "streaming" || streamState.status === "done"
    ? streamState.documents
    : [];
  const count = docs.length;

  const paginatedDocs = useMemo(() => {
    const start = (currentPage - 1) * GENERATE_PAGE_SIZE;
    return docs.slice(start, start + GENERATE_PAGE_SIZE);
  }, [docs, currentPage]);

  useEffect(() => {
    if (!jobId) navigate("/", { replace: true });
  }, [jobId, navigate]);

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(count / GENERATE_PAGE_SIZE));
    if (currentPage > maxPage) setCurrentPage(maxPage);
  }, [count, currentPage]);

  if (!jobId) return null;

  return (
    <PageLayout
      step="Step 3 of 3"
      title="Generating documents"
      subtitle={
        streamState.status === "streaming" || (streamState.status === "done" && count > 0)
          ? `Processed ${count} document${count !== 1 ? "s" : ""}. Open the Dashboard to view or save as PDF.`
          : undefined
      }
      toolbar={
        (streamState.status === "streaming" || streamState.status === "done") && count > 0 ? (
          <button type="button" onClick={() => navigate("/documents")} className="btn-outline">
            Open Dashboard
          </button>
        ) : null
      }
    >
      <div className="card-elevated p-6 sm:p-8">
        {streamState.status === "connecting" && (
          <div className="flex items-center gap-3 text-slate-600" role="status">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" aria-hidden />
            <span>Starting… waiting for first document.</span>
          </div>
        )}

        {(streamState.status === "streaming" || (streamState.status === "done" && count > 0)) && (
          <>
            {/* Animated progress indicator + % */}
            <div className="mb-6">
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className="font-medium text-slate-700">
                  {streamState.status === "done" ? "Complete" : "Generating…"}
                </span>
                <span className="text-slate-500">
                  {streamState.status === "done" ? "100%" : `${count} document${count !== 1 ? "s" : ""}`}
                </span>
              </div>
              <div className="progress-track mt-2">
                {streamState.status === "done" ? (
                  <div className="progress-fill w-full" />
                ) : (
                  <div className="progress-fill-indeterminate" />
                )}
              </div>
            </div>

            {/* Clean rows with doc type icons */}
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 overflow-hidden">
              <ul className="divide-y divide-slate-200/80" role="list">
                {paginatedDocs.map((d, i) => {
                  const globalIndex = (currentPage - 1) * GENERATE_PAGE_SIZE + i;
                  return (
                    <li key={d.id} className="flex items-center gap-4 px-4 py-3 sm:px-5 sm:py-3.5 transition-colors hover:bg-slate-100/50">
                      <DocTypeIcon type={d.doc_type} />
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-slate-800">{d.buyer_name} / {d.product_name}</p>
                        <p className="text-xs text-slate-500">Processed #{globalIndex + 1}</p>
                      </div>
                      <span className="shrink-0 rounded-full bg-slate-200/80 px-2.5 py-1 text-xs font-medium uppercase text-slate-600">{d.doc_type}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
            {count > GENERATE_PAGE_SIZE && (
              <div className="mt-5">
                <DocumentPagination page={currentPage} pageSize={GENERATE_PAGE_SIZE} total={count} onPageChange={setCurrentPage} />
              </div>
            )}
            {streamState.status === "streaming" && (
              <div className="mt-4 flex items-center gap-2 text-teal-600" role="status">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" aria-hidden />
                <span className="text-sm font-medium">Processing next…</span>
              </div>
            )}
          </>
        )}

        {streamState.status === "done" && count === 0 && (
          <>
            <div className="alert-warning" role="alert">
              <strong>No documents were created.</strong> The job may have failed. Check the backend terminal. If you see &quot;MongoDB&quot; or &quot;SSL&quot;, fix your database connection first.
            </div>
            <div className="mt-5 flex flex-wrap gap-3">
              <button type="button" onClick={() => navigate("/documents")} className="btn-primary">Go to Dashboard</button>
              <button type="button" onClick={() => navigate("/preview")} className="btn-outline">Try again from Preview</button>
            </div>
          </>
        )}

        {streamState.status === "done" && count > 0 && (
          <div className="alert-success mt-4 flex flex-wrap items-center gap-3">
            <span className="text-xl" aria-hidden>✓</span>
            <span className="font-medium">Complete. {count} document(s) created.</span>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => navigate("/documents")} className="btn-primary">Go to Dashboard</button>
              <button type="button" onClick={() => navigate("/")} className="btn-outline">Upload another file</button>
            </div>
          </div>
        )}

        {streamState.status === "error" && (
          <>
            <div className="alert-error" role="alert">
              <strong>Connection error:</strong> {streamState.message}
              <p className="mt-2 text-sm">Ensure the backend is running and MongoDB is reachable. Try opening the Dashboard.</p>
            </div>
            <div className="mt-5 flex flex-wrap gap-3">
              <button type="button" onClick={() => navigate("/documents")} className="btn-primary">Open Dashboard</button>
              <button type="button" onClick={() => navigate("/preview")} className="btn-outline">Back to Preview</button>
            </div>
          </>
        )}
      </div>
    </PageLayout>
  );
}
