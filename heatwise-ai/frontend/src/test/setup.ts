import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom has no layout: Recharts' ResponsiveContainer needs a ResizeObserver to exist.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", ResizeObserverStub);
// jsdom does not implement scrolling; the router calls it on navigation.
window.scrollTo = () => {};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
