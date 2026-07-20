import { useState } from "react";
import { EmailPreviewBox } from "./EmailPreviewBox";

interface DocTypeOption {
  value: string;
  label: string;
}

interface Props {
  buyerName: string;
  productName: string;
  senderEmail: string;
  recipientEmail: string;
  defaultSubject: string;
  defaultMessage: string;
  initialSubject: string;
  initialMessage: string;
  docTypeOptions: DocTypeOption[];
  defaultDocTypes: string[];
  initialDocTypes: string[];
  onSave: (subject: string, message: string, docTypes: string[]) => void;
  onClose: () => void;
}

function attachmentNamesFor(docTypes: string[], productName: string): string[] {
  const safe = productName.slice(0, 40).replace(/\//g, "-").replace(/ /g, "_");
  return docTypes.map((t) => `${t.toUpperCase()}_${safe}.pdf`);
}

export function PerRowEmailModal({
  buyerName,
  productName,
  senderEmail,
  recipientEmail,
  defaultSubject,
  defaultMessage,
  initialSubject,
  initialMessage,
  docTypeOptions,
  defaultDocTypes,
  initialDocTypes,
  onSave,
  onClose,
}: Props) {
  const [subject, setSubject] = useState(initialSubject);
  const [message, setMessage] = useState(initialMessage);
  const [docTypes, setDocTypes] = useState<string[]>(initialDocTypes.length ? initialDocTypes : defaultDocTypes);
  const [previewing, setPreviewing] = useState(false);

  const hasTextOverride = subject.trim() !== "" || message.trim() !== "";
  const docTypesChanged =
    docTypes.length !== defaultDocTypes.length || docTypes.some((t) => !defaultDocTypes.includes(t));
  const resolvedSubject = subject.trim() || defaultSubject;
  const resolvedMessage = message.trim() || defaultMessage;
  const attachments = attachmentNamesFor(docTypes, productName);

  function toggleDocType(type: string) {
    setDocTypes((prev) => (prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]));
  }

  function handleSave() {
    onSave(subject.trim(), message.trim(), docTypes);
    onClose();
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-[2px]">
      <div className="flex max-h-[88vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between gap-4 border-b border-slate-100 px-6 py-4">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-slate-800">Customize this email</h2>
            <p className="truncate text-xs text-slate-400">{buyerName} · {productName}</p>
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
          {previewing ? (
            <EmailPreviewBox
              from={senderEmail}
              to={recipientEmail}
              subject={resolvedSubject}
              message={resolvedMessage}
              attachments={attachments}
              onBack={() => setPreviewing(false)}
              onSend={handleSave}
              sending={false}
              sendLabel="Save"
            />
          ) : (
            <div className="space-y-5">
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-slate-400">
                  Subject — this recipient only
                </label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder={defaultSubject}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 transition-shadow focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-100"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-widest text-slate-400">
                  Message — this recipient only
                </label>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder={defaultMessage}
                  rows={6}
                  className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm leading-relaxed text-slate-800 transition-shadow focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-100"
                />
                <p className="mt-1.5 text-xs text-slate-400">
                  Leave either field blank to use the batch default shown as a placeholder above.
                </p>
              </div>

              {hasTextOverride && (
                <button
                  type="button"
                  onClick={() => { setSubject(""); setMessage(""); }}
                  className="text-xs font-medium text-teal-600 hover:underline"
                >
                  Reset subject/message to batch default
                </button>
              )}

              <div className="border-t border-slate-100 pt-5">
                <div className="mb-2 flex items-center justify-between">
                  <label className="block text-xs font-semibold uppercase tracking-widest text-slate-400">
                    Attach documents — this recipient only
                  </label>
                  <span className="text-xs font-medium text-teal-600">{docTypes.length} selected</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {docTypeOptions.map((opt) => {
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
                {docTypesChanged && (
                  <button
                    type="button"
                    onClick={() => setDocTypes(defaultDocTypes)}
                    className="mt-2 text-xs font-medium text-teal-600 hover:underline"
                  >
                    Reset attachments to batch default
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {!previewing && (
          <div className="flex shrink-0 gap-2 border-t border-slate-100 px-6 py-4">
            <button type="button" onClick={onClose} className="btn-outline flex-1">
              Cancel
            </button>
            <button type="button" onClick={() => setPreviewing(true)} disabled={docTypes.length === 0} className="btn-outline flex-1">
              Preview
            </button>
            <button type="button" onClick={handleSave} disabled={docTypes.length === 0} className="btn-primary flex-1">
              Save
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
