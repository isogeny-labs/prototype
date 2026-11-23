import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { ChangeRow, ChangeWatchView } from "../api";
import { ChangeWatchScreen } from "../components/ChangeWatchScreen";
import { LinkProvider } from "../components/related";
import { CLOSED_SENTENCE, ReadOnlyProvider } from "../readOnly";
import { calls, mockApi, text } from "./fixtures";
import { labCopy } from "./sourceFixtures";

type Routes = Parameters<typeof mockApi>[0];

const VIEW = "GET /api/plans/1/change-watch";
const bringIn = (key: string) => `POST /api/plans/1/change-watch/demo/${key}`;
const runOf = (id: string) => `POST /api/plans/1/change-watch/${id}/run`;
const NOT_CONNECTED = "Connect the demo code first. Connect demo code is on Fixes.";
const NOT_TESTED = "The app has not tested what this line does.";

const menu = (revert: boolean, tls: boolean, why = "Connect the demo code first."): ChangeWatchView["menu"] => ({
  button: "Bring in a demo change",
  note: "Adds the chosen change to this assessment's own copy of the demo repository, as a push would: one branch with one commit by “Demo developer”. It runs nothing.",
  items: [
    {
      key: "revert-range-check",
      title: "Revert the range check",
      what_it_does: "Undoes the merged fix. The program it gives is, byte for byte, acme-sign 1.4.2.",
      can: revert,
      blocked_reason: revert ? null : why,
    },
    {
      key: "allow-tls-1-0",
      title: "Allow TLS 1.0 for an old partner",
      what_it_does: "Adds one settings file. The program is untouched.",
      can: tls,
      blocked_reason: tls ? null : why,
    },
  ],
});

const base: ChangeWatchView = {
  plan_id: 1,
  title: "Change watch",
  subline:
    "A developer's change in the connected demo repository, the tests picked for it, and what they show once you run them. Nothing runs by itself.",
  code: {
    state: "connected",
    line: null,
    link: null,
    connected_line: "Connected: the demo repository acme-sign, branch main.",
  },
  menu: menu(true, true),
  changes: [],
  empty: "No developer's change is in the connected repository yet. Bring in a demo change adds one, and runs nothing.",
  busy: false,
};

const notConnected: ChangeWatchView = {
  ...base,
  code: {
    state: "not_connected",
    line: NOT_CONNECTED,
    link: { page: "fixes", item: null, group: null },
    connected_line: null,
  },
  menu: menu(false, false),
  empty: null,
};

const test = (item_id: number, title: string, reason: string) => ({
  item_id,
  title,
  reason,
  link: { page: "checks", item: `test-${item_id}`, group: null },
});

const tls: ChangeRow = {
  id: "change-aaaaaaaaaaaa",
  title: "Allow TLS 1.0 for an old partner",
  branch: "dev/allow-tls-1-0-for-partner",
  commit: "aaaaaaa",
  author: "Demo developer",
  is_demo: true,
  when: "19 November 2026, 6:02 am EST",
  files_line: "partner-gateway.conf (added)",
  picked_line: "0 of 4 tests picked",
  status: {
    key: "nothing_to_run",
    word: "Nothing to run",
    tone: "neutral",
    busy: false,
    reason: "This change edits no file of a program under test, so no test is picked.",
  },
  flags_count: 1,
  panel: {
    message: "Allow TLS 1.0 for an old partner\n\nThe partner's gateway cannot do anything newer yet.",
    starts_from: "Starts from commit 1234567 (acme-sign 1.4.2), 1 commit on the branch.",
    gives: null,
    files: [
      {
        name: "partner-gateway.conf",
        what: "Added",
        counts: "2 lines added",
        is_program: false,
        note: null,
        blocks: [
          {
            before: [],
            after: [
              { n: 1, mark: "+", text: "port = 443" },
              { n: 2, mark: "+", text: "minimum_protocol = TLS 1.0" },
            ],
          },
        ],
      },
    ],
    picked: [],
    not_picked: [
      test(4, "Attacker tricks (our short list)", "Runs acme-sign, and this change does not edit acme_sign.py."),
      test(1, "Old TLS versions", "Tests the server localhost:8443. It does not run acme-sign."),
    ],
    picked_empty: "This change edits no file of a program under test, so no test is picked.",
    run: {
      label: "Run the picked tests",
      can: false,
      blocked_reason: "This change edits no file of a program under test, so no test is picked.",
      will_run: [],
      note: null,
    },
    last_run: null,
    results: [],
    flags: [
      {
        title: "Old cryptography is named in the change",
        text: "partner-gateway.conf, line 2: “minimum_protocol = TLS 1.0” names TLS 1.0.",
        note: NOT_TESTED,
        source: { title: "RFC 8996, Deprecating TLS 1.0 and TLS 1.1", url: "https://www.rfc-editor.org/rfc/rfc8996" },
      },
    ],
    flags_note: "A flag is something to look at. It is never a result.",
    more_flags: null,
    fix_line: null,
    fix: null,
  },
};

