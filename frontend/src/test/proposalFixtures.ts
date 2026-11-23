import type { OttoProposal } from "../api";

/** Phase 5c: one of Otto's proposals as the backend sends it, for screen tests. Every word here stands in for the
 * backend's; a test changes only what it is about. */
export function proposal(over: Partial<OttoProposal> = {}): OttoProposal {
  return {
    id: "check-cve-2022-21449-f3ea2161c217",
    kind: "check",
    kind_label: "check",
    label: "From Otto",
    title: "Advisory check: Missing ECDSA signature range check (CVE-2022-21449) on acme-sign 1.4.2",
    why: "acme-sign 1.4.2 checks ECDSA P-256 signatures, and this test hands a program published signature cases of the kind the advisory describes.",
    why_label: "Why it applies",
    lines: [
      "Does acme-sign 1.4.2 reject the signatures that advisory CVE-2022-21449 describes?",
      "77 published cases from Project Wycheproof, pinned by SHA-256.",
      "Control that must fail: a program that accepts every signature.",
    ],
    status: { key: "proposed", word: "Proposed", tone: "warn" },
    decided_line: "Nobody has decided this yet.",
    effect: null,
    buttons: [
      { key: "accept", label: "Accept", can: true, blocked_reason: null },
      { key: "reject", label: "Reject", can: true, blocked_reason: null },
    ],
    note: "Accept adds this check to the test plan, exactly as “+ Add test” would. It runs nothing.",
    reject_dialog: {
      title: "Reject this proposal?",
      line: "It is not deleted: it stays on the record as “Not added”, with your reason, and can be taken up again later.",
      reason_label: "Reason (optional, one short line)",
      max: 300,
      confirm: "Reject",
      cancel: "Cancel",
    },
    history: {
      title: "Decisions on this proposal",
      count: 0,
      rows: [],
      footnote:
        "This version has one login and no separate accounts. Whoever is at the keyboard records each decision, under the name shown.",
      ledger: null,
    },
    link: { page: "advisories", item: "CVE-2022-21449" },
    proposed_at: "2026-11-18T09:00:00Z",
    ...over,
  };
}

/** The same proposal after Accept: its word for this kind, who decided and when, and Undo. */
export function acceptedProposal(over: Partial<OttoProposal> = {}): OttoProposal {
  return proposal({
    status: { key: "accepted", word: "Added", tone: "pass" },
    decided_line: "Accepted by You on 18 November 2026, 10:02 UTC.",
    effect: "It is in the test plan, on Checks. It has not run yet.",
    buttons: [{ key: "undo", label: "Undo", can: true, blocked_reason: null }],
    note: "Undo takes it out of the test plan again, until it has run.",
    reject_dialog: null,
    history: {
      title: "Decisions on this proposal",
      count: 1,
      rows: [
        {
          number: 1,
          word: "Accepted",
          by: "You",
          at: "2026-11-18T10:02:00Z",
          at_text: "18 November 2026, 10:02 UTC",
          reason: null,
          ledger_entry: "a1b2c3d4e5f6",
          line: "1. Accepted by You on 18 November 2026, 10:02 UTC.",
        },
      ],
      footnote:
        "This version has one login and no separate accounts. Whoever is at the keyboard records each decision, under the name shown.",
      ledger: null,
    },
    ...over,
  });
}

/** The same proposal after Reject with a reason: "Not added (reason)", kept on the record, with Reconsider. */
export function rejectedProposal(reason = "Not this quarter", over: Partial<OttoProposal> = {}): OttoProposal {
  return proposal({
    status: { key: "rejected", word: `Not added (${reason})`, tone: "neutral" },
    decided_line: `Rejected by You on 18 November 2026, 10:03 UTC. Reason: ${reason}`,
    effect: null,
    buttons: [{ key: "reconsider", label: "Reconsider", can: true, blocked_reason: null }],
    note: null,
    reject_dialog: null,
    history: {
      title: "Decisions on this proposal",
      count: 1,
      rows: [
        {
          number: 1,
          word: "Rejected",
          by: "You",
          at: "2026-11-18T10:03:00Z",
          at_text: "18 November 2026, 10:03 UTC",
          reason,
          ledger_entry: "b2c3d4e5f6a1",
          line: `1. Rejected by You on 18 November 2026, 10:03 UTC: ${reason}.`,
        },
      ],
      footnote:
        "This version has one login and no separate accounts. Whoever is at the keyboard records each decision, under the name shown.",
      ledger: null,
    },
    ...over,
  });
}
