import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import { calls, mockApi, plan, session, text } from "./fixtures";
import { advisoriesNotAdded, nextStepAdvisories, nextStepVerify } from "./ottoFixtures";
import { ONE_LOGIN_LINE, OVERVIEW_BLOCKS, acmeRoutes, assessmentView, closedAssessment, emptyAssessment, emptyWorkspace, openAssessment } from "./shellFixtures";

type Routes = Parameters<typeof mockApi>[0];

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "#/a/101/overview");
});

const routes = (extra: Record<string, unknown> = {}): Routes =>
  ({ "GET /api/session": { body: session }, ...acmeRoutes, "POST /api/import/7/plan": { body: { ...plan, has_results: true } }, ...extra }) as Routes;

const group = (key: string) => screen.getAllByTestId("overview-group").find((g) => g.getAttribute("data-group") === key)!;

async function show(extra: Record<string, unknown> = {}) {
  const fetchMock = mockApi(routes(extra));
  render(<App />);
  await screen.findByTestId("overview-page");
  return fetchMock;
}

describe("Overview blocks", () => {
  it("shows the four work groups in order, each with its counts and facts as links to its own page", async () => {
    await show();
    expect(screen.getAllByTestId("overview-group").map((g) => g.getAttribute("data-group"))).toEqual([
      "verification",
      "encryption",
      "migration",
      "dependencies",
    ]);
    expect(text(group("verification"))).toContain("Checks: Open 0 · In progress 0 · Done 12");
    expect(within(group("verification")).getAllByTestId("overview-fact").map((a) => [text(a), a.getAttribute("href")])).toEqual([
      ["True 7", "#/a/101/inventory/verify?group=verification"],
      ["False 3", "#/a/101/inventory/verify?group=verification"],
      ["Couldn't check 2", "#/a/101/inventory/verify?group=verification"],
    ]);
    // Verification has no fixes of its own, so it shows no fixes count.
    expect(text(group("verification"))).not.toContain("Fixes:");
    const fixes = within(group("encryption")).getByRole("link", { name: /^Fixes:/ });
    expect(text(fixes)).toBe("Fixes: Open 1 · In progress 1 · Done 0");
    expect(fixes.getAttribute("href")).toBe("#/a/101/fixes?group=encryption");
    expect(within(group("encryption")).getByRole("link", { name: /^Checks:/ }).getAttribute("href")).toBe("#/a/101/checks?group=encryption");
    // An empty group stays and says why.
    expect(text(group("migration"))).toContain("Nothing measured yet. Measure status is on Migration.");
    expect(text(group("dependencies"))).toContain("No dependency list yet. Add one on Dependencies.");
  });

  it("takes every number from assessment.blocks and nowhere else", async () => {
    // The workspace's row for this project and the 5a counts say something different; the page must not use them.
    const blocks = {
      ...OVERVIEW_BLOCKS,
      groups: OVERVIEW_BLOCKS.groups.map((g) => (g.key === "verification" ? { ...g, facts: g.facts.map((f, i) => ({ ...f, value: [30, 9, 2][i]! })) } : g)),
      findings: OVERVIEW_BLOCKS.findings.map((f) => ({ ...f, value: f.label === "False claims" ? 9 : f.value })),
      evidence: { runs: 41, last_download: null },
    };
    await show({ "GET /api/assessments/101": { body: assessmentView({ blocks }) } });
    expect(within(group("verification")).getAllByTestId("overview-fact").map((a) => text(a))).toEqual(["True 30", "False 9", "Couldn't check 2"]);
    expect(within(screen.getByTestId("open-findings")).getAllByTestId("finding-count").map((a) => text(a))).toEqual([
      "False claims 9",
      "Failed tests 2",
      "Dependency blockers 0",
    ]);
    expect(text(screen.getByTestId("overview-evidence"))).toContain("41 runs recorded");
  });

  it("shows no group and no number that has not happened when no file is in yet", async () => {
    window.history.replaceState(null, "", "#/a/111/overview");
    mockApi({
      "GET /api/session": { body: session },
      "GET /api/workspace": { body: { ...emptyWorkspace } },
      "GET /api/assessments/111": { body: emptyAssessment },
      "GET /api/projects/11": { body: { id: 11, name: "Ledger", folder_id: null, archived: false, is_demo: false, path: [], assessments: [], next_name: "Assessment 2" } },
    });
    render(<App />);
    await screen.findByTestId("overview-page");
    expect(screen.queryAllByTestId("overview-group")).toHaveLength(0);
    expect(screen.queryByTestId("open-findings")).toBeNull();
    expect(text(screen.getByTestId("brought-in"))).toContain("Nothing yet.");
    expect(text(screen.getByTestId("brought-in")).match(/\d/)).toBeNull();
  });

  it("uses no score, grade or verdict words", async () => {
    await show();
    expect(text(screen.getByTestId("overview-page"))).not.toMatch(/\bscore|\bgrade|secure|time to hack/i);
  });

  it("says what was brought in and when, labelled as demo data, with the purpose beside the status", async () => {
    await show();
    const header = screen.getByTestId("page-header");
    expect(text(header)).toContain("acme-pay-cbom.json");
    expect(text(header)).toContain("Demo data");
    expect(text(screen.getByTestId("assessment-purpose"))).toBe("Full review");
    const brought = screen.getByRole("region", { name: "Brought in" });
    expect(text(brought)).toContain("acme-pay-cbom.json");
    expect(text(brought)).toContain("Dependency list: none yet");
  });

  it("shows the open findings and the evidence, each a link to the page that holds them", async () => {
    await show({
      "GET /api/assessments/101": {
        body: assessmentView({ blocks: { ...OVERVIEW_BLOCKS, evidence: { runs: 6, last_download: { at: "2026-11-12T10:00:00Z", fingerprint: "ab12cd34ef567890" } } } }),
      },
    });
    const findings = within(screen.getByTestId("open-findings")).getAllByTestId("finding-count");
    expect(findings.map((a) => a.getAttribute("href"))).toEqual([
      "#/a/101/inventory/verify?group=verification",
      "#/a/101/evidence?group=encryption",
      "#/a/101/migration/dependencies?group=dependencies",
    ]);
    const evidence = screen.getByTestId("overview-evidence");
    expect(text(evidence)).toContain("6 runs recorded");
    expect(text(evidence)).toContain("fingerprint ab12cd34ef56");
    expect(within(evidence).getByRole("link", { name: "6 runs recorded" }).getAttribute("href")).toBe("#/a/101/evidence");
  });
});

