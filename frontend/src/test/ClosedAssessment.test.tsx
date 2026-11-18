import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import { calls, lab, mockApi, plan, session, text } from "./fixtures";
import { acmeRoutes, assessmentView, closedAssessment } from "./shellFixtures";

// The one sentence that is the requirement.
const CLOSED = "This assessment is closed. Start a new one to continue.";

type Routes = Parameters<typeof mockApi>[0];

beforeEach(() => {
  window.localStorage.clear();
});

function routes(extra: Record<string, unknown> = {}): Routes {
  return {
    "GET /api/session": { body: session },
    ...acmeRoutes,
    "GET /api/assessments/100": { body: closedAssessment },
    "GET /api/plans/1/lab": { body: lab },
    "POST /api/import/7/plan": { body: { ...plan, has_results: true } },
    ...extra,
  } as Routes;
}

async function openClosed(page: string, extra: Record<string, unknown> = {}) {
  window.history.replaceState(null, "", `#/a/100/${page}`);
  const fetchMock = mockApi(routes(extra));
  render(<App />);
  await screen.findByTestId("closed-banner");
  return fetchMock;
}

const button = (name: string | RegExp) => screen.getByRole("button", { name }) as HTMLButtonElement;
const main = () => within(screen.getByRole("main"));

describe("closed assessment banner", () => {
  it("says the assessment is closed and what to do", async () => {
    await openClosed("overview");
    const banner = screen.getByTestId("closed-banner");
    expect(banner.getAttribute("role")).toBe("status");
    expect(text(banner)).toContain(CLOSED);
  });

  it.each(["overview", "inventory/import", "tests", "evidence"])("is shown on the %s page", async (page) => {
    await openClosed(page);
    expect(text(screen.getByTestId("closed-banner"))).toContain(CLOSED);
  });

  it("is not shown for an open assessment, and its buttons work", async () => {
    window.history.replaceState(null, "", "#/a/101/tests");
    mockApi(routes());
    render(<App />);
    await screen.findByRole("button", { name: "Run all" });
    expect(screen.queryByTestId("closed-banner")).toBeNull();
    expect(button("Run all").disabled).toBe(false);
    expect(button("Run all").getAttribute("title")).toBeNull();
  });

  it("its New assessment button stays on, starts a new assessment and opens it on Import", async () => {
    const fetchMock = await openClosed("overview", {
      "POST /api/projects/10/assessments": { body: { id: 102 } },
      "GET /api/assessments/102": { body: assessmentView({ id: 102, number: 3, title: "Assessment 3", file: null, import: null, plan_id: null }) },
    });
    const banner = within(screen.getByTestId("closed-banner"));
    const fresh = banner.getByRole("button", { name: "New assessment" }) as HTMLButtonElement;
    expect(fresh.disabled).toBe(false);
    fireEvent.click(fresh);
    // The New assessment box opens (its buttons stay on too); Start makes the new one and opens it on Import.
    const box = within(await screen.findByTestId("new-assessment-box"));
    // The name the box suggests comes with the project's data, in a request of its own, so it is waited for.
    await waitFor(() => expect((box.getByLabelText("Name") as HTMLInputElement).value).toBe("Assessment 3"));
    fireEvent.click(box.getByRole("button", { name: "Start" }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/102/inventory/import"));
    expect(calls(fetchMock)).toContain("POST /api/projects/10/assessments");
  });
});

describe("closed assessment is read-only", () => {
  it("turns off the action buttons on Import and gives the closed sentence as their reason", async () => {
    await openClosed("inventory/import");
    for (const name of ["Use demo file", "Verify claims"]) {
      expect(button(name).disabled, name).toBe(true);
      expect(button(name).getAttribute("title"), name).toBe(CLOSED);
    }
  });

  it("turns off Run all and Add test on Checks", async () => {
    await openClosed("checks");
    await screen.findByRole("button", { name: "Run all" });
    for (const name of ["Run all", "+ Add test"]) {
      expect(button(name).disabled, name).toBe(true);
      expect(button(name).getAttribute("title"), name).toBe(CLOSED);
    }
  });

  it("turns off Retest on Evidence but keeps the evidence download on", async () => {
    await openClosed("evidence");
    await screen.findByRole("button", { name: "Download evidence" });
    expect(button("Retest new version").disabled).toBe(true);
    expect(button("Retest new version").getAttribute("title")).toBe(CLOSED);
    expect(button("Download evidence").disabled).toBe(false);
    expect(button("Download evidence").getAttribute("title")).toBeNull();
  });

  it("keeps New assessment on in the page header of the Overview", async () => {
    await openClosed("overview");
    const header = within(screen.getByTestId("page-header"));
    expect((header.getByRole("button", { name: "New assessment" }) as HTMLButtonElement).disabled).toBe(false);
    expect(header.getByRole("button", { name: "New assessment" }).getAttribute("title")).toBeNull();
  });

  it("keeps the navigation on: every open page can still be looked at", async () => {
    await openClosed("overview");
    const nav = within(screen.getByRole("navigation", { name: "Assessment" }));
    for (const name of ["Overview", "Import", "Checks", "Evidence"]) {
      expect(nav.getByRole("link", { name }).getAttribute("aria-disabled"), name).toBeNull();
    }
    fireEvent.click(nav.getByRole("link", { name: "Checks" }));
    await waitFor(() => expect(window.location.hash).toBe("#/a/100/checks"));
    expect(main().queryByText(CLOSED)).not.toBeNull();
  });

  it("does not call the server when a turned-off button is clicked", async () => {
    const fetchMock = await openClosed("inventory/import");
    const before = calls(fetchMock).length;
    fireEvent.click(button("Use demo file"));
    fireEvent.click(button("Verify claims"));
    expect(calls(fetchMock).slice(before).filter((c) => c.startsWith("POST"))).toEqual([]);
  });
});
