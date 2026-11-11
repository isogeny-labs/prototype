import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "../App";
import { address, calls, demoImport, mockApi, notFound, run, session, text } from "./fixtures";

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
    expect(steps.getByRole("button", { name: /Import/ }).getAttribute("aria-current")).toBe("step");
    expect((steps.getByRole("button", { name: /Verify/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((steps.getByRole("button", { name: /Tests.*Coming in phase 2/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((steps.getByRole("button", { name: /Evidence Lab.*Coming in phase 2/ }) as HTMLButtonElement).disabled).toBe(true);
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
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Verify" });
    const text = document.body.textContent ?? "";
    const withoutDisclaimer = text.replace("Passing these tests doesn't prove a system secure.", "");
    expect(withoutDisclaimer).not.toMatch(/secure|score|safe/i);
  });
});

describe("full flow", () => {
  it("imports the demo file, ticks the address, verifies and continues to the tests placeholder", async () => {
    const fetchMock = mockApi({
      "GET /api/session": { body: session },
      "GET /api/import/current": notFound,
      "POST /api/import/demo": { body: demoImport },
      "POST /api/import/7/confirm-address": { body: { ...address, confirmed: true } },
      "POST /api/import/7/verify": { body: run },
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Use demo file" }));
    expect(await screen.findAllByTestId("claim-row")).toHaveLength(3);

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
    expect(screen.getByText(/arrives in phase 2/)).not.toBeNull();

    const steps = within(screen.getByRole("navigation", { name: "Steps" }));
    const tests = steps.getByRole("button", { name: /Tests.*Coming in phase 2/ });
    expect(tests.getAttribute("aria-current")).toBe("step");
    expect(steps.getAllByRole("button").filter((b) => b.getAttribute("aria-current") === "step")).toEqual([tests]);
    const lab = steps.getByRole("button", { name: /Evidence Lab.*Coming in phase 2/ }) as HTMLButtonElement;
    expect(lab.disabled).toBe(true);
    expect(lab.getAttribute("aria-current")).toBeNull();
    expect(tests.className).not.toBe(lab.className);
  });

  it("clears the previous file's claims and results when an upload fails, leaving only the error", async () => {
    mockApi({
      "GET /api/session": { body: session },
      "GET /api/import/current": { body: { ...demoImport, addresses: [{ ...address, confirmed: true }] } },
      "GET /api/import/7/verify": { body: run },
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
    });
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Verify" })).not.toBeNull();
    expect(calls(fetchMock)).toEqual(["GET /api/session", "GET /api/import/current", "GET /api/import/7/verify"]);

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
