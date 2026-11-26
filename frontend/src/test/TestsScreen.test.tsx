import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { PlanView } from "../api";
import { CLOSED_SENTENCE, ReadOnlyProvider } from "../readOnly";
import { LinkProvider } from "../components/related";
import { TestsScreen } from "../components/TestsScreen";
import { calls, cards, groupedPlan, mockApi, plan, pqCard, runningPlan, text } from "./fixtures";
import { labCopy, live } from "./sourceFixtures";

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
    expect(titles()).toEqual([
      "Old TLS versions",
      "Certificate strength",
      "Official test vectors",
      "Bad signatures",
      "Speed and size",
    ]);
    for (const [i, el] of list.entries()) {
      expect(within(el).getByText(cards[i]!.description)).not.toBeNull();
      expect(within(el).getByText(/^Why it matters: /).textContent).toBe(cards[i]!.why);
      expect(within(el).getByText("Not run yet")).not.toBeNull();
    }
    expect(screen.getByText(plan.intro)).not.toBeNull();
    expect(screen.getByText("Demo data")).not.toBeNull();
    expect(text(screen.getByTestId("plan-subject"))).toBe(
      "Testing: server localhost:8443 and signing component acme-sign 1.4.2 from the file",
    );
  });

  it("an advisory check's card says which advisory it came from, with the way to it (phase 5c)", async () => {
    const advisoryCard = {
      ...cards[3]!,
      id: 21,
      kind: "advisory_cases" as const,
      title: "Advisory check: Missing ECDSA signature range check (CVE-2022-21449)",
      origin: "added" as const,
      advisory: { label: "From advisory CVE-2022-21449", link: { page: "advisories", item: "CVE-2022-21449" } },
    };
    mockApi({ "POST /api/import/7/plan": { body: { ...plan, tests: [...cards, advisoryCard] } } });
    render(
      <LinkProvider assessmentId={101} planId={1}>
        <Harness />
      </LinkProvider>,
    );
    const shown = await shownCards();
    const links = screen.getAllByTestId("card-advisory");
    // only the advisory check carries it, in the backend's words, and it opens that advisory on Advisories
    expect(links).toHaveLength(1);
    expect(shown.at(-1)!.contains(links[0]!)).toBe(true);
    expect(links[0]!.textContent).toBe("From advisory CVE-2022-21449");
    expect(links[0]!.getAttribute("href")).toBe("#/a/101/advisories?item=CVE-2022-21449");
  });

  it("keeps the flat list when the plan is not grouped: no group headings and no Not tested box", async () => {
    open();
    const list = await shownCards();
    expect(screen.queryByTestId("test-group")).toBeNull();
    expect(screen.queryByTestId("not-tested")).toBeNull();
    // One table for the plan's standard tests, each row with its own level-2 title. (The 5c fixes: the plan is two
    // lists; with no advisory check in the plan, the second list says so and has no table.)
    const body = list[0]!.parentElement!;
    expect(body.tagName).toBe("TBODY");
    expect(body.closest("table")!.getAttribute("aria-label")).toBe("Tests: Standard tests");
    expect(body.children).toHaveLength(5);
    expect(screen.getAllByRole("table")).toHaveLength(1);
    expect(list.map((c) => within(c).getByRole("heading").tagName)).toEqual(["H2", "H2", "H2", "H2", "H2"]);
  });

  it("says on each test where it runs, in the flat plan: on your server, or on a copy on this computer", async () => {
    // (26 November 2026: observing and testing are told apart on every row; under a target's own heading the heading
    // says it, and the row does not repeat it)
    const server = { key: "server:localhost:8443", kind: "server" as const, heading: "Server: localhost:8443", note: null };
    const program = {
      key: "software:lib-acme-sign",
      kind: "software" as const,
      heading: "Signing program: acme-sign 1.4.2",
      note: null,
    };
    const where = {
      [server.key]: "On your server, localhost:8443",
      [program.key]: "On a copy of acme-sign 1.4.2, on this computer",
    };
    const told: PlanView = {
      ...plan,
      groups: [server, program].map((g) => ({ ...g, runs_on: where[g.key]! })),
      tests: plan.tests.map((t) => ({
        ...t,
        group: ["tls_versions", "certificate"].includes(t.kind) ? server.key : program.key,
      })),
    };
    open({}, told);
    const cards = await shownCards();
    expect(cards.map((card) => within(card).getByTestId("card-runs-on").textContent)).toEqual(
      told.tests.map((t) => where[t.group!]),
    );
    cleanup();
    // Grouped under target headings, the heading says it: no second line on the card.
    open({}, { ...told, grouped: true });
    for (const card of await shownCards()) expect(within(card).queryByTestId("card-runs-on")).toBeNull();
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
    expect(names.filter((n) => n === "Run all" || !/^(Reorder|Run|Remove) /.test(n ?? ""))).toEqual([
      "Run all",
      "+ Add test",
    ]);
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
      "POST /api/import/7/plan": {
        status: 409,
        body: { error: { message: "Verify the claims first.", line: null, field: null } },
      },
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
    for (const b of screen.getAllByRole("button", { name: /^Run (?!all)/ }))
      expect((b as HTMLButtonElement).disabled).toBe(true);
    expect(button("Remove Old TLS versions").disabled).toBe(false);
    expect(button("Remove Official test vectors").disabled).toBe(true);
    expect(button("Remove Post-quantum readiness").disabled).toBe(true);
  });

  it("shows any result label the backend sends, including the two cautious ones", async () => {
    const done = (
      i: number,
      label: string,
      tone: "warn" | "neutral" | "pass",
      code: "couldnt_run" | "couldnt_trust" | "offered" | "no_slowdown",
    ) => ({ ...cards[i]!, status: "done" as const, status_text: label, result: { code, label, tone } });
    open(
      {},
      {
        ...plan,
        tests: [
          done(0, "Couldn't run (address not confirmed)", "warn", "couldnt_run"),
          done(1, "Couldn't trust this run", "warn", "couldnt_trust"),
          done(2, "Offered", "neutral", "offered"),
          done(3, "No slowdown beyond measured noise", "pass", "no_slowdown"),
        ],
      },
    );
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
      "POST /api/plans/1/run-all": {
        status: 409,
        body: { error: { message: "Tests are already running.", line: null, field: null } },
      },
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
    expect(screen.getByText("Official test vectors moved to position 2 of 5 in Standard tests.")).not.toBeNull();
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
    const fetchMock = open({
      "POST /api/plans/1/tests/14/remove": { body: { ...plan, tests: cards.filter((c) => c.id !== 14) } },
    });
    await shownCards();
    fireEvent.click(button("Remove Bad signatures"));
    await waitFor(() => expect(screen.getAllByTestId("test-card")).toHaveLength(4));
    expect(calls(fetchMock)).toContain("POST /api/plans/1/tests/14/remove");
  });

  it("+ Add test lists the catalog with its note, and clicking an item adds it", async () => {
    const fetchMock = open({
      "POST /api/plans/1/tests": { body: { ...plan, tests: [...cards, pqCard], catalog: [plan.catalog[1]!] } },
    });
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

  it("a read of the plan that was on its way while a test was added does not put the old list back", async () => {
    // Inside Checks the plan is known already and is read again when the page opens. That read can still be on its way
    // when a person adds a test (the reads take turns on the server). It then holds the plan from before the add and
    // lands after the add's own answer: it is asked again (src/api.ts), so the card that was added stays.
    const added = { ...plan, tests: [...cards, pqCard], catalog: [plan.catalog[1]!] };
    let reads = 0;
    const inner = mockApi({
      "GET /api/import/7/plan": () => ({ body: reads++ === 0 ? plan : added }),
      "POST /api/plans/1/tests": { body: added },
    });
    let land: () => void = () => undefined;
    const held = new Promise<void>((resolve) => (land = resolve));
    let first = true;
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const answer = await inner(input, init); // (the answer is made now, from the plan as it is at this moment)
      if (first && String(input) === "/api/import/7/plan") {
        first = false;
        await held; // ... and is on its way until the test lets it land
      }
      return answer;
    });
    function Embedded() {
      const [current, setCurrent] = useState<PlanView | null>(plan);
      return <TestsScreen importId={7} plan={current} onPlan={setCurrent} embedded />;
    }
    render(<Embedded />);
    expect(await shownCards()).toHaveLength(5);

    fireEvent.click(button("+ Add test"));
    fireEvent.click(
      within(screen.getByRole("menu", { name: "Tests you can add" })).getByRole("menuitem", {
        name: /Post-quantum readiness/,
      }),
    );
    await waitFor(() => expect(screen.getAllByTestId("test-card")).toHaveLength(6));

    land();
    await waitFor(() =>
      expect(calls(inner)).toEqual(["GET /api/import/7/plan", "POST /api/plans/1/tests", "GET /api/import/7/plan"]),
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(titles()).toHaveLength(6);
    expect(titles()).toContain("Post-quantum readiness");
  });

  it("closes the add-test list on Escape without adding anything", async () => {
    const fetchMock = open();
    await shownCards();
    fireEvent.click(button("+ Add test"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(calls(fetchMock)).toEqual(["POST /api/import/7/plan"]);
  });

  describe("grouped by target", () => {
    it("draws one heading per group with its note, and each group's cards under it", async () => {
      open({}, groupedPlan);
      await shownCards();
      const groupsShown = screen.getAllByTestId("test-group");
      expect(groupsShown.map((g) => within(g).getByRole("heading", { level: 2 }).textContent)).toEqual([
        "Server: localhost:8444",
        "Server: localhost:8445",
        "Signing program: acme-sign 1.4.2",
      ]);
      expect(screen.getAllByTestId("test-group-note")).toHaveLength(1);
      expect(within(groupsShown[1]!).getByTestId("test-group-note").textContent).toBe(
        "A local test server started for this file (Demo data).",
      );
      expect(groupsShown.map((g) => within(g).getAllByTestId("test-card").length)).toEqual([2, 2, 3]);
      expect(
        within(groupsShown[2]!)
          .getAllByRole("heading", { level: 3 })
          .map((h) => h.textContent),
      ).toEqual(["Official test vectors", "Bad signatures", "Speed and size"]);
    });

    it("shows the Not tested, and why box above the cards, one line per item, calmly", async () => {
      open({}, groupedPlan);
      await shownCards();
      const box = screen.getByTestId("not-tested");
      expect(within(box).getByRole("heading").textContent).toBe("Not tested, and why");
      expect(
        within(box)
          .getAllByRole("listitem")
          .map((li) => li.textContent),
      ).toEqual(groupedPlan.not_tested!.items);
      expect(box.getAttribute("role")).toBeNull();
      expect(box.className).not.toMatch(/amber|red/);
      expect(
        box.compareDocumentPosition(screen.getAllByTestId("test-group")[0]!) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(
        screen.getByTestId("plan-subject").compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });

    it("moves a card with the arrow keys only inside its own group and sends the whole list in the order shown", async () => {
      const fetchMock = open({ "POST /api/plans/1/order": { body: groupedPlan } }, groupedPlan);
      await shownCards();
      const handles = () => screen.getAllByRole("button", { name: /^Reorder / });
      // The first card of the second group can't move up into the first group.
      fireEvent.keyDown(handles()[2]!, { key: "ArrowUp" });
      // The last card of the first group can't move down into the second group.
      fireEvent.keyDown(handles()[1]!, { key: "ArrowDown" });
      expect(calls(fetchMock)).toEqual(["POST /api/import/7/plan"]);
      expect(handles()[2]!.getAttribute("aria-label")).toMatch(/position 1 of 2\./);

      // Inside a group it moves as before.
      fireEvent.keyDown(handles()[6]!, { key: "ArrowUp" });
      await waitFor(() => expect(calls(fetchMock)).toContain("POST /api/plans/1/order"));
      expect(body(fetchMock, "/api/plans/1/order")).toEqual({ order: [21, 22, 31, 32, 41, 43, 42] });
      expect(
        screen.getByText(
          "Speed and size moved to position 2 of 3 in Standard tests under Signing program: acme-sign 1.4.2.",
        ),
      ).not.toBeNull();
    });

    it("doesn't let a card be dropped into another group", async () => {
      const fetchMock = open({ "POST /api/plans/1/order": { body: groupedPlan } }, groupedPlan);
      const list = await shownCards();
      const dataTransfer = { setData: () => {}, effectAllowed: "", dropEffect: "" };
      const handles = screen.getAllByRole("button", { name: /^Reorder / });
      fireEvent.dragStart(handles[4]!, { dataTransfer });
      fireEvent.dragOver(list[0]!, { dataTransfer });
      fireEvent.drop(list[0]!, { dataTransfer });
      fireEvent.dragEnd(handles[4]!, { dataTransfer });
      expect(calls(fetchMock)).toEqual(["POST /api/import/7/plan"]);

      fireEvent.dragStart(handles[3]!, { dataTransfer });
      fireEvent.dragOver(list[2]!, { dataTransfer });
      fireEvent.drop(list[2]!, { dataTransfer });
      await waitFor(() => expect(calls(fetchMock)).toContain("POST /api/plans/1/order"));
      expect(body(fetchMock, "/api/plans/1/order")).toEqual({ order: [21, 22, 32, 31, 41, 42, 43] });
    });
  });
});

// The 5c fixes: the test plan is two lists, Standard tests and Advisory checks. An advisory check is a test a person
// accepted from a proposal; its list is marked From Otto. A card moves only within its own list.
describe("Tests screen, the plan's two lists", () => {
  const advisoryCard = (id: number, title: string) => ({
    ...cards[3]!,
    id,
    kind: "advisory_cases" as const,
    title,
    origin: "added" as const,
    from_otto: "From Otto",
    advisory: { label: "From advisory CVE-2022-21449", link: { page: "advisories", item: "CVE-2022-21449" } },
  });
  // in the plan's own order the two kinds are mixed: 11, A (21), 12, 13, B (22), 14, 15
  const mixed: PlanView = {
    ...plan,
    tests: [
      cards[0]!,
      advisoryCard(21, "Advisory check: A"),
      cards[1]!,
      cards[2]!,
      advisoryCard(22, "Advisory check: B"),
      cards[3]!,
      cards[4]!,
    ],
  };
  const lists = () => screen.getAllByTestId("plan-list");
  const titlesIn = (el: HTMLElement) =>
    within(el)
      .getAllByTestId("test-card")
      .map((c) => within(c).getByRole("heading").textContent);

  it("shows Standard tests and Advisory checks as two lists, each with its count, and marks the second From Otto", async () => {
    open({}, mixed);
    await shownCards();
    expect(lists().map((l) => l.getAttribute("data-list"))).toEqual(["standard", "advisory"]);
    const [standard, advisory] = lists() as [HTMLElement, HTMLElement];
    expect(within(standard).getByRole("heading", { level: 3 }).textContent).toContain("Standard tests");
    expect(within(advisory).getByRole("heading", { level: 3 }).textContent).toContain("Advisory checks");
    expect(within(standard).getByTestId("plan-list-count").textContent).toBe("5");
    expect(within(advisory).getByTestId("plan-list-count").textContent).toBe("2");
    expect(within(standard).queryByTestId("plan-list-from-otto")).toBeNull();
    expect(within(advisory).getByTestId("plan-list-from-otto").textContent).toBe("From Otto");
    // every card is in exactly one list, in the plan's order within that list
    expect(titlesIn(standard)).toEqual([
      "Old TLS versions",
      "Certificate strength",
      "Official test vectors",
      "Bad signatures",
      "Speed and size",
    ]);
    expect(titlesIn(advisory)).toEqual(["Advisory check: A", "Advisory check: B"]);
    expect(screen.getAllByTestId("test-card")).toHaveLength(7);
    expect(screen.getAllByRole("table").map((t) => t.getAttribute("aria-label"))).toEqual([
      "Tests: Standard tests",
      "Tests: Advisory checks",
    ]);
    // a card's place is counted in its own list
    expect(button(/^Reorder Advisory check: B/).getAttribute("aria-label")).toMatch(/position 2 of 2\./);
    expect(button(/^Reorder Speed and size/).getAttribute("aria-label")).toMatch(/position 5 of 5\./);
  });

  it("moves a card with the arrow keys only within its own list, and every other card keeps its place in the plan", async () => {
    const fetchMock = open({ "POST /api/plans/1/order": { body: mixed } }, mixed);
    await shownCards();
    // The first advisory check is second in the plan, but first in its list: it can't move up into the standard tests.
    fireEvent.keyDown(button(/^Reorder Advisory check: A/), { key: "ArrowUp" });
    // The last standard test can't move down into the advisory checks.
    fireEvent.keyDown(button(/^Reorder Speed and size/), { key: "ArrowDown" });
    expect(calls(fetchMock)).toEqual(["POST /api/import/7/plan"]);

    // Within its list it moves: A and B swap the two places advisory checks hold in the plan; no standard test moves.
    fireEvent.keyDown(button(/^Reorder Advisory check: A/), { key: "ArrowDown" });
    await waitFor(() => expect(calls(fetchMock)).toContain("POST /api/plans/1/order"));
    expect(body(fetchMock, "/api/plans/1/order")).toEqual({ order: [11, 22, 12, 13, 21, 14, 15] });
    expect(screen.getByText("Advisory check: A moved to position 2 of 2 in Advisory checks.")).not.toBeNull();
  });

  it("doesn't let a card be dropped into the other list", async () => {
    const fetchMock = open({ "POST /api/plans/1/order": { body: mixed } }, mixed);
    await shownCards();
    const dataTransfer = { setData: () => {}, effectAllowed: "", dropEffect: "" };
    const [standard, advisory] = lists() as [HTMLElement, HTMLElement];
    const standardCards = within(standard).getAllByTestId("test-card");
    const advisoryCards = within(advisory).getAllByTestId("test-card");
    // an advisory check dragged onto a standard test: no drop is offered, and nothing is sent
    fireEvent.dragStart(button(/^Reorder Advisory check: B/), { dataTransfer });
    fireEvent.dragOver(standardCards[0]!, { dataTransfer });
    fireEvent.drop(standardCards[0]!, { dataTransfer });
    fireEvent.dragEnd(button(/^Reorder Advisory check: B/), { dataTransfer });
    // a standard test dragged onto an advisory check: the same
    fireEvent.dragStart(button(/^Reorder Old TLS versions/), { dataTransfer });
    fireEvent.dragOver(advisoryCards[1]!, { dataTransfer });
    fireEvent.drop(advisoryCards[1]!, { dataTransfer });
    fireEvent.dragEnd(button(/^Reorder Old TLS versions/), { dataTransfer });
    expect(calls(fetchMock)).toEqual(["POST /api/import/7/plan"]);

    // inside its own list a drop works, and only that list's places in the plan change
    fireEvent.dragStart(button(/^Reorder Advisory check: B/), { dataTransfer });
    fireEvent.dragOver(advisoryCards[0]!, { dataTransfer });
    fireEvent.drop(advisoryCards[0]!, { dataTransfer });
    await waitFor(() => expect(calls(fetchMock)).toContain("POST /api/plans/1/order"));
    expect(body(fetchMock, "/api/plans/1/order")).toEqual({ order: [11, 22, 12, 13, 21, 14, 15] });
  });

  it("says so when no advisory check is in the plan, with the way to Advisories", async () => {
    mockApi({ "POST /api/import/7/plan": { body: plan } });
    render(
      <LinkProvider assessmentId={101} planId={1}>
        <Harness />
      </LinkProvider>,
    );
    await shownCards();
    const [, advisory] = lists() as [HTMLElement, HTMLElement];
    expect(within(advisory).getByTestId("plan-list-count").textContent).toBe("0");
    expect(within(advisory).queryByRole("table")).toBeNull();
    expect(text(within(advisory).getByTestId("plan-list-empty"))).toBe(
      "No advisory check is in the plan. A proposed check joins it when you accept it on Advisories.",
    );
    expect(within(advisory).getByRole("link", { name: "Advisories" }).getAttribute("href")).toBe("#/a/101/advisories");
  });

  it("under a target heading, a target with no advisory check shows no empty second list", async () => {
    open({}, groupedPlan);
    await shownCards();
    expect(lists().map((l) => l.getAttribute("data-list"))).toEqual(["standard", "standard", "standard"]);
    expect(screen.queryByTestId("plan-list-empty")).toBeNull();
  });
});

describe("Tests screen, closed assessment", () => {
  it("turns off Run, remove, reorder, Run all and the catalog, each with the reason", async () => {
    mockApi({ "POST /api/import/7/plan": { body: plan } });
    render(
      <ReadOnlyProvider readOnly>
        <Harness />
      </ReadOnlyProvider>,
    );
    await shownCards();
    for (const b of [
      ...screen.getAllByRole("button", { name: /^Run / }),
      ...screen.getAllByRole("button", { name: /^Remove / }),
      ...screen.getAllByTestId("drag-handle"),
    ]) {
      expect((b as HTMLButtonElement).disabled).toBe(true);
      expect(b.getAttribute("title")).toBe(CLOSED_SENTENCE);
    }
    expect((screen.getByRole("button", { name: "+ Add test" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

// 22 November 2026: where a finished test's result came from, beside its word on its card: a server test is read live,
// every other test runs a copy here. A test that couldn't run has no tag.
describe("Test plan, where each result came from", () => {
  it("draws one tag beside each finished card's result, and none where it couldn't run", async () => {
    open(
      {},
      {
        ...plan,
        tests: [
          {
            ...cards[0]!,
            status: "done",
            status_text: "Failed",
            result: { code: "failed", label: "Failed", tone: "fail" },
            source_tag: live("localhost:8443"),
          },
          {
            ...cards[2]!,
            status: "done",
            status_text: "Failed",
            result: { code: "failed", label: "Failed", tone: "fail" },
            source_tag: labCopy("acme-sign 1.4.2"),
          },
          {
            ...cards[3]!,
            status: "done",
            status_text: "Couldn't run",
            result: { code: "couldnt_run", label: "Couldn't run", tone: "warn" },
            source_tag: null,
          },
        ],
      },
    );
    await shownCards();
    const shown = screen.getAllByTestId("test-card").map((c) =>
      within(c)
        .queryAllByTestId("source-tag")
        .map((t) => t.textContent),
    );
    expect(shown).toEqual([["Observed live"], ["Proven in the lab"], []]);
    const first = within(screen.getAllByTestId("test-card")[0]!);
    expect(first.getByTestId("result-badge").parentElement!.contains(first.getByTestId("source-tag"))).toBe(true);
  });
});