const revert: ChangeRow = {
  id: "change-bbbbbbbbbbbb",
  title: "Revert the range check",
  branch: "dev/revert-range-check",
  commit: "bbbbbbb",
  author: "Demo developer",
  is_demo: true,
  when: "19 November 2026, 6:05 am EST",
  files_line: "acme_sign.py (changed)",
  picked_line: "2 of 4 tests picked",
  status: { key: "not_run", word: "Not run yet", tone: "neutral", busy: false, reason: null },
  flags_count: 0,
  panel: {
    message: "Revert the range check\n\nPutting the old code back until we know why.",
    starts_from: "Starts from commit 7654321 (acme-sign 1.4.3), 1 commit on the branch.",
    gives: "Its code is, byte for byte, acme-sign 1.4.2, one of our registered demo programs.",
    files: [
      {
        name: "acme_sign.py",
        what: "Changed",
        counts: "1 line added, 3 lines removed",
        is_program: true,
        note: null,
        blocks: [
          {
            before: [
              { n: 40, mark: " ", text: "def verify(r, s):" },
              { n: 41, mark: "-", text: "    if not 1 <= r < N: return False" },
            ],
            after: [
              { n: 40, mark: " ", text: "def verify(r, s):" },
              { n: 41, mark: "+", text: "    pass" },
            ],
          },
        ],
      },
    ],
    picked: [
      test(4, "Attacker tricks (our short list)", "Runs acme-sign, and this change edits acme_sign.py."),
      test(5, "Speed and size", "Runs acme-sign, and this change edits acme_sign.py."),
    ],
    not_picked: [test(1, "Old TLS versions", "Tests the server localhost:8443. It does not run acme-sign.")],
    picked_empty: null,
    run: {
      label: "Run the picked tests",
      can: true,
      blocked_reason: null,
      will_run: ["Attacker tricks (our short list)", "Speed and size"],
      note: "Runs Attacker tricks (our short list) and Speed and size on acme-sign 1.4.2: the registered demo program this change's code is, byte for byte.",
    },
    last_run: null,
    results: [],
    flags: [],
    flags_note: null,
    more_flags: null,
    fix_line: null,
    fix: null,
  },
};

const side = (
  run_id: number,
  label: string,
  tone: "pass" | "fail",
  plain: string,
  ran_on: string,
  item: string | null,
) => ({
  run_id,
  label,
  tone,
  plain,
  ran_on,
  link: item ? { page: "checks", item, group: null } : null,
  // 22 November 2026: a watch run runs a copy of the code on this computer
  source_tag: labCopy(ran_on),
});

const running: ChangeRow = {
  ...revert,
  status: { key: "running", word: "Running", tone: "neutral", busy: true, reason: "0 of 2 tests have run." },
  panel: {
    ...revert.panel,
    run: {
      ...revert.panel.run,
      label: "Run again",
      can: false,
      blocked_reason: "The tests picked for a change are running in Change watch. Wait until they have finished.",
    },
    last_run: "19 November 2026, 6:06 am EST",
    results: [
      {
        item_id: 4,
        title: "Attacker tricks (our short list)",
        before: side(7, "Passed", "pass", "Every damaged signature was refused.", "acme-sign 1.4.3", "proof-4-in-1"),
        before_note: "From the proof of a fix.",
        now: null,
        job: { status: "running", progress_text: "checking signature 3 of 9", progress_percent: 30 },
        differs: null,
        outcome: null,
      },
    ],
  },
};

