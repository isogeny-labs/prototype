import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DependenciesView as View, DependencyAdvisory, DependencyRow, OttoProposal } from "../api";
import { DependenciesView } from "../components/dependencies/DependenciesView";
import { LinkProvider } from "../components/related";
import { ReadOnlyProvider } from "../readOnly";
import { DEPENDENCIES_DEMO } from "./dependenciesFixtures";
import { calls, mockApi, text } from "./fixtures";
import { acceptedProposal, proposal, rejectedProposal } from "./proposalFixtures";

/** Phase 5c: on Dependencies, a library that a published advisory names says so ("Named by advisory X: measured
 * affected / measured not affected / not yet checked") with the way to the proposed fix, and Otto's proposal to change
 * its status is accepted or rejected like every other. Every word below stands in for the backend's. */

const GET = "GET /api/import/1/dependencies";
const ID = "dep-3f2a1b4c5d6e";
const decide = (decision: string) => `POST /api/plans/1/otto/proposals/${ID}/${decision}`;
const ERROR = (message: string) => ({ status: 409, body: { error: { message, line: null, field: null } } });

const ECDSA = "python-ecdsa 0.13.2";
const JAVA = "openjdk 17.0.2";
const ELLIPTIC = "elliptic 6.5.6";

const NOT_CHECKED: DependencyAdvisory = {
  id: "CVE-2019-14859",
  name: "Badly encoded signature accepted",
  line: "Named by advisory CVE-2019-14859: not yet checked",
  state: { key: "not_checked", label: "not yet checked", tone: "neutral" },
  detail:
    "No check has run on python-ecdsa 0.13.2 here. An advisory check runs on the signing programs your scanner file names, and this " +
    "library is in the dependency list only.",
  fixed_line: "Its publisher names 0.13.3 as the fixed version; your list has 0.13.2.",
  advisory_link: { page: "advisories", item: "CVE-2019-14859" },
  evidence_link: null,
  fix_link: { page: "advisories", item: "CVE-2019-14859" },
  fix_label: "See the proposed fix",
};
/** A second advisory about the same library that has no test, so the pack carries no fix for it. */
const NO_TEST: DependencyAdvisory = {
  id: "CVE-2019-14853",
  name: "Malformed signature raises unexpected error",
  line: "Named by advisory CVE-2019-14853: not yet checked",
  state: { key: "not_checked", label: "not yet checked", tone: "neutral" },
  detail: "This advisory has no test yet, so nothing can be measured.",
  fixed_line: "Its publisher names 0.13.3 as the fixed version; your list has 0.13.2.",
  advisory_link: { page: "advisories", item: "CVE-2019-14853" },
  evidence_link: null,
  fix_link: null,
  fix_label: null,
};
const AFFECTED: DependencyAdvisory = {
  id: "CVE-2022-21449",
  name: "Missing ECDSA signature range check",
  line: "Named by advisory CVE-2022-21449: measured affected",
  state: { key: "affected", label: "measured affected", tone: "fail" },
  detail: "The advisory check failed on openjdk 17.0.2 in this assessment.",
  fixed_line: "Its publisher names 17.0.3 as the fixed version; your list has 17.0.2.",
  advisory_link: { page: "advisories", item: "CVE-2022-21449" },
  evidence_link: { page: "evidence", item: "test-12" },
  fix_link: { page: "fixes", item: "fix-advisory-cases-12" },
  fix_label: "See the proposed fix",
};
const NOT_AFFECTED: DependencyAdvisory = {
  id: "CVE-2024-42460",
  name: "Wrongly encoded signature accepted",
  line: "Named by advisory CVE-2024-42460: measured not affected",
  state: { key: "not_affected", label: "measured not affected", tone: "pass" },
  detail: "The advisory check passed on elliptic 6.5.6 in this assessment: the published cases chosen for this advisory got the right answer.",
  fixed_line: "Its publisher names 6.5.7 as the fixed version; your list has 6.5.6.",
  advisory_link: { page: "advisories", item: "CVE-2024-42460" },
  evidence_link: { page: "evidence", item: "test-14" },
  fix_link: { page: "advisories", item: "CVE-2024-42460" },
  fix_label: "See the proposed fix",
};

