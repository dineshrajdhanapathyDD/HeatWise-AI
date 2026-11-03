import { motion } from "framer-motion";
import { ChartNoAxesColumn, ClipboardPlus, History, House } from "lucide-react";
import { type RefObject, useEffect, useRef } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { Badges } from "./Badges";
import { Mark } from "./Mark";

const NAV = [
  { to: "/", label: "Home", icon: House, end: true },
  { to: "/assess", label: "New assessment", icon: ClipboardPlus, end: false },
  { to: "/history", label: "History", icon: History, end: false },
  { to: "/impact", label: "Impact", icon: ChartNoAxesColumn, end: false },
] as const;

const REPORT_TABS: Record<string, string> = {
  climate: "Climate",
  risk: "Risk",
  plan: "Plan",
  activity: "Agent activity",
};

function routeTitle(rawPath: string): string {
  // Amplify Hosting redirects deep links to a trailing slash ("/history/"); treat both forms alike.
  const pathname = rawPath.length > 1 ? rawPath.replace(/\/+$/, "") : rawPath;
  if (pathname === "/") return "Home";
  if (pathname === "/assess") return "New assessment";
  if (pathname === "/history") return "History";
  if (pathname === "/impact") return "Impact";
  if (/^\/assessments\/[^/]+\/?$/.test(pathname)) return "Assessment in progress";
  const report = /^\/reports\/[^/]+(?:\/([^/]+))?\/?$/.exec(pathname);
  if (report) return report[1] && REPORT_TABS[report[1]] ? `${REPORT_TABS[report[1]]} - Report` : "Report";
  return "Page not found";
}

function reportOf(pathname: string): string | null {
  return /^\/reports\/([^/]+)/.exec(pathname)?.[1] ?? null;
}

/** Report tabs share one key, so switching tabs does not replay the page entrance. */
function pageKey(pathname: string): string {
  const report = reportOf(pathname);
  return report ? `report:${report}` : pathname;
}

/**
 * Gives each screen its own document title and, after a client-side navigation, moves focus to main
 * so screen-reader users hear the page change. Switching tabs inside one report keeps focus on the tab nav.
 */
function useRouteAnnouncement(main: RefObject<HTMLElement | null>) {
  const { pathname } = useLocation();
  const previous = useRef<string | null>(null);
  useEffect(() => {
    document.title = `${routeTitle(pathname)} - HeatWise AI`;
    const prev = previous.current;
    previous.current = pathname;
    if (prev === null || prev === pathname) return;
    const report = reportOf(pathname);
    if (report !== null && report === reportOf(prev)) return;
    main.current?.focus();
  }, [pathname, main]);
}

/**
 * Shell: an atmospheric fixed background, a 248px sidebar on large screens, and on smaller screens a top bar
 * with a fixed bottom tab bar. The single "Main" navigation element is restyled per breakpoint.
 */
export function AppShell() {
  const main = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  useRouteAnnouncement(main);

  return (
    <div className="relative min-h-dvh lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <div aria-hidden="true" className="hw-atmosphere" />
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to main content
      </a>

      <header className="relative z-20 flex items-center gap-3 border-b border-line bg-ground/95 px-4 py-3 sm:px-6 lg:sticky lg:top-0 lg:h-dvh lg:flex-col lg:items-stretch lg:border-b-0 lg:border-r lg:bg-surface/40 lg:px-4 lg:py-6">
        <Link to="/" className="flex items-center gap-2.5 rounded-control px-2 py-1">
          <span className="grid h-9 w-9 place-items-center rounded-control bg-raised ring-1 ring-line">
            <Mark size={22} />
          </span>
          <span>
            <span className="block text-section font-semibold leading-5">HeatWise AI</span>
            <span className="block text-small text-muted">Heat-risk intelligence</span>
          </span>
        </Link>

        <nav
          aria-label="Main"
          className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 px-2 pb-[max(8px,env(safe-area-inset-bottom))] pt-2 lg:static lg:mt-8 lg:border-0 lg:bg-transparent lg:p-0"
        >
          <ul className="grid grid-cols-4 gap-1 lg:flex lg:flex-col">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `relative flex flex-col items-center gap-1 rounded-control px-2 py-1.5 text-small font-medium transition-colors lg:h-10 lg:flex-row lg:gap-3 lg:px-3 lg:text-body ${
                      isActive ? "text-ink" : "text-muted hover:text-ink"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <motion.span
                          layoutId="nav-active"
                          aria-hidden="true"
                          className="absolute inset-0 rounded-control bg-active ring-1 ring-line"
                          transition={{ type: "spring", stiffness: 420, damping: 34 }}
                        />
                      )}
                      <Icon
                        size={18}
                        strokeWidth={1.75}
                        aria-hidden="true"
                        className={`relative ${isActive ? "text-amber" : ""}`}
                      />
                      <span className="relative whitespace-nowrap">{label}</span>
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="ml-auto lg:ml-0 lg:mt-auto lg:px-2">
          <p className="mb-2 hidden text-small text-muted lg:block">Data and agents</p>
          <Badges />
        </div>
      </header>

      <div className="relative z-10 flex min-w-0 flex-col pb-24 lg:pb-0">
        <main ref={main} id="main" tabIndex={-1} className="flex-1 focus:outline-none">
          <motion.div
            key={pageKey(pathname)}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            className="mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6 lg:px-10 lg:py-9"
          >
            <Outlet />
          </motion.div>
        </main>
        <footer className="mx-auto w-full max-w-[1320px] px-4 pb-8 text-small text-muted sm:px-6 lg:px-10">
          HeatWise AI is an informational tool. It is not medical advice, not an emergency service and not a
          substitute for official warnings.
        </footer>
      </div>
    </div>
  );
}
