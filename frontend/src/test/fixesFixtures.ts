// The Fixes step in each of its statuses, built from the view types with the words of the approved mockup
// (pictures 03 to 11). Commit ids, times and the proof fingerprint are examples.
import type {
  ApprovalRowView,
  FixButton,
  FixDetail,
  FixSection,
  FixesView,
  ProofCell,
  ProofRow,
  ProofTable,
  RichText,
  TestKind,
  TextSuggestion,
  Tone,
} from "../api";
import { DISCLAIMER } from "./fixtures";

export const CODE_FIX = "fix-ecdsa-range-check";
export const TLS_FIX = "fix-tls-versions";

const SIZE = "3 lines added and 1 removed";
const BUILT_SHA256 = "d49e46ed3121ab0f2220a8b0a7a50f18b684b310e465d5e755062f69be40a378";
export const PROOF_FINGERPRINT = "5e1c7a09b3d24f6688a1c0e9d7b25f31c4a6e80b92d3f7514ac6e0b8d19f2c73";

const PR_OPENED = "2026-11-11T15:22:10.000Z";
const APPROVED_YOU = "2026-11-11T15:22:31.000Z";
const APPROVED_A = "2026-11-11T15:23:05.000Z";
const MERGED = "2026-11-11T15:23:40.000Z";

export const SERVER_LINE = "This fixes the signing program. The server finding is separate and still open.";
export const SERVER_LINE_UNPROVEN =
  "This change is for the signing program only. The server finding is separate and still open.";
export const ONE_LOGIN =
  "This version has one login and no separate accounts. Whoever is at the keyboard records each approval, under the name shown.";
const PROOF_PASSED =
  "All 3 tests that run the changed code passed, every control behaved as expected, and the 3 server tests came out the same as before.";
const PROOF_FAILED =
  "1 of the 3 tests that run the changed code did not pass: Official test vectors, Couldn't run (it took too long).";

const t = (v: string) => ({ t: "text", v }) as const;
const m = (v: string) => ({ t: "mono", v }) as const;

// ---- The change ----

const changeSection: FixSection = {
  key: "change",
  title: "The change",
  line: `${SIZE}, in 1 file (acme_sign.py)`,
  open: true,
  intro:
    "Written from a fix template: a ready-made change for one known kind of bug, a missing range check when checking an ECDSA signature. It was not written by an AI model, and it applies only where the code has exactly the lines it expects.",
  parts: [
    {
      title: "1. The check: reject a signature whose numbers are out of range",
      why: "acme_sign.py, in the verify command. r and s must each be at least 1 and below n, a fixed upper limit set by the P-256 standard.",
      before_label: { lead: "Before:", strong: "acme-sign 1.4.2", rest: ", nothing removed here" },
      before: [
        { n: 165, mark: " ", text: "    try:" },
        { n: 166, mark: " ", text: '        r, s = der_decode(bytes.fromhex(req["signature"]))' },
        { n: 167, mark: " ", text: "    except ValueError:" },
        { n: 168, mark: " ", text: '        return {"valid": False}' },
        { n: 169, mark: " ", text: "    e = digest_int(message)" },
      ],
      after_label: { lead: "After:", strong: "this change", rest: ", 2 lines added (marked +)" },
      after: [
        { n: 165, mark: " ", text: "    try:" },
        { n: 166, mark: " ", text: '        r, s = der_decode(bytes.fromhex(req["signature"]))' },
        { n: 167, mark: " ", text: "    except ValueError:" },
        { n: 168, mark: " ", text: '        return {"valid": False}' },
        { n: 169, mark: "+", text: "    if not (1 <= r < N and 1 <= s < N):" },
        { n: 170, mark: "+", text: '        return {"valid": False}' },
        { n: 171, mark: " ", text: "    e = digest_int(message)" },
      ],
    },
    {
      title: "2. The version number",
      why: "So the changed program reports itself as 1.4.3 and can be told apart from 1.4.2.",
      before_label: { lead: "Before:", strong: "acme-sign 1.4.2", rest: ", 1 line removed (marked −)" },
      before: [
        { n: 19, mark: " ", text: 'NAME = "acme-sign"' },
        { n: 20, mark: "-", text: 'VERSION = "1.4.2"' },
        { n: 21, mark: " ", text: 'ALGORITHM = "ECDSA P-256"' },
      ],
      after_label: { lead: "After:", strong: "this change", rest: ", 1 line added (marked +)" },
      after: [
        { n: 19, mark: " ", text: 'NAME = "acme-sign"' },
        { n: 20, mark: "+", text: 'VERSION = "1.4.3"' },
        { n: 21, mark: " ", text: 'ALGORITHM = "ECDSA P-256"' },
      ],
    },
  ],
};

