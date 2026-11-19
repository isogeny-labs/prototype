import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AssistantEntry, AssistantGo, AssistantView, OttoProposal, PlanView } from "../api";
import { OttoPanel } from "../components/assistant/OttoPanel";
import { ProposalCard } from "../components/otto/ProposalCard";
import { LinkProvider } from "../components/related";
import { TestsScreen } from "../components/TestsScreen";
import { ReadOnlyProvider } from "../readOnly";
import type { Page } from "../router";
import {
  answer,
  checkAccepted,
  checkProposal,
  checkRejected,
  decided,
  dependencyProposal,
  elsewhere,
  fixProposal,
  goTo,
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

function Panel({
  page = "checks",
  item = null,
  onGo = () => {},
  onGoTo,
  closed = false,
}: {
  page?: string;
  item?: string | null;
  onGo?: (page: Page, item?: string | null) => void;
  onGoTo?: (where: AssistantGo) => void;
  closed?: boolean;
}) {
  return (
    <ReadOnlyProvider readOnly={closed}>
      <LinkProvider assessmentId={101} planId={1}>
        <OttoPanel assessmentId={101} page={page as Page} item={item} onGo={onGo} onGoTo={onGoTo} />
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

const STEPS: { what: string; title: string; page: string; label: string; action: Parameters<typeof nextStep>[3]; request: string; body: unknown; then?: string; thenItem?: string }[] = [
  { what: "next:verify", title: "Verify claims", page: "inventory/import", label: "Import", action: { type: "verify", import_id: 7 }, request: "POST /api/import/7/verify", body: null, then: "inventory/verify" },
  { what: "next:run_all", title: "Run all", page: "checks", label: "Checks", action: { type: "run_all", plan_id: 1 }, request: "POST /api/plans/1/run-all", body: null },
  { what: "next:run", title: "Run", page: "checks", label: "Checks", action: { type: "run", plan_id: 1, item_id: 12 }, request: "POST /api/plans/1/tests/12/run", body: null },
  { what: "next:retest", title: "Retest new version", page: "evidence", label: "Evidence", action: { type: "retest", plan_id: 1, version: "1.4.3", component: "acme-sign" }, request: "POST /api/plans/1/retest", body: { version: "1.4.3", component: "acme-sign" } },
  { what: "next:connect", title: "Connect demo code", page: "fixes", label: "Fixes", action: { type: "connect", plan_id: 1, fix_id: "fix-ecdsa-range-check" }, request: "POST /api/plans/1/fixes/connect", body: null },
  { what: "next:run_proof_again", title: "Run proof again", page: "fixes", label: "Fixes", action: { type: "run_proof_again", plan_id: 1, fix_id: "fix-ecdsa-range-check" }, request: "POST /api/plans/1/fixes/fix-ecdsa-range-check/proof", body: null },
  { what: "next:open_pull_request", title: "Open pull request", page: "fixes", label: "Fixes", action: { type: "open_pull_request", plan_id: 1, fix_id: "fix-ecdsa-range-check", reviewers: ["a", "you"] }, request: "POST /api/plans/1/fixes/fix-ecdsa-range-check/pull-request", body: { reviewers: ["a", "you"] } },
  { what: "next:retest_now", title: "Retest now", page: "fixes", label: "Fixes", action: { type: "retest_now", plan_id: 1, fix_id: "fix-ecdsa-range-check", link: { page: "evidence", item: "test-4", group: null } }, request: "POST /api/plans/1/fixes/fix-ecdsa-range-check/retest", body: null, then: "evidence", thenItem: "test-4" },
  { what: "next:try", title: "Try on a test copy", page: "fixes", label: "Fixes", action: { type: "try", plan_id: 1, fix_id: "fix-tls-versions", change: "tls:server:localhost:8443" }, request: "POST /api/plans/1/changes/try", body: { change: "tls:server:localhost:8443" } },
  { what: "next:ask_approval", title: "Ask for approval", page: "fixes", label: "Fixes", action: { type: "ask_approval", plan_id: 1, fix_id: "fix-tls-versions", change: "tls:server:localhost:8443", reviewers: ["you"] }, request: "POST /api/plans/1/changes/ask-approval", body: { change: "tls:server:localhost:8443", reviewers: ["you"] } },
  { what: "next:measure_library", title: "Measure on a public copy", page: "migration/dependencies", label: "Dependencies", action: { type: "measure_library", plan_id: 1, row: "row-5" }, request: "POST /api/plans/1/dependencies/measure", body: { row: "row-5" } },
  { what: "next:measure_all", title: "Measure all", page: "migration/dependencies", label: "Dependencies", action: { type: "measure_all", plan_id: 1 }, request: "POST /api/plans/1/dependencies/measure", body: {} },
  { what: "next:measure_status", title: "Measure status", page: "migration/systems", label: "Systems", action: { type: "measure_status", plan_id: 1 }, request: "POST /api/plans/1/migration/measure", body: {} },
];

describe("a next step", () => {
  it.each(STEPS)("$title: the page button's own name, a Confirm step, and on Confirm that button's own request", async ({ what, title, page, label, action, request, body, then, thenItem }) => {
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
    // where the page itself goes after its button's answer, the panel goes too (Verify; Evidence, on the result the fix
    // came from, as Retest now on Fixes does); otherwise it stays
    await waitFor(() => expect(onGo.mock.calls).toEqual(then ? [[then, thenItem ?? null]] : []));
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
      "POST /api/plans/1/run-all": { status: 409, body: { error: { message: "Tests are still running. Wait until they have finished.", line: null, field: null } } },
    });
    fireEvent.click(button(entry(step.id), "Run all"));
    fireEvent.click(screen.getByTestId("otto-confirm-button"));
    expect(text(await within(entry(step.id)).findByRole("alert"))).toContain("Tests are still running. Wait until they have finished.");
    expect(within(entry(step.id)).getByTestId("otto-confirm")).not.toBeNull();
  });

  it("while something runs the card says so, and the panel asks again", async () => {
    let reads = 0;
    const step = nextStep("next:run_all", "Run all", "Checks", { type: "run_all", plan_id: 1 }, { can: false, blocked_reason: "Tests are still running. Wait until they have finished.", running: true, progress: "3 still running" });
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

  it("goes on asking after a read that failed, so one lost answer does not leave the card saying it runs for good", async () => {
    let reads = 0;
    const step = nextStep("next:run_all", "Run all", "Checks", { type: "run_all", plan_id: 1 }, { can: false, blocked_reason: "Tests are still running. Wait until they have finished.", running: true, progress: "3 still running" });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockApi({
      [read("checks")]: () => {
        reads += 1;
        if (reads === 2) return { status: 500, body: { error: { message: "The app could not answer.", line: null, field: null } } };
        return { body: panel("checks", { busy: reads < 3, on_page: onPage(reads < 3 ? [step] : []) }) };
      },
    });
    render(<Panel page="checks" />);
    expect(text(await screen.findByTestId("otto-step-running"))).toBe("3 still running");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100); // the second read fails
    });
    await waitFor(() => expect(reads).toBe(2));
    expect(screen.getByTestId("otto-step-running")).not.toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100); // and the panel asks a third time
    });
    await waitFor(() => expect(screen.queryByTestId("otto-step-running")).toBeNull());
    expect(reads).toBe(3);
    vi.useRealTimers();
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
    // it is back for good: it is no longer remembered as closed
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem("evidence-lab-otto-tabs-101") ?? "{}").closed).toEqual({}));

    // and its thread reading again as it did when the tab was closed (a proof that failed, ran, and failed again)
    // does not hide it a second time (it has no dot then: that state was seen when the tab was closed)
    now = three();
    act(() => notifyChanged());
    await waitFor(() => expect(tabOf("fixing")?.getAttribute("data-dot")).toBe("false"));
    expect(tabs().map((t) => t.getAttribute("data-thread"))).toEqual(["testing", "fixing", "planning"]);
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

