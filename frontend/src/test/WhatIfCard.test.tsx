import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { WhatIf } from "../api";
import { OttoPanel } from "../components/assistant/OttoPanel";
import { LinkProvider } from "../components/related";
import { ReadOnlyProvider } from "../readOnly";
import { answer, nextStep, panel } from "./assistantFixtures";
import { calls, mockApi, text } from "./fixtures";

/** What one request sent: its JSON body. */
function sent(fetchMock: ReturnType<typeof mockApi>, key: string): { body: unknown } | null {
  const call = fetchMock.mock.calls.find(([input, init]) => `${init?.method ?? "GET"} ${String(input)}` === key);
  return call ? { body: call[1]?.body ? JSON.parse(String(call[1].body)) : null } : null;
}

const SAY = "POST /api/plans/1/assistant/messages";
const ASK = "If I update elliptic to 6.5.7, how does that affect my libraries and dependencies?";
const PKG = {
  title: "The package.json of elliptic 6.5.7 (npm registry)",
  url: "https://registry.npmjs.org/elliptic/-/elliptic-6.5.7.tgz",
  quote: '"dependencies": {\n    "bn.js": "^4.11.9"\n  }',
  read_on: "2026-11-19",
};

const group = (
  key: WhatIf["facts"][number]["key"],
  title: string,
  lines: WhatIf["facts"][number]["lines"],
  none: string | null = null,
) => ({ key, title, lines, none });
type Line = WhatIf["facts"][number]["lines"][number];
const line = (
  text_: string,
  label: string | null = null,
  link: Line["link"] = null,
  source: Line["source"] = null,
): Line => ({ text: text_, label, link, source });

const whatif: WhatIf = {
  plan_id: 1,
  asked: { library: "elliptic", version: "6.5.7" },
  known: true,
  library: { key: "elliptic", label: "elliptic" },
  version: "6.5.7",
  version_read: true,
  have: ["6.5.6"],
  title: "What if elliptic is updated to 6.5.7?",
  facts_title: "What the app knows",
  facts: [
    group("used", "Where the library is used", [
      line("elliptic 6.5.6 is in your dependency list, under acme-ledger 5.1.0 (direct).", "From your file", {
        page: "migration/dependencies",
        item: "row-5",
        group: null,
      }),
    ]),
    group("needs", "Dependencies added or removed by the new version", [
      line(
        "elliptic 6.5.7 declares the same 7 packages as 6.5.6: nothing added, nothing removed, no range changed.",
        "Package file says",
        null,
        PKG,
      ),
    ]),
    group("advisories", "Published advisories and the new version", [
      line(
        "CVE-2024-42460 (Wrongly encoded signature accepted): its publisher names 6.5.7 as the fixed version. 6.5.7 is at or past it, so the update answers this advisory by the publisher's own statement.",
        "Test pack 2026.11.2",
        { page: "advisories", item: "CVE-2024-42460", group: null },
        {
          title: "The publisher's line, as test pack 2026.11.2 holds it",
          url: null,
          quote: '"fixed": "6.5.7"',
          read_on: null,
        },
      ),
    ]),
    group("trial", "What the test pack's own trial showed on public copies", [
      line(
        "CVE-2024-42460: Proven on public copies: Passed. 6.5.6 fails the advisory check; 6.5.7 passes.",
        "Test pack 2026.11.2",
        { page: "advisories", item: "CVE-2024-42460", group: null },
      ),
    ]),
    group("post_quantum", "Post-quantum support of both versions", [
      line(
        "ML-KEM-768 key exchange. elliptic 6.5.6: Not in our knowledge base yet; elliptic 6.5.7: Not in our knowledge base yet.",
      ),
    ]),
    group("blocks", "The migration track it blocks today", [], "elliptic blocks no migration track today."),
    group(
      "own_results",
      "Your own results on this library",
      [],
      "Your scanner file does not name elliptic, so this assessment has no result of its own on it.",
    ),
  ],
  test_copy: {
    title: "A try on a test copy",
    button: "Retest new version",
    offered: false,
    reason: "Your scanner file does not name elliptic, so there is no locked test of this assessment to rerun on it.",
    component: null,
    version: "6.5.7",
    changes: [
      "It reruns this assessment's locked tests for that library on the public copy of the new version, on this computer.",
      "“Proven in this assessment” then reads this run.",
    ],
  },
  explanation: "Live Otto is off. This is what the app knows.",
  hypotheses_title: "Hypothesis",
  hypotheses_note:
    "What the facts above do not show. Turning one of these into a test, or adding it to Change watch, is not part of this version yet.",
  hypotheses: [
    { text: "Whether your system really loads this library needs your environment." },
    { text: "The app has tested the library's public copy, not the programs of yours that use it." },
  ],
};

