// Typed client for the backend API. Everything the screens know about the
// server goes through here.

export type ClaimKind =
  | "protocol_versions"
  | "cipher_suites"
  | "key_exchange"
  | "certificate"
  | "signature_algorithm"
  /** Phase 4a: "classical", "hybrid" or "post-quantum only", checked with the migration measurement. */
  | "post_quantum";

export type LocationKind = "server" | "software" | "unknown";

export type ResultValue = "True" | "False" | "Couldn't check";

export interface DemoServer {
  address: string;
  running: boolean;
  error: string | null;
}

export type Mode = "demo" | "isolated";

export interface Session {
  setup_required: boolean;
  logged_in: boolean;
  mode: Mode;
  /** The sentence under the header saying how software is run, written by the backend. */
  mode_line: string;
  demo_server: DemoServer;
}

export interface Claim {
  id: number;
  ref: string;
  location: string;
  location_kind: LocationKind;
  kind: ClaimKind;
  claimed_value: string;
  text: string;
  source: string;
}

export interface Address {
  address: string;
  host: string;
  port: number;
  resolved_ip: string | null;
  is_loopback: boolean;
  confirmed: boolean;
  error: string | null;
}

/** Something in the file that this version doesn't check (for example a hash algorithm). */
export interface SkippedItem {
  name: string;
  what: string;
  source: string;
  reason: string;
}

export interface Import {
  id: number;
  filename: string;
  format: "cyclonedx-cbom" | "csv";
  is_demo: boolean;
  claims: Claim[];
  addresses: Address[];
  /** Always sent by the current backend; optional so an older reply doesn't break the screen. */
  skipped?: SkippedItem[];
  /** Plain sentences about what the upload started on this computer (for example the demo test servers). Only on the upload reply. */
  notices?: string[];
  /** The heading of the settings list, e.g. "System settings from the file". */
  settings_title?: string;
  /** Settings rows the file carries (not claims: nothing checks them). Optional: older stored answers may lack it. */
  settings?: ImportSetting[];
}

/** One settings row from the file, e.g. location "localhost:8451", text "Exposure: internet-facing. Data lifespan: long-lived." */
export interface ImportSetting {
  location: string;
  text: string;
}

export interface Evidence {
  title: string;
  command: string;
  output: string;
  started_at: string;
  duration_ms: number;
  tool: string;
  tool_version: string;
}

export interface Result {
  claim_id: number;
  claim: Claim;
  result: ResultValue;
  found: string;
  reason: string | null;
  evidence: Evidence[];
  /** One plain sentence: what was found and why that gives this result. Shown on top of the row. */
  summary: string;
  /** Things the check saw that the file didn't ask about. Side notes, never a result. Often empty. */
  also_noticed: string[];
}

export interface VerifyRun {
  id: number;
  import_id: number;
  started_at: string;
  finished_at: string;
  results: Result[];
}

// ---- Phase 2: test plan and Evidence Lab. All wording comes from the backend. ----

export type TestKind =
  | "tls_versions"
  | "certificate"
  | "official_vectors"
  | "bad_signatures"
  | "speed_size"
  | "pq_readiness"
  | "mldsa_compare";

export type ResultCode =
  | "passed"
  | "failed"
  | "couldnt_run"
  | "couldnt_trust"
  | "measured"
  | "no_slowdown"
  | "slowdown"
  | "offered"
  | "not_offered";

export type Tone = "pass" | "fail" | "neutral" | "warn";
export type JobStatus = "not_run" | "waiting" | "running" | "done";
/** "demo" is drawn as the violet "Demo data" label. */
export type RichPart = { t: "text" | "mono" | "tag" | "time" | "demo"; v: string };
export type RichText = RichPart[];

export interface Progress {
  text: string;
  percent: number | null;
}

export interface Badge {
  code: ResultCode;
  label: string;
  tone: Tone;
}

export interface TestCard {
  id: number;
  kind: TestKind;
  title: string;
  origin: "suggested" | "added";
  tag: string | null;
  description: string;
  why: string;
  status: JobStatus;
  status_text: string;
  progress: Progress | null;
  result: Badge | null;
  can_run: boolean;
  can_remove: boolean;
  /** The key of the group this card is under, when the plan is grouped. */
  group: string | null;
}