const TITLE = "Update python-ecdsa 0.13.2 to 0.13.3 before the move";
const DEP: Partial<OttoProposal> = {
  id: ID,
  kind: "dependency",
  kind_label: "dependency update",
  title: TITLE,
  why:
    "Your dependency list has python-ecdsa 0.13.2. Advisory CVE-2019-14859 (Badly encoded signature accepted) is about python-ecdsa, " +
    "and its publisher names 0.13.3 as the fixed version.",
  why_label: "Why Otto proposes it",
  lines: [
    "Update python-ecdsa to version 0.13.3, whose DER reader has checks that the 0.13.2 reader lacks.",
    "Proven on public copies: Passed. 0.13.2 fails the advisory check; 0.13.3 passes.",
    "Otto proposes to mark this library “update first”. Accepting changes nothing on any system and runs nothing.",
  ],
  link: { page: "migration/dependencies", item: "row-1" },
};
const proposed = proposal({ ...DEP, note: "Accept marks this library “update first”. It runs nothing and changes nothing on any system." });
const EFFECT = "Marked “update first”: python-ecdsa 0.13.2 to 0.13.3.";
const accepted = acceptedProposal({
  ...DEP,
  status: { key: "accepted", word: "Accepted", tone: "pass" },
  effect: EFFECT,
  note: "Undo takes the mark off again.",
});
const rejected = rejectedProposal("We vendor our own build", DEP);
const STATUS = { label: "Update first", tone: "warn" as const, lines: [`${EFFECT} Accepted by You on 18 November 2026, 10:02 UTC.`] };

/** The demo list with a change to the rows named by their labels. */
function withRows(changes: Record<string, Partial<DependencyRow>>, base: View = DEPENDENCIES_DEMO): View {
  return { ...base, groups: base.groups.map((g) => ({ ...g, rows: g.rows.map((r) => (changes[r.label] ? { ...r, ...changes[r.label] } : r)) })) };
}

const NAMED = withRows({
  [ECDSA]: { advisories: [NOT_CHECKED, NO_TEST], otto_proposals: [proposed], otto_status: null },
  [JAVA]: { advisories: [AFFECTED] },
  [ELLIPTIC]: { advisories: [NOT_AFFECTED] },
});
const AFTER_ACCEPT = withRows({ [ECDSA]: { advisories: [NOT_CHECKED, NO_TEST], otto_proposals: [accepted], otto_status: STATUS } });
const AFTER_REJECT = withRows({ [ECDSA]: { advisories: [NOT_CHECKED, NO_TEST], otto_proposals: [rejected], otto_status: null } });

afterEach(() => vi.restoreAllMocks());

/** Opens the Dependencies view inside an assessment (so a link has an address). `views` are the answers of the page's
 * own GET, in order (the last one repeats). */
async function open(views: View[], routes: Parameters<typeof mockApi>[0] = {}, readOnly = false) {
  let n = 0;
  const fetchMock = mockApi({ [GET]: () => ({ body: views[Math.min(n++, views.length - 1)] }), ...routes });
  const onChanged = vi.fn();
  render(
    <ReadOnlyProvider readOnly={readOnly}>
      <LinkProvider assessmentId={101} planId={null}>
        <DependenciesView importId={1} onViewFix={vi.fn()} onChanged={onChanged} />
      </LinkProvider>
    </ReadOnlyProvider>,
  );
  await screen.findByTestId("dependencies-subline");
  return { fetchMock, onChanged };
}

