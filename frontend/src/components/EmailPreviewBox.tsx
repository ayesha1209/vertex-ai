interface Props {
  from: string;
  to: string;
  toNote?: string;
  subject: string;
  message: string;
  attachments: string[];
  onBack: () => void;
  onSend: () => void;
  sending: boolean;
  sendLabel: string;
}

function initialOf(email: string): string {
  const c = email.trim()[0];
  return c ? c.toUpperCase() : "?";
}

export function EmailPreviewBox({
  from,
  to,
  toNote,
  subject,
  message,
  attachments,
  onBack,
  onSend,
  sending,
  sendLabel,
}: Props) {
  return (
    <div className="space-y-4">
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-slate-400">
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
        </svg>
        Preview
      </p>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        {/* Header block */}
        <div className="flex items-start gap-3 border-b border-slate-100 bg-gradient-to-b from-slate-50 to-white px-4 py-3.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-teal-100 text-sm font-semibold text-teal-700">
            {initialOf(from)}
          </span>
          <div className="min-w-0 flex-1 space-y-1 text-sm">
            <div className="flex flex-wrap items-baseline gap-x-1.5">
              <span className="font-medium text-slate-700 truncate">{from || "—"}</span>
              <span className="text-xs text-slate-400">to</span>
              <span className="text-slate-600 truncate">{to || "—"}</span>
            </div>
            {toNote && <p className="text-xs text-slate-400">{toNote}</p>}
            <p className="pt-0.5 text-[15px] font-semibold text-slate-800 truncate">
              {subject || <span className="italic font-normal text-slate-400">(no subject)</span>}
            </p>
          </div>
        </div>

        {/* Body */}
        <div className="whitespace-pre-wrap px-4 py-4 text-sm leading-relaxed text-slate-700">
          {message || <span className="italic text-slate-400">(empty message)</span>}
        </div>

        {/* Attachments */}
        <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-3">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-slate-400">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 10-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
            </svg>
            {attachments.length} attachment{attachments.length !== 1 ? "s" : ""}
          </p>
          {attachments.length === 0 ? (
            <p className="text-xs text-slate-400">No files attached.</p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {attachments.map((name) => (
                <li
                  key={name}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 shadow-sm"
                >
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-red-50 text-[9px] font-bold text-red-600">
                    PDF
                  </span>
                  <span className="max-w-[220px] truncate">{name}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="flex gap-2">
        <button type="button" onClick={onBack} className="btn-outline flex-1" disabled={sending}>
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          Back to edit
        </button>
        <button
          type="button"
          onClick={onSend}
          disabled={sending}
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
              {sendLabel}
            </>
          )}
        </button>
      </div>
    </div>
  );
}