/** A heading the cards (or Evidence Lab rows) are grouped under, e.g. "Server: localhost:8444". */
export interface PlanGroup {
  key: string;
  kind: "server" | "software" | "reference";
  heading: string;
  note: string | null;
}

/** The "Not tested, and why" box: every target or test the plan leaves out, one line each. */
export interface NotTested {
  title: string;
  items: string[];
}

export interface CatalogItem {
  catalog_id: TestKind;
  title: string;
  tag: string | null;
  description: string;
}

export interface PlanView {
  id: number;
  import_id: number;
  is_demo: boolean;
  intro: string;
  subject: RichText;
  running: boolean;
  can_run_all: boolean;
  has_results: boolean;
  /** A migration measurement exists for this plan (the Fixes step opens for it too). */
  has_migration: boolean;
  max_parallel: number;
  /** True when the file has more than one server or signing program: cards are drawn under group headings. */
  grouped: boolean;
  /** In display order. Sent even when not grouped (the screen then ignores them). */
  groups: PlanGroup[];
  not_tested: NotTested | null;
  /** When grouped, already ordered group by group, in the order of `groups`. */
  tests: TestCard[];
  catalog_title: string;
  catalog: CatalogItem[];
  catalog_note: string;
}

export interface MetaItem {
  label: string | null;
  value: string;
  tag: string | null;
  time?: string;
  href?: string;
}

export interface TableColumn {
  label: string;
  align: "left" | "right";
  mono?: boolean;
}

export type EvidenceBlock =
  | {
      type: "table";
      title: string;
      tag: string | null;
      columns: TableColumn[];
      rows: string[][];
      meta: MetaItem[];
      note: string | null;
    }
  | { type: "text"; title: string; tag: string | null; text: string };

export interface RunRecordView {
  title: string;
  command: string;
  outputs: { title: string; text: string }[];
  meta: MetaItem[];
}

export interface LockedTestView {
  title: string;
  fields: { label: string; lines: string[] }[];
  locked_at: string;
  locked_text: string;
  fingerprint_label: string;
  fingerprint: string;
  note: string;
}

export interface ResearchView {
  id: number;
  title: string;
  badge: string;
  status: string;
  status_line: string;
  fields: { label: string; value: string }[];
  saved_at: string;
  note: string;
}

/** Published advisories for the tested version. Information from the advisory, never a result. */
export interface Advisories {
  title: string;
  tag: string;
  items: { id: string; text: string; link: string; href: string; covered: string }[];
}

export interface LabResult extends Badge {
  run_id: number;
  component: string | null;
  mode: Mode;
  finished_at: string;
  duration_ms: number;
  summary: string;
  short: string;
  /** One plain sentence: what was found and why that gives this result. */
  plain: string;
  /** Side notes about things the test saw that it wasn't asked about. Never a result. */
  also_noticed: string[];
  also_noticed_title: string;
  control: { outcome: "as_expected" | "not_as_expected" | "errored" | "not_run"; line: string; text: string };
  what_happened: string[];
  shows_title: string;
  shows: string[];
  evidence: EvidenceBlock[];
  run_record: RunRecordView;
  locked_test: LockedTestView;
  fix_title: string;
  suggested_fix: string | null;
  /** When set, suggested_fix is null and the "Suggested fix" box is not drawn. */
  fix_line: FixLine | null;
  reviewed: { at: string; text: string } | null;
  research: ResearchView | null;
  /** Phase 4c: advisories for this version. Missing in older answers: treated as null. */
  advisories?: Advisories | null;
}

export interface RowStatus {
  status: JobStatus;
  status_text: string;
  progress: Progress | null;
}

export interface LabRow {
  item_id: number;
  kind: TestKind;
  title: string;
  control_line: string;
  result: LabResult | null;
  result_status: RowStatus | null;
  after: LabResult | null;
  after_status: RowStatus | null;
  group: string | null;
}

export interface RetestVersion {
  version: string;
  /** Which library this version belongs to. Missing in older answers: the plan's own program. */
  component?: string;
  label: string;
  tag: string;
  note: string;
}

