// The Checks page (phase 5b) for the Acme Pay demo, built from the view types with the backend's words
// (backend/app/ledger/groups.py and checks.py). Times and ids are examples.
import type { CheckDetail, CheckGroup, CheckRow, ChecksView } from "../api";

const VERIFIED_AT = "2026-11-10T09:10:00Z";
const RAN_AT = "2026-11-10T09:20:00Z";
const RETESTED_AT = "2026-11-10T10:05:00Z";

function claimRow(id: number, name: string, ranOn: string, label: "True" | "False" | "Couldn't check", plain: string): CheckRow {
  const tone = label === "True" ? "pass" : label === "False" ? "fail" : "warn";
  const code = label === "True" ? "true" : label === "False" ? "false" : "couldnt_check";
  return {
    id: `claim-${id}`,
    group: "verification",
    kind: "verify",
    name,
    ran_on: ranOn,
    came_from: { key: "verify", label: "Verify" },
    link: { page: "inventory/verify", item: `claim-${id}` },
    evidence_link: { page: "evidence", item: `claim-${id}` },
    state: "done",
    status: null,
    result: { label, tone, code },
    plain,
    last_run_at: VERIFIED_AT,
    runs: 1,
  };
}

function testRow(id: number, name: string, ranOn: string, passed: boolean, origin: "plan" | "retest" = "plan", runs = 1): CheckRow {
  const key = origin === "plan" ? "test" : "retest";
  return {
    id: `${key}-${id}`,
    group: "encryption",
    kind: "test",
    name,
    ran_on: ranOn,
    came_from: { key: origin, label: origin === "plan" ? "Test plan" : "Retest" },
    link: origin === "plan" ? { page: "checks", item: `test-${id}` } : { page: "evidence", item: `retest-${id}` },
    evidence_link: { page: "evidence", item: `${key}-${id}` },
    state: "done",
    status: null,
    result: passed ? { label: "Passed", tone: "pass", code: "passed" } : { label: "Failed", tone: "fail", code: "failed" },
    plain: passed ? "Every case gave the expected answer." : "Some cases did not give the expected answer.",
    last_run_at: origin === "plan" ? RAN_AT : RETESTED_AT,
    runs,
  };
}

export const verifyRows: CheckRow[] = [
  claimRow(1, "Uses TLS 1.3 only", "localhost:8443", "False", "The server also accepts TLS 1.2."),
  claimRow(2, "Certificate signed with ECDSA P-256", "localhost:8443", "True", "The certificate is signed with ECDSA P-256."),
  claimRow(3, "acme-sign uses ML-DSA-65", "acme-sign 1.4.2", "Couldn't check", "Nothing was run for this claim."),
];

export const planRows: CheckRow[] = [
  testRow(1, "Official test vectors", "acme-sign 1.4.2", false),
  testRow(2, "Bad signatures", "acme-sign 1.4.2", false),
  testRow(3, "Old TLS versions", "localhost:8443", false),
];

export const retestRow: CheckRow = testRow(1, "Official test vectors", "acme-sign 1.4.3 (the new version)", true, "retest", 1);

export function checkGroups(over: { verification?: CheckRow[]; encryption?: CheckRow[] } = {}): CheckGroup[] {
  const verification = over.verification ?? verifyRows;
  const encryption = over.encryption ?? [...planRows, retestRow];
  const counts = (rows: CheckRow[]) => ({
    open: rows.filter((r) => r.state === "open").length,
    in_progress: rows.filter((r) => r.state === "in_progress").length,
    done: rows.filter((r) => r.state === "done").length,
  });
  return [
    {
      key: "verification",
      label: "Verification",
      question: "Is the scanner file true?",
      counts: counts(verification),
      empty_text: verification.length ? null : "Nothing verified yet. Verify claims is on Import.",
      note: null,
      started_on: { label: "Started on Import", page: "inventory/import" },
      rows: verification,
    },
    {
      key: "encryption",
      label: "Encryption tests",
      question: "Is the encryption built right?",
      counts: counts(encryption),
      empty_text: encryption.length ? null : "No test has run yet. The test plan is on Checks.",
      note: null,
      started_on: { label: "The test plan is here", page: "checks" },
      rows: encryption,
    },
    {
      key: "migration",
      label: "Migration",
      question: "Where does each system stand on the move to post-quantum, and what must change?",
      counts: { open: 0, in_progress: 0, done: 0 },
      empty_text: "Nothing measured yet. Measure status is on Migration.",
      note: null,
      started_on: { label: "Started on Migration", page: "migration/systems" },
      rows: [],
    },
    {
      key: "dependencies",
      label: "Dependencies",
      question: "What can your libraries do?",
      counts: { open: 0, in_progress: 0, done: 0 },
      empty_text: "No dependency list yet. Add one on Dependencies.",
      note: null,
      started_on: { label: "Started on Dependencies", page: "migration/dependencies" },
      rows: [],
    },
  ];
}

export const CHECKS_SUBLINE =
  "Every check in this assessment, wherever it was started. The test plan is under Encryption tests; every other check is started where it is today, and its result reads as it does there.";

export const checksView: ChecksView = {
  plan_id: 1,
  title: "Checks",
  subline: CHECKS_SUBLINE,
  groups: checkGroups(),
  busy: false,
  came_from_options: [
    { key: "verify", label: "Verify" },
    { key: "plan", label: "Test plan" },
    { key: "retest", label: "Retest" },
    { key: "proof", label: "Fix proof" },
    { key: "try", label: "Try on a test copy" },
    { key: "after_apply", label: "After Apply" },
    { key: "after_rollback", label: "After Roll back" },
    { key: "measure", label: "Measure status" },
    { key: "public_copy", label: "Measure on a public copy" },
  ],
  libraries: [],
  evidence_counts: {},
};

/** One check in its panel: the retest of the official vectors, with its earlier run and what it relates to. */
export const retestDetail: CheckDetail = {
  check: retestRow,
  result: null,
  verify: null,
  runs: [
    { run_id: 12, verify_run_id: null, at: RETESTED_AT, came_from: "Retest", label: "Passed", tone: "pass", fingerprint: "9f2c41aa07d3b5e1" },
    { run_id: 4, verify_run_id: null, at: RAN_AT, came_from: "Test plan", label: "Failed", tone: "fail", fingerprint: "1b7e02cc93a4f0d8" },
  ],
  related: [
    {
      kind: "claim",
      title: "Claim",
      items: [{ key: "claim-3", label: "acme-sign uses ML-DSA-65", sub: "Couldn't check", link: { page: "inventory/verify", item: "claim-3" }, also: null }],
    },
    {
      kind: "fix",
      title: "Fix",
      items: [
        {
          key: "fix-ecdsa-range-check",
          label: "acme-sign accepts out-of-range signatures",
          sub: "Merged",
          link: { page: "fixes", item: "fix-ecdsa-range-check" },
          also: null,
        },
      ],
    },
  ],
};
