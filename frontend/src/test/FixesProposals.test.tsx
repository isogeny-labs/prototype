import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { FixesView, OttoProposal } from "../api";
import { FixesScreen } from "../components/FixesScreen";
import { LinkProvider } from "../components/related";
import { CLOSED_SENTENCE, ReadOnlyProvider } from "../readOnly";
import {
  CODE_PROPOSAL,
  codeAccepted,
  codeProposal,
  CONNECT_NOTE,
  fixesWith,
  HERE_LABEL,
  HERE_NOTE,
  hereNotYet,
  herePassed,
  javaFix,
  NOT_ACCEPTED,
  ottoCodeFix,
  PUBLIC_LABEL,
  publicNotProven,
  publicPassed,
  UPDATE_FIX,
  UPDATE_PROPOSAL,
  updateAccepted,
  updateFix,
  updateProposal,
  updateRejected,
} from "./fixProposalFixtures";
import { CODE_FIX, TLS_FIX, tlsFix } from "./fixesFixtures";
import { calls, mockApi, text } from "./fixtures";

/** Phase 5c, second part, on Fixes: a library's fix from Otto has two proof rows in place of the one Proof line, and
 * every fix of Otto's is a proposal a person accepts or rejects. Nothing runs without a click. */

type Routes = Parameters<typeof mockApi>[0];

const FIXES = "GET /api/plans/1/fixes";
const CONNECT = "POST /api/plans/1/fixes/connect";
const decide = (id: string, decision: string) => `POST /api/plans/1/otto/proposals/${id}/${decision}`;
/** The Related block every open fix asks for (nothing recorded here). */
const related = (...fixIds: string[]): Routes =>
  Object.fromEntries(
    fixIds.map((id) => [
      `GET /api/plans/1/related?key=${encodeURIComponent(`fix:${id}`)}`,
      { body: { key: `fix:${id}`, related: [] } },
    ]),
  );

function Harness({ start, readOnly = false }: { start: string | null; readOnly?: boolean }) {
  const [selected, setSelected] = useState(start);
  return (
    <ReadOnlyProvider readOnly={readOnly}>
      <LinkProvider assessmentId={101} planId={1}>
        <FixesScreen planId={1} selectedId={selected} onSelect={setSelected} onRetestStarted={() => {}} />
      </LinkProvider>
    </ReadOnlyProvider>
  );
}

/** Opens Fixes on one fix. Every read of the view takes the next one of `views` (the last one stays). */
async function open(views: FixesView | FixesView[], start: string, routes: Routes = {}, readOnly = false) {
  const list = Array.isArray(views) ? views : [views];
  let read = 0;
  const fetchMock = mockApi({
    [FIXES]: () => ({ body: list[Math.min(read++, list.length - 1)] }),
    ...related(...list.flatMap((v) => v.fixes.map((f) => f.id))),
    ...routes,
  });
  render(<Harness start={start} readOnly={readOnly} />);
  await screen.findByTestId("fix-summary");
  return fetchMock;
}

/** The requests so far, without the Related block's own reads. */
const asked = (fetchMock: ReturnType<typeof mockApi>) => calls(fetchMock).filter((c) => !c.includes("/related?"));
/** The JSON body of the n-th POST. */
function posted(fetchMock: ReturnType<typeof mockApi>, n = 0): unknown {
  const init = fetchMock.mock.calls.filter(([, i]) => i?.method === "POST")[n]?.[1];
  return init?.body === undefined ? undefined : JSON.parse(String(init.body));
}

const summary = () => screen.getByTestId("fix-summary");
const inSummary = () => within(summary());
const proofRows = () => inSummary().getAllByTestId("proof-row");
const rowNames = () => Array.from(summary().querySelectorAll("dt")).map((dt) => text(dt));
const card = () => within(inSummary().getByTestId("fix-proposal"));
const cardStatus = () => text(card().getByTestId("proposal-status"));
const connect = () => inSummary().getByRole("button", { name: "Connect demo code" }) as HTMLButtonElement;
const listRow = (fixId: string) => screen.getAllByTestId("fix-row").find((r) => r.getAttribute("data-key") === fixId)!;

