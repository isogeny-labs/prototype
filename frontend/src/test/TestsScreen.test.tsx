import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { PlanView } from "../api";
import { TestsScreen } from "../components/TestsScreen";
import { calls, cards, mockApi, plan, pqCard, runningPlan, text } from "./fixtures";

function Harness({ initial = null }: { initial?: PlanView | null }) {
  const [current, setCurrent] = useState<PlanView | null>(initial);
  return <TestsScreen importId={7} plan={current} onPlan={setCurrent} />;
}

type Routes = Parameters<typeof mockApi>[0];

function open(routes: Routes = {}, first: PlanView = plan) {
  const fetchMock = mockApi({ "POST /api/import/7/plan": { body: first }, ...routes });
  render(<Harness />);
  return fetchMock;
}

async function shownCards() {
  await screen.findAllByTestId("test-card");
  return screen.getAllByTestId("test-card");
}

const titles = () => screen.getAllByTestId("test-card").map((c) => within(c).getByRole("heading").textContent);
const body = (fetchMock: ReturnType<typeof mockApi>, path: string) =>
  JSON.parse(String(fetchMock.mock.calls.find(([url]) => String(url) === path)?.[1]?.body));
const button = (name: string | RegExp) => screen.getByRole("button", { name }) as HTMLButtonElement;

