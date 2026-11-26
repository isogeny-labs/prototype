import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DecisionsPage } from "../components/evidence/DecisionsPage";
import { EvidenceFilesPage } from "../components/evidence/EvidenceFilesPage";
import { HistoryFold, HistoryOfPage } from "../components/evidence/HistoryFold";
import { TimelinePage } from "../components/evidence/TimelinePage";
import { dayWords } from "../components/evidence/parts";
import { LinkProvider } from "../components/related";
import { calls, mockApi, text } from "./fixtures";
import {
  decisionsView,
  evidenceFilesView,
  evidenceFilesWithOne,
  runAllEntry,
  testHistory,
  timelineView,
  verifyEntry,
} from "./recordFixtures";

// The design refactor (26 November 2026): Evidence as the full record. Four views and a history in every panel. Every
// one of them only reads: these tests hold each to the words of the record and to sending nothing but its own read.

const ZONE = encodeURIComponent(Intl.DateTimeFormat().resolvedOptions().timeZone);
const TIMELINE = `GET /api/plans/1/timeline?tz=${ZONE}`;
const timelineOf = (query: string) => `GET /api/plans/1/timeline?${query}&tz=${ZONE}`;
const DECISIONS = `GET /api/plans/1/decisions?tz=${ZONE}`;
const FILES = "GET /api/plans/1/evidence-files";
const entryOf = (id: string) => `GET /api/plans/1/timeline/${id}`;
const posts = (fetchMock: ReturnType<typeof mockApi>) => calls(fetchMock).filter((c) => !c.startsWith("GET"));
const entries = timelineView.days.flatMap((d) => d.entries);
const runAll = entries.find((e) => e.id === runAllEntry.entry.id)!;

beforeEach(() => {
  window.localStorage.clear();
});

function inApp(ui: React.ReactNode) {
  return render(
    <LinkProvider assessmentId={101} planId={1}>
      {ui}
    </LinkProvider>,
  );
}

