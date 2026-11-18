import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { OttoResultBlock } from "../api";
import { ResultDetail } from "../components/lab/ResultDetail";
import { LinkProvider } from "../components/related";
import { text, vectorsResult } from "./fixtures";

/** Phase 5c, second part (Kevin, 18 November 2026): "Evidence: each result from an Otto check shows the advisory, the
 * test design, the trial on public copies, the ledger entries, and the accept/reject decisions with who and when."
 * The block is a record of where the check came from. Every word is the view's; it has no button and no result look. */

const ADVISORY = "CVE-2022-21449";
const SHA = "7b06a70535ac437d660e31e54dd0f01dedf7dc784d79ae0fc64cffc34e5384cc";

const block: OttoResultBlock = {
  label: "From Otto",
  title: "Where this check came from",
  line:
    "Otto proposed this check from the advisory “Missing ECDSA signature range check (CVE-2022-21449)”, in test pack 2026.11.1. " +
    "Accepted by You on 18 November 2026, 05:53 UTC.",
  advisory: { label: "Open the advisory", link: { page: "advisories", item: ADVISORY } },
  design: {
    title: "The test's design",
    lines: [
      `Design fingerprint (SHA-256): ${SHA}`,
      "Its question, its control that must fail and its pass rule are in the test details, locked before the run.",
    ],
  },
  trial: {
    title: "How the test did when it was tried on public copies",
    lines: [
      "openjdk 17.0.2 (affected): 10 of 77 cases wrong.",
      "openjdk 17.0.3 (the publisher's fixed version): 0 of 77 cases wrong.",
      "The control that must fail (a program that accepts every signature): 77 of 77 cases wrong.",
    ],
  },
  decisions: {
    title: "Decisions on Otto's proposal",
    count: 3,
    rows: [
      {
        number: 1,
        word: "Rejected",
        by: "You",
        at: "2026-11-18T05:51:02Z",
        at_text: "18 November 2026, 05:51 UTC",
        reason: "Not this quarter",
        ledger_entry: "106a5f9110af",
        line: "1. Rejected by You on 18 November 2026, 05:51 UTC: Not this quarter.",
      },
      {
        number: 2,
        word: "Taken up again",
        by: "You",
        at: "2026-11-18T05:52:10Z",
        at_text: "18 November 2026, 05:52 UTC",
        reason: null,
        ledger_entry: "d109ff77031c",
        line: "2. Taken up again by You on 18 November 2026, 05:52 UTC.",
      },
      {
        number: 3,
        word: "Accepted",
        by: "You",
        at: "2026-11-18T05:53:46Z",
        at_text: "18 November 2026, 05:53 UTC",
        reason: null,
        ledger_entry: "e5d9f2e33b37",
        line: "3. Accepted by You on 18 November 2026, 05:53 UTC.",
      },
    ],
    footnote: "This version has one login and no separate accounts. Whoever is at the keyboard records each decision, under the name shown.",
    empty: null,
  },
  ledger: {
    title: "Otto ledger entries for this check and its decisions",
    count: 4,
    entries: [
      { seq: 0, kind: "Opened", id: "56182a377c5d", at: "2026-11-18T05:51:02+00:00", what: "Proposal entry: names what Otto proposed, written with the first decision on it" },
      { seq: 1, kind: "Recorded", id: "106a5f9110af", at: "2026-11-18T05:51:02+00:00", what: "Decision 1: rejected by You" },
      { seq: 5, kind: "Opened", id: "ddfe22721c13", at: "2026-11-18T05:53:46+00:00", what: "Lock entry: the test's fingerprint, its design and its pack, written before any run" },
      { seq: 8, kind: "Recorded", id: "a2011827a5af", at: "2026-11-18T05:54:10+00:00", what: "Run 1 (first run) bound to the locked test" },
    ],
    note: "The lock entry was written before the check could run; each reviewed run and each decision added an entry. The ledger holds no result.",
  },
  note: "This says where the check came from and who decided to add it. The result comes only from the test.",
};

function open(otto: OttoResultBlock | null | undefined) {
  return render(
    <LinkProvider assessmentId={4} planId={7}>
      <ResultDetail result={{ ...vectorsResult, otto }} busy={false} />
    </LinkProvider>,
  );
}

describe("Evidence, a result of an advisory check: where the check came from", () => {
  it("says which advisory and pack it came from, with the way to the advisory", () => {
    open(block);
    const box = screen.getByTestId("result-otto");
    expect(text(within(box).getByTestId("result-otto-label"))).toBe("From Otto");
    expect(text(box)).toContain("Where this check came from");
    expect(text(within(box).getByTestId("result-otto-line"))).toContain(block.line);
    const link = within(box).getByTestId("result-otto-advisory");
    expect(text(link)).toBe("Open the advisory");
    expect(link.getAttribute("href")).toBe(`#/a/4/advisories?item=${ADVISORY}`);
  });

  it("shows the test's design by its fingerprint and the trial on public copies, in the view's counts", () => {
    open(block);
    expect(text(screen.getByTestId("result-otto-design"))).toContain(`Design fingerprint (SHA-256): ${SHA}`);
    const trial = screen.getByTestId("result-otto-trial");
    expect(text(trial)).toContain("How the test did when it was tried on public copies");
    for (const line of block.trial!.lines) expect(text(trial)).toContain(line);
  });

  it("lists every decision on Otto's proposal with who and when, and the reason of a rejection", () => {
    open(block);
    const decisions = screen.getByTestId("result-otto-decisions");
    expect(decisions.getAttribute("data-count")).toBe("3");
    expect(within(decisions).getAllByTestId("result-otto-decision").map(text)).toEqual(block.decisions.rows.map((row) => row.line));
    expect(text(decisions)).toContain("1. Rejected by You on 18 November 2026, 05:51 UTC: Not this quarter.");
    expect(text(decisions)).toContain(block.decisions.footnote);
  });

  it("lists the Otto ledger entries, folded, with the note that the ledger holds no result", () => {
    open(block);
    const ledger = within(screen.getByTestId("result-otto")).getByTestId("advisory-ledger");
    expect(ledger.tagName).toBe("DETAILS");
    expect((ledger as HTMLDetailsElement).open).toBe(false);
    expect(within(ledger).getAllByTestId("advisory-ledger-entry")).toHaveLength(4);
    expect(text(ledger)).toContain("The ledger holds no result.");
  });

  it("is a record only: no button, no result look of its own, and the note says where the result comes from", () => {
    open(block);
    const box = screen.getByTestId("result-otto");
    expect(within(box).queryAllByRole("button")).toEqual([]);
    expect(box.querySelector("[data-testid='result-badge']")).toBeNull();
    expect(text(within(box).getByTestId("result-otto-note"))).toBe(block.note);
  });

  it("says so when the check was added before decisions were recorded", () => {
    const empty = "No decision is on record: this check was added before decisions were recorded.";
    open({ ...block, decisions: { ...block.decisions, count: 0, rows: [], empty } });
    expect(text(screen.getByTestId("result-otto-no-decision"))).toBe(empty);
    expect(screen.queryByTestId("result-otto-decision")).toBeNull();
  });

  it("leaves the trial out when the installed packs no longer hold it", () => {
    open({ ...block, trial: null });
    expect(screen.queryByTestId("result-otto-trial")).toBeNull();
    expect(screen.getByTestId("result-otto-design")).not.toBeNull();
  });

  it("is not drawn on a result that is not an advisory check's", () => {
    open(undefined);
    expect(screen.queryByTestId("result-otto")).toBeNull();
    open(null);
    expect(screen.queryByTestId("result-otto")).toBeNull();
  });
});
