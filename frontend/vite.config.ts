import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    // The 5c fixes: every time on screen is written in the viewer's own time zone. The tests are one viewer, in New
    // York, so a time they read is the same on every machine (and visibly not UTC).
    env: { TZ: "America/New_York" },
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // A test waits for real conditions on screen (up to 5 s each, see setup.ts); on a busy machine a test that waits for
    // a few of them needs more than the default 5 s in all.
    testTimeout: 30_000,
  },
});
