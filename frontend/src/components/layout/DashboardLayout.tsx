import { ReactNode } from "react";

interface DashboardLayoutProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
}

/**
 * Centered dashboard layout: single column, responsive.
 * Use for Documents and other list/dashboard pages.
 */
export function DashboardLayout({ title, subtitle, children }: DashboardLayoutProps) {
  return (
    <div className="dashboard-container">
      <header className="mb-6 sm:mb-8 md:mb-10">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-800 sm:text-3xl md:text-4xl">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1.5 text-sm font-normal text-slate-500 sm:mt-2">
            {subtitle}
          </p>
        )}
      </header>
      {children}
    </div>
  );
}