const ran: ChangeRow = {
  ...revert,
  status: {
    key: "passed_before_fails_now",
    word: "Passed before, fails now (1 test)",
    tone: "fail",
    busy: false,
    reason: "1 test passed on the code before and fails on this change.",
  },
  panel: {
    ...revert.panel,
    run: { ...revert.panel.run, label: "Run again" },
    last_run: "19 November 2026, 6:06 am EST",
    results: [
      {
        item_id: 4,
        title: "Attacker tricks (our short list)",
        before: side(7, "Passed", "pass", "Every damaged signature was refused.", "acme-sign 1.4.3", "proof-4-in-1"),
        before_note: "From the proof of a fix.",
        now: side(9, "Failed", "fail", "acme-sign 1.4.2 accepted a signature made of zeros.", "acme-sign 1.4.2", null),
        job: null,
        differs: "Passed before, fails now",
        outcome: "fails_now",
      },
    ],
  },
};

const withRows = (...changes: ChangeRow[]): ChangeWatchView => ({
  ...base,
  changes,
  empty: null,
  busy: changes.some((c) => c.status.busy),
});

async function open(view: ChangeWatchView, routes: Routes = {}, more: { openItem?: string; closed?: boolean } = {}) {
  const fetchMock = mockApi({ [VIEW]: { body: view }, ...routes });
  render(
    <ReadOnlyProvider readOnly={more.closed === true}>
      <LinkProvider assessmentId={101} planId={1}>
        <ChangeWatchScreen planId={1} openItem={more.openItem ?? null} />
      </LinkProvider>
    </ReadOnlyProvider>,
  );
  await screen.findByTestId("page-header");
  await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  return fetchMock;
}

const rows = () => screen.getAllByTestId("change-row");
const panel = () => within(screen.getByTestId("change-panel"));

beforeEach(() => window.localStorage.clear());

describe("Change watch, before a change is in", () => {
  it("says what to do first while the demo code is not connected, with the way to Fixes, and offers nothing", async () => {
    const fetchMock = await open(notConnected);
    expect(text(screen.getByTestId("change-watch-code-line"))).toBe(`${NOT_CONNECTED} Open Fixes`);
    expect(screen.getByTestId("change-watch-code-link").getAttribute("href")).toBe("#/a/101/fixes");
    expect(screen.queryByTestId("changes-table")).toBeNull();
    fireEvent.click(screen.getByTestId("demo-change-button"));
    const items = screen.getAllByTestId("demo-change-item") as HTMLButtonElement[];
    expect(items.map((i) => i.disabled)).toEqual([true, true]);
    expect(screen.getAllByTestId("demo-change-blocked").map((b) => text(b))).toEqual([
      "Connect the demo code first.",
      "Connect the demo code first.",
    ]);
    expect(calls(fetchMock)).toEqual([VIEW]);
  });

  it("connected with no change: the table says so, and reading the page sent nothing but its one read", async () => {
    const fetchMock = await open(base);
    expect(text(screen.getByRole("heading", { level: 1 }))).toBe("Change watch");
    expect(text(screen.getByTestId("change-watch-connected"))).toBe(
      "Connected: the demo repository acme-sign, branch main.",
    );
    expect(text(screen.getByTestId("changes-empty"))).toBe(base.empty);
    expect(screen.queryByTestId("demo-change-menu")).toBeNull(); // the menu is shut until its button is pressed
    expect(calls(fetchMock)).toEqual([VIEW]);
  });

  it("Bring in a demo change sends exactly one request for the chosen change and opens it; the menu says it runs nothing", async () => {
    const fetchMock = await open(base, { [bringIn("allow-tls-1-0")]: { body: withRows(tls) } });
    fireEvent.click(screen.getByTestId("demo-change-button"));
    const list = within(screen.getByTestId("demo-change-menu"));
    expect(text(screen.getByTestId("demo-change-menu"))).toContain("It runs nothing.");
    expect(list.getByText("Demo data")).not.toBeNull();
    expect(calls(fetchMock)).toEqual([VIEW]); // opening the menu sent nothing
    fireEvent.click(list.getByText("Allow TLS 1.0 for an old partner"));
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(calls(fetchMock)).toEqual([VIEW, bringIn("allow-tls-1-0")]);
    expect(screen.getByTestId("change-panel").getAttribute("data-change")).toBe(tls.id);
    expect(screen.queryByTestId("demo-change-menu")).toBeNull();
  });

  it("shows the server's sentence when a change can't be brought in", async () => {
    await open(base, {
      [bringIn("revert-range-check")]: {
        status: 409,
        body: { error: { message: "This demo change is already in the repository.", line: null, field: null } },
      },
    });
    fireEvent.click(screen.getByTestId("demo-change-button"));
    fireEvent.click(within(screen.getByTestId("demo-change-menu")).getByText("Revert the range check"));
    expect(await screen.findByText("This demo change is already in the repository.")).not.toBeNull();
  });
});

