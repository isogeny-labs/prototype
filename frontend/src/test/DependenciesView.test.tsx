import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, MAX_DEPENDENCY_LIST_BYTES, type DependenciesView as View } from "../api";
import { DependenciesView } from "../components/dependencies/DependenciesView";
import { MigrationScreen } from "../components/MigrationScreen";
import {
  DEPENDENCIES_DEMO,
  DEPENDENCIES_DIFFERS,
  DEPENDENCIES_EMPTY,
  DEPENDENCIES_ISOLATED,
  DIFFERS_WORDS,
} from "./dependenciesFixtures";
import { mockApi, text } from "./fixtures";
import { migrationView } from "./migrationFixtures";

afterEach(() => vi.restoreAllMocks());

async function open(view: View, props: { onViewFix?: (id: string) => void; onChanged?: () => void } = {}) {
  vi.spyOn(api, "getDependencies").mockResolvedValue(view);
  const onViewFix = props.onViewFix ?? vi.fn();
  const onChanged = props.onChanged ?? vi.fn();
  render(<DependenciesView importId={1} onViewFix={onViewFix} onChanged={onChanged} />);
  await screen.findByTestId("dependencies-subline");
  return { onViewFix, onChanged };
}

const rows = () => screen.getAllByTestId("dependency-row");
const row = (label: string) => rows().find((r) => r.querySelector("p.font-mono")?.textContent === label)!;
/** The answer chips of the table (one per question, with the proof chip). */
const cells = (el: HTMLElement = document.body) => within(el).queryAllByTestId("dependency-answer");
const panel = () => screen.getByTestId("detail-panel");
/** Opens a library's row (unless it is already open) and gives back the detail panel's queries. */
const detail = (label: string) => {
  const r = row(label);
  if (r.getAttribute("aria-selected") !== "true") fireEvent.click(r);
  return within(panel());
};
/** The full answers in the panel: reason, first version, state, agreement. */
const detailCells = (label: string) => detail(label).queryAllByTestId("dependency-cell");
const allRows = (v: View) => v.groups.flatMap((g) => g.rows);
const fixtureRow = (v: View, label: string) => allRows(v).find((r) => r.label === label)!;
const button = (el: HTMLElement, name: string | RegExp) => within(el).getByRole("button", { name }) as HTMLButtonElement;

