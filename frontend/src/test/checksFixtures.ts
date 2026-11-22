// The Checks page (phase 5b) for the Acme Pay demo, built from the view types with the backend's words
// (backend/app/ledger/groups.py and checks.py). Times and ids are examples.
import type { CheckDetail, CheckGroup, CheckRow, ChecksView } from "../api";
import { couldntCheck, labCopy, live } from "./sourceFixtures";

const VERIFIED_AT = "2026-11-10T09:10:00Z";
const RAN_AT = "2026-11-10T09:20:00Z";
const RETESTED_AT = "2026-11-10T10:05:00Z";

function claimRow(
  id: number,
  name: string,
  ranOn: string,
  label: "True" | "False" | "Couldn't check",
  plain: string,
): CheckRow {
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
    // where it came from: a server claim is read from the server; one the app couldn't check rests on the file
    source_tag: label === "Couldn't check" ? couldntCheck() : ranOn.includes(":") ? live(ranOn) : labCopy(ranOn),
    last_run_at: VERIFIED_AT,
    runs: 1,
  };
}

function testRow(
  id: number,
  name: string,
  ranOn: string,
  passed: boolean,
  origin: "plan" | "retest" = "plan",
  runs = 1,
): CheckRow {
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
    result: passed
      ? { label: "Passed", tone: "pass", code: "passed" }
      : { label: "Failed", tone: "fail", code: "failed" },
    plain: passed ? "Every case gave the expected answer." : "Some cases did not give the expected answer.",
    source_tag: ranOn.includes(":") ? live(ranOn) : labCopy(ranOn),
    last_run_at: origin === "plan" ? RAN_AT : RETESTED_AT,
    runs,
  };
}

export const verifyRows: CheckRow[] = [
  claimRow(1, "Uses TLS 1.3 only", "localhost:8443", "False", "The server also accepts TLS 1.2."),
  claimRow(
    2,
    "Certificate signed with ECDSA P-256",
    "localhost:8443",
    "True",
    "The certificate is signed with ECDSA P-256.",
  ),
  claimRow(3, "acme-sign uses ML-DSA-65", "acme-sign 1.4.2", "Couldn't check", "Nothing was run for this claim."),
];

export const planRows: CheckRow[] = [
  testRow(1, "Official test vectors", "acme-sign 1.4.2", false),
  testRow(2, "Bad signatures", "acme-sign 1.4.2", false),
  testRow(3, "Old TLS versions", "localhost:8443", false),
];

export const retestRow: CheckRow = testRow(
  1,
  "Official test vectors",
  "acme-sign 1.4.3 (the new version)",
  true,
  "retest",
  1,
);

// ---- The 5c fixes: the Crypto tests group in four labelled parts, as the backend sends them ----

export type EncryptionParts = NonNullable<CheckGroup["parts"]>;
type CheckBlock = EncryptionParts["retests"]["blocks"][number];

/** A retest's row in the block of the version it ran on: the test, read on that block's runs only. */
export function blockRow(
  id: number,
  block: number,
  name: string,
  ranOn: string,
  passed: boolean,
  more: Partial<CheckRow> = {},
): CheckRow {
  return {
    ...testRow(id, name, ranOn, passed, "retest"),
    id: `retest-${id}-on-${block}`,
    alias: `retest-${id}`,
    mark: null,
    ...more,
  };
}

export const NO_RETEST = "No retest yet. Retest new version reruns every test in the plan on another version.";

/** The newest block: the retest on acme-sign 1.4.3. A server was not moved, so its test was run again as it is. */
export const newestBlock: CheckBlock = {
  key: "on-2",
  title: "acme-sign 1.4.3",
  line: "One retest on this version. The newest started 10 November 2026, 5:05 am EST.",
  newest: true,
  rows: [
    blockRow(1, 2, "Official test vectors", "acme-sign 1.4.3", true),
    blockRow(2, 2, "Bad signatures", "acme-sign 1.4.3", true),
    blockRow(3, 2, "Old TLS versions", "localhost:8443", false, { mark: "tested again as it is" }),
  ],
};

/** An older block: an earlier retest on another version. Its rows are no longer the newest of their tests. */
export const olderBlock: CheckBlock = {
  key: "on-1",
  title: "acme-sign 1.4.3-otto",
  line: "One retest on this version. The newest started 10 November 2026, 4:40 am EST.",
  newest: false,
  rows: [blockRow(1, 1, "Official test vectors", "acme-sign 1.4.3-otto", true, { alias: null })],
};

export const proofBlock: CheckBlock = {
  key: "proof-1",
  title: "acme-sign 1.4.3 (the changed code)",
  line: "The proof reran the plan's locked tests on the changed code. It started 10 November 2026, 4:50 am EST.",
  newest: true,
  rows: [
    {
      ...testRow(1, "Official test vectors", "acme-sign 1.4.3 (the changed code)", true, "retest"),
      id: "proof-1-in-1",
      alias: "proof-1",
      mark: null,
      came_from: { key: "proof", label: "Fix proof" },
      link: { page: "fixes", item: "fix-ecdsa-range-check", section: "proof" },
    },
  ],
};

