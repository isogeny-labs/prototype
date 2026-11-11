import fs from "node:fs";
import os from "node:os";
import path from "node:path";

/** Removes the throwaway data folder (test database and test certificate) made for this run. */
export default function globalTeardown(): void {
  const dir = process.env.E2E_DATA_DIR;
  if (dir && path.dirname(dir) === os.tmpdir() && path.basename(dir).startsWith("evidence-lab-e2e-")) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}
