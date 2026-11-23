import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import App from "../App";
import { calls, mockApi, session, text } from "./fixtures";
import { demoLoaded, demoWorkspace, emptyAssessment, emptyWorkspace, workspace } from "./shellFixtures";

type Routes = Parameters<typeof mockApi>[0];

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "#/projects");
});

const base = (ws = workspace): Routes => ({
  "GET /api/session": { body: session },
  "GET /api/workspace": { body: ws },
});
const rows = () => screen.queryAllByTestId("project-row");
const rowOf = (name: string) => rows().find((r) => within(r).queryByText(name))!;

describe("Projects page table", () => {
  it("has one row per project that is not archived, and none of the archived ones", async () => {
    mockApi(base());
    render(<App />);
    await screen.findByTestId("projects-page");
    expect(screen.getByRole("heading", { level: 1, name: "Projects" })).not.toBeNull();
    expect(rows().map((r) => text(within(r).getAllByRole("cell")[0]))).toEqual([
      expect.stringContaining("Acme Pay"),
      expect.stringContaining("Ledger"),
    ]);
    expect(screen.queryByText("Legacy")).toBeNull();
    expect(screen.queryByText("Retired")).toBeNull();
  });

  it("shows each project's folder path and its latest assessment with status and file", async () => {
    mockApi(base());
    render(<App />);
    await screen.findByTestId("projects-page");
    const acme = text(rowOf("Acme Pay"));
    expect(acme).toContain("Payments / EU");
    expect(acme).toContain("Assessment 2");
    expect(acme).toContain("Open");
    expect(acme).toContain("acme-pay-cbom.json");
    expect(acme).toContain("Demo data");
    expect(text(rowOf("Ledger"))).toContain("Top level");
    expect(text(rowOf("Ledger"))).toContain("No file yet");
  });

  it("shows counts only where they were measured, and Not yet everywhere else", async () => {
    mockApi(base());
    render(<App />);
    await screen.findByTestId("projects-page");
    const acme = text(rowOf("Acme Pay"));
    expect(acme).toContain("12 checked");
    expect(acme).toContain("3 false");
    expect(acme).toContain("2 failed");
    expect(acme).toContain("of 5 run");
    expect(acme).toContain("2 open");
    expect(acme).toContain("3 Classical");
    expect(acme).toContain("2 Hybrid");
    expect(acme).toContain("1 Couldn't check");
    expect(acme).not.toContain("Post-quantum only");
    expect(acme).not.toContain("Not yet");
    // Each project says how many of its assessments are open and closed; the counts are those of the one worked on last.
    expect(acme).toContain("1 open · 1 closed");
    const ledger = text(rowOf("Ledger"));
    expect(ledger).toContain("1 open · 0 closed");
    expect(ledger.match(/Not yet/g)).toHaveLength(4);
    expect(ledger.replace("1 open · 0 closed", "")).not.toMatch(/\d+ (checked|failed|open)/);
  });

  it("uses no score, grade or verdict words", async () => {
    mockApi(base());
    render(<App />);
    await screen.findByTestId("projects-page");
    const page = text(screen.getByTestId("projects-page"));
    expect(page).not.toMatch(/\bscore|\bgrade|secure|\brisk level|time to hack/i);
  });

  it("searches by name and opens the project's overview from a row", async () => {
    mockApi(base());
    render(<App />);
    await screen.findByTestId("projects-page");
    fireEvent.change(within(screen.getByTestId("projects-page")).getByRole("searchbox", { name: "Search projects" }), {
      target: { value: "ledg" },
    });
    expect(rows()).toHaveLength(1);
    fireEvent.click(rows()[0]!);
    await waitFor(() => expect(window.location.hash).toBe("#/p/11"));
  });

  it("opens a row with the keyboard", async () => {
    mockApi(base());
    render(<App />);
    await screen.findByTestId("projects-page");
    fireEvent.keyDown(rowOf("Acme Pay"), { key: "Enter" });
    await waitFor(() => expect(window.location.hash).toBe("#/p/10"));
  });
});

