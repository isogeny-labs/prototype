// Phase 5c, second part: Otto's fixes as the Fixes step shows them. A library's fix has two proof rows ("Proven on
// public copies", "Proven on your system") in place of the one Proof line, and every fix of Otto's is a proposal a
// person accepts or rejects. Every word here stands in for the backend's (backend/app/present/otto.py and fixes.py).
import type { AdvisoryLedger, FixDetail, FixProofRow, FixesView, OttoProposal } from "../api";
import { CODE_FIX, fixGroups, fixesViews, tlsFix } from "./fixesFixtures";
import { acceptedProposal, proposal, rejectedProposal } from "./proposalFixtures";

const t = (v: string) => ({ t: "text" as const, v });
const m = (v: string) => ({ t: "mono" as const, v });

export const PUBLIC_LABEL = "Proven on public copies";
export const HERE_LABEL = "Proven on your system";

/** One proof row as the view sends it: the row's own word and tone, its sentence, its links and (first row) the ledger. */
export function proofRow(
  key: FixProofRow["key"],
  word: string,
  tone: FixProofRow["badge"]["tone"],
  text: string,
  links: FixProofRow["links"] = [],
  ledger: AdvisoryLedger | null = null,
): FixProofRow {
  const label = key === "public" ? PUBLIC_LABEL : HERE_LABEL;
  // The row's chip is a word and a tone, as the backend words it. The second row also says what a retest here runs on.
  const note = key === "here" ? HERE_NOTE : null;
  return { key, label, badge: { label: word, tone } as FixProofRow["badge"], text, line: `${label}: ${word}. ${text}`, links, ledger, note };
}

/** Under the second row: what the row is about (a public copy of the updated version, not the system you run). */
export const HERE_NOTE =
  "This row is about a public copy, not the system you run. A retest reruns the same locked tests on a public copy of the updated version, on this computer. The app has not checked that your own system was updated: in this version it does not connect to it.";

/** The research ledger's entries behind a first row, folded under it. */
export const researchLedger: AdvisoryLedger = {
  title: "Otto ledger entries",
  count: 2,
  entries: [
    { seq: 41, kind: "Registered", id: "31469ae34ab1", at: "2026-11-18T00:31:00+00:00", what: "Trial registered: the fix for CVE-2024-42460" },
    { seq: 47, kind: "Judged", id: "d01078b87c71", at: "2026-11-18T00:36:00+00:00", what: "Trial judged against thresholds fixed before the first run" },
  ],
  note: "From Otto's research ledger, a hash chain kept with the Otto harness: the test and the fix were registered, tried and judged before the pack was signed.",
};

const TRIAL_LINK = (advisory: string) => [{ label: "See the trial on Advisories", link: { page: "advisories", item: advisory } }];

export const publicPassed = proofRow("public", "Passed", "pass", "6.5.6 fails the advisory check; 6.5.7 passes.", TRIAL_LINK("CVE-2024-42460"), researchLedger);
export const publicNotProven = proofRow(
  "public",
  "Not proven",
  "warn",
  "17.0.2 fails the advisory check and 17.0.3 passes it, but another locked test still fails on 17.0.3.",
  TRIAL_LINK("CVE-2022-21449"),
  { ...researchLedger, entries: researchLedger.entries.slice(0, 1), count: 1 },
);
/** Where the retest is started: the row says "press Retest", and the button ("Retest new version") is on Checks, under
 * Retests by version (the 5c fixes). */
export const RETEST_LINK: FixProofRow["links"] = [{ label: "Retest new version is on Checks", link: { page: "checks", item: null, group: "encryption" } }];
export const hereNotYet = proofRow("here", "Not yet", "neutral", "Update the library, then press Retest.", RETEST_LINK);
export const herePassed = proofRow(
  "here",
  "Passed",
  "pass",
  "On 18 November 2026, 10:20 UTC the retest on elliptic 6.5.7 passed: the advisory check and every other locked pass-or-fail test.",
  [{ label: "See the retest's result", link: { page: "evidence", item: "test-23" } }],
);

export const UPDATE_FIX = "fix-advisory-cases-23";
export const UPDATE_PROPOSAL = "fix-update-23";
export const CODE_PROPOSAL = "fix-code-otto-cve-2022-21449";
export const NOT_ACCEPTED = "This change is a proposal. Accept it first; accepting runs nothing.";
export const CONNECT_NOTE =
  "Connects a fresh copy of the small demo repository of acme-sign 1.4.2 that comes with the app (the source code and its history of changes, in git's format), for this imported file and every fix in it. The proof then starts by itself.";

/** Otto's proposal for a library update, in the three states a person's decisions leave it in. */
export const updateProposal = (over: Partial<OttoProposal> = {}): OttoProposal =>
  proposal({
    id: UPDATE_PROPOSAL,
    kind: "fix",
    kind_label: "fix",
    title: "Update elliptic to 6.5.7",
    why: "The advisory check for CVE-2024-42460 (Wrongly encoded signature accepted) failed on elliptic 6.5.6, and its publisher names 6.5.7 as the fixed version.",
    why_label: "Why it is proposed",
    lines: [
      "Update the elliptic npm package to version 6.5.7, which the advisory record gives as the fixed version.",
      "Proven on public copies: Passed. 6.5.6 fails the advisory check; 6.5.7 passes.",
      "This is other people's code: the app offers no code change and no pull request for it. Whoever owns the software updates it; Retest then proves it here.",
    ],
    note: "Accept records your decision. It runs nothing and changes nothing on any system.",
    link: { page: "fixes", item: UPDATE_FIX },
    ...over,
  });
