interface DocumentPaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export function DocumentPagination({
  page,
  pageSize,
  total,
  onPageChange,
}: DocumentPaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  if (total === 0) return null;

  return (
    <nav
      className="mt-4 flex flex-wrap items-center justify-between gap-3 pt-4 sm:mt-6 sm:gap-4"
      aria-label="Pagination"
    >
      <p className="text-xs text-slate-500 sm:text-sm">
        Showing <span className="font-medium text-slate-700">{start}–{end}</span> of{" "}
        <span className="font-medium text-slate-700">{total}</span>
      </p>
      <div className="flex items-center gap-1.5 sm:gap-2">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="btn-outline btn-sm min-h-9 disabled:opacity-50 sm:min-h-10"
          aria-label="Previous page"
        >
          Previous
        </button>
        <span className="px-1.5 text-xs text-slate-500 sm:px-2 sm:text-sm" aria-live="polite">
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="btn-outline btn-sm min-h-9 disabled:opacity-50 sm:min-h-10"
          aria-label="Next page"
        >
          Next
        </button>
      </div>
    </nav>
  );
}
