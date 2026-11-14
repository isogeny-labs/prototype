import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "../App";
import { CODE_FIX, TLS_FIX, fixesViews } from "./fixesFixtures";
import { address, beforeAfter, calls, demoImport, lab, mockApi, notFound, plan, run, session, text } from "./fixtures";

describe("first run and login", () => {
  it("shows the create-password screen the first time", async () => {
    mockApi({ "GET /api/session": { body: { ...session, setup_required: true, logged_in: false } } });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Create your password" })).not.toBeNull();
    expect(screen.getByText("Isogeny Labs")).not.toBeNull();
    expect(screen.getByLabelText("Password")).not.toBeNull();
    expect(screen.getByLabelText("Repeat password")).not.toBeNull();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Create password"]);
  });

  it("gives friendly validation and does not call the server for a bad password", async () => {
    const fetchMock = mockApi({ "GET /api/session": { body: { ...session, setup_required: true, logged_in: false } } });
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Password"), { target: { value: "short" } });
    fireEvent.change(screen.getByLabelText("Repeat password"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: "Create password" }));
    expect(text(screen.getByRole("alert"))).toContain("at least 8 characters");
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "long-enough-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create password" }));
    expect(text(screen.getByRole("alert"))).toContain("don't match");
    expect(calls(fetchMock)).toEqual(["GET /api/session"]);
  });

  it("creates the password and opens the app", async () => {
    let created = false;
    const fetchMock = mockApi({
      "GET /api/session": () => ({ body: { ...session, setup_required: !created, logged_in: created } }),
      "POST /api/setup": () => {
        created = true;
        return { body: { ok: true } };
      },
      "GET /api/import/current": notFound,
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Password"), { target: { value: "test-password-1" } });
    fireEvent.change(screen.getByLabelText("Repeat password"), { target: { value: "test-password-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create password" }));
    expect(await screen.findByRole("heading", { name: "Import" })).not.toBeNull();
    const setupCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/setup");
    expect(JSON.parse(String(setupCall?.[1]?.body))).toEqual({ password: "test-password-1" });
  });

  it("shows the normal login screen on later visits and reports a wrong password", async () => {
    mockApi({
      "GET /api/session": { body: { ...session, logged_in: false } },
      "POST /api/login": { status: 401, body: { error: { message: "Wrong password", line: null, field: null } } },
    });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Log in" })).not.toBeNull();
    expect(screen.queryByText("Create your password")).toBeNull();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Log in"]);
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "not-the-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(text(await screen.findByRole("alert"))).toContain("That password isn't right");
  });
});

