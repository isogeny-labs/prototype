import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { PlanView } from "../api";
import { ChecksScreen } from "../components/ChecksScreen";
import { LinkProvider } from "../components/related";
import { parseRoute, routeHref } from "../router";
import { checksView, planRows } from "./checksFixtures";
import { lab, mockApi, plan, run, session } from "./fixtures";
import { assessmentView, workspace } from "./shellFixtures";

// Phase 6b: three more filters of a page's table are part of its address, so a command to Otto or a link can open a
// filtered table and Back returns: Result (Checks, Evidence), Came from (Checks) and Decision (Advisories).

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", "#/projects");
});

describe("the address of a filtered table", () => {
  it("names the Result, Came from and Decision filters, and reads back the same", () => {
    const failed = routeHref({ kind: "assessment", id: 12, page: "checks", result: "Failed" });
    expect(failed).toBe("#/a/12/checks?result=Failed");
    expect(parseRoute(failed)).toMatchObject({ kind: "assessment", id: 12, page: "checks", result: "Failed" });
    expect(routeHref(parseRoute(failed))).toBe(failed);
    const retests = routeHref({ kind: "assessment", id: 12, page: "checks", from: "retest", result: "Passed", group: "encryption" });
    expect(parseRoute(retests)).toMatchObject({ from: "retest", result: "Passed", group: "encryption" });
    expect(routeHref(parseRoute(retests))).toBe(retests);
    expect(parseRoute("#/a/3/advisories?decision=proposed")).toMatchObject({ page: "advisories", decision: "proposed" });
    // a value with a space or an apostrophe survives the address
    const odd = routeHref({ kind: "assessment", id: 1, page: "checks", result: "Couldn't check" });
    expect(parseRoute(odd)).toMatchObject({ result: "Couldn't check" });
  });

  it("an address without a filter is exactly what it was before", () => {
    expect(routeHref({ kind: "assessment", id: 12, page: "checks", item: "test-5" })).toBe("#/a/12/checks?item=test-5");
    expect(routeHref({ kind: "assessment", id: 12, page: "checks", result: null, from: null, decision: null })).toBe("#/a/12/checks");
    const plain = parseRoute("#/a/12/checks?item=test-5");
    expect("result" in plain || "from" in plain || "decision" in plain).toBe(false);
  });
});