describe("Tests screen", () => {
  it("asks for the plan and shows the five suggested cards with their why-it-matters line", async () => {
    const fetchMock = open();
    const list = await shownCards();
    expect(calls(fetchMock)).toEqual(["POST /api/import/7/plan"]);
    expect(list).toHaveLength(5);
    expect(titles()).toEqual(["Old TLS versions", "Certificate strength", "Official test vectors", "Bad signatures", "Speed and size"]);
    for (const [i, el] of list.entries()) {
      expect(within(el).getByText(cards[i]!.description)).not.toBeNull();
      expect(within(el).getByText(/^Why it matters: /).textContent).toBe(cards[i]!.why);
      expect(within(el).getByText("Not run yet")).not.toBeNull();
    }
    expect(screen.getByText(plan.intro)).not.toBeNull();
    expect(screen.getByText("Demo data")).not.toBeNull();
    expect(text(screen.getByTestId("plan-subject"))).toBe("Testing: server localhost:8443 and signing component acme-sign 1.4.2 from the file");
  });

  it("carries the one fixed line about what passing means, and uses the word 'secure' nowhere else", async () => {
    open({}, runningPlan);
    await shownCards();
    expect(screen.getByTestId("disclaimer").textContent).toBe(
      "Passing these tests doesn't prove a system secure. It shows these specific checks passed.",
    );
    expect((document.body.textContent ?? "").match(/secure/gi)).toHaveLength(1);
  });

  it("has only the buttons the spec lists, and no upload control", async () => {
    open();
    await shownCards();
    const names = screen.getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent);
    expect(names.filter((n) => n === "Run all" || !/^(Reorder|Run|Remove) /.test(n ?? ""))).toEqual(["Run all", "+ Add test"]);
    expect(screen.getAllByRole("button", { name: /^Run (?!all)/ })).toHaveLength(5);
    expect(screen.getAllByRole("button", { name: /^Remove / })).toHaveLength(5);
    expect(screen.getAllByRole("button", { name: /^Reorder / })).toHaveLength(5);
    expect(document.querySelector("input, textarea, select, form")).toBeNull();
    expect(document.body.textContent).not.toMatch(/upload|mockup/i);
  });

  it("hides the Demo data label for the user's own file", async () => {
    open({}, { ...plan, is_demo: false });
    await shownCards();
    expect(screen.queryByText("Demo data")).toBeNull();
  });

  it("shows a plain error when the plan can't be loaded", async () => {
    mockApi({
      "POST /api/import/7/plan": { status: 409, body: { error: { message: "Verify the claims first.", line: null, field: null } } },
    });
    render(<Harness />);
    expect(text(await screen.findByRole("alert"))).toContain("Verify the claims first.");
  });

  it("renders every status: result badge, running with and without a bar, waiting, not run", async () => {
    open({ "GET /api/plans/1": { body: runningPlan } }, runningPlan);
    const list = await shownCards();
    expect(list).toHaveLength(6);

    expect(within(list[0]!).getByTestId("result-badge").textContent).toContain("Failed");
    expect(within(list[0]!).getByTestId("result-badge").getAttribute("data-tone")).toBe("fail");

    expect(within(list[1]!).getByText("Running")).not.toBeNull();
    expect(within(list[1]!).getByText("reading the certificate")).not.toBeNull();
    expect(within(list[1]!).queryByRole("progressbar")).toBeNull();

    expect(within(list[2]!).getByText("312 of 484 cases")).not.toBeNull();
    expect(within(list[2]!).getByRole("progressbar").getAttribute("aria-valuenow")).toBe("64");

    expect(within(list[3]!).getByText("Not run yet")).not.toBeNull();
    expect(within(list[5]!).getByText("Waiting")).not.toBeNull();
    expect(within(list[5]!).getByText("4 tests run at once; starts when one finishes")).not.toBeNull();
    expect(within(list[5]!).queryByTestId("result-badge")).toBeNull();
  });

  it("dims Run, Run all and the remove button of busy cards while tests are running", async () => {
    open({ "GET /api/plans/1": { body: runningPlan } }, runningPlan);
    await shownCards();
    expect(button("Run all").disabled).toBe(true);
    for (const b of screen.getAllByRole("button", { name: /^Run (?!all)/ })) expect((b as HTMLButtonElement).disabled).toBe(true);
    expect(button("Remove Old TLS versions").disabled).toBe(false);
    expect(button("Remove Official test vectors").disabled).toBe(true);
    expect(button("Remove Post-quantum readiness").disabled).toBe(true);
  });

  it("shows any result label the backend sends, including the two cautious ones", async () => {
    const done = (i: number, label: string, tone: "warn" | "neutral" | "pass", code: "couldnt_run" | "couldnt_trust" | "offered" | "no_slowdown") =>
      ({ ...cards[i]!, status: "done" as const, status_text: label, result: { code, label, tone } });
    open({}, {
      ...plan,
      tests: [
        done(0, "Couldn't run (address not confirmed)", "warn", "couldnt_run"),
        done(1, "Couldn't trust this run", "warn", "couldnt_trust"),
        done(2, "Offered", "neutral", "offered"),
        done(3, "No slowdown beyond measured noise", "pass", "no_slowdown"),
      ],
    });
    await shownCards();
    const badges = screen.getAllByTestId("result-badge");
    expect(badges.map((b) => b.lastElementChild?.textContent)).toEqual([
      "Couldn't run (address not confirmed)",
      "Couldn't trust this run",
      "Offered",
      "No slowdown beyond measured noise",
    ]);
    expect(badges[0]!.className).toBe(badges[1]!.className);
    expect(badges[0]!.className).not.toBe(badges[3]!.className);
  });

  it("Run on a card and Run all call the API", async () => {
    const fetchMock = open({
      "POST /api/plans/1/tests/12/run": { body: plan },
      "POST /api/plans/1/run-all": { body: plan },
    });
    await shownCards();
    fireEvent.click(button("Run Certificate strength"));
    await waitFor(() => expect(calls(fetchMock)).toContain("POST /api/plans/1/tests/12/run"));
    await waitFor(() => expect(button("Run all").disabled).toBe(false));
    fireEvent.click(button("Run all"));
    await waitFor(() => expect(calls(fetchMock)).toContain("POST /api/plans/1/run-all"));
  });

  it("shows the server's reason when a run is refused", async () => {
    open({
      "POST /api/plans/1/run-all": { status: 409, body: { error: { message: "Tests are already running.", line: null, field: null } } },
    });
    await shownCards();
    fireEvent.click(button("Run all"));
    expect(text(await screen.findByRole("alert"))).toContain("Tests are already running.");
  });

  it("polls every second while running and stops when nothing is running", async () => {
    let polls = 0;
    const finished: PlanView = { ...plan, has_results: true };
    const fetchMock = open({
      "POST /api/plans/1/run-all": { body: runningPlan },
      "GET /api/plans/1": () => {
        polls += 1;
        return { body: polls < 2 ? runningPlan : finished };
      },
    });
    await shownCards();
    fireEvent.click(button("Run all"));
    await screen.findByText("312 of 484 cases");
    await waitFor(() => expect(screen.queryByText("312 of 484 cases")).toBeNull(), { timeout: 4000 });
    expect(polls).toBe(2);
    await new Promise((r) => setTimeout(r, 1300));
    expect(polls).toBe(2);
    expect(calls(fetchMock).filter((c) => c === "GET /api/plans/1")).toHaveLength(2);
  }, 10000);

  it("moves a card with the arrow keys on its handle and sends the new order", async () => {
    const reordered: PlanView = { ...plan, tests: [cards[0]!, cards[2]!, cards[1]!, cards[3]!, cards[4]!] };
    const fetchMock = open({ "POST /api/plans/1/order": { body: reordered } });
    await shownCards();
    const handle = button(/^Reorder Official test vectors/);
    handle.focus();
    fireEvent.keyDown(handle, { key: "ArrowUp" });
    await waitFor(() => expect(calls(fetchMock)).toContain("POST /api/plans/1/order"));
    expect(body(fetchMock, "/api/plans/1/order")).toEqual({ order: [11, 13, 12, 14, 15] });
    expect(titles().slice(0, 3)).toEqual(["Old TLS versions", "Official test vectors", "Certificate strength"]);
    await waitFor(() => expect(document.activeElement).toBe(button(/^Reorder Official test vectors/)));
    expect(screen.getByText("Official test vectors moved to position 2 of 5.")).not.toBeNull();
  });

  it("does nothing when the first card is moved up or the last one down", async () => {
    const fetchMock = open();
    await shownCards();
    fireEvent.keyDown(button(/^Reorder Old TLS versions/), { key: "ArrowUp" });
    fireEvent.keyDown(button(/^Reorder Speed and size/), { key: "ArrowDown" });
    expect(calls(fetchMock)).toEqual(["POST /api/import/7/plan"]);
  });

  it("reorders by dragging a handle onto another card", async () => {
    const fetchMock = open({ "POST /api/plans/1/order": { body: plan } });
    const list = await shownCards();
    const dataTransfer = { setData: () => {}, effectAllowed: "", dropEffect: "" };
    fireEvent.dragStart(button(/^Reorder Speed and size/), { dataTransfer });
    fireEvent.dragOver(list[0]!, { dataTransfer });
    fireEvent.drop(list[0]!, { dataTransfer });
    await waitFor(() => expect(calls(fetchMock)).toContain("POST /api/plans/1/order"));
    expect(body(fetchMock, "/api/plans/1/order")).toEqual({ order: [15, 11, 12, 13, 14] });
    expect(button(/^Reorder Speed and size/).draggable).toBe(true);
  });

  it("removes a test with its × button", async () => {
    const fetchMock = open({ "POST /api/plans/1/tests/14/remove": { body: { ...plan, tests: cards.filter((c) => c.id !== 14) } } });
    await shownCards();
    fireEvent.click(button("Remove Bad signatures"));
    await waitFor(() => expect(screen.getAllByTestId("test-card")).toHaveLength(4));
    expect(calls(fetchMock)).toContain("POST /api/plans/1/tests/14/remove");
  });

  it("+ Add test lists the catalog with its note, and clicking an item adds it", async () => {
    const fetchMock = open({ "POST /api/plans/1/tests": { body: { ...plan, tests: [...cards, pqCard], catalog: [plan.catalog[1]!] } } });
    await shownCards();
    const add = button("+ Add test");
    expect(add.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.click(add);
    expect(add.getAttribute("aria-expanded")).toBe("true");
    const menu = within(screen.getByRole("menu", { name: "Tests you can add" }));
    expect(menu.getAllByRole("menuitem")).toHaveLength(2);
    expect(menu.getByText("reference, not production")).not.toBeNull();
    expect(menu.getByText("Tests you remove from the plan come back to this list.")).not.toBeNull();

    fireEvent.click(menu.getByRole("menuitem", { name: /Post-quantum readiness/ }));
    await waitFor(() => expect(screen.getAllByTestId("test-card")).toHaveLength(6));
    expect(body(fetchMock, "/api/plans/1/tests")).toEqual({ catalog_id: "pq_readiness" });
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("closes the add-test list on Escape without adding anything", async () => {
    const fetchMock = open();
    await shownCards();
    fireEvent.click(button("+ Add test"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(calls(fetchMock)).toEqual(["POST /api/import/7/plan"]);
  });
});