describe("Overview next step", () => {
  it("shows the next step and its button goes to that page", async () => {
    await show();
    const next = screen.getByTestId("next-step");
    expect(text(next)).toContain("Run the suggested tests");
    fireEvent.click(within(next).getByRole("button", { name: "Open checks" }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/101/checks"));
  });

  it("goes to Import when the next step is the import", async () => {
    window.history.replaceState(null, "", "#/a/101/overview");
    await show({ "GET /api/assessments/101": { body: assessmentView({ next_step: { page: "inventory/import", label: "Import a file", text: "Bring in a scanner file." } }) } });
    fireEvent.click(within(screen.getByTestId("next-step")).getByRole("button", { name: "Import a file" }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/101/inventory/import"));
  });

  it("goes to Advisories when checks of an installed test pack are ready to add (phase 5c), and adds nothing by itself", async () => {
    const fetchMock = await show({
      "GET /api/assessments/101": { body: assessmentView({ next_step: nextStepAdvisories }) },
      "GET /api/plans/1/advisories": { body: advisoriesNotAdded },
    });
    const next = screen.getByTestId("next-step");
    expect(text(next)).toContain(nextStepAdvisories.text);
    fireEvent.click(within(next).getByRole("button", { name: nextStepAdvisories.label }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/101/advisories"));
    // The Advisories page opens with its button waiting: the next step only opened the page.
    await screen.findByTestId("advisories-standing");
    expect(screen.getByRole("heading", { level: 1, name: advisoriesNotAdded.title })).not.toBeNull();
    expect((screen.getByTestId("add-new-checks") as HTMLButtonElement).disabled).toBe(false);
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("shows the next step exactly as the backend sends it (the sample taken before the claims were verified)", async () => {
    await show({ "GET /api/assessments/101": { body: assessmentView({ next_step: nextStepVerify }) } });
    const next = screen.getByTestId("next-step");
    expect(text(next)).toContain(nextStepVerify.text);
    fireEvent.click(within(next).getByRole("button", { name: nextStepVerify.label }));
    await waitFor(() => expect(window.location.hash).toBe(`#/a/101/${nextStepVerify.page}`));
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
    const box = await screen.findByTestId("new-assessment-box");
    fireEvent.click(within(box).getByRole("button", { name: "Start" }));
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
    fireEvent.click(within(bar).getByRole("button", { name: /Next: Checks/ }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/101/checks"));
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
    // The box: a name filled in ("Assessment 3"), a purpose and an optional reference. It closes nothing.
    const box = within(await screen.findByTestId("new-assessment-box"));
    expect((box.getByLabelText("Name") as HTMLInputElement).value).toBe("Assessment 3");
    expect((box.getByLabelText("Purpose") as HTMLSelectElement).value).toBe("full_review");
    expect(Array.from((box.getByLabelText("Purpose") as HTMLSelectElement).options).map((o) => o.textContent)).toEqual([
      "Full review",
      "Compliance review",
      "Migration wave",
      "Release check",
      "Advisory response",
      "Other",
    ]);
    fireEvent.change(box.getByLabelText("Purpose"), { target: { value: "release_check" } });
    fireEvent.change(box.getByLabelText("Reference (optional)"), { target: { value: "Release 2.1" } });
    fireEvent.click(box.getByRole("button", { name: "Start" }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/102/overview"));
    const call = fetchMock.mock.calls.find(([u, i]) => String(u) === "/api/projects/10/assessments" && i?.method === "POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ name: "Assessment 3", purpose: "release_check", reference: "Release 2.1" });
    // Nothing else was closed or changed.
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual(["POST /api/projects/10/assessments"]);
    expect(await screen.findByRole("heading", { level: 1, name: "Assessment 3" })).not.toBeNull();
  });

  it("Cancel in the New assessment box starts nothing", async () => {
    const fetchMock = await show();
    fireEvent.click(within(screen.getByTestId("page-header")).getByRole("button", { name: "New assessment" }));
    fireEvent.click(within(await screen.findByTestId("new-assessment-box")).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByTestId("new-assessment-box")).toBeNull();
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("Rerun as new assessment opens the same box, filled in, and brings the same file in again on Import", async () => {
    const fetchMock = await show({
      "POST /api/assessments/101/rerun": { body: { id: 102 } },
      "GET /api/assessments/102": { body: assessmentView({ id: 102, number: 3, title: "Assessment 2 (again)", import: null, plan_id: null }) },
    });
    fireEvent.click(within(screen.getByTestId("page-header")).getByRole("button", { name: "Rerun as new assessment" }));
    const box = within(await screen.findByTestId("new-assessment-box"));
    expect(box.getByRole("heading", { name: "Rerun as new assessment" })).not.toBeNull();
    expect((box.getByLabelText("Name") as HTMLInputElement).value).toBe("Assessment 2 (again)");
    expect(text(screen.getByTestId("new-assessment-box"))).toContain("the file only, no results or choices");
    fireEvent.click(box.getByRole("button", { name: "Start" }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/102/inventory/import"));
    const call = fetchMock.mock.calls.find(([u, i]) => String(u) === "/api/assessments/101/rerun" && i?.method === "POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ name: "Assessment 2 (again)", purpose: "full_review", reference: "" });
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
    // Closing is a sign-off: the box needs a name before it can close, and says it can't be undone.
    const box = within(await screen.findByTestId("close-box"));
    expect(text(screen.getByTestId("close-box"))).toContain("It can't be reopened.");
    expect(text(screen.getByTestId("close-box"))).toContain(ONE_LOGIN_LINE);
    const sign = box.getByRole("button", { name: "Close and sign off" }) as HTMLButtonElement;
    expect(sign.disabled).toBe(true);
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
    fireEvent.change(box.getByLabelText("Signed off by"), { target: { value: "Dana Lee" } });
    fireEvent.change(box.getByLabelText("Note (optional)"), { target: { value: "Wave 1 done" } });
    fireEvent.click(sign);
    expect(await screen.findByTestId("closed-banner")).not.toBeNull();
    const call = fetchMock.mock.calls.find(([u, i]) => String(u) === "/api/assessments/101" && i?.method === "POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ close: true, signed_off_by: "Dana Lee", note: "Wave 1 done" });
    expect(screen.queryByRole("button", { name: "Close assessment" })).toBeNull();
  });

  it("shows no Close assessment button once it is closed", async () => {
    window.history.replaceState(null, "", "#/a/100/overview");
    mockApi(routes({ "GET /api/assessments/100": { body: closedAssessment } }));
    render(<App />);
    await screen.findByTestId("overview-page");
    expect(screen.queryByRole("button", { name: "Close assessment" })).toBeNull();
  });

  it("offers Rename, Change purpose, Move and Archive in the more-actions menu", async () => {
    const fetchMock = await show({ "POST /api/assessments/101": { body: openAssessment } });
    fireEvent.click(screen.getByRole("button", { name: "More actions for this assessment" }));
    expect(screen.getAllByRole("menuitem").map((m) => text(m))).toEqual(["Rename", "Change purpose", "Move to another project", "Archive"]);
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

describe("Overview and the project", () => {
  it("has no history table of its own: one link opens the Project overview, where every assessment is", async () => {
    await show();
    expect(screen.queryByRole("table", { name: "Assessments in this project" })).toBeNull();
    const link = screen.getByTestId("to-project-overview");
    expect(text(link)).toBe("Project overview");
    expect(link.getAttribute("href")).toBe("#/p/10");
  });

  it("shows who signed a closed assessment off, and when", async () => {
    window.history.replaceState(null, "", "#/a/100/overview");
    const signed = { ...closedAssessment, status: { ...closedAssessment.status, signoff: { by: "Dana Lee", at: "2026-11-11T09:00:00Z", note: null } } };
    mockApi(routes({ "GET /api/assessments/100": { body: signed } }));
    render(<App />);
    await screen.findByTestId("overview-page");
    expect(text(screen.getByTestId("signoff-line"))).toMatch(/^· Signed off by Dana Lee, /);
  });
});

describe("Overview stays current", () => {
  it("asks for the assessment again each time it opens, so it shows what the pages say now", async () => {
    let asked = 0;
    const later = {
      ...OVERVIEW_BLOCKS,
      findings: OVERVIEW_BLOCKS.findings.map((f) => (f.label === "Failed tests" ? { ...f, value: 4 } : f)),
    };
    await show({
      "GET /api/assessments/101": () => {
        asked += 1;
        return { body: assessmentView({ blocks: asked > 2 ? later : OVERVIEW_BLOCKS }) };
      },
      "GET /api/plans/1/checks": { body: { plan_id: 1, title: "Checks", subline: "", groups: [], busy: false, came_from_options: [], libraries: [], evidence_counts: {} } },
      "POST /api/import/7/plan": { body: { ...plan, has_results: true } },
    });
    const failed = () => within(screen.getByTestId("open-findings")).getAllByTestId("finding-count")[1]!;
    await waitFor(() => expect(text(failed())).toBe("Failed tests 2"));
    fireEvent.click(within(screen.getByRole("navigation", { name: "Assessment" })).getByRole("link", { name: "Checks" }));
    await screen.findByRole("heading", { level: 1, name: "Checks" });
    fireEvent.click(within(screen.getByRole("navigation", { name: "Assessment" })).getByRole("link", { name: "Overview" }));
    await waitFor(() => expect(text(failed())).toBe("Failed tests 4"));
  });
});