describe("Evidence, the Timeline", () => {
  async function open(
    routes: Parameters<typeof mockApi>[0] = {},
    props: Partial<Parameters<typeof TimelinePage>[0]> = {},
  ) {
    const fetchMock = mockApi({ [TIMELINE]: { body: timelineView }, ...routes });
    inApp(<TimelinePage planId={1} {...props} />);
    await screen.findByTestId("timeline-page");
    return fetchMock;
  }

  it("lists everything that happened, newest first, one day at a time, and reading it sends nothing but its read", async () => {
    const fetchMock = await open();
    expect(screen.getByRole("heading", { level: 1, name: timelineView.title })).not.toBeNull();
    expect(screen.getByTestId("timeline-subline").textContent).toBe(timelineView.subline);
    const days = screen.getAllByTestId("timeline-day");
    expect(days.map((d) => d.getAttribute("data-date"))).toEqual(timelineView.days.map((d) => d.date));
    expect(text(within(days[0]!).getByTestId("record-day"))).toBe(
      `${dayWords(timelineView.days[0]!.date)} ${timelineView.days[0]!.count} entries`,
    );
    // One entry for one press, in the record's order.
    expect(screen.getAllByTestId("timeline-entry").map((e) => e.getAttribute("data-entry"))).toEqual(
      entries.map((e) => e.id),
    );
    expect(screen.getByTestId("timeline-total").textContent).toBe(`${timelineView.total} entries`);
    // Where names come from is said once under the list, and the standing line is there.
    expect(screen.getByTestId("names-note").textContent).toBe(timelineView.names_note);
    expect(screen.getByTestId("disclaimer").textContent).toBe(timelineView.disclaimer);
    expect(calls(fetchMock)).toEqual([TIMELINE]);
  });

  it("says each entry in one sentence, with its result words counted, who did it and with which button, and where", async () => {
    await open();
    const row = within(
      screen.getAllByTestId("timeline-entry").find((e) => e.getAttribute("data-entry") === runAll.id)!,
    );
    expect(text(row.getByTestId("timeline-sentence"))).toBe(`${runAll.lead}${runAll.rest.map((p) => p.v).join("")}`);
    // The runs a press started are in its entry, counted by the reviewer's own words.
    expect(row.getAllByTestId("timeline-count").map((c) => text(c))).toEqual(
      runAll.counts.map((c) => `${c.label} ${c.count}`),
    );
    expect(text(row.getByTestId("record-who"))).toBe(`${runAll.who.name} with ${runAll.who.button}`);
    expect(row.getByTestId("record-who").getAttribute("data-source")).toBe(runAll.who.source);
    // A result is never a person's: the entry says who decided its runs, in the same words everywhere.
    expect(text(row.getByTestId("timeline-decided-by"))).toContain("decided by the separate reviewer");
    expect(row.getByTestId("timeline-area").textContent).toBe(runAll.area.label);
    expect(row.getByRole("time").getAttribute("datetime")).toBe(runAll.at);
    // An entry that is no run has no result word and names no decider.
    const added = within(
      screen.getAllByTestId("timeline-entry").find((e) => e.getAttribute("data-kind") === "people")!,
    );
    expect(added.queryByTestId("timeline-results")).toBeNull();
    expect(added.queryByTestId("timeline-decided-by")).toBeNull();
  });

  it("filters by place and by kind, never by what a result rests on, and searches a moment after the last key", async () => {
    const checks = { ...timelineView, chosen: { ...timelineView.chosen, area: "checks" } };
    const runs = { ...checks, chosen: { ...checks.chosen, kind: "runs" } };
    const fetchMock = await open({
      [timelineOf("area=checks")]: { body: checks },
      [timelineOf("area=checks&kind=runs")]: { body: runs },
      [timelineOf("area=checks&kind=runs&q=retest")]: { body: { ...runs, chosen: { ...runs.chosen, q: "retest" } } },
    });
    const where = within(screen.getByRole("group", { name: "Where" }));
    expect(where.getAllByRole("button").map((b) => text(b))).toEqual(
      timelineView.areas.map((a) => `${a.label} ${a.count}`),
    );
    expect(where.getByRole("button", { pressed: true }).getAttribute("data-filter")).toBe("all");
    const what = within(screen.getByRole("group", { name: "What" }));
    expect(what.getAllByRole("button").map((b) => b.getAttribute("data-filter"))).toEqual(
      timelineView.kinds.map((k) => k.key),
    );
    // (no filter by Observed live, Proven in the lab, From your file or Published: the SPEC says there is none)
    for (const group of ["Where", "What"])
      expect(
        within(screen.getByRole("group", { name: group })).queryByRole("button", {
          name: /Observed live|Proven in the lab|From your file|Published/,
        }),
        group,
      ).toBeNull();

    fireEvent.click(where.getByRole("button", { name: /^Checks/ }));
    await waitFor(() => expect(calls(fetchMock)).toContain(timelineOf("area=checks")));
    await waitFor(() =>
      expect(
        within(screen.getByRole("group", { name: "Where" }))
          .getByRole("button", { pressed: true })
          .getAttribute("data-filter"),
      ).toBe("checks"),
    );
    fireEvent.click(
      within(screen.getByRole("group", { name: "What" })).getByRole("button", { name: /^Runs and results/ }),
    );
    await waitFor(() => expect(calls(fetchMock)).toContain(timelineOf("area=checks&kind=runs")));
    fireEvent.change(screen.getByRole("searchbox", { name: "Search the timeline" }), { target: { value: "retest" } });
    await waitFor(() => expect(calls(fetchMock)).toContain(timelineOf("area=checks&kind=runs&q=retest")));
    expect(posts(fetchMock)).toEqual([]);
  });

  it("opens with the place the address names, and tells the app when another is chosen", async () => {
    const onArea = vi.fn();
    const fixes = { ...timelineView, chosen: { ...timelineView.chosen, area: "fixes" }, days: [], total: 0 };
    mockApi({
      [timelineOf("area=fixes")]: {
        body: { ...fixes, empty_text: "Nothing has happened on Fixes yet." },
      },
    });
    inApp(<TimelinePage planId={1} area="fixes" onArea={onArea} />);
    expect((await screen.findByTestId("timeline-empty")).textContent).toBe("Nothing has happened on Fixes yet.");
    fireEvent.click(within(screen.getByRole("group", { name: "Where" })).getByRole("button", { name: /^All/ }));
    expect(onArea).toHaveBeenCalledWith(null);
  });

  it("opens an entry's story in the panel: who, each run with the reviewer's word, and the technical record folded", async () => {
    const fetchMock = await open({ [entryOf(runAll.id)]: { body: runAllEntry } });
    fireEvent.click(
      within(
        screen.getAllByTestId("timeline-entry").find((e) => e.getAttribute("data-entry") === runAll.id)!,
      ).getByRole("button"),
    );
    const panel = within(await screen.findByTestId("entry-panel"));
    expect(screen.getByRole("heading", { level: 2, name: runAllEntry.title })).not.toBeNull();
    expect(screen.getByTestId("panel-kicker").textContent).toBe(`${runAll.area.label} · ${runAll.kind.label}`);
    // Who: each person with what they did, under the name the record was made under.
    const people = panel.getAllByTestId("entry-person");
    expect(people).toHaveLength(runAllEntry.people.length);
    expect(text(people[0]!)).toContain(`${runAllEntry.people[0]!.role}${runAllEntry.people[0]!.who.name}`);
    expect(text(panel.getByTestId("entry-decided-by"))).toBe("Each result here was decided by the separate reviewer.");
    // Every run the press started, each with its own result word and tag, and the way to its record.
    const runs = panel.getAllByTestId("entry-run");
    expect(runs.map((r) => within(r).getByTestId("entry-run-result").textContent)).toEqual(
      runAllEntry.entry.runs.map((r) => r.result.label),
    );
    expect(within(runs[0]!).getByTestId("entry-run-link").getAttribute("href")).toBe(
      `#/a/101/evidence?item=${runAllEntry.entry.runs[0]!.link.item}`,
    );
    // The ids and fingerprints are kept whole behind one fold, a Technical record.
    const fold = panel.getByTestId("entry-record") as HTMLDetailsElement;
    expect(fold.open).toBe(false);
    expect(within(fold).getByTestId("proof-fold-name").textContent).toBe("Technical record");
    expect(within(fold).getAllByTestId("entry-fact")).toHaveLength(runAllEntry.record.length);
    expect(calls(fetchMock)).toEqual([TIMELINE, entryOf(runAll.id)]);
    expect(posts(fetchMock)).toEqual([]);
  });

  it("says of a Verify entry that fixed rules decided its claims, and opens the entry the address names", async () => {
    await open({ [entryOf(verifyEntry.entry.id)]: { body: verifyEntry } }, { openItem: verifyEntry.entry.id });
    const panel = within(await screen.findByTestId("entry-panel"));
    expect(text(panel.getByTestId("entry-decided-by"))).toBe("Each result here was decided by fixed rules.");
    expect(panel.getAllByTestId("entry-run")).toHaveLength(verifyEntry.entry.runs.length);
  });

  it("keeps Change watch's runs apart: listed under Change watch only, with a line that says how many", async () => {
    const apart = {
      count: 2,
      label: "From Change watch",
      text: "Its runs are kept apart and counted nowhere else.",
      area: "watch" as const,
    };
    const fetchMock = await open({
      [TIMELINE]: { body: { ...timelineView, apart } },
      [timelineOf("area=watch")]: { body: { ...timelineView, chosen: { ...timelineView.chosen, area: "watch" } } },
    });
    const line = screen.getByTestId("timeline-apart");
    expect(text(line)).toBe("From Change watch (2). Its runs are kept apart and counted nowhere else. Show them");
    fireEvent.click(within(line).getByRole("button", { name: "Show them" }));
    await waitFor(() => expect(calls(fetchMock)).toContain(timelineOf("area=watch")));
  });
});

