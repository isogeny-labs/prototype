// GENERATED from the backend's API description (src/api-schema.json). Do not edit by hand.
// The shapes live in backend/app/web/models.py; see scripts/gen-api-types.mjs for how to remake this file.

export type ClaimKind =
  "protocol_versions" | "cipher_suites" | "key_exchange" | "certificate" | "signature_algorithm" | "post_quantum";
export type LocationKind = "server" | "software" | "unknown";
export type ResultValue = "True" | "False" | "Couldn't check";
export type Mode = "demo" | "isolated";
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
export type RichText = RichPart[];
export type EvidenceBlock = EvidenceBlockTable | EvidenceBlockText;
export type FixStatusKey =
  "not_connected" | "proving" | "ready" | "failed" | "waiting" | "ready_to_merge" | "merged" | "text_only";
export type FixSection = FixSectionChange | FixSectionProof | FixSectionDetails | FixSectionSuggestion;
export type FixAction = "connect" | "run_proof_again" | "open_pull_request" | "merge" | "download_patch" | "retest_now";
export type MigrationStatusCode = "hybrid" | "pq_only" | "classical" | "couldnt_check" | "not_measured";
export type TrackStatusCode = "hybrid" | "pq_only" | "classical" | "couldnt_check" | "not_measured" | "post_quantum";
export type MigrationOptionKey = "keep" | "hybrid" | "full_pq" | "wrap";
export type TrackKey = "kex" | "auth" | "signatures";
export type ChangeAction = "try" | "ask_approval" | "approve" | "apply" | "rollback" | "download";
export type ChangeSection = ChangeSectionTable | ChangeSectionLines | ChangeSectionText;

export interface AddTestBody {
  catalog_id: string;
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
/**
 * Published advisories for the tested version. Information from the advisory, never a result.
 */
export interface Advisories {
  title: string;
  tag: string;
  items: AdvisoriesItem[];
}
export interface AdvisoriesItem {
  id: string;
  text: string;
  link: string;
  href: string;
  covered: string;
}
export interface ApplyView {
  title: string;
  badge: ChangeBadge;
  paragraphs: RichPart[][];
  differences: string[];
  history: string[];
}
export interface ChangeBadge {
  label: string;
  look: "pass" | "fail" | "warn" | "neutral";
}
export interface RichPart {
  t: "text" | "mono" | "tag" | "time" | "demo";
  v: string;
}
export interface ApprovalRowView {
  id: string;
  name: string;
  note: string | null;
  demo: boolean;
  /**
   * ISO time, or null while waiting
   */
  approved_at: string | null;
  /**
   * "Approved"
   */
  approved_text: string | null;
  /**
   * "Approve" | "Approve as Demo reviewer A"; null once approved or after the merge
   */
  approve_label: string | null;
  /**
   * the "You" row's button is the primary look
   */
  primary: boolean;
}
export interface ApprovalsPicker {
  options: ApprovalsPickerOption[];
  button: string;
  enabled: boolean;
  reason: string | null;
}
export interface ApprovalsPickerOption {
  id: string;
  name: string;
  demo: boolean;
  checked: boolean;
}
export interface ApprovalsRow {
  reviewer: string;
  name: string;
  demo: boolean;
  approved_at: string | null;
  status_text: string;
  approve: ApprovalsRowApprove | null;
}
export interface ApprovalsRowApprove {
  label: string;
  enabled: boolean;
}
export interface ApprovalsView {
  title: string;
  picker: ApprovalsPicker | null;
  rows: ApprovalsRow[];
  footnote: string;
}
export interface ApproveBody {
  reviewer: string;
}
export interface ApproveChangeBody {
  change: string;
  reviewer: string;
}
export interface AskApprovalBody {
  change: string;
  /**
   * @maxItems 8
   */
  reviewers:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string];
}
export interface Badge {
  code:
    | "passed"
    | "failed"
    | "couldnt_run"
    | "couldnt_trust"
    | "measured"
    | "no_slowdown"
    | "slowdown"
    | "offered"
    | "not_offered";
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
}
export interface CatalogItem {
  catalog_id:
    | "tls_versions"
    | "certificate"
    | "official_vectors"
    | "bad_signatures"
    | "speed_size"
    | "pq_readiness"
    | "mldsa_compare";
  title: string;
  tag: string | null;
  description: string;
}
export interface ChangeBody {
  change: string;
}
export interface ChangeButton {
  action: "try" | "ask_approval" | "approve" | "apply" | "rollback" | "download";
  label: string;
  primary: boolean;
  enabled: boolean;
  reason: string | null;
}
export interface ChangePart {
  /**
   * "1. The check: reject a signature whose numbers are out of range"
   */
  title: string;
  why: string;
  before_label: StrongLabel;
  before: DiffLine[];
  after_label: StrongLabel;
  after: DiffLine[];
}
/**
 * "Before: " + strong + rest, e.g. lead "Before:", strong "acme-sign 1.4.2", rest ", nothing removed here".
 */
