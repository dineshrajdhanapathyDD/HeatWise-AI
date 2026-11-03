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

function routeTitle(pathname: string): string {
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

/*
 * Open-plane shell (taste-skill sheet, shell redrawn once): a labelled 240px sidebar on the page ground,
 * no top bar; the canvas is a centred 1088px column (report pattern). Below 1024px the sidebar folds into
 * a top bar: mark and badges on one row, the four links on the next.
 */
export function AppShell() {
  const main = useRef<HTMLElement>(null);
  useRouteAnnouncement(main);
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[240px_minmax(0,1fr)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to main content
      </a>
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 sm:px-6 lg:sticky lg:top-0 lg:h-dvh lg:flex-col lg:flex-nowrap lg:items-stretch lg:px-3 lg:py-6">
        <Link to="/" className="order-1 flex items-center gap-2 rounded-control px-2 py-1">
          <Mark />
          <span className="text-section font-medium">HeatWise AI</span>
        </Link>
        <div className="order-2 ml-auto lg:order-3 lg:ml-0 lg:mt-auto lg:px-2">
          <Badges />
        </div>
        <nav aria-label="Main" className="order-3 w-full lg:order-2 lg:mt-4">
          <ul className="flex gap-1 lg:flex-col">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `flex h-9 items-center gap-2 whitespace-nowrap rounded-control px-2 text-body lg:h-8 ${
                      isActive ? "bg-active text-ink" : "text-muted hover:text-ink"
                    }`
                  }
                >
                  <Icon size={16} strokeWidth={1.5} aria-hidden="true" className="hidden sm:block" />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <div className="flex min-w-0 flex-col">
        <main ref={main} id="main" tabIndex={-1} className="flex-1 focus:outline-none">
          <div className="mx-auto w-full max-w-[1088px] px-4 py-6 sm:px-6 lg:px-8 lg:py-9">
            <Outlet />
          </div>
        </main>
        <footer className="mx-auto w-full max-w-[1088px] px-4 pb-8 text-small text-muted sm:px-6 lg:px-8">
          HeatWise AI is an informational tool. It is not medical advice, not an emergency service and not a
          substitute for official warnings.
        </footer>
      </div>
    </div>
  );
}
