import { useEffect, useState } from "react";
import { getSenderEmails, sendBatchEmails, type EmailSendResult } from "../lib/api";

const DOC_TYPE_OPTIONS = [
  { value: "quotation", label: "Quotation" },
  { value: "tds", label: "TDS" },
  { value: "coa", label: "COA" },
  { value: "msds", label: "MSDS" },
];

interface Props {
  batchId: string;
  onClose: () => void;
}

export function SendEmailModal({ batchId, onClose }: Props) {
  const [senders, setSenders] = useState<string[]>([]);
  const [selectedSender, setSelectedSender] = useState("");
  const [docTypes, setDocTypes] = useState<string[]>(["quotation"]);
  const [sending, setSending] = useState(false);
  const [results, setResults] = useState<EmailSendResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSenderEmails()
      .then((emails) => {
        setSenders(emails);
        if (emails.length > 0) setSelectedSender(emails[0]);
      })
      .catch(() => setError("Failed to load sender emails."));
  }, []);

  function toggleDocType(type: string) {
    setDocTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  }

  async function handleSend() {
    if (!selectedSender || docTypes.length === 0) return;
    setSending(true);
    setError(null);
    try {
      const res = await sendBatchEmails({
        batch_id: batchId,
        sender_email: selectedSender,
        doc_types: docTypes,
      });
      setResults(res.results);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send emails.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 className="text-base font-semibold text-slate-800">Send Emails</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {/* Results view */}
          {results ? (
            <div className="space-y-3">
              <p className="text-sm font-medium text-slate-700">
                {results.filter((r) => r.status === "sent").length} sent ·{" "}
                {results.filter((r) => r.status === "error").length} failed
              </p>
              <ul className="space-y-2 max-h-64 overflow-y-auto">
                {results.map((r, i) => (
                  <li key={i} className={`rounded-lg px-3 py-2.5 text-sm ${r.status === "sent" ? "bg-teal-50" : "bg-red-50"}`}>
                    <div className="flex items-center gap-2">
                      {r.status === "sent" ? (
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-teal-500 text-white shrink-0">
                          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        </span>
                      ) : (
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-red-400 text-white shrink-0">
                          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </span>
                      )}
                      <div className="min-w-0">
                        <p className={`font-medium truncate ${r.status === "sent" ? "text-teal-800" : "text-red-700"}`}>
                          {r.buyer_name}
                        </p>
                        <p className="text-xs text-slate-500 truncate">{r.email}</p>
                        {r.reason && <p className="text-xs text-red-500 mt-0.5">{r.reason}</p>}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
              <button type="button" onClick={onClose} className="btn-primary w-full">
                Done
              </button>
            </div>
          ) : (
            <>
              {/* Send from */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-slate-400 mb-1.5">
                  Send from
                </label>
                {senders.length === 0 ? (
                  <p className="text-sm text-slate-400">Loading…</p>
                ) : (
                  <select
                    value={selectedSender}
                    onChange={(e) => setSelectedSender(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-100"
                  >
                    {senders.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                )}
              </div>

              {/* Attach */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-widest text-slate-400 mb-1.5">
                  Attach documents
                </label>
                <div className="flex flex-wrap gap-2">
                  {DOC_TYPE_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => toggleDocType(opt.value)}
                      className={`rounded-full px-3 py-1 text-sm font-medium border transition-colors ${
                        docTypes.includes(opt.value)
                          ? "bg-teal-500 border-teal-500 text-white"
                          : "bg-white border-slate-200 text-slate-600 hover:border-teal-300"
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {error && (
                <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
              )}

              {/* Actions */}
              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={onClose}
                  className="btn-outline flex-1"
                  disabled={sending}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={sending || !selectedSender || docTypes.length === 0}
                  className="btn-primary flex-1 flex items-center justify-center gap-2"
                >
                  {sending ? (
                    <>
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      Sending…
                    </>
                  ) : (
                    <>
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                      </svg>
                      Send Emails
                    </>
                  )}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