export interface LabView {
  plan_id: number;
  is_demo: boolean;
  view: "results" | "before_after";
  subline: RichText;
  /** "Code they ran on: before, ...; after, ..." (before/after view only). */
  code_line: RichText | null;
  disclaimer: string;
  columns: {
    test: string;
    before: string;
    after: string;
    /** The second line under each heading: which code that side ran on. */
    before_note: RichText;
    after_note: RichText;
    /** The headings of the opened details. */
    before_heading: string;
    after_heading: string;
  } | null;
  grouped: boolean;
  groups: PlanGroup[];
  not_tested: NotTested | null;
  /** When grouped, already ordered group by group, in the order of `groups`. */
  rows: LabRow[];
  retest: {
    can_start: boolean;
    blocked_reason: string | null;
    running: boolean;
    progress_text: string | null;
    menu_title: string;
    versions: RetestVersion[];
    menu_note: string;
  };
  download: { can_start: boolean; blocked_reason: string | null };
  /** Something is running for this file (tests, a retest or a proof in Fixes): ask again in a second. */
  busy: boolean;
}

export interface EvidenceExport {
  id: number;
  created_at: string;
  fingerprint: string;
  fingerprint_label: string;
  json: { url: string; filename: string };
  html: { url: string; filename: string };
  message: string;
  verify_hint: string;
}

// ---- Phase 3a: the Fixes step. Everything a user reads is in here as text written by the backend. ----

/** The one line on a failed result that has a fix in the Fixes step. */
export interface FixLine {
  fix_id: string;                 // which fix "View in Fixes" opens
  lead: string;                   // "Fix ready:"            (drawn bold)
  rest: string;                   // "3 lines added and 1 removed, proof passed"
  look: "plain" | "pass" | "fail" | "dashed";
  busy: boolean;                  // true while the proof runs: a small spinner before the words
  button: string;                 // "View in Fixes"
}

export type FixStatusKey =
  | "not_connected"
  | "proving"
  | "ready"
  | "failed"
  | "waiting"
  | "ready_to_merge"
  | "merged"
  | "text_only";

export interface FixStatus {
  key: FixStatusKey;
  word: string;                   // "Ready for review"
  busy: boolean;                  // true while proving: the chip shows a spinner
}

/** "Before: " + strong + rest, e.g. lead "Before:", strong "acme-sign 1.4.2", rest ", nothing removed here". */
export interface StrongLabel {
  lead: string;
  strong: string;
  rest: string;
}

/** One line of code in a before or after block. n is the line number in that version of the file. */
export interface DiffLine {
  n: number;
  mark: " " | "-" | "+";
  text: string;
}

export interface ChangePart {
  title: string;                  // "1. The check: reject a signature whose numbers are out of range"
  why: string;
  before_label: StrongLabel;
  before: DiffLine[];
  after_label: StrongLabel;
  after: DiffLine[];
}

/** A result badge and one line under it, as in Evidence Lab's before/after cells. */
export interface ProofCell {
  label: string;
  tone: Tone;
  short: string;
}

export interface ProofWaiting {
  text: string;                   // "Running" or "Waiting"
  detail: string | null;          // "212 of 484 cases"
  percent: number | null;
}

export interface ProofRow {
  kind: TestKind;
  title: string;
  before: ProofCell | null;       // the first result this is compared with
  proof: ProofCell | null;        // null while this test has no proof result yet
  waiting: ProofWaiting | null;   // set while it is waiting or running
  control: string;                // the control line under the proof cell
  check: { ok: boolean | null; text: string };   // "Passed", "No slowdown", "Same as before", "Did not pass", "Not finished yet"
}

export interface ProofTable {
  heading: string;                // "Tests that run the changed code"
  tag: string;                    // "measured"
  need: string;
  columns: [string, string, string, string];     // "Test", "Before: acme-sign 1.4.2", "On the changed code", "Rule check"
  rows: ProofRow[];
}