// ---- Proof ----

const cell = (label: string, tone: Tone, short: string): ProofCell => ({ label, tone, short });

function proofRow(kind: TestKind, title: string, before: ProofCell, proof: ProofCell, control: string, check: string): ProofRow {
  return { kind, title, before, proof, waiting: null, control, check: { ok: true, text: check } };
}

const SIGNER_CONTROL = "Control: a deliberately broken signer failed this test, as expected.";

const codeRows: ProofRow[] = [
  proofRow(
    "official_vectors",
    "Official test vectors",
    cell("Failed", "fail", "3 of 484 official cases wrong (168, 171, 364), all from one missing range check."),
    cell("Passed", "pass", "484 of 484 official cases right."),
    SIGNER_CONTROL,
    "Passed",
  ),
  proofRow(
    "bad_signatures",
    "Bad signatures",
    cell("Failed", "fail", "Accepts the signature r=0, s=0. One cause: no range check."),
    cell("Passed", "pass", "Rejects r=0, s=0 and every other bad signature tried."),
    SIGNER_CONTROL,
    "Passed",
  ),
  proofRow(
    "speed_size",
    "Speed and size",
    cell("Measured", "neutral", "Sign 5.2 ms, verify 10.7 ms (medians, first run)."),
    cell(
      "No slowdown beyond measured noise",
      "pass",
      "Sign 5.3 ms, verify 10.5 ms on acme-sign 1.4.3, against 5.3 ms and 10.5 ms on acme-sign 1.4.2, measured side by side (medians). Noise: ±1.5%.",
    ),
    "Control: a deliberately slowed signer was flagged as slower, as expected.",
    "No slowdown",
  ),
];

const serverRows: ProofRow[] = [
  proofRow(
    "tls_versions",
    "Old TLS versions",
    cell("Failed", "fail", "Server accepted TLS 1.2."),
    cell("Failed", "fail", "Server still accepts TLS 1.2. This change doesn't touch the server."),
    "Control: a deliberately misconfigured test server failed this test, as expected.",
    "Same as before",
  ),
  proofRow(
    "certificate",
    "Certificate strength",
    cell("Passed", "pass", "ECDSA P-256, as claimed. NIST retirement note."),
    cell("Passed", "pass", "ECDSA P-256, as claimed. NIST retirement note."),
    "Control: a deliberately weak test certificate failed this test, as expected.",
    "Same as before",
  ),
  proofRow(
    "pq_readiness",
    "Post-quantum readiness",
    cell("Not offered", "neutral", "Server does not offer X25519MLKEM768."),
    cell("Not offered", "neutral", "Server does not offer X25519MLKEM768. This change doesn't touch the server."),
    "Control: a test server that does offer the new key exchange was detected as offering it, as expected.",
    "Same as before",
  ),
];

function proofTables(code: ProofRow[], server: ProofRow[]): ProofTable[] {
  return [
    {
      heading: "Tests that run the changed code",
      tag: "measured",
      need: "Each of these must pass, and its control must behave as expected.",
      columns: ["Test", "Before: acme-sign 1.4.2", "On the changed code", "Rule check"],
      rows: code,
    },
    {
      heading: "Tests that don't run this code (they test the server)",
      tag: "measured",
      need: "A code change can't affect these. They are rerun anyway and must come out the same as before.",
      columns: ["Test", "Before", "Rerun for this proof", "Rule check"],
      rows: server,
    },
  ];
}

const PROOF_INTRO =
  "The app applied this change on a new branch of its own copy of the code, then reran every locked test in your plan, with the old and the new version timed side by side. The runs went through the same steps as your first results: the same test runner, then the same automatic check that decides each result from what the run recorded. The fix template has no say in any result.";