export const updateAccepted = (): OttoProposal => ({
  ...acceptedProposal(),
  ...pick(updateProposal()),
  status: { key: "accepted", word: "Accepted", tone: "pass" },
  effect: "Next: whoever owns the software updates it; then press Retest.",
  note: "Undo is possible until the fix has run or been applied.",
});
export const updateRejected = (reason = "We replace elliptic next month"): OttoProposal => ({
  ...rejectedProposal(reason),
  ...pick(updateProposal()),
});

/** What names a proposal, kept when its state changes. */
function pick(p: OttoProposal): Pick<OttoProposal, "id" | "kind" | "kind_label" | "title" | "why" | "why_label" | "lines" | "link"> {
  return { id: p.id, kind: p.kind, kind_label: p.kind_label, title: p.title, why: p.why, why_label: p.why_label, lines: p.lines, link: p.link };
}

/** A library's fix from Otto (text only): the publisher's fixed version, its two proof rows and its proposal. */
export function updateFix(over: Partial<FixDetail> = {}): FixDetail {
  return {
    ...tlsFix,
    id: UPDATE_FIX,
    title: "Update elliptic to 6.5.7",
    list_source: "Came from 1 failed test: Advisory check: Wrongly encoded signature accepted (CVE-2024-42460) on elliptic 6.5.6",
    source: [t("Came from 1 failed test on signing component "), m("elliptic 6.5.6"), t(": Advisory check: Wrongly encoded signature accepted (CVE-2024-42460).")],
    labels: ["From Otto"],
    is_demo: false,
    what: {
      label: "What it suggests",
      paragraphs: [
        [
          t(
            "From Otto, for advisory CVE-2024-42460: update the library to the version its publisher names as fixed. This is other people's code: the app offers no code change and no pull request for it.",
          ),
        ],
      ],
      server_line: null,
    },
    proof: { state: "none", badge: null, text: "In the two rows below: on public copies, and on your system.", muted: null },
    proof_rows: [publicPassed, hereNotYet],
    proposal: updateProposal(),
    approvers: { text: "Whoever looks after this software, outside this app.", options: null, rows: null, footnote: null },
    sections: [],
    ...over,
  };
}

/** The Java fix: the publisher's fixed version is named, and on public copies it is not proven (another locked test still fails). */
export const javaFix: FixDetail = updateFix({
  id: "fix-advisory-cases-21",
  title: "Update openjdk to 17.0.3",
  proof_rows: [publicNotProven, hereNotYet],
  proposal: updateProposal({ id: "fix-update-21", title: "Update openjdk to 17.0.3", link: { page: "fixes", item: "fix-advisory-cases-21" } }),
});

/** Otto's own change for acme-sign, before the code is connected, as a proposal nobody has decided yet: Connect demo
 * code arrives switched off, and the note under it starts with the backend's reason. */
export function codeProposal(over: Partial<OttoProposal> = {}): OttoProposal {
  return proposal({
    id: CODE_PROPOSAL,
    kind: "fix",
    kind_label: "fix",
    title: "Reject signatures with r or s out of range (CVE-2022-21449) (acme-sign)",
    why: "The advisory check for CVE-2022-21449 (Missing ECDSA signature range check) failed on acme-sign 1.4.2, which is your own code.",
    why_label: "Why it is proposed",
    lines: [
      "What it changes: The verify command now rejects a signature unless both of its numbers, r and s, are from 1 to n - 1, where n is the curve order.",
      "Written by Otto. Accepting it runs nothing and changes nothing: you then connect the code, and the proof reruns every locked test on the changed code before anything is offered for review.",
    ],
    note: "Accept records your decision. It runs nothing and changes nothing on any system.",
    link: { page: "fixes", item: CODE_FIX },
    ...over,
  });
}
export const codeAccepted = (): OttoProposal => ({
  ...acceptedProposal(),
  ...pick(codeProposal()),
  status: { key: "accepted", word: "Accepted", tone: "pass" },
  effect: "Next: Connect demo code. The change goes on a branch, and the proof reruns every locked test on it.",
  note: "Undo is possible until the fix has run or been applied.",
});

const notConnected = fixesViews.not_connected.fixes.find((f) => f.id === CODE_FIX)!;

/** Otto's code fix, not connected: with the proposal in the given state. Only an accepted one has Connect switched on. */
export function ottoCodeFix(state: OttoProposal): FixDetail {
  const accepted = state.status.key === "accepted";
  return {
    ...notConnected,
    title: "acme-sign: Reject signatures with r or s out of range (CVE-2022-21449)",
    labels: ["Written by Otto"],
    proposal: state,
    actions: {
      buttons: [{ action: "connect", label: "Connect demo code", primary: true, enabled: accepted }],
      note: accepted ? CONNECT_NOTE : `${NOT_ACCEPTED} ${CONNECT_NOTE}`,
    },
  };
}

/** A Fixes view that holds exactly these fixes (all from failed tests: Crypto tests). */
export function fixesWith(fixes: FixDetail[]): FixesView {
  return {
    ...fixesViews.not_connected,
    is_demo: false,
    list_title: `Open findings with a fix (${fixes.length})`,
    fixes,
    busy: false,
    groups: fixGroups(fixes),
  };
}