export interface ProofVerdict {
  tone: "pass" | "fail";
  title: string;                  // "Why it is ready for review" | "Why this change is not offered"
  checks: { ok: boolean; text: string }[];
  shows_title: string | null;     // "What this proof shows, and what it doesn't"
  shows: string[];
}

export interface DetailFact {
  label: string;
  value: RichText;
  fingerprint: boolean;           // true: draw the value small, fixed-width, breaking anywhere
}

export interface RanOn {
  title: string;                  // "What the tests ran on"
  text: RichText;
  fingerprints: { label: string; value: string; tag: string }[];
  note: string;
}

/** The fuller text-only suggestion. Words between backticks are names: fixed width, never broken across lines. */
export interface TextSuggestion {
  intro: string[];
  warning: { title: string; text: string } | null;
  where: {
    title: string;
    note: string;
    columns: [string, string, string];
    rows: { place: string; setting: string; lead: string; code: string }[];
    after: string[];
  } | null;
  options: { title: string; items: { title: string; when: string; steps: string[]; note: string }[] } | null;
  exact: { title: string; note: string; blocks: { place: string; code: string }[] } | null;
}

export type FixSection =
  | { key: "change"; title: string; line: string; open: boolean; intro: string; parts: ChangePart[] }
  | {
      key: "proof";
      title: string;
      line: string;               // the one-line summary shown while folded
      open: boolean;
      intro: string;
      tables: ProofTable[];
      verdict: ProofVerdict | null;      // null while the proof runs
    }
  | { key: "details"; title: string; line: string; open: boolean; facts: DetailFact[]; note: string; ran_on: RanOn | null }
  | { key: "suggestion"; title: string; line: string; open: boolean; suggestion: TextSuggestion };

export interface ReviewerOption {
  id: string;                     // "you" | "a" | "b"
  name: string;                   // "You" | "Demo reviewer A"
  note: string | null;            // "(the person logged in)"
  demo: boolean;                  // true: the Demo data label follows the name
  checked: boolean;               // ticked by default
}

export interface ApprovalRowView {
  id: string;
  name: string;
  note: string | null;
  demo: boolean;
  approved_at: string | null;     // ISO time, or null while waiting
  approved_text: string | null;   // "Approved"
  approve_label: string | null;   // "Approve" | "Approve as Demo reviewer A"; null once approved or after the merge
  primary: boolean;               // the "You" row's button is the primary look
}

export interface FixApprovers {
  text: string | null;            // a plain sentence, when there is nothing to pick or approve
  options: ReviewerOption[] | null;      // the tick list (status "ready")
  rows: ApprovalRowView[] | null;        // once a pull request exists
  footnote: string | null;        // the one-login sentence
}

export type FixAction = "connect" | "run_proof_again" | "open_pull_request" | "merge" | "download_patch" | "retest_now";

export interface FixButton {
  action: FixAction;
  label: string;
  primary: boolean;
  enabled: boolean;
}

export interface FixDetail {
  id: string;                     // "fix-ecdsa-range-check" | "fix-tls-versions"
  kind: "code" | "text";
  title: string;
  list_source: string;            // in the list: "Came from 2 failed tests: Official test vectors, Bad signatures"
  source: RichText;               // in the summary: "Came from 2 failed tests on signing component acme-sign 1.4.2: ..."
  status: FixStatus;
  labels: string[];               // ["From a fix template"] for a code fix, [] for a text one
  is_demo: boolean;
  what: { label: string; paragraphs: RichText[]; server_line: string | null };
  proof: {
    state: "none" | "not_started" | "running" | "passed" | "failed";
    badge: { label: string; tone: Tone } | null;
    text: string;
    muted: string | null;         // "Not offered yet."
  };
  pull_request: { title: string; text: RichText } | null;
  approvers: FixApprovers;
  actions: { buttons: FixButton[]; note: string | null };
  patch: { url: string; filename: string } | null;
  merge_dialog: { title: string; paragraphs: RichText[]; confirm: string; cancel: string } | null;
  sections: FixSection[];
  sections_note: string | null;   // shown instead of sections before the code is connected
  /** Phase 4b: the change box, drawn first in the fix's detail. Missing in older answers: treated as null. */
  change_box?: ChangeView | null;
  /** Phase 4c: advisories for a text-only fix. Missing in older answers: treated as null. */
  advisories?: Advisories | null;
}