describe("Evidence, Approvals and decisions", () => {
  async function open(view = decisionsView, routes: Parameters<typeof mockApi>[0] = {}) {
    const fetchMock = mockApi({ [DECISIONS]: { body: view }, ...routes });
    inApp(<DecisionsPage planId={1} />);
    await screen.findByTestId("decisions-page");
    return fetchMock;
  }

  it("lists every decision a person made, with who and where, and says why no result is in the list", async () => {
    const fetchMock = await open();
    expect(screen.getByRole("heading", { level: 1, name: decisionsView.title })).not.toBeNull();
    expect(screen.getByTestId("decisions-results-note").textContent).toBe(decisionsView.results_note);
    // The four counts, in the record's words. The sign-off reads "Not yet" until the assessment is closed.
    const cards = within(screen.getByRole("list", { name: "Decisions summary" })).getAllByRole("listitem");
    expect(cards.map((c) => text(c))).toEqual(decisionsView.cards.map((c) => `${c.title}${c.value}${c.small}`));
    const row = decisionsView.days[0]!.rows[0]!;
    const shown = within(screen.getAllByTestId("decision-row")[0]!);
    expect(shown.getByTestId("decision-word").textContent).toBe(row.decision.label);
    expect(shown.getByTestId("decision-on").textContent).toBe(row.on);
    expect(text(shown.getByTestId("decision-who"))).toBe(`${row.who.name} with ${row.who.button}`);
    expect(shown.getByRole("time").getAttribute("datetime")).toBe(row.at);
    // No row is a result: nothing here carries a result word.
    expect(screen.queryByTestId("result-badge")).toBeNull();
    expect(calls(fetchMock)).toEqual([DECISIONS]);
  });

  it("shows who pressed where an approval was recorded under another name, and Demo data on a demo reviewer", async () => {
    const row = decisionsView.days[0]!.rows[0]!;
    const approved = {
      ...row,
      id: "approval-1",
      decision: { key: "approved", label: "Approved" },
      on: "Pull request 1: acme-sign range check",
      who: { ...row.who, name: "Demo reviewer A", source: "reviewer" as const, demo: true, button: null },
      pressed_by: { ...row.who, button: "Approve as Demo reviewer A" },
    };
    await open({ ...decisionsView, days: [{ ...decisionsView.days[0]!, rows: [approved] }] });
    const shown = within(screen.getByTestId("decision-row"));
    expect(text(shown.getByTestId("decision-who"))).toBe("Demo reviewer ADemo data");
    expect(text(shown.getByTestId("decision-pressed-by"))).toBe("pressed by You with Approve as Demo reviewer A");
  });

  it("filters by place, and a row opens the same story the Timeline shows", async () => {
    const row = decisionsView.days[0]!.rows[0]!;
    const fetchMock = await open(decisionsView, {
      [`GET /api/plans/1/decisions?area=observe&tz=${ZONE}`]: {
        body: { ...decisionsView, chosen: { area: "observe" } },
      },
      [entryOf(row.id)]: { body: { ...verifyEntry, entry: { ...verifyEntry.entry, id: row.id } } },
    });
    fireEvent.click(
      within(screen.getByRole("group", { name: "Where" })).getByRole("button", { name: /^Observatory and Verify/ }),
    );
    await waitFor(() => expect(calls(fetchMock)).toContain(`GET /api/plans/1/decisions?area=observe&tz=${ZONE}`));
    fireEvent.click(screen.getAllByTestId("decision-row")[0]!);
    expect((await screen.findByTestId("entry-panel")).getAttribute("data-entry")).toBe(row.id);
    expect(posts(fetchMock)).toEqual([]);
  });
});

