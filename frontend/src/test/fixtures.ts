import { vi } from "vitest";
import type {
  Address,
  Claim,
  EvidenceExport,
  FixLine,
  Import,
  LabResult,
  LabRow,
  LabView,
  PlanView,
  Session,
  TestCard,
  TestKind,
  VerifyRun,
} from "../api";

export const session: Session = {
  setup_required: false,
  logged_in: true,
  mode: "demo",
  mode_line: "Demo mode: running our own demo software, not isolated.",
  demo_server: { address: "localhost:8443", running: true, error: null },
};

export const claims: Claim[] = [
  {
    id: 1,
    ref: "tls-acme-pay",
    location: "localhost:8443",
    location_kind: "server",
    kind: "protocol_versions",
    claimed_value: "TLS 1.3",
    text: "localhost:8443 accepts TLS 1.3 only",
    source: "components[0] (bom-ref tls-acme-pay)",
  },
  {
    id: 2,
    ref: "cert-acme-pay",
    location: "localhost:8443",
    location_kind: "server",
    kind: "certificate",
    claimed_value: "ECDSA P-256",
    text: "localhost:8443 certificate is ECDSA P-256",
    source: "components[1] (bom-ref cert-acme-pay)",
  },
  {
    id: 3,
    ref: "acme-sign",
    location: "acme-sign 1.4.2",
    location_kind: "software",
    kind: "signature_algorithm",
    claimed_value: "ECDSA P-256",
    text: "signing component is acme-sign 1.4.2 implementing ECDSA P-256",
    source: "components[2] (bom-ref acme-sign)",
  },
];

export const address: Address = {
  address: "localhost:8443",
  host: "localhost",
  port: 8443,
  resolved_ip: "127.0.0.1",
  is_loopback: true,
  confirmed: false,
  error: null,
};

export const demoImport: Import = {
  id: 7,
  filename: "acme-pay-cbom.json",
  format: "cyclonedx-cbom",
  is_demo: true,
  claims,
  addresses: [address],
  skipped: [],
};

const evidence = {
  title: "TLS 1.2 handshake",
  command: "openssl s_client -connect localhost:8443 -tls1_2",
  output: "Protocol  : TLSv1.2\nCipher    : ECDHE-ECDSA-AES128-SHA",
  started_at: "2026-11-11T10:00:00Z",
  duration_ms: 42,
  tool: "OpenSSL",
  tool_version: "3.0.13",
};

export const run: VerifyRun = {
  id: 1,
  import_id: 7,
  started_at: "2026-11-11T10:00:00Z",
  finished_at: "2026-11-11T10:00:02Z",
  results: [
    {
      claim_id: 1,
      claim: claims[0]!,
      result: "False",
      found: "Accepts TLS 1.3 and TLS 1.2 (with ECDHE-ECDSA-AES128-SHA). Refuses TLS 1.1 and TLS 1.0.",
      reason: null,
      evidence: [evidence],
    },
    {
      claim_id: 2,
      claim: claims[1]!,
      result: "True",
      found: "The certificate uses an ECDSA P-256 key.",
      reason: null,
      evidence: [{ ...evidence, title: "Certificate read", command: "openssl x509 -noout -text" }],
    },
    {
      claim_id: 3,
      claim: claims[2]!,
      result: "Couldn't check",
      found: "Nothing was measured.",
      reason: "The component did not start within the time limit.",
      evidence: [],
    },
  ],
};

type Reply = { status?: number; body: unknown };
type Route = Reply | ((init: RequestInit | undefined) => Reply);

