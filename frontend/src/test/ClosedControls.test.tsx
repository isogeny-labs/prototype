// Phase 5a, from the independent review: in a closed assessment the controls that change something without being a
// button are off too, with the closed sentence: the "I own this system" tick on Import and a system's settings in Migration.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ImportScreen } from "../components/ImportScreen";
import { MigrationScreen } from "../components/MigrationScreen";
import { CLOSED_SENTENCE, ReadOnlyProvider } from "../readOnly";
import { demoImport, mockApi, session } from "./fixtures";
import { migrationView } from "./migrationFixtures";

function renderImport(readOnly: boolean) {
  render(
    <ReadOnlyProvider readOnly={readOnly}>
      <ImportScreen
        demoServer={session.demo_server}
        imp={demoImport}
        onImported={vi.fn()}
        onImportFailed={vi.fn()}
        onAddressChanged={vi.fn()}
        onVerified={vi.fn()}
      />
    </ReadOnlyProvider>,
  );
}

async function renderMigration(readOnly: boolean) {
  mockApi({ "GET /api/import/7/migration": { body: migrationView } });
  render(
    <ReadOnlyProvider readOnly={readOnly}>
      <MigrationScreen importId={7} onViewFix={vi.fn()} onPlanChanged={vi.fn()} />
    </ReadOnlyProvider>,
  );
  await screen.findByRole("heading", { level: 1, name: migrationView.title });
}

describe("a closed assessment's controls that are not buttons", () => {
  it("turns the address tick off with the closed sentence, and leaves it on in an open assessment", () => {
    renderImport(true);
    const tick = screen.getByTestId("address-confirm") as HTMLInputElement;
    expect(tick.disabled).toBe(true);
    expect(tick.getAttribute("title")).toBe(CLOSED_SENTENCE);
  });

  it("leaves the address tick on in an open assessment", () => {
    renderImport(false);
    const tick = screen.getByTestId("address-confirm") as HTMLInputElement;
    expect(tick.disabled).toBe(false);
    expect(tick.getAttribute("title")).toBeNull();
  });

  it("turns every setting of the open system off with the closed sentence", async () => {
    await renderMigration(true);
    const settings = screen.getAllByTestId("migration-setting");
    expect(settings.length).toBeGreaterThan(0);
    for (const s of settings) {
      const select = within(s).getByRole("combobox") as HTMLSelectElement;
      expect(select.disabled).toBe(true);
      expect(select.getAttribute("title")).toBe(CLOSED_SENTENCE);
    }
  });

  it("leaves the settings as they were in an open assessment", async () => {
    await renderMigration(false);
    for (const s of screen.getAllByTestId("migration-setting")) {
      expect(within(s).getByRole("combobox").getAttribute("title")).toBeNull();
    }
  });
});
