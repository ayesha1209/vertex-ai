import { useEffect, useRef, useState } from "react";
import { PageLayout } from "../components/ui/PageLayout";
import { EmailPreviewBox } from "../components/EmailPreviewBox";
import { PerRowEmailModal } from "../components/PerRowEmailModal";
import { getSenderEmails, type EmailSendResult } from "../lib/api";

const DOC_TYPES = [
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

function resolvePlaceholders(text: string, buyerName: string, productName: string): string {
  return text.replace(/\{product_name\}/g, productName).replace(/\{buyer_name\}/g, buyerName);
}

interface PreviewRow {
  buyer_name: string;
  email: string;
  product_name: string;
  batch_id: string | null;
  doc_count: number;
  has_email: boolean;
  has_docs: boolean;
}

type Step = "upload" | "preview" | "sending" | "done";

export function EmailSendPage() {
  const [step, setStep] = useState<Step>("upload");
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const [rows, setRows] = useState<PreviewRow[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const [senders, setSenders] = useState<string[]>([]);
  const [sender, setSender] = useState("");
  const [docTypes, setDocTypes] = useState<string[]>(["quotation"]);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [previewingEmail, setPreviewingEmail] = useState(false);
  const [rowSubjects, setRowSubjects] = useState<Record<number, string>>({});
  const [rowMessages, setRowMessages] = useState<Record<number, string>>({});
  const [rowDocTypes, setRowDocTypes] = useState<Record<number, string[]>>({});
  const [editingRowIndex, setEditingRowIndex] = useState<number | null>(null);

  const [sending, setSending] = useState(false);
  const [results, setResults] = useState<EmailSendResult[]>([]);
  const [sendError, setSendError] = useState<string | null>(null);

  const API = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "/api" : "http://localhost:8000/api");

  useEffect(() => {
    getSenderEmails().then((s) => {
      setSenders(s);
      if (s.length > 0) setSender(s[0]);
    });
  }, []);

  async function handleFile(file: File) {
    setUploadError(null);
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API}/email/preview-from-excel`, { method: "POST", body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || "Upload failed");
      }
      const data: PreviewRow[] = await res.json();
      setRows(data);
      // Pre-select rows that have both email and docs
      setSelected(new Set(data.map((_, i) => i).filter((i) => data[i].has_email && data[i].has_docs)));
      setStep("preview");
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function toggleSelect(i: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }

  function toggleDocType(t: string) {
    setDocTypes((prev) => prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]);
  }

  async function handleSend() {
    if (!sender || docTypes.length === 0 || selected.size === 0) return;
    setSending(true);
    setSendError(null);
    setStep("sending");

    const sendRows = [...selected].map((i) => ({
      buyer_name: rows[i].buyer_name,
      email: rows[i].email,
      product_name: rows[i].product_name,
      batch_id: rows[i].batch_id!,
      subject: rowSubjects[i]?.trim() || undefined,
      message: rowMessages[i]?.trim() || undefined,
      doc_types: rowDocTypes[i]?.length ? rowDocTypes[i] : undefined,
    }));

    try {
      const res = await fetch(`${API}/email/send-from-list`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rows: sendRows,
          sender_email: sender,
          doc_types: docTypes,
          subject: subject.trim() || undefined,
          message: message.trim() || undefined,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || "Send failed");
      }
      const data = await res.json();
      setResults(data.results);
      setStep("done");
    } catch (e) {
      setSendError(e instanceof Error ? e.message : "Send failed");
      setStep("preview");
    } finally {
      setSending(false);
    }
  }

  const readyCount = [...selected].filter((i) => rows[i]?.has_email && rows[i]?.has_docs).length;
  const skippedCount = [...selected].filter((i) => !rows[i]?.has_email || !rows[i]?.has_docs).length;

  const readyIndices = [...selected].filter((i) => rows[i]?.has_email && rows[i]?.has_docs);
  const sampleIndex = readyIndices.length > 0 ? readyIndices[0] : null;
  const sampleRow = sampleIndex !== null ? rows[sampleIndex] : null;
  const previewBuyer = sampleRow?.buyer_name || "the buyer";
  const previewProduct = sampleRow?.product_name || "the product";
  const rawSubjectForSample = (sampleIndex !== null && rowSubjects[sampleIndex]) || subject;
  const rawMessageForSample = (sampleIndex !== null && rowMessages[sampleIndex]) || message;
  const resolvedSubject = resolvePlaceholders(rawSubjectForSample.trim() || DEFAULT_SUBJECT_PLACEHOLDER, previewBuyer, previewProduct);
  const resolvedMessage = resolvePlaceholders(rawMessageForSample.trim() || DEFAULT_MESSAGE_PLACEHOLDER, previewBuyer, previewProduct);
  const rawDocTypesForSample = (sampleIndex !== null && rowDocTypes[sampleIndex]?.length) ? rowDocTypes[sampleIndex] : docTypes;
  const previewAttachments = rawDocTypesForSample.map((t) => {
    const safe = previewProduct.slice(0, 40).replace(/\//g, "-").replace(/ /g, "_");
    return `${t.toUpperCase()}_${safe}.pdf`;
  });

  function defaultsFor(row: PreviewRow) {
    return {
      subject: resolvePlaceholders(subject.trim() || DEFAULT_SUBJECT_PLACEHOLDER, row.buyer_name, row.product_name),
      message: resolvePlaceholders(message.trim() || DEFAULT_MESSAGE_PLACEHOLDER, row.buyer_name, row.product_name),
    };
  }

  return (
    <PageLayout title="Send Emails" subtitle="Upload your enquiry Excel to mass-send generated documents to buyers.">
      <div className="space-y-5 max-w-3xl mx-auto">

        {/* ── Step 1: Upload ── */}
        {step === "upload" && (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`flex flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed p-12 transition-colors cursor-pointer
              ${dragging ? "border-teal-400 bg-teal-50" : "border-slate-200 bg-white hover:border-teal-300 hover:bg-slate-50"}`}
            onClick={() => fileRef.current?.click()}
          >
            <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
            {uploading ? (
              <>
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
                <p className="text-sm text-slate-500">Reading Excel…</p>
              </>
            ) : (
              <>
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-teal-50 text-teal-500">
                  <svg className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                  </svg>
                </div>
                <div className="text-center">
                  <p className="font-medium text-slate-700">Drop your Excel file here</p>
                  <p className="mt-1 text-sm text-slate-400">or click to browse — .xlsx / .xls</p>
                </div>
                <p className="text-xs text-slate-400">Same Excel format used for generating documents (needs "Buyer Name", "Product Name", "Email id" columns)</p>
              </>
            )}
            {uploadError && (
              <p className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">{uploadError}</p>
            )}
          </div>
        )}

        {/* ── Step 2: Preview ── */}
        {step === "preview" && (
          <>
            {/* Compose card */}
            <div className="card-elevated space-y-5 p-5">
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-50 text-teal-600">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                </span>
                <h3 className="text-sm font-semibold text-slate-800">Compose email</h3>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-widest text-slate-400 mb-1.5">Send from</label>
                  <select
                    value={sender}
                    onChange={(e) => setSender(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 transition-shadow focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-100"
                  >
                    {senders.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-widest text-slate-400 mb-1.5">Subject</label>
                  <input
                    type="text"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    placeholder={DEFAULT_SUBJECT_PLACEHOLDER}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 transition-shadow focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-100"
                  />
                </div>
              </div>

              <div className="border-t border-slate-100 pt-4">
                <label className="block text-xs font-semibold uppercase tracking-widest text-slate-400 mb-1.5">Message</label>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder={DEFAULT_MESSAGE_PLACEHOLDER}
                  rows={4}
                  className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm leading-relaxed text-slate-800 transition-shadow focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-100"
                />
                <p className="mt-1.5 text-xs text-slate-400">
                  Leave blank to use the defaults. <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px] text-slate-500">{"{product_name}"}</code>{" "}
                  and <code className="rounded bg-slate-100 px-1 py-0.5 text-[11px] text-slate-500">{"{buyer_name}"}</code> are filled in per recipient.
                </p>
              </div>

              <div className="border-t border-slate-100 pt-4">
                <div className="mb-2 flex items-center justify-between">
                  <label className="block text-xs font-semibold uppercase tracking-widest text-slate-400">Attach documents</label>
                  <span className="text-xs font-medium text-teal-600">{docTypes.length} selected</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {DOC_TYPES.map((opt) => {
                    const active = docTypes.includes(opt.value);
                    return (
                      <button key={opt.value} type="button" onClick={() => toggleDocType(opt.value)}
                        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold border transition-colors ${
                          active
                            ? "bg-teal-500 border-teal-500 text-white shadow-sm"
                            : "bg-white border-slate-200 text-slate-500 hover:border-teal-300 hover:text-teal-700"
                        }`}>
                        {active && (
                          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {previewingEmail ? (
              <EmailPreviewBox
                from={sender}
                to={sampleRow?.email || "—"}
                toNote={readyCount > 1 ? `and ${readyCount - 1} more recipient${readyCount - 1 !== 1 ? "s" : ""} (names filled in per buyer)` : undefined}
                subject={resolvedSubject}
                message={resolvedMessage}
                attachments={previewAttachments}
                onBack={() => setPreviewingEmail(false)}
                onSend={handleSend}
                sending={sending}
                sendLabel={`Send ${readyCount} Email${readyCount !== 1 ? "s" : ""}`}
              />
            ) : (
              <>
                {/* Buyer table */}
                <div className="card-elevated overflow-hidden p-0">
                  <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
                    <p className="text-sm font-semibold text-slate-700">
                      {rows.length} buyer{rows.length !== 1 ? "s" : ""} found
                    </p>
                    <div className="flex gap-2">
                      <button type="button" onClick={() => setSelected(new Set(rows.map((r, i) => r.has_email && r.has_docs ? i : -1).filter(i => i >= 0)))}
                        className="text-xs text-teal-600 hover:underline">Select all ready</button>
                      <span className="text-slate-300">|</span>
                      <button type="button" onClick={() => setSelected(new Set())}
                        className="text-xs text-slate-400 hover:underline">Clear</button>
                    </div>
                  </div>

                  <ul className="divide-y divide-slate-50 max-h-[400px] overflow-y-auto">
                    {rows.map((row, i) => {
                      const canSend = row.has_email && row.has_docs;
                      const isSelected = selected.has(i);
                      return (
                        <li key={i}
                          onClick={() => canSend && toggleSelect(i)}
                          className={`flex items-center gap-3 px-5 py-3 transition-colors
                            ${canSend ? "cursor-pointer hover:bg-slate-50" : "opacity-50 cursor-not-allowed"}
                            ${isSelected ? "bg-teal-50/60" : ""}`}
                        >
                          <input type="checkbox" readOnly checked={isSelected} disabled={!canSend}
                            className="h-4 w-4 accent-teal-500 shrink-0" />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <p className="text-sm font-medium text-slate-800 truncate">{row.buyer_name}</p>
                              {(rowSubjects[i]?.trim() || rowMessages[i]?.trim() || rowDocTypes[i]?.length) && (
                                <span className="shrink-0 rounded-full bg-teal-100 px-1.5 py-0.5 text-[9px] font-semibold text-teal-700">
                                  Customized
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-slate-400 truncate">{row.product_name}</p>
                          </div>
                          {canSend && (
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); setEditingRowIndex(i); }}
                              title="Preview / customize this email"
                              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-slate-400 hover:bg-teal-50 hover:text-teal-600"
                            >
                              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 112.828 2.828L11.828 15.828a4 4 0 01-1.414.94l-3.243 1.135 1.135-3.243a4 4 0 01.94-1.414z" />
                              </svg>
                            </button>
                          )}
                          <div className="flex flex-col items-end gap-1 shrink-0">
                            {row.has_email ? (
                              <span className="text-xs text-slate-500 truncate max-w-[180px]">{row.email}</span>
                            ) : (
                              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-700">No email</span>
                            )}
                            {row.has_docs ? (
                              <span className="rounded-full bg-teal-100 px-2 py-0.5 text-[10px] font-semibold text-teal-700">
                                {row.doc_count} doc{row.doc_count !== 1 ? "s" : ""}
                              </span>
                            ) : (
                              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">No docs</span>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>

                {sendError && (
                  <p className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">{sendError}</p>
                )}

                {/* Action bar */}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm text-slate-500">
                    {readyCount} ready to send{skippedCount > 0 ? `, ${skippedCount} will be skipped (missing email/docs)` : ""}
                  </div>
                  <div className="flex gap-2">
                    <button type="button" onClick={() => { setStep("upload"); setRows([]); setSelected(new Set()); }}
                      className="btn-outline">
                      Change file
                    </button>
                    <button type="button" onClick={() => setPreviewingEmail(true)}
                      disabled={readyCount === 0 || !sender || docTypes.length === 0}
                      className="btn-outline">
                      Preview
                    </button>
                    <button type="button" onClick={handleSend}
                      disabled={readyCount === 0 || !sender || docTypes.length === 0}
                      className="btn-primary flex items-center gap-2">
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                      </svg>
                      Send {readyCount} Email{readyCount !== 1 ? "s" : ""}
                    </button>
                  </div>
                </div>
              </>
            )}

            {editingRowIndex !== null && rows[editingRowIndex] && (
              <PerRowEmailModal
                buyerName={rows[editingRowIndex].buyer_name}
                productName={rows[editingRowIndex].product_name}
                senderEmail={sender}
                recipientEmail={rows[editingRowIndex].email}
                defaultSubject={defaultsFor(rows[editingRowIndex]).subject}
                defaultMessage={defaultsFor(rows[editingRowIndex]).message}
                initialSubject={rowSubjects[editingRowIndex] || ""}
                initialMessage={rowMessages[editingRowIndex] || ""}
                docTypeOptions={DOC_TYPES}
                defaultDocTypes={docTypes}
                initialDocTypes={rowDocTypes[editingRowIndex] || []}
                onSave={(s, m, dt) => {
                  setRowSubjects((prev) => ({ ...prev, [editingRowIndex]: s }));
                  setRowMessages((prev) => ({ ...prev, [editingRowIndex]: m }));
                  const isSameAsDefault =
                    dt.length === docTypes.length && dt.every((t) => docTypes.includes(t));
                  setRowDocTypes((prev) => {
                    if (isSameAsDefault) {
                      const next = { ...prev };
                      delete next[editingRowIndex];
                      return next;
                    }
                    return { ...prev, [editingRowIndex]: dt };
                  });
                }}
                onClose={() => setEditingRowIndex(null)}
              />
            )}
          </>
        )}

        {/* ── Step 3: Sending ── */}
        {step === "sending" && (
          <div className="card-elevated flex flex-col items-center gap-5 py-14 text-center">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
            <div>
              <p className="font-semibold text-slate-700">Sending emails…</p>
              <p className="mt-1 text-sm text-slate-400">Generating PDFs and sending via Microsoft 365. Please wait.</p>
            </div>
          </div>
        )}

        {/* ── Step 4: Done ── */}
        {step === "done" && (
          <>
            <div className={`flex items-center gap-3 rounded-xl border px-5 py-4 ${
              results.every(r => r.status === "sent") ? "border-teal-200 bg-teal-50" : "border-amber-200 bg-amber-50"
            }`}>
              <div className={`flex h-9 w-9 items-center justify-center rounded-full shrink-0 ${
                results.every(r => r.status === "sent") ? "bg-teal-500" : "bg-amber-400"
              } text-white`}>
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div>
                <p className="font-semibold text-slate-800">
                  {results.filter(r => r.status === "sent").length} sent · {results.filter(r => r.status === "error").length} failed
                </p>
                <p className="text-sm text-slate-500">Sent from {sender}</p>
              </div>
            </div>

            <div className="card-elevated overflow-hidden p-0">
              <ul className="divide-y divide-slate-50 max-h-[400px] overflow-y-auto">
                {results.map((r, i) => (
                  <li key={i} className={`flex items-center gap-3 px-5 py-3 ${r.status === "sent" ? "" : "bg-red-50/50"}`}>
                    <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-white ${r.status === "sent" ? "bg-teal-500" : "bg-red-400"}`}>
                      {r.status === "sent" ? (
                        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-700 truncate">{r.buyer_name}</p>
                      <p className="text-xs text-slate-400 truncate">{r.email}</p>
                      {r.reason && <p className="text-xs text-red-500 mt-0.5">{r.reason}</p>}
                    </div>
                    <span className={`text-xs font-semibold ${r.status === "sent" ? "text-teal-600" : "text-red-500"}`}>
                      {r.status === "sent" ? "Sent" : "Failed"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <button type="button"
              onClick={() => { setStep("upload"); setRows([]); setSelected(new Set()); setResults([]); }}
              className="btn-outline">
              Send another batch
            </button>
          </>
        )}
      </div>
    </PageLayout>
  );
}