const rows = () => screen.getAllByTestId("dependency-row");
const row = (label: string) => rows().find((r) => r.querySelector("p.font-mono")?.textContent === label)!;
const panel = () => within(screen.getByTestId("detail-panel"));
/** Opens a library's row (unless it is already open) and gives back the detail panel's queries. */
const detail = (label: string) => {
  const r = row(label);
  if (r.getAttribute("aria-selected") !== "true") fireEvent.click(r);
  return panel();
};
const href = (el: HTMLElement) => el.getAttribute("href");
const sent = (fetchMock: ReturnType<typeof mockApi>, key: string) => {
  const found = fetchMock.mock.calls.filter(([url, init]) => `${init?.method ?? "GET"} ${String(url)}` === key).at(-1);
  return JSON.parse(String(found?.[1]?.body));
};

describe("Dependencies: libraries named by an advisory", () => {
  it("says it in the table row, one line for each advisory, with the state as the chip's tone and the way to the proposed fix", async () => {
    await open([NAMED]);
    const ecdsa = within(row(ECDSA)).getAllByTestId("advisory-marker");
    expect(ecdsa.map((m) => text(m))).toEqual(["Named by advisory CVE-2019-14859: not yet checkedSee the proposed fix", "Named by advisory CVE-2019-14853: not yet checked"]);
    expect(ecdsa.map((m) => m.getAttribute("data-state"))).toEqual(["not_checked", "not_checked"]);
    const java = within(row(JAVA)).getByTestId("advisory-marker");
    expect(text(java)).toBe("Named by advisory CVE-2022-21449: measured affectedSee the proposed fix");
    expect(java.getAttribute("data-state")).toBe("affected");
    expect(java.querySelector("[data-tone]")?.getAttribute("data-tone")).toBe("fail");
    // where a check failed here, the proposed fix is the entry in Fixes; otherwise it is on the advisory
    expect(href(within(java).getByTestId("advisory-marker-fix"))).toBe("#/a/101/fixes?item=fix-advisory-cases-12");
    expect(href(within(ecdsa[0]!).getByTestId("advisory-marker-fix"))).toBe("#/a/101/advisories?item=CVE-2019-14859");
    const elliptic = within(row(ELLIPTIC)).getByTestId("advisory-marker");
    expect(text(elliptic)).toContain("Named by advisory CVE-2024-42460: measured not affected");
    expect(elliptic.querySelector("[data-tone]")?.getAttribute("data-tone")).toBe("pass");
    // an advisory with no test has no fix to point to
    expect(within(ecdsa[1]!).queryByTestId("advisory-marker-fix")).toBeNull();
    // Otto's proposal for the library shows in the row too: its tag and where it stands
    expect(text(within(row(ECDSA)).getByTestId("proposal-marker"))).toBe("From OttoProposed");
    expect(within(row(JAVA)).queryByTestId("proposal-marker")).toBeNull();
  });

  it("a click on the row's link to the fix does not also open the row", async () => {
    await open([NAMED]);
    fireEvent.click(within(row(JAVA)).getByTestId("advisory-marker-fix"));
    expect(screen.queryByTestId("dependency-detail")).toBeNull();
    // ... while a click on the line itself opens the row like any other part of it
    fireEvent.click(within(row(JAVA)).getByTestId("advisory-marker"));
    expect(screen.getByTestId("dependency-detail").getAttribute("data-row")).toBe("row-4");
  });

  it("shows the three states in the library's panel, each with its sentence, the fixed version and its links", async () => {
    await open([NAMED]);
    const affected = within(detail(JAVA).getByTestId("dependency-advisory"));
    const li = detail(JAVA).getByTestId("dependency-advisory");
    expect(li.getAttribute("data-advisory")).toBe("CVE-2022-21449");
    expect(li.getAttribute("data-state")).toBe("affected");
    expect(text(affected.getByTestId("dependency-advisory-line"))).toBe("Named by advisory CVE-2022-21449: measured affected");
    expect(affected.getByTestId("dependency-advisory-line").getAttribute("data-tone")).toBe("fail");
    expect(text(affected.getByTestId("dependency-advisory-detail"))).toBe(AFFECTED.detail);
    expect(text(affected.getByTestId("dependency-advisory-fixed"))).toBe(AFFECTED.fixed_line);
    expect(text(affected.getByTestId("dependency-advisory-link"))).toBe("CVE-2022-21449");
    expect(href(affected.getByTestId("dependency-advisory-link"))).toBe("#/a/101/advisories?item=CVE-2022-21449");
    expect(text(affected.getByTestId("dependency-advisory-evidence"))).toBe("See the evidence");
    expect(href(affected.getByTestId("dependency-advisory-evidence"))).toBe("#/a/101/evidence?item=test-12");
    expect(text(affected.getByTestId("dependency-advisory-fix"))).toBe("See the proposed fix");
    expect(href(affected.getByTestId("dependency-advisory-fix"))).toBe("#/a/101/fixes?item=fix-advisory-cases-12");

    const passed = detail(ELLIPTIC).getByTestId("dependency-advisory");
    expect(passed.getAttribute("data-state")).toBe("not_affected");
    expect(within(passed).getByTestId("dependency-advisory-line").getAttribute("data-tone")).toBe("pass");
    expect(text(within(passed).getByTestId("dependency-advisory-detail"))).toBe(NOT_AFFECTED.detail);
    expect(href(within(passed).getByTestId("dependency-advisory-evidence"))).toBe("#/a/101/evidence?item=test-14");

    const named = detail(ECDSA).getAllByTestId("dependency-advisory");
    expect(named.map((n) => n.getAttribute("data-advisory"))).toEqual(["CVE-2019-14859", "CVE-2019-14853"]);
    expect(named.map((n) => n.getAttribute("data-state"))).toEqual(["not_checked", "not_checked"]);
    expect(text(within(named[0]!).getByTestId("dependency-advisory-detail"))).toBe(NOT_CHECKED.detail);
    // not checked here: no evidence to see; the fix is the one on the advisory
    expect(within(named[0]!).queryByTestId("dependency-advisory-evidence")).toBeNull();
    expect(href(within(named[0]!).getByTestId("dependency-advisory-fix"))).toBe("#/a/101/advisories?item=CVE-2019-14859");
    // no test, so no fix is offered: the line and the advisory's link only
    expect(text(within(named[1]!).getByTestId("dependency-advisory-detail"))).toBe("This advisory has no test yet, so nothing can be measured.");
    expect(within(named[1]!).queryByTestId("dependency-advisory-fix")).toBeNull();
    expect(href(within(named[1]!).getByTestId("dependency-advisory-link"))).toBe("#/a/101/advisories?item=CVE-2019-14853");
  });

  it("words no result of its own: nothing is called secure or scored", async () => {
    await open([NAMED]);
    detail(JAVA);
    expect(document.body.textContent).not.toMatch(/score|severity|critical/i);
  });
});