export interface FixesView {
  plan_id: number;
  is_demo: boolean;
  title: string;                  // "Fixes"
  subline: string;
  disclaimer: string;
  list_title: string;             // "Open findings with a fix (2)"
  empty_text: string | null;      // when no failed test has a fix: one plain sentence, and fixes is []
  fixes: FixDetail[];             // in list order; the list on the left is drawn from these too
  busy: boolean;                  // something is running: ask again in a second
}

// ---- Phase 4a: the Migration step. The screen draws only what is sent; it decides no status, recommendation or wording. ----

export type MigrationStatusCode = "hybrid" | "pq_only" | "classical" | "couldnt_check" | "not_measured";
/** Phase 4b: a track's status adds "post_quantum" (a post-quantum signature or certificate). */
export type TrackStatusCode = MigrationStatusCode | "post_quantum";
export type MigrationOptionKey = "keep" | "hybrid" | "full_pq" | "wrap";

/** The status pill. Its look is picked by code; the words are the label. */
export interface MigrationStatus {
  code: MigrationStatusCode;
  label: string;
}

/** A sentence that may be followed by "View in Fixes" (when fix_id is set). */
export interface MigrationLine {
  text: RichText;
  fix_id: string | null;
}

export interface MigrationSettingField {
  field: "lifespan" | "exposure" | "can_change";
  label: string;
  /** The small grey question under the control. */
  help: string;
  value: string;
  options: { value: string; label: string }[];
  /** "from the file" | "assumed" | "set by you": a small tag beside the control. */
  source: string;
  /** False while a measurement runs. */
  enabled: boolean;
}

export interface MigrationCostTable {
  title: string;
  intro: string;
  /** The first is the row label column. */
  columns: string[];
  /** One cell per column after the first. */
  rows: { label: string; cells: RichText[] }[];
  note: string | null;
}

export interface MigrationChooseBox {
  title: string;
  /** True: Save stays disabled until the reason has text. */
  needs_reason: boolean;
  reason_label: string;
  /** ISO dates (YYYY-MM-DD); only for "keep". */
  review_date: { label: string; value: string; min: string; max: string; help: string } | null;
  save: string;
  cancel: string;
  note: string;
}

export interface MigrationOption {
  key: MigrationOptionKey;
  title: string;
  tags: string[];
  /** The sky border (the recommended or chosen one). */
  highlighted: boolean;
  what: string;
  sections: { title: string; lines: MigrationLine[] }[];
  /** When set: no Choose button, this sentence instead. */
  not_offered: string | null;
  choose_label: string;
  /** The box that opens in the card when "Choose this option" is pressed. */
  choose: MigrationChooseBox | null;
}

export interface MigrationSystem {
  key: string;
  kind_label: string;
  name: string;
  status: MigrationStatus;
  plan_line: string;
  /** Set while this system's measurement waits or runs (drawn in place of Today's sentence). */
  measuring: RowStatus | null;
  today: {
    title: string;
    sentence: string;
    file_note: string | null;
    facts: { label: string; value: RichText }[];
    control_line: string | null;
    details_label: string;
    /** Drawn with ResultDetail inside a closed disclosure. */
    result: LabResult | null;
  };
  settings: { title: string; intro: string; fields: MigrationSettingField[] };
  cost: MigrationCostTable | null;
  recommendation: {
    title: string;
    tag: string | null;
    reasons: RichText[];
    evidence: RichText | null;
    /** "See the evidence": opens the details disclosure above and scrolls to it. */
    evidence_link: string | null;
    /** Shown instead of reasons when there is no recommendation. */
    none_text: string | null;
  };
  options_title: string;
  /** In the order keep, hybrid, full_pq, wrap. Empty when there is no status. */
  options: MigrationOption[];
  /** The user's saved choice (history: older choices, newest first). */
  choice: { line: string; history: string[] } | null;
  choices_note: string;

