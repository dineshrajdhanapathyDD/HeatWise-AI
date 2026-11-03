/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
    css: false,
    // Chart-heavy screens render slowly in jsdom on low-memory machines when ten files run in
    // parallel; the first test of a file then exceeds the 5 s default. Assertions are unchanged.
    testTimeout: 20_000,
  },
});