const proofPassedSection: FixSection = {
  key: "proof",
  title: "Proof",
  line: "Passed: all 3 tests that run the changed code passed, every control behaved as expected, and the 3 server tests came out the same as before.",
  open: false,
  intro: PROOF_INTRO,
  tables: proofTables(codeRows, serverRows),
  verdict: {
    tone: "pass",
    title: "Why it is ready for review",
    checks: [
      { ok: true, text: "All 3 tests that run the changed code passed." },
      { ok: true, text: "Every control behaved as expected." },
      { ok: true, text: "The 3 server tests came out the same as before." },
    ],
    shows_title: "What this proof shows, and what it doesn't",
    shows: [
      "It shows that with this change the two failed tests pass, no slowdown beyond measured noise was found, and the server tests came out as before.",
      "It doesn't show that the change is free of other faults, and it does nothing about the server finding.",
    ],
  },
};

const proofFailedSection: FixSection = {
  key: "proof",
  title: "Proof",
  line: "Did not pass: 1 of the 3 tests that run the changed code did not pass.",
  open: false,
  intro: PROOF_INTRO,
  tables: proofTables(
    codeRows.map((row) =>
      row.kind === "official_vectors"
        ? {
            ...row,
            proof: cell("Couldn't run (it took too long)", "warn", "Could not run: it took too long."),
            control: "Control: not run, because the test couldn't run.",
            check: { ok: false, text: "Did not pass" },
          }
        : row,
    ),
    serverRows,
  ),
  verdict: {
    tone: "fail",
    title: "Why this change is not offered",
    checks: [
      { ok: false, text: PROOF_FAILED },
      { ok: true, text: "Every control behaved as expected in the tests that ran." },
      { ok: true, text: "The 3 server tests came out the same as before." },
    ],
    shows_title: null,
    shows: [],
  },
};

/** Two of the six tests have their proof result; one is running and three wait. */
const unfinished = (row: ProofRow, waiting: ProofRow["waiting"]): ProofRow => ({
  ...row,
  proof: null,
  waiting,
  control: "",
  check: { ok: null, text: "Not finished yet" },
});

const proofRunningSection: FixSection = {
  key: "proof",
  title: "Proof",
  line: "Running: 2 of 6 tests finished.",
  open: false,
  intro: PROOF_INTRO,
  tables: proofTables(
    codeRows.map((row) =>
      unfinished(
        row,
        row.kind === "official_vectors"
          ? { text: "Running", detail: "212 of 484 cases", percent: 44 }
          : { text: "Waiting", detail: null, percent: null },
      ),
    ),
    serverRows.map((row) => (row.kind === "pq_readiness" ? unfinished(row, { text: "Waiting", detail: null, percent: null }) : row)),
  ),
  verdict: null,
};

// ---- Technical details ----

type Stage = "proving" | "proved" | "failed" | "open" | "merged";

function detailsSection(stage: Stage): FixSection {
  const finished = stage !== "proving";
  const hasPullRequest = stage === "open" || stage === "merged";
  const facts: { label: string; value: RichText; fingerprint: boolean }[] = [
    {
      label: "Repository",
      value: [m("acme-sign"), t(" "), { t: "demo", v: "Demo data" }, t(", the app's own copy. Nothing is sent anywhere else.")],
      fingerprint: false,
    },
    {
      label: "Starting point",
      value: [t("branch "), m("main"), t(", commit "), m("3f9c2ab"), t(" ("), m("acme-sign 1.4.2"), t(")")],
      fingerprint: false,
    },
    { label: "Change branch", value: [m("fix/ecdsa-range-check"), t(", commit "), m("8b1d4e7")], fingerprint: false },
    { label: "File changed", value: [m("acme_sign.py"), t(`: ${SIZE}`)], fingerprint: false },
  ];
  if (hasPullRequest) {
    facts.push({
      label: "Pull request",
      value: [
        t("#1, opened "),
        { t: "time", v: PR_OPENED },
        ...(stage === "merged"
          ? [t("; merged "), { t: "time", v: MERGED } as const, t(" (merge commit "), m("c41f0d2"), t(")")]
          : []),
      ],
      fingerprint: false,
    });
  }
  if (finished) {
    facts.push({
      label: "Proof finished",
      value: [
        { t: "time", v: stage === "failed" ? "2026-11-11T15:24:14.000Z" : "2026-11-11T15:20:44.000Z" },
        t(stage === "failed" ? ", after 4 min 12 s " : ", after 42.0 s "),
        { t: "tag", v: "measured" },
      ],
      fingerprint: false,
    });
  }
  facts.push({ label: "Mode", value: [t("Demo mode, not isolated")], fingerprint: false });
  if (finished) {
    facts.push({ label: "Evidence fingerprint of the proof (SHA-256)", value: [t(PROOF_FINGERPRINT)], fingerprint: true });
  }
  return {
    key: "details",
    title: "Technical details",
    line: "Repository, branches, commits, fingerprints and mode",
    open: false,
    facts,
    note:
      "A branch is a separate line of work inside the repository, so the main copy stays untouched until a merge. A commit is one saved state of the code, named by a short id such as 8b1d4e7." +
      (finished
        ? ' The full record of every run in this proof is in the files saved by "Download evidence", where the evidence fingerprint of the proof can be checked. That fingerprint is listed inside the evidence file; it is not the fingerprint of the file itself.'
        : "") +
      (hasPullRequest ? ' "Download patch" saves this change as one file that a developer can apply to another copy of the code.' : ""),
    ran_on: {
      title: finished ? "What the tests ran on" : "What the tests are running on",
      text: [
        t("Our own bundled demo component, "),
        m("acme-sign 1.4.3"),
        t(". Before running anything, the app checked that the file built from branch "),
        m("fix/ecdsa-range-check"),
        t(" is exactly the same as that bundled component, byte for byte: the two fingerprints below match."),
      ],
      fingerprints: [
        { label: "The built file (SHA-256)", value: BUILT_SHA256, tag: "measured" },
        { label: "Bundled acme-sign 1.4.3 (SHA-256)", value: BUILT_SHA256, tag: "demo" },
      ],
      note: "This version of Evidence Lab only ever runs our own demo software. If a change produced anything else, the app would run nothing and would not offer the change.",
    },
  };
}

