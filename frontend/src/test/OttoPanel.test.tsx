import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AssistantEntry, AssistantView, OttoProposal, PlanView } from "../api";
import { OttoPanel } from "../components/assistant/OttoPanel";
import { ProposalCard } from "../components/otto/ProposalCard";
import { LinkProvider } from "../components/related";
import { TestsScreen } from "../components/TestsScreen";
import { ReadOnlyProvider } from "../readOnly";
import type { Page } from "../router";
import {
  checkAccepted,
  checkProposal,
  checkRejected,
  decided,
  dependencyProposal,
  elsewhere,
  fixProposal,
  meaning,
  nextStep,
  onPage,
  panel,
  planProposal,
  result,
  suggestion,
  tab,
} from "./assistantFixtures";
import { allCalls, calls, mockApi, panelReads, plan, text } from "./fixtures";
import { CLOSED_REASON, NO_OTTO_REASON, NOT_INSTALLED_LINE } from "./ottoFixtures";

/** Phase 6a: the Otto assistant, the right-hand panel beside every page of an assessment. It draws what its one read
 * sends and has no request of its own: a button first shows what it will do and waits for Confirm, and Confirm sends
 * the very request the page's own button sends. */

type Routes = Parameters<typeof mockApi>[0];
const read = (page: string, item?: string) => `GET /api/assessments/101/assistant?${new URLSearchParams(item ? { page, item } : { page }).toString()}`;
const decide = (of: OttoProposal, decision: string) => `POST /api/plans/1/otto/proposals/${of.id}/${decision}`;

function Panel({ page = "checks", item = null, onGo = () => {}, closed = false }: { page?: string; item?: string | null; onGo?: (page: Page) => void; closed?: boolean }) {
  return (
    <ReadOnlyProvider readOnly={closed}>
      <LinkProvider assessmentId={101} planId={1}>
        <OttoPanel assessmentId={101} page={page as Page} item={item} onGo={onGo} />
      </LinkProvider>
    </ReadOnlyProvider>
  );
}

/** Shows the panel beside one page with what the backend would send for it. */
async function open(view: AssistantView, routes: Routes = {}, props: Parameters<typeof Panel>[0] = {}) {
  const fetchMock = mockApi({ [read(view.page, props.item ?? undefined)]: { body: view }, ...routes });
  render(<Panel page={view.page} {...props} />);
  await screen.findByTestId("otto-status");
  return fetchMock;
}

/** What one request sent: its method, its address and its JSON body. */
function sent(fetchMock: ReturnType<typeof mockApi>, key: string): { key: string; body: unknown } | null {
  const call = fetchMock.mock.calls.find(([input, init]) => `${init?.method ?? "GET"} ${String(input)}` === key);
  if (!call) return null;
  return { key, body: call[1]?.body ? JSON.parse(String(call[1].body)) : null };
}

const entries = () => screen.queryAllByTestId("otto-entry");
const entry = (id: string) => entries().find((e) => e.getAttribute("data-entry") === id) as HTMLElement;
const tabs = () => screen.queryAllByTestId("otto-tab");
const tabOf = (thread: string) => tabs().find((t) => t.getAttribute("data-thread") === thread) as HTMLElement;
const button = (within_: HTMLElement, name: string) => within(within_).getByRole("button", { name }) as HTMLButtonElement;

beforeEach(() => window.localStorage.clear());

// ---------------------------------------------------------------- the shell and the standing sentences