// ---------------------------------------------------------------- the Confirm step itself

describe("the Confirm step", () => {
  it("shows once: a decided suggestion that is listed on the page and in its thread opens the step only on the card that was pressed", async () => {
    const accepted: AssistantEntry = suggestion(decided(dependencyProposal, "accepted"));
    const fetchMock = await open(panel("migration/dependencies", { on_page: onPage([accepted]), tabs: [tab("planning", { so_far: [accepted] })] }));
    const onThePage = within(screen.getByTestId("otto-on-page")).getByTestId("otto-entry");
    const inTheThread = within(screen.getByTestId("otto-so-far")).getByTestId("otto-entry");
    fireEvent.click(button(inTheThread, "Undo"));
    expect(screen.getAllByTestId("otto-confirm")).toHaveLength(1);
    expect(within(inTheThread).getByTestId("otto-confirm")).not.toBeNull();
    expect(button(onThePage, "Undo")).not.toBeNull(); // the other card still shows its button
    fireEvent.click(button(onThePage, "Undo"));
    expect(screen.getAllByTestId("otto-confirm")).toHaveLength(1); // the step moved; there is never a second Confirm
    expect(within(onThePage).getByTestId("otto-confirm")).not.toBeNull();
    expect(calls(fetchMock)).toEqual([]);
  });

  it("names its fields by ids of their own, so two panels of one page never share one", async () => {
    await open(panel("checks", { on_page: onPage([suggestion(checkProposal)]) }));
    fireEvent.click(button(entry(checkProposal.id), "Reject"));
    const reason = screen.getByTestId("otto-reason");
    const name = screen.getByTestId("otto-name");
    expect(reason.id).not.toBe("");
    expect(reason.id).not.toBe(name.id);
    expect(document.querySelectorAll(`[id="${reason.id}"]`)).toHaveLength(1);
    expect(screen.getByLabelText(/Reason \(optional/)).toBe(reason);
  });

  it("takes the keyboard's place when it opens, and gives it back to the button on Cancel", async () => {
    await open(panel("checks", { on_page: onPage([suggestion(checkProposal)]) }));
    const reject = button(entry(checkProposal.id), "Reject");
    reject.focus();
    fireEvent.click(reject);
    expect(document.activeElement).toBe(screen.getByTestId("otto-confirm"));
    fireEvent.click(screen.getByTestId("otto-cancel-button"));
    await waitFor(() => expect(document.activeElement).toBe(button(entry(checkProposal.id), "Reject")));
    // and for a next step the same
    cleanup();
    const step = nextStep("next:run_all", "Run all", "Checks", { type: "run_all", plan_id: 1 });
    await open(panel("checks", { on_page: onPage([step]) }));
    fireEvent.click(button(entry(step.id), "Run all"));
    expect(document.activeElement).toBe(screen.getByTestId("otto-confirm"));
    fireEvent.click(screen.getByTestId("otto-cancel-button"));
    await waitFor(() => expect(document.activeElement).toBe(button(entry(step.id), "Run all")));
  });

  it("closes when a new read turns its button off: the card shows the button again, off, with the page's reason", async () => {
    const why = "Tests are still running. Wait until they have finished.";
    const off: OttoProposal = { ...checkProposal, buttons: checkProposal.buttons.map((b) => ({ ...b, can: false, blocked_reason: why })) };
    let now = panel("checks", { on_page: onPage([suggestion(checkProposal)]) });
    const fetchMock = await open(now, { [read("checks")]: () => ({ body: now }) });
    fireEvent.click(button(entry(checkProposal.id), "Accept"));
    expect(screen.getByTestId("otto-confirm")).not.toBeNull();
    now = panel("checks", { on_page: onPage([suggestion(off)]) });
    const { notifyChanged } = await import("../changes");
    act(() => notifyChanged());
    await waitFor(() => expect(screen.queryByTestId("otto-confirm")).toBeNull());
    const card = entry(checkProposal.id);
    expect(button(card, "Accept").disabled).toBe(true);
    expect(text(within(card).getByTestId("otto-blocked"))).toBe(why);
    expect(calls(fetchMock)).toEqual([]);
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

// ---------------------------------------------------------------- phase 6b: the text box

describe("the text box (phase 6b)", () => {
  const SAY = "POST /api/plans/1/assistant/messages";
  const box = () => screen.getByTestId("otto-box-text") as HTMLTextAreaElement;
  const type = (words: string) => fireEvent.change(box(), { target: { value: words } });
  const send = () => fireEvent.click(screen.getByTestId("otto-box-send"));
  const reply = () => screen.getByTestId("otto-reply");
  const LABEL = "Ask Otto, or tell it what to do";
  const checksBox = { label: LABEL, send: "Send", max: 500, chips: ["Show failed checks", "Run all", "What can you do?"], questions: [] as string[], kept: true, kept_note: null };

  it("sits at the foot of the panel with its label, Send and up to three chips; typing sends nothing", async () => {
    const fetchMock = await open(panel("checks", { box: checksBox }));
    expect(screen.getByLabelText(LABEL)).toBe(box());
    expect(screen.getAllByTestId("otto-chip").map((c) => text(c))).toEqual(["Show failed checks", "Run all", "What can you do?"]);
    expect((screen.getByTestId("otto-box-send") as HTMLButtonElement).disabled).toBe(true); // nothing typed yet
    type("show me failed checks");
    expect((screen.getByTestId("otto-box-send") as HTMLButtonElement).disabled).toBe(false);
    expect(calls(fetchMock)).toEqual([]);
    expect(screen.queryByTestId("otto-reply")).toBeNull();
    // it comes after what fits the page, and before the standing note
    expect(screen.getByTestId("otto-on-page").compareDocumentPosition(screen.getByTestId("otto-box")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByTestId("otto-box").compareDocumentPosition(screen.getByTestId("otto-note")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("moving around is done at once: the sentence is sent with the page and the open item, and the app goes where the answer says", async () => {
    const onGoTo = vi.fn();
    const where = goTo("checks", { result: "Failed" });
    const fetchMock = await open(
      panel("checks", { box: checksBox }),
      { [read("checks", "test-5")]: { body: panel("checks", { box: checksBox }) }, [SAY]: { body: answer("went", "Opened Checks, filtered to Failed: 2 checks.", { go: where, thread: "testing" }) } },
      { onGoTo, item: "test-5" },
    );
    type("show me failed checks");
    send();
    await waitFor(() => expect(onGoTo).toHaveBeenCalledWith(where));
    expect(calls(fetchMock)).toEqual([SAY]);
    expect(sent(fetchMock, SAY)?.body).toEqual({ text: "show me failed checks", page: "checks", item: "test-5" });
    expect(text(within(reply()).getByTestId("otto-reply-said"))).toBe("You said: show me failed checks");
    expect(text(within(reply()).getByTestId("otto-reply-text"))).toBe("Opened Checks, filtered to Failed: 2 checks.");
    expect(reply().getAttribute("data-kind")).toBe("went");
    expect(box().value).toBe(""); // the box is ready for the next sentence
    expect(screen.queryByTestId("otto-confirm")).toBeNull();
  });

  it("Enter sends, Shift and Enter does not, and a chip sends its own words", async () => {
    const fetchMock = await open(panel("checks", { box: checksBox }), { [SAY]: { body: answer("help", "On Checks you can tell Otto:") } });
    type("what can you do?");
    fireEvent.keyDown(box(), { key: "Enter", shiftKey: true });
    expect(calls(fetchMock)).toEqual([]);
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(calls(fetchMock)).toEqual([SAY]));
    fireEvent.click(screen.getAllByTestId("otto-chip")[1]!);
    await waitFor(() => expect(calls(fetchMock)).toEqual([SAY, SAY]));
    const bodies = fetchMock.mock.calls.filter(([url]) => String(url) === "/api/plans/1/assistant/messages").map(([, init]) => JSON.parse(String(init!.body)).text);
    expect(bodies).toEqual(["what can you do?", "Run all"]);
  });

  it("a decision comes back as the suggestion's card with its Confirm step open; only Confirm sends the page's own request", async () => {
    const card = suggestion(dependencyProposal);
    const fetchMock = await open(panel("checks", { box: checksBox }), {
      [SAY]: { body: answer("card", `Accept “${card.title}”, on Dependencies. Nothing happens until you press Confirm.`, { entry: card, open: { key: "accept", reason: null }, thread: "fixing" }) },
      [decide(dependencyProposal, "accept")]: { body: decided(dependencyProposal, "accepted") },
    });
    type("accept the java fix");
    send();
    const shown = await within(await screen.findByTestId("otto-reply")).findByTestId("otto-entry");
    expect(text(within(shown).getByTestId("otto-entry-title"))).toBe(card.title);
    expect(text(within(shown).getByTestId("otto-entry-where"))).toBe("On Dependencies"); // it names the proposal's page
    const step = within(shown).getByTestId("otto-confirm");
    expect(text(within(step).getByTestId("otto-confirm-names"))).toBe("This is the Accept button on Dependencies.");
    expect(calls(fetchMock)).toEqual([SAY]); // the sentence was kept; nothing was decided
    // Cancel leaves everything as it was, and the card stays with its buttons
    fireEvent.click(within(step).getByTestId("otto-cancel-button"));
    expect(calls(fetchMock)).toEqual([SAY]);
    fireEvent.click(button(within(reply()).getByTestId("otto-entry"), "Accept"));
    fireEvent.click(within(reply()).getByTestId("otto-confirm-button"));
    await waitFor(() => expect(calls(fetchMock)).toEqual([SAY, decide(dependencyProposal, "accept")]));
    expect(sent(fetchMock, decide(dependencyProposal, "accept"))?.body).toEqual({}); // exactly what the page's Accept sends (no reason)
    await waitFor(() => expect(within(reply()).queryByTestId("otto-entry")).toBeNull());
    expect(text(within(reply()).getByTestId("otto-reply-confirmed"))).toContain("Confirmed.");
  });

  it("a reason that rides along fills the reason box in the person's own words, and Confirm sends it", async () => {
    const card = suggestion(dependencyProposal);
    const why = "we stay on 17.0.2 until January";
    const fetchMock = await open(panel("checks", { box: checksBox }), {
      [SAY]: { body: answer("card", "Reject …", { entry: card, open: { key: "reject", reason: why }, thread: "fixing" }) },
      [decide(dependencyProposal, "reject")]: { body: decided(dependencyProposal, "rejected", why) },
    });
    type(`reject the java fix: ${why}`);
    send();
    const field = (await within(await screen.findByTestId("otto-reply")).findByTestId("otto-reason")) as HTMLInputElement;
    expect(field.value).toBe(why);
    fireEvent.click(within(reply()).getByTestId("otto-confirm-button"));
    await waitFor(() => expect(sent(fetchMock, decide(dependencyProposal, "reject"))?.body).toEqual({ reason: why }));
  });

  it("where several things fit it asks Which one? and sends the words of the one that is chosen; it never picks one itself", async () => {
    let asked = 0;
    const fetchMock = await open(panel("fixes", { box: checksBox }), {
      [SAY]: () => {
        asked += 1;
        return {
          body:
            asked === 1
              ? answer("which", "Which one?", { options: [{ label: "Update openjdk (on Dependencies)", say: "Accept Update openjdk" }, { label: "Range check (on Fixes)", say: "Accept Range check" }] })
              : answer("card", "Accept …", { entry: suggestion(fixProposal), open: { key: "accept", reason: null } }),
        };
      },
    });
    type("accept the fix");
    send();
    const options = await within(await screen.findByTestId("otto-reply")).findAllByTestId("otto-reply-option");
    expect(options.map((o) => text(o))).toEqual(["Update openjdk (on Dependencies)", "Range check (on Fixes)"]);
    expect(within(reply()).queryByTestId("otto-entry")).toBeNull();
    expect(calls(fetchMock)).toEqual([SAY]);
    fireEvent.click(options[1]!);
    await within(await screen.findByTestId("otto-reply")).findByTestId("otto-confirm");
    const said = fetchMock.mock.calls.filter(([url]) => String(url) === "/api/plans/1/assistant/messages").map(([, init]) => JSON.parse(String(init!.body)).text);
    expect(said).toEqual(["accept the fix", "Accept Range check"]);
  });

  it("where nothing fits it says so and lists what can be said here; an example goes into the box and is not sent", async () => {
    const can = [
      { say: "Show failed checks", about: "Opens a page with its table filtered.", kind: "go" as const },
      { say: "Run all", about: "The Run all button of Checks. It waits for Confirm.", kind: "do" as const },
    ];
    const fetchMock = await open(panel("checks", { box: checksBox }), { [SAY]: { body: answer("cannot", "I can't do that.", { can }) } });
    type("make me a sandwich");
    send();
    await waitFor(() => expect(text(within(reply()).getByTestId("otto-reply-text"))).toBe("I can't do that."));
    const examples = within(reply()).getAllByTestId("otto-reply-example");
    expect(examples.map((e) => text(e))).toEqual(["Show failed checks", "Run all"]);
    fireEvent.click(examples[1]!);
    expect(box().value).toBe("Run all");
    expect(calls(fetchMock)).toEqual([SAY]); // only the first sentence was sent
  });

  it("a button that is off comes back as its card with the page's own reason, and no Confirm step", async () => {
    const why = "This change is a proposal. Accept it first; accepting runs nothing.";
    const off = nextStep("next:connect", "Connect demo code", "Fixes", { type: "connect", plan_id: 1 }, { can: false, blocked_reason: why });
    await open(panel("fixes", { box: checksBox }), { [SAY]: { body: answer("cannot", why, { entry: off }) } });
    type("connect demo code");
    send();
    const shown = await within(await screen.findByTestId("otto-reply")).findByTestId("otto-entry");
    expect(button(shown, "Connect demo code").disabled).toBe(true);
    expect(text(within(shown).getByTestId("otto-blocked"))).toBe(why);
    expect(within(reply()).queryByTestId("otto-confirm")).toBeNull();
  });

  it("closes and opens a tab of the panel when told to, in this browser", async () => {
    let now = answer("tab", "Closed the Fixing tab.", { tab: { thread: "fixing", how: "close" } });
    const view = panel("checks", { box: checksBox, tabs: [tab("testing"), tab("fixing"), tab("planning")] });
    const fetchMock = await open(view, { [read("checks")]: () => ({ body: view }), [SAY]: () => ({ body: now }) });
    type("close the fixing tab");
    send();
    await waitFor(() => expect(tabs().map((t) => t.getAttribute("data-thread"))).toEqual(["testing", "planning"]));
    now = answer("tab", "Opened the Fixing tab.", { tab: { thread: "fixing", how: "open" } });
    type("open the fixing tab");
    send();
    await waitFor(() => expect(tabs().map((t) => t.getAttribute("data-thread"))).toEqual(["testing", "fixing", "planning"]));
    expect(tabOf("fixing").getAttribute("data-selected")).toBe("true");
    expect(calls(fetchMock)).toEqual([SAY, SAY]);
  });

  it("in a closed assessment the box still takes you places: the read is used, nothing is kept, and the box says so", async () => {
    const closedBox = { ...checksBox, kept: false, kept_note: "This assessment is closed. The text box can still take you places and answer the fixed questions. What you type is not kept." };
    const onGoTo = vi.fn();
    const ANSWER = `GET /api/assessments/101/assistant/answer?${new URLSearchParams({ text: "open evidence", page: "checks" }).toString()}`;
    const fetchMock = await open(panel("checks", { box: closedBox }), { [ANSWER]: { body: answer("went", "Opened Evidence.", { go: goTo("evidence") }) } }, { onGoTo, closed: true });
    expect(text(screen.getByTestId("otto-box-note"))).toContain("What you type is not kept.");
    type("open evidence");
    expect((screen.getByTestId("otto-box-send") as HTMLButtonElement).disabled).toBe(false); // Send stays on in a closed assessment
    send();
    await waitFor(() => expect(onGoTo).toHaveBeenCalledWith(goTo("evidence")));
    expect(calls(fetchMock)).toEqual([ANSWER]);
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("what was said is listed in its thread so far as You said, with Otto's line and the way to where it led", async () => {
    const said: AssistantEntry = {
      id: "said:3", kind: "said", what: "said:testing", thread: "testing", mark: "You said", title: "show me failed checks",
      text: "Opened Checks, filtered to Failed: 2 checks.", at: "2026-11-19T06:00:00Z", badge: null, where: null,
      links: [{ label: "Open where it led", link: { page: "checks", item: null, group: null } }], proposal: null, decisions: [], step: null, open_item: false,
    };
    await open(panel("checks", { box: checksBox, tabs: [tab("testing", { so_far: [said] })] }));
    const line = within(screen.getByTestId("otto-so-far")).getByTestId("otto-entry");
    expect(text(within(line).getByTestId("otto-entry-mark"))).toBe("You said");
    expect(text(within(line).getByTestId("otto-entry-title"))).toBe("show me failed checks");
    expect(text(within(line).getByTestId("otto-entry-text"))).toBe("Opened Checks, filtered to Failed: 2 checks.");
    expect(within(line).getByTestId("otto-entry-link").getAttribute("href")).toBe("#/a/101/checks");
    expect(within(line).queryAllByRole("button")).toHaveLength(0); // a record of what was said: nothing to press
  });

  it("a refusal of the server is shown under the box in its own words, and nothing else happens", async () => {
    const onGoTo = vi.fn();
    await open(panel("checks", { box: checksBox }), { [SAY]: { status: 422, body: { error: { message: "Type where to go or what to do.", line: null, field: "text" } } } }, { onGoTo });
    type("   ?   ");
    send();
    expect(text(await within(screen.getByTestId("otto-box")).findByRole("alert"))).toBe("Type where to go or what to do.");
    expect(onGoTo).not.toHaveBeenCalled();
    expect(screen.queryByTestId("otto-reply")).toBeNull();
  });
});

// ---------------------------------------------------------------- the fixed questions (phase 6c, first half)

describe("the fixed questions (phase 6c)", () => {
  const SAY = "POST /api/plans/1/assistant/messages";
  const LABEL = "Ask Otto, or tell it what to do";
  const QUESTIONS = ["Why did this check fail?", "What should I do next?", "What is this page for?"];
  const evidenceBox = { label: LABEL, send: "Send", max: 500, chips: ["Show failed results", "What can you do?"], questions: QUESTIONS, kept: true, kept_note: null };
  const reply = () => screen.getByTestId("otto-reply");
  const evidenceOf = { page: "evidence", item: "test-6", group: null };
  const why = answer("answer", "Why did this check fail? Advisory check: Blank signature accepted (CVE-2022-21449)", {
    thread: "testing",
    question: "Why did this check fail?",
    label: "From this assessment's records",
    facts: [
      { text: "“Advisory check: Blank signature accepted (CVE-2022-21449)” reads Failed on acme-sign 1.4.2.", link: evidenceOf, label: "See the evidence" },
      { text: "acme-sign 1.4.2 got 2 of the 64 published cases for advisory CVE-2022-21449 wrong.", link: evidenceOf, label: "See the evidence" },
      { text: "This check was proposed from the advisory “Blank signature accepted (CVE-2022-21449)”, in test pack 2026.11.1.", link: { page: "advisories", item: "CVE-2022-21449", group: null }, label: "Open the advisory" },
      { text: "Accept waits for your Confirm, here and on its page.", link: null, label: null },
    ],
  });

  it("the questions that fit show as their own row above the examples; looking at them asks nothing", async () => {
    const fetchMock = await open(panel("evidence", { box: evidenceBox }));
    expect(screen.getAllByTestId("otto-question").map((q) => text(q))).toEqual(QUESTIONS);
    expect(screen.getAllByTestId("otto-chip").map((c) => text(c))).toEqual(["Show failed results", "What can you do?"]);
    expect(screen.getByTestId("otto-questions").compareDocumentPosition(screen.getByTestId("otto-chips")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(calls(fetchMock)).toEqual([]);
    expect(screen.queryByTestId("otto-reply")).toBeNull();
  });

  it("with no question that fits there is no row of questions", async () => {
    await open(panel("evidence", { box: { ...evidenceBox, questions: [] } }));
    expect(screen.queryByTestId("otto-questions")).toBeNull();
    expect(screen.getAllByTestId("otto-chip")).toHaveLength(2);
  });

  it("a click asks the question with the page and the open item; the answer is a list of facts, each with the link to where it is shown, and nothing to press", async () => {
    const onGoTo = vi.fn();
    const fetchMock = await open(
      panel("evidence", { box: evidenceBox }),
      { [read("evidence", "test-6")]: { body: panel("evidence", { box: evidenceBox }) }, [SAY]: { body: why } },
      { item: "test-6", onGoTo },
    );
    fireEvent.click(screen.getAllByTestId("otto-question")[0]!);
    const shown = await screen.findByTestId("otto-reply");
    expect(calls(fetchMock)).toEqual([SAY]);
    expect(sent(fetchMock, SAY)?.body).toEqual({ text: "Why did this check fail?", page: "evidence", item: "test-6" });
    expect(shown.getAttribute("data-kind")).toBe("answer");
    expect(text(within(shown).getByTestId("otto-reply-said"))).toBe("You said: Why did this check fail?");
    expect(text(within(shown).getByTestId("otto-reply-text"))).toBe(why.text);
    // where the answer is from, said once, above the facts
    expect(text(within(shown).getByTestId("otto-reply-label"))).toBe("From this assessment's records");
    const facts = within(shown).getAllByTestId("otto-fact");
    expect(facts).toHaveLength(4);
    expect(text(facts[0]!)).toContain("reads Failed on acme-sign 1.4.2.");
    const links = within(shown).getAllByTestId("otto-fact-link");
    expect(links.map((l) => [text(l), l.getAttribute("href")])).toEqual([
      ["See the evidence", "#/a/101/evidence?item=test-6"],
      ["See the evidence", "#/a/101/evidence?item=test-6"],
      ["Open the advisory", "#/a/101/advisories?item=CVE-2022-21449"],
    ]);
    expect(within(facts[3]!).queryByRole("link")).toBeNull(); // a fact with nowhere to open has no link
    // an answer is facts only: no card, no Confirm step, no button in it, and the app went nowhere
    expect(within(shown).queryAllByRole("button")).toHaveLength(0);
    expect(within(shown).queryByTestId("otto-entry")).toBeNull();
    expect(screen.queryByTestId("otto-confirm")).toBeNull();
    expect(onGoTo).not.toHaveBeenCalled();
  });

  it("where several fit it asks which one; the option asks about that one, and its answer replaces the question", async () => {
    const which = answer("which", "Which one?", {
      thread: "testing",
      options: [
        { label: "Old TLS versions (Failed)", say: "Why did Old TLS versions fail?" },
        { label: "Advisory check: Blank signature accepted (CVE-2022-21449) (Failed)", say: "Why did Advisory check Blank signature accepted (CVE-2022-21449) fail?" },
      ],
    });
    let n = 0;
    const fetchMock = await open(panel("evidence", { box: evidenceBox }), { [SAY]: () => ({ body: n++ === 0 ? which : why }) });
    fireEvent.click(screen.getAllByTestId("otto-question")[0]!);
    const options = await screen.findAllByTestId("otto-reply-option");
    expect(options.map((o) => text(o))).toEqual(["Old TLS versions (Failed)", "Advisory check: Blank signature accepted (CVE-2022-21449) (Failed)"]);
    expect(within(reply()).queryByTestId("otto-facts")).toBeNull();
    fireEvent.click(options[1]!);
    await waitFor(() => expect(within(reply()).getAllByTestId("otto-fact")).toHaveLength(4));
    const said = fetchMock.mock.calls.filter(([url]) => String(url) === "/api/plans/1/assistant/messages").map(([, init]) => JSON.parse(String(init!.body)).text);
    expect(said).toEqual(["Why did this check fail?", "Why did Advisory check Blank signature accepted (CVE-2022-21449) fail?"]);
    expect(within(reply()).queryByTestId("otto-reply-options")).toBeNull();
  });

  it("a question can be typed in other words too: it is sent as typed", async () => {
    const fetchMock = await open(panel("evidence", { box: evidenceBox }), { [SAY]: { body: why } });
    fireEvent.change(screen.getByTestId("otto-box-text"), { target: { value: "why did the blank signature check fail?" } });
    fireEvent.click(screen.getByTestId("otto-box-send"));
    await screen.findByTestId("otto-facts");
    expect(sent(fetchMock, SAY)?.body).toEqual({ text: "why did the blank signature check fail?", page: "evidence", item: null });
  });

  it("a closed assessment still answers: the read is used and nothing is kept", async () => {
    const closedBox = { ...evidenceBox, kept: false, kept_note: "This assessment is closed. The text box can still take you places and answer the fixed questions. What you type is not kept." };
    const ANSWER = `GET /api/assessments/101/assistant/answer?${new URLSearchParams({ text: "Why did this check fail?", page: "evidence" }).toString()}`;
    const fetchMock = await open(panel("evidence", { box: closedBox }), { [ANSWER]: { body: why } }, { closed: true });
    const first = screen.getAllByTestId("otto-question")[0] as HTMLButtonElement;
    expect(first.disabled).toBe(false); // asking is a read: it stays on in a closed assessment
    fireEvent.click(first);
    await screen.findByTestId("otto-facts");
    expect(calls(fetchMock)).toEqual([ANSWER]);
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("a kept answer stands in its thread so far as You said, with the facts it had then and nothing to press", async () => {
    const kept: AssistantEntry = {
      id: "said:4", kind: "said", what: "said:testing", thread: "testing", mark: "You said", title: "why did the blank signature check fail?",
      text: why.text, at: "2026-11-19T06:00:00Z", badge: null, where: null, links: [], proposal: null, decisions: [], step: null, open_item: false,
      facts: why.facts,
    };
    await open(panel("evidence", { box: evidenceBox, tabs: [tab("testing", { so_far: [kept] })] }));
    const line = within(screen.getByTestId("otto-so-far")).getByTestId("otto-entry");
    expect(text(within(line).getByTestId("otto-entry-mark"))).toBe("You said");
    expect(within(line).getAllByTestId("otto-fact")).toHaveLength(4);
    expect(within(line).getAllByTestId("otto-fact-link")[2]!.getAttribute("href")).toBe("#/a/101/advisories?item=CVE-2022-21449");
    expect(within(line).queryAllByRole("button")).toHaveLength(0);
  });
});

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
