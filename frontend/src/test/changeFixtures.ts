import type { ChangeButton, ChangeStep, ChangeView, RichText } from "../api";
import { result } from "./fixtures";

// Phase 4b change boxes in each state the demo goes through, worded as in the approved mockups.

export const CHANGE_ID = "migration:server:localhost:8452";
export const TLS_CHANGE_ID = "tls:server:localhost:8443";

const t = (v: string): RichText => [{ t: "text", v }];
const m = (v: string): RichText[number] => ({ t: "mono", v });
const tag = (v: string): RichText[number] => ({ t: "tag", v });

const btn = (action: ChangeButton["action"], label: string, primary: boolean, enabled = true, reason: string | null = null): ChangeButton => ({
  action,
  label,
  primary,
  enabled,
  reason,
});

const step = (key: ChangeStep["key"], label: string, state: ChangeStep["state"], text: string): ChangeStep => ({ key, label, state, text });

export const tryEvidence = {
  ...result(61, "offered", "Hybrid", "pass", "The copy asked for X25519MLKEM768 in its first answer."),
  component: null,
};

const tryTable = {
  columns: ["", "Before: localhost:8452 as measured", "After: a test copy with the change"],
  rows: [
    { label: "Key exchange", cells: [[m("Classical"), tag("measured")], [m("Hybrid (interim)"), tag("measured on the copy")]] },
    { label: "Classical-only clients", cells: [[{ t: "text" as const, v: "connect " }, tag("measured")], [{ t: "text" as const, v: "still connect " }, tag("measured on the copy")]] },
    { label: "First message", cells: [[{ t: "text" as const, v: "1,412 bytes " }, tag("measured")], [{ t: "text" as const, v: "2,580 bytes " }, tag("measured on the copy")]] },
  ] as { label: string; cells: RichText[] }[],
};

const SECTIONS: ChangeView["sections"] = [
  {
    kind: "table",
    title: "What changes",
    columns: ["", "Today", "After the change"],
    rows: [
      [[{ t: "text", v: "Key exchange" }], [{ t: "text", v: "Classical (X25519)" }], [{ t: "text", v: "Hybrid: X25519MLKEM768 first" }]],
      [[{ t: "text", v: "Certificate" }], [{ t: "text", v: "ECDSA P-256" }], [{ t: "text", v: "Unchanged" }]],
    ],
  },
  {
    kind: "lines",
    title: "The exact lines",
    rows: [
      { place: "tls.conf", lead: "Set the preferred groups:", code: "ssl_ecdh_curve X25519MLKEM768:X25519:prime256v1;" },
      { place: "reload", lead: "Then reload:", code: "nginx -s reload" },
    ],
    note: "Nothing is sent to your server by this app.",
  },
  { kind: "text", title: "What it costs", paragraphs: [t("Plainly: bigger first messages and two algorithms to keep up to date.")] },
];

const FOOTNOTE = "This version has one login and no separate accounts. Each approval is recorded by name only.";

function base(over: Partial<ChangeView>): ChangeView {
  return {
    id: CHANGE_ID,
    title: "Your change: turn on hybrid key exchange on localhost:8452",
    badge: { label: "Ready to try", look: "neutral" },
    intro: [...t("Built from your choice. It is only a description until you try it and apply it: "), m("localhost:8452"), ...t(" has not changed.")],
    steps: [
      step("built", "Built", "done", "5:08 PM"),
      step("tried", "Tried on a test copy", "now", "not tried yet"),
      step("approvals", "Approvals", "off", ""),
      step("applied", "Apply", "off", ""),
      step("measured", "Measured after", "off", ""),
    ],
    sections: SECTIONS,
    try: null,
    approvals: null,
    applied: null,
    buttons: [
      btn("try", "Try on a test copy", true),
      btn("apply", "Apply to localhost:8452", false, false, "Try it on a test copy first."),
      btn("download", "Download change", false),
    ],
    note: "The app never changes your server by itself. Apply works only on our demo server.",
    busy: false,
    ...over,
  };
}

export const readyToTry: ChangeView = base({});

export const trying: ChangeView = base({
  busy: true,
  badge: { label: "Trying", look: "neutral" },
  try: {
    title: "Try on a test copy: running",
    running: { status: "running", status_text: "Running the same measurement on a test copy", progress: { text: "hello 2 of 3", percent: null } },
    verdict: null,
    columns: [],
    rows: [],
    notes: [],
    results: [],
  },
  buttons: [btn("try", "Try on a test copy", true, false, "A try is running."), btn("download", "Download change", false)],
});

const passedTry: NonNullable<ChangeView["try"]> = {
  title: "Try on a test copy: passed",
  running: null,
  verdict: { label: "Try passed.", look: "pass", text: "The copy measures what Hybrid promises, and the control was read correctly." },
  columns: tryTable.columns,
  rows: tryTable.rows,
  notes: ["Real nginx was not tried: that needs isolated mode (Docker)."],
  results: [{ label: "the test copy", result: tryEvidence }],
};

export const triedPassedPicker: ChangeView = base({
  badge: { label: "Ready to try", look: "pass" },
  steps: [
    step("built", "Built", "done", "5:08 PM"),
    step("tried", "Tried on a test copy", "done", "passed, 5:14 PM"),
    step("approvals", "Approvals", "now", "not asked yet"),
    step("applied", "Apply", "off", ""),
    step("measured", "Measured after", "off", ""),
  ],
  try: passedTry,
  approvals: {
    title: "Who must approve before Apply",
    picker: {
      options: [
        { id: "you", name: "You", demo: false, checked: true },
        { id: "reviewer-a", name: "Demo reviewer A", demo: true, checked: true },
        { id: "reviewer-b", name: "Demo reviewer B", demo: true, checked: false },
      ],
      button: "Ask for approval",
      enabled: true,
      reason: null,
    },
    rows: [],
    footnote: FOOTNOTE,
  },
  buttons: [
    btn("try", "Try again on a test copy", false),
    btn("apply", "Apply to localhost:8452", false, false, "Apply stays off until everyone you asked has approved."),
    btn("download", "Download change", false),
  ],
});

