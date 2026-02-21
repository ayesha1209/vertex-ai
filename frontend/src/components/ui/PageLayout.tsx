import { ReactNode } from "react";

interface PageLayoutProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  toolbar?: ReactNode;
  /** Optional step indicator (e.g. "Step 1 of 3") */
  step?: string;
}

export function PageLayout({
  title,
  subtitle,
  children,
  toolbar,
  step,
}: PageLayoutProps) {
  return (
    <div className="page-container">
      <div className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          {step && (
            <p
              className="mb-1 text-xs font-medium uppercase tracking-wider text-teal-600"
              aria-hidden
            >
              {step}
            </p>
          )}
          <h1 className="page-title">{title}</h1>
          {subtitle && <p className="page-subtitle">{subtitle}</p>}
        </div>
        {toolbar && (
          <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
            {toolbar}
          </div>
        )}
      </div>
      {children}
    </div>
  );
}
