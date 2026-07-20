import { useEffect, useState } from "react";
import { getBatchEmail, getSenderEmails, sendBatchEmails, type EmailSendResult } from "../lib/api";
import { EmailPreviewBox } from "./EmailPreviewBox";

const DOC_TYPE_OPTIONS = [
  { value: "quotation", label: "Quotation" },
  { value: "tds", label: "TDS" },
  { value: "coa", label: "COA" },
  { value: "msds", label: "MSDS" },
  { value: "proforma_invoice", label: "Proforma Invoice" },
  { value: "invoice", label: "Invoice" },
  { value: "commercial_invoice", label: "Commercial Invoice" },
  { value: "tax_invoice", label: "Tax Invoice" },
];

const DEFAULT_SUBJECT_PLACEHOLDER = "Quotation – {product_name} | Vertex Chemical Corporation";
const DEFAULT_MESSAGE_PLACEHOLDER = `Dear {buyer_name},

Please find attached our quotation for {product_name}.

We look forward to your valued business. Please feel free to contact us for any queries.

Best regards,
Vertex Chemical Corporation`;

interface Props {
  batchId: string;
  onClose: () => void;
  buyerName?: string;
  productName?: string;
  defaultDocTypes?: string[];
}

function resolvePlaceholders(text: string, buyerName: string, productName: string): string {
  return text.replace(/\{product_name\}/g, productName).replace(/\{buyer_name\}/g, buyerName);
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="mb-2 block text-xs font-semibold uppercase tracking-widest text-slate-400">
      {children}
    </label>
  );
}