  // ---- Phase 4b. Older answers lack these: draw them as empty. ----
  tracks?: MigrationTrack[];
  tracks_brief?: { title: string; status: { code: TrackStatusCode; label: string } }[];
  target_line?: string;
  also_noticed_title?: string;
  also_noticed?: string[];
  change?: ChangeView | null;
}

export type TrackKey = "kex" | "auth" | "signatures";

export interface MigrationTrack {
  key: TrackKey;
  title: string;
  short_title: string;
  status: { code: TrackStatusCode; label: string };
  sentence: string;
  facts: { label: string; value: RichText }[];
  next: RichText;
  why: RichText;
  next_label: string;
  why_label: string;
}

// ---- Phase 4b: the change box (Migration and Fixes) ----

export type ChangeAction = "try" | "ask_approval" | "approve" | "apply" | "rollback" | "download";

export interface ChangeButton {
  action: ChangeAction;
  label: string;
  primary: boolean;
  enabled: boolean;
  reason: string | null;
}

export interface ChangeStep {
  key: "built" | "tried" | "approvals" | "applied" | "measured";
  label: string;
  state: "done" | "now" | "off" | "failed";
  text: string;
}

export type ChangeSection =
  | { kind: "table"; title: string; columns: string[]; rows: RichText[][] }
  | { kind: "lines"; title: string; rows: { place: string; lead: string; code: string }[]; note: string | null }
  | { kind: "text"; title: string; paragraphs: RichText[] };

export interface ChangeBadge {
  label: string;
  look: "pass" | "fail" | "warn" | "neutral";
}

export interface TryView {
  title: string;
  running: RowStatus | null;
  verdict: { label: string; look: "pass" | "fail" | "warn"; text: string } | null;
  columns: string[];
  rows: { label: string; cells: RichText[] }[];
  notes: string[];
  results: { label: string; result: LabResult }[];
}

export interface ApprovalsView {
  title: string;
  picker: {
    options: { id: string; name: string; demo: boolean; checked: boolean }[];
    button: string;
    enabled: boolean;
    reason: string | null;
  } | null;
  rows: {
    reviewer: string;
    name: string;
    demo: boolean;
    approved_at: string | null;
    status_text: string;
    approve: { label: string; enabled: boolean } | null;
  }[];
  footnote: string;
}

export interface ApplyView {
  title: string;
  badge: ChangeBadge;
  paragraphs: RichText[];
  differences: string[];
  history: string[];
}

export interface ChangeView {
  /** The key to send back, e.g. "migration:server:localhost:8452". */
  id: string;
  title: string;
  badge: ChangeBadge;
  intro: RichText;
  steps: ChangeStep[];
  sections: ChangeSection[];
  try: TryView | null;
  approvals: ApprovalsView | null;
  applied: ApplyView | null;
  buttons: ChangeButton[];
  note: string | null;
  busy: boolean;
}

export interface MigrationRoadmapRow {
  system_key: string;
  kind_label: string;
  name: string;
  option: string;
  plan_tag: string | null;
  note: MigrationLine;
  /** Phase 4b: "Key exchange" | "Authentication" | "Signatures" | "Both tracks". */
  track?: string;
}

export interface MigrationRoadmapBand {
  key: string;
  title: string;
  sub: string;
  look: "plain" | "highlight" | "dashed";
  rows: MigrationRoadmapRow[];
}