describe("app shell", () => {
  it("shows the wordmark, step bar, demo-mode line and co-pilot panel", async () => {
    mockApi({ "GET /api/session": { body: session }, "GET /api/import/current": notFound });
    render(<App />);
    await screen.findByRole("heading", { name: "Import" });
    expect(screen.getByText("Isogeny Labs")).not.toBeNull();
    expect(screen.getByText("Demo mode: running our own demo software, not isolated.")).not.toBeNull();

    const steps = within(screen.getByRole("navigation", { name: "Steps" }));
    expect(steps.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "1. Import",
      "2. Verify",
      "3. Tests",
      "4. Evidence Lab",
      "5. Fixes",
    ]);
    expect(steps.getByRole("button", { name: /Import/ }).getAttribute("aria-current")).toBe("step");
    expect((steps.getByRole("button", { name: /Verify/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((steps.getByRole("button", { name: "3. Tests" }) as HTMLButtonElement).disabled).toBe(true);
    expect((steps.getByRole("button", { name: "4. Evidence Lab" }) as HTMLButtonElement).disabled).toBe(true);
    expect((steps.getByRole("button", { name: "5. Fixes" }) as HTMLButtonElement).disabled).toBe(true);
    expect(document.body.textContent).not.toMatch(/Coming in phase 2/);
  });

  it("takes the mode line from the backend", async () => {
    const line = "Isolated mode: our demo software runs in a locked-down container with no network.";
    mockApi({
      "GET /api/session": { body: { ...session, mode: "isolated", mode_line: line } },
      "GET /api/import/current": notFound,
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Import" });
    expect(screen.getByTestId("mode-line").textContent).toBe(line);
    expect(screen.queryByText(/Demo mode/)).toBeNull();
  });

  it("has a collapsible co-pilot panel with the exact title, an empty state and no input", async () => {
    mockApi({ "GET /api/session": { body: session }, "GET /api/import/current": notFound });
    render(<App />);
    const panel = await screen.findByTestId("copilot-panel");
    expect(within(panel).getByRole("heading", { name: "Prototype assistant (no AI model connected)" })).not.toBeNull();
    expect(within(panel).getByText(/The assistant isn't built yet/)).not.toBeNull();
    expect(within(panel).queryByRole("textbox")).toBeNull();

    const toggle = screen.getByTestId("copilot-toggle");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(within(panel).queryByText(/The assistant isn't built yet/)).toBeNull();
    fireEvent.click(toggle);
    expect(within(panel).getByText(/The assistant isn't built yet/)).not.toBeNull();
  });

  it("never uses the word 'secure' as a verdict or shows a score", async () => {
    mockApi({
      "GET /api/session": { body: session },
      "GET /api/import/current": { body: demoImport },
      "GET /api/import/7/verify": { body: run },
      "GET /api/import/7/plan": notFound,
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    const text = document.body.textContent ?? "";
    const withoutDisclaimer = text.replace("Passing these tests doesn't prove a system secure.", "");
    expect(withoutDisclaimer).not.toMatch(/secure|score|safe/i);
  });
});

describe("full flow", () => {
  it("imports the demo file, ticks the address, verifies and continues to the five suggested tests", async () => {
    const fetchMock = mockApi({
      "GET /api/session": { body: session },
      "GET /api/import/current": notFound,
      "POST /api/import/demo": { body: demoImport },
      "POST /api/import/7/confirm-address": { body: { ...address, confirmed: true } },
      "POST /api/import/7/verify": { body: run },
      "POST /api/import/7/plan": { body: plan },
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Use demo file" }));
    expect(await screen.findAllByTestId("claim-row")).toHaveLength(3);

    const steps = within(screen.getByRole("navigation", { name: "Steps" }));
    const tests = steps.getByRole("button", { name: "3. Tests" }) as HTMLButtonElement;
    const labStep = steps.getByRole("button", { name: "4. Evidence Lab" }) as HTMLButtonElement;
    const fixesStep = steps.getByRole("button", { name: "5. Fixes" }) as HTMLButtonElement;
    // Tests opens once there is an import; Evidence Lab and Fixes wait for results.
    expect(tests.disabled).toBe(false);
    expect(labStep.disabled).toBe(true);
    expect(fixesStep.disabled).toBe(true);

    const verify = screen.getByRole("button", { name: "Verify claims" });
    expect((verify as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/I own this system or am allowed to test it/));
    await waitFor(() => expect((verify as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(verify);

    expect(await screen.findByRole("heading", { name: "Verify" })).not.toBeNull();
    expect(screen.getAllByTestId("result-row")).toHaveLength(3);
    expect(calls(fetchMock)).toEqual([
      "GET /api/session",
      "GET /api/import/current",
      "POST /api/import/demo",
      "POST /api/import/7/confirm-address",
      "POST /api/import/7/verify",
    ]);
    const confirmCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/confirm-address"));
    expect(JSON.parse(String(confirmCall?.[1]?.body))).toEqual({ address: "localhost:8443", confirmed: true });

    fireEvent.click(screen.getByRole("button", { name: "Continue to tests" }));
    expect(screen.getByRole("heading", { name: "Tests" })).not.toBeNull();
    expect(await screen.findAllByTestId("test-card")).toHaveLength(5);
    expect(calls(fetchMock).at(-1)).toBe("POST /api/import/7/plan");

    expect(tests.getAttribute("aria-current")).toBe("step");
    expect(steps.getAllByRole("button").filter((b) => b.getAttribute("aria-current") === "step")).toEqual([tests]);
    expect(labStep.disabled).toBe(true);
    expect(labStep.getAttribute("aria-current")).toBeNull();
    expect(fixesStep.disabled).toBe(true);
    // No "continue" button on Tests: the step bar is the way forward.
    expect(screen.queryByRole("button", { name: /continue/i })).toBeNull();
  });

  it("opens Evidence Lab from the step bar once the plan has results", async () => {
    const withResults = { ...plan, has_results: true };
    mockApi({
      "GET /api/session": { body: session },
      "GET /api/import/current": { body: demoImport },
      "GET /api/import/7/verify": { body: run },
      "GET /api/import/7/plan": { body: withResults },
      "POST /api/import/7/plan": { body: withResults },
      "GET /api/plans/1/lab": { body: lab },
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    const steps = within(screen.getByRole("navigation", { name: "Steps" }));
    const labStep = steps.getByRole("button", { name: "4. Evidence Lab" }) as HTMLButtonElement;
    expect(labStep.disabled).toBe(false);
    fireEvent.click(labStep);
    expect(await screen.findAllByTestId("lab-row")).toHaveLength(5);
    expect(labStep.getAttribute("aria-current")).toBe("step");
    expect(screen.getByTestId("copilot-panel")).not.toBeNull();

    fireEvent.click(steps.getByRole("button", { name: "3. Tests" }));
    expect(await screen.findAllByTestId("test-card")).toHaveLength(5);
  });

  // Everything the Fixes tests below need: a plan with results, its Evidence Lab and its fixes.
  const withFixes = (fixes = fixesViews.ready) => ({
    "GET /api/session": { body: session },
    "GET /api/import/current": { body: demoImport },
    "GET /api/import/7/verify": { body: run },
    "GET /api/import/7/plan": { body: { ...plan, has_results: true } },
    "POST /api/import/7/plan": { body: { ...plan, has_results: true } },
    "GET /api/plans/1/lab": { body: lab },
    "GET /api/plans/1/fixes": { body: fixes },
  });
  const stepButton = (name: string) =>
    within(screen.getByRole("navigation", { name: "Steps" })).getByRole("button", { name }) as HTMLButtonElement;
  const currentSteps = () =>
    within(screen.getByRole("navigation", { name: "Steps" }))
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-current") === "step")
      .map((b) => b.textContent);
  const expandRow = (title: string) => fireEvent.click(screen.getByRole("button", { name: title }));
  const rowOf = (title: string) => screen.getAllByTestId("lab-row").find((r) => within(r).queryByRole("heading", { name: title }))!;
  const viewInFixes = (title: string) => fireEvent.click(within(rowOf(title)).getByRole("button", { name: "View in Fixes" }));

  it("opens Fixes from the step bar whenever Evidence Lab can be opened", async () => {
    const fetchMock = mockApi(withFixes());
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    expect(stepButton("4. Evidence Lab").disabled).toBe(false);
    expect(stepButton("5. Fixes").disabled).toBe(false);
    expect(calls(fetchMock)).not.toContain("GET /api/plans/1/fixes");

    fireEvent.click(stepButton("5. Fixes"));
    const summary = await screen.findByTestId("fix-summary");
    expect(screen.getByRole("heading", { level: 1, name: "Fixes" })).not.toBeNull();
    expect(currentSteps()).toEqual(["5. Fixes"]);
    // With nothing asked for, the first fix in the list is the one shown.
    expect(summary.getAttribute("data-fix-id")).toBe(CODE_FIX);
    expect(screen.getByTestId("copilot-panel")).not.toBeNull();
    expect(screen.getByTestId("mode-line")).not.toBeNull();

    fireEvent.click(stepButton("4. Evidence Lab"));
    expect(await screen.findAllByTestId("lab-row")).toHaveLength(5);
    expect(currentSteps()).toEqual(["4. Evidence Lab"]);
  });

  it("View in Fixes on an Evidence Lab line opens the Fixes step with that fix selected", async () => {
    mockApi(withFixes());
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    fireEvent.click(stepButton("4. Evidence Lab"));
    await screen.findAllByTestId("lab-row");

    // The server finding's line opens the second fix in the list, not the first.
    expandRow("Old TLS versions");
    viewInFixes("Old TLS versions");
    expect((await screen.findByTestId("fix-summary")).getAttribute("data-fix-id")).toBe(TLS_FIX);
    expect(currentSteps()).toEqual(["5. Fixes"]);
    expect(screen.getByRole("heading", { level: 2, name: "Server accepts TLS 1.2" })).not.toBeNull();
    const selected = () =>
      within(screen.getByRole("navigation", { name: /^Open findings with a fix/ }))
        .getAllByRole("button")
        .map((b) => b.getAttribute("aria-current"));
    expect(selected()).toEqual([null, "true"]);

    // And the signing finding's line opens its own fix.
    fireEvent.click(stepButton("4. Evidence Lab"));
    await screen.findAllByTestId("lab-row");
    expandRow("Official test vectors");
    viewInFixes("Official test vectors");
    expect((await screen.findByTestId("fix-summary")).getAttribute("data-fix-id")).toBe(CODE_FIX);
    expect(selected()).toEqual(["true", null]);
  });

  it("keeps the fix that was picked in Fixes while the user looks at another step", async () => {
    mockApi(withFixes());
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    fireEvent.click(stepButton("5. Fixes"));
    await screen.findByTestId("fix-summary");
    fireEvent.click(screen.getByRole("button", { name: /^Server accepts TLS 1\.2/ }));
    expect(screen.getByTestId("fix-summary").getAttribute("data-fix-id")).toBe(TLS_FIX);

    fireEvent.click(stepButton("4. Evidence Lab"));
    await screen.findAllByTestId("lab-row");
    fireEvent.click(stepButton("5. Fixes"));
    expect((await screen.findByTestId("fix-summary")).getAttribute("data-fix-id")).toBe(TLS_FIX);
  });

  it("starts a newly imported file from its first fix, not from the fix picked for the file before", async () => {
    // The file imported next has its own plan and its own fixes. In the demo their ids are the same as the first file's.
    mockApi({
      ...withFixes(),
      "POST /api/import/demo": { body: { ...demoImport, id: 8 } },
      "POST /api/import/8/plan": { body: { ...plan, id: 2, import_id: 8, has_results: true } },
      "GET /api/plans/2/fixes": { body: { ...fixesViews.ready, plan_id: 2 } },
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    fireEvent.click(stepButton("5. Fixes"));
    await screen.findByTestId("fix-summary");
    fireEvent.click(screen.getByRole("button", { name: /^Server accepts TLS 1\.2/ }));
    expect(screen.getByTestId("fix-summary").getAttribute("data-fix-id")).toBe(TLS_FIX);

    fireEvent.click(stepButton("1. Import"));
    fireEvent.click(await screen.findByRole("button", { name: "Use demo file" }));
    // The new file's plan is not known yet, so Fixes is closed until its tests have been opened.
    await waitFor(() => expect(stepButton("5. Fixes").disabled).toBe(true));
    fireEvent.click(stepButton("3. Tests"));
    await screen.findAllByTestId("test-card");
    await waitFor(() => expect(stepButton("5. Fixes").disabled).toBe(false));
    fireEvent.click(stepButton("5. Fixes"));
    expect((await screen.findByTestId("fix-summary")).getAttribute("data-fix-id")).toBe(CODE_FIX);
  });

  it("Retest now calls its route and then opens Evidence Lab, where before and after show", async () => {
    const retest = `POST /api/plans/1/fixes/${CODE_FIX}/retest`;
    let retested = false;
    const fetchMock = mockApi({
      ...withFixes(fixesViews.merged),
      "GET /api/plans/1/lab": () => ({ body: retested ? beforeAfter : lab }),
      [retest]: () => {
        retested = true;
        return { body: beforeAfter };
      },
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    fireEvent.click(stepButton("5. Fixes"));
    await screen.findByTestId("fix-summary");

    fireEvent.click(screen.getByRole("button", { name: "Retest now" }));
    expect(await screen.findByTestId("lab-columns")).not.toBeNull();
    expect(currentSteps()).toEqual(["4. Evidence Lab"]);
    expect(screen.queryByTestId("fix-summary")).toBeNull();
    expect(calls(fetchMock).slice(-3)).toEqual(["GET /api/plans/1/fixes", retest, "GET /api/plans/1/lab"]);
    expect(calls(fetchMock).filter((c) => c === retest)).toHaveLength(1);
  });

  it("stays on Fixes when Retest now is refused", async () => {
    mockApi({
      ...withFixes(fixesViews.merged),
      [`POST /api/plans/1/fixes/${CODE_FIX}/retest`]: {
        status: 409,
        body: { error: { message: "A retest is running. Wait until it has finished.", line: null, field: null } },
      },
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    fireEvent.click(stepButton("5. Fixes"));
    await screen.findByTestId("fix-summary");
    fireEvent.click(screen.getByRole("button", { name: "Retest now" }));
    expect(text(await screen.findByRole("alert"))).toBe("A retest is running. Wait until it has finished.");
    expect(currentSteps()).toEqual(["5. Fixes"]);
  });

  it("comes back to Fixes after a refresh", async () => {
    mockApi(withFixes());
    const first = render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    fireEvent.click(stepButton("5. Fixes"));
    await screen.findByTestId("fix-summary");
    first.unmount();

    render(<App />);
    expect(await screen.findByTestId("fix-summary")).not.toBeNull();
    expect(currentSteps()).toEqual(["5. Fixes"]);
  });

  it("falls back to an earlier step after a refresh when the plan has no results any more", async () => {
    window.sessionStorage.setItem("evidence-lab-step", "fixes");
    mockApi({ ...withFixes(), "GET /api/import/7/plan": { body: plan } });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Verify" })).not.toBeNull();
    expect(stepButton("5. Fixes").disabled).toBe(true);
    expect(screen.queryByTestId("fix-summary")).toBeNull();
  });

  it("comes back to the step that was open after a refresh", async () => {
    const routes = {
      "GET /api/session": { body: session },
      "GET /api/import/current": { body: demoImport },
      "GET /api/import/7/verify": { body: run },
      "GET /api/import/7/plan": { body: { ...plan, has_results: true } },
      "POST /api/import/7/plan": { body: { ...plan, has_results: true } },
      "GET /api/plans/1/lab": { body: lab },
    };
    mockApi(routes);
    const first = render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    fireEvent.click(screen.getByRole("button", { name: "4. Evidence Lab" }));
    await screen.findAllByTestId("lab-row");
    first.unmount();

    render(<App />);
    expect(await screen.findAllByTestId("lab-row")).toHaveLength(5);
  });

  it("offers no upload of software on any step", async () => {
    mockApi({
      "GET /api/session": { body: session },
      "GET /api/import/current": { body: demoImport },
      "GET /api/import/7/verify": { body: run },
      "GET /api/import/7/plan": { body: { ...plan, has_results: true } },
      "POST /api/import/7/plan": { body: { ...plan, has_results: true } },
      "GET /api/plans/1/lab": { body: lab },
      "GET /api/plans/1/fixes": { body: fixesViews.ready },
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    for (const [name, testId] of [["3. Tests", "test-card"], ["4. Evidence Lab", "lab-row"], ["5. Fixes", "fix-summary"]] as const) {
      fireEvent.click(screen.getByRole("button", { name }));
      await screen.findAllByTestId(testId);
      expect(document.querySelector('input[type="file"]')).toBeNull();
      expect(screen.getByRole("main").textContent).not.toMatch(/upload|drop a file|choose a file/i);
    }
  });

  it("clears the previous file's claims and results when an upload fails, leaving only the error", async () => {
    mockApi({
      "GET /api/session": { body: session },
      "GET /api/import/current": { body: { ...demoImport, addresses: [{ ...address, confirmed: true }] } },
      "GET /api/import/7/verify": { body: run },
      "GET /api/import/7/plan": notFound,
      "POST /api/import/file?filename=broken.csv": {
        status: 422,
        body: { error: { message: "The value column is empty.", line: 3, field: "value" } },
      },
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    const steps = within(screen.getByRole("navigation", { name: "Steps" }));
    fireEvent.click(steps.getByRole("button", { name: /Import/ }));
    expect(screen.getAllByTestId("claim-row")).toHaveLength(3);

    fireEvent.change(screen.getByLabelText("Choose a file to import"), { target: { files: [new File(["x"], "broken.csv")] } });
    expect(text(await screen.findByRole("alert"))).toContain("The value column is empty.");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryAllByTestId("claim-row")).toHaveLength(0);
    expect(screen.queryByTestId("address-confirm")).toBeNull();
    expect(screen.queryByRole("button", { name: "Verify claims" })).toBeNull();
    expect((steps.getByRole("button", { name: /Verify/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("keeps the import and the latest results after a refresh", async () => {
    const fetchMock = mockApi({
      "GET /api/session": { body: session },
      "GET /api/import/current": { body: { ...demoImport, addresses: [{ ...address, confirmed: true }] } },
      "GET /api/import/7/verify": { body: run },
      "GET /api/import/7/plan": notFound,
    });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Verify" })).not.toBeNull();
    expect(calls(fetchMock)).toEqual([
      "GET /api/session",
      "GET /api/import/current",
      "GET /api/import/7/verify",
      "GET /api/import/7/plan",
    ]);

    fireEvent.click(within(screen.getByRole("navigation", { name: "Steps" })).getByRole("button", { name: /Import/ }));
    expect(screen.getAllByTestId("claim-row")).toHaveLength(3);
    expect((screen.getByTestId("address-confirm") as HTMLInputElement).checked).toBe(true);
  });

  it("returns to the login screen if the session has ended", async () => {
    mockApi({
      "GET /api/session": { body: session },
      "GET /api/import/current": notFound,
      "POST /api/import/demo": { status: 401, body: { error: { message: "Please log in", line: null, field: null } } },
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Use demo file" }));
    expect(await screen.findByRole("heading", { name: "Log in" })).not.toBeNull();
  });
});