describe("Fixes, a library's fix from Otto: the two proof rows", () => {
  it("shows two plain rows in place of the Proof line: Passed on public copies, Not yet in this assessment", async () => {
    await open(fixesWith([updateFix(), tlsFix]), UPDATE_FIX);
    // The rows are named by the view; there is no row called Proof, and nothing reads "None".
    expect(rowNames()).toEqual(["What it suggests", PUBLIC_LABEL, HERE_LABEL, "Who approves"]);
    expect(inSummary().queryByTestId("fix-proof")).toBeNull();
    expect(text(summary())).not.toContain("None. This suggestion is text only");
    const [onPublic, here] = proofRows();
    expect(proofRows().map((r) => r.getAttribute("data-key"))).toEqual(["public", "here"]);
    expect(text(within(onPublic!).getByTestId("proof-row-badge"))).toBe("Passed");
    expect(within(onPublic!).getByTestId("proof-row-badge").getAttribute("data-tone")).toBe("pass");
    expect(text(within(onPublic!).getByTestId("proof-row-text"))).toBe("6.5.6 fails the advisory check; 6.5.7 passes.");
    expect(text(within(here!).getByTestId("proof-row-badge"))).toBe("Not yet");
    expect(within(here!).getByTestId("proof-row-badge").getAttribute("data-tone")).toBe("neutral");
    expect(text(within(here!).getByTestId("proof-row-text"))).toBe("Update the library, then press Retest.");
    // the second row says plainly what a retest here runs on; the first row is the pack's trial and has no such note
    expect(text(within(here!).getByTestId("proof-row-note"))).toBe(HERE_NOTE);
    // 22 November 2026: where each row came from, beside its word: the pack's trial ran on public copies here; "Not yet" has none
    expect(
      within(onPublic!)
        .getAllByTestId("source-tag")
        .map((t) => t.textContent),
    ).toEqual(["Proven in the lab"]);
    expect(within(onPublic!).getByTestId("source-tag").getAttribute("title")).toBe(
      "Run on a copy on this computer, never on your live system.",
    );
    expect(within(here!).queryAllByTestId("source-tag")).toEqual([]);
    expect(within(onPublic!).queryByTestId("proof-row-note")).toBeNull();
    // The fix is still text only, and still labelled as Otto's.
    expect(text(inSummary().getByTestId("fix-status"))).toBe("Text only");
    expect(text(summary())).toContain("From Otto");
  });

  it("links the first row to the trial and folds the Otto ledger entries under it; the second row links to where Retest is and has no ledger", async () => {
    await open(fixesWith([updateFix()]), UPDATE_FIX);
    const [onPublic, here] = proofRows();
    const link = within(onPublic!).getByTestId("proof-row-link");
    expect(link.textContent).toBe("See the trial on Advisories");
    expect(link.getAttribute("href")).toBe("#/a/101/advisories?item=CVE-2024-42460");
    const ledger = within(onPublic!).getByTestId("advisory-ledger") as HTMLDetailsElement;
    expect(ledger.open).toBe(false);
    expect(text(ledger.querySelector("summary"))).toBe("Otto ledger entries (2)");
    expect(within(ledger).getAllByTestId("advisory-ledger-entry")).toHaveLength(publicPassed.ledger!.entries.length);
    expect(text(ledger)).toContain(publicPassed.ledger!.note);
    // "Then press Retest": the button is on Checks, under Retests by version, so the row's one link goes there.
    const retest = within(here!).getByTestId("proof-row-link");
    expect(retest.textContent).toBe("Retest new version is on Checks");
    expect(retest.getAttribute("href")).toBe("#/a/101/checks?group=encryption");
    expect(within(here!).queryByTestId("advisory-ledger")).toBeNull();
    // What the row is about (a public copy, not the reader's own system) comes right under its sentence, before the
    // link, at the size of the text: it qualifies the word in the chip and is never small print at the foot.
    const note = within(here!).getByTestId("proof-row-note");
    const sentence = within(here!).getByTestId("proof-row-text");
    expect(sentence.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(note.compareDocumentPosition(retest) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(note.className).not.toMatch(/text-xs|text-slate-400|text-slate-500/);
  });

  it("says Not proven on public copies, with the pack's own reason, when another locked test still fails on the fixed version", async () => {
    await open(fixesWith([javaFix]), javaFix.id);
    const [onPublic, here] = proofRows();
    expect(text(within(onPublic!).getByTestId("proof-row-badge"))).toBe("Not proven");
    expect(onPublic!.getAttribute("data-tone")).toBe("warn");
    expect(text(within(onPublic!).getByTestId("proof-row-text"))).toBe(publicNotProven.text);
    expect(publicNotProven.text).toBe(
      "17.0.2 fails the advisory check and 17.0.3 passes it, but another locked test still fails on 17.0.3.",
    );
    expect(text(within(here!).getByTestId("proof-row-badge"))).toBe("Not yet");
    // The title no longer says whether it is proven: the two rows do.
    expect(text(screen.getByTestId("detail-panel").querySelector("h2"))).toBe("Update openjdk to 17.0.3");
  });

  it("after a passing retest the second row reads Passed, with its date and the way to the retest's result", async () => {
    const retested = updateFix({ proof_rows: [publicPassed, herePassed], proposal: updateAccepted() });
    await open(fixesWith([retested]), UPDATE_FIX);
    const here = proofRows()[1]!;
    expect(text(within(here).getByTestId("proof-row-badge"))).toBe("Passed");
    expect(text(within(here).getByTestId("proof-row-text"))).toBe(
      "On 18 November 2026, 10:20 UTC the retest on elliptic 6.5.7 passed: the advisory check and every other locked pass-or-fail test.",
    );
    const link = within(here).getByTestId("proof-row-link");
    expect(link.textContent).toBe("See the retest's result");
    expect(link.getAttribute("href")).toBe("#/a/101/evidence?item=test-23");
  });

  it("a fix without the two rows keeps its Proof line exactly as it was", async () => {
    await open(fixesWith([updateFix(), tlsFix]), TLS_FIX);
    expect(inSummary().queryAllByTestId("proof-row")).toHaveLength(0);
    expect(rowNames()).toEqual(["What it suggests", "Proof", "Who approves"]);
    expect(text(inSummary().getByTestId("fix-proof"))).toBe(
      "None. This suggestion is text only: the app has not applied it or tested it.",
    );
    // ... and it is not a proposal: no card, no mark in the list.
    expect(inSummary().queryByTestId("fix-proposal")).toBeNull();
    expect(within(listRow(TLS_FIX)).queryByTestId("fix-proposal-mark")).toBeNull();
  });
});

describe("Fixes, a fix of Otto's is a proposal: a person decides", () => {
  it("shows the proposal on top of the summary: From Otto, why, Proposed, with Accept and Reject", async () => {
    const fetchMock = await open(fixesWith([updateFix()]), UPDATE_FIX);
    expect(text(card().getByTestId("proposal-label"))).toBe("From Otto");
    expect(cardStatus()).toBe("Proposed");
    expect(text(card().getByTestId("proposal-title"))).toBe("Update elliptic to 6.5.7");
    expect(text(card().getByTestId("proposal-why"))).toContain("its publisher names 6.5.7 as the fixed version");
    expect(text(card().getByTestId("proposal-note"))).toBe(
      "Accept records your decision. It runs nothing and changes nothing on any system.",
    );
    expect((card().getByTestId("proposal-accept") as HTMLButtonElement).disabled).toBe(false);
    expect((card().getByTestId("proposal-reject") as HTMLButtonElement).disabled).toBe(false);
    // Looking at it asked for the view and nothing else.
    expect(asked(fetchMock)).toEqual([FIXES]);
  });

  it("Accept records one decision and then reads the Fixes view again", async () => {
    const before = fixesWith([updateFix()]);
    const after = fixesWith([updateFix({ proposal: updateAccepted() })]);
    const fetchMock = await open([before, after], UPDATE_FIX, {
      [decide(UPDATE_PROPOSAL, "accept")]: { body: updateAccepted() },
    });
    fireEvent.click(card().getByTestId("proposal-accept"));
    await waitFor(() => expect(cardStatus()).toBe("Accepted"));
    expect(asked(fetchMock)).toEqual([FIXES, decide(UPDATE_PROPOSAL, "accept"), FIXES]);
    expect(posted(fetchMock)).toEqual({});
    // What the view now sends: who decided and when, what comes next, and Undo in place of Accept and Reject.
    expect(text(card().getByTestId("proposal-decided"))).toBe("Accepted by You on 18 November 2026, 10:02 UTC.");
    expect(text(card().getByTestId("proposal-effect"))).toBe(
      "Next: whoever owns the software updates it; then press Retest.",
    );
    expect(card().queryByTestId("proposal-accept")).toBeNull();
    expect((card().getByTestId("proposal-undo") as HTMLButtonElement).disabled).toBe(false);
    // The list says the same.
    expect(text(within(listRow(UPDATE_FIX)).getByTestId("fix-proposal-status"))).toBe("Accepted");
  });

  it("Reject asks for an optional short reason, records it, reads the view again, and the fix stays as Not added (reason)", async () => {
    const reason = "We replace elliptic next month";
    const before = fixesWith([updateFix()]);
    const after = fixesWith([updateFix({ proposal: updateRejected(reason) })]);
    const fetchMock = await open([before, after], UPDATE_FIX, {
      [decide(UPDATE_PROPOSAL, "reject")]: { body: updateRejected(reason) },
    });
    fireEvent.click(card().getByTestId("proposal-reject"));
    const box = screen.getByTestId("proposal-reject-dialog");
    expect(text(box)).toContain("It is not deleted");
    // Opening the box recorded nothing.
    expect(asked(fetchMock)).toEqual([FIXES]);
    fireEvent.change(within(box).getByTestId("proposal-reject-reason"), { target: { value: reason } });
    fireEvent.click(within(box).getByTestId("proposal-reject-confirm"));
    await waitFor(() => expect(cardStatus()).toBe(`Not added (${reason})`));
    expect(asked(fetchMock)).toEqual([FIXES, decide(UPDATE_PROPOSAL, "reject"), FIXES]);
    expect(posted(fetchMock)).toEqual({ reason });
    expect(screen.queryByTestId("proposal-reject-dialog")).toBeNull();
    // Nothing is deleted: the fix is still listed, with its rows, its reason and the way to take it up again.
    expect(proofRows()).toHaveLength(2);
    expect(text(card().getByTestId("proposal-decided"))).toContain(`Reason: ${reason}`);
    expect((card().getByTestId("proposal-reconsider") as HTMLButtonElement).disabled).toBe(false);
    expect(text(within(listRow(UPDATE_FIX)).getByTestId("fix-proposal-status"))).toBe(`Not added (${reason})`);
  });

  it("Undo of an accept records one decision, reads the view again, and the proposal is open for a decision once more", async () => {
    const accepted = fixesWith([updateFix({ proposal: updateAccepted() })]);
    const undone = updateProposal({
      decided_line: "Accept undone by You on 18 November 2026, 10:05 UTC. It is open for a decision again.",
    });
    const again = fixesWith([updateFix({ proposal: undone })]);
    const fetchMock = await open([accepted, again], UPDATE_FIX, {
      [decide(UPDATE_PROPOSAL, "undo")]: { body: undone },
    });
    expect(cardStatus()).toBe("Accepted");
    fireEvent.click(card().getByTestId("proposal-undo"));
    await waitFor(() => expect(cardStatus()).toBe("Proposed"));
    expect(asked(fetchMock)).toEqual([FIXES, decide(UPDATE_PROPOSAL, "undo"), FIXES]);
    expect(text(card().getByTestId("proposal-decided"))).toContain("Accept undone by You");
    expect((card().getByTestId("proposal-accept") as HTMLButtonElement).disabled).toBe(false);
  });

  it("Reconsider takes a rejected proposal up again", async () => {
    const rejected = fixesWith([updateFix({ proposal: updateRejected() })]);
    const again = fixesWith([updateFix()]);
    const fetchMock = await open([rejected, again], UPDATE_FIX, {
      [decide(UPDATE_PROPOSAL, "reconsider")]: { body: updateProposal() },
    });
    fireEvent.click(card().getByTestId("proposal-reconsider"));
    await waitFor(() => expect(cardStatus()).toBe("Proposed"));
    expect(asked(fetchMock)).toEqual([FIXES, decide(UPDATE_PROPOSAL, "reconsider"), FIXES]);
  });

  it("a refusal is shown in the backend's words, and the view is not read again", async () => {
    const locked = "A retest has run on the updated version, so this accept stands.";
    const fetchMock = await open(fixesWith([updateFix({ proposal: updateAccepted() })]), UPDATE_FIX, {
      [decide(UPDATE_PROPOSAL, "undo")]: { status: 409, body: { error: { message: locked, line: null, field: null } } },
    });
    fireEvent.click(card().getByTestId("proposal-undo"));
    await waitFor(() => expect(text(inSummary().getByTestId("fix-proposal"))).toContain(locked));
    expect(asked(fetchMock)).toEqual([FIXES, decide(UPDATE_PROPOSAL, "undo")]);
    expect(cardStatus()).toBe("Accepted");
  });

  it("an accept that can no longer be undone has Undo switched off, with the reason", async () => {
    const reason = "A retest has run on the updated version, so this accept stands.";
    const proposal: OttoProposal = {
      ...updateAccepted(),
      buttons: [{ key: "undo", label: "Undo", can: false, blocked_reason: reason }],
      note: null,
    };
    const fetchMock = await open(
      fixesWith([updateFix({ proof_rows: [publicPassed, herePassed], proposal })]),
      UPDATE_FIX,
    );
    expect((card().getByTestId("proposal-undo") as HTMLButtonElement).disabled).toBe(true);
    expect(text(card().getByTestId("proposal-blocked"))).toBe(reason);
    fireEvent.click(card().getByTestId("proposal-undo"));
    expect(asked(fetchMock)).toEqual([FIXES]);
  });

  it("in a closed assessment the decision buttons are off, and the rows and the proposal can still be read", async () => {
    const fetchMock = await open(fixesWith([updateFix()]), UPDATE_FIX, {}, true);
    for (const id of ["proposal-accept", "proposal-reject"]) {
      const button = card().getByTestId(id) as HTMLButtonElement;
      expect(button.disabled, id).toBe(true);
      expect(button.getAttribute("title"), id).toBe(CLOSED_SENTENCE);
    }
    expect(proofRows()).toHaveLength(2);
    expect(asked(fetchMock)).toEqual([FIXES]);
  });
});

describe("Fixes, Otto's own change: nothing runs without a click", () => {
  it("opening Fixes on a proposed change sends only reads, and Connect demo code is off with the backend's reason", async () => {
    const fetchMock = await open(fixesWith([ottoCodeFix(codeProposal()), tlsFix]), CODE_FIX);
    expect(cardStatus()).toBe("Proposed");
    expect(text(summary())).toContain("Written by Otto");
    expect(connect().disabled).toBe(true);
    expect(text(inSummary().getByTestId("fix-actions"))).toContain(NOT_ACCEPTED);
    // A click on the switched-off button does nothing, and the proof has not started.
    fireEvent.click(connect());
    expect(text(inSummary().getByTestId("fix-proof"))).toContain("Not started");
    expect(calls(fetchMock).every((c) => c.startsWith("GET "))).toBe(true);
    expect(asked(fetchMock)).toEqual([FIXES]);
  });

  it("Accept records the decision only; the code is connected by its own click afterwards", async () => {
    const before = fixesWith([ottoCodeFix(codeProposal()), tlsFix]);
    const after = fixesWith([ottoCodeFix(codeAccepted()), tlsFix]);
    const fetchMock = await open([before, after], CODE_FIX, {
      [decide(CODE_PROPOSAL, "accept")]: { body: codeAccepted() },
      [CONNECT]: { body: after },
    });
    fireEvent.click(card().getByTestId("proposal-accept"));
    await waitFor(() => expect(cardStatus()).toBe("Accepted"));
    // Accepting ran nothing: one decision, then the view again. No connect, no proof.
    expect(asked(fetchMock)).toEqual([FIXES, decide(CODE_PROPOSAL, "accept"), FIXES]);
    expect(connect().disabled).toBe(false);
    expect(text(inSummary().getByTestId("fix-actions"))).toContain(CONNECT_NOTE);
    expect(text(inSummary().getByTestId("fix-actions"))).not.toContain(NOT_ACCEPTED);
    expect(text(card().getByTestId("proposal-effect"))).toContain("Next: Connect demo code.");
    // Only the person's own click connects the code.
    fireEvent.click(connect());
    await waitFor(() => expect(asked(fetchMock)).toEqual([FIXES, decide(CODE_PROPOSAL, "accept"), FIXES, CONNECT]));
  });

  it("a rejected change keeps Connect demo code off, and stays listed as Not added with its reason", async () => {
    const reason = "We fix this ourselves";
    const rejected = {
      ...updateRejected(reason),
      ...{ id: CODE_PROPOSAL, title: codeProposal().title, why: codeProposal().why, lines: codeProposal().lines },
    };
    const view = fixesWith([
      {
        ...ottoCodeFix(rejected),
        actions: {
          buttons: [{ action: "connect", label: "Connect demo code", primary: true, enabled: false }],
          note: "This proposal was rejected, so its change is not added. Reconsider takes it up again.",
        },
      },
      tlsFix,
    ]);
    const fetchMock = await open(view, CODE_FIX);
    expect(cardStatus()).toBe(`Not added (${reason})`);
    expect(connect().disabled).toBe(true);
    expect(text(inSummary().getByTestId("fix-actions"))).toContain("Reconsider takes it up again.");
    expect((card().getByTestId("proposal-reconsider") as HTMLButtonElement).disabled).toBe(false);
    expect(asked(fetchMock)).toEqual([FIXES]);
  });
});

describe("Fixes, the list: Otto's fixes say they are proposals", () => {
  it("shows From Otto and where the proposal stands under the fix's name, beside an open panel and with the panel closed", async () => {
    await open(fixesWith([updateFix(), javaFix, tlsFix]), UPDATE_FIX);
    const marked = () => within(listRow(UPDATE_FIX));
    // Beside the open panel the table is in its compact form: the mark sits under the name there too.
    expect(screen.getAllByTestId("data-table").every((table) => table.getAttribute("data-compact") === "true")).toBe(
      true,
    );
    expect(marked().getByTestId("fix-proposal-label").textContent).toBe("From Otto");
    expect(text(marked().getByTestId("fix-proposal-status"))).toBe("Proposed");
    fireEvent.click(within(screen.getByTestId("detail-panel")).getByRole("button", { name: "Close details" }));
    await waitFor(() => expect(screen.queryByTestId("fix-summary")).toBeNull());
    expect(screen.getAllByTestId("data-table").some((table) => table.getAttribute("data-compact") === "true")).toBe(
      false,
    );
    expect(marked().getByTestId("fix-proposal-label").textContent).toBe("From Otto");
    expect(text(marked().getByTestId("fix-proposal-status"))).toBe("Proposed");
    // Every fix of Otto's carries it; a fix that is not Otto's carries none.
    expect(screen.getAllByTestId("fix-proposal-status")).toHaveLength(2);
    expect(within(listRow(TLS_FIX)).queryByTestId("fix-proposal-mark")).toBeNull();
  });

  it("finds a fix by the word its proposal stands at", async () => {
    await open(fixesWith([updateFix({ proposal: updateRejected("Not this quarter") }), tlsFix]), TLS_FIX);
    fireEvent.change(screen.getByRole("searchbox", { name: "Search fixes" }), { target: { value: "not added" } });
    await waitFor(() =>
      expect(screen.getAllByTestId("fix-row").map((r) => r.getAttribute("data-key"))).toEqual([UPDATE_FIX, TLS_FIX]),
    );
    // (the open fix stays listed whatever the search; the other one is there because its proposal's word matches)
    fireEvent.change(screen.getByRole("searchbox", { name: "Search fixes" }), { target: { value: "no such words" } });
    await waitFor(() =>
      expect(screen.getAllByTestId("fix-row").map((r) => r.getAttribute("data-key"))).toEqual([TLS_FIX]),
    );
  });
});

// The two row labels are the view's: these are only what the fixtures stand in for.
describe("the fixtures' row words", () => {
  it("are the words the backend sends", () => {
    expect([publicPassed.line, hereNotYet.line]).toEqual([
      "Proven on public copies: Passed. 6.5.6 fails the advisory check; 6.5.7 passes.",
      "Proven in this assessment: Not yet. Update the library, then press Retest.",
    ]);
  });
});
