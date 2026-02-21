import { NavLink } from "react-router-dom";

interface GenerationProgressCardProps {
  documentCount: number;
  isStreaming: boolean;
  documents: { id: string; buyer_name: string; product_name: string; doc_type: string }[];
}

export function GenerationProgressCard({
  documentCount,
  isStreaming,
  documents,
}: GenerationProgressCardProps) {
  return (
    <div className="card mb-6 overflow-hidden bg-gradient-to-br from-teal-50/80 to-white p-6 shadow-[0_1px_3px_rgb(0_0_0_/0.05)]">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-teal-900">
            Generation in progress
          </h2>
          <p className="mt-0.5 text-sm text-teal-700/90">
            {isStreaming
              ? `${documentCount} document${documentCount !== 1 ? "s" : ""} created so far`
              : "Connecting…"}
          </p>
        </div>
        <NavLink
          to="/generate"
          className="btn-outline btn-sm shrink-0"
        >
          View full progress
        </NavLink>
      </div>
      <div className="progress-track mt-4">
        {isStreaming ? (
          <div className="progress-fill-indeterminate" />
        ) : (
          <div className="progress-fill w-[30%]" />
        )}
      </div>
      {documents.length > 0 && (
        <div className="mt-4 max-h-28 overflow-auto rounded-xl bg-white/70 py-2.5 pl-3 pr-2 shadow-[0_1px_2px_rgb(0_0_0_/0.04)]">
          <ul className="space-y-1.5 text-xs text-slate-600" role="list">
            {documents.slice(-6).map((d) => (
              <li key={d.id} className="flex justify-between gap-2">
                <span className="truncate">{d.buyer_name} / {d.product_name}</span>
                <span className="shrink-0 uppercase text-slate-500">{d.doc_type}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
