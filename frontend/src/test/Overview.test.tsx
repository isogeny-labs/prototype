import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import { calls, mockApi, plan, session, text } from "./fixtures";
import { acmeRoutes, assessmentView, closedAssessment, emptyAssessment, openAssessment } from "./shellFixtures";

type Routes = Parameters<typeof mockApi>[0];

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "#/a/101/overview");
});

const routes = (extra: Record<string, unknown> = {}): Routes =>
  ({ "GET /api/session": { body: session }, ...acmeRoutes, "POST /api/import/7/plan": { body: { ...plan, has_results: true } }, ...extra }) as Routes;

const card = (key: string) => screen.getAllByTestId("summary-card").find((c) => c.getAttribute("data-card") === key)!;

async function show(extra: Record<string, unknown> = {}) {
  const fetchMock = mockApi(routes(extra));
  render(<App />);
  await screen.findByTestId("overview-page");
  return fetchMock;
}

describe("Overview counts", () => {
  it("shows the four counts from the assessment, with what each counts", async () => {
    await show();
    expect(text(card("claims"))).toContain("12");
    expect(text(card("claims"))).toContain("3 false");
    expect(text(card("tests"))).toContain("2");
    expect(text(card("tests"))).toContain("of 5 run");
    expect(text(card("fixes"))).toContain("2");
    expect(text(card("fixes"))).toContain("of 4");
    expect(text(card("systems"))).toContain("6");
    expect(text(card("systems"))).toContain("3 classical");
    expect(text(card("systems"))).toContain("2 hybrid");
  });

  it("takes every number from assessment.counts and nowhere else", async () => {
    // The workspace's row for this project says something different; the page must not use it.
    const counts = {
      claims: { checked: 41, false: 9, true: 30, couldnt_check: 2 },
      tests: { run: 17, failed: 6, passed: 11 },
      fixes: { total: 8, open: 7 },
      systems: { total: 5, classical: 1, hybrid: 0, pq_only: 2, couldnt_check: 0, not_measured: 2 },
    };
    await show({ "GET /api/assessments/101": { body: assessmentView({ counts }) } });
    expect(text(card("claims"))).toContain("41");
    expect(text(card("claims"))).toContain("9 false");
    expect(text(card("tests"))).toContain("6");
    expect(text(card("tests"))).toContain("of 17 run");
    expect(text(card("fixes"))).toContain("7");
    expect(text(card("fixes"))).toContain("of 8");
    // Measured systems are the ones that are not "not measured": 5 - 2.
    expect(text(card("systems"))).toContain("3");
    expect(text(card("systems"))).toContain("2 post-quantum only");
  });

  it("shows a dash and says it has not happened, instead of a made-up number, when nothing was measured", async () => {
    window.history.replaceState(null, "", "#/a/111/overview");
    mockApi({
      "GET /api/session": { body: session },
      "GET /api/workspace": { body: { organization: "Acme Security", folders: [], projects: [] } },
      "GET /api/assessments/111": { body: emptyAssessment },
      "GET /api/projects/11": { body: { id: 11, name: "Ledger", folder_id: null, archived: false, is_demo: false, path: [], assessments: [] } },
    });
    render(<App />);
    await screen.findByTestId("overview-page");
    for (const key of ["claims", "tests", "fixes", "systems"]) {
      expect(text(card(key)), key).toContain("—");
      expect(text(card(key)).replace(/—/g, "").match(/\d/), key).toBeNull();
    }
    expect(text(card("claims"))).toMatch(/not verified/i);
  });

  it("uses no score, grade or verdict words", async () => {
    await show();
    expect(text(screen.getByTestId("overview-page"))).not.toMatch(/\bscore|\bgrade|secure|time to hack/i);
  });

  it("says what was imported and when, labelled as demo data", async () => {
    await show();
    const header = screen.getByTestId("page-header");
    expect(text(header)).toContain("acme-pay-cbom.json");
    expect(text(header)).toContain("Demo data");
    const imported = screen.getByRole("region", { name: "What was imported" });
    expect(text(imported)).toContain("acme-pay-cbom.json");
    expect(text(imported)).toContain("3");
  });
});