// ---- The code fix, status by status ----

const WHAT_UNPROVEN: RichText = [
  t("Adds a range check on the two signature numbers (r and s) to "),
  m("acme-sign"),
  t(`'s signature check, and gives the changed program the version number 1.4.3. ${SIZE}.`),
];
const WHAT_PROVEN: RichText = [
  t("Adds the missing range check to "),
  m("acme-sign"),
  t(
    `'s signature check, so it now rejects signatures such as r = 0, s = 0, as the proof's tests show. The changed program reports version 1.4.3. ${SIZE}.`,
  ),
];

const codeFixBase: FixDetail = {
  id: CODE_FIX,
  kind: "code",
  title: "acme-sign accepts out-of-range signatures",
  list_source: "Came from 2 failed tests: Official test vectors, Bad signatures",
  source: [
    t("Came from 2 failed tests on signing component "),
    m("acme-sign 1.4.2"),
    t(": Official test vectors and Bad signatures."),
  ],
  status: { key: "not_connected", word: "Code not connected", busy: false },
  labels: ["From a fix template"],
  is_demo: true,
  what: {
    label: "What it changes",
    paragraphs: [
      [
        t("A fix template exists for this failure: a ready-made change for a missing range check on the two signature numbers (r and s), written for "),
        m("acme-sign"),
        t("'s code. Connect the code to prepare the change and prove it."),
      ],
    ],
    server_line: SERVER_LINE_UNPROVEN,
  },
  proof: {
    state: "not_started",
    badge: null,
    text: "Not started. It starts by itself once the code is connected: every locked test in your plan is rerun on the changed code. This takes about a minute.",
    muted: null,
  },
  pull_request: null,
  approvers: { text: "You pick the reviewers once the proof has passed.", options: null, rows: null, footnote: null },
  actions: {
    buttons: [{ action: "connect", label: "Connect demo code", primary: true, enabled: true }],
    note: "Connects a fresh copy of the small demo repository of acme-sign 1.4.2 that comes with the app (the source code and its history of changes, in git's format), for this imported file and every fix in it. The proof then starts by itself.",
  },
  patch: null,
  merge_dialog: null,
  sections: [],
  sections_note: "The change, its proof and the technical details appear below once the code is connected.",
};

const provingFix: FixDetail = {
  ...codeFixBase,
  status: { key: "proving", word: "Proving", busy: true },
  what: { label: "What it changes", paragraphs: [WHAT_UNPROVEN], server_line: SERVER_LINE_UNPROVEN },
  proof: { state: "running", badge: null, text: "Running: 2 of 6 tests finished.", muted: "Not offered yet." },
  actions: { buttons: [], note: null },
  sections: [changeSection, proofRunningSection, detailsSection("proving")],
  sections_note: null,
};

