import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useActiveJob } from "../context/ActiveJobContext";
import { useJobStream, getActiveJobId } from "../hooks/useJobStream";
import type { RowProgress } from "../hooks/useJobStream";
import { PageLayout } from "../components/ui/PageLayout";
import { SendEmailModal } from "../components/SendEmailModal";

function truncate(s: string, max: number) {
  return s.length > max ? s.slice(0, max) + "…" : s;
}

function RowStatusIcon({ done, active }: { done: boolean; active: boolean }) {
  if (done) {
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-teal-500 text-white shrink-0">
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </span>
    );
  }
  if (active) {
    return (
      <span className="flex h-6 w-6 items-center justify-center shrink-0">
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
      </span>
    );
  }
  return (
    <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-slate-200 bg-slate-50 shrink-0">
      <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />
    </span>
  );
}

function StatusBadge({ status }: { status: "done" | "in_progress" | "queued" }) {
  const config = {
    done: { label: "Done", className: "bg-teal-100 text-teal-700" },
    in_progress: { label: "In progress", className: "bg-amber-100 text-amber-800" },
    queued: { label: "Queued", className: "bg-slate-100 text-slate-500" },
  }[status];
  return (
    <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${config.className}`}>
      {config.label}
    </span>
  );
}

function RowItem({ row, active }: { row: RowProgress; active: boolean }) {
  const products = row.product_name.split(",").map((p) => p.trim()).filter(Boolean);
  const status: "done" | "in_progress" | "queued" = active ? "in_progress" : row.done ? "done" : "queued";
  return (
    <li
      className={`flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors ${
        active
          ? "bg-teal-50 ring-1 ring-teal-200"
          : row.done
          ? "bg-white"
          : "bg-slate-50/50 opacity-60"
      }`}
    >
      <RowStatusIcon done={row.done} active={active} />
      <div className="min-w-0 flex-1">
        <p className={`text-sm font-medium leading-snug ${row.done ? "text-slate-700" : active ? "text-teal-800" : "text-slate-500"}`}>
          {truncate(row.buyer_name, 36)}
        </p>
        <div className="mt-0.5 flex flex-wrap gap-1">
          {products.slice(0, 4).map((p, i) => (
            <span key={i} className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500">
              {truncate(p, 28)}
            </span>
          ))}
          {products.length > 4 && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-400">
              +{products.length - 4} more
            </span>
          )}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <StatusBadge status={status} />
        {row.done && row.doc_count > 0 && (
          <span className="rounded-full bg-teal-50 px-2.5 py-1 text-[11px] font-semibold text-teal-600">
            {row.doc_count} doc{row.doc_count !== 1 ? "s" : ""}
          </span>
        )}
      </div>
    </li>
  );
}

export function GeneratePage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setActiveJobId } = useActiveJob();
  const jobId = searchParams.get("job") || getActiveJobId();
  const [streamState, { stop }] = useJobStream(jobId, () => setActiveJobId(null));

  const [showAll, setShowAll] = useState(false);
  const [showEmailModal, setShowEmailModal] = useState(false);

  useEffect(() => {
    if (!jobId) navigate("/", { replace: true });
  }, [jobId, navigate]);

  if (!jobId) return null;

  const docs =
    streamState.status === "streaming" || streamState.status === "done"
      ? streamState.documents
      : [];
  const count = docs.length;

  const progress =
    streamState.status === "streaming" || streamState.status === "done"
      ? streamState.progress
      : null;

  const totalRows = progress?.total_rows ?? 0;
  const completedRows = progress?.rows.filter((r) => r.done).length ?? 0;
  const currentRowIndex = progress?.current_row_index ?? null;
  const allRows = progress?.rows ?? [];
  const pct = totalRows > 0 ? Math.round((completedRows / totalRows) * 100) : 0;

  const PREVIEW_COUNT = 6;
  const visibleRows = showAll ? allRows : allRows.slice(0, PREVIEW_COUNT);

  return (
    <>
    <PageLayout
      step="Step 3 of 3"
      title="Generating documents"
      subtitle={
        streamState.status === "queued"
          ? "Your job is in the queue. It will start when a slot is free."
          : streamState.status === "done" && count > 0
          ? `All done — ${count} document${count !== 1 ? "s" : ""} created.`
          : streamState.status === "streaming"
          ? totalRows > 0
            ? `Row ${completedRows + 1} of ${totalRows} — ${count} document${count !== 1 ? "s" : ""} so far.`
            : `${count} document${count !== 1 ? "s" : ""} created so far…`
          : undefined
      }
      toolbar={
        <div className="flex flex-wrap items-center gap-2">
          {(streamState.status === "streaming" || streamState.status === "done") && count > 0 && (
            <button type="button" onClick={() => navigate("/documents")} className="btn-outline">
              Open Dashboard
            </button>
          )}
          {streamState.status === "done" && count > 0 && (
            <button
              type="button"
              onClick={() => setShowEmailModal(true)}
              className="btn-primary flex items-center gap-2"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              Send Emails
            </button>
          )}
          {(streamState.status === "connecting" || streamState.status === "streaming" || streamState.status === "queued") && (
            <button
              type="button"
              onClick={stop}
              className="btn-ghost text-amber-700 hover:bg-amber-50 hover:text-amber-800"
            >
              Stop generating
            </button>
          )}
        </div>
      }
    >
      <div className="space-y-4">
        {/* ── Connecting ── */}
        {streamState.status === "connecting" && (
          <div className="card-elevated flex items-center gap-4 p-6">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-teal-500 border-t-transparent shrink-0" />
            <div>
              <p className="font-medium text-slate-700">Connecting to generation server…</p>
              <p className="mt-0.5 text-sm text-slate-500">Document generation usually takes 30–90 seconds per row. Please wait.</p>
            </div>
          </div>
        )}

        {/* ── Queued ── */}
        {streamState.status === "queued" && (
          <div className="card-elevated flex items-center gap-4 p-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-100 shrink-0">
              <svg className="h-5 w-5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <p className="font-medium text-slate-700">Waiting in queue</p>
              <p className="mt-0.5 text-sm text-slate-500">
                {streamState.message ?? "Your batch will start when a slot is free. Up to 2 batches run at a time."}
              </p>
            </div>
          </div>
        )}

        {/* ── Progress card (streaming or done with docs) ── */}
        {(streamState.status === "streaming" || (streamState.status === "done" && count > 0)) && (
          <div className="card-elevated overflow-hidden p-0">
            {/* Header with progress bar */}
            <div className="border-b border-slate-100 px-5 py-4">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="font-semibold text-slate-800">
                    {streamState.status === "done" ? "Generation complete" : "Generating documents…"}
                  </p>
                  {totalRows > 0 && (
                    <p className="mt-0.5 text-sm text-slate-500">
                      {streamState.status === "done"
                        ? `${completedRows} row${completedRows !== 1 ? "s" : ""} processed · ${count} document${count !== 1 ? "s" : ""} created`
                        : `Row ${completedRows + 1} of ${totalRows} · ${count} doc${count !== 1 ? "s" : ""} created`}
                    </p>
                  )}
                </div>

                {/* Circular-ish percentage badge */}
                {totalRows > 0 && (
                  <div className="shrink-0 text-center">
                    <span className={`text-2xl font-bold tabular-nums ${streamState.status === "done" ? "text-teal-600" : "text-slate-700"}`}>
                      {streamState.status === "done" ? "100" : pct}%
                    </span>
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide">rows done</p>
                  </div>
                )}
              </div>

              {/* Progress bar */}
              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100">
                {streamState.status === "done" ? (
                  <div className="h-2 w-full rounded-full bg-teal-500 transition-all duration-500" />
                ) : totalRows > 0 ? (
                  <div
                    className="h-2 rounded-full bg-teal-500 transition-all duration-700"
                    style={{ width: `${Math.max(pct, 3)}%` }}
                  />
                ) : (
                  <div className="progress-fill-indeterminate h-2" />
                )}
              </div>
            </div>

            {/* Stats row */}
            {totalRows > 0 && (
              <div className="grid grid-cols-3 divide-x divide-slate-100 border-b border-slate-100 text-center">
                <div className="px-4 py-3">
                  <p className="text-xl font-bold text-slate-800 tabular-nums">{completedRows}</p>
                  <p className="text-[11px] text-slate-400 uppercase tracking-wide">Rows done</p>
                </div>
                <div className="px-4 py-3">
                  <p className="text-xl font-bold text-slate-800 tabular-nums">
                    {totalRows - completedRows - (streamState.status === "streaming" ? 1 : 0)}
                  </p>
                  <p className="text-[11px] text-slate-400 uppercase tracking-wide">Rows queued</p>
                </div>
                <div className="px-4 py-3">
                  <p className="text-xl font-bold text-teal-600 tabular-nums">{count}</p>
                  <p className="text-[11px] text-slate-400 uppercase tracking-wide">Docs created</p>
                </div>
              </div>
            )}

            {/* Row progress list */}
            {allRows.length > 0 && (
              <div className="px-4 py-3">
                <div className="mb-3 flex flex-wrap items-center gap-4">
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                    Row queue
                  </p>
                  <div className="flex items-center gap-3 text-[10px] text-slate-500" role="list" aria-label="Status legend">
                    <span className="flex items-center gap-1.5">
                      <span className="flex h-4 w-4 items-center justify-center rounded-full bg-teal-500 text-white">
                        <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      </span>
                      Done
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-amber-500 border-t-transparent" />
                      In progress
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="flex h-4 w-4 items-center justify-center rounded-full border-2 border-slate-200 bg-slate-50">
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />
                      </span>
                      Queued
                    </span>
                  </div>
                </div>
                <ul className="space-y-1.5">
                  {visibleRows.map((row) => (
                    <RowItem
                      key={row.row_index}
                      row={row}
                      active={row.row_index === currentRowIndex}
                    />
                  ))}
                  {/* Pending rows not yet started */}
                  {Array.from({ length: Math.max(0, totalRows - allRows.length) }).map((_, i) => (
                    <li
                      key={`pending-${i}`}
                      className="flex items-center gap-3 rounded-lg bg-slate-50/50 px-3 py-2.5"
                    >
                      <RowStatusIcon done={false} active={false} />
                      <span className="flex-1 text-sm text-slate-500">Row {allRows.length + i + 1} — waiting…</span>
                      <StatusBadge status="queued" />
                    </li>
                  ))}
                </ul>
                {allRows.length > PREVIEW_COUNT && (
                  <button
                    type="button"
                    onClick={() => setShowAll((v) => !v)}
                    className="mt-2 w-full rounded-lg border border-slate-200 bg-slate-50 py-1.5 text-xs text-slate-500 transition-colors hover:bg-slate-100"
                  >
                    {showAll ? "Show less" : `Show all ${allRows.length} rows`}
                  </button>
                )}
              </div>
            )}

            {/* "Currently processing" indicator when no row list yet */}
            {allRows.length === 0 && streamState.status === "streaming" && (
              <div className="flex items-center gap-3 px-5 py-4 text-teal-600">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
                <span className="text-sm font-medium">Starting first row…</span>
              </div>
            )}
          </div>
        )}

        {/* ── Done banner ── */}
        {streamState.status === "done" && count > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-teal-200 bg-teal-50 px-5 py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-teal-500 text-white shrink-0">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div>
                <p className="font-semibold text-teal-800">All documents ready!</p>
                <p className="text-sm text-teal-600">{count} document{count !== 1 ? "s" : ""} saved to the dashboard.</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => navigate("/documents")} className="btn-primary">
                Open Dashboard
              </button>
              <button type="button" onClick={() => navigate("/")} className="btn-outline">
                Upload another file
              </button>
            </div>
          </div>
        )}

        {/* ── Done but empty ── */}
        {streamState.status === "done" && count === 0 && (
          <>
            <div className="alert-warning" role="alert">
              <strong>No documents were created.</strong> The job may have failed silently. Check the backend terminal for errors. If you see "MongoDB" or "SSL", fix your database connection first.
            </div>
            <div className="flex flex-wrap gap-3">
              <button type="button" onClick={() => navigate("/documents")} className="btn-primary">
                Go to Dashboard
              </button>
              <button type="button" onClick={() => navigate("/preview")} className="btn-outline">
                Try again from Preview
              </button>
            </div>
          </>
        )}

        {/* ── Error ── */}
        {streamState.status === "error" && (
          <>
            <div className="alert-error" role="alert">
              <strong>Connection error:</strong> {streamState.message}
              <p className="mt-2 text-sm">
                Ensure the backend is running and MongoDB is reachable. Try opening the Dashboard — documents may have been partially saved.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <button type="button" onClick={() => navigate("/documents")} className="btn-primary">
                Open Dashboard
              </button>
              <button type="button" onClick={() => navigate("/preview")} className="btn-outline">
                Back to Preview
              </button>
            </div>
          </>
        )}
      </div>
    </PageLayout>

    {showEmailModal && docs[0]?.batch_id && (
      <SendEmailModal
        batchId={docs[0].batch_id}
        onClose={() => setShowEmailModal(false)}
      />
    )}
    </>
  );
}