describe("Change watch, the table and a change's panel", () => {
  it("lists each change with its branch, who and when, its files, the tests picked, its status word and its flags", async () => {
    await open(withRows(revert, tls));
    expect(rows().map((r) => r.getAttribute("data-status"))).toEqual(["not_run", "nothing_to_run"]);
    const first = within(rows()[0]!);
    expect(first.getByText("Revert the range check")).not.toBeNull();
    expect(first.getByText("dev/revert-range-check")).not.toBeNull();
    expect(first.getByText("Demo data")).not.toBeNull();
    expect(text(rows()[0]!)).toContain("Demo developer");
    expect(text(rows()[0]!)).toContain("19 November 2026, 6:05 am EST");
    expect(text(rows()[0]!)).toContain("commit bbbbbbb");
    expect(text(rows()[0]!)).toContain("acme_sign.py (changed)");
    expect(text(rows()[0]!)).toContain("2 of 4 tests picked");
    expect(text(first.getByTestId("change-status"))).toBe("Not run yet");
    expect(text(within(rows()[1]!).getByTestId("change-status"))).toBe("Nothing to run");
    expect(text(within(rows()[1]!).getByTestId("change-flags-count"))).toBe("1 flag");
    expect(first.queryByTestId("change-flags-count")).toBeNull();
  });

  it("opens a change: what changed line by line, the tests picked and not picked with their reasons, and what Run will run", async () => {
    const fetchMock = await open(withRows(revert, tls));
    fireEvent.click(rows()[0]!);
    const p = panel();
    expect(text(p.getByTestId("change-panel-status"))).toBe("Not run yet");
    expect(text(p.getByTestId("change-gives"))).toBe(
      "Its code is, byte for byte, acme-sign 1.4.2, one of our registered demo programs.",
    );
    expect(text(p.getByTestId("change-message"))).toContain("Putting the old code back");
    const lines = p.getAllByTestId("code-line");
    expect(lines.map((l) => l.getAttribute("data-mark"))).toEqual([" ", "-", " ", "+"]);
    expect(text(p.getByTestId("change-file"))).toContain("acme_sign.py: Changed (1 line added, 3 lines removed)");
    const picked = within(p.getByTestId("change-picked")).getAllByTestId("change-test");
    expect(picked.map((t) => text(t))).toEqual([
      "Attacker tricks (our short list)Runs acme-sign, and this change edits acme_sign.py.",
      "Speed and sizeRuns acme-sign, and this change edits acme_sign.py.",
    ]);
    expect(within(picked[0]!).getByRole("link").getAttribute("href")).toBe("#/a/101/checks?item=test-4");
    expect(text(within(p.getByTestId("change-not-picked")).getByTestId("change-test"))).toBe(
      "Old TLS versionsTests the server localhost:8443. It does not run acme-sign.",
    );
    const button = p.getByTestId("change-run-button") as HTMLButtonElement;
    expect(text(button)).toBe("Run the picked tests");
    expect(button.disabled).toBe(false);
    expect(text(p.getByTestId("change-run-note"))).toContain(
      "Attacker tricks (our short list) and Speed and size on acme-sign 1.4.2",
    );
    expect(p.queryByTestId("change-results")).toBeNull();
    expect(calls(fetchMock)).toEqual([VIEW]); // opening a change ran nothing
  });

  it("Run the picked tests sends one request, and only when its button is pressed", async () => {
    const fetchMock = await open(withRows(revert), { [runOf(revert.id)]: { body: withRows(ran) } });
    fireEvent.click(rows()[0]!);
    expect(calls(fetchMock)).toEqual([VIEW]);
    fireEvent.click(panel().getByTestId("change-run-button"));
    await waitFor(() =>
      expect(text(panel().getByTestId("change-panel-status"))).toBe("Passed before, fails now (1 test)"),
    );
    expect(calls(fetchMock)).toEqual([VIEW, runOf(revert.id)]);
    expect(text(panel().getByTestId("change-run-button"))).toBe("Run again");
    expect(text(panel().getByTestId("change-status-reason"))).toBe(
      "1 test passed on the code before and fails on this change.",
    );
  });

  it("a change with nothing to run has its button off with the reason, and shows its flag with the note and the source", async () => {
    const fetchMock = await open(withRows(tls), {}, { openItem: tls.id });
    const p = panel();
    expect((p.getByTestId("change-run-button") as HTMLButtonElement).disabled).toBe(true);
    expect(text(p.getByTestId("change-run-blocked"))).toBe(
      "This change edits no file of a program under test, so no test is picked.",
    );
    expect(text(p.getByTestId("change-picked-empty"))).toBe(
      "This change edits no file of a program under test, so no test is picked.",
    );
    const flag = within(p.getByTestId("change-flag"));
    expect(text(p.getByTestId("change-flag"))).toContain(
      "partner-gateway.conf, line 2: “minimum_protocol = TLS 1.0” names TLS 1.0.",
    );
    expect(text(flag.getByTestId("change-flag-note"))).toBe(NOT_TESTED);
    expect(flag.getByRole("link", { name: "RFC 8996, Deprecating TLS 1.0 and TLS 1.1" }).getAttribute("href")).toBe(
      "https://www.rfc-editor.org/rfc/rfc8996",
    );
    expect(text(screen.getByTestId("change-panel"))).toContain("A flag is something to look at. It is never a result.");
    // a flag carries no badge of a result
    expect(flag.queryByTestId("result-badge")).toBeNull();
    fireEvent.click(p.getByTestId("change-run-button"));
    expect(calls(fetchMock)).toEqual([VIEW]);
  });

  it("does not turn a source that is not https into a link", async () => {
    const odd: ChangeRow = {
      ...tls,
      panel: {
        ...tls.panel,
        flags: [{ ...tls.panel.flags[0]!, source: { title: "A note", url: "javascript:alert(1)" } }],
      },
    };
    await open(withRows(odd), {}, { openItem: odd.id });
    expect(within(panel().getByTestId("change-flag")).queryByRole("link")).toBeNull();
    expect(text(panel().getByTestId("change-flag"))).toContain("A note");
  });

  it("while the picked tests run it shows their progress, keeps Run off with the reason, and asks again until they have finished", async () => {
    let reads = 0;
    const fetchMock = await open(
      withRows(running),
      { [VIEW]: () => ({ body: ++reads >= 3 ? withRows(ran) : withRows(running) }) },
      { openItem: revert.id },
    );
    expect(text(panel().getByTestId("change-panel-status"))).toBe("Running");
    expect((panel().getByTestId("change-run-button") as HTMLButtonElement).disabled).toBe(true);
    expect(text(panel().getByTestId("change-run-blocked"))).toContain("are running in Change watch");
    expect(text(panel().getByTestId("change-result"))).toContain("checking signature 3 of 9");
    await waitFor(
      () => expect(text(panel().getByTestId("change-panel-status"))).toBe("Passed before, fails now (1 test)"),
      { timeout: 4000 },
    );
    expect(calls(fetchMock).every((c) => c === VIEW)).toBe(true); // it only read again
    const settled = calls(fetchMock).length;
    await new Promise((done) => setTimeout(done, 1200));
    expect(calls(fetchMock).length).toBe(settled); // and stopped asking once nothing runs
  });

  it("a read that fails while the tests run is said on the page, and the page asks again until they have finished", async () => {
    let reads = 0;
    await open(
      withRows(running),
      {
        [VIEW]: () => {
          reads += 1;
          if (reads === 2 || reads === 3) return { status: 503, body: { detail: "The app is busy. Try again." } };
          return { body: reads >= 4 ? withRows(ran) : withRows(running) };
        },
      },
      { openItem: revert.id },
    );
    expect(screen.queryByTestId("change-watch-stale")).toBeNull();
    const stale = await screen.findByTestId("change-watch-stale", undefined, { timeout: 3000 });
    expect(text(stale)).toContain(
      "This page could not be read again, so it may be behind. It asks again every second.",
    );
    expect(text(stale)).toContain("The app is busy. Try again.");
    expect(text(panel().getByTestId("change-panel-status"))).toBe("Running"); // (what was read last stays, with the line above it)
    await waitFor(
      () => expect(text(panel().getByTestId("change-panel-status"))).toBe("Passed before, fails now (1 test)"),
      { timeout: 5000 },
    );
    expect(screen.queryByTestId("change-watch-stale")).toBeNull();
  }, 10_000);

  it("keeps asking while anything else runs for the assessment, so Run comes back on when that has finished", async () => {
    // (the server says so with `busy`: no change of the page is running, but a retest is, and Run is off meanwhile)
    const blocked: ChangeRow = {
      ...revert,
      panel: {
        ...revert.panel,
        run: { ...revert.panel.run, can: false, blocked_reason: "A retest is running. Wait until it has finished." },
      },
    };
    let reads = 0;
    await open(
      { ...withRows(blocked), busy: true },
      { [VIEW]: () => ({ body: ++reads >= 3 ? withRows(revert) : { ...withRows(blocked), busy: true } }) },
      { openItem: revert.id },
    );
    expect((panel().getByTestId("change-run-button") as HTMLButtonElement).disabled).toBe(true);
    expect(text(panel().getByTestId("change-run-blocked"))).toBe("A retest is running. Wait until it has finished.");
    await waitFor(() => expect((panel().getByTestId("change-run-button") as HTMLButtonElement).disabled).toBe(false), {
      timeout: 4000,
    });
  });

  it("the speed test's line says what its run on the change found against the code before", async () => {
    const speed: ChangeRow = {
      ...ran,
      status: {
        key: "no_difference",
        word: "No difference found",
        tone: "neutral",
        busy: false,
        reason: "No picked test that passed on the code before fails on this change, and none that failed passes.",
      },
      panel: {
        ...ran.panel,
        results: [
          {
            item_id: 5,
            title: "Speed and size",
            before: side(
              8,
              "No slowdown beyond measured noise",
              "pass",
              "No slowdown was measured.",
              "acme-sign 1.4.3",
              "proof-5-in-1",
            ),
            before_note: "From the proof of a fix.",
            now: side(
              10,
              "No slowdown beyond measured noise",
              "pass",
              "No slowdown was measured.",
              "acme-sign 1.4.2",
              "watch-5-in-1",
            ),
            job: null,
            differs: "No slowdown against the code before",
            outcome: "not_slower",
          },
        ],
      },
    };
    await open(withRows(speed), {}, { openItem: speed.id });
    expect(panel().getByTestId("change-result").getAttribute("data-outcome")).toBe("not_slower");
    expect(text(panel().getByTestId("change-result-differs"))).toBe("No slowdown against the code before");
  });

  it("after a run it repeats the reviewer's word and plain sentence for before and now, with the way to the evidence", async () => {
    await open(withRows(ran), {}, { openItem: ran.id });
    const result = within(panel().getByTestId("change-result"));
    expect(panel().getByTestId("change-result").getAttribute("data-outcome")).toBe("fails_now");
    expect(text(result.getByTestId("change-result-differs"))).toBe("Passed before, fails now");
    const before = within(result.getByTestId("change-result-before"));
    const now = within(result.getByTestId("change-result-now"));
    expect(text(before.getByTestId("result-badge"))).toBe("Passed");
    expect(text(result.getByTestId("change-result-before"))).toContain("Before: acme-sign 1.4.3");
    expect(text(result.getByTestId("change-result-before"))).toContain("Every damaged signature was refused.");
    expect(text(result.getByTestId("change-result-before"))).toContain("From the proof of a fix.");
    expect(before.getByTestId("change-result-link").getAttribute("href")).toBe("#/a/101/checks?item=proof-4-in-1");
    expect(text(now.getByTestId("result-badge"))).toBe("Failed");
    expect(text(result.getByTestId("change-result-now"))).toContain("On this change: acme-sign 1.4.2");
    expect(text(result.getByTestId("change-result-now"))).toContain(
      "acme-sign 1.4.2 accepted a signature made of zeros.",
    );
    expect(text(panel().getByTestId("change-last-run"))).toBe("Last run started 19 November 2026, 6:06 am EST.");
    expect(panel().queryByTestId("change-fix-line")).toBeNull(); // (no entry in Fixes is named by the server for this view)
  });

  it("tags before and now each by where its run came from, beside the reviewer's word, with that run's own sentence", async () => {
    const fetchMock = await open(withRows(ran), {}, { openItem: ran.id });
    const result = within(panel().getByTestId("change-result"));
    for (const [id, program] of [
      ["change-result-before", "acme-sign 1.4.3"],
      ["change-result-now", "acme-sign 1.4.2"],
    ] as const) {
      const sideBox = within(result.getByTestId(id));
      expect(sideBox.getAllByTestId("source-tag").map((t) => [t.textContent, t.getAttribute("data-source")])).toEqual([
        ["Proven in the lab", "lab"],
      ]);
      expect(sideBox.getByTestId("result-badge").parentElement!.contains(sideBox.getByTestId("source-tag"))).toBe(true);
      expect(sideBox.getByTestId("source-note").textContent).toContain(`Run on a copy of ${program} on this computer`);
    }
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("a side with no reviewed run yet has no tag", async () => {
    await open(withRows(running), {}, { openItem: running.id });
    expect(
      panel()
        .getAllByTestId("source-tag")
        .map((t) => t.closest("[data-testid^='change-result-']")!.getAttribute("data-testid")),
    ).toEqual(["change-result-before"]);
    expect(within(panel().getByTestId("change-result-now")).queryAllByTestId("source-tag")).toEqual([]);
  });

  it("where Fixes has an entry for the change, its panel says so in one line with the way there", async () => {
    const withFix: ChangeRow = {
      ...ran,
      panel: {
        ...ran.panel,
        fix_line: "A suggestion for this change is in Fixes. It is text only.",
        fix: { page: "fixes", item: `fix-${ran.id}`, group: null },
      },
    };
    await open(withRows(withFix), {}, { openItem: withFix.id });
    expect(text(panel().getByTestId("change-fix-line"))).toBe(
      "A suggestion for this change is in Fixes. It is text only. View in Fixes",
    );
    expect(panel().getByTestId("change-fix-link").getAttribute("href")).toBe(`#/a/101/fixes?item=fix-${ran.id}`);
  });

  it("in a closed assessment the two buttons are off with the closed sentence, and nothing is sent", async () => {
    const fetchMock = await open(withRows(revert), {}, { openItem: revert.id, closed: true });
    const button = panel().getByTestId("change-run-button") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(button.getAttribute("title")).toBe(CLOSED_SENTENCE);
    expect((screen.getByTestId("demo-change-button") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(button);
    expect(calls(fetchMock)).toEqual([VIEW]);
  });

  it("opens the change the address names, and Escape or the close button shuts its panel", async () => {
    await open(withRows(revert, tls), {}, { openItem: tls.id });
    expect(screen.getByTestId("change-panel").getAttribute("data-change")).toBe(tls.id);
    fireEvent.click(panel().getByRole("button", { name: "Close details" }));
    expect(screen.queryByTestId("change-panel")).toBeNull();
    fireEvent.click(rows()[0]!);
    expect(screen.getByTestId("change-panel").getAttribute("data-change")).toBe(revert.id);
  });
});