export interface MigrationView {
  plan_id: number;
  import_id: number;
  is_demo: boolean;
  title: string;
  subline: RichText;
  disclaimer: string;
  /** True while measuring: ask again every second. */
  busy: boolean;
  measure: { label: string; enabled: boolean; blocked_reason: string | null; progress_text: string | null };
  tabs: { systems: string; roadmap: string };
  list_title: string;
  /** Set when the file names no server and no signing program. */
  empty_text: string | null;
  systems: MigrationSystem[];
  roadmap: {
    intro: string;
    /** The same evidence download as Evidence Lab's button. */
    download: { label: string; can_start: boolean; blocked_reason: string | null };
    /** Empty bands are not sent. */
    bands: MigrationRoadmapBand[];
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly line: number | null;
  readonly field: string | null;

  constructor(status: number, message: string, line: number | null = null, field: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.line = line;
    this.field = field;
  }
}

let onUnauthorized: (() => void) | null = null;

/** The app registers this so it can show the login screen when the session ends. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function toApiError(status: number, body: unknown): ApiError {
  if (isRecord(body)) {
    const err = body["error"];
    if (isRecord(err) && typeof err["message"] === "string") {
      return new ApiError(
        status,
        err["message"],
        typeof err["line"] === "number" ? err["line"] : null,
        typeof err["field"] === "string" ? err["field"] : null,
      );
    }
    if (typeof body["detail"] === "string") {
      // A form's refusal can name its field too: {detail, field}.
      return new ApiError(status, body["detail"], null, typeof body["field"] === "string" ? body["field"] : null);
    }
  }
  return new ApiError(status, `Something went wrong (the server answered ${status}).`);
}

interface RequestOptions {
  method?: "GET" | "POST";
  json?: unknown;
  raw?: Blob;
  /** Don't treat 401 as "session ended" (used by the login call itself). */
  quiet401?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const init: RequestInit = { method: options.method ?? "GET", credentials: "same-origin" };
  if (options.json !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.json);
  } else if (options.raw !== undefined) {
    init.headers = { "Content-Type": "application/octet-stream" };
    init.body = options.raw;
  }

  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Can't reach the app. Check that it is still running, then try again.");
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    if (response.status === 401 && !options.quiet401 && onUnauthorized) {
      onUnauthorized();
    }
    throw toApiError(response.status, body);
  }
  return body as T;
}

async function orNullOn404<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export const MAX_UPLOAD_BYTES = 1024 * 1024;

function fixPath(planId: number, fixId: string): string {
  return `/api/plans/${planId}/fixes/${encodeURIComponent(fixId)}`;
}