const proofPassed: FixDetail["proof"] = {
  state: "passed",
  badge: { label: "Proof passed", tone: "pass" },
  text: PROOF_PASSED,
  muted: null,
};

const readyFix: FixDetail = {
  ...provingFix,
  status: { key: "ready", word: "Ready for review", busy: false },
  what: { label: "What it fixes", paragraphs: [WHAT_PROVEN], server_line: SERVER_LINE },
  proof: proofPassed,
  approvers: {
    text: null,
    options: [
      { id: "you", name: "You", note: "(the person logged in)", demo: false, checked: true },
      { id: "a", name: "Demo reviewer A", note: null, demo: true, checked: false },
      { id: "b", name: "Demo reviewer B", note: null, demo: true, checked: false },
    ],
    rows: null,
    footnote: ONE_LOGIN,
  },
  actions: {
    buttons: [{ action: "open_pull_request", label: "Open pull request", primary: true, enabled: true }],
    note: "Nothing goes into the main copy of the code until the reviewers you pick approve and you confirm the merge.",
  },
  sections: [changeSection, proofPassedSection, detailsSection("proved")],
};

const failedFix: FixDetail = {
  ...provingFix,
  status: { key: "failed", word: "Proof failed", busy: false },
  proof: {
    state: "failed",
    badge: { label: "Proof did not pass", tone: "fail" },
    text: `${PROOF_FAILED} The change is not offered.`,
    muted: null,
  },
  approvers: {
    text: "Nobody yet: a change that is not offered can't get a pull request.",
    options: null,
    rows: null,
    footnote: null,
  },
  actions: {
    buttons: [{ action: "run_proof_again", label: "Run proof again", primary: false, enabled: true }],
    note: "Reruns all 6 tests in your plan. The change is offered only if the proof passes.",
  },
  sections: [changeSection, proofFailedSection, detailsSection("failed")],
};

function approvalRow(id: "you" | "a", approvedAt: string | null): ApprovalRowView {
  const you = id === "you";
  const name = you ? "You" : "Demo reviewer A";
  return {
    id,
    name,
    note: you ? "(the person logged in)" : null,
    demo: !you,
    approved_at: approvedAt,
    approved_text: approvedAt ? "Approved" : null,
    approve_label: approvedAt ? null : you ? "Approve" : `Approve as ${name}`,
    primary: you,
  };
}

const PATCH = { url: `/api/plans/1/fixes/${CODE_FIX}/patch`, filename: "acme-sign-pull-request-1.patch" };
const PR_TITLE = "#1 Reject signatures whose r or s is out of range.";
const downloadPatch: FixButton = { action: "download_patch", label: "Download patch", primary: false, enabled: true };

function waitingFix(youApprovedAt: string | null): FixDetail {
  return {
    ...readyFix,
    status: { key: "waiting", word: "Waiting for approval", busy: false },
    pull_request: {
      title: PR_TITLE,
      text: [t("Open since "), { t: "time", v: PR_OPENED }, t(". It stays inside the app; nothing is sent anywhere else.")],
    },
    approvers: { text: null, options: null, rows: [approvalRow("you", youApprovedAt), approvalRow("a", null)], footnote: ONE_LOGIN },
    actions: {
      buttons: [{ action: "merge", label: "Merge pull request", primary: true, enabled: false }, downloadPatch],
      note: youApprovedAt
        ? '"Merge pull request" unlocks when every reviewer has approved: waiting for Demo reviewer A. The app never merges on its own: you press the button and confirm.'
        : '"Merge pull request" unlocks when every reviewer has approved: waiting for You and Demo reviewer A. The app never merges on its own: you press the button and confirm.',
    },
    patch: PATCH,
    sections: [changeSection, proofPassedSection, detailsSection("open")],
  };
}