export interface StrongLabel {
  lead: string;
  strong: string;
  rest: string;
}
/**
 * One line of code in a before or after block. n is the line number in that version of the file.
 */
export interface DiffLine {
  n: number;
  mark: " " | "-" | "+";
  text: string;
}
export interface ChangeSectionLine {
  place: string;
  lead: string;
  code: string;
}
export interface ChangeSectionLines {
  kind: "lines";
  title: string;
  rows: ChangeSectionLine[];
  note: string | null;
}
export interface ChangeSectionTable {
  kind: "table";
  title: string;
  columns: string[];
  rows: RichPart[][][];
}
export interface ChangeSectionText {
  kind: "text";
  title: string;
  paragraphs: RichPart[][];
}
export interface ChangeStep {
  key: "built" | "tried" | "approvals" | "applied" | "measured";
  label: string;
  state: "done" | "now" | "off" | "failed";
  text: string;
}
export interface ChangeView {
  /**
   * The key to send back, e.g. "migration:server:localhost:8452".
   */
  id: string;
  title: string;
  badge: ChangeBadge;
  intro: RichPart[];
  steps: ChangeStep[];
  sections: (ChangeSectionTable | ChangeSectionLines | ChangeSectionText)[];
  try: TryView | null;
  approvals: ApprovalsView | null;
  applied: ApplyView | null;
  buttons: ChangeButton[];
  note: string | null;
  busy: boolean;
}
export interface TryView {
  title: string;
  running: RowStatus | null;
  verdict: TryViewVerdict | null;
  columns: string[];
  rows: TryViewRow[];
  notes: string[];
  results: TryViewResult[];
}
export interface RowStatus {
  status: "not_run" | "waiting" | "running" | "done";
  status_text: string;
  progress: Progress | null;
}
export interface Progress {
  text: string;
  percent: number | null;
}
export interface TryViewVerdict {
  label: string;
  look: "pass" | "fail" | "warn";
  text: string;
}
export interface TryViewRow {
  label: string;
  cells: RichPart[][];
}
export interface TryViewResult {
  label: string;
  result: MeasurementResult;
}
/**
 * A result as the Migration step and a change box's try show it: the same as a test's result, but its code can
 * also be a measured post-quantum status (found by the phase 4c+ check of every answer against its shape).
 */