describe("Evidence, Evidence files", () => {
  it("says so when nothing was downloaded yet, how to check a file, and what the file holds", async () => {
    const fetchMock = mockApi({ [FILES]: { body: evidenceFilesView } });
    inApp(<EvidenceFilesPage planId={1} />);
    await screen.findByTestId("evidence-files-page");
    expect(screen.getByRole("heading", { level: 1, name: evidenceFilesView.title })).not.toBeNull();
    expect(screen.getByTestId("evidence-files-empty").textContent).toBe(evidenceFilesView.empty_text);
    expect(screen.getByTestId("verify-command").textContent).toBe(evidenceFilesView.check.command);
    expect(
      within(screen.getByTestId("evidence-files-holds"))
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(evidenceFilesView.holds.items);
    expect((screen.getByRole("button", { name: "Download evidence" }) as HTMLButtonElement).disabled).toBe(false);
    expect(calls(fetchMock)).toEqual([FILES]);
  });

  it("lists every download with its time, its fingerprint whole and who downloaded it", async () => {
    mockApi({ [FILES]: { body: evidenceFilesWithOne } });
    inApp(<EvidenceFilesPage planId={1} />);
    const row = within(await screen.findByTestId("evidence-file-row"));
    const file = evidenceFilesWithOne.files[0]!;
    expect(row.getByTestId("file-fingerprint").textContent).toBe(file.fingerprint);
    expect(text(row.getByTestId("file-who"))).toBe(`${file.who.name} with ${file.who.button}`);
    expect(row.getByRole("time").getAttribute("datetime")).toBe(file.at);
    expect(row.getByTestId("file-json")).not.toBeNull();
    expect(row.getByTestId("file-html")).not.toBeNull();
  });

  it("turns Download evidence off, with the reason, where the record says it can't start", async () => {
    mockApi({
      [FILES]: {
        body: { ...evidenceFilesView, download: { can_start: false, blocked_reason: "Tests are still running." } },
      },
    });
    inApp(<EvidenceFilesPage planId={1} />);
    await screen.findByTestId("evidence-files-page");
    expect((screen.getByRole("button", { name: "Download evidence" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("download-blocked").textContent).toBe("Tests are still running.");
  });
});

describe("History of this item, in a panel", () => {
  const HISTORY = `GET /api/plans/1/history?key=${encodeURIComponent(testHistory.key)}`;

  it("asks for nothing until it is opened, then lists what happened to the item with who started each run", async () => {
    const fetchMock = mockApi({ [HISTORY]: { body: testHistory } });
    inApp(<HistoryFold itemKey={testHistory.key} />);
    const fold = screen.getByTestId("history-fold");
    // Folded: its name says what it is a history of, and nothing was read.
    expect(within(fold).getByRole("button").textContent).toBe("History of this check");
    expect(calls(fetchMock)).toEqual([]);
    fireEvent.click(within(fold).getByRole("button"));
    const history = within(await screen.findByTestId("history"));
    expect(calls(fetchMock)).toEqual([HISTORY]);
    // On top: who decides a result. Never a person.
    expect(history.getByTestId("history-decides").textContent).toBe(testHistory.decides);
    const lines = history.getAllByTestId("history-line");
    expect(lines.map((l) => l.getAttribute("data-line"))).toEqual(testHistory.lines.map((l) => l.id));
    const first = testHistory.lines[0]!;
    expect(within(lines[0]!).getByTestId("history-result").textContent).toBe(first.result!.label);
    expect(within(lines[0]!).getByTestId("history-said").textContent).toBe(first.said);
    expect(within(lines[0]!).getByTestId("history-decided-by").textContent).toBe(first.decided_by);
    // A fingerprint is cut short; the whole value shows on hover.
    expect(within(lines[0]!).getByTitle(first.fingerprint!).textContent).toBe(first.fingerprint!.slice(0, 12));
    // The way to the same records in the timeline, with this item's place chosen.
    expect(history.getByTestId("history-timeline").getAttribute("href")).toBe(
      `#/a/101/evidence/timeline?group=${testHistory.timeline.area}`,
    );
    // Closing and opening it again does not ask a second time.
    fireEvent.click(within(fold).getByRole("button"));
    fireEvent.click(within(fold).getByRole("button"));
    expect(calls(fetchMock)).toEqual([HISTORY]);
    expect(posts(fetchMock)).toEqual([]);
  });

  it("names itself by the kind of item, and is not drawn without one", () => {
    mockApi({});
    for (const [key, name] of [
      ["fix:fix-tls-versions", "History of this fix"],
      ["system:server:localhost:8443", "History of this system"],
      ["advisory:CVE-2022-21449", "History of this advisory"],
      ["claim:3", "History of this claim"],
    ] as const) {
      inApp(<HistoryFold itemKey={key} />);
      expect(within(screen.getByTestId("history-fold")).getByRole("button").textContent, key).toBe(name);
      cleanup();
    }
    inApp(<HistoryFold itemKey={null} />);
    expect(screen.queryByTestId("history-fold")).toBeNull();
  });

  it("History of a page opens the timeline with that page's records chosen", () => {
    inApp(<HistoryOfPage area="fixes" page="Fixes" />);
    const link = screen.getByTestId("history-of-page");
    expect(link.textContent).toBe("History of Fixes");
    expect(link.getAttribute("href")).toBe("#/a/101/evidence/timeline?group=fixes");
  });
});