const readyToMergeFix: FixDetail = {
  ...waitingFix(APPROVED_YOU),
  status: { key: "ready_to_merge", word: "Ready to merge", busy: false },
  pull_request: {
    title: PR_TITLE,
    text: [
      t("Open since "),
      { t: "time", v: PR_OPENED },
      t(". It stays inside the app; nothing is sent anywhere else. Every reviewer has approved. Not merged yet."),
    ],
  },
  approvers: { text: null, options: null, rows: [approvalRow("you", APPROVED_YOU), approvalRow("a", APPROVED_A)], footnote: ONE_LOGIN },
  actions: {
    buttons: [{ action: "merge", label: "Merge pull request", primary: true, enabled: true }, downloadPatch],
    note: "Every reviewer has approved. The app never merges on its own: you press the button and confirm.",
  },
  merge_dialog: {
    title: "Merge pull request #1?",
    paragraphs: [
      [
        t("This puts the change on the "),
        m("main"),
        t(" branch of the app's own copy of the demo repository "),
        m("acme-sign"),
        t(". After the merge, that branch holds "),
        m("acme-sign 1.4.3"),
        t("."),
      ],
      [t("Every reviewer has approved. The app deploys nothing, and a merge can't be undone here.")],
    ],
    confirm: "Confirm merge",
    cancel: "Cancel",
  },
};

const mergedFix: FixDetail = {
  ...readyToMergeFix,
  status: { key: "merged", word: "Merged", busy: false },
  pull_request: {
    title: PR_TITLE,
    text: [
      t("Merged "),
      { t: "time", v: MERGED },
      t(" by the person logged in, after confirming. The demo repository's "),
      m("main"),
      t(" branch now holds "),
      m("acme-sign 1.4.3"),
      t(". Nothing was deployed."),
    ],
  },
  actions: {
    buttons: [{ action: "retest_now", label: "Retest now", primary: true, enabled: true }, downloadPatch],
    note: 'Reruns the same locked tests on acme-sign 1.4.3, the code now on main, and shows before and after in Evidence Lab. It does the same as "Retest new version" there.',
  },
  merge_dialog: null,
  sections: [changeSection, proofPassedSection, detailsSection("merged")],
};

// ---- The text-only fix (the server TLS suggestion, picture 11) ----

const CIPHERS =
  "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305";

export const tlsSuggestion: TextSuggestion = {
  intro: [
    "This is usually a server setting, not a code change. The server accepted TLS 1.2, with the older cipher suite (the set of algorithms a connection uses) `ECDHE-ECDSA-AES128-SHA`. The file claims TLS 1.3 only.",
  ],
  warning: {
    title: "Before you switch TLS 1.2 off:",
    text: "older clients and partner systems that can't use TLS 1.3 will no longer be able to connect.",
  },
  where: {
    title: "Where the setting lives",
    note: "Use the row that matches how TLS is handled for this server.",
    columns: ["Where TLS is set up", "The setting", "To accept TLS 1.3 only"],
    rows: [
      {
        place: "nginx",
        setting: "the `ssl_protocols` line (often in the `http` block of `nginx.conf`)",
        lead: "",
        code: "ssl_protocols TLSv1.3;",
      },
      {
        place: "Apache",
        setting: "the `SSLProtocol` line (in the main server config, or in every virtual host on the address)",
        lead: "",
        code: "SSLProtocol -all +TLSv1.3",
      },
      {
        place: "A cloud load balancer",
        setting:
          "the security policy (also called a TLS or SSL policy) on the load balancer's HTTPS or TLS listener, the part that accepts incoming connections",
        lead: "Choose a policy that allows TLS 1.3 only (not every provider has one), and check it in your provider's own list. On an AWS Application or Network Load Balancer, for example:",
        code: "ELBSecurityPolicy-TLS13-1-3-2021-06",
      },
      {
        place: "Your own application",
        setting: "the minimum TLS version in your application's own TLS settings",
        lead: "Set the minimum to TLS 1.3. In Python, for example:",
        code: "context.minimum_version = ssl.TLSVersion.TLSv1_3",
      },
    ],
    after: [
      "For either option, change every existing line, including any in a site's own block, rather than adding another one. Make sure every site on that address is covered, then reload the server.",
    ],
  },
  options: {
    title: "Two ways to fix it",
    items: [
      {
        title: "Option 1: switch TLS 1.2 off",
        when: "Choose this when nothing still connects with TLS 1.2.",
        steps: [
          "Check the access logs of the server or load balancer for connections that used TLS 1.2. Many servers do not log the TLS version until you add it (nginx: `$ssl_protocol`; Apache: `%{SSL_PROTOCOL}x`).",
          "If the log shows only TLS 1.3 over a normal period of use, apply the setting above.",
          "Run this test again.",
        ],
        note: "",
      },
      {
        title: "Option 2: keep TLS 1.2, with strong settings only",
        when: "Choose this when some clients or partners still need TLS 1.2.",
        steps: [
          "Remove the older cipher suite this test found, `ECDHE-ECDSA-AES128-SHA`, and keep only strong ones. The exact settings are below.",
          "Correct the scanner file so that it says TLS 1.2 and TLS 1.3.",
          "Import the corrected file and run the tests again.",
        ],
        note: "This test checks TLS versions only. It will not show whether the old cipher suite is gone.",
      },
    ],
  },
  exact: {
    title: "Option 2: the exact settings",
    note: "These keep TLS 1.2 and TLS 1.3. For TLS 1.2 they keep only cipher suites that use ECDHE with AES-GCM or ChaCha20-Poly1305, the same kinds of encryption TLS 1.3 uses. Copy each setting exactly, as one line, even where it wraps here.",
    blocks: [
      { place: "nginx", code: `ssl_protocols TLSv1.2 TLSv1.3;\nssl_ciphers ${CIPHERS};` },
      { place: "Apache", code: `SSLProtocol -all +TLSv1.2 +TLSv1.3\nSSLCipherSuite ${CIPHERS}` },
      { place: "AWS Application or Network Load Balancer (security policy)", code: "ELBSecurityPolicy-TLS13-1-2-Res-2021-06" },
    ],
  },
};

