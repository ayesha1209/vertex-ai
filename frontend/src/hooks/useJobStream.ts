import { useCallback, useEffect, useRef, useState } from "react";
import { getJobStreamUrl } from "../lib/api";
import type { DocumentSummary } from "../lib/types";

const PREVIEW_STORAGE_KEY = "vertex_preview_rows";
const ACTIVE_JOB_KEY = "vertex_active_job_id";

export function getStoredPreviewRows(): unknown {
  try {
    const raw = sessionStorage.getItem(PREVIEW_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setStoredPreviewRows(rows: unknown): void {
  try {
    sessionStorage.setItem(PREVIEW_STORAGE_KEY, JSON.stringify(rows));
  } catch {
    // ignore
  }
}

export function getActiveJobId(): string | null {
  return sessionStorage.getItem(ACTIVE_JOB_KEY);
}

export function setActiveJobId(jobId: string | null): void {
  if (jobId == null) sessionStorage.removeItem(ACTIVE_JOB_KEY);
  else sessionStorage.setItem(ACTIVE_JOB_KEY, jobId);
}

export interface RowProgress {
  row_index: number;
  buyer_name: string;
  product_name: string;
  doc_count: number;
  done: boolean;
}

export interface JobProgress {
  total_rows: number;
  current_row_index: number | null;
  rows: RowProgress[];
}

export type JobStreamState =
  | { status: "connecting" }
  | { status: "queued"; message?: string }
  | { status: "streaming"; documents: DocumentSummary[]; progress: JobProgress }
  | { status: "done"; documents: DocumentSummary[]; progress: JobProgress }
  | { status: "error"; message: string };

const EMPTY_PROGRESS: JobProgress = { total_rows: 0, current_row_index: null, rows: [] };

export function useJobStream(
  jobId: string | null,
  onDone?: () => void
): [JobStreamState, { stop: () => void }] {
  const [state, setState] = useState<JobStreamState>(
    jobId ? { status: "connecting" } : { status: "done", documents: [], progress: EMPTY_PROGRESS }
  );
  const docsRef = useRef<DocumentSummary[]>([]);
  const progressRef = useRef<JobProgress>({ ...EMPTY_PROGRESS });
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;
  const esRef = useRef<EventSource | null>(null);

  const stop = useCallback(() => {
    if (!jobId) return;
    import("../lib/api").then(({ cancelJob }) => cancelJob(jobId).catch(() => {}));
    esRef.current?.close();
    esRef.current = null;
    setState({ status: "done", documents: docsRef.current, progress: progressRef.current });
    setActiveJobId(null);
    onDoneRef.current?.();
  }, [jobId]);

  useEffect(() => {
    if (!jobId) {
      setState({ status: "done", documents: [] });
      return;
    }
    docsRef.current = [];
    progressRef.current = { ...EMPTY_PROGRESS };
    setState({ status: "connecting" });

    const url = getJobStreamUrl(jobId);
    const es = new EventSource(url);
    esRef.current = es;
    // Allow time for first event: document generation (AI + assembly) often takes 30–90+ seconds
    const CONNECT_TIMEOUT_MS = 120_000; // 2 minutes
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const clearConnectTimeout = () => {
      if (timeoutId != null) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
    };

    timeoutId = setTimeout(() => {
      setState((prev) => {
        if (prev.status !== "connecting") return prev;
        es.close();
        return {
          status: "error",
          message:
            "Progress stream timed out. Backend or database may be slow or down. Check uvicorn logs. You can still open Dashboard.",
        };
      });
      clearConnectTimeout();
    }, CONNECT_TIMEOUT_MS);

    es.onmessage = (e) => {
      clearConnectTimeout();
      try {
        const data = JSON.parse(e.data) as {
          type: string;
          doc?: Record<string, unknown>;
          total_rows?: number;
          row_index?: number;
          buyer_name?: string;
          product_name?: string;
        };

        if (data.type === "queued") {
          setState({
            status: "queued",
            message: (data as { message?: string }).message ?? "Waiting in queue…",
          });
        } else if (data.type === "start") {
          progressRef.current = {
            total_rows: data.total_rows ?? 0,
            current_row_index: null,
            rows: [],
          };
          setState({ status: "streaming", documents: docsRef.current, progress: { ...progressRef.current } });

        } else if (data.type === "row_start") {
          const p = progressRef.current;
          // Mark previous row as done
          const prevIdx = p.current_row_index;
          const rows = p.rows.map((r) =>
            r.row_index === prevIdx ? { ...r, done: true } : r
          );
          // Add new row entry
          const newRow: RowProgress = {
            row_index: data.row_index ?? rows.length,
            buyer_name: data.buyer_name ?? "",
            product_name: data.product_name ?? "",
            doc_count: 0,
            done: false,
          };
          progressRef.current = {
            total_rows: data.total_rows ?? p.total_rows,
            current_row_index: data.row_index ?? null,
            rows: [...rows, newRow],
          };
          setState({ status: "streaming", documents: docsRef.current, progress: { ...progressRef.current } });

        } else if (data.type === "document" && data.doc) {
          const doc = data.doc as DocumentSummary;
          docsRef.current = [...docsRef.current, doc];
          // Increment doc count for current row
          const p = progressRef.current;
          const curIdx = p.current_row_index;
          if (curIdx !== null) {
            progressRef.current = {
              ...p,
              rows: p.rows.map((r) =>
                r.row_index === curIdx ? { ...r, doc_count: r.doc_count + 1 } : r
              ),
            };
          }
          setState({ status: "streaming", documents: docsRef.current, progress: { ...progressRef.current } });

        } else if (data.type === "error") {
          setState({
            status: "error",
            message: (data as { message?: string }).message ?? "Stream error",
          });
          es.close();
        } else if (data.type === "done") {
          // Mark last row as done
          const p = progressRef.current;
          progressRef.current = {
            ...p,
            current_row_index: null,
            rows: p.rows.map((r) => ({ ...r, done: true })),
          };
          setState({ status: "done", documents: docsRef.current, progress: { ...progressRef.current } });
          es.close();
          setActiveJobId(null);
          onDoneRef.current?.();
        }
      } catch (err) {
        setState({
          status: "error",
          message: err instanceof Error ? err.message : "Invalid stream data",
        });
        es.close();
      }
    };

    es.onerror = () => {
      clearConnectTimeout();
      es.close();
      setState((prev) =>
        prev.status === "connecting"
          ? {
              status: "error",
              message:
                "Could not connect to progress stream. Is the backend running? If MongoDB fails, the backend returns 500 and the stream may not start.",
            }
          : prev
      );
    };

    return () => {
      clearConnectTimeout();
      es.close();
      esRef.current = null;
    };
  }, [jobId]);

  return [state, { stop }];
}