export interface MeasurementResult {
  code:
    | (
        | "passed"
        | "failed"
        | "couldnt_run"
        | "couldnt_trust"
        | "measured"
        | "no_slowdown"
        | "slowdown"
        | "offered"
        | "not_offered"
      )
    | ("hybrid" | "pq_only" | "classical" | "post_quantum");
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  run_id: number;
  component: string | null;
  mode: "demo" | "isolated";
  finished_at: string;
  duration_ms: number;
  summary: string;
  short: string;
  /**
   * One plain sentence: what was found and why that gives this result.
   */
  plain: string;
  /**
   * Side notes about things the test saw that it wasn't asked about. Never a result.
   */
  also_noticed: string[];
  also_noticed_title: string;
  control: LabResultControl;
  what_happened: string[];
  shows_title: string;
  shows: string[];
  evidence: (EvidenceBlockTable | EvidenceBlockText)[];
  run_record: RunRecordView;
  locked_test: LockedTestView;
  /**
   * True when the component is a real library, not one of our demo components (phase 4c).
   */
  real: boolean;
  fix_title: string;
  suggested_fix: string | null;
  /**
   * Not sent here: a measurement has no fix line.
   */
  fix_line?: FixLine | null;
  reviewed: LabResultReviewed | null;
  research: ResearchView | null;
  /**
   * Phase 4c: advisories for this version (null for our own demo code).
   */
  advisories: Advisories | null;
}
export interface LabResultControl {
  outcome: "as_expected" | "not_as_expected" | "errored" | "not_run";
  line: string;
  text: string;
}
export interface EvidenceBlockTable {
  type: "table";
  title: string;
  tag: string | null;
  columns: TableColumn[];
  rows: string[][];
  meta: MetaItem[];
  note: string | null;
}
export interface TableColumn {
  label: string;
  align: "left" | "right";
  mono?: boolean;
}
export interface MetaItem {
  label: string | null;
  value: string;
  tag: string | null;
  time?: string;
  href?: string;
}
export interface EvidenceBlockText {
  type: "text";
  title: string;
  tag: string | null;
  text: string;
}
export interface RunRecordView {
  title: string;
  command: string;
  outputs: RunRecordOutput[];
  meta: MetaItem[];
}
export interface RunRecordOutput {
  title: string;
  text: string;
}
export interface LockedTestView {
  title: string;
  fields: LockedTestField[];
  locked_at: string;
  locked_text: string;
  fingerprint_label: string;
  fingerprint: string;
  note: string;
}
export interface LockedTestField {
  label: string;
  lines: string[];
}
/**
 * The one line on a failed result that has a fix in the Fixes step.
 */