export function SendEmailModal({
  batchId,
  onClose,
  buyerName = "",
  productName = "",
  defaultDocTypes,
}: Props) {
  const [senders, setSenders] = useState<string[]>([]);
  const [selectedSender, setSelectedSender] = useState("");
  const [docTypes, setDocTypes] = useState<string[]>(defaultDocTypes?.length ? defaultDocTypes : ["quotation"]);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [recipientLoading, setRecipientLoading] = useState(true);
  const [previewing, setPreviewing] = useState(false);
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

  useEffect(() => {
    getBatchEmail(batchId)
      .then((email) => setRecipientEmail(email || ""))
      .finally(() => setRecipientLoading(false));
  }, [batchId]);

  const previewBuyer = buyerName || "the buyer";
  const previewProduct = productName || "the product";
  const resolvedSubject = resolvePlaceholders(subject.trim() || DEFAULT_SUBJECT_PLACEHOLDER, previewBuyer, previewProduct);
  const resolvedMessage = resolvePlaceholders(message.trim() || DEFAULT_MESSAGE_PLACEHOLDER, previewBuyer, previewProduct);
  const attachmentNames = docTypes.map((t) => {
    const safe = previewProduct.slice(0, 40).replace(/\//g, "-").replace(/ /g, "_");
    return `${t.toUpperCase()}_${safe}.pdf`;
  });

  const canSend = !!selectedSender && docTypes.length > 0 && !!recipientEmail.trim();

  function toggleDocType(type: string) {
    setDocTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  }

  async function handleSend() {
    if (!canSend) return;
    setSending(true);
    setError(null);
    try {
      const res = await sendBatchEmails({
        batch_id: batchId,
        sender_email: selectedSender,
        doc_types: docTypes,
        subject: subject.trim() || undefined,
        recipient_email: recipientEmail.trim(),
        message: message.trim() || undefined,
      });
      setResults(res.results);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send emails.");
    } finally {
      setSending(false);
    }
  }

  const sentCount = results?.filter((r) => r.status === "sent").length ?? 0;
  const failedCount = results?.filter((r) => r.status === "error").length ?? 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-[2px]">
      <div className="flex max-h-[88vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between gap-4 border-b border-slate-100 px-6 py-4">
          <div className="flex items-center gap-3 min-w-0">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-teal-50 text-teal-600">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </span>
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-slate-800">Send Email</h2>
              {productName && (
                <p className="truncate text-xs text-slate-400">{buyerName ? `${buyerName} · ` : ""}{productName}</p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          {/* Results view */}
          {results ? (
            <div className="space-y-4">
              <div className={`flex items-center gap-3 rounded-xl border px-4 py-3.5 ${
                failedCount === 0 ? "border-teal-200 bg-teal-50" : "border-amber-200 bg-amber-50"
              }`}>
                <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white ${
                  failedCount === 0 ? "bg-teal-500" : "bg-amber-400"
                }`}>
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
                <p className="text-sm font-semibold text-slate-800">
                  {sentCount} sent{failedCount > 0 ? ` · ${failedCount} failed` : ""}
                </p>
              </div>
              <ul className="space-y-2 max-h-64 overflow-y-auto">
                {results.map((r, i) => (
                  <li key={i} className={`rounded-lg px-3 py-2.5 text-sm ${r.status === "sent" ? "bg-teal-50/70" : "bg-red-50"}`}>
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
          ) : previewing ? (
            <EmailPreviewBox
              from={selectedSender}
              to={recipientEmail}
              subject={resolvedSubject}
              message={resolvedMessage}
              attachments={attachmentNames}
              onBack={() => setPreviewing(false)}
              onSend={handleSend}
              sending={sending}
              sendLabel="Send Email"
            />
          ) : (
            <div className="space-y-6">
              {/* Recipient section */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <SectionLabel>Send from</SectionLabel>
                  {senders.length === 0 ? (
                    <p className="text-sm text-slate-400">Loading…</p>
                  ) : (
                    <select
                      value={selectedSender}
                      onChange={(e) => setSelectedSender(e.target.value)}
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 transition-shadow focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-100"
                    >
                      {senders.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  )}
                </div>

                <div>
                  <SectionLabel>Send to</SectionLabel>
                  <input
                    type="email"
                    value={recipientEmail}
                    onChange={(e) => setRecipientEmail(e.target.value)}
                    placeholder={recipientLoading ? "Loading…" : "buyer@example.com"}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 transition-shadow focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-100"
                  />
                </div>
              </div>
              <p className="-mt-3 text-xs text-slate-400">
                {recipientLoading
                  ? "Checking the batch for a stored email…"
                  : recipientEmail
                    ? "Auto-filled from the batch's Excel — edit to send elsewhere."
                    : "No email stored on this batch — enter one to send."}
              </p>

              {/* Subject */}
              <div className="border-t border-slate-100 pt-5">
                <SectionLabel>Subject</SectionLabel>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder={DEFAULT_SUBJECT_PLACEHOLDER}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 transition-shadow focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-100"
                />
                <p className="mt-1.5 text-xs text-slate-400">
                  Leave blank to use the default. <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px] text-slate-500">{"{product_name}"}</code>{" "}
                  and <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px] text-slate-500">{"{buyer_name}"}</code> get filled in automatically.
                </p>
              </div>

              {/* Message body */}
              <div className="border-t border-slate-100 pt-5">
                <SectionLabel>Message</SectionLabel>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder={DEFAULT_MESSAGE_PLACEHOLDER}
                  rows={7}
                  className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm leading-relaxed text-slate-800 transition-shadow focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-100"
                />
                <p className="mt-1.5 text-xs text-slate-400">
                  Leave blank to use the default message. <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px] text-slate-500">{"{product_name}"}</code>{" "}
                  and <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px] text-slate-500">{"{buyer_name}"}</code> get filled in automatically.
                </p>
              </div>

              {/* Attach */}
              <div className="border-t border-slate-100 pt-5">
                <div className="mb-2 flex items-center justify-between">
                  <SectionLabel>Attach documents</SectionLabel>
                  <span className="text-xs font-medium text-teal-600">{docTypes.length} selected</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {DOC_TYPE_OPTIONS.map((opt) => {
                    const active = docTypes.includes(opt.value);
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => toggleDocType(opt.value)}
                        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium border transition-colors ${
                          active
                            ? "bg-teal-500 border-teal-500 text-white shadow-sm"
                            : "bg-white border-slate-200 text-slate-600 hover:border-teal-300 hover:text-teal-700"
                        }`}
                      >
                        {active && (
                          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {error && (
                <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
              )}
            </div>
          )}
        </div>

        {/* Footer actions */}
        {!results && !previewing && (
          <div className="flex shrink-0 gap-2 border-t border-slate-100 px-6 py-4">
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
              onClick={() => setPreviewing(true)}
              disabled={!canSend}
              className="btn-outline flex-1"
            >
              Preview
            </button>
            <button
              type="button"
              onClick={handleSend}
              disabled={sending || !canSend}
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
                  Send Email
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