describe("Dependencies view: empty", () => {
  it("shows the empty text and the add button, with no groups", async () => {
    await open(DEPENDENCIES_EMPTY);
    expect(screen.getByTestId("dependencies-empty").textContent).toBe(DEPENDENCIES_EMPTY.empty_text);
    expect(screen.getByTestId("dependencies-subline").textContent).toBe(DEPENDENCIES_EMPTY.subline);
    expect(screen.getByRole("button", { name: DEPENDENCIES_EMPTY.upload.label })).not.toBeNull();
    expect(screen.getByText(DEPENDENCIES_EMPTY.upload.note)).not.toBeNull();
    expect(screen.queryAllByTestId("dependency-group")).toHaveLength(0);
    expect(screen.queryAllByTestId("dependency-system")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Measure all" })).toBeNull();
  });

  it("shows the legend as sent", async () => {
    await open(DEPENDENCIES_EMPTY);
    const legend = screen.getByRole("list", { name: "What the labels mean" });
    expect(within(legend).getAllByRole("listitem").map((li) => li.textContent)).toEqual(DEPENDENCIES_EMPTY.legend.map((l) => l.words));
  });
});

describe("Dependencies view: answers and labels", () => {
  it("draws every kind of answer with the backend's words", async () => {
    await open(DEPENDENCIES_DEMO);
    const wanted: Record<string, string> = {
      yes: "Yes",
      no: "No",
      doesnt_apply: "Doesn't apply",
      not_in_knowledge_base: "Not in our knowledge base yet",
      couldnt_tell_version: "Couldn't tell the version",
      needs_your_environment: "Needs your environment",
    };
    for (const [answer, words] of Object.entries(wanted)) {
      const found = cells().filter((c) => c.getAttribute("data-answer") === answer);
      expect(found.length, answer).toBeGreaterThan(0);
      for (const c of found) expect(within(c).getByTestId("result-badge").textContent).toContain(words);
    }
    // Three cells per row, one per question, in the order sent.
    for (const r of rows()) {
      expect(cells(r).map((c) => c.getAttribute("data-question"))).toEqual(DEPENDENCIES_DEMO.questions.map((q) => q.key));
    }
  });

  it("labels yes and no cells 'Release notes say' in demo mode, and never 'Measured on a public copy' on a cell", async () => {
    await open(DEPENDENCIES_DEMO);
    const answered = cells().filter((c) => ["yes", "no"].includes(c.getAttribute("data-answer")!));
    expect(answered.length).toBeGreaterThan(0);
    for (const c of answered) expect(c.textContent).toContain("Release notes say");
    for (const c of cells()) expect(c.textContent).not.toContain("Measured on a public copy");
    for (const c of cells()) expect(c.textContent).not.toContain("Measured in your environment");
  });

  it("labels measured cells 'Measured on a public copy' in isolated mode, and never 'Measured in your environment'", async () => {
    await open(DEPENDENCIES_ISOLATED);
    const measured = cells().filter((c) => c.getAttribute("data-state") === "measured");
    expect(measured.length).toBe(
      allRows(DEPENDENCIES_ISOLATED).flatMap((r) => r.cells).filter((c) => c.state === "measured").length,
    );
    expect(measured.length).toBeGreaterThan(0);
    for (const c of measured) expect(c.textContent).toContain("Measured on a public copy");
    for (const c of cells()) expect(c.textContent).not.toContain("Measured in your environment");
    expect(document.body.textContent).not.toContain("Measured in your environment");
  });

  it("shows the first version that can on a No", async () => {
    await open(DEPENDENCIES_DEMO);
    const cell = detailCells("openssl 3.0.22")[0]!;
    expect(cell.getAttribute("data-answer")).toBe("no");
    expect(within(cell).getByTestId("first-version").textContent).toBe("3.5.0 or later can.");
    expect(within(detailCells("openssl 3.5.9")[0]!).queryByTestId("first-version")).toBeNull();
  });

  it("shows the measurement state words as sent", async () => {
    await open(DEPENDENCIES_ISOLATED);
    const measured = detailCells("python-ecdsa 0.13.2")[0]!;
    const fixtureCell = fixtureRow(DEPENDENCIES_ISOLATED, "python-ecdsa 0.13.2").cells[0]!;
    expect(within(measured).getByTestId("measure-state").textContent).toBe(fixtureCell.state_words);
    expect(measured.textContent).toContain(fixtureCell.reason);
  });

  it("shows an agreement note, and marks a disagreement", async () => {
    await open(DEPENDENCIES_DIFFERS);
    // The notes sit in each library's panel: open every row in turn and gather them.
    const notes: HTMLElement[] = [];
    let owner = "";
    let differsQuestion: string | null | undefined;
    for (const r of rows()) {
      fireEvent.click(r);
      for (const n of within(panel()).queryAllByTestId("agreement")) {
        notes.push(n);
        if (n.getAttribute("data-agreement") === "differs") {
          owner = r.querySelector("p.font-mono")?.textContent ?? "";
          differsQuestion = n.closest("[data-testid=dependency-cell]")?.getAttribute("data-question");
        }
      }
    }
    const differs = notes.filter((n) => n.getAttribute("data-agreement") === "differs");
    expect(differs).toHaveLength(1);
    expect(differs[0]!.textContent).toBe(DIFFERS_WORDS);
    const agrees = notes.filter((n) => n.getAttribute("data-agreement") === "agrees");
    expect(agrees.length).toBeGreaterThan(0);
    expect(agrees[0]!.textContent).toBe("The release notes say the same.");
    // The disagreement sits on the one cell that was changed.
    expect(differsQuestion).toBe("ml_kem_768");
    expect(owner).toBe("openssl 3.5.9");
  });

  it("shows no agreement note on a lookup-only cell", async () => {
    await open(DEPENDENCIES_DEMO);
    for (const r of rows()) {
      fireEvent.click(r);
      expect(within(panel()).queryAllByTestId("agreement")).toHaveLength(0);
    }
  });
});

describe("Dependencies view: measure buttons", () => {
  it("demo mode: 'Measure all' is off with its reason, and each row's button is off with its reason", async () => {
    await open(DEPENDENCIES_DEMO);
    const all = screen.getByRole("button", { name: "Measure all" }) as HTMLButtonElement;
    expect(all.disabled).toBe(true);
    expect(screen.getByTestId("measure-all-blocked").textContent).toBe(DEPENDENCIES_DEMO.measure_all!.blocked_reason);
    for (const label of ["openssl 3.0.22", "python-ecdsa 0.13.2", "openjdk 17.0.2", "elliptic 6.5.6", "openssl 3.5.9"]) {
      const r = detail(label);
      expect(r.getByRole("button", { name: "Measure on a public copy" }).hasAttribute("disabled"), label).toBe(true);
      expect(r.getByTestId("row-measure-blocked").textContent, label).toBe("Measuring needs isolated mode (Docker).");
    }
  });

  it("shows 'Not on the approved pinned list.' for a library that is not pinned", async () => {
    await open(DEPENDENCIES_DEMO);
    for (const label of ["wolfssl 5.7.2", "Go standard library 1.23.4", "python 3.12.3"]) {
      const r = detail(label);
      expect(r.getByRole("button", { name: "Measure on a public copy" }).hasAttribute("disabled")).toBe(true);
      expect(r.getByTestId("row-measure-blocked").textContent).toBe("Not on the approved pinned list.");
    }
  });

  it("isolated mode: the buttons are on and a row's button measures that row", async () => {
    const measure = vi.spyOn(api, "measureDependencies").mockResolvedValue(DEPENDENCIES_ISOLATED);
    const { onChanged } = await open(DEPENDENCIES_ISOLATED);
    expect((screen.getByRole("button", { name: "Measure all" }) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByTestId("measure-all-blocked")).toBeNull();
    detail("openssl 3.5.9");
    const b = button(panel(), fixtureRow(DEPENDENCIES_ISOLATED, "openssl 3.5.9").measure.label);
    expect(b.disabled).toBe(false);
    fireEvent.click(b);
    await waitFor(() => expect(measure).toHaveBeenCalledWith(DEPENDENCIES_ISOLATED.plan_id, "row-6"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    // A library that is not pinned stays off even in isolated mode.
    detail("wolfssl 5.7.2");
    expect(button(panel(), "Measure on a public copy").disabled).toBe(true);
  });

  it("isolated mode: 'Measure all' sends no row", async () => {
    const measure = vi.spyOn(api, "measureDependencies").mockResolvedValue(DEPENDENCIES_ISOLATED);
    await open(DEPENDENCIES_ISOLATED);
    fireEvent.click(screen.getByRole("button", { name: "Measure all" }));
    await waitFor(() => expect(measure).toHaveBeenCalledWith(DEPENDENCIES_ISOLATED.plan_id, null));
  });

  it("shows a measuring job and polls until it ends, then tells the app", async () => {
    const busy: View = { ...DEPENDENCIES_ISOLATED, busy: true };
    const get = vi.spyOn(api, "getDependencies").mockResolvedValueOnce(busy).mockResolvedValue(DEPENDENCIES_ISOLATED);
    const onChanged = vi.fn();
    render(<DependenciesView importId={1} onViewFix={vi.fn()} onChanged={onChanged} />);
    await screen.findByTestId("dependencies-subline");
    expect((screen.getByRole("button", { name: DEPENDENCIES_ISOLATED.upload.label }) as HTMLButtonElement).disabled).toBe(true);
    await waitFor(() => expect(onChanged).toHaveBeenCalled(), { timeout: 4000 });
    expect(get.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect((screen.getByRole("button", { name: DEPENDENCIES_ISOLATED.upload.label }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("Dependencies view: Part of", () => {
  it("draws the picker as sent and the tie words", async () => {
    await open(DEPENDENCIES_DEMO);
    const groups = screen.getAllByTestId("dependency-group");
    expect(groups.map((g) => g.getAttribute("aria-label"))).toEqual(DEPENDENCIES_DEMO.groups.map((g) => g.label));
    const select = screen.getByLabelText("Part of: acme-pay-server 1.0.0") as HTMLSelectElement;
    expect(select.value).toBe("server:localhost:8443");
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual(DEPENDENCIES_DEMO.groups[1]!.picker.options.map((o) => o.name));
    expect(within(groups[2]!).getByTestId("tie-words").textContent).toBe(DEPENDENCIES_DEMO.groups[2]!.tie_words);
  });

  it("choosing a system for acme-ledger 5.1.0 sends the group key and the system key", async () => {
    const tie = vi.spyOn(api, "tieDependency").mockResolvedValue(DEPENDENCIES_DEMO);
    await open(DEPENDENCIES_DEMO);
    const select = screen.getByLabelText("Part of: acme-ledger 5.1.0");
    fireEvent.change(select, { target: { value: "server:localhost:8443" } });
    await waitFor(() => expect(tie).toHaveBeenCalledWith(DEPENDENCIES_DEMO.plan_id, "acme-ledger", "server:localhost:8443"));
  });

  it("choosing 'None of these' sends an empty system", async () => {
    const tie = vi.spyOn(api, "tieDependency").mockResolvedValue(DEPENDENCIES_DEMO);
    await open(DEPENDENCIES_DEMO);
    fireEvent.change(screen.getByLabelText("Part of: acme-pay-server 1.0.0"), { target: { value: "" } });
    await waitFor(() => expect(tie).toHaveBeenCalledWith(DEPENDENCIES_DEMO.plan_id, "acme-pay-server", ""));
  });
});

describe("Dependencies view: upload", () => {
  const chooser = () => screen.getByLabelText("Choose a dependency list") as HTMLInputElement;

  it("choosing a file sends it with the plan id, and shows the new view", async () => {
    const add = vi.spyOn(api, "addDependencyList").mockResolvedValue(DEPENDENCIES_DEMO);
    const { onChanged } = await open(DEPENDENCIES_EMPTY);
    const file = new File(['{"bomFormat":"CycloneDX"}'], "deps.cdx.json", { type: "application/json" });
    fireEvent.change(chooser(), { target: { files: [file] } });
    await waitFor(() => expect(add).toHaveBeenCalledWith(DEPENDENCIES_EMPTY.plan_id, file));
    await screen.findAllByTestId("dependency-group");
    expect(screen.getByTestId("dependencies-subline").textContent).toBe(DEPENDENCIES_DEMO.subline);
    expect(onChanged).toHaveBeenCalled();
  });

  it("the add button opens the file chooser", async () => {
    await open(DEPENDENCIES_EMPTY);
    const click = vi.spyOn(chooser(), "click");
    fireEvent.click(screen.getByRole("button", { name: "Add dependency list" }));
    expect(click).toHaveBeenCalled();
  });

  it("refuses a file larger than the limit on screen, without calling the api", async () => {
    const add = vi.spyOn(api, "addDependencyList").mockResolvedValue(DEPENDENCIES_DEMO);
    await open(DEPENDENCIES_EMPTY);
    const big = new File(["x"], "huge.json", { type: "application/json" });
    Object.defineProperty(big, "size", { value: MAX_DEPENDENCY_LIST_BYTES + 1 });
    fireEvent.change(chooser(), { target: { files: [big] } });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("huge.json");
    expect(alert.textContent).toContain("16 MB");
    expect(add).not.toHaveBeenCalled();
  });

  it("accepts a file of exactly the limit", async () => {
    const add = vi.spyOn(api, "addDependencyList").mockResolvedValue(DEPENDENCIES_DEMO);
    await open(DEPENDENCIES_EMPTY);
    const file = new File(["x"], "edge.json");
    Object.defineProperty(file, "size", { value: MAX_DEPENDENCY_LIST_BYTES });
    fireEvent.change(chooser(), { target: { files: [file] } });
    await waitFor(() => expect(add).toHaveBeenCalled());
  });

  it("shows the api's refusal and keeps the earlier list on screen", async () => {
    const message = "Line 3: this is not a CycloneDX or SPDX file.";
    vi.spyOn(api, "addDependencyList").mockRejectedValue(new ApiError(422, message));
    const { onChanged } = await open(DEPENDENCIES_DEMO);
    fireEvent.change(chooser(), { target: { files: [new File(["nope"], "bad.json")] } });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(message);
    expect(screen.getAllByTestId("dependency-group")).toHaveLength(DEPENDENCIES_DEMO.groups.length);
    expect(screen.getByTestId("dependencies-subline").textContent).toBe(DEPENDENCIES_DEMO.subline);
    expect(onChanged).not.toHaveBeenCalled();
  });
});

describe("Dependencies view: systems and blockers", () => {
  it("draws one box per system with its kind, tie, blocker lines and environment line", async () => {
    await open(DEPENDENCIES_DEMO);
    const boxes = screen.getAllByTestId("dependency-system");
    expect(boxes.map((b) => b.getAttribute("data-system"))).toEqual(DEPENDENCIES_DEMO.systems.map((s) => s.key));
    const server = boxes.find((b) => b.getAttribute("data-system") === "server:localhost:8443")!;
    const s = DEPENDENCIES_DEMO.systems.find((x) => x.key === "server:localhost:8443")!;
    expect(server.textContent).toContain(s.kind_label);
    expect(server.textContent).toContain(s.name);
    expect(server.textContent).toContain(`from ${s.tied_from}`);
    expect(within(server).getAllByTestId("blocker-line").map((l) => l.textContent)).toEqual(s.blocker_lines.map((l) => `${l.text} View in Fixes`));
    expect(server.textContent).toContain(s.without_answer_text!);
    expect(server.textContent).toContain(s.environment_line);
  });

  it("a system's blocker line has 'View in Fixes' and sends the fix id; a line with no fix has none", async () => {
    const { onViewFix } = await open(DEPENDENCIES_DEMO);
    const server = screen.getAllByTestId("dependency-system").find((b) => b.getAttribute("data-system") === "server:localhost:8443")!;
    const lines = within(server).getAllByTestId("blocker-line");
    const fixId = DEPENDENCIES_DEMO.systems.find((x) => x.key === "server:localhost:8443")!.blocker_lines[0]!.fix_id!;
    fireEvent.click(within(lines[0]!).getByRole("button", { name: "View in Fixes" }));
    expect(onViewFix).toHaveBeenCalledWith(fixId);
    const signing = screen.getAllByTestId("dependency-system").find((b) => b.getAttribute("data-system") === "software:lib-acme-sign")!;
    expect(within(signing).queryByRole("button", { name: "View in Fixes" })).toBeNull();
  });

  it("a row's block names the track and the system and has 'View in Fixes'", async () => {
    const { onViewFix } = await open(DEPENDENCIES_DEMO);
    const blocks = within(detail("openssl 3.0.22").getByTestId("row-blocks")).getAllByRole("listitem");
    const fixture = fixtureRow(DEPENDENCIES_DEMO, "openssl 3.0.22").blocks;
    expect(blocks.map((b) => text(b))).toEqual(fixture.map((b) => `Blocks the ${b.track_words} track of ${b.system}. View in Fixes`));
    fireEvent.click(within(blocks[1]!).getByRole("button", { name: "View in Fixes" }));
    expect(onViewFix).toHaveBeenCalledWith(fixture[1]!.fix_id);
    expect(detail("openssl 3.5.9").queryByTestId("row-blocks")).toBeNull();
  });
});

describe("Dependencies view: details and evidence", () => {
  it("shows the lookup source, its quote and the label, once for a repeated source", async () => {
    await open(DEPENDENCIES_DEMO);
    const r = detail("openssl 3.0.22");
    const fixture = fixtureRow(DEPENDENCIES_DEMO, "openssl 3.0.22").lookups;
    const shown = r.getAllByTestId("lookup-source");
    expect(shown).toHaveLength(fixture.filter((l) => !l.repeat).length);
    expect(shown[0]!.textContent).toContain(fixture[0]!.title);
    expect(shown[0]!.textContent).toContain(fixture[0]!.quote);
    expect(shown[0]!.textContent).toContain("Release notes say");
    expect(shown[0]!.textContent).toContain(`checked ${fixture[0]!.checked}`);
    expect(r.getByText("Details and evidence")).not.toBeNull();
    // A row with no lookup and no measurement has no details.
    expect(detail("wolfssl 5.7.2").queryByText("Details and evidence")).toBeNull();
  });

  it("an https source is a link", async () => {
    await open(DEPENDENCIES_DEMO);
    const fixture = fixtureRow(DEPENDENCIES_DEMO, "openssl 3.0.22").lookups[0]!;
    if (fixture.url.startsWith("https://")) {
      const link = detail("openssl 3.0.22").getAllByRole("link")[0]!;
      expect(link.getAttribute("href")).toBe(fixture.url);
    }
  });

  it("a measured row shows the copy label, 'Measured on a public copy', the controls words and the result", async () => {
    await open(DEPENDENCIES_ISOLATED);
    const fixture = fixtureRow(DEPENDENCIES_ISOLATED, "openssl 3.0.22");
    const m = detail("openssl 3.0.22").getByTestId("measurement");
    expect(m.textContent).toContain(fixture.measurement!.copy_label);
    expect(m.textContent).toContain("Measured on a public copy");
    expect(m.textContent).toContain(fixture.measurement!.controls_words);
    expect(within(m).getByTestId("result-detail").getAttribute("data-run-id")).toBe(String(fixture.measurement!.result!.run_id));
    // The same-copy note comes from the backend and shows only where sent.
    expect(detail("openssl 3.5.9").getByTestId("measurement").textContent).toContain(fixtureRow(DEPENDENCIES_ISOLATED, "openssl 3.5.9").same_copy_note!);
    expect(detail("python-ecdsa 0.13.2").queryByText(/capable control/)).toBeNull();
  });

  it("an unmeasured row has no measurement section", async () => {
    await open(DEPENDENCIES_DEMO);
    expect(screen.queryAllByTestId("measurement")).toHaveLength(0);
  });
});

describe("Dependencies view: loading and wording", () => {
  it("shows the error when the view can't be loaded", async () => {
    vi.spyOn(api, "getDependencies").mockRejectedValue(new ApiError(500, "The server broke."));
    render(<DependenciesView importId={1} onViewFix={vi.fn()} onChanged={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toContain("The server broke.");
  });

  it.each([
    ["empty", DEPENDENCIES_EMPTY],
    ["demo", DEPENDENCIES_DEMO],
    ["isolated", DEPENDENCIES_ISOLATED],
    ["differs", DEPENDENCIES_DIFFERS],
  ])("never says 'secure' or 'score' (%s)", async (_name, view) => {
    await open(view);
    const shown = screen.getByTestId("dependencies-view").textContent ?? "";
    expect(shown).not.toMatch(/secure/i);
    expect(shown).not.toMatch(/score/i);
  });
});

describe("Migration screen: Dependencies tab", () => {
  it("the third tab shows the Dependencies view", async () => {
    mockApi({
      "GET /api/import/7/migration": { body: migrationView },
      "GET /api/import/7/dependencies": { body: DEPENDENCIES_DEMO },
    });
    render(<MigrationScreen importId={7} onViewFix={vi.fn()} onPlanChanged={vi.fn()} />);
    await screen.findByRole("heading", { level: 1, name: migrationView.title });
    const tab = screen.getByRole("button", { name: migrationView.tabs.dependencies }) as HTMLButtonElement;
    expect(tab.textContent).toBe("Dependencies");
    expect(tab.getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByTestId("dependencies-view")).toBeNull();
    fireEvent.click(tab);
    expect(tab.getAttribute("aria-pressed")).toBe("true");
    expect((await screen.findByTestId("dependencies-subline")).textContent).toBe(DEPENDENCIES_DEMO.subline);
    expect(screen.getAllByTestId("dependency-group")).toHaveLength(DEPENDENCIES_DEMO.groups.length);
    expect(screen.getByRole("button", { name: "Systems · 7" }).getAttribute("aria-pressed")).toBe("false");
  });
});