export const waitingOneApproval: ChangeView = base({
  badge: { label: "Waiting for approval", look: "warn" },
  steps: [
    step("built", "Built", "done", "5:08 PM"),
    step("tried", "Tried on a test copy", "done", "passed, 5:14 PM"),
    step("approvals", "Approvals", "now", "1 of 2"),
    step("applied", "Apply", "off", ""),
    step("measured", "Measured after", "off", ""),
  ],
  try: passedTry,
  approvals: {
    title: "Who must approve before Apply",
    picker: null,
    rows: [
      { reviewer: "you", name: "You", demo: false, approved_at: "2026-11-14T17:20:00Z", status_text: "approved, 5:20 PM", approve: null },
      { reviewer: "reviewer-a", name: "Demo reviewer A", demo: true, approved_at: null, status_text: "not yet", approve: { label: "Approve as Demo reviewer A", enabled: true } },
    ],
    footnote: FOOTNOTE,
  },
  buttons: [
    btn("try", "Try again on a test copy", false),
    btn("apply", "Apply to localhost:8452", true, false, "Apply stays off until 1 more approval is in."),
    btn("download", "Download change", false),
  ],
});

export const readyToApply: ChangeView = base({
  badge: { label: "Ready to apply", look: "pass" },
  steps: [
    step("built", "Built", "done", "5:08 PM"),
    step("tried", "Tried on a test copy", "done", "passed, 5:14 PM"),
    step("approvals", "Approvals", "done", "2 of 2"),
    step("applied", "Apply", "now", "waiting for you"),
    step("measured", "Measured after", "off", ""),
  ],
  try: passedTry,
  approvals: {
    title: "Who must approve before Apply",
    picker: null,
    rows: [
      { reviewer: "you", name: "You", demo: false, approved_at: "2026-11-14T17:20:00Z", status_text: "approved, 5:20 PM", approve: null },
      { reviewer: "reviewer-a", name: "Demo reviewer A", demo: true, approved_at: "2026-11-14T17:22:00Z", status_text: "approved, 5:22 PM", approve: null },
    ],
    footnote: FOOTNOTE,
  },
  buttons: [btn("try", "Try again on a test copy", false), btn("apply", "Apply to localhost:8452", true), btn("download", "Download change", false)],
});

export const appliedMatches: ChangeView = base({
  badge: { label: "Applied", look: "pass" },
  steps: [
    step("built", "Built", "done", "5:08 PM"),
    step("tried", "Tried on a test copy", "done", "passed, 5:14 PM"),
    step("approvals", "Approvals", "done", "2 of 2"),
    step("applied", "Apply", "done", "5:30 PM"),
    step("measured", "Measured after", "done", "matches the try"),
  ],
  try: passedTry,
  approvals: null,
  applied: {
    title: "After Apply",
    badge: { label: "Applied · matches the try", look: "pass" },
    paragraphs: [[...t("We measured "), m("localhost:8452"), ...t(" again after Apply. Its key exchange is now Hybrid, as on the copy.")]],
    differences: [],
    history: ["Applied 14 Nov 2026, 5:30 PM, by You.", "Rolled back 13 Nov 2026, 9:02 AM, by You."],
  },
  buttons: [btn("rollback", "Roll back", false), btn("download", "Download change", false)],
});

export const appliedMismatch: ChangeView = {
  ...appliedMatches,
  badge: { label: "Applied", look: "warn" },
  steps: appliedMatches.steps.map((s) => (s.key === "measured" ? { ...s, state: "failed" as const, text: "does not match the try" } : s)),
  applied: {
    title: "After Apply",
    badge: { label: "Applied · does not match the try", look: "fail" },
    paragraphs: [t("The measurement after Apply differs from the try.")],
    differences: ["The copy was Hybrid; the server now measures Classical.", "The first message is 1,412 bytes, not 2,580."],
    history: ["Applied 14 Nov 2026, 5:30 PM, by You."],
  },
};

export const cantTry: ChangeView = base({
  id: "migration:server:localhost:8454",
  title: "Your change: wrap the connection on localhost:8454",
  badge: { label: "Can't be tried here", look: "warn" },
  steps: [],
  buttons: [
    btn("try", "Try on a test copy", true, false, "This change can't be tried here: it needs a gateway the app doesn't run."),
    btn("download", "Download change", false),
  ],
  note: "Hand the downloaded file to your team.",
});

export const textOnly: ChangeView = {
  id: "migration:server:localhost:8453",
  title: "Your choice: keep localhost:8453 classical",
  badge: { label: "Text only", look: "neutral" },
  intro: t("Nothing to change now. The choice is recorded with a review date."),
  steps: [],
  sections: [{ kind: "text", title: "What this means", paragraphs: [t("The server stays Classical until 14 Nov 2027, then you review it.")] }],
  try: null,
  approvals: null,
  applied: null,
  buttons: [],
  note: null,
  busy: false,
};

export const tlsChange: ChangeView = base({
  id: TLS_CHANGE_ID,
  title: "Your change: stop accepting TLS 1.2 on localhost:8443",
  intro: t("Built from the failed Old TLS versions test."),
});