/** Replaces fetch with a table of "METHOD /path" -> reply. Unknown calls fail the test loudly. */
export function mockApi(routes: Record<string, Route>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${String(input)}`;
    const route = routes[key];
    if (!route) throw new Error(`Unexpected request: ${key}`);
    const reply = typeof route === "function" ? route(init) : route;
    return new Response(JSON.stringify(reply.body), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function calls(fetchMock: ReturnType<typeof mockApi>): string[] {
  return fetchMock.mock.calls.map(([input, init]) => `${init?.method ?? "GET"} ${String(input)}`);
}

export const notFound: Reply = { status: 404, body: { error: { message: "Not found", line: null, field: null } } };

/** The visible text of an element with runs of whitespace collapsed (empty if the element is missing). */
export function text(el: Element | null | undefined): string {
  return (el?.textContent ?? "").replace(/\s+/g, " ").trim();
}

// ---- Phase 2 payloads, copied from the design contract (section 4) ----

function card(id: number, kind: TestKind, title: string, description: string, why: string): TestCard {
  return {
    id,
    kind,
    title,
    origin: "suggested",
    tag: null,
    description,
    why,
    status: "not_run",
    status_text: "Not run yet",
    progress: null,
    result: null,
    can_run: true,
    can_remove: true,
  };
}

export const cards: TestCard[] = [
  card(
    11,
    "tls_versions",
    "Old TLS versions",
    "Checks whether the server at localhost:8443 accepts any TLS version older than the file claims (TLS 1.3 only).",
    "Why it matters: older versions have known weaknesses and are easy to leave switched on.",
  ),
  card(
    12,
    "certificate",
    "Certificate strength",
    "Checks that the server's certificate uses the algorithm and key size the file claims, and compares them with current NIST guidance.",
    "Why it matters: a weak or outdated certificate undermines every connection.",
  ),
  card(
    13,
    "official_vectors",
    "Official test vectors",
    "Gives acme-sign 484 published signature cases with known right answers (Project Wycheproof, ECDSA P-256) and counts any it gets wrong.",
    "Why it matters: these cases were written to catch real, known mistakes.",
  ),
  card(
    14,
    "bad_signatures",
    "Bad signatures",
    "Feeds acme-sign signatures it must reject: changed messages, changed signatures, wrong lengths, zeros and out-of-range values.",
    "Why it matters: accepting one forged signature defeats the point of signing.",
  ),
  card(
    15,
    "speed_size",
    "Speed and size",
    "Times signing and checking inside the program (200 repeats each) and records key and signature sizes. Reports numbers; no pass or fail on the first run.",
    "Why it matters: gives a baseline, so a later version that slows down gets noticed.",
  ),
];

export const pqCard: TestCard = {
  ...card(
    16,
    "pq_readiness",
    "Post-quantum readiness",
    "Checks whether the server at localhost:8443 offers the newer quantum-resistant key exchange (X25519MLKEM768).",
    "Why it matters: shows how far the server is from the post-quantum move.",
  ),
  origin: "added",
};

export const plan: PlanView = {
  id: 1,
  import_id: 7,
  is_demo: true,
  intro:
    "Five tests suggested from the claims in acme-pay-cbom.json. Drag to change the order, remove any you don't want, then run them.",
  subject: [
    { t: "text", v: "Testing: server " },
    { t: "mono", v: "localhost:8443" },
    { t: "text", v: " and signing component " },
    { t: "mono", v: "acme-sign 1.4.2" },
    { t: "text", v: " " },
    { t: "tag", v: "from the file" },
  ],
  running: false,
  can_run_all: true,
  has_results: false,
  max_parallel: 4,
  tests: cards,
  catalog_title: "Tests you can add",
  catalog: [
    {
      catalog_id: "pq_readiness",
      title: "Post-quantum readiness",
      tag: null,
      description: "Checks whether the server offers the newer quantum-resistant key exchange (X25519MLKEM768).",
    },
    {
      catalog_id: "mldsa_compare",
      title: "ML-DSA-65 comparison",
      tag: "reference, not production",
      description:
        "Shows the speed and sizes of a post-quantum signature (ML-DSA-65) from a reference implementation, next to acme-sign's.",
    },
  ],
  catalog_note: "Tests you remove from the plan come back to this list.",
};

const locked = (c: TestCard): TestCard => ({ ...c, can_run: false });

/** Every status at once: done, running with a bar, running without, waiting, not run. */
export const runningPlan: PlanView = {
  ...plan,
  intro:
    "Six tests in the plan: five suggested from the claims, one added by you. Drag to change the order, remove any you don't want, then run them.",
  running: true,
  can_run_all: false,
  has_results: true,
  tests: [
    { ...locked(cards[0]!), status: "done", status_text: "Failed", result: { code: "failed", label: "Failed", tone: "fail" } },
    {
      ...locked(cards[1]!),
      status: "running",
      status_text: "Running",
      progress: { text: "reading the certificate", percent: null },
      can_remove: false,
    },
    {
      ...locked(cards[2]!),
      status: "running",
      status_text: "Running",
      progress: { text: "312 of 484 cases", percent: 64 },
      can_remove: false,
    },
    locked(cards[3]!),
    locked(cards[4]!),
    {
      ...locked(pqCard),
      status: "waiting",
      status_text: "Waiting",
      progress: { text: "4 tests run at once; starts when one finishes", percent: null },
      can_remove: false,
    },
  ],
  catalog: [plan.catalog[1]!],
};

export const FINGERPRINT = "7c1f9a3e52b08d46e0a97b15c3d2f48861ae0b7d94c5f3210e8d6a4b9f7c2e15";
export const DISCLAIMER = "Passing these tests doesn't prove a system secure. It shows these specific checks passed.";

// ---- Phase 3a: the one line on a failed result that points to its fix (contract 5.3, the mockup's words) ----

const CHANGE_SIZE = "3 lines added and 1 removed";

function fixLine(fix_id: string, lead: string, rest: string, look: FixLine["look"]): FixLine {
  return { fix_id, lead, rest, look, busy: false, button: "View in Fixes" };
}

const codeLine = (lead: string, rest: string, look: FixLine["look"]) => fixLine("fix-ecdsa-range-check", lead, rest, look);

/** The line in each of its states. */
export const fixLines = {
  not_connected: codeLine("Fix available,", "code not connected", "plain"),
  proving: { ...codeLine("Fix prepared:", `${CHANGE_SIZE}, proof running`, "plain"), busy: true },
  passed: codeLine("Fix ready:", `${CHANGE_SIZE}, proof passed`, "pass"),
  failed: codeLine("Fix not offered:", "the proof did not pass", "fail"),
  merged: codeLine("Fix merged:", `${CHANGE_SIZE}, proof passed`, "plain"),
  text_only: fixLine("fix-tls-versions", "Text-only suggestion:", "a server setting", "dashed"),
} satisfies Record<string, FixLine>;

export const vectorsResult: LabResult = {
  run_id: 7,
  component: "acme-sign 1.4.2",
  mode: "demo",
  finished_at: "2026-11-11T01:42:16.000Z",
  duration_ms: 9400,
  code: "failed",
  label: "Failed",
  tone: "fail",
  summary: "3 of 484 official cases wrong. Headline: case 168, a signature made of zeros (r=0 and s=0) was accepted.",
  short: "3 of 484 official cases wrong (168, 171, 364), all from one missing range check.",
  control: {
    outcome: "as_expected",
    line: "Control: a deliberately broken signer failed this test, as expected.",
    text: "The deliberately broken signer got all 310 invalid cases wrong, so it failed as expected. That tells us this test can catch a faulty signer, and the result above can be trusted.",
  },
  what_happened: [
    'acme-sign 1.4.2 was shown 484 official signatures and asked "is this one genuine?". It gave the wrong answer 3 times.',
    "The clearest is case 168: a signature made only of zeros.",
  ],
  shows_title: "What this shows, and what it doesn't",
  shows: [
    "It shows this version accepts specific forged signatures that a correct ECDSA P-256 checker rejects.",
    "It doesn't show whether anyone has used this.",
  ],
  evidence: [
    {
      type: "table",
      title: "The 3 cases it got wrong",
      tag: "measured",
      columns: [
        { label: "Official case", align: "left", mono: true },
        { label: "What the case is", align: "left" },
        { label: "Right answer", align: "left" },
        { label: "acme-sign 1.4.2 said", align: "left" },
      ],
      rows: [
        ["168", "r=0 and s=0 (a signature made of zeros)", "reject", "accepted"],
        ["171", "r=0 and s=n (zero, written a second way)", "reject", "accepted"],
        ["364", "s larger than n (a value outside the allowed range)", "reject", "accepted"],
      ],
      meta: [],
      note: null,
    },
  ],
  run_record: {
    title: "Run record",
    command: "acme-sign verify (once per case, JSON in, JSON out), 484 cases from ecdsa_secp256r1_sha256_test.json",
    outputs: [{ title: "Output summary", text: "cases run: 484   right: 481   wrong: 3\nreview step: pass/fail rule applied => Failed" }],
    meta: [
      { label: "Time", value: "", time: "2026-11-11T01:42:07.000Z", tag: null },
      { label: "Duration", value: "9.4 s", tag: "measured" },
      { label: "Component", value: "acme-sign 1.4.2", tag: "demo" },
      { label: "Code", value: "the bundled demo version of acme-sign 1.4.2", tag: "demo" },
      { label: "Mode", value: "Demo mode, not isolated", tag: null },
      {
        label: "Vectors",
        value: "Project Wycheproof, C2SP/wycheproof commit dab4ea2",
        tag: "reference",
        href: "https://github.com/C2SP/wycheproof/tree/dab4ea2ed021eb633874959ca601004f3457d911/testvectors_v1",
      },
    ],
  },
  locked_test: {
    title: "Test details, locked before the run",
    fields: [
      { label: "Question", lines: ["Does acme-sign give the right answer on every official ECDSA P-256 test case?"] },
      { label: "Method", lines: ["Run the verify command once per case and compare its answer with the published one."] },
      { label: "Inputs", lines: ["Wycheproof file (484 cases), pinned to commit dab4ea2.", "The Ed25519 file is run on the reference library."] },
      { label: "Control", lines: ["The same cases run against a deliberately broken signer, which must get every invalid case wrong."] },
      { label: "Pass/fail rule", lines: ["Passed only if all 484 answers are right. Any wrong answer means Failed."] },
    ],
    locked_at: "2026-11-11T01:41:52.000Z",
    locked_text: "before the run started",
    fingerprint_label: "Fingerprint of these details (SHA-256)",
    fingerprint: FINGERPRINT,
    note: "The details can't change after locking.",
  },
  fix_title: "Suggested fix",
  suggested_fix: null,
  fix_line: fixLines.not_connected,
  reviewed: null,
  research: null,
};

export const research: NonNullable<LabResult["research"]> = {
  id: 1,
  title: "Research request saved",
  badge: "Queued",
  status: "waiting for research engine",
  status_line: "Status: waiting for research engine",
  fields: [
    { label: "Finding", value: "Official test vectors: Failed, 3 of 484 cases wrong on acme-sign 1.4.2" },
    { label: "Question", value: "Why does this version accept cases 168, 171 and 364?" },
    { label: "Evidence attached", value: "The run record and locked test details above" },
  ],
  saved_at: "2026-11-11T01:47:30.000Z",
  note: "No answer yet. The research engine isn't connected in this version, so nothing has been looked into and this result is unchanged.",
};

/** A small result of any label, for rows whose detail a test doesn't look into. */
export function result(runId: number, code: LabResult["code"], label: string, tone: LabResult["tone"], summary: string): LabResult {
  return {
    ...vectorsResult,
    run_id: runId,
    code,
    label,
    tone,
    summary,
    short: summary,
    evidence: [],
    suggested_fix: code === "couldnt_run" || code === "couldnt_trust" ? null : "None needed.",
    fix_line: null,
  };
}

export const speedAfter: LabResult = {
  ...result(25, "no_slowdown", "No slowdown beyond measured noise", "pass", "Sign 7.0 ms, verify 13.4 ms (medians). Noise: ±2.4%."),
  component: "acme-sign 1.4.3",
  evidence: [
    {
      type: "table",
      title: "Timings and sizes, before and after",
      tag: null,
      columns: [
        { label: "What was measured", align: "left" },
        { label: "acme-sign 1.4.2\nbefore", align: "right" },
        { label: "acme-sign 1.4.3\nafter", align: "right" },
        { label: "Change", align: "right" },
        { label: "Reference library\n(cryptography)", align: "right" },
      ],
      rows: [
        ["Sign, median", "7.1 ms", "7.0 ms", "-1.4%", "0.04 ms"],
        ["Signature size, this run", "71 bytes", "71 bytes", "none", "71 bytes"],
      ],
      meta: [
        { label: "Repeats", value: "200 sign and 200 verify per version, in 10 alternating rounds", tag: null },
        { label: "Measured noise", value: "±2.4% (from the paired differences in this run)", tag: null },
        { label: null, value: "acme-sign columns", tag: "measured" },
        { label: null, value: "last column", tag: "reference" },
      ],
      note: "The reference library is a heavily optimised production library. It is shown for scale only and is not part of the slowdown rule.",
    },
  ],
  run_record: {
    ...vectorsResult.run_record,
    command: "acme-sign bench",
    outputs: [
      { title: "Output summary, acme-sign 1.4.2", text: "sign median 7.1 ms" },
      { title: "Output summary, acme-sign 1.4.3", text: "sign median 7.0 ms" },
    ],
  },
  suggested_fix: "None needed. No slowdown beyond measured noise was found.",
};

function row(item_id: number, kind: TestKind, title: string, control_line: string, r: LabResult | null): LabRow {
  return { item_id, kind, title, control_line, result: r, result_status: null, after: null, after_status: null };
}

export const labRows: LabRow[] = [
  row(
    11,
    "tls_versions",
    "Old TLS versions",
    "Control: a deliberately misconfigured test server failed this test, as expected.",
    {
      ...result(5, "failed", "Failed", "fail", "The server accepted TLS 1.2. The file claims TLS 1.3 only."),
      suggested_fix: null,
      fix_line: fixLines.text_only,
    },
  ),
  row(
    12,
    "certificate",
    "Certificate strength",
    "Control: a deliberately weak test certificate failed this test, as expected.",
    result(6, "passed", "Passed", "pass", "The certificate is ECDSA P-256, 256 bits, as claimed."),
  ),
  row(13, "official_vectors", "Official test vectors", "Control: a deliberately broken signer failed this test, as expected.", vectorsResult),
  row(
    15,
    "speed_size",
    "Speed and size",
    "Control: a deliberately slowed signer was flagged as slower, as expected.",
    result(9, "measured", "Measured", "neutral", "Sign 7.1 ms, verify 13.2 ms (medians over 200 repeats)."),
  ),
  row(
    16,
    "pq_readiness",
    "Post-quantum readiness",
    "Control: not run, because the test couldn't run.",
    result(10, "couldnt_run", "Couldn't run (needs OpenSSL 3.5 or newer)", "warn", "The checker on this computer is too old."),
  ),
];

export const lab: LabView = {
  plan_id: 1,
  is_demo: true,
  view: "results",
  subline: [
    { t: "text", v: "Results by test for server " },
    { t: "mono", v: "localhost:8443" },
    { t: "text", v: " and signing component " },
    { t: "mono", v: "acme-sign 1.4.2" },
    { t: "text", v: ". Run finished " },
    { t: "time", v: "2026-11-11T01:42:16.000Z" },
    { t: "text", v: "." },
  ],
  code_line: null,
  disclaimer: DISCLAIMER,
  columns: null,
  rows: labRows,
  retest: {
    can_start: true,
    blocked_reason: null,
    running: false,
    progress_text: null,
    menu_title: "Choose the version to retest",
    versions: [
      { version: "1.4.3", label: "acme-sign 1.4.3", tag: "demo", note: "The corrected demo version." },
      { version: "1.4.2", label: "acme-sign 1.4.2", tag: "demo", note: "The demo version these results are for." },
    ],
    menu_note:
      "Choosing a version reruns the same five locked tests on it and shows before and after. Only our two demo versions can be chosen here.",
  },
  download: { can_start: true, blocked_reason: null },
};

/** Swaps one row's first-run result. */
export function withResult(view: LabView, itemId: number, change: Partial<LabResult>): LabView {
  return {
    ...view,
    rows: view.rows.map((r) => (r.item_id === itemId && r.result ? { ...r, result: { ...r.result, ...change } } : r)),
  };
}

export const beforeAfter: LabView = {
  ...lab,
  view: "before_after",
  subline: [
    { t: "text", v: "Before and after: the same five locked tests, run on " },
    { t: "mono", v: "acme-sign 1.4.2" },
    { t: "text", v: " and then on " },
    { t: "mono", v: "acme-sign 1.4.3" },
    { t: "text", v: ". Retest finished " },
    { t: "time", v: "2026-11-11T01:55:03.000Z" },
    { t: "text", v: "." },
  ],
  // Which code each side ran on, as after "Retest now" on the merged fix (mockup picture 12).
  code_line: [
    {
      t: "text",
      v: "Code they ran on: before, the bundled demo version of acme-sign 1.4.2; after, the merged fix: branch main, commit c41f0d2 (pull request #1), the same byte for byte as our bundled acme-sign 1.4.3.",
    },
  ],
  columns: {
    test: "Test",
    before: "Before: acme-sign 1.4.2",
    after: "After: acme-sign 1.4.3",
    before_note: [{ t: "text", v: "the bundled demo version" }],
    after_note: [
      { t: "text", v: "the merged fix, commit " },
      { t: "mono", v: "c41f0d2" },
    ],
    before_heading: "Before: acme-sign 1.4.2, the bundled demo version",
    after_heading: "After: acme-sign 1.4.3, the merged fix (commit c41f0d2)",
  },
  rows: labRows.map((r) => ({
    ...r,
    control_line: "Control failed as expected in both runs.",
    result: r.kind === "official_vectors" && r.result ? { ...r.result, fix_line: fixLines.merged } : r.result,
    after:
      r.kind === "official_vectors"
        ? { ...result(23, "passed", "Passed", "pass", "484 of 484 official cases right."), component: "acme-sign 1.4.3" }
        : r.kind === "speed_size"
          ? speedAfter
          : r.result
            ? { ...r.result, run_id: r.result.run_id + 20 }
            : null,
  })),
};

export const retestRunning: LabView = {
  ...beforeAfter,
  subline: [{ t: "text", v: "Before and after: the same five locked tests. Retest running." }],
  rows: beforeAfter.rows.map((r, i) => ({
    ...r,
    after: i === 0 ? r.after : null,
    after_status:
      i === 0
        ? null
        : i === 1
          ? { status: "running", status_text: "Running", progress: { text: "reading the certificate", percent: 40 } }
          : { status: "waiting", status_text: "Waiting", progress: null },
  })),
  retest: { ...lab.retest, can_start: false, blocked_reason: "A retest is running.", running: true, progress_text: "Retest running: 1 of 5 tests finished." },
  download: { can_start: false, blocked_reason: "A retest is running." },
};

export const evidenceExport: EvidenceExport = {
  id: 3,
  created_at: "2026-11-11T01:58:10.000Z",
  fingerprint: "5e1c".padEnd(64, "a"),
  fingerprint_label: "Fingerprint (SHA-256)",
  json: { url: "/api/evidence/3/json", filename: "evidence-lab-evidence-20261111-015810.json" },
  html: { url: "/api/evidence/3/html", filename: "evidence-lab-report-20261111-015810.html" },
  message: "Two files were downloaded: the evidence (JSON) and a readable report (HTML). The JSON file is the record.",
  verify_hint: "To check the file: cd backend && .venv/bin/python -m evidence verify <the downloaded .json file>",
};