describe("Overview next step", () => {
  it("shows the next step and its button goes to that page", async () => {
    await show();
    const next = screen.getByTestId("next-step");
    expect(text(next)).toContain("Run the suggested tests");
    fireEvent.click(within(next).getByRole("button", { name: "Go to Tests" }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/101/tests"));
  });

  it("goes to Import when the next step is the import", async () => {
    window.history.replaceState(null, "", "#/a/101/overview");
    await show({ "GET /api/assessments/101": { body: assessmentView({ next_step: { page: "inventory/import", label: "Import a file", text: "Bring in a scanner file." } }) } });
    fireEvent.click(within(screen.getByTestId("next-step")).getByRole("button", { name: "Import a file" }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/101/inventory/import"));
  });

  it("on a closed assessment the next step is a new assessment", async () => {
    window.history.replaceState(null, "", "#/a/100/overview");
    const fetchMock = mockApi(
      routes({
        "GET /api/assessments/100": { body: closedAssessment },
        "POST /api/projects/10/assessments": { body: { id: 102 } },
        "GET /api/assessments/102": { body: assessmentView({ id: 102, number: 3, title: "Assessment 3", file: null, import: null, plan_id: null, counts: { claims: null, tests: null, fixes: null, systems: null } }) },
      }),
    );
    render(<App />);
    await screen.findByTestId("overview-page");
    const button = within(screen.getByTestId("next-step")).getByRole("button", { name: "New assessment" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    fireEvent.click(button);
    await waitFor(() => expect(window.location.hash).toBe("#/a/102/overview"));
    expect(calls(fetchMock)).toContain("POST /api/projects/10/assessments");
  });
});

describe("Overview buttons", () => {
  it("has a Guided demo switch that is off at first, is remembered, and adds Back and Next to the pages", async () => {
    await show();
    const sw = screen.getByRole("switch", { name: /Guided demo/ }) as HTMLInputElement;
    expect(sw.checked).toBe(false);
    expect(screen.queryByTestId("guided-bar")).toBeNull();
    fireEvent.click(sw);
    expect(sw.checked).toBe(true);
    expect(window.localStorage.getItem("evidence-lab-guided")).toBe("on");
    // The Overview itself has no step bar; the pages do.
    expect(screen.queryByTestId("guided-bar")).toBeNull();
    fireEvent.click(within(screen.getByRole("navigation", { name: "Assessment" })).getByRole("link", { name: "Verify" }));
    const bar = await screen.findByTestId("guided-bar");
    expect(within(bar).getByRole("button", { name: /Back: Import/ })).not.toBeNull();
    fireEvent.click(within(bar).getByRole("button", { name: /Next: Tests/ }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/101/tests"));
  });

  it("starts with Guided demo on when it was left on", async () => {
    window.localStorage.setItem("evidence-lab-guided", "on");
    await show();
    expect((screen.getByRole("switch", { name: /Guided demo/ }) as HTMLInputElement).checked).toBe(true);
  });

  it("New assessment starts a fresh pass in this project and opens it", async () => {
    const fetchMock = await show({
      "POST /api/projects/10/assessments": { body: { id: 102 } },
      "GET /api/assessments/102": { body: assessmentView({ id: 102, number: 3, title: "Assessment 3", file: null, import: null, plan_id: null }) },
    });
    fireEvent.click(within(screen.getByTestId("page-header")).getByRole("button", { name: "New assessment" }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/102/overview"));
    expect(calls(fetchMock)).toContain("POST /api/projects/10/assessments");
    expect(await screen.findByRole("heading", { level: 1, name: "Assessment 3" })).not.toBeNull();
  });

  it("Close assessment closes it, and then the page is read-only", async () => {
    let closed = false;
    const fetchMock = await show({
      "GET /api/assessments/101": () => ({ body: closed ? { ...openAssessment, status: closedAssessment.status } : openAssessment }),
      "POST /api/assessments/101": () => {
        closed = true;
        return { body: { ...openAssessment, status: closedAssessment.status } };
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Close assessment" }));
    expect(await screen.findByTestId("closed-banner")).not.toBeNull();
    const call = fetchMock.mock.calls.find(([u, i]) => String(u) === "/api/assessments/101" && i?.method === "POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ close: true });
    expect(screen.queryByRole("button", { name: "Close assessment" })).toBeNull();
  });

  it("shows no Close assessment button once it is closed", async () => {
    window.history.replaceState(null, "", "#/a/100/overview");
    mockApi(routes({ "GET /api/assessments/100": { body: closedAssessment } }));
    render(<App />);
    await screen.findByTestId("overview-page");
    expect(screen.queryByRole("button", { name: "Close assessment" })).toBeNull();
  });

  it("offers Rename, Move and Archive in the more-actions menu", async () => {
    const fetchMock = await show({ "POST /api/assessments/101": { body: openAssessment } });
    fireEvent.click(screen.getByRole("button", { name: "More actions for this assessment" }));
    expect(screen.getAllByRole("menuitem").map((m) => text(m))).toEqual(["Rename", "Move to another project", "Archive"]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename" }));
    const form = screen.getByRole("form", { name: "Rename this assessment" });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Before the fix" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save name" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u, i]) => String(u) === "/api/assessments/101" && i?.method === "POST");
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ name: "Before the fix" });
    });
  });
});

describe("Overview history", () => {
  it("lists the project's assessments with file, status and start time, and marks this one", async () => {
    await show();
    const table = await screen.findByRole("table", { name: "Assessments in this project" });
    const rows = within(table).getAllByTestId("history-row");
    expect(rows).toHaveLength(2);
    expect(text(rows[0]!)).toContain("Assessment 2");
    expect(text(rows[0]!)).toContain("(this one)");
    expect(text(rows[0]!)).toContain("Open");
    expect(text(rows[1]!)).toContain("Assessment 1");
    expect(text(rows[1]!)).toContain("Closed");
    expect(text(rows[1]!)).toContain("acme-pay-cbom.json");
  });

  it("opens an older assessment from its row, and does nothing for the one already open", async () => {
    await show({ "GET /api/assessments/100": { body: closedAssessment } });
    const rows = await screen.findAllByTestId("history-row");
    fireEvent.click(rows[0]!);
    expect(window.location.hash).toBe("#/a/101/overview");
    fireEvent.click(rows[1]!);
    await waitFor(() => expect(window.location.hash).toBe("#/a/100/overview"));
  });
});