export const tlsFix: FixDetail = {
  id: TLS_FIX,
  kind: "text",
  title: "Server accepts TLS 1.2",
  list_source: "Came from 1 failed test: Old TLS versions",
  source: [t("Came from 1 failed test on server "), m("localhost:8443"), t(": Old TLS versions. The file claims TLS 1.3 only.")],
  status: { key: "text_only", word: "Text only", busy: false },
  labels: [],
  is_demo: true,
  what: {
    label: "What it suggests",
    paragraphs: [
      [
        t(
          "A server setting, not a code change: stop accepting TLS 1.2, or keep it with strong settings only and correct the scanner file. The suggestion below says where the setting lives and gives two ways to do it.",
        ),
      ],
    ],
    server_line: null,
  },
  proof: {
    state: "none",
    badge: null,
    text: "None. This suggestion is text only: the app has not applied it or tested it.",
    muted: null,
  },
  pull_request: null,
  approvers: {
    text: "Your own server team, outside this app. The app never changes your server.",
    options: null,
    rows: null,
    footnote: null,
  },
  actions: { buttons: [], note: null },
  patch: null,
  merge_dialog: null,
  sections: [
    {
      key: "suggestion",
      title: "The suggestion",
      line: "A warning first, where the setting lives, and two ways to fix it",
      open: true,
      suggestion: tlsSuggestion,
    },
  ],
  sections_note: null,
};

// ---- The whole view, one for each status of the code fix ----

function view(codeFix: FixDetail): FixesView {
  return {
    plan_id: 1,
    is_demo: true,
    title: "Fixes",
    subline: "Fixes for the findings in Evidence Lab. A code change is ready for review only after its proof has passed.",
    disclaimer: DISCLAIMER,
    list_title: "Open findings with a fix (2)",
    empty_text: null,
    fixes: [codeFix, tlsFix],
    busy: codeFix.status.busy,
  };
}

export const fixesViews = {
  not_connected: view(codeFixBase),
  proving: view(provingFix),
  ready: view(readyFix),
  failed: view(failedFix),
  /** The pull request was just opened: nobody has approved yet. */
  opened: view(waitingFix(null)),
  /** Picture 08: "You" has approved, Demo reviewer A has not. */
  waiting: view(waitingFix(APPROVED_YOU)),
  ready_to_merge: view(readyToMergeFix),
  merged: view(mergedFix),
} satisfies Record<string, FixesView>;

/** No failed test has a fix. */
export const noFixes: FixesView = {
  ...fixesViews.ready,
  list_title: "Open findings with a fix (0)",
  empty_text: "No failed test has a fix. Fixes for failed tests show here.",
  fixes: [],
};

/** Swaps the code fix of a view. */
export function withCodeFix(base: FixesView, change: Partial<FixDetail>): FixesView {
  return { ...base, fixes: base.fixes.map((fix) => (fix.id === CODE_FIX ? { ...fix, ...change } : fix)) };
}
