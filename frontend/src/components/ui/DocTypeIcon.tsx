const DOC_TYPES = ["quotation", "coa", "coc", "tds", "msds", "combined", "proforma_invoice", "invoice"] as const;
type DocType = (typeof DOC_TYPES)[number];

interface DocTypeIconProps {
  type: string;
  className?: string;
}

const icons: Record<DocType, { bg: string; path: string }> = {
  quotation: {
    bg: "bg-blue-100 text-blue-600",
    path: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  },
  coa: {
    bg: "bg-emerald-100 text-emerald-600",
    path: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4",
  },
  coc: {
    bg: "bg-violet-100 text-violet-600",
    path: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
  },
  tds: {
    bg: "bg-amber-100 text-amber-600",
    path: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  },
  msds: {
    bg: "bg-rose-100 text-rose-600",
    path: "M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z",
  },
  combined: {
    bg: "bg-slate-100 text-slate-600",
    path: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  },
  proforma_invoice: {
    bg: "bg-indigo-100 text-indigo-600",
    path: "M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z",
  },
  invoice: {
    bg: "bg-orange-100 text-orange-600",
    path: "M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z",
  },
};

function normalizeDocType(type: string): DocType {
  const lower = (type || "").toLowerCase();
  return DOC_TYPES.includes(lower as DocType) ? (lower as DocType) : "combined";
}

export function DocTypeIcon({ type, className = "" }: DocTypeIconProps) {
  const key = normalizeDocType(type);
  const { bg, path } = icons[key];
  return (
    <span
      className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${bg} ${className}`}
      aria-hidden
    >
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d={path} />
      </svg>
    </span>
  );
}
