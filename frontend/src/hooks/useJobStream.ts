import { useEffect, useRef, useState } from "react";
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

export type JobStreamState =
  | { status: "connecting" }
  | { status: "streaming"; documents: DocumentSummary[] }
  | { status: "done"; documents: DocumentSummary[] }
  | { status: "error"; message: string };

export function useJobStream(
  jobId: string | null,
  onDone?: () => void
): JobStreamState {
  const [state, setState] = useState<JobStreamState>(
    jobId ? { status: "connecting" } : { status: "done", documents: [] }
  );
  const docsRef = useRef<DocumentSummary[]>([]);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (!jobId) {
      setState({ status: "done", documents: [] });
      return;
    }
    docsRef.current = [];
    setState({ status: "connecting" });

    const url = getJobStreamUrl(jobId);
    const es = new EventSource(url);
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
        const data = JSON.parse(e.data) as { type: string; doc?: Record<string, unknown> };
        if (data.type === "document" && data.doc) {
          const doc = data.doc as DocumentSummary;
          docsRef.current = [...docsRef.current, doc];
          setState({ status: "streaming", documents: docsRef.current });
        } else if (data.type === "done") {
          setState({ status: "done", documents: docsRef.current });
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
    };
  }, [jobId]);

  return state;
}
