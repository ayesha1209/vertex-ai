import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useActiveJob } from "../../context/ActiveJobContext";

const navItems: { to: string; label: string; step?: string; showWhen?: string }[] = [
  { to: "/", label: "Upload", step: "1" },
  { to: "/generate", label: "Generate", step: "2", showWhen: "activeJob" },
  { to: "/documents", label: "Dashboard" },
  { to: "/terms", label: "Terms & Conditions" },
];

export function Header() {
  const location = useLocation();
  const { activeJobId } = useActiveJob();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const isActive = (path: string) => {
    if (path === "/") return location.pathname === "/";
    if (path === "/documents") return location.pathname === "/documents" || location.pathname.startsWith("/documents/");
    if (path === "/generate") return location.pathname === "/generate";
    if (path === "/terms") return location.pathname === "/terms";
    return false;
  };

  const visibleNavItems = navItems.filter((item) => {
    if (item.showWhen === "activeJob" && !activeJobId) return false;
    return true;
  });

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white shadow-sm">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <div className="page-container">
        <div className="flex min-h-[3.25rem] items-center justify-between gap-4">
          <Link
            to="/"
            className="flex shrink-0 items-center gap-2.5 rounded-lg py-2 pr-2 focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-2"
            onClick={() => setMobileMenuOpen(false)}
          >
            <div
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-teal-600 text-sm font-bold text-white"
              aria-hidden
            >
              V
            </div>
            <span className="hidden text-sm font-semibold text-slate-800 sm:inline">Vertex</span>
          </Link>

          <nav className="hidden items-center gap-1 md:flex" aria-label="Main navigation">
            {visibleNavItems.map(({ to, label, step }) => {
              const active = isActive(to);
              return (
                <Link
                  key={to}
                  to={to}
                  className={`
                    flex min-h-[2.5rem] items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors
                    ${active ? "bg-teal-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100 hover:text-slate-800"}
                  `}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {step && (
                <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${active ? "bg-white/20 text-white" : "bg-slate-200 text-slate-600"}`}>
                  {step}
                </span>
              )}
                  {label}
                </Link>
              );
            })}
          </nav>

          <button
            type="button"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-teal-500 md:hidden"
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-nav"
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            onClick={() => setMobileMenuOpen((o) => !o)}
          >
            {mobileMenuOpen ? (
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>

        {/* Mobile nav */}
        <div
          id="mobile-nav"
          className={`overflow-hidden transition-all duration-200 md:hidden ${mobileMenuOpen ? "max-h-64 opacity-100" : "max-h-0 opacity-0"}`}
          aria-hidden={!mobileMenuOpen}
        >
          <nav className="flex flex-col gap-1 border-t border-slate-100 py-3" aria-label="Main navigation">
            {visibleNavItems.map(({ to, label, step }) => {
              const active = isActive(to);
              return (
                <Link
                  key={to}
                  to={to}
                  className={`flex items-center gap-2 rounded-lg px-4 py-3 text-sm font-medium ${active ? "bg-teal-600 text-white" : "text-slate-600 hover:bg-slate-50"}`}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {step && (
                    <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${active ? "bg-white/20 text-white" : "bg-slate-200 text-slate-600"}`}>
                      {step}
                    </span>
                  )}
                  {label}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>
    </header>
  );
}