export interface FixLine {
  /**
   * which fix "View in Fixes" opens
   */
  fix_id: string;
  /**
   * "Fix ready:"            (drawn bold)
   */
  lead: string;
  /**
   * "3 lines added and 1 removed, proof passed"
   */
  rest: string;
  look: "plain" | "pass" | "fail" | "dashed";
  /**
   * true while the proof runs: a small spinner before the words
   */
  busy: boolean;
  /**
   * "View in Fixes"
   */
  button: string;
}
export interface LabResultReviewed {
  at: string;
  text: string;
}
export interface ResearchView {
  id: number;
  title: string;
  badge: string;
  status: string;
  status_line: string;
  fields: ResearchField[];
  saved_at: string;
  note: string;
}
export interface ResearchField {
  label: string;
  value: string;
}
export interface Claim {
  id: number;
  ref: string;
  location: string;
  location_kind: "server" | "software" | "unknown";
  kind: "protocol_versions" | "cipher_suites" | "key_exchange" | "certificate" | "signature_algorithm" | "post_quantum";
  claimed_value: string;
  text: string;
  source: string;
}
export interface ConfirmBody {
  address: string;
  confirmed: boolean;
}
export interface DemoServer {
  address: string;
  running: boolean;
  error: string | null;
}
export interface DetailFact {
  label: string;
  value: RichPart[];
  /**
   * true: draw the value small, fixed-width, breaking anywhere
   */
  fingerprint: boolean;
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
export interface EvidenceExport {
  id: number;
  created_at: string;
  fingerprint: string;
  fingerprint_label: string;
  json: FileLink;
  html: FileLink;
  message: string;
  verify_hint: string;
}
export interface FileLink {
  url: string;
  filename: string;
}
export interface FixApprovers {
  /**
   * a plain sentence, when there is nothing to pick or approve
   */
  text: string | null;
  /**
   * the tick list (status "ready")
   */
  options: ReviewerOption[] | null;
  /**
   * once a pull request exists
   */
  rows: ApprovalRowView[] | null;
  /**
   * the one-login sentence
   */
  footnote: string | null;
}
export interface ReviewerOption {
  /**
   * "you" | "a" | "b"
   */
  id: string;
  /**
   * "You" | "Demo reviewer A"
   */
  name: string;
  /**
   * "(the person logged in)"
   */
  note: string | null;
  /**
   * true: the Demo data label follows the name
   */
  demo: boolean;
  /**
   * ticked by default
   */
  checked: boolean;
}
export interface FixButton {
  action: "connect" | "run_proof_again" | "open_pull_request" | "merge" | "download_patch" | "retest_now";
  label: string;
  primary: boolean;
  enabled: boolean;
}
export interface FixDetail {
  /**
   * "fix-ecdsa-range-check" | "fix-tls-versions"
   */
  id: string;
  kind: "code" | "text";
  title: string;
  /**
   * in the list: "Came from 2 failed tests: Official test vectors, Bad signatures"
   */
  list_source: string;
  /**
   * in the summary: "Came from 2 failed tests on signing component acme-sign 1.4.2: ..."
   */
  source: RichPart[];
  status: FixStatus;
  /**
   * ["From a fix template"] for a code fix, [] for a text one
   */
  labels: string[];
  is_demo: boolean;
  what: FixDetailWhat;
  proof: FixDetailProof;
  pull_request: FixDetailPullRequest | null;
  approvers: FixApprovers;
  actions: FixDetailActions;
  patch: FileLink | null;
  merge_dialog: FixDetailMergeDialog | null;
  sections: (FixSectionChange | FixSectionProof | FixSectionDetails | FixSectionSuggestion)[];
  /**
   * shown instead of sections before the code is connected
   */
  sections_note: string | null;
  /**
   * Phase 4b: the change box, drawn first in the fix's detail.
   */
  change_box: ChangeView | null;
  /**
   * Phase 4c: advisories for a text-only fix on a real library.
   */
  advisories: Advisories | null;
}
export interface FixStatus {
  key: "not_connected" | "proving" | "ready" | "failed" | "waiting" | "ready_to_merge" | "merged" | "text_only";
  /**
   * "Ready for review"
   */
  word: string;
  /**
   * true while proving: the chip shows a spinner
   */
  busy: boolean;
}
export interface FixDetailWhat {
  label: string;
  paragraphs: RichPart[][];
  server_line: string | null;
}
export interface FixDetailProof {
  state: "none" | "not_started" | "running" | "passed" | "failed";
  badge: FixDetailProofBadge | null;
  text: string;
  /**
   * "Not offered yet."
   */
  muted: string | null;
}
export interface FixDetailProofBadge {
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
}
export interface FixDetailPullRequest {
  title: string;
  text: RichPart[];
}
export interface FixDetailActions {
  buttons: FixButton[];
  note: string | null;
}
export interface FixDetailMergeDialog {
  title: string;
  paragraphs: RichPart[][];
  confirm: string;
  cancel: string;
}
export interface FixSectionChange {
  key: "change";
  title: string;
  line: string;
  open: boolean;
  intro: string;
  parts: ChangePart[];
}
export interface FixSectionProof {
  key: "proof";
  title: string;
  /**
   * the one-line summary shown while folded
   */
  line: string;
  open: boolean;
  intro: string;
  tables: ProofTable[];
  /**
   * null while the proof runs
   */
  verdict: ProofVerdict | null;
}
export interface ProofTable {
  /**
   * "Tests that run the changed code"
   */
  heading: string;
  /**
   * "measured"
   */
  tag: string;
  need: string;
  /**
   * "Test", "Before: acme-sign 1.4.2", "On the changed code", "Rule check"
   *
   * @minItems 4
   * @maxItems 4
   */
  columns: [string, string, string, string];
  rows: ProofRow[];
}
export interface ProofRow {
  kind:
    | "tls_versions"
    | "certificate"
    | "official_vectors"
    | "bad_signatures"
    | "speed_size"
    | "pq_readiness"
    | "mldsa_compare";
  title: string;
  /**
   * the first result this is compared with
   */
  before: ProofCell | null;
  /**
   * null while this test has no proof result yet
   */
  proof: ProofCell | null;
  /**
   * set while it is waiting or running
   */
  waiting: ProofWaiting | null;
  /**
   * the control line under the proof cell
   */
  control: string;
  check: ProofRowCheck;
}
/**
 * A result badge and one line under it, as in Evidence Lab's before/after cells.
 */
export interface ProofCell {
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  short: string;
}
export interface ProofWaiting {
  /**
   * "Running" or "Waiting"
   */
  text: string;
  /**
   * "212 of 484 cases"
   */
  detail: string | null;
  percent: number | null;
}
/**
 * "Passed", "No slowdown", "Same as before", "Did not pass", "Not finished yet"
 */
export interface ProofRowCheck {
  ok: boolean | null;
  text: string;
}
export interface ProofVerdict {
  tone: "pass" | "fail";
  /**
   * "Why it is ready for review" | "Why this change is not offered"
   */
  title: string;
  checks: ProofVerdictCheck[];
  /**
   * "What this proof shows, and what it doesn't"
   */
  shows_title: string | null;
  shows: string[];
}
export interface ProofVerdictCheck {
  ok: boolean;
  text: string;
}
export interface FixSectionDetails {
  key: "details";
  title: string;
  line: string;
  open: boolean;
  facts: DetailFact[];
  note: string;
  ran_on: RanOn | null;
}
export interface RanOn {
  /**
   * "What the tests ran on"
   */
  title: string;
  text: RichPart[];
  fingerprints: RanOnFingerprint[];
  note: string;
}
export interface RanOnFingerprint {
  label: string;
  value: string;
  tag: string;
}
export interface FixSectionSuggestion {
  key: "suggestion";
  title: string;
  line: string;
  open: boolean;
  suggestion: TextSuggestion;
}
/**
 * The fuller text-only suggestion. Words between backticks are names: fixed width, never broken across lines.
 */
export interface TextSuggestion {
  intro: string[];
  warning: TextSuggestionWarning | null;
  where: TextSuggestionWhere | null;
  options: TextSuggestionOptions | null;
  exact: TextSuggestionExact | null;
}
export interface TextSuggestionWarning {
  title: string;
  text: string;
}
export interface TextSuggestionWhere {
  title: string;
  note: string;
  /**
   * @minItems 3
   * @maxItems 3
   */
  columns: [string, string, string];
  rows: TextSuggestionWhereRow[];
  after: string[];
}
export interface TextSuggestionWhereRow {
  place: string;
  setting: string;
  lead: string;
  code: string;
}
export interface TextSuggestionOptions {
  title: string;
  items: TextSuggestionOption[];
}
export interface TextSuggestionOption {
  title: string;
  when: string;
  steps: string[];
  note: string;
}
export interface TextSuggestionExact {
  title: string;
  note: string;
  blocks: TextSuggestionBlock[];
}
export interface TextSuggestionBlock {
  place: string;
  code: string;
}
export interface FixesView {
  plan_id: number;
  is_demo: boolean;
  /**
   * "Fixes"
   */
  title: string;
  subline: string;
  disclaimer: string;
  /**
   * "Open findings with a fix (2)"
   */
  list_title: string;
  /**
   * when no failed test has a fix: one plain sentence, and fixes is []
   */
  empty_text: string | null;
  /**
   * in list order; the list on the left is drawn from these too
   */
  fixes: FixDetail[];
  /**
   * something is running: ask again in a second
   */
  busy: boolean;
}
export interface Import {
  id: number;
  filename: string;
  format: "cyclonedx-cbom" | "csv";
  is_demo: boolean;
  claims: Claim[];
  addresses: Address[];
  /**
   * Always sent by the current backend; optional so an older reply doesn't break the screen.
   */
  skipped?: SkippedItem[];
  /**
   * Plain sentences about what the upload started on this computer (for example the demo test servers). Only on the upload reply.
   */
  notices?: string[];
  /**
   * The heading of the settings list, e.g. "System settings from the file".
   */
  settings_title?: string;
  /**
   * Settings rows the file carries (not claims: nothing checks them). Optional: older stored answers may lack it.
   */
  settings?: ImportSetting[];
}
/**
 * Something in the file that this version doesn't check (for example a hash algorithm).
 */
export interface SkippedItem {
  name: string;
  what: string;
  source: string;
  reason: string;
}
/**
 * One settings row from the file, e.g. location "localhost:8451", text "Exposure: internet-facing. Data lifespan: long-lived."
 */
export interface ImportSetting {
  location: string;
  text: string;
}
export interface LabResult {
  code:
    | "passed"
    | "failed"
    | "couldnt_run"
    | "couldnt_trust"
    | "measured"
    | "no_slowdown"
    | "slowdown"
    | "offered"
    | "not_offered";
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  run_id: number;
  component: string | null;
  mode: "demo" | "isolated";
  finished_at: string;
  duration_ms: number;
  summary: string;
  short: string;
  /**
   * One plain sentence: what was found and why that gives this result.
   */
  plain: string;
  /**
   * Side notes about things the test saw that it wasn't asked about. Never a result.
   */
  also_noticed: string[];
  also_noticed_title: string;
  control: LabResultControl;
  what_happened: string[];
  shows_title: string;
  shows: string[];
  evidence: (EvidenceBlockTable | EvidenceBlockText)[];
  run_record: RunRecordView;
  locked_test: LockedTestView;
  /**
   * True when the component is a real library, not one of our demo components (phase 4c).
   */
  real: boolean;
  fix_title: string;
  suggested_fix: string | null;
  /**
   * When set, suggested_fix is null and the "Suggested fix" box is not drawn.
   */
  fix_line: FixLine | null;
  reviewed: LabResultReviewed | null;
  research: ResearchView | null;
  /**
   * Phase 4c: advisories for this version (null for our own demo code).
   */
  advisories: Advisories | null;
}
export interface LabRow {
  item_id: number;
  kind:
    | "tls_versions"
    | "certificate"
    | "official_vectors"
    | "bad_signatures"
    | "speed_size"
    | "pq_readiness"
    | "mldsa_compare";
  title: string;
  control_line: string;
  result: LabResult | null;
  result_status: RowStatus | null;
  after: LabResult | null;
  after_status: RowStatus | null;
  group: string | null;
}
export interface LabView {
  plan_id: number;
  is_demo: boolean;
  view: "results" | "before_after";
  subline: RichPart[];
  /**
   * "Code they ran on: before, ...; after, ..." (before/after view only).
   */
  code_line: RichPart[] | null;
  disclaimer: string;
  columns: LabViewColumns | null;
  grouped: boolean;
  groups: PlanGroup[];
  not_tested: NotTested | null;
  /**
   * When grouped, already ordered group by group, in the order of `groups`.
   */
  rows: LabRow[];
  retest: LabViewRetest;
  download: LabViewDownload;
  /**
   * Something is running for this file (tests, a retest or a proof in Fixes): ask again in a second.
   */
  busy: boolean;
}
export interface LabViewColumns {
  test: string;
  before: string;
  after: string;
  /**
   * The second line under each heading: which code that side ran on.
   */
  before_note: RichPart[];
  after_note: RichPart[];
  /**
   * The headings of the opened details.
   */
  before_heading: string;
  after_heading: string;
}
/**
 * A heading the cards (or Evidence Lab rows) are grouped under, e.g. "Server: localhost:8444".
 */
export interface PlanGroup {
  key: string;
  kind: "server" | "software" | "reference";
  heading: string;
  note: string | null;
}
/**
 * The "Not tested, and why" box: every target or test the plan leaves out, one line each.
 */
export interface NotTested {
  title: string;
  items: string[];
}
export interface LabViewRetest {
  can_start: boolean;
  blocked_reason: string | null;
  running: boolean;
  progress_text: string | null;
  menu_title: string;
  versions: RetestVersion[];
  menu_note: string;
}
export interface RetestVersion {
  version: string;
  /**
   * Which library this version belongs to (phase 4c).
   */
  component: string;
  label: string;
  tag: string;
  note: string;
}
export interface LabViewDownload {
  can_start: boolean;
  blocked_reason: string | null;
}
export interface LabeledRichValue {
  label: string;
  value: RichPart[];
}
export interface MigrationChoiceBody {
  system: string;
  option: string;
  reason?: string;
  review_date?: string | null;
}
export interface MigrationChooseBox {
  title: string;
  /**
   * True: Save stays disabled until the reason has text.
   */
  needs_reason: boolean;
  reason_label: string;
  /**
   * ISO dates (YYYY-MM-DD); only for "keep".
   */
  review_date: MigrationReviewDate | null;
  save: string;
  cancel: string;
  note: string;
}
export interface MigrationReviewDate {
  label: string;
  value: string;
  min: string;
  max: string;
  help: string;
}
export interface MigrationCostRow {
  label: string;
  cells: RichPart[][];
}
export interface MigrationCostTable {
  title: string;
  intro: string;
  /**
   * The first is the row label column.
   */
  columns: string[];
  /**
   * One cell per column after the first.
   */
  rows: MigrationCostRow[];
  note: string | null;
}
/**
 * A sentence that may be followed by "View in Fixes" (when fix_id is set).
 */
export interface MigrationLine {
  text: RichPart[];
  fix_id: string | null;
}
export interface MigrationMeasure {
  label: string;
  enabled: boolean;
  blocked_reason: string | null;
  progress_text: string | null;
}
export interface MigrationOption {
  key: "keep" | "hybrid" | "full_pq" | "wrap";
  title: string;
  tags: string[];
  /**
   * The sky border (the recommended or chosen one).
   */
  highlighted: boolean;
  what: string;
  sections: MigrationOptionSection[];
  /**
   * When set: no Choose button, this sentence instead.
   */
  not_offered: string | null;
  choose_label: string;
  /**
   * The box that opens in the card when "Choose this option" is pressed.
   */
  choose: MigrationChooseBox | null;
}
export interface MigrationOptionSection {
  title: string;
  lines: MigrationLine[];
}
export interface MigrationRoadmap {
  intro: string;
  download: MigrationRoadmapDownload;
  /**
   * Empty bands are not sent.
   */
  bands: MigrationRoadmapBand[];
}
/**
 * The same evidence download as Evidence Lab's button.
 */
export interface MigrationRoadmapDownload {
  label: string;
  can_start: boolean;
  blocked_reason: string | null;
}
export interface MigrationRoadmapBand {
  key: string;
  title: string;
  sub: string;
  look: "plain" | "highlight" | "dashed";
  rows: MigrationRoadmapRow[];
}
export interface MigrationRoadmapRow {
  system_key: string;
  kind_label: string;
  name: string;
  option: string;
  plan_tag: string | null;
  note: MigrationLine;
  /**
   * Phase 4b: "Key exchange" | "Authentication" | "Signatures" | "Both tracks".
   */
  track?: string;
}
export interface MigrationRoadmapDownload1 {
  label: string;
  can_start: boolean;
  blocked_reason: string | null;
}
export interface MigrationSettingBody {
  system: string;
  field: string;
  value: string;
}
export interface MigrationSettingField {
  field: "lifespan" | "exposure" | "can_change";
  label: string;
  /**
   * The small grey question under the control.
   */
  help: string;
  value: string;
  options: MigrationSettingOption[];
  /**
   * "from the file" | "assumed" | "set by you": a small tag beside the control.
   */
  source: string;
  /**
   * False while a measurement runs.
   */
  enabled: boolean;
}
export interface MigrationSettingOption {
  value: string;
  label: string;
}
/**
 * The status pill. Its look is picked by code; the words are the label.
 */
export interface MigrationStatus {
  code: "hybrid" | "pq_only" | "classical" | "couldnt_check" | "not_measured";
  label: string;
}
export interface MigrationSystem {
  key: string;
  kind_label: string;
  name: string;
  status: MigrationStatus;
  plan_line: string;
  /**
   * Set while this system's measurement waits or runs (drawn in place of Today's sentence).
   */
  measuring: RowStatus | null;
  today: MigrationSystemToday;
  settings: MigrationSystemSettings;
  cost: MigrationCostTable | null;
  recommendation: MigrationSystemRecommendation;
  options_title: string;
  /**
   * In the order keep, hybrid, full_pq, wrap. Empty when there is no status.
   */
  options: MigrationOption[];
  /**
   * The user's saved choice (history: older choices, newest first).
   */
  choice: MigrationSystemChoice | null;
  choices_note: string;
  tracks?: MigrationTrack[];
  tracks_brief?: MigrationTrackBrief[];
  target_line?: string;
  also_noticed_title?: string;
  also_noticed?: string[];
  change?: ChangeView | null;
}
export interface MigrationSystemToday {
  title: string;
  sentence: string;
  file_note: string | null;
  facts: LabeledRichValue[];
  control_line: string | null;
  details_label: string;
  /**
   * Drawn with ResultDetail inside a closed disclosure.
   */
  result: MeasurementResult | null;
}
export interface MigrationSystemSettings {
  title: string;
  intro: string;
  fields: MigrationSettingField[];
}
export interface MigrationSystemRecommendation {
  title: string;
  tag: string | null;
  reasons: RichPart[][];
  evidence: RichPart[] | null;
  /**
   * "See the evidence": opens the details disclosure above and scrolls to it.
   */
  evidence_link: string | null;
  /**
   * Shown instead of reasons when there is no recommendation.
   */
  none_text: string | null;
}
export interface MigrationSystemChoice {
  line: string;
  history: string[];
}
export interface MigrationTrack {
  key: "kex" | "auth" | "signatures";
  title: string;
  short_title: string;
  status: TrackStatus;
  sentence: string;
  facts: LabeledRichValue[];
  next: RichPart[];
  why: RichPart[];
  next_label: string;
  why_label: string;
}
export interface TrackStatus {
  code: "hybrid" | "pq_only" | "classical" | "couldnt_check" | "not_measured" | "post_quantum";
  label: string;
}
export interface MigrationTrackBrief {
  title: string;
  status: TrackStatus;
}
export interface MigrationTabs {
  systems: string;
  roadmap: string;
}
export interface MigrationView {
  plan_id: number;
  import_id: number;
  is_demo: boolean;
  title: string;
  subline: RichPart[];
  disclaimer: string;
  /**
   * True while measuring: ask again every second.
   */
  busy: boolean;
  measure: MigrationMeasure;
  tabs: MigrationTabs;
  list_title: string;
  /**
   * Set when the file names no server and no signing program.
   */
  empty_text: string | null;
  systems: MigrationSystem[];
  roadmap: MigrationRoadmap;
}
export interface Ok {
  ok: true;
}
export interface OrderBody {
  /**
   * @maxItems 50
   */
  order: number[];
}
export interface PasswordBody {
  password: string;
}
export interface PlanView {
  id: number;
  import_id: number;
  is_demo: boolean;
  intro: string;
  subject: RichPart[];
  running: boolean;
  can_run_all: boolean;
  has_results: boolean;
  /**
   * A migration measurement exists for this plan (the Fixes step opens for it too).
   */
  has_migration: boolean;
  max_parallel: number;
  /**
   * True when the file has more than one server or signing program: cards are drawn under group headings.
   */
  grouped: boolean;
  /**
   * In display order. Sent even when not grouped (the screen then ignores them).
   */
  groups: PlanGroup[];
  not_tested: NotTested | null;
  /**
   * When grouped, already ordered group by group, in the order of `groups`.
   */
  tests: TestCard[];
  catalog_title: string;
  catalog: CatalogItem[];
  catalog_note: string;
}
export interface TestCard {
  id: number;
  kind:
    | "tls_versions"
    | "certificate"
    | "official_vectors"
    | "bad_signatures"
    | "speed_size"
    | "pq_readiness"
    | "mldsa_compare";
  title: string;
  origin: "suggested" | "added";
  tag: string | null;
  description: string;
  why: string;
  status: "not_run" | "waiting" | "running" | "done";
  status_text: string;
  progress: Progress | null;
  result: Badge | null;
  can_run: boolean;
  can_remove: boolean;
  /**
   * The key of the group this card is under, when the plan is grouped.
   */
  group: string | null;
}
export interface ProofRowCheck1 {
  ok: boolean | null;
  text: string;
}
export interface PullRequestBody {
  /**
   * @maxItems 8
   */
  reviewers:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string];
}
export interface Result {
  claim_id: number;
  claim: Claim;
  result: "True" | "False" | "Couldn't check";
  found: string;
  reason: string | null;
  evidence: Evidence[];
  /**
   * One plain sentence: what was found and why that gives this result. Shown on top of the row.
   */
  summary: string;
  /**
   * Things the check saw that the file didn't ask about. Side notes, never a result. Often empty.
   */
  also_noticed: string[];
}
export interface RetestBody {
  version: string;
  component?: string | null;
}
export interface Session {
  setup_required: boolean;
  logged_in: boolean;
  mode: "demo" | "isolated";
  /**
   * The sentence under the header saying how software is run, written by the backend.
   */
  mode_line: string;
  demo_server: DemoServer;
}
export interface VerifyRun {
  id: number;
  import_id: number;
  started_at: string;
  finished_at: string;
  results: Result[];
}