export const tryRow: CheckRow = {
  ...testRow(3, "Turn off TLS 1.2 on localhost:8443", "A test copy", true),
  id: "try-tls:localhost:8443-try",
  came_from: { key: "try", label: "Try on a test copy" },
  link: { page: "fixes", item: "fix-tls-versions" },
  evidence_link: { page: "evidence", item: "try-tls:localhost:8443-try" },
};

export function encryptionParts(
  over: {
    retests?: CheckBlock[];
    proofs?: CheckBlock[];
    tries?: CheckRow[];
    tests?: number;
    changes?: CheckBlock[];
  } = {},
): EncryptionParts {
  const retests = over.retests ?? [newestBlock];
  const proofs = over.proofs ?? [];
  const tries = over.tries ?? [];
  const changes = over.changes ?? [];
  const tests = over.tests ?? 3;
  const counted = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
  return {
    plan: {
      key: "plan",
      label: "Test plan",
      count: tests,
      count_label: counted(tests, "test"),
      note: "First runs, on the version the file names: acme-sign 1.4.2.",
      empty_text: null,
      blocks: [],
      rows: [],
    },
    retests: {
      key: "retests",
      label: "Retests by version",
      count: retests.length,
      count_label: counted(retests.length, "version"),
      note: retests.length ? "One block for each version a retest ran on, the newest first." : null,
      empty_text: retests.length ? null : NO_RETEST,
      blocks: retests,
      rows: [],
    },
    proofs: {
      key: "proofs",
      label: "Fix proofs",
      count: proofs.length,
      count_label: counted(proofs.length, "proof"),
      note: proofs.length
        ? "One block for each proof of a change, the newest first. A proof is started in Fixes."
        : null,
      empty_text: proofs.length
        ? null
        : "No fix proof yet. A proof starts in Fixes, when the code of a fix is connected.",
      blocks: proofs,
      rows: [],
    },
    tries: tries.length
      ? {
          key: "tries",
          label: "Tries on a test copy",
          count: tries.length,
          count_label: counted(tries.length, "try", "tries"),
          note: "A try of a server setting change on a test copy. A try is started where the change is.",
          empty_text: null,
          blocks: [],
          rows: tries,
        }
      : null,
    // Phase 6d: only when the tests picked for a developer's change were run.
    changes: changes.length
      ? {
          key: "changes",
          label: "Change watch",
          count: changes.length,
          count_label: counted(changes.length, "run"),
          note: "One block for each run of the tests picked for a developer's change, the newest first. A run is started on Change watch. These runs never replace a result of the test plan.",
          empty_text: null,
          blocks: changes,
          rows: [],
        }
      : null,
  };
}

/** Phase 6d: one run of the tests picked for a developer's change, as Checks lists it. */
export const watchBlock: CheckBlock = {
  key: "watch-1",
  title: "From a developer's change: dev/revert-range-check, commit bd2fc09",
  line: "The tests picked for this change ran on its code, acme-sign 1.4.2. The run started 19 November 2026, 6:28 am EST.",
  newest: true,
  rows: [
    {
      ...testRow(
        1,
        "Official test vectors",
        "acme-sign 1.4.2, the change on dev/revert-range-check (commit bd2fc09)",
        false,
        "retest",
      ),
      id: "watch-1-in-1",
      alias: null,
      mark: null,
      came_from: { key: "watch", label: "Change watch" },
      link: { page: "change-watch", item: "change-bd2fc0900000" },
    },
  ],
};

export function checkGroups(
  over: { verification?: CheckRow[]; encryption?: CheckRow[]; parts?: EncryptionParts | null } = {},
): CheckGroup[] {
  const verification = over.verification ?? verifyRows;
  const encryption = over.encryption ?? [...planRows, retestRow];
  // (the backend always sends the parts with this group; `parts: null` is a view from before the 5c fixes)
  const parts =
    over.parts === undefined
      ? encryptionParts(over.encryption && !over.encryption.includes(retestRow) ? { retests: [] } : {})
      : over.parts;
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
      label: "Crypto tests",
      question: "Is the cryptography built right?",
      counts: counts(encryption),
      empty_text: encryption.length ? null : "No test has run yet. The test plan is on Checks.",
      note: null,
      started_on: { label: "The test plan is here", page: "checks" },
      rows: encryption,
      parts,
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
  "Every check in this assessment, wherever it was started. The test plan is under Crypto tests; every other check is started where it is today, and its result reads as it does there.";

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
    {
      run_id: 12,
      verify_run_id: null,
      at: RETESTED_AT,
      came_from: "Retest",
      label: "Passed",
      tone: "pass",
      fingerprint: "9f2c41aa07d3b5e1",
    },
    {
      run_id: 4,
      verify_run_id: null,
      at: RAN_AT,
      came_from: "Test plan",
      label: "Failed",
      tone: "fail",
      fingerprint: "1b7e02cc93a4f0d8",
    },
  ],
  related: [
    {
      kind: "claim",
      title: "Claim",
      items: [
        {
          key: "claim-3",
          label: "acme-sign uses ML-DSA-65",
          sub: "Couldn't check",
          link: { page: "inventory/verify", item: "claim-3" },
          also: null,
        },
      ],
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