describe("the Otto panel: title, status line and standing sentences", () => {
  it("is titled Otto and repeats what Settings says about Live Otto, with the way there when it is off", async () => {
    const fetchMock = await open(panel("checks"));
    const box = screen.getByTestId("otto-panel");
    expect(within(box).getByRole("heading", { level: 2, name: "Otto" })).not.toBeNull();
    expect(text(screen.getByTestId("otto-status"))).toBe("Live Otto is off. Settings");
    expect(screen.getByTestId("otto-status-link").getAttribute("href")).toBe("#/settings?section=live-otto");
    expect(text(screen.getByTestId("otto-note"))).toContain("Looking at this panel runs nothing.");
    // looking at the panel is one read, and nothing else
    expect(allCalls(fetchMock)).toEqual([read("checks")]);
  });

  it("says Live Otto is on when it is, with no link", async () => {
    await open(panel("checks", { status: { text: "Live Otto is on.", live: true, link: null } }));
    expect(text(screen.getByTestId("otto-status"))).toBe("Live Otto is on.");
    expect(screen.queryByTestId("otto-status-link")).toBeNull();
  });

  it("with no file in yet: how to start, with Open Import, and no tab", async () => {
    await open(
      panel("overview", {
        plan_id: null,
        on_page: { title: "On this page", entries: [], empty: "Bring in a scanner file to start. Nothing is suggested yet.", empty_link: { label: "Open Import", link: { page: "inventory/import", item: null } } },
        elsewhere: { title: "Elsewhere: 0 more", count: 0, lines: [], empty: null },
      }),
    );
    expect(text(screen.getByTestId("otto-empty"))).toBe("Bring in a scanner file to start. Nothing is suggested yet. Open Import");
    expect(screen.getByTestId("otto-empty-link").getAttribute("href")).toBe("#/a/101/inventory/import");
    expect(screen.queryByTestId("otto-tabs")).toBeNull();
    expect(screen.queryByTestId("otto-elsewhere")).toBeNull();
  });

  it("with nothing for this page it says so, and lists what waits elsewhere", async () => {
    await open(
      panel("evidence", {
        tabs: [tab("fixing", { waiting: 1 })],
        elsewhere: elsewhere([{ text: "Fixes: 1 proposed fix, Update elliptic to 6.5.7", count: 1, link: { page: "fixes", item: "fix-advisory-cases-23" }, thread: "fixing" }]),
        waiting: 1,
      }),
    );
    expect(text(screen.getByTestId("otto-empty"))).toBe("Nothing is suggested on this page.");
    const box = screen.getByTestId("otto-elsewhere");
    expect(within(box).getByRole("heading", { level: 3 }).textContent).toBe("Elsewhere: 1 more");
    const line = within(box).getByTestId("otto-elsewhere-line");
    expect(text(line)).toBe("Fixes: 1 proposed fix, Update elliptic to 6.5.7");
    expect(within(line).getByRole("link").getAttribute("href")).toBe("#/a/101/fixes?item=fix-advisory-cases-23");
  });

  it("with nothing waiting anywhere it says the Overview's sentence", async () => {
    await open(panel("checks"));
    expect(text(screen.getByTestId("otto-nothing-waiting"))).toBe("Nothing from Otto is waiting for a decision.");
  });

  it("without Otto: the sentence Settings shows, and every suggestion is listed with its buttons off and that reason", async () => {
    const off = { ...checkProposal, buttons: checkProposal.buttons.map((b) => ({ ...b, can: false, blocked_reason: NO_OTTO_REASON })) };
    const fetchMock = await open(panel("advisories", { notices: [NOT_INSTALLED_LINE], tabs: [tab("testing", { waiting: 1 })], on_page: onPage([suggestion(off)]), waiting: 1 }));
    expect(text(screen.getByTestId("otto-notice"))).toBe(NOT_INSTALLED_LINE);
    const card = entry(off.id);
    expect(button(card, "Accept").disabled).toBe(true);
    expect(button(card, "Reject").disabled).toBe(true);
    expect(text(within(card).getByTestId("otto-blocked"))).toBe(NO_OTTO_REASON);
    fireEvent.click(button(card, "Accept"));
    expect(screen.queryByTestId("otto-confirm")).toBeNull();
    expect(calls(fetchMock)).toEqual([]);
  });

  it("in a closed assessment everything is listed and nothing can be pressed", async () => {
    const undo = { ...checkAccepted, buttons: [{ key: "undo" as const, label: "Undo", can: false, blocked_reason: CLOSED_REASON }] };
    const step = nextStep("next:run_all", "Run all", "Checks", { type: "run_all", plan_id: 1 }, { can: false, blocked_reason: CLOSED_REASON });
    const fetchMock = await open(
      panel("checks", { notices: [`Closed and signed off by A tester. ${CLOSED_REASON}`], tabs: [tab("testing")], on_page: onPage([suggestion(undo), step]) }),
      {},
      { closed: true },
    );
    expect(text(screen.getByTestId("otto-notice"))).toContain(CLOSED_REASON);
    expect(entries()).toHaveLength(2);
    for (const b of within(screen.getByTestId("otto-on-page")).getAllByRole("button")) expect((b as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByTestId("otto-blocked").map((e) => text(e))).toEqual([CLOSED_REASON, CLOSED_REASON]);
    expect(calls(fetchMock)).toEqual([]);
  });
});

// ---------------------------------------------------------------- a suggestion, in each of the three tabs

const THREADS: { name: string; page: string; thread: "testing" | "fixing" | "planning"; of: OttoProposal; where: string; href: string }[] = [
  { name: "Testing", page: "checks", thread: "testing", of: checkProposal, where: "On Advisories", href: "#/a/101/advisories?item=CVE-2022-21449" },
  { name: "Fixing", page: "fixes", thread: "fixing", of: fixProposal, where: "On Fixes", href: "#/a/101/fixes?item=fix-otto-cve-2022-21449" },
  { name: "Planning", page: "migration/systems", thread: "planning", of: planProposal, where: "On Systems", href: "#/a/101/migration/systems?item=software%3Alib-acme-sign" },
];

describe.each(THREADS)("a suggestion in the $name tab", ({ page, thread, of, where, href }) => {
  const proposed = () => panel(page, { tabs: [tab(thread, { waiting: 1 })], on_page: onPage([suggestion(of)]), waiting: 1 });

  it("carries From Otto, its title, why, where it lives and its status, and sends nothing by being shown", async () => {
    const fetchMock = await open(proposed());
    const card = entry(of.id);
    expect(card.getAttribute("data-what")).toBe(`suggestion:${of.kind}`);
    expect(text(within(card).getByTestId("otto-entry-mark"))).toBe("From Otto");
    expect(text(within(card).getByTestId("otto-entry-title"))).toBe(of.title);
    expect(text(within(card).getByTestId("otto-entry-text"))).toBe(of.why);
    expect(text(within(card).getByTestId("otto-entry-badge"))).toBe("Proposed");
    const link = within(card).getByTestId("otto-entry-where");
    expect(text(link)).toBe(where);
    expect(link.getAttribute("href")).toBe(href);
    expect(calls(fetchMock)).toEqual([]);
  });

  it("Accept first shows what will happen and waits; Cancel sends nothing; Confirm sends the page's own accept", async () => {
    let now = proposed();
    const after = decided(of, "accepted");
    const fetchMock = await open(now, {
      [read(page)]: () => ({ body: now }),
      [decide(of, "accept")]: () => {
        now = panel(page, { tabs: [tab(thread, { mark: `${thread}-mark-2` })], on_page: onPage([suggestion(after)]) });
        return { body: after };
      },
    });
    fireEvent.click(button(entry(of.id), "Accept"));
    const step = within(entry(of.id)).getByTestId("otto-confirm");
    expect(within(step).getAllByRole("listitem").map((li) => text(li))).toContain(of.kind === "check" ? "Runs nothing." : "Runs nothing and changes nothing on any system.");
    expect(text(within(step).getByTestId("otto-confirm-names"))).toBe(`This is the Accept button on ${where.slice(3)}.`);
    expect(within(step).queryByTestId("otto-reason")).toBeNull();
    expect(calls(fetchMock)).toEqual([]); // nothing was sent by the click on Accept
    fireEvent.click(within(step).getByTestId("otto-cancel-button"));
    expect(screen.queryByTestId("otto-confirm")).toBeNull();
    expect(calls(fetchMock)).toEqual([]); // ... nor by Cancel

    fireEvent.click(button(entry(of.id), "Accept"));
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    await waitFor(() => expect(text(within(entry(of.id)).getByTestId("otto-entry-badge"))).toBe(of.kind === "check" ? "Added" : "Accepted"));
    expect(calls(fetchMock)).toEqual([decide(of, "accept")]);
    expect(sent(fetchMock, decide(of, "accept"))?.body).toEqual({});
    // the card now reads as the page does: who and when, and Undo
    expect(text(within(entry(of.id)).getByTestId("otto-entry-decided"))).toContain("Accepted by You on");
    expect(button(entry(of.id), "Undo")).not.toBeNull();
    expect(panelReads(fetchMock).length).toBeGreaterThanOrEqual(2); // the panel read again after the decision
  });

  it("Reject asks for an optional short reason and sends it; without one it sends none", async () => {
    let now = proposed();
    const after = decided(of, "rejected", "Not this quarter");
    const fetchMock = await open(now, {
      [read(page)]: () => ({ body: now }),
      [decide(of, "reject")]: () => {
        now = panel(page, { tabs: [tab(thread, { mark: `${thread}-mark-2` })], on_page: onPage([suggestion(after)]) });
        return { body: after };
      },
    });
    fireEvent.click(button(entry(of.id), "Reject"));
    const step = within(entry(of.id)).getByTestId("otto-confirm");
    expect(text(step)).toContain("It is not deleted");
    const box = within(step).getByLabelText("Reason (optional, one short line)") as HTMLInputElement;
    expect(box.maxLength).toBe(300);
    expect(calls(fetchMock)).toEqual([]);
    fireEvent.change(box, { target: { value: "  Not this quarter " } });
    fireEvent.click(within(step).getByTestId("otto-confirm-button"));
    await waitFor(() => expect(text(within(entry(of.id)).getByTestId("otto-entry-badge"))).toBe("Not added (Not this quarter)"));
    expect(sent(fetchMock, decide(of, "reject"))?.body).toEqual({ reason: "Not this quarter" });
    expect(button(entry(of.id), "Reconsider")).not.toBeNull();
  });

  it("Reject with the reason left empty sends no reason", async () => {
    const fetchMock = await open(proposed(), { [decide(of, "reject")]: { body: decided(of, "rejected", "") } });
    fireEvent.click(button(entry(of.id), "Reject"));
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    await waitFor(() => expect(calls(fetchMock)).toEqual([decide(of, "reject")]));
    expect(sent(fetchMock, decide(of, "reject"))?.body).toEqual({});
  });

  it("Undo of an accept and Reconsider of a reject each wait for Confirm and send the page's own request", async () => {
    const accepted = decided(of, "accepted");
    const rejected = { ...decided(of, "rejected"), id: `${of.id}-two` };
    const fetchMock = await open(
      panel(page, { tabs: [tab(thread)], on_page: onPage([suggestion(accepted), suggestion(rejected)]) }),
      { [decide(accepted, "undo")]: { body: of }, [decide(rejected, "reconsider")]: { body: { ...of, id: rejected.id } } },
    );
    fireEvent.click(button(entry(accepted.id), "Undo"));
    expect(text(within(entry(accepted.id)).getByTestId("otto-confirm"))).toContain("open for a decision again");
    expect(calls(fetchMock)).toEqual([]);
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    await waitFor(() => expect(calls(fetchMock)).toEqual([decide(accepted, "undo")]));
    expect(sent(fetchMock, decide(accepted, "undo"))?.body).toEqual({});
    await waitFor(() => expect(screen.queryByTestId("otto-confirm")).toBeNull());

    fireEvent.click(button(entry(rejected.id), "Reconsider"));
    expect(calls(fetchMock)).toEqual([decide(accepted, "undo")]);
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    await waitFor(() => expect(calls(fetchMock)).toEqual([decide(accepted, "undo"), decide(rejected, "reconsider")]));
  });
});

describe("a decision from the panel is the page's own request", () => {
  /** The same proposal decided on its page (the card every tab shows) and in the panel: what each one sent. */
  async function both(decision: "accept" | "reject", reason?: string) {
    const route = `POST /api/plans/1/otto/proposals/${checkProposal.id}/${decision}`;
    const answer = { body: decision === "accept" ? checkAccepted : checkRejected };
    const onPageMock = mockApi({ [route]: answer });
    const done = vi.fn();
    const page = render(<ProposalCard planId={1} proposal={checkProposal} onDecided={done} />);
    fireEvent.click(screen.getByTestId(decision === "accept" ? "proposal-accept" : "proposal-reject"));
    if (decision === "reject") {
      if (reason) fireEvent.change(screen.getByTestId("proposal-reject-reason"), { target: { value: reason } });
      fireEvent.click(screen.getByTestId("proposal-reject-confirm"));
    }
    await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
    const fromPage = sent(onPageMock, route);
    const pageInit = onPageMock.mock.calls.find(([input]) => String(input).endsWith(`/${decision}`))?.[1];
    page.unmount();

    const view = panel("checks", { tabs: [tab("testing", { waiting: 1 })], on_page: onPage([suggestion(checkProposal)]), waiting: 1 });
    const inPanelMock = mockApi({ [read("checks")]: { body: view }, [route]: answer });
    render(<Panel page="checks" />);
    await screen.findByTestId("otto-status");
    fireEvent.click(button(entry(checkProposal.id), decision === "accept" ? "Accept" : "Reject"));
    if (reason) fireEvent.change(screen.getByTestId("otto-reason"), { target: { value: reason } });
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    await waitFor(() => expect(calls(inPanelMock)).toEqual([route]));
    const panelInit = inPanelMock.mock.calls.find(([input]) => String(input).endsWith(`/${decision}`))?.[1];
    return { fromPage, fromPanel: sent(inPanelMock, route), pageInit, panelInit };
  }

  it.each([
    ["accept", undefined],
    ["reject", "Not this quarter"],
    ["reject", undefined],
  ] as const)("%s (reason: %s): the same address, method, headers and body", async (decision, reason) => {
    const { fromPage, fromPanel, pageInit, panelInit } = await both(decision, reason);
    expect(fromPage).not.toBeNull();
    expect(fromPanel).toEqual(fromPage);
    expect(panelInit?.method).toBe(pageInit?.method);
    expect(panelInit?.headers).toEqual(pageInit?.headers);
    // nothing in the request says where the button was pressed
    expect(JSON.stringify(fromPanel)).not.toMatch(/panel|assistant|otto-panel/i);
  });
});

// ---------------------------------------------------------------- next steps: a button of the page, by its own name

const STEPS: { what: string; title: string; page: string; label: string; action: Parameters<typeof nextStep>[3]; request: string; body: unknown; then?: string }[] = [
  { what: "next:verify", title: "Verify claims", page: "inventory/import", label: "Import", action: { type: "verify", import_id: 7 }, request: "POST /api/import/7/verify", body: null, then: "inventory/verify" },
  { what: "next:run_all", title: "Run all", page: "checks", label: "Checks", action: { type: "run_all", plan_id: 1 }, request: "POST /api/plans/1/run-all", body: null },
  { what: "next:run", title: "Run", page: "checks", label: "Checks", action: { type: "run", plan_id: 1, item_id: 12 }, request: "POST /api/plans/1/tests/12/run", body: null },
  { what: "next:retest", title: "Retest new version", page: "evidence", label: "Evidence", action: { type: "retest", plan_id: 1, version: "1.4.3", component: "acme-sign" }, request: "POST /api/plans/1/retest", body: { version: "1.4.3", component: "acme-sign" } },
  { what: "next:connect", title: "Connect demo code", page: "fixes", label: "Fixes", action: { type: "connect", plan_id: 1, fix_id: "fix-ecdsa-range-check" }, request: "POST /api/plans/1/fixes/connect", body: null },
  { what: "next:run_proof_again", title: "Run proof again", page: "fixes", label: "Fixes", action: { type: "run_proof_again", plan_id: 1, fix_id: "fix-ecdsa-range-check" }, request: "POST /api/plans/1/fixes/fix-ecdsa-range-check/proof", body: null },
  { what: "next:open_pull_request", title: "Open pull request", page: "fixes", label: "Fixes", action: { type: "open_pull_request", plan_id: 1, fix_id: "fix-ecdsa-range-check", reviewers: ["a", "you"] }, request: "POST /api/plans/1/fixes/fix-ecdsa-range-check/pull-request", body: { reviewers: ["a", "you"] } },
  { what: "next:retest_now", title: "Retest now", page: "fixes", label: "Fixes", action: { type: "retest_now", plan_id: 1, fix_id: "fix-ecdsa-range-check" }, request: "POST /api/plans/1/fixes/fix-ecdsa-range-check/retest", body: null, then: "evidence" },
  { what: "next:try", title: "Try on a test copy", page: "fixes", label: "Fixes", action: { type: "try", plan_id: 1, fix_id: "fix-tls-versions", change: "tls:server:localhost:8443" }, request: "POST /api/plans/1/changes/try", body: { change: "tls:server:localhost:8443" } },
  { what: "next:ask_approval", title: "Ask for approval", page: "fixes", label: "Fixes", action: { type: "ask_approval", plan_id: 1, fix_id: "fix-tls-versions", change: "tls:server:localhost:8443", reviewers: ["you"] }, request: "POST /api/plans/1/changes/ask-approval", body: { change: "tls:server:localhost:8443", reviewers: ["you"] } },
  { what: "next:measure_library", title: "Measure on a public copy", page: "migration/dependencies", label: "Dependencies", action: { type: "measure_library", plan_id: 1, row: "row-5" }, request: "POST /api/plans/1/dependencies/measure", body: { row: "row-5" } },
  { what: "next:measure_all", title: "Measure all", page: "migration/dependencies", label: "Dependencies", action: { type: "measure_all", plan_id: 1 }, request: "POST /api/plans/1/dependencies/measure", body: {} },
  { what: "next:measure_status", title: "Measure status", page: "migration/systems", label: "Systems", action: { type: "measure_status", plan_id: 1 }, request: "POST /api/plans/1/migration/measure", body: {} },
];

describe("a next step", () => {
  it.each(STEPS)("$title: the page button's own name, a Confirm step, and on Confirm that button's own request", async ({ what, title, page, label, action, request, body, then }) => {
    const step = nextStep(what, title, label, action);
    const onGo = vi.fn();
    const fetchMock = await open(panel(page, { on_page: onPage([step]) }), { [request]: { body: {} } }, { onGo });
    const card = entry(step.id);
    expect(text(within(card).getByTestId("otto-entry-mark"))).toBe("Next step");
    expect(text(within(card).getByTestId("otto-entry-title"))).toBe(title);
    fireEvent.click(button(card, title));
    const confirm = within(card).getByTestId("otto-confirm");
    expect(text(within(confirm).getByTestId("otto-confirm-names"))).toBe(`This is the ${title} button on ${label}.`);
    expect(calls(fetchMock)).toEqual([]); // nothing before Confirm
    fireEvent.click(within(confirm).getByTestId("otto-cancel-button"));
    expect(calls(fetchMock)).toEqual([]);
    fireEvent.click(button(entry(step.id), title));
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    await waitFor(() => expect(calls(fetchMock)).toEqual([request]));
    expect(sent(fetchMock, request)?.body).toEqual(body);
    // where the page itself goes after its button's answer, the panel goes too (Verify, Evidence); otherwise it stays
    await waitFor(() => expect(onGo.mock.calls.map((c) => c[0])).toEqual(then ? [then] : []));
  });

  it("every kind of next step the backend can send has its request here", () => {
    const sendable = ["verify", "run", "run_all", "retest", "connect", "run_proof_again", "open_pull_request", "retest_now", "try", "ask_approval", "measure_library", "measure_all", "measure_status"];
    expect(STEPS.map((s) => s.action.type).sort()).toEqual([...sendable].sort());
  });

  it("Run all and Run send exactly what the buttons of the test plan send", async () => {
    function Harness() {
      const [current, setCurrent] = useState<PlanView | null>(null);
      return <TestsScreen importId={7} plan={current} onPlan={setCurrent} />;
    }
    const onPageMock = mockApi({ "POST /api/import/7/plan": { body: plan }, "POST /api/plans/1/run-all": { body: plan }, "POST /api/plans/1/tests/11/run": { body: plan } });
    const page = render(<Harness />);
    await screen.findAllByTestId("test-card");
    fireEvent.click(screen.getByRole("button", { name: "Run all" }));
    await waitFor(() => expect(calls(onPageMock)).toContain("POST /api/plans/1/run-all"));
    const firstCard = screen.getAllByTestId("test-card")[0] as HTMLElement;
    await waitFor(() => expect((within(firstCard).getByRole("button", { name: /^Run/ }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(within(firstCard).getByRole("button", { name: /^Run/ }));
    await waitFor(() => expect(calls(onPageMock)).toContain("POST /api/plans/1/tests/11/run"));
    const fromPage = { all: sent(onPageMock, "POST /api/plans/1/run-all"), one: sent(onPageMock, "POST /api/plans/1/tests/11/run") };
    page.unmount();

    const all = nextStep("next:run_all", "Run all", "Checks", { type: "run_all", plan_id: 1 });
    const one = nextStep("next:run", "Run", "Checks", { type: "run", plan_id: 1, item_id: 11 });
    const inPanelMock = await open(panel("checks", { on_page: onPage([all, one]) }), { "POST /api/plans/1/run-all": { body: plan }, "POST /api/plans/1/tests/11/run": { body: plan } });
    fireEvent.click(button(entry(all.id), "Run all"));
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    await waitFor(() => expect(calls(inPanelMock)).toEqual(["POST /api/plans/1/run-all"]));
    await waitFor(() => expect(screen.queryByTestId("otto-confirm")).toBeNull());
    fireEvent.click(button(entry(one.id), "Run"));
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    await waitFor(() => expect(calls(inPanelMock)).toEqual(["POST /api/plans/1/run-all", "POST /api/plans/1/tests/11/run"]));
    expect({ all: sent(inPanelMock, "POST /api/plans/1/run-all"), one: sent(inPanelMock, "POST /api/plans/1/tests/11/run") }).toEqual(fromPage);
  });

  it("a button that is off on its page is off here, with the page's own reason and no Confirm", async () => {
    const why = "Run every test in the plan first, so there is a result to compare with.";
    const step = nextStep("next:connect", "Connect demo code", "Fixes", { type: "connect", plan_id: 1 }, { can: false, blocked_reason: why });
    const fetchMock = await open(panel("fixes", { on_page: onPage([step]) }));
    expect(button(entry(step.id), "Connect demo code").disabled).toBe(true);
    expect(text(within(entry(step.id)).getByTestId("otto-blocked"))).toBe(why);
    fireEvent.click(button(entry(step.id), "Connect demo code"));
    expect(screen.queryByTestId("otto-confirm")).toBeNull();
    expect(calls(fetchMock)).toEqual([]);
  });

  it("a step that only opens a page is a link: it needs no Confirm and sends nothing", async () => {
    const step = nextStep("next:open", "Open checks", "Overview", { type: "open", link: { page: "checks", item: null } }, { needs: "nothing", confirm: null });
    const fetchMock = await open(panel("overview", { on_page: onPage([step]) }));
    const link = within(entry(step.id)).getByTestId("otto-step-open");
    expect(text(link)).toBe("Open checks");
    expect(link.getAttribute("href")).toBe("#/a/101/checks");
    expect(within(entry(step.id)).queryByRole("button")).toBeNull();
    expect(calls(fetchMock)).toEqual([]);
  });

  it("a refusal is the server's own sentence, shown in the card, and the Confirm step stays", async () => {
    const step = nextStep("next:run_all", "Run all", "Checks", { type: "run_all", plan_id: 1 });
    await open(panel("checks", { on_page: onPage([step]) }), {
      "POST /api/plans/1/run-all": { status: 409, body: { error: { message: "Tests are running. Wait for them to finish.", line: null, field: null } } },
    });
    fireEvent.click(button(entry(step.id), "Run all"));
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    expect(text(await within(entry(step.id)).findByRole("alert"))).toContain("Tests are running. Wait for them to finish.");
    expect(within(entry(step.id)).getByTestId("otto-confirm")).not.toBeNull();
  });

  it("while something runs the card says so, and the panel asks again", async () => {
    let reads = 0;
    const step = nextStep("next:run_all", "Run all", "Checks", { type: "run_all", plan_id: 1 }, { can: false, blocked_reason: "Tests are running. Wait for them to finish.", running: true, progress: "3 still running" });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockApi({
      [read("checks")]: () => {
        reads += 1;
        return { body: panel("checks", { busy: reads < 2, on_page: onPage(reads < 2 ? [step] : []) }) };
      },
    });
    render(<Panel page="checks" />);
    expect(text(await screen.findByTestId("otto-step-running"))).toBe("3 still running");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    await waitFor(() => expect(screen.queryByTestId("otto-step-running")).toBeNull());
    expect(reads).toBe(2);
  });
});

// ---------------------------------------------------------------- what this means

describe("what this means", () => {
  it("is the result's own sentence with links to its evidence and its fix, and nothing to press", async () => {
    const fetchMock = await open(panel("evidence", { tabs: [tab("testing")], on_page: onPage([meaning()]) }));
    const card = entry("meaning:result:12");
    expect(text(within(card).getByTestId("otto-entry-mark"))).toBe("What this means");
    expect(text(within(card).getByTestId("otto-entry-badge"))).toBe("Failed");
    expect(text(within(card).getByTestId("otto-entry-text"))).toContain("A fix is suggested: see Fixing.");
    expect(within(card).getAllByTestId("otto-entry-link").map((a) => [text(a), a.getAttribute("href")])).toEqual([
      ["See the evidence", "#/a/101/evidence?item=test-4"],
      ["View in Fixes", "#/a/101/fixes?item=fix-ecdsa-range-check"],
    ]);
    expect(within(card).queryByRole("button")).toBeNull();
    expect(calls(fetchMock)).toEqual([]);
  });
});

// ---------------------------------------------------------------- the tabs

describe("the tabs", () => {
  const three = (over: Partial<AssistantView> = {}) =>
    panel("checks", {
      tabs: [
        tab("testing", { waiting: 2, so_far: [result(1), result(2, "Failed", "fail")] }),
        tab("fixing", { waiting: 1, so_far: [suggestion(decided(dependencyProposal, "accepted"))] }),
        tab("planning", { waiting: 0 }),
      ],
      ...over,
    });

  it("are at most three, each with how many of its suggestions wait and a way to close it", async () => {
    await open(three());
    expect(tabs().map((t) => [t.getAttribute("data-thread"), text(within(t).getByRole("tab")).replace(/ waiting for a decision$/, "")])).toEqual([
      ["testing", "Testing 2"],
      ["fixing", "New: Fixing 1"],
      ["planning", "New: Planning 0"],
    ]);
    expect(tabs()).toHaveLength(3);
    expect(screen.getAllByTestId("otto-tab-close").map((b) => b.getAttribute("aria-label"))).toEqual(["Close the Testing tab", "Close the Fixing tab", "Close the Planning tab"]);
  });

  it("a next step alone opens no tab", async () => {
    await open(panel("checks", { on_page: onPage([nextStep("next:run_all", "Run all", "Checks", { type: "run_all", plan_id: 1 })]) }));
    expect(screen.queryByTestId("otto-tabs")).toBeNull();
    expect(screen.queryByTestId("otto-so-far")).toBeNull();
    expect(entries()).toHaveLength(1);
  });

  it("opening a page selects its tab, and a tab picked by hand shows its own thread so far", async () => {
    const fetchMock = await open(three());
    expect(tabOf("testing").getAttribute("data-selected")).toBe("true");
    expect(screen.getByTestId("otto-so-far").getAttribute("data-thread")).toBe("testing");
    expect(within(screen.getByTestId("otto-so-far")).getAllByTestId("otto-entry")).toHaveLength(2);
    fireEvent.click(within(tabOf("fixing")).getByRole("tab"));
    expect(tabOf("fixing").getAttribute("data-selected")).toBe("true");
    const soFar = screen.getByTestId("otto-so-far");
    expect(within(soFar).getByRole("heading", { level: 3 }).textContent).toBe("This thread so far: Fixing");
    expect(text(within(soFar).getByTestId("otto-entry-badge"))).toBe("Accepted");
    // switching tabs is free: it sent nothing
    expect(allCalls(fetchMock)).toEqual([read("checks")]);
  });

  it("where the page's own tab is not open, the tab you had stays and the page's next step shows there", async () => {
    const step = nextStep("next:measure_status", "Measure status", "Systems", { type: "measure_status", plan_id: 1 });
    await open(panel("migration/systems", { tabs: [tab("testing", { so_far: [result(1)] })], on_page: onPage([step]) }));
    expect(tabs().map((t) => t.getAttribute("data-thread"))).toEqual(["testing"]);
    expect(tabOf("testing").getAttribute("data-selected")).toBe("true");
    expect(entry(step.id)).not.toBeUndefined();
  });

  it("a tab that has something new shows a dot until it is opened", async () => {
    await open(three());
    expect(tabOf("fixing").getAttribute("data-dot")).toBe("true");
    expect(within(tabOf("fixing")).getByTestId("otto-tab-dot")).not.toBeNull();
    expect(tabOf("testing").getAttribute("data-dot")).toBe("false"); // the open tab has been seen
    fireEvent.click(within(tabOf("fixing")).getByRole("tab"));
    await waitFor(() => expect(tabOf("fixing").getAttribute("data-dot")).toBe("false"));
    fireEvent.click(within(tabOf("testing")).getByRole("tab"));
    expect(tabOf("fixing").getAttribute("data-dot")).toBe("false"); // seen: no dot until something new arrives
  });

  it("closing a tab sends nothing, is remembered in this browser, and the tab returns with a dot when its thread has something new", async () => {
    let now = three();
    const fetchMock = await open(now, { [read("checks")]: () => ({ body: now }) });
    fireEvent.click(within(tabOf("fixing")).getByTestId("otto-tab-close"));
    expect(tabs().map((t) => t.getAttribute("data-thread"))).toEqual(["testing", "planning"]);
    expect(calls(fetchMock)).toEqual([]);
    expect(JSON.parse(window.localStorage.getItem("evidence-lab-otto-tabs-101") ?? "{}").closed).toEqual({ fixing: "fixing-mark-1" });

    // the same panel opened again (a reload): the tab stays closed
    screen.getByTestId("otto-panel");
    const again = render(<Panel page="checks" />);
    await waitFor(() => expect(screen.getAllByTestId("otto-tabs")).toHaveLength(2));
    for (const list of screen.getAllByTestId("otto-tabs")) expect(within(list).queryAllByTestId("otto-tab").map((t) => t.getAttribute("data-thread"))).toEqual(["testing", "planning"]);
    again.unmount();

    // its thread gets a new entry (the mark changes): it comes back by itself, with a dot
    now = three({ tabs: [...three().tabs.filter((t) => t.key !== "fixing"), tab("fixing", { waiting: 2, mark: "fixing-mark-2" })].sort((a, b) => ["testing", "fixing", "planning"].indexOf(a.key) - ["testing", "fixing", "planning"].indexOf(b.key)) });
    const { notifyChanged } = await import("../changes");
    act(() => notifyChanged());
    await waitFor(() => expect(tabs().map((t) => t.getAttribute("data-thread"))).toEqual(["testing", "fixing", "planning"]));
    expect(tabOf("fixing").getAttribute("data-dot")).toBe("true");
  });

  it("a closed tab opens again from its line under Elsewhere", async () => {
    await open(
      three({ elsewhere: elsewhere([{ text: "Fixes: 1 proposed fix, Update elliptic to 6.5.7", count: 1, link: { page: "fixes", item: null }, thread: "fixing" }]), waiting: 1 }),
    );
    fireEvent.click(within(tabOf("fixing")).getByTestId("otto-tab-close"));
    expect(tabOf("fixing")).toBeUndefined();
    fireEvent.click(within(screen.getByTestId("otto-elsewhere-line")).getByRole("link"));
    await waitFor(() => expect(tabOf("fixing")).not.toBeUndefined());
  });

  it("a long thread shows its newest entries, and the rest unfold", async () => {
    const many = Array.from({ length: 9 }, (_, i) => result(i + 1));
    await open(panel("checks", { tabs: [tab("testing", { so_far: many })] }));
    const soFar = screen.getByTestId("otto-so-far");
    expect(within(soFar).getAllByTestId("otto-entry").map((e) => e.getAttribute("data-entry"))).toEqual(["result:4", "result:5", "result:6", "result:7", "result:8", "result:9"]);
    fireEvent.click(within(soFar).getByTestId("otto-so-far-all"));
    expect(within(soFar).getAllByTestId("otto-entry")).toHaveLength(9);
  });

  it("a decided suggestion in a thread so far keeps its page's buttons, each behind Confirm", async () => {
    const accepted: AssistantEntry = suggestion(decided(dependencyProposal, "accepted"));
    const fetchMock = await open(panel("fixes", { tabs: [tab("fixing", { so_far: [accepted] })] }), { [decide(dependencyProposal, "undo")]: { body: dependencyProposal } });
    const line = within(screen.getByTestId("otto-so-far")).getByTestId("otto-entry");
    expect(text(within(line).getByTestId("otto-entry-decided"))).toContain("Accepted by You on");
    fireEvent.click(button(line, "Undo"));
    expect(calls(fetchMock)).toEqual([]);
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    await waitFor(() => expect(calls(fetchMock)).toEqual([decide(dependencyProposal, "undo")]));
  });
});

// ---------------------------------------------------------------- reading again

describe("the panel reads again", () => {
  it("when the page or the open item changes, and after a change made on the page", async () => {
    const fetchMock = mockApi({});
    const first = render(<Panel page="checks" />);
    await screen.findByTestId("otto-status");
    first.rerender(<Panel page="evidence" />);
    await waitFor(() => expect(panelReads(fetchMock)).toEqual([read("checks"), read("evidence")]));
    first.rerender(<Panel page="evidence" item="test-4" />);
    await waitFor(() => expect(panelReads(fetchMock)).toEqual([read("checks"), read("evidence"), read("evidence", "test-4")]));
    const { notifyChanged } = await import("../changes");
    act(() => notifyChanged());
    await waitFor(() => expect(panelReads(fetchMock)).toHaveLength(4));
    expect(calls(fetchMock)).toEqual([]); // reads only
  });
});

// ---------------------------------------------------------------- the panel beside a page, in the app

describe("the panel beside a page of the app", () => {
  it("after a decision in the panel the page reads its own view again and shows the same status word", async () => {
    const { default: App } = await import("../App");
    const { advisoriesAddedNotRun, advisoriesNotAdded, blankProposal, blankProposalAccepted } = await import("./ottoFixtures");
    const { assessmentView, workspace } = await import("./shellFixtures");
    const { checksView } = await import("./checksFixtures");
    const { lab, run, session } = await import("./fixtures");
    let accepted = false;
    const before = panel("advisories", { tabs: [tab("testing", { waiting: 1 })], on_page: onPage([suggestion(blankProposal)]), waiting: 1 });
    const after = panel("advisories", { tabs: [tab("testing", { mark: "testing-mark-2" })], on_page: onPage([suggestion(blankProposalAccepted)]) });
    window.history.replaceState(null, "", "#/a/101/advisories");
    const fetchMock = mockApi({
      "GET /api/session": { body: session },
      "GET /api/workspace": { body: workspace },
      "GET /api/assessments/101": { body: assessmentView() },
      "GET /api/import/7/verify": { body: run },
      "GET /api/import/7/plan": { body: { ...plan, has_results: true } },
      "GET /api/plans/1/lab": { body: lab },
      "GET /api/plans/1/checks": { body: checksView },
      "GET /api/projects/10": { body: { id: 10, name: "Acme Pay", folder_id: null, archived: false, is_demo: true, path: [], assessments: [], next_name: "Assessment 2" } },
      "GET /api/plans/1/advisories": () => ({ body: accepted ? advisoriesAddedNotRun : advisoriesNotAdded }),
      [read("advisories")]: () => ({ body: accepted ? after : before }),
      [`POST /api/plans/1/otto/proposals/${blankProposal.id}/accept`]: () => {
        accepted = true;
        return { body: blankProposalAccepted };
      },
    });
    render(<App />);
    const box = await screen.findByTestId("otto-panel");
    await within(box).findByTestId("otto-entry");
    const rows = () => screen.getAllByTestId("advisory-row");
    await waitFor(() => expect(rows().length).toBeGreaterThan(0));
    const readsBefore = allCalls(fetchMock).filter((k) => k === "GET /api/plans/1/advisories").length;
    expect(text(rows()[0])).toContain("Proposed");

    fireEvent.click(within(box).getByRole("button", { name: "Accept" }));
    expect(calls(fetchMock).filter((k) => k.startsWith("POST"))).toEqual([]);
    fireEvent.click(within(box).getByTestId("otto-confirm-button"));
    // the panel shows the page's word, and the page has read its own view again and shows it too
    await waitFor(() => expect(text(within(box).getByTestId("otto-entry-badge"))).toBe("Added"));
    await waitFor(() => expect(allCalls(fetchMock).filter((k) => k === "GET /api/plans/1/advisories").length).toBeGreaterThan(readsBefore));
    await waitFor(() => expect(text(rows()[0])).toContain("Added"));
    expect(calls(fetchMock).filter((k) => k.startsWith("POST"))).toEqual([`POST /api/plans/1/otto/proposals/${blankProposal.id}/accept`]);
    window.history.replaceState(null, "", "#/projects");
  });
});

// ---------------------------------------------------------------- who a decision is recorded as

describe("who a decision is recorded as", () => {
  const proposed = () => panel("checks", { tabs: [tab("testing", { waiting: 1 })], on_page: onPage([suggestion(checkProposal)]), waiting: 1 });
  const NAME = "POST /api/otto/name";

  it("asks for a name once, at the first Confirm of a decision; a typed name is kept first, and then the decision is sent", async () => {
    const order: string[] = [];
    const fetchMock = await open(proposed(), {
      [NAME]: () => {
        order.push("name");
        return { body: {} };
      },
      [decide(checkProposal, "accept")]: () => {
        order.push("decision");
        return { body: checkAccepted };
      },
    });
    fireEvent.click(button(entry(checkProposal.id), "Accept"));
    const box = screen.getByLabelText("Your name (asked once; kept in Settings)") as HTMLInputElement;
    expect(box.maxLength).toBe(60);
    expect(text(screen.getByTestId("otto-name-note"))).toContain("This app has one login and does not check who is at the keyboard.");
    expect(calls(fetchMock)).toEqual([]);
    fireEvent.change(box, { target: { value: "  Kevin Singuyen " } });
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    await waitFor(() => expect(order).toEqual(["name", "decision"]));
    expect(sent(fetchMock, NAME)?.body).toEqual({ name: "Kevin Singuyen" });
    expect(sent(fetchMock, decide(checkProposal, "accept"))?.body).toEqual({}); // the decision itself is the page's own request
    expect(window.localStorage.getItem("evidence-lab-otto-name")).toBe("asked");
  });

  it("left empty, only the decision is sent, and the name is not asked for again in this browser", async () => {
    const fetchMock = await open(proposed(), { [decide(checkProposal, "accept")]: { body: checkAccepted }, [decide(checkProposal, "reject")]: { body: checkRejected } });
    fireEvent.click(button(entry(checkProposal.id), "Accept"));
    expect(screen.getByTestId("otto-name")).not.toBeNull();
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    await waitFor(() => expect(calls(fetchMock)).toEqual([decide(checkProposal, "accept")]));
    await waitFor(() => expect(screen.queryByTestId("otto-confirm")).toBeNull());
    // the next decision: no field, and one line that says who it is recorded as
    fireEvent.click(button(entry(checkProposal.id), "Reject"));
    expect(screen.queryByTestId("otto-name")).toBeNull();
    expect(text(screen.getByTestId("otto-recorded-as"))).toBe("Recorded as You, with the time.");
  });

  it("once a name has been typed, the Confirm step says who the decision is recorded as and asks for nothing", async () => {
    const view = proposed();
    const named = { ...view, recorded_as: { ...view.recorded_as, value: "Kevin Singuyen", recorded_as: "Kevin Singuyen", typed: true, line: "Recorded as Kevin Singuyen, with the time." } };
    await open(named);
    fireEvent.click(button(entry(checkProposal.id), "Accept"));
    expect(screen.queryByTestId("otto-name")).toBeNull();
    expect(text(screen.getByTestId("otto-recorded-as"))).toBe("Recorded as Kevin Singuyen, with the time.");
  });

  it("a next step records no name, so its Confirm step asks for none", async () => {
    const step = nextStep("next:run_all", "Run all", "Checks", { type: "run_all", plan_id: 1 });
    await open(panel("checks", { on_page: onPage([step]) }));
    fireEvent.click(button(entry(step.id), "Run all"));
    expect(screen.getByTestId("otto-confirm")).not.toBeNull();
    expect(screen.queryByTestId("otto-name")).toBeNull();
    expect(screen.queryByTestId("otto-recorded-as")).toBeNull();
  });
});