describe("Checks, filtered from its address", () => {
  // Of the plan's tests, one reads Failed in the list of checks (its row is "test-<id>"), the others Passed.
  const failedId = plan.tests[1]!.id;
  const passed = { label: "Passed", tone: "pass" as const, code: "passed" };
  const view = {
    ...checksView,
    groups: checksView.groups.map((g) =>
      g.key === "encryption"
        ? {
            ...g,
            rows: [
              ...plan.tests.map((t, n) => ({ ...planRows[0]!, id: `test-${t.id}`, name: t.title, ...(t.id === failedId ? {} : { result: passed }), runs: n + 1 })),
              ...g.rows.filter((r) => !r.id.startsWith("test-")),
            ],
          }
        : g,
    ),
  };

  /** Checks with its filters held where the app holds them: in the address. `onFilters` is told of each change; the
   * button stands for Back (or a link) changing the address from outside the page. */
  function Harness({ result = null, from = null, onFilters }: { result?: string | null; from?: string | null; onFilters?: (f: { result?: string | null; from?: string | null }) => void }) {
    const [current, setCurrent] = useState<PlanView | null>(plan);
    const [address, setAddress] = useState<{ result: string | null; from: string | null; group?: string | null }>({ result, from });
    return (
      <LinkProvider assessmentId={101} planId={1}>
        <button type="button" onClick={() => setAddress({ result: null, from: "retest" })}>
          the address changes
        </button>
        {/* (what Otto's "show me failed checks" does: the same page, with the Result filter and no group in the address) */}
        <button type="button" onClick={() => setAddress({ result: "Failed", from: null, group: null })}>
          failed checks are asked for
        </button>
        <ChecksScreen
          importId={7}
          plan={current}
          onPlan={setCurrent}
          group={address.group ?? null}
          onGroup={(g) => setAddress((now) => ({ ...now, group: g }))}
          result={address.result}
          from={address.from}
          onFilters={(change) => {
            onFilters?.(change);
            setAddress((now) => ({ ...now, ...change }));
          }}
        />
      </LinkProvider>
    );
  }
  const routes = { "GET /api/plans/1/checks": { body: view }, "GET /api/plans/1/lab": { body: lab }, "GET /api/import/7/plan": { body: plan } };

  it("starts with the Result filter the address names: only the checks that read that way are listed, the plan's tests included", async () => {
    mockApi(routes);
    render(<Harness result="Failed" />);
    await screen.findAllByTestId("group-section");
    expect((screen.getByRole("combobox", { name: "Result" }) as HTMLSelectElement).value).toBe("Failed");
    // the test plan lists its one failed test, and no other card
    await waitFor(() => expect(screen.getAllByTestId("test-card").map((c) => Number(c.getAttribute("data-test")))).toEqual([failedId]));
    expect(screen.getAllByTestId("plan-list-count").map((c) => c.textContent)).toEqual(["1"]);
    // taking the filter off lists every test again
    fireEvent.change(screen.getByRole("combobox", { name: "Result" }), { target: { value: "all" } });
    await waitFor(() => expect(screen.getAllByTestId("test-card")).toHaveLength(plan.tests.length));
  });

  it("says in one line that the plan is narrowed and what Run all still does", async () => {
    mockApi(routes);
    render(<Harness result="Failed" />);
    await screen.findAllByTestId("group-section");
    const line = await screen.findByTestId("plan-narrowed");
    expect(line.textContent).toBe(`1 of the plan's ${plan.tests.length} tests is listed (Result: Failed). Run all runs all ${plan.tests.length}.`);
    // with the filter off the line is gone
    fireEvent.change(screen.getByRole("combobox", { name: "Result" }), { target: { value: "all" } });
    await waitFor(() => expect(screen.queryByTestId("plan-narrowed")).toBeNull());
  });

  it("a Result value from the address that no check reads now stays shown in the control, and the Test plan part stays with a line that says why it is empty", async () => {
    mockApi(routes);
    render(<Harness result="Couldn't check" />); // (as "show checks that could not be checked" opens the page)
    await screen.findAllByTestId("group-section");
    const control = screen.getByRole("combobox", { name: "Result" }) as HTMLSelectElement;
    expect(control.value).toBe("Couldn't check"); // the filter that is on, not "All results"
    expect(Array.from(control.options).map((o) => o.value)).toContain("Couldn't check");
    // 20 November 2026: a filter in the address opens the first tab with a match: Verify's claim that it couldn't check
    expect(screen.getAllByTestId("group-section").map((g) => g.getAttribute("data-group"))).toEqual(["verification"]);
    expect(screen.getAllByTestId("check-row").map((r) => r.getAttribute("data-check"))).toEqual(["claim-3"]);
    // on Crypto tests no card of the plan is listed, and the part says so; + Add test and Run all are still there
    fireEvent.click(screen.getByRole("tab", { name: "Crypto tests" }));
    const line = await screen.findByTestId("plan-narrowed");
    expect(line.textContent).toBe(`No test of the plan reads Couldn't check now. Run all runs all ${plan.tests.length}.`);
    expect(screen.queryAllByTestId("test-card")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Run all" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "+ Add test" })).toBeTruthy();
  });

  it("a filter changed on the page goes into the address, and one the address names comes back to the page", async () => {
    mockApi(routes);
    const onFilters = vi.fn();
    render(<Harness onFilters={onFilters} />);
    await screen.findAllByTestId("group-section");
    // (a filter changed here also names the open tab, so the tab stays where it is)
    fireEvent.change(screen.getByRole("combobox", { name: "Result" }), { target: { value: "Failed" } });
    expect(onFilters).toHaveBeenLastCalledWith({ result: "Failed", group: "verification" });
    fireEvent.change(screen.getByRole("combobox", { name: "Came from" }), { target: { value: "retest" } });
    expect(onFilters).toHaveBeenLastCalledWith({ from: "retest", group: "verification" });
    fireEvent.change(screen.getByRole("combobox", { name: "Came from" }), { target: { value: "all" } });
    expect(onFilters).toHaveBeenLastCalledWith({ from: null, group: "verification" });
    expect((screen.getByRole("combobox", { name: "Result" }) as HTMLSelectElement).value).toBe("Failed");
    fireEvent.click(screen.getByRole("button", { name: "the address changes" })); // Back, or a link, changed the address
    await waitFor(() => expect((screen.getByRole("combobox", { name: "Came from" }) as HTMLSelectElement).value).toBe("retest"));
    expect((screen.getByRole("combobox", { name: "Result" }) as HTMLSelectElement).value).toBe("all");
  });

  it("a filter changed on the page keeps the open tab; a filter the address names from elsewhere opens the first tab with a match", async () => {
    mockApi(routes);
    render(<Harness />);
    await screen.findAllByTestId("group-section");
    const shown = () => screen.getAllByTestId("group-section").map((g) => g.getAttribute("data-group"));
    expect(shown()).toEqual(["verification"]);
    // on the page: the tab stays, and says that nothing in it reads Failed
    fireEvent.change(screen.getByRole("combobox", { name: "Result" }), { target: { value: "Failed" } });
    expect(shown()).toEqual(["verification"]);
    fireEvent.change(screen.getByRole("combobox", { name: "Result" }), { target: { value: "all" } });
    expect(shown()).toEqual(["verification"]);
    // from elsewhere (Otto's "show me failed checks", a link): the tab of the failed checks opens
    fireEvent.click(screen.getByRole("button", { name: "failed checks are asked for" }));
    await waitFor(() => expect(shown()).toEqual(["encryption"]));
    expect((screen.getByRole("combobox", { name: "Result" }) as HTMLSelectElement).value).toBe("Failed");
  });
});

describe("the app, with a filter in the address", () => {
  const routes = {
    "GET /api/session": { body: session },
    "GET /api/workspace": { body: workspace },
    "GET /api/assessments/101": { body: assessmentView() },
    "GET /api/import/7/verify": { body: run },
    "GET /api/import/7/plan": { body: { ...plan, has_results: true } },
    "POST /api/import/7/plan": { body: { ...plan, has_results: true } },
    "GET /api/plans/1/lab": { body: lab },
    "GET /api/plans/1/checks": { body: checksView },
  };

  it("opens Checks filtered as the address says, and a filter changed there is in the address, so Back returns", async () => {
    window.history.replaceState(null, "", "#/a/101/checks?result=Passed");
    mockApi(routes);
    render(<App />);
    const result = (await screen.findByRole("combobox", { name: "Result" })) as HTMLSelectElement;
    await waitFor(() => expect(result.value).toBe("Passed"));
    // the first tab with a passed check is Crypto tests; a filter changed there keeps that tab in the address
    expect((await screen.findByRole("tab", { name: "Crypto tests" })).getAttribute("aria-selected")).toBe("true");
    fireEvent.change(screen.getByRole("combobox", { name: "Came from" }), { target: { value: "retest" } });
    await waitFor(() => expect(window.location.hash).toBe("#/a/101/checks?group=encryption&result=Passed&from=retest"));
    fireEvent.change(screen.getByRole("combobox", { name: "Result" }), { target: { value: "all" } });
    await waitFor(() => expect(window.location.hash).toBe("#/a/101/checks?group=encryption&from=retest"));
    expect(screen.getByRole("tab", { name: "Crypto tests" }).getAttribute("aria-selected")).toBe("true");
    // the sidebar's link to the page is the page itself, with no filter
    expect(within(screen.getByRole("navigation", { name: "Assessment" })).getByRole("link", { name: "Checks" }).getAttribute("href")).toBe("#/a/101/checks");
  });
});