describe("archived projects", () => {
  it("Show archived reveals archived projects, marked, with Unarchive", async () => {
    let archived = true;
    const fetchMock = mockApi({
      ...base(),
      "GET /api/workspace": () => ({
        body: { ...workspace, projects: workspace.projects.map((p) => (p.id === 12 ? { ...p, archived } : p)) },
      }),
      "POST /api/projects/12": () => {
        archived = false;
        return { body: { id: 12 } };
      },
    });
    render(<App />);
    await screen.findByTestId("projects-page");
    expect(rows()).toHaveLength(2);
    fireEvent.click(screen.getByLabelText("Show archived"));
    expect(rows()).toHaveLength(4);
    expect(text(rowOf("Legacy"))).toContain("Archived");

    fireEvent.click(within(rowOf("Legacy")).getByRole("button", { name: "Actions for Legacy" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Unarchive" }));
    await waitFor(() => expect(text(rowOf("Legacy"))).not.toContain("Archived"));
    const call = fetchMock.mock.calls.find(([u]) => String(u) === "/api/projects/12");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ archived: false });
  });

  it("offers Archive on a normal project and sends it", async () => {
    const fetchMock = mockApi({ ...base(), "POST /api/projects/11": { body: { id: 11 } } });
    render(<App />);
    await screen.findByTestId("projects-page");
    fireEvent.click(within(rowOf("Ledger")).getByRole("button", { name: "Actions for Ledger" }));
    expect(screen.getByRole("menuitem", { name: "Rename" })).not.toBeNull();
    expect(screen.getByRole("menuitem", { name: "Move to folder" })).not.toBeNull();
    fireEvent.click(screen.getByRole("menuitem", { name: "Archive" }));
    await waitFor(() => expect(calls(fetchMock)).toContain("POST /api/projects/11"));
  });
});

describe("empty state", () => {
  it("explains what a project and an assessment are, and offers New project and Load demo projects", async () => {
    mockApi(base(emptyWorkspace));
    render(<App />);
    const empty = await screen.findByTestId("empty-state");
    const words = text(empty);
    expect(words).toMatch(/project/i);
    expect(words).toMatch(/assessment/i);
    expect(within(empty).getByRole("button", { name: "New project" })).not.toBeNull();
    expect(within(empty).getByRole("button", { name: "Load demo projects" })).not.toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("Load demo projects calls the API, and the table then shows the projects", async () => {
    let loaded = false;
    const fetchMock = mockApi({
      ...base(),
      "GET /api/workspace": () => ({ body: loaded ? demoWorkspace : emptyWorkspace }),
      "POST /api/demo-projects": () => {
        loaded = true;
        return { body: demoLoaded };
      },
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Load demo projects" }));
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(calls(fetchMock)).toContain("POST /api/demo-projects");
    expect(screen.queryByTestId("empty-state")).toBeNull();
    expect(text(rowOf("Acme Pay"))).toContain("Demo");
    expect(text(rowOf("Migration demo"))).toContain("Demo");
  });

  it("says so when Load demo projects fails", async () => {
    mockApi({
      ...base(emptyWorkspace),
      "POST /api/demo-projects": {
        status: 500,
        body: { error: { message: "The demo files could not be read.", line: null, field: null } },
      },
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Load demo projects" }));
    expect(text(await screen.findByRole("alert"))).toContain("The demo files could not be read.");
    expect(screen.getByRole("button", { name: "Load demo projects" })).not.toBeNull();
  });
});

describe("New project", () => {
  it("creates the project and opens its new assessment on Inventory, Import", async () => {
    const fetchMock = mockApi({
      ...base(),
      "POST /api/projects": { body: { id: 30, assessment_id: 301 } },
      "GET /api/assessments/301": { body: { ...emptyAssessment, id: 301, title: "Assessment 1" } },
      "GET /api/projects/11": {
        body: { id: 11, name: "Ledger", folder_id: null, archived: false, is_demo: false, path: [], assessments: [] },
      },
    });
    render(<App />);
    await screen.findByTestId("projects-page");
    fireEvent.click(screen.getByRole("button", { name: "New project" }));
    const form = screen.getByRole("form", { name: "New project" });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Payments gateway" } });
    fireEvent.click(within(form).getByRole("button", { name: "Create project" }));

    await waitFor(() => expect(window.location.hash).toBe("#/a/301/inventory/import"));
    const call = fetchMock.mock.calls.find(([u, i]) => String(u) === "/api/projects" && i?.method === "POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ name: "Payments gateway", folder_id: null });
    expect(await screen.findByRole("heading", { name: "Import" })).not.toBeNull();
  });

  it("can be cancelled without calling the server", async () => {
    const fetchMock = mockApi(base());
    render(<App />);
    await screen.findByTestId("projects-page");
    fireEvent.click(screen.getByRole("button", { name: "New project" }));
    fireEvent.click(within(screen.getByRole("form", { name: "New project" })).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form", { name: "New project" })).toBeNull();
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("keeps the form and shows the reason when the server refuses the name", async () => {
    mockApi({
      ...base(),
      "POST /api/projects": {
        status: 409,
        body: { error: { message: "A project with this name already exists here.", line: null, field: null } },
      },
    });
    render(<App />);
    await screen.findByTestId("projects-page");
    fireEvent.click(screen.getByRole("button", { name: "New project" }));
    const form = screen.getByRole("form", { name: "New project" });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Ledger" } });
    fireEvent.click(within(form).getByRole("button", { name: "Create project" }));
    expect(text(await within(form).findByRole("alert"))).toContain("already exists");
    expect(window.location.hash).toBe("#/projects");
  });
});
