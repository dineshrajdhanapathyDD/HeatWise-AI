import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";

// findBy*/waitFor default to 1 s. On a low-memory machine running ten jsdom files in parallel, a route change
// can take longer, so failing tests named a different navigation each run. Assertions are unchanged.
configure({ asyncUtilTimeout: 5000 });
import { afterEach, vi } from "vitest";

// jsdom has no layout: Recharts' ResponsiveContainer needs a ResizeObserver to exist.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", ResizeObserverStub);
// jsdom has no IntersectionObserver either (framer-motion whileInView, AnimatedNumber). This stub never
// reports an intersection, so entrance animations stay idle and counters expose only their final value.
class IntersectionObserverStub {
  readonly root = null;
  readonly rootMargin = "";
  readonly thresholds: number[] = [];
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}
vi.stubGlobal("IntersectionObserver", IntersectionObserverStub);
// jsdom does not implement scrolling; the router calls it on navigation.
window.scrollTo = () => {};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
