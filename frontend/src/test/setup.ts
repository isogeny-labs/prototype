import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// findBy* and waitFor wait for the real condition on screen; they finish as soon as it holds. On a busy machine (the
// whole suite runs in parallel) the default 1 second can run out before a screen has drawn, so allow up to 5 seconds.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.sessionStorage.clear();
});