async function ask(reply: ReturnType<typeof answer>, routes: Parameters<typeof mockApi>[0] = {}) {
  const view = panel("migration/dependencies");
  const fetchMock = mockApi({
    "GET /api/assessments/101/assistant?page=migration%2Fdependencies": { body: view },
    [SAY]: { body: reply },
    ...routes,
  });
  render(
    <ReadOnlyProvider readOnly={false}>
      <LinkProvider assessmentId={101} planId={1}>
        <OttoPanel assessmentId={101} page="migration/dependencies" item={null} onGo={() => {}} />
      </LinkProvider>
    </ReadOnlyProvider>,
  );
  await screen.findByTestId("otto-status");
  fireEvent.change(screen.getByTestId("otto-box-text"), { target: { value: ASK } });
  fireEvent.click(screen.getByTestId("otto-box-send"));
  const shown = await screen.findByTestId("otto-reply");
  return { fetchMock, shown };
}

beforeEach(() => window.localStorage.clear());

describe("a what-if in the Otto panel (phase 6e, first half)", () => {
  it("draws what the app knows in its four parts, each fact with where it comes from and where it is shown, and has nothing to press where the try is off", async () => {
    const { fetchMock, shown } = await ask(
      answer("whatif", whatif.title, {
        thread: "fixing",
        label: "From what the app knows",
        whatif,
        facts: [{ text: "Where the library is used: ...", link: null, label: null }],
      }),
    );
    expect(calls(fetchMock)).toEqual([SAY]);
    expect(sent(fetchMock, SAY)?.body).toEqual({ text: ASK, page: "migration/dependencies", item: null });
    expect(shown.getAttribute("data-kind")).toBe("whatif");
    expect(text(within(shown).getByTestId("otto-reply-text"))).toBe("What if elliptic is updated to 6.5.7?");
    expect(text(within(shown).getByTestId("otto-reply-label"))).toBe("From what the app knows");
    const card = within(within(shown).getByTestId("whatif-card"));
    // part 1: the seven kinds of fact, in order; a kind with nothing says so in one sentence
    expect(card.getAllByTestId("whatif-group").map((g) => g.getAttribute("data-group"))).toEqual([
      "used",
      "needs",
      "advisories",
      "trial",
      "post_quantum",
      "blocks",
      "own_results",
    ]);
    expect(card.getAllByTestId("whatif-none").map((n) => text(n))).toEqual([
      "elliptic blocks no migration track today.",
      "Your scanner file does not name elliptic, so this assessment has no result of its own on it.",
    ]);
    const used = within(card.getAllByTestId("whatif-group")[0]!);
    expect(text(used.getByTestId("whatif-label"))).toBe("From your file");
    expect(used.getByTestId("whatif-link").getAttribute("href")).toBe("#/a/101/migration/dependencies?item=row-5");
    // a publisher's package file is a link to the publisher, with its lines quoted and the day it was read
    const needs = within(card.getAllByTestId("whatif-group")[1]!);
    expect(needs.getByTestId("whatif-source-link").getAttribute("href")).toBe(PKG.url);
    expect(needs.getByTestId("whatif-source-link").getAttribute("rel")).toBe("noreferrer noopener");
    expect(text(needs.getByTestId("whatif-source"))).toContain("read on 2026-11-19");
    expect(needs.getByTestId("whatif-quote").textContent).toContain('"bn.js": "^4.11.9"');
    // a line quoted from a test pack has no address: it is named, not linked
    const advisories = within(card.getAllByTestId("whatif-group")[2]!);
    expect(advisories.queryByTestId("whatif-source-link")).toBeNull();
    expect(text(advisories.getByTestId("whatif-source"))).toContain(
      "The publisher's line, as test pack 2026.11.2 holds it",
    );
    // part 2: the try is off, with the reason; there is no button
    const tried = card.getByTestId("whatif-try");
    expect(tried.getAttribute("data-offered")).toBe("no");
    expect(text(card.getByTestId("whatif-try-reason"))).toBe(
      "Retest new version is not offered for this. Your scanner file does not name elliptic, so there is no locked test of this assessment to rerun on it.",
    );
    expect(within(tried).queryAllByRole("button")).toHaveLength(0);
    // part 3 and part 4
    expect(text(card.getByTestId("whatif-explanation"))).toBe("Live Otto is off. This is what the app knows.");
    expect(card.getAllByTestId("whatif-hypothesis").map((h) => text(h))).toEqual(whatif.hypotheses.map((h) => h.text));
    // the flat facts are what is kept of the exchange; they are not drawn a second time
    expect(within(shown).queryByTestId("otto-facts")).toBeNull();
    expect(calls(fetchMock)).toEqual([SAY]); // drawing the answer asked nothing more
  });

  it("where the page offers the retest, the try is that button's own card: what a retest changes is said first, and nothing is sent before Confirm", async () => {
    const step = nextStep("next:retest", "Retest new version", "Evidence", {
      type: "retest",
      plan_id: 1,
      version: "1.4.3",
      component: "acme-sign",
    });
    const offered: WhatIf = {
      ...whatif,
      title: "What if acme-sign is updated to 1.4.3?",
      test_copy: { ...whatif.test_copy, offered: true, reason: null, component: "acme-sign", version: "1.4.3" },
    };
    const RETEST = "POST /api/plans/1/retest";
    const { fetchMock, shown } = await ask(
      answer("whatif", offered.title, {
        thread: "fixing",
        label: "From what the app knows",
        whatif: offered,
        entry: step,
      }),
      { [RETEST]: { body: {} } },
    );
    const tried = within(within(shown).getByTestId("whatif-try"));
    expect(within(shown).getByTestId("whatif-try").getAttribute("data-offered")).toBe("yes");
    expect(tried.getAllByRole("listitem").map((li) => text(li))).toEqual(offered.test_copy.changes);
    expect(tried.queryByTestId("whatif-try-reason")).toBeNull();
    const card = tried.getByTestId("otto-entry");
    expect(text(within(card).getByTestId("otto-entry-title"))).toBe("Retest new version");
    expect(calls(fetchMock)).toEqual([SAY]);
    fireEvent.click(within(card).getByRole("button", { name: "Retest new version" }));
    expect(text(within(card).getByTestId("otto-confirm-names"))).toBe(
      "This is the Retest new version button on Evidence.",
    );
    expect(calls(fetchMock)).toEqual([SAY]); // nothing before Confirm
    fireEvent.click(within(card).getByTestId("otto-confirm-button"));
    await waitFor(() => expect(calls(fetchMock)).toContain(RETEST));
    expect(sent(fetchMock, RETEST)?.body).toEqual({ version: "1.4.3", component: "acme-sign" }); // the page button's own request
    // Once confirmed, the card is gone and the panel says it was sent. The try was offered all the same: the part keeps
    // what a retest changes and never says that it is not offered (the review of 19 November 2026).
    await waitFor(() => expect(screen.getByTestId("otto-reply-confirmed")).toBeTruthy());
    const after = screen.getByTestId("whatif-try");
    expect(after.getAttribute("data-offered")).toBe("yes");
    expect(within(after).queryByTestId("whatif-try-reason")).toBeNull();
    expect(after.textContent).not.toContain("is not offered");
    expect(within(after).queryByTestId("otto-entry")).toBeNull();
    expect(
      within(after)
        .getAllByRole("listitem")
        .map((li) => text(li)),
    ).toEqual(offered.test_copy.changes);
  });

  it("a library the app knows nothing about still gets its four parts, and says so", async () => {
    const unknown: WhatIf = {
      ...whatif,
      known: false,
      title: "What if left-pad is updated to 1.3.0?",
      facts: whatif.facts.map((g) => ({ ...g, lines: [], none: "Not known." })),
      hypotheses: [{ text: "The app holds nothing about this library, so everything about the update is open." }],
    };
    const { shown } = await ask(answer("whatif", unknown.title, { thread: "fixing", whatif: unknown }));
    const card = within(shown).getByTestId("whatif-card");
    expect(card.getAttribute("data-known")).toBe("no");
    expect(within(card).getAllByTestId("whatif-none")).toHaveLength(7);
    expect(within(card).queryAllByTestId("whatif-line")).toHaveLength(0);
    expect(text(within(card).getByTestId("whatif-hypothesis"))).toBe(
      "The app holds nothing about this library, so everything about the update is open.",
    );
  });
});