export const api = {
  getSession: () => request<Session>("/api/session"),

  setup: (password: string) =>
    request<{ ok: true }>("/api/setup", { method: "POST", json: { password }, quiet401: true }),

  login: (password: string) =>
    request<{ ok: true }>("/api/login", { method: "POST", json: { password }, quiet401: true }),

  importDemo: () => request<Import>("/api/import/demo", { method: "POST" }),

  /** Sends the file's raw bytes. The server only reads it as data. */
  importFile: (file: File) =>
    request<Import>(`/api/import/file?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      raw: file,
    }),

  getCurrentImport: () => orNullOn404(request<Import>("/api/import/current")),

  confirmAddress: (importId: number, address: string, confirmed: boolean) =>
    request<Address>(`/api/import/${importId}/confirm-address`, {
      method: "POST",
      json: { address, confirmed },
    }),

  verify: (importId: number) => request<VerifyRun>(`/api/import/${importId}/verify`, { method: "POST" }),

  getLatestVerify: (importId: number) => orNullOn404(request<VerifyRun>(`/api/import/${importId}/verify`)),

  // The test plan. Every call answers with the whole plan as it now stands.
  getPlan: (importId: number) => orNullOn404(request<PlanView>(`/api/import/${importId}/plan`)),

  ensurePlan: (importId: number) => request<PlanView>(`/api/import/${importId}/plan`, { method: "POST" }),

  pollPlan: (planId: number) => request<PlanView>(`/api/plans/${planId}`),

  reorder: (planId: number, order: number[]) =>
    request<PlanView>(`/api/plans/${planId}/order`, { method: "POST", json: { order } }),

  addTest: (planId: number, catalogId: TestKind) =>
    request<PlanView>(`/api/plans/${planId}/tests`, { method: "POST", json: { catalog_id: catalogId } }),

  removeTest: (planId: number, itemId: number) =>
    request<PlanView>(`/api/plans/${planId}/tests/${itemId}/remove`, { method: "POST" }),

  runTest: (planId: number, itemId: number) =>
    request<PlanView>(`/api/plans/${planId}/tests/${itemId}/run`, { method: "POST" }),

  runAll: (planId: number) => request<PlanView>(`/api/plans/${planId}/run-all`, { method: "POST" }),

  // Evidence Lab. Results are only ever read from here; nothing in the screens sets one.
  getLab: (planId: number) => request<LabView>(`/api/plans/${planId}/lab`),

  markReviewed: (runId: number) => request<LabView>(`/api/runs/${runId}/mark-reviewed`, { method: "POST" }),

  digDeeper: (runId: number) => request<LabView>(`/api/runs/${runId}/dig-deeper`, { method: "POST" }),

  /** The version is one of the demo versions the backend listed. No software is sent. */
  retest: (planId: number, version: string, component?: string) =>
    request<LabView>(`/api/plans/${planId}/retest`, {
      method: "POST",
      json: component !== undefined ? { version, component } : { version },
    }),

  exportEvidence: (planId: number) => request<EvidenceExport>(`/api/plans/${planId}/evidence`, { method: "POST" }),

  // The Fixes step. Every call answers with the whole view as it now stands. Nothing here sends code.
  getFixes: (planId: number) => request<FixesView>(`/api/plans/${planId}/fixes`),

  connectCode: (planId: number) => request<FixesView>(`/api/plans/${planId}/fixes/connect`, { method: "POST" }),

  runProofAgain: (planId: number, fixId: string) =>
    request<FixesView>(`${fixPath(planId, fixId)}/proof`, { method: "POST" }),

  openPullRequest: (planId: number, fixId: string, reviewers: string[]) =>
    request<FixesView>(`${fixPath(planId, fixId)}/pull-request`, { method: "POST", json: { reviewers } }),

  approve: (planId: number, fixId: string, reviewer: string) =>
    request<FixesView>(`${fixPath(planId, fixId)}/approve`, { method: "POST", json: { reviewer } }),

  /** Only the "Confirm merge" button calls this. */
  mergePullRequest: (planId: number, fixId: string) =>
    request<FixesView>(`${fixPath(planId, fixId)}/merge`, { method: "POST" }),

  /** The same retest as "Retest new version", on the merged version. Answers with the Evidence Lab view. */
  retestNow: (planId: number, fixId: string) =>
    request<LabView>(`${fixPath(planId, fixId)}/retest`, { method: "POST" }),

  // The Migration step. Every call answers with the whole view as it now stands. The GET makes the test plan if there is none.
  getMigration: (importId: number) => request<MigrationView>(`/api/import/${importId}/migration`),

  measureMigration: (planId: number) =>
    request<MigrationView>(`/api/plans/${planId}/migration/measure`, { method: "POST", json: {} }),

  saveMigrationSetting: (planId: number, system: string, field: MigrationSettingField["field"], value: string) =>
    request<MigrationView>(`/api/plans/${planId}/migration/settings`, { method: "POST", json: { system, field, value } }),

  /** Only "Save choice" calls this. */
  saveMigrationChoice: (
    planId: number,
    system: string,
    option: MigrationOptionKey,
    reason: string,
    reviewDate: string | null,
  ) =>
    request<MigrationView>(`/api/plans/${planId}/migration/choice`, {
      method: "POST",
      json: { system, option, reason, review_date: reviewDate },
    }),

  // Phase 4b: the change box. Each POST answers { ok: true }; the screen then loads its own view again.
  changeTry: (planId: number, change: string) =>
    request<{ ok: true }>(`/api/plans/${planId}/changes/try`, { method: "POST", json: { change } }),

  changeAskApproval: (planId: number, change: string, reviewers: string[]) =>
    request<{ ok: true }>(`/api/plans/${planId}/changes/ask-approval`, { method: "POST", json: { change, reviewers } }),

  changeApprove: (planId: number, change: string, reviewer: string) =>
    request<{ ok: true }>(`/api/plans/${planId}/changes/approve`, { method: "POST", json: { change, reviewer } }),

  changeApply: (planId: number, change: string) =>
    request<{ ok: true }>(`/api/plans/${planId}/changes/apply`, { method: "POST", json: { change } }),

  changeRollback: (planId: number, change: string) =>
    request<{ ok: true }>(`/api/plans/${planId}/changes/rollback`, { method: "POST", json: { change } }),

  /** The address of the change file; the page saves it like the evidence files. */
  changeDownloadUrl: (planId: number, change: string) =>
    `/api/plans/${planId}/changes/download?change=${encodeURIComponent(change)}`,
};

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong.";
}