describe("Dependencies: Otto's proposal to change a library's status", () => {
  it("shows the proposal in the library's panel, and opening the page and the row sends the one GET and nothing else", async () => {
    const { fetchMock, onChanged } = await open([NAMED]);
    const card = within(detail(ECDSA).getByTestId("otto-proposal"));
    expect(detail(ECDSA).getByTestId("otto-proposal").getAttribute("data-kind")).toBe("dependency");
    expect(text(card.getByTestId("proposal-label"))).toBe("From Otto");
    expect(text(card.getByTestId("proposal-status"))).toBe("Proposed");
    expect(text(card.getByTestId("proposal-title"))).toBe(TITLE);
    expect(text(card.getByTestId("proposal-note"))).toContain("It runs nothing and changes nothing on any system.");
    expect((card.getByTestId("proposal-accept") as HTMLButtonElement).disabled).toBe(false);
    expect((card.getByTestId("proposal-reject") as HTMLButtonElement).disabled).toBe(false);
    expect(detail(ECDSA).queryByTestId("dependency-otto-status")).toBeNull();
    // nothing runs without a click: no measurement, no tie, no decision
    expect(calls(fetchMock)).toEqual([GET]);
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("Accept sends one POST to the decide route, then reads the dependencies view again; the library then carries the status", async () => {
    const { fetchMock, onChanged } = await open([NAMED, AFTER_ACCEPT], { [decide("accept")]: { body: accepted } });
    fireEvent.click(detail(ECDSA).getByTestId("proposal-accept"));
    await waitFor(() => expect(text(panel().getByTestId("proposal-status"))).toBe("Accepted"));
    expect(calls(fetchMock)).toEqual([GET, decide("accept"), GET]);
    expect(sent(fetchMock, decide("accept"))).toEqual({});
    const status = panel().getByTestId("dependency-otto-status");
    expect(text(status)).toBe(`Update first${STATUS.lines[0]}`);
    expect(status.querySelector("[data-tone]")?.getAttribute("data-tone")).toBe("warn");
    expect(text(panel().getByTestId("proposal-effect"))).toBe(EFFECT);
    expect(panel().queryByTestId("proposal-accept")).toBeNull();
    expect((panel().getByTestId("proposal-undo") as HTMLButtonElement).disabled).toBe(false);
    // the row in the table says it too
    expect(text(within(row(ECDSA)).getByTestId("otto-status-marker"))).toBe("Update first");
    expect(text(within(row(ECDSA)).getByTestId("proposal-marker"))).toBe("From OttoAccepted");
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it("Reject asks for a reason, sends it, and the proposal stays as Not added with that reason", async () => {
    const { fetchMock } = await open([NAMED, AFTER_REJECT], { [decide("reject")]: { body: rejected } });
    fireEvent.click(detail(ECDSA).getByTestId("proposal-reject"));
    expect(calls(fetchMock)).toEqual([GET]);
    fireEvent.change(screen.getByTestId("proposal-reject-reason"), { target: { value: "We vendor our own build" } });
    fireEvent.click(screen.getByTestId("proposal-reject-confirm"));
    await waitFor(() => expect(text(panel().getByTestId("proposal-status"))).toBe("Not added (We vendor our own build)"));
    expect(calls(fetchMock)).toEqual([GET, decide("reject"), GET]);
    expect(sent(fetchMock, decide("reject"))).toEqual({ reason: "We vendor our own build" });
    expect(text(panel().getByTestId("proposal-decided"))).toContain("Reason: We vendor our own build");
    // not deleted: still there, with Reconsider, and the library carries no status
    expect(text(panel().getByTestId("proposal-title"))).toBe(TITLE);
    expect((panel().getByTestId("proposal-reconsider") as HTMLButtonElement).disabled).toBe(false);
    expect(panel().queryByTestId("dependency-otto-status")).toBeNull();
    expect(text(within(row(ECDSA)).getByTestId("proposal-marker"))).toBe("From OttoNot added (We vendor our own build)");
  });

  it("Undo of an accept sends one POST, and the status is gone when the view is read again", async () => {
    const { fetchMock } = await open([AFTER_ACCEPT, NAMED], { [decide("undo")]: { body: proposed } });
    expect(text(detail(ECDSA).getByTestId("dependency-otto-status"))).toContain("Update first");
    fireEvent.click(panel().getByTestId("proposal-undo"));
    await waitFor(() => expect(text(panel().getByTestId("proposal-status"))).toBe("Proposed"));
    expect(calls(fetchMock)).toEqual([GET, decide("undo"), GET]);
    expect(sent(fetchMock, decide("undo"))).toEqual({});
    expect(panel().queryByTestId("dependency-otto-status")).toBeNull();
    expect(within(row(ECDSA)).queryByTestId("otto-status-marker")).toBeNull();
  });

  it("a decision the backend refuses is shown in its words, and the view is not read again", async () => {
    const { fetchMock } = await open([NAMED], { [decide("accept")]: ERROR("This assessment is closed. Start a new one to continue.") });
    fireEvent.click(detail(ECDSA).getByTestId("proposal-accept"));
    await waitFor(() => expect(text(panel().getByTestId("otto-proposal"))).toContain("This assessment is closed. Start a new one to continue."));
    expect(calls(fetchMock)).toEqual([GET, decide("accept")]);
    expect(text(panel().getByTestId("proposal-status"))).toBe("Proposed");
  });

  it("in a closed assessment the decision buttons are off", async () => {
    const { fetchMock } = await open([NAMED], {}, true);
    const card = within(detail(ECDSA).getByTestId("otto-proposal"));
    expect((card.getByTestId("proposal-accept") as HTMLButtonElement).disabled).toBe(true);
    expect((card.getByTestId("proposal-reject") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(card.getByTestId("proposal-accept"));
    expect(calls(fetchMock)).toEqual([GET]);
  });
});

describe("Dependencies: a system's box", () => {
  const SERVER = "server:localhost:8443";
  const LINE = "Marked “update first”: to 3.5.0. Accepted by You on 18 November 2026, 10:02 UTC.";
  const withLines: View = { ...DEPENDENCIES_DEMO, systems: DEPENDENCIES_DEMO.systems.map((s) => (s.key === SERVER ? { ...s, otto_lines: [LINE] } : s)) };
  const box = (key: string) => screen.getAllByTestId("dependency-system").find((b) => b.getAttribute("data-system") === key)!;

  it("lists what a person accepted from Otto under the blockers, tagged From Otto, and never among them", async () => {
    await open([withLines]);
    const server = within(box(SERVER));
    const lines = server.getAllByTestId("system-otto-line");
    expect(lines.map((l) => text(l))).toEqual([`From Otto${LINE}`]);
    expect(text(within(lines[0]!).getByTestId("system-otto-line-label"))).toBe("From Otto");
    // the blocker lines are exactly the view's, as before
    const blockers = server.getAllByTestId("blocker-line");
    const sentLines = DEPENDENCIES_DEMO.systems.find((s) => s.key === SERVER)!.blocker_lines;
    expect(blockers).toHaveLength(sentLines.length);
    blockers.forEach((b, i) => expect(text(b)).toContain(sentLines[i]!.text));
    for (const b of blockers) expect(text(b)).not.toContain("From Otto");
    // ... and Otto's list comes after them
    expect(Boolean(blockers.at(-1)!.compareDocumentPosition(lines[0]!) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
    // a system with none has no such list
    expect(within(box("software:lib-acme-sign")).queryByTestId("system-otto-lines")).toBeNull();
  });
});

describe("Dependencies: a view without the new fields", () => {
  it("renders exactly as before: no advisory line, no proposal, no status, no Otto tag", async () => {
    const { fetchMock } = await open([DEPENDENCIES_DEMO]);
    expect(screen.queryAllByTestId("dependency-otto-marker")).toHaveLength(0);
    expect(screen.queryAllByTestId("system-otto-line")).toHaveLength(0);
    detail(ECDSA);
    expect(panel().queryByTestId("dependency-otto")).toBeNull();
    expect(panel().queryByTestId("otto-proposal")).toBeNull();
    expect(document.body.textContent).not.toContain("From Otto");
    expect(document.body.textContent).not.toContain("Named by advisory");
    expect(calls(fetchMock)).toEqual([GET]);
  });

  it("empty lists and a null status draw nothing either", async () => {
    await open([withRows({ [ECDSA]: { advisories: [], otto_proposals: [], otto_status: null } })]);
    expect(within(row(ECDSA)).queryByTestId("dependency-otto-marker")).toBeNull();
    expect(detail(ECDSA).queryByTestId("dependency-otto")).toBeNull();
  });
});
