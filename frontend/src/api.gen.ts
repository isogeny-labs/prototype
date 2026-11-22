// GENERATED from the backend's API description (src/api-schema.json). Do not edit by hand.
// The shapes live in backend/app/web/models.py; see scripts/gen-api-types.mjs for how to remake this file.

export type ClaimKind =
  "protocol_versions" | "cipher_suites" | "key_exchange" | "certificate" | "signature_algorithm" | "post_quantum";
export type LocationKind = "server" | "software" | "unknown";
export type ResultValue = "True" | "False" | "Couldn't check";
export type Mode = "demo" | "isolated";
export type CatalogKind =
  | "tls_versions"
  | "certificate"
  | "official_vectors"
  | "bad_signatures"
  | "speed_size"
  | "pq_readiness"
  | "mldsa_compare";
export type TestKind =
  | "tls_versions"
  | "certificate"
  | "official_vectors"
  | "bad_signatures"
  | "speed_size"
  | "pq_readiness"
  | "mldsa_compare"
  | "advisory_cases";
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
export type SourceKey = "live" | "lab" | "file" | "published";
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
export type DependencyQuestionKey = "ml_kem_768" | "x25519mlkem768" | "ml_dsa_65";
export type DependencyAnswer =
  "yes" | "no" | "doesnt_apply" | "not_in_knowledge_base" | "couldnt_tell_version" | "needs_your_environment";
export type DependencyLabel = "release_notes" | "public_copy";
export type DependencyState = "measured" | "not_measured" | "couldnt_check" | "couldnt_trust" | "not_offered";
export type DependencyTrack = "kex" | "auth" | "signatures";
export type GroupKey = "verification" | "encryption" | "migration" | "dependencies";
export type ItemState = "open" | "in_progress" | "done";
export type ChangeStatusKey =
  | "not_run"
  | "running"
  | "no_difference"
  | "passed_before_fails_now"
  | "failed_before_passes_now"
  | "nothing_to_run"
  | "cant_run"
  | "couldnt_trust";
export type ChangeOutcome =
  "fails_now" | "passes_now" | "same" | "slower_now" | "not_slower" | "not_compared" | "not_trusted";
export type WatchStatusKey =
  | "no_fix"
  | "fix_published"
  | "being_tested"
  | "test_proposed"
  | "no_test"
  | "not_yours"
  | "withdrawn"
  | "gone"
  | "not_watched";
export type AssistantThread = "testing" | "fixing" | "planning";

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
/**
 * The Advisories page of an assessment (phase 5c). It words no result and decides none.
 */
export interface AdvisoriesView {
  title: string;
  subline: string;
  standing_line: string;
  packs_line: string;
  packs_link: ItemLink;
  answers_line: string;
  otto: OttoHarnessLine;
  waiting: AdvisoryWaiting;
  filters: AdvisoryFilters;
  columns: string[];
  rows: AdvisoryRow[];
  empty: string | null;
  assessment_id: number | null;
  /**
   * Phase 6: the block New advisories. Always sent by the current backend.
   */
  lookup?: AdvisoryLookup | null;
}
export interface ItemLink {
  /**
   * The page that holds the item, e.g. "evidence", "fixes", "migration/systems".
   */
  page: string;
  /**
   * The item to open there (a check, claim, fix, system or library id); null for the page.
   */
  item: string | null;
  section?: string | null;
  /**
   * The work group to filter the page to.
   */
  group?: string | null;
  /**
   * Another assessment (the Project overview links into each).
   */
  assessment_id?: number | null;
}
export interface OttoHarnessLine {
  installed: boolean;
  line: string;
}
/**
 * Above the table: how many proposed checks nobody has decided yet. There is no button that decides several.
 */
export interface AdvisoryWaiting {
  count: number;
  /**
   * Why nothing can be decided here right now (closed, or Otto not installed).
   */
  blocked_reason: string | null;
  line: string;
  note: string;
}
export interface AdvisoryFilters {
  test: AdvisoryFilterOption[];
  decision: AdvisoryFilterOption[];
  result: AdvisoryFilterOption[];
}
export interface AdvisoryFilterOption {
  key: string;
  label: string;
}
export interface AdvisoryRow {
  id: string;
  name: string;
  /**
   * Null for an advisory of an earlier pack (also one a later pack only updates).
   */
  new: AdvisoryNew | null;
  published: string;
  published_text: string;
  package: string;
  pack: string;
  fits: string[];
  fits_text: string;
  test: AdvisoryTestCell;
  proposal: AdvisoryProposalCell;
  result: AdvisoryResultCell;
  search: string;
  panel: AdvisoryPanel;
}
/**
 * The 5c fixes: the tag beside an advisory that first arrived with the most recently installed test pack.
 */
export interface AdvisoryNew {
  /**
   * "New"
   */
  label: string;
  /**
   * Said on hover and to a screen reader: "Arrived with test pack 2026.11.2".
   */
  title: string;
}
export interface AdvisoryTestCell {
  key: "ready" | "not_offered" | "none";
  /**
   * "Test ready", "Not offered" or "No test yet"
   */
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  reason: string;
}
export interface AdvisoryProposalCell {
  /**
   * "proposed", "accepted", "rejected", "mixed" or "none" (for the Decision filter)
   */
  key: string;
  /**
   * "Proposed", "Added", "Not added (reason)", "Mixed" or "Nothing proposed"
   */
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  /**
   * With several programs: the counts, never merged.
   */
  text: string | null;
  /**
   * With several programs: every state among them.
   */
  keys?: string[];
}
export interface AdvisoryResultCell {
  /**
   * "pass", "fail", "warn", "neutral", "not_run", "not_added" or "none" (for the Result filter)
   */
  key: string;
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  text: string | null;
  /**
   * 22 November 2026: where the result came from; null where there is none.
   */
  source_tag?: Source | null;
}
/**
 * The one tag beside a result's, a status's or a fix's own word: Observed live, Proven in the lab, From your file or
 * Published. It decides nothing and changes no result.
 */
export interface Source {
  key: "live" | "lab" | "file" | "published";
  label: string;
  /**
   * What the tag means, in one line, wherever it is shown.
   */
  meaning: string;
  /**
   * One sentence about this item (shown in its panel), or null.
   */
  note?: string | null;
}
export interface AdvisoryPanel {
  sentence: string;
  publisher: AdvisoryQuote | null;
  affected: AdvisoryAffected | null;
  notes: AdvisoryNotes | null;
  also_known_as: string[];
  sources: AdvisorySource[];
  test: AdvisoryTestBlock | null;
  no_test: AdvisoryNoTest | null;
  here: AdvisoryHere;
  fix: AdvisoryFix;
  claude: AdvisoryClaude;
  related_key: string;
}
/**
 * A line of the publisher's own text, word for word. Information from the advisory, never a result.
 */
export interface AdvisoryQuote {
  text: string;
  source: string;
  publisher: string;
  /**
   * An https link to a known publisher, or "" (then the source is shown as text).
   */
  href: string;
  read_on: string;
  tag: string;
}
export interface AdvisoryAffected {
  line: string;
  quote: AdvisoryQuote;
}
/**
 * What Claude noted when it read the advisory. Information, never a result.
 */
export interface AdvisoryNotes {
  title: string;
  kind_line: string;
  text: string | null;
  caption: string;
}
export interface AdvisorySource {
  label: string;
  title: string;
  publisher: string;
  href: string;
  read_on: string;
}
export interface AdvisoryTestBlock {
  title: string;
  question: string;
  cases_line: string;
  control: string;
  rule: string;
  design_fingerprint: string;
  trial: AdvisoryTrial;
  ledger: AdvisoryLedger;
  /**
   * Sandbox research: the proof of a test tried on sandbox copies.
   */
  proof?: TestProofBlock | null;
}
export interface AdvisoryTrial {
  title: string;
  lines: string[];
}
export interface AdvisoryLedger {
  title: string;
  count: number;
  entries: AdvisoryLedgerEntry[];
  note: string;
}
export interface AdvisoryLedgerEntry {
  seq: number;
  kind: string;
  id: string;
  at: string;
  what: string;
}
/**
 * Sandbox research (a prototype): everything that stands behind a test tried on sandbox copies. It words no result.
 */
export interface TestProofBlock {
  /**
   * "How this test was proven"
   */
  title: string;
  /**
   * "Sandbox copy"
   */
  label: string;
  summary: string;
  table: TestProofTable;
  registered: TestProofRegistered;
  judged: string;
  code: TestProofCode;
  copies: TestProofCopies;
  replayed: string;
  not_shown: string;
}
export interface TestProofTable {
  columns: string[];
  rows: TestProofRow[];
  note: string;
}
export interface TestProofRow {
  key: string;
  /**
   * What ran: our reference library, a public copy, or the control.
   */
  label: string;
  /**
   * The count for that part of the trial (the separate reviewer's for a copy and for the reference; the pinned trial script's for the control). A count, never Passed or Failed.
   */
  count: string;
  /**
   * What had to happen, as it was frozen before the first run.
   */
  must: string;
}
export interface TestProofRegistered {
  line: string;
  pins_title: string;
  pins: TestProofPin[];
}
export interface TestProofPin {
  name: string;
  sha256: string;
}
/**
 * The code that asked the library its questions, shown as text. It is data here: nothing on a screen runs it.
 */
export interface TestProofCode {
  title: string;
  /**
   * "Written by Otto" when Claude wrote it; null for the app's own asking code.
   */
  label: string | null;
  author: string;
  file: string;
  lines: number;
  source: string;
  sha256: string;
  line: string;
  show: string;
  hide: string;
  second: TestProofSecondCode | null;
  agree_line: string | null;
  known_lines: string[];
}
export interface TestProofSecondCode {
  title: string;
  author: string;
  lines: number;
  source: string;
  sha256: string;
}
export interface TestProofCopies {
  title: string;
  rows: TestProofCopy[];
  left_out: string[];
  image_line: string;
  trust_line: string;
}
export interface TestProofCopy {
  version: string;
  role: string;
  line: string;
  published: string | null;
  helpers_line: string | null;
  sha256: string;
  url: string;
}
export interface AdvisoryNoTest {
  /**
   * "No test yet" or "Not offered"
   */
  label: string;
  reason: string;
  trial: AdvisoryTrial | null;
  ledger: AdvisoryLedger | null;
  /**
   * Sandbox research: what a design's trial on sandbox copies showed.
   */
  proof?: TestProofBlock | null;
}
export interface AdvisoryHere {
  title: string;
  rows: AdvisoryHereRow[];
  empty: string | null;
  note?: string | null;
}
export interface AdvisoryHereRow {
  program: string;
  /**
   * The proposal's word ("Proposed", "Not added (reason)") or "Not run yet"; null once there is a result.
   */
  status: string | null;
  /**
   * Otto's proposed check for this program, with its state, decisions and buttons.
   */
  proposal: OttoProposal | null;
  result: AdvisoryHereResult | null;
  /**
   * Open in Checks.
   */
  checks_link: ItemLink | null;
  /**
   * See the evidence.
   */
  evidence_link: ItemLink | null;
  ledger: AdvisoryLedger | null;
}
/**
 * One proposal of Otto's as a screen shows it. It words no result; a decision is recorded with who and when.
 */
export interface OttoProposal {
  id: string;
  kind: "check" | "fix" | "plan" | "dependency";
  kind_label: string;
  /**
   * "From Otto"
   */
  label: string;
  title: string;
  why: string;
  why_label: string;
  lines: string[];
  status: OttoProposalStatus;
  decided_line: string | null;
  /**
   * What an accepted proposal has led to so far.
   */
  effect: string | null;
  buttons: OttoProposalButton[];
  note: string | null;
  reject_dialog: OttoRejectDialog | null;
  history: OttoProposalHistory;
  link: ItemLink;
  proposed_at: string | null;
  /**
   * Sandbox research: how the proposed test was proven, folded under the card.
   */
  proof?: TestProofBlock | null;
}
export interface OttoProposalStatus {
  key: "proposed" | "accepted" | "rejected";
  /**
   * "Proposed", "Added" or "Accepted", "Not added (reason)"
   */
  word: string;
  tone: "pass" | "fail" | "neutral" | "warn";
}
export interface OttoProposalButton {
  key: "accept" | "reject" | "undo" | "reconsider";
  label: string;
  can: boolean;
  /**
   * Why the button is off right now.
   */
  blocked_reason: string | null;
}
export interface OttoRejectDialog {
  title: string;
  line: string;
  reason_label: string;
  max: number;
  confirm: string;
  cancel: string;
}
export interface OttoProposalHistory {
  title: string;
  count: number;
  rows: OttoDecisionLine[];
  footnote: string;
  ledger: AdvisoryLedger | null;
}
export interface OttoDecisionLine {
  number: number;
  word: string;
  by: string;
  at: string;
  at_text: string;
  reason: string | null;
  ledger_entry: string | null;
  line: string;
}
/**
 * The reviewer's result for this advisory's check in this assessment, as Evidence Lab words it.
 */
export interface AdvisoryHereResult {
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  plain: string;
  component: string | null;
  finished_at: string | null;
  /**
   * After a retest: which version this result is of, and what the first run read.
   */
  ran_on?: string | null;
  /**
   * 22 November 2026: where this result came from (Proven in the lab).
   */
  source_tag?: Source | null;
  /**
   * Sandbox research: the run was on a public copy sandbox research made.
   */
  sandbox_copy?: boolean;
}
export interface AdvisoryFix {
  title: string;
  /**
   * "From Otto" when the pack proposes a fix.
   */
  label: string | null;
  state: "proven" | "not_proven" | "none";
  lines: string[];
  quote: AdvisoryQuote | null;
  here: AdvisoryFixHere | null;
}
export interface AdvisoryFixHere {
  /**
   * "View in Fixes"
   */
  label: string;
  link: ItemLink;
  line: string;
}
export interface AdvisoryClaude {
  title: string;
  steps: AdvisoryStep[];
  note: string;
}
export interface AdvisoryStep {
  step: string;
  source: "recorded" | "live";
  line: string;
  prompt_sha256: string;
  answer_sha256: string;
}
/**
 * Phase 6, Otto's research loop: the block "New advisories" of the Advisories page.
 */
export interface AdvisoryLookup {
  title: string;
  intro: string;
  covers: string;
  /**
   * Sandbox research: what the research runs of the last day did and spent.
   */
  sandbox_line?: string | null;
  libraries_line: string;
  look: LookupButton;
  last: LookupLast | null;
  research: LookupResearch;
  /**
   * A research run is going on: ask again in a few seconds.
   */
  busy: boolean;
}
export interface LookupButton {
  label: string;
  can: boolean;
  blocked_reason: string | null;
  dialog: LookupDialog;
}
/**
 * The box a button opens first: what will be sent or started, and what will not.
 */
export interface LookupDialog {
  title: string;
  lines: string[];
  confirm: string;
  cancel: string;
}
export interface LookupLast {
  line: string;
  source_line: string;
  notes: string[];
  rows: LookupRow[];
  empty: string | null;
}
/**
 * One published advisory a look found, with where it stands. Information from the publisher, never a result.
 */
export interface LookupRow {
  id: string;
  /**
   * The publisher's own title.
   */
  title: string;
  library: string;
  published: string;
  /**
   * What it says about the versions this assessment has.
   */
  fits: string;
  state: LookupRowState;
  /**
   * Why there is no test yet, or where the advisory is now.
   */
  reason: string | null;
  /**
   * Its row on this page, once a test pack holds it.
   */
  link: ItemLink | null;
  publisher: string;
  url: string;
  /**
   * Sandbox research: a test for it would be tried on public copies fetched from a registry.
   */
  sandbox?: boolean;
  /**
   * Sandbox research: its row on the Watch list, while it has no fix yet.
   */
  watch?: LabelledLink | null;
}
export interface LookupRowState {
  key: "in_pack" | "in_waiting_pack" | "new" | "no_test" | "not_yours";
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
}
export interface LabelledLink {
  label: string;
  link: ItemLink;
}
export interface LookupResearch {
  label: string;
  can: boolean;
  blocked_reason: string | null;
  /**
   * False until a look has been made.
   */
  shown: boolean;
  dialog: LookupDialog;
  progress: LookupProgress | null;
}
export interface LookupProgress {
  line: string;
  running: boolean;
  title: string;
  /**
   * What the research command said, newest last.
   */
  lines: string[];
}
export interface AlgorithmName {
  technical: string;
  plain: string;
}
export interface ApplyView {
  title: string;
  badge: ChangeBadge;
  paragraphs: RichPart[][];
  differences: string[];
  history: string[];
  /**
   * 22 November 2026: Observed live once the server was measured again after Apply or Roll back; null while it is measured, or when Apply was refused.
   */
  source_tag?: Source | null;
}
export interface ChangeBadge {
  label: string;
  look: "pass" | "fail" | "warn" | "neutral";
}
export interface RichPart {
  t: "text" | "mono" | "tag" | "time" | "demo";
  v: string;
  s?: ("live" | "lab" | "file" | "published") | null;
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
export interface AssessmentBrief {
  id: number;
  number: number;
  /**
   * "Assessment 2", or the name the person gave it
   */
  title: string;
  name: string | null;
  /**
   * Phase 5b: what it is for (a label only); null for one made before phase 5b.
   */
  purpose: Purpose | null;
  reference: string | null;
  status: AssessmentStatus;
  archived: boolean;
  created_at: string;
  closed_at: string | null;
  file: AssessmentFile | null;
}
export interface Purpose {
  key: string;
  label: string;
}
export interface AssessmentStatus {
  key: "open" | "closed";
  label: string;
  /**
   * Why it is closed, then the closed sentence; null when open.
   */
  closed_line: string | null;
  /**
   * Phase 5b: who signed it off and when; null when open or closed by the earlier rule.
   */
  signoff: Signoff | null;
}
export interface Signoff {
  /**
   * The name typed when it was closed (the app has one login).
   */
  by: string;
  note: string | null;
  at: string;
}
export interface AssessmentFile {
  import_id: number;
  filename: string;
  format: string;
  is_demo: boolean;
  imported_at: string;
}
export interface AssessmentChangeBody {
  name?: string | null;
  project_id?: number | null;
  archived?: boolean | null;
  close?: boolean;
  signed_off_by?: string | null;
  note?: string | null;
  purpose?: string | null;
  reference?: string | null;
}
export interface AssessmentCounts {
  claims: ClaimCounts | null;
  tests: TestCounts | null;
  fixes: FixCounts | null;
  systems: SystemCounts | null;
}
export interface ClaimCounts {
  checked: number;
  false: number;
  true: number;
  couldnt_check: number;
}
export interface TestCounts {
  run: number;
  failed: number;
  passed: number;
}
export interface FixCounts {
  total: number;
  open: number;
}
export interface SystemCounts {
  total: number;
  classical: number;
  hybrid: number;
  pq_only: number;
  couldnt_check: number;
  not_measured: number;
}
export interface AssessmentProject {
  id: number;
  name: string;
  is_demo: boolean;
  archived: boolean;
}
export interface AssessmentView {
  id: number;
  number: number;
  /**
   * "Assessment 2", or the name the person gave it
   */
  title: string;
  name: string | null;
  /**
   * Phase 5b: what it is for (a label only); null for one made before phase 5b.
   */
  purpose: Purpose | null;
  reference: string | null;
  status: AssessmentStatus;
  archived: boolean;
  created_at: string;
  closed_at: string | null;
  file: AssessmentFile | null;
  organization: string;
  project: AssessmentProject;
  path: PathStep[];
  import: Import | null;
  plan_id: number | null;
  has_verify: boolean;
  has_results: boolean;
  has_migration: boolean;
  counts: AssessmentCounts;
  next_step: NextStep;
  /**
   * Phase 5b: the Overview's blocks (null before a file).
   */
  blocks?: OverviewBlocks | null;
  /**
   * Phase 5c: "Waiting for you": the proposals nobody has decided yet.
   */
  waiting?: OttoWaiting | null;
}
export interface PathStep {
  id: number;
  name: string;
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
   * Phase 5a: the assessment this import belongs to.
   */
  assessment_id?: number | null;
  /**
   * The heading of the settings list, e.g. "System settings from the file".
   */
  settings_title?: string;
  /**
   * Settings rows the file carries (not claims: nothing checks them). Optional: older stored answers may lack it.
   */
  settings?: ImportSetting[];
  /**
   * Phase 5c: "N checks may apply", marked From Otto. Nothing runs on import.
   */
  otto?: ImportOtto | null;
  /**
   * 22 November 2026: where every claim on this page came from (From your file).
   */
  claim_source_tag?: Source | null;
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
/**
 * Import: "N checks may apply", marked From Otto, with the way to Advisories. Nothing runs on import.
 */
export interface ImportOtto {
  count: number;
  label: string;
  text: string;
  note: string;
  link: ItemLink;
  link_label: string;
}
export interface NextStep {
  /**
   * The page that holds the next thing to do, e.g. "inventory/import", "tests".
   */
  page: string;
  label: string;
  text: string;
}
export interface OverviewBlocks {
  groups: OverviewGroup[];
  /**
   * False claims, failed tests, dependency blockers: each its own count.
   */
  findings: OverviewFact[];
  evidence: OverviewEvidence;
  /**
   * Only while Sandbox research is on and the list holds something.
   */
  watch_list?: OverviewWatchList | null;
}
export interface OverviewGroup {
  key: "verification" | "encryption" | "migration" | "dependencies";
  label: string;
  question: string;
  checks: StateCounts | null;
  /**
   * 22 November 2026: where the group's items came from, counted as Checks counts them (Observed live, Proven in the lab, ...).
   */
  source_counts?: SourceCount[];
  fixes: StateCounts | null;
  facts: OverviewFact[];
  empty_text: string | null;
}
export interface StateCounts {
  open: number;
  in_progress: number;
  done: number;
}
/**
 * How many of a group's checks rest on one source (the Overview's line).
 */
export interface SourceCount {
  key: "live" | "lab" | "file" | "published";
  label: string;
  meaning: string;
  count: number;
}
export interface OverviewFact {
  label: string;
  value: number;
  link: ItemLink;
}
export interface OverviewEvidence {
  runs: number;
  last_download: LastDownload | null;
}
export interface LastDownload {
  at: string;
  fingerprint: string;
}
/**
 * Sandbox research: how many watched weaknesses have no fix yet. Information, never a result.
 */
export interface OverviewWatchList {
  no_fix: number;
  fix_published: number;
  line: string;
  link: ItemLink;
}
/**
 * The Overview's "Waiting for you": the proposals nobody has decided yet, each kind linking to its page.
 */
export interface OttoWaiting {
  title: string;
  total: number;
  items: OttoWaitingItem[];
  line: string;
  note: string;
}
export interface OttoWaitingItem {
  kind: "check" | "fix" | "plan" | "dependency";
  count: number;
  text: string;
  link: ItemLink;
  page_label: string;
}
/**
 * The request of the page's own button. The browser sends it on Confirm, through the same call the page uses.
 */
export interface AssistantAction {
  type:
    | "verify"
    | "run"
    | "run_all"
    | "retest"
    | "run_picked_tests"
    | "connect"
    | "run_proof_again"
    | "open_pull_request"
    | "retest_now"
    | "try"
    | "ask_approval"
    | "measure_library"
    | "measure_all"
    | "measure_status"
    | "open";
  plan_id: number | null;
  import_id: number | null;
  /**
   * A test of the plan (Run).
   */
  item_id: number | null;
  fix_id: string | null;
  /**
   * A server change's key (Try on a test copy, Ask for approval), or the id of a developer's change (Run the picked tests).
   */
  change: string | null;
  /**
   * A library row (Measure on a public copy).
   */
  row: string | null;
  version: string | null;
  component: string | null;
  /**
   * The reviewers the page ticks by default.
   */
  reviewers: string[] | null;
  /**
   * "open": where it goes; opening a page needs no Confirm. "retest_now": where the page itself goes once its request is answered (Evidence, on the result the fix came from).
   */
  link: ItemLink | null;
}
export interface AssistantBadge {
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
}
/**
 * Phase 6b: the text box at the foot of the panel.
 */
export interface AssistantBox {
  /**
   * "Ask Otto, or tell it what to do" (phase 6c; in 6b alone it read "Tell Otto where to go or what to do")
   */
  label: string;
  send: string;
  max: number;
  /**
   * Up to three examples fitted to the page. A chip sends its own words.
   */
  chips: string[];
  /**
   * Phase 6c: up to three of the six fixed questions that fit the page and the open item.
   */
  questions: string[];
  /**
   * False in a closed assessment: what is typed there is answered and not kept.
   */
  kept: boolean;
  kept_note: string | null;
}
export interface AssistantCan {
  say: string;
  about: string;
  kind: "go" | "do";
}
/**
 * The Confirm step: what will happen and what will not, and which button of which page it presses.
 */
export interface AssistantConfirm {
  title: string;
  lines: string[];
  /**
   * "This is the Run all button on Checks."
   */
  names: string;
  /**
   * "Confirm"
   */
  confirm: string;
  /**
   * "Cancel"
   */
  cancel: string;
  /**
   * Reject only: the optional reason.
   */
  reason: AssistantReason | null;
}
export interface AssistantReason {
  /**
   * "Reason (optional, one short line)"
   */
  label: string;
  max: number;
}
/**
 * One button of a suggestion: the page's own button, with the page's own reason when it is off.
 */
export interface AssistantDecision {
  key: "accept" | "reject" | "undo" | "reconsider";
  label: string;
  can: boolean;
  blocked_reason: string | null;
  /**
   * Null when the button is off: there is nothing to confirm.
   */
  confirm: AssistantConfirm | null;
}
export interface AssistantElsewhere {
  /**
   * "Elsewhere: 2 more"
   */
  title: string;
  count: number;
  lines: AssistantElsewhereLine[];
  /**
   * "Nothing from Otto is waiting for a decision." when nothing waits anywhere.
   */
  empty: string | null;
}
export interface AssistantElsewhereLine {
  /**
   * "Fixes: 1 proposed fix, Update elliptic to 6.5.7"
   */
  text: string;
  count: number;
  link: ItemLink;
  thread: "testing" | "fixing" | "planning";
}
/**
 * One entry of the panel: a suggestion (one of Otto's proposals), a next step (a button of a page) or what a
 * result means; and, in a thread so far, a reviewed result or where a fix stands.
 */
export interface AssistantEntry {
  id: string;
  kind: "suggestion" | "next" | "meaning" | "result" | "fix_step" | "said";
  /**
   * Its line in the one table of kinds, e.g. "next:run_all".
   */
  what: string;
  thread: ("testing" | "fixing" | "planning") | null;
  /**
   * "From Otto", "Next step", "What this means", "Result", "Fix" or (phase 6b) "You said"
   */
  mark: string;
  title: string;
  text: string | null;
  /**
   * When its cause happened (ISO): the order of a thread so far.
   */
  at: string | null;
  badge: AssistantBadge | null;
  /**
   * Where it lives: "On Advisories", with the link.
   */
  where: LabeledLink | null;
  links: LabeledLink[];
  /**
   * A suggestion: the proposal exactly as its page shows it.
   */
  proposal: OttoProposal | null;
  decisions: AssistantDecision[];
  step: AssistantStep | null;
  /**
   * It is about the item that is open on the page.
   */
  open_item: boolean;
  /**
   * Phase 6c: a kept answer to a fixed question: its facts.
   */
  facts?: AssistantFact[];
}
export interface LabeledLink {
  label: string;
  link: ItemLink;
}
export interface AssistantStep {
  /**
   * "nothing": it only opens a page, at once.
   */
  needs: "confirm" | "nothing";
  action: AssistantAction;
  can: boolean;
  /**
   * The page's own reason when its button is off.
   */
  blocked_reason: string | null;
  running: boolean;
  progress: string | null;
  confirm: AssistantConfirm | null;
}
/**
 * Phase 6c: one fact of an answer: a sentence the app already shows about the item, with the link to where.
 */
export interface AssistantFact {
  text: string;
  link: ItemLink | null;
  /**
   * What the link is called: "See the evidence", "Open the advisory", "View in Fixes".
   */
  label: string | null;
}
/**
 * Where an answer leads: a page of this assessment (or Settings), one item on it, and the filters of its table.
 */
export interface AssistantGo {
  page: string;
  item: string | null;
  group: string | null;
  /**
   * The page's own Result filter value.
   */
  result: string | null;
  /**
   * Checks: its Came from filter value.
   */
  came_from: string | null;
  /**
   * Advisories: its Decision filter value.
   */
  decision: string | null;
}
export interface AssistantOnPage {
  title: string;
  entries: AssistantEntry[];
  empty: string | null;
  empty_link: LabeledLink | null;
}
export interface AssistantOpen {
  /**
   * Which button of the card shows its Confirm step.
   */
  key: "accept" | "reject" | "undo" | "reconsider" | "step";
  /**
   * A reject's reason, cut from the person's own words. Nothing is sent before Confirm.
   */
  reason: string | null;
}
export interface AssistantOption {
  label: string;
  /**
   * A sentence that names exactly this one. Choosing it sends these words.
   */
  say: string;
}
/**
 * Phase 6b: Otto's answer to one typed sentence. Nothing has been decided or started by it: `went`, `page_only`
 * and `tab` only move around, and `card` hands back an entry whose Confirm step the browser shows.
 */
export interface AssistantReply {
  kind: "went" | "card" | "which" | "cannot" | "help" | "page_only" | "tab" | "closed" | "answer" | "whatif";
  text: string;
  go: AssistantGo | null;
  entry: AssistantEntry | null;
  open: AssistantOpen | null;
  options: AssistantOption[];
  /**
   * What can be said on this page, from the one list.
   */
  can: AssistantCan[];
  tab: AssistantTabChange | null;
  /**
   * The tab the exchange is filed under, if any.
   */
  thread: ("testing" | "fixing" | "planning") | null;
  /**
   * Phase 6c: the fixed question that was answered, in its own wording.
   */
  question?: string | null;
  /**
   * Phase 6c: where an answer is from: "From this assessment's records".
   */
  label?: string | null;
  /**
   * Phase 6c: an answer's facts, each with its link.
   */
  facts?: AssistantFact[];
  /**
   * Phase 6e: the four parts of a what-if.
   */
  whatif?: WhatIf | null;
}
export interface AssistantTabChange {
  thread: "testing" | "fixing" | "planning";
  how: "open" | "close";
}
/**
 * Phase 6e, first half: what the app knows about updating one library to one version, in four parts. Facts by fixed
 * rules; nothing here is a result, and nothing is started by reading it.
 */
export interface WhatIf {
  plan_id: number;
  asked: WhatIfName;
  known: boolean;
  library: WhatIfLibrary;
  version: string;
  version_read: boolean;
  /**
   * The versions of this library the assessment has (its dependency list, its scanner file).
   */
  have: string[];
  title: string;
  facts_title: string;
  facts: WhatIfGroup[];
  test_copy: WhatIfTry;
  explanation: string;
  hypotheses_title: string;
  hypotheses_note: string;
  hypotheses: WhatIfHypothesis[];
}
export interface WhatIfName {
  library: string;
  version: string;
}
export interface WhatIfLibrary {
  key: string | null;
  label: string;
}
export interface WhatIfGroup {
  key: "used" | "needs" | "advisories" | "trial" | "post_quantum" | "blocks" | "own_results";
  title: string;
  lines: WhatIfLine[];
  /**
   * What is said when the app has nothing on this point.
   */
  none: string | null;
}
export interface WhatIfLine {
  text: string;
  /**
   * Where it comes from: "From your file", "Package file says", "Release notes say", "Test pack 2026.11.2", ...
   */
  label: string | null;
  /**
   * Where the app shows it.
   */
  link: ItemLink | null;
  source: WhatIfSource | null;
}
/**
 * Where a fact is quoted from: the publisher's package file or release notes, or a test pack's copy of a publisher's line.
 */
export interface WhatIfSource {
  title: string;
  /**
   * An https address of the publisher, or null where the line is quoted from an installed test pack.
   */
  url: string | null;
  quote: string | null;
  /**
   * The day it was read, YYYY-MM-DD, where the source records one.
   */
  read_on: string | null;
}
/**
 * The try on a test copy: Evidence's own Retest new version, pointed at this version.
 */
export interface WhatIfTry {
  title: string;
  /**
   * "Retest new version": the button of Evidence it stands for.
   */
  button: string;
  offered: boolean;
  /**
   * Why it is not offered, in the page's own words where the page has them.
   */
  reason: string | null;
  component: string | null;
  version: string;
  /**
   * What a retest changes in this assessment, said before anything is pressed.
   */
  changes: string[];
}
export interface WhatIfHypothesis {
  text: string;
}
/**
 * The one line under the title: what Settings says about Live Otto, with the way there when it is off.
 */
export interface AssistantStatus {
  /**
   * "Live Otto is off." or "Live Otto is on."
   */
  text: string;
  live: boolean;
  link: LabeledLink | null;
}
export interface AssistantTab {
  key: "testing" | "fixing" | "planning";
  label: string;
  /**
   * How many of this thread's suggestions nobody has decided yet.
   */
  waiting: number;
  /**
   * Changes when the thread gets a new entry: the browser keeps it for a closed tab and for the dot.
   */
  mark: string;
  so_far_title: string;
  so_far: AssistantEntry[];
  so_far_empty: string | null;
}
export interface AssistantView {
  assessment_id: number;
  plan_id: number | null;
  /**
   * "Otto"
   */
  title: string;
  status: AssistantStatus;
  /**
   * The closed sentence, and what Settings says when Otto is not installed.
   */
  notices: string[];
  note: string;
  recorded_as: OttoName;
  page: string;
  page_label: string;
  /**
   * The tab this page selects (null on the Overview).
   */
  thread: ("testing" | "fixing" | "planning") | null;
  box: AssistantBox;
  /**
   * At most three, and only the open ones.
   */
  tabs: AssistantTab[];
  on_page: AssistantOnPage;
  elsewhere: AssistantElsewhere;
  /**
   * Undecided suggestions on this page plus elsewhere.
   */
  waiting: number;
  /**
   * Something is running: ask again in a second.
   */
  busy: boolean;
}
/**
 * Who a decision is recorded as, and whether a name has been typed yet.
 */
export interface OttoName {
  /**
   * "Who decides"
   */
  title: string;
  /**
   * "Your name"
   */
  label: string;
  /**
   * The name a person typed; empty until then.
   */
  value: string;
  /**
   * The typed name, or "You".
   */
  recorded_as: string;
  typed: boolean;
  /**
   * "Recorded as You, with the time."
   */
  line: string;
  save: string;
  note: string;
  max: number;
  /**
   * The label of the field in the Otto panel's first Confirm step.
   */
  ask_label: string;
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
export interface CameFrom {
  key: string;
  /**
   * "Verify", "Test plan", "Retest", "Fix proof", "Try on a test copy", "After Apply", ...
   */
  label: string;
}
/**
 * On an advisory check's card: "From advisory CVE-...", with the link to it on the Advisories page.
 */
export interface CardAdvisory {
  label: string;
  link: ItemLink;
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
export interface ChangeBlock {
  before: DiffLine[];
  after: DiffLine[];
}
/**
 * One line of code in a before or after block. n is the line number in that version of the file.
 */
export interface DiffLine {
  n: number;
  mark: " " | "-" | "+";
  text: string;
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
export interface ChangeFile {
  name: string;
  /**
   * "Added", "Changed" or "Removed"
   */
  what: string;
  /**
   * "5 lines added"; null when the file is not text
   */
  counts: string | null;
  /**
   * the file of the program under test
   */
  is_program: boolean;
  note: string | null;
  /**
   * each changed place, with the lines around it, before and after
   */
  blocks: ChangeBlock[];
}
/**
 * Something to look at. Never a result.
 */
export interface ChangeFlag {
  title: string;
  text: string;
  /**
   * "The app has not tested what this line does."
   */
  note: string;
  source: ChangeSource;
}
export interface ChangeSource {
  title: string;
  url: string;
}
export interface ChangeJob {
  status: "not_run" | "waiting" | "running" | "done";
  progress_text: string | null;
  progress_percent: number | null;
}
export interface ChangePanel {
  message: string;
  starts_from: string | null;
  /**
   * which registered demo program the change's code is, or that it is none
   */
  gives: string | null;
  files: ChangeFile[];
  picked: ChangeTest[];
  not_picked: ChangeTest[];
  picked_empty: string | null;
  run: ChangeRunButton;
  last_run: string | null;
  results: ChangeResult[];
  flags: ChangeFlag[];
  flags_note: string | null;
  more_flags: string | null;
  /**
   * one line when Fixes has an entry for this change (tests that passed fail on it)
   */
  fix_line: string | null;
  /**
   * the way to that entry on Fixes
   */
  fix: ItemLink | null;
}
export interface ChangeTest {
  item_id: number;
  title: string;
  /**
   * the rule that picked it, or left it out, in one sentence
   */
  reason: string;
  link: ItemLink;
}
export interface ChangeRunButton {
  /**
   * "Run the picked tests", then "Run again"
   */
  label: string;
  can: boolean;
  blocked_reason: string | null;
  /**
   * the tests the button runs, by name
   */
  will_run: string[];
  note: string | null;
}
export interface ChangeResult {
  item_id: number;
  title: string;
  before: ChangeResultSide | null;
  /**
   * where the result before comes from
   */
  before_note: string | null;
  now: ChangeResultSide | null;
  job: ChangeJob | null;
  /**
   * "Passed before, fails now", "Failed before, passes now", "Same as before", ...; null until reviewed
   */
  differs: string | null;
  outcome: ("fails_now" | "passes_now" | "same" | "slower_now" | "not_slower" | "not_compared" | "not_trusted") | null;
}
/**
 * The reviewer's word for one run, repeated: a watch run words no result of its own.
 */
export interface ChangeResultSide {
  run_id: number;
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  plain: string;
  ran_on: string | null;
  /**
   * where that run's evidence is shown
   */
  link: ItemLink | null;
  /**
   * 22 November 2026: where this run came from (a copy of the code: Proven in the lab).
   */
  source_tag?: Source | null;
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
export interface ChangeRow {
  /**
   * "change-" and the first twelve characters of its commit: it names the exact code
   */
  id: string;
  title: string;
  branch: string;
  commit: string;
  author: string | null;
  /**
   * a bundled demo change: drawn with the Demo data label
   */
  is_demo: boolean;
  when: string | null;
  files_line: string | null;
  picked_line: string;
  status: ChangeStatus;
  flags_count: number;
  panel: ChangePanel;
}
/**
 * The status word of a developer's change. It is the change's, never a test result.
 */
export interface ChangeStatus {
  key:
    | "not_run"
    | "running"
    | "no_difference"
    | "passed_before_fails_now"
    | "failed_before_passes_now"
    | "nothing_to_run"
    | "cant_run"
    | "couldnt_trust";
  /**
   * "Not run yet", "Running", "No difference found", "Passed before, fails now (1 test)", ...
   */
  word: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  /**
   * its picked tests are running: ask again in a second
   */
  busy: boolean;
  /**
   * one sentence under the word that says why
   */
  reason: string | null;
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
  /**
   * Phase 4e: who can still connect; null for a try made before it.
   */
  clients?: TryClients | null;
  /**
   * 22 November 2026: where the try came from (Proven in the lab: test copies).
   */
  source_tag?: Source | null;
  /**
   * 22 November 2026: one per column: none for the label column, Observed live for the server as measured before, Proven in the lab for each copy.
   */
  column_source_tags?: (Source | null)[];
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
  /**
   * Sandbox research: the run was on a public copy sandbox research made.
   */
  sandbox_copy?: boolean;
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
  /**
   * Phase 5c, on a result of an advisory check only: where the check came from, the trial on public copies, the decisions on its proposal with who and when, and its Otto ledger entries. Records, never a result.
   */
  otto?: OttoResultBlock | null;
  /**
   * Where it came from (22 November 2026): what this rests on; null where nothing was observed or proven (a check not run yet, or that couldn't run).
   */
  source_tag?: Source | null;
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
  /**
   * Phase 5c: a library's fix from Otto: its two proof rows, word for word as in Fixes.
   */
  rows?: string[] | null;
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
/**
 * Evidence, on a result of an advisory check: what stands behind the check. Records only; it words no result.
 */
export interface OttoResultBlock {
  /**
   * "From Otto"
   */
  label: string;
  title: string;
  line: string;
  advisory: LabeledLink;
  design: AdvisoryTrial;
  trial: AdvisoryTrial | null;
  decisions: OttoResultDecisions;
  ledger: AdvisoryLedger;
  note: string;
}
export interface OttoResultDecisions {
  title: string;
  count: number;
  rows: OttoDecisionLine[];
  footnote: string;
  empty: string | null;
}
/**
 * Phase 4e: who can still connect, measured on the try's first copy. Information: it decides nothing about the try.
 */
export interface TryClients {
  title: string;
  running: RowStatus | null;
  /**
   * "1 breaks, 2 connect, 1 didn't connect before either."
   */
  summary: string | null;
  /**
   * "Sort out the 1 that breaks before you apply this change." Holds nothing off.
   */
  warning: string | null;
  columns: string[];
  rows: TryClientRow[];
  note: string;
  /**
   * That it is information and holds Apply off nothing.
   */
  decides: string;
  control: string | null;
  /**
   * Set when the stand-ins' run gave no answer (it could not run, or its control misread).
   */
  no_answer: string | null;
}
export interface TryClientRow {
  /**
   * The stand-in: "old-terminal" | "partner-classical" | "new-terminal" | "pq-only".
   */
  id: string;
  /**
   * "Payment terminal, old firmware"
   */
  name: string;
  /**
   * What its profile offers, in one plain line.
   */
  offers: string;
  /**
   * "Demo data"
   */
  label: string;
  /**
   * Its handshake with the server as it is today: "TLS 1.2, classical (X25519)" | "Refused (protocol version)".
   */
  today: string;
  /**
   * Its handshake with the test copy, in the same words.
   */
  on_copy: string;
  /**
   * The reviewer's word: Connects, Falls back, Breaks, Didn't connect before either, Couldn't check.
   */
  word: string;
  word_key: "connects" | "falls_back" | "breaks" | "not_before" | "couldnt_check";
  tone: "pass" | "fail" | "neutral" | "warn";
  /**
   * "New: it can't connect today." when it connects only on the copy.
   */
  note: string | null;
}
export interface ChangeWatchCode {
  state: "no_code" | "not_connected" | "unreadable" | "connected";
  /**
   * what to do first, or why nothing can come in here; null once connected
   */
  line: string | null;
  link: ItemLink | null;
  connected_line: string | null;
}
export interface ChangeWatchMenu {
  /**
   * "Bring in a demo change"
   */
  button: string;
  note: string;
  items: DemoChangeItem[];
}
export interface DemoChangeItem {
  key: string;
  title: string;
  what_it_does: string;
  can: boolean;
  blocked_reason: string | null;
}
export interface ChangeWatchView {
  plan_id: number;
  /**
   * "Change watch"
   */
  title: string;
  subline: string;
  code: ChangeWatchCode;
  menu: ChangeWatchMenu;
  /**
   * newest first; read from the connected repository on every ask
   */
  changes: ChangeRow[];
  empty: string | null;
  /**
   * a change's picked tests are running: ask again in a second
   */
  busy: boolean;
}
/**
 * The 5c fixes: one version a retest ran on, or one proof of a change, with the rows of its own runs.
 */
export interface CheckBlock {
  /**
   * "on-3" (the block retest 3 opened) or "proof-2".
   */
  key: string;
  /**
   * "acme-sign 1.4.3", or "acme-sign 1.4.3-otto (the changed code)".
   */
  title: string;
  line: string;
  /**
   * The newest block is open; older ones are folded.
   */
  newest: boolean;
  rows: CheckRow[];
}
export interface CheckRow {
  /**
   * "claim-3", "test-12", "retest-12", "proof-12", "try-<change>-try", "system-<key>", "library-<row>"
   */
  id: string;
  group: "verification" | "encryption" | "migration" | "dependencies";
  kind: string;
  name: string;
  ran_on: string;
  came_from: CameFrom;
  link: ItemLink1;
  evidence_link: ItemLink;
  state: "open" | "in_progress" | "done";
  /**
   * Set while it waits or runs.
   */
  status: RowStatus | null;
  /**
   * Its newest result, in the words of the page it came from.
   */
  result: CheckResult | null;
  plain: string | null;
  last_run_at: string | null;
  runs: number;
  /**
   * Phase 5b: the same measurement made elsewhere (decisions 3 and 4); each keeps its own run.
   */
  same_as?: SameMeasurement[];
  /**
   * Phase 5c: "From Otto" on an advisory check, with the way to its advisory.
   */
  from_otto?: CheckFromOtto | null;
  /**
   * The 5c fixes, in a retest's block: "tested again as it is" for a server, or a program the retest did not move.
   */
  mark?: string | null;
  /**
   * The 5c fixes: the older id of this row ("retest-12"), which still opens it while this is the newest block of its test.
   */
  alias?: string | null;
  /**
   * Where it came from (22 November 2026): what this rests on; null where nothing was observed or proven (a check not run yet, or that couldn't run).
   */
  source_tag?: Source | null;
}
/**
 * Open where it started.
 */
export interface ItemLink1 {
  /**
   * The page that holds the item, e.g. "evidence", "fixes", "migration/systems".
   */
  page: string;
  /**
   * The item to open there (a check, claim, fix, system or library id); null for the page.
   */
  item: string | null;
  section?: string | null;
  /**
   * The work group to filter the page to.
   */
  group?: string | null;
  /**
   * Another assessment (the Project overview links into each).
   */
  assessment_id?: number | null;
}
export interface CheckResult {
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  code: string;
}
export interface SameMeasurement {
  id: string;
  name: string;
  ran_on: string;
  group_label: string;
  link: ItemLink2;
  evidence_link: ItemLink;
}
/**
 * The other check on Checks.
 */
export interface ItemLink2 {
  /**
   * The page that holds the item, e.g. "evidence", "fixes", "migration/systems".
   */
  page: string;
  /**
   * The item to open there (a check, claim, fix, system or library id); null for the page.
   */
  item: string | null;
  section?: string | null;
  /**
   * The work group to filter the page to.
   */
  group?: string | null;
  /**
   * Another assessment (the Project overview links into each).
   */
  assessment_id?: number | null;
}
export interface CheckFromOtto {
  label: string;
  advisory: string;
  link: ItemLink;
}
export interface CheckDetail {
  check: CheckRow;
  /**
   * The newest run, worded as its page words it (null for a claim).
   */
  result: LabResult | null;
  /**
   * For a claim: its newest Verify result.
   */
  verify: Result | null;
  /**
   * Newest first.
   */
  runs: CheckRun[];
  related: RelatedLine[];
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
  /**
   * Sandbox research: the run was on a public copy sandbox research made.
   */
  sandbox_copy?: boolean;
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
  /**
   * Phase 5c, on a result of an advisory check only: where the check came from, the trial on public copies, the decisions on its proposal with who and when, and its Otto ledger entries. Records, never a result.
   */
  otto?: OttoResultBlock | null;
  /**
   * Where it came from (22 November 2026): what this rests on; null where nothing was observed or proven (a check not run yet, or that couldn't run).
   */
  source_tag?: Source | null;
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
  /**
   * Where it came from (22 November 2026): Observed live for a server, Proven in the lab for a signing program, From your file where it couldn't be checked.
   */
  source_tag?: Source | null;
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
export interface CheckRun {
  run_id: number | null;
  verify_run_id: number | null;
  at: string | null;
  came_from: string;
  label: string | null;
  tone: "pass" | "fail" | "neutral" | "warn";
  /**
   * The run record's SHA-256 (a Verify run has none).
   */
  fingerprint: string | null;
}
export interface RelatedLine {
  kind: "claim" | "test" | "fix" | "system" | "library" | "advisory";
  /**
   * "Claim", "Checks", "Fix", "System and track", "Library", "Advisory" (phase 5c)
   */
  title: string;
  items: RelatedItem[];
}
export interface RelatedItem {
  key: string;
  label: string;
  sub: string;
  link: ItemLink;
  also: ItemLink | null;
}
export interface CheckGroup {
  key: "verification" | "encryption" | "migration" | "dependencies";
  label: string;
  question: string;
  counts: StateCounts;
  /**
   * Set when the group has no rows: why it is empty.
   */
  empty_text: string | null;
  note: string | null;
  started_on: StartedOn;
  rows: CheckRow[];
  /**
   * 22 November 2026: how many of the group's items rest on each source (the Overview's line); the ones with none left out.
   */
  source_counts?: SourceCount[];
  /**
   * Checks of another group linked from this group's foot ("Also relates to this group").
   */
  also?: SameMeasurement[];
  /**
   * The 5c fixes: set on the Crypto tests group only.
   */
  parts?: EncryptionParts | null;
}
export interface StartedOn {
  label: string;
  page: string;
}
/**
 * The 5c fixes: Checks shows the Crypto tests group in four parts. A run shows in one part only.
 */
export interface EncryptionParts {
  plan: CheckPart;
  retests: CheckPart1;
  proofs: CheckPart1;
  /**
   * Only when a server change was tried on a test copy.
   */
  tries: CheckPart1 | null;
  /**
   * Phase 6d: only when the tests picked for a developer's change were run.
   */
  changes?: CheckPart1 | null;
}
/**
 * The test plan itself (drawn from the plan view); its heading names the version the file names.
 */
export interface CheckPart {
  key: "plan" | "retests" | "proofs" | "tries" | "changes";
  label: string;
  count: number;
  /**
   * "8 tests", "1 version", "2 proofs", "1 try".
   */
  count_label: string;
  note: string | null;
  /**
   * Set when the part has nothing yet: "No retest yet. ..."
   */
  empty_text: string | null;
  /**
   * Retests by version and Fix proofs: one block for each version, or each proof.
   */
  blocks: CheckBlock[];
  /**
   * Tries on a test copy: a plain list.
   */
  rows: CheckRow[];
}
/**
 * The 5c fixes: one labelled, foldable part of the Crypto tests group on Checks, with its count.
 */
export interface CheckPart1 {
  key: "plan" | "retests" | "proofs" | "tries" | "changes";
  label: string;
  count: number;
  /**
   * "8 tests", "1 version", "2 proofs", "1 try".
   */
  count_label: string;
  note: string | null;
  /**
   * Set when the part has nothing yet: "No retest yet. ..."
   */
  empty_text: string | null;
  /**
   * Retests by version and Fix proofs: one block for each version, or each proof.
   */
  blocks: CheckBlock[];
  /**
   * Tries on a test copy: a plain list.
   */
  rows: CheckRow[];
}
export interface ChecksView {
  plan_id: number;
  title: string;
  subline: string;
  /**
   * Always the four groups, in order.
   */
  groups: CheckGroup[];
  busy: boolean;
  came_from_options: CameFrom[];
  /**
   * For Evidence's Dependencies group: one row per library.
   */
  libraries: LibraryEvidenceRow[];
  evidence_counts: {
    [k: string]: StateCounts | undefined;
  };
}
export interface LibraryEvidenceRow {
  id: string;
  row_id: string;
  name: string;
  via_words: string;
  answers_short: string;
  blocks: DependencyBlock[];
  measured: boolean;
  state: "open" | "in_progress" | "done";
  /**
   * Where its answers came from (22 November 2026), taken together.
   */
  source_tag?: Source | null;
  /**
   * Each lookup's source, quoted line and date checked.
   */
  lookups?: DependencyLookup[];
  /**
   * Its answers as Dependencies words them.
   */
  cells?: DependencyCell[];
}
export interface DependencyBlock {
  system: string;
  track: "kex" | "auth" | "signatures";
  track_words: string;
  fix_id: string;
  /**
   * Phase 5b: the system the Blocks marker opens.
   */
  system_key?: string | null;
  /**
   * Phase 5b: "Blocks localhost:8443 · key exchange".
   */
  words?: string;
}
export interface DependencyLookup {
  question: "ml_kem_768" | "x25519mlkem768" | "ml_dsa_65";
  question_words: string;
  title: string;
  url: string;
  quote: string;
  checked: string;
  /**
   * the same source and quote as an earlier question of this row
   */
  repeat: boolean;
}
export interface DependencyCell {
  question: "ml_kem_768" | "x25519mlkem768" | "ml_dsa_65";
  answer: "yes" | "no" | "doesnt_apply" | "not_in_knowledge_base" | "couldnt_tell_version" | "needs_your_environment";
  answer_words: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  /**
   * exactly one label on a yes or a no; null on every other answer
   */
  label: ("release_notes" | "public_copy") | null;
  label_words: string | null;
  reason: string;
  /**
   * on a no: the first version that can, or "none_known"
   */
  first_version: string | null;
  first_version_words: string | null;
  state: "measured" | "not_measured" | "couldnt_check" | "couldnt_trust" | "not_offered";
  state_words: string;
  agreement: ("agrees" | "differs") | null;
  agreement_words: string | null;
  /**
   * Phase 5b: under a No, the reason in one line ("OpenSSL added this in 3.5.0; you have 3.0.22.").
   */
  no_reason?: string | null;
  /**
   * Where this answer came from (22 November 2026): Published (release notes), Proven in the lab (a public copy), or From your file (no answer yet).
   */
  source_tag?: Source | null;
}
export interface Compare {
  from_id: number;
  to_id: number;
  lists: CompareList[];
}
export interface CompareList {
  key: "new" | "gone" | "moved" | "single";
  title: string;
  items: CompareItem[];
}
export interface CompareItem {
  label: string;
  sub: string;
  link: ItemLink;
}
export interface ConfirmBody {
  address: string;
  confirmed: boolean;
}
export interface Created {
  id: number;
  /**
   * A new project's first assessment.
   */
  assessment_id?: number | null;
  /**
   * Phase 5b: Rerun as new assessment, the import's notices.
   */
  notices?: string[] | null;
}
export interface DecisionBody {
  reason?: string | null;
}
export interface DemoProjectsLoaded {
  added: string[];
  summary: string;
  notices: string[];
  open_assessment_id: number | null;
}
export interface DemoServer {
  address: string;
  running: boolean;
  error: string | null;
}
export interface DependenciesMeasureAll {
  /**
   * "Measure all"
   */
  label: string;
  enabled: boolean;
  blocked_reason: string | null;
}
export interface DependenciesUpload {
  /**
   * "Add dependency list"
   */
  label: string;
  note: string;
}
export interface DependenciesView {
  plan_id: number;
  import_id: number;
  is_demo: boolean;
  title: string;
  subline: string;
  disclaimer: string;
  /**
   * True while a measurement runs: ask again every second.
   */
  busy: boolean;
  questions: DependencyQuestion[];
  legend: DependencyLegendItem[];
  upload: DependenciesUpload;
  /**
   * The list in force: the newest one added. Null before the first.
   */
  list_file: DependencyListInfo | null;
  measure_all: DependenciesMeasureAll | null;
  systems: DependencySystem[];
  groups: DependencyGroup[];
  /**
   * Set when no list has been added yet.
   */
  empty_text: string | null;
}
export interface DependencyQuestion {
  key: "ml_kem_768" | "x25519mlkem768" | "ml_dsa_65";
  /**
   * "ML-KEM-768 key exchange"
   */
  title: string;
  /**
   * "Key exchange": the column heading
   */
  short: string;
}
export interface DependencyLegendItem {
  key: "release_notes" | "public_copy";
  /**
   * "Release notes say" | "Measured on a public copy"
   */
  words: string;
}
export interface DependencyListInfo {
  filename: string;
  /**
   * "CycloneDX 1.6" | "SPDX 2.3"
   */
  format: string;
  at: string;
  sha256: string;
  not_libraries_text: string | null;
}
export interface DependencySystem {
  key: string;
  name: string;
  kind_label: string;
  /**
   * the top entries of the list tied to it
   */
  tied_from: string;
  blocker_lines: DependencyBlockerLine[];
  without_answer: number;
  without_answer_text: string | null;
  environment_line: string;
  /**
   * Phase 5c: what a person accepted from Otto for a library of this system.
   */
  otto_lines?: string[];
}
export interface DependencyBlockerLine {
  text: string;
  /**
   * the Fixes entry it opens; null on the line that says nothing blocks
   */
  fix_id: string | null;
}
export interface DependencyGroup {
  key: string;
  label: string;
  tie_words: string;
  system: string | null;
  tie_source: ("user" | "name_version") | null;
  picker: DependencyPicker;
  /**
   * Set when the file lists no libraries under this entry.
   */
  empty_text: string | null;
  rows: DependencyRow[];
}
export interface DependencyPicker {
  /**
   * "Part of"
   */
  label: string;
  options: DependencyPickerOption[];
  selected: string;
}
export interface DependencyPickerOption {
  /**
   * "" is "None of these"
   */
  key: string;
  name: string;
}
export interface DependencyRow {
  id: string;
  label: string;
  /**
   * "direct" | "through python 3.12.3"
   */
  via_words: string;
  /**
   * the knowledge base's name for it; null when it is not in the knowledge base
   */
  library: string | null;
  /**
   * one per question, in the order of questions
   */
  cells: DependencyCell[];
  /**
   * Phase 5b: the answers in a few words, for the compact table ("No to all three").
   */
  answers_short?: string;
  /**
   * Where the library came from (22 November 2026): From your file (the list names it).
   */
  source_tag?: Source | null;
  blocks: DependencyBlock[];
  measure: DependencyMeasure;
  same_copy_note: string | null;
  lookups: DependencyLookup[];
  measurement: DependencyMeasurement | null;
  job: RowStatus | null;
  /**
   * Phase 5c: "Named by advisory X: ..." lines.
   */
  advisories?: DependencyAdvisory[];
  /**
   * Phase 5c: the proposals to change this library's status.
   */
  otto_proposals?: OttoProposal[];
  /**
   * Phase 5c: the status a person accepted.
   */
  otto_status?: DependencyOttoStatus | null;
  /**
   * Phase 4e: where this library is used.
   */
  impact?: Impact | null;
}
export interface DependencyMeasure {
  label: string;
  enabled: boolean;
  blocked_reason: string | null;
  busy: boolean;
}
export interface DependencyMeasurement {
  /**
   * the pinned public copy that was measured
   */
  copy_label: string;
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
  run_id: number;
  finished_at: string | null;
  /**
   * The reviewed run, worded: its locked test, raw record and review.
   */
  result: MeasurementResult | null;
  controls: string | null;
  controls_words: string;
}
export interface DependencyAdvisory {
  id: string;
  name: string;
  /**
   * "Named by advisory CVE-...: measured affected"
   */
  line: string;
  state: DependencyAdvisoryState;
  detail: string;
  fixed_line: string;
  advisory_link: ItemLink;
  evidence_link: ItemLink | null;
  fix_link: ItemLink | null;
  fix_label: string | null;
}
export interface DependencyAdvisoryState {
  key: "affected" | "not_affected" | "not_checked";
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
}
export interface DependencyOttoStatus {
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  lines: string[];
}
/**
 * Phase 4e: where the part a change touches is used. Read from the scanner files, the dependency lists and the
 * knowledge base; it decides nothing.
 */
export interface Impact {
  /**
   * "What this change touches" on a fix, "Where it is used" on a library.
   */
  title: string;
  /**
   * The part: "localhost:8443" | "acme-sign 1.4.2" | "openssl 3.0.22".
   */
  part: string;
  /**
   * Systems of this assessment it reaches, plus one for each other project that names it.
   */
  count: number;
  count_line: string;
  here: ImpactPart;
  elsewhere: ImpactPart;
  notes: string[];
  /**
   * "Can the parts that use it take 1.4.3?" with "Not known" and why.
   */
  compatible: ImpactLineText | null;
  /**
   * "Who can still connect": whether a client check applies, and where it is.
   */
  connect: ImpactLineText | null;
}
export interface ImpactPart {
  title: string;
  lines: ImpactLine[];
  /**
   * Said in place of the lines when there are none.
   */
  none: string | null;
}
export interface ImpactLine {
  /**
   * "acme-sign 1.4.2" | "Migration demo › Assessment 1"
   */
  text: string;
  /**
   * One plain sentence: what it is, and which rule matched it.
   */
  sub: string;
  /**
   * Where it came from: "from your file".
   */
  tag: string;
  /**
   * For another assessment: its status.
   */
  chip: ("Open" | "Closed") | null;
  link: ItemLink | null;
}
export interface ImpactLineText {
  title: string;
  text: string;
}
export interface DependencyMeasureBody {
  row?: string | null;
}
export interface DependencyTieBody {
  top: string;
  system?: string;
}
export interface DetailFact {
  label: string;
  value: RichPart[];
  /**
   * true: draw the value small, fixed-width, breaking anywhere
   */
  fingerprint: boolean;
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
export interface FixCameFrom {
  label: string;
  link: ItemLink;
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
  /**
   * Phase 5c: a library's fix from Otto: two rows in place of the Proof line.
   */
  proof_rows?: FixProofRow[] | null;
  /**
   * Phase 5c: a fix of Otto's is a proposal: its state, decisions and buttons.
   */
  proposal?: OttoProposal | null;
  /**
   * Phase 5b: the work group it came from.
   */
  group?: string;
  group_label?: string;
  /**
   * Phase 5b: where it came from, as links.
   */
  came_from_links?: FixCameFrom[];
  fix_state?: "open" | "in_progress" | "done";
  /**
   * Phase 6d: listed under its group's own heading for a developer's change and never counted with the findings.
   */
  apart?: boolean;
  /**
   * Phase 4e: what this change touches; null for Change watch's entry.
   */
  impact?: Impact | null;
  /**
   * 22 November 2026: where the finding this fix answers came from (Observed live, Proven in the lab or From your file); its proof lines carry their own.
   */
  source_tag?: Source | null;
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
  /**
   * 22 November 2026: Proven in the lab once a proof has passed or failed; null otherwise.
   */
  source_tag?: Source | null;
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
    | "mldsa_compare"
    | "advisory_cases";
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
/**
 * One of the two proof rows of a library's fix: "Proven on public copies" or "Proven in this assessment".
 */
export interface FixProofRow {
  key: "public" | "here";
  label: string;
  badge: FixDetailProofBadge1;
  text: string;
  /**
   * The row in one line, the same words wherever it is shown.
   */
  line: string;
  links: LabeledLink[];
  /**
   * The research ledger's entries behind the first row.
   */
  ledger: AdvisoryLedger | null;
  /**
   * Under the second row: what a retest here runs on (a public copy, not your system).
   */
  note?: string | null;
  /**
   * 22 November 2026: Proven in the lab (both rows are runs on public copies); null while the row reads Not yet.
   */
  source_tag?: Source | null;
}
/**
 * "Passed", "Not proven" or "Not yet"
 */
export interface FixDetailProofBadge1 {
  label: string;
  tone: "pass" | "fail" | "neutral" | "warn";
}
export interface FixGroup {
  key: "verification" | "encryption" | "migration" | "dependencies";
  label: string;
  question: string;
  counts: StateCounts1;
  fix_ids: string[];
  empty_text: string | null;
  /**
   * Phase 6d: the group's entries for a developer's change, under their own heading; None when there are none.
   */
  apart?: FixGroupApart | null;
  /**
   * "Also relates to this group": fixes listed in another group.
   */
  also: FixGroupAlso[];
}
/**
 * of fix_ids only: an entry listed apart is never counted
 */
export interface StateCounts1 {
  open: number;
  in_progress: number;
  done: number;
}
export interface FixGroupApart {
  /**
   * "From a developer's change"
   */
  label: string;
  note: string;
  fix_ids: string[];
}
export interface FixGroupAlso {
  fix_id: string;
  title: string;
  group_label: string;
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
   * "Open findings with a fix (2)": the entries that are not listed apart
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
  /**
   * Phase 5b: the four work groups, in order.
   */
  groups?: FixGroup[];
}
export interface FolderBody {
  name: string;
  parent_id?: number | null;
}
/**
 * Rename, move or archive. Only the fields sent change (move to the top level with parent_id null).
 */
export interface FolderChangeBody {
  name?: string | null;
  parent_id?: number | null;
  move?: boolean;
  archived?: boolean | null;
}
export interface Headline {
  claims: ClaimCounts | null;
  tests: TestCounts | null;
  fixes: FixCounts | null;
  systems: SystemCounts | null;
  blockers: number | null;
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
    | "mldsa_compare"
    | "advisory_cases";
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
export interface LiveOttoBody {
  on?: boolean | null;
  limit?: string | null;
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
  /**
   * Phase 5c: the mark of a proposal of Otto's for this system.
   */
  otto?: OttoRoadmapMark | null;
}
export interface OttoRoadmapMark {
  label: string;
  text: string;
  tone: "pass" | "fail" | "neutral" | "warn";
  waiting: number;
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
  /**
   * Phase 5c: Otto's proposed changes to this system's plan.
   */
  otto?: OttoPlanBlock | null;
  /**
   * Where its status came from (22 November 2026): Observed live for a server, Proven in the lab for a signing program, From your file before a measurement.
   */
  source_tag?: Source | null;
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
export interface OttoPlanBlock {
  title: string;
  note: string;
  proposals: OttoProposal[];
}
export interface MigrationTabs {
  systems: string;
  roadmap: string;
  /**
   * Phase 4d: the third view, the dependency list.
   */
  dependencies: string;
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
/**
 * Phase 5b: the New assessment box (and Rerun as new assessment). Every field may be left out.
 */
export interface NewAssessmentBody {
  name?: string | null;
  purpose?: string | null;
  reference?: string | null;
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
export interface OttoAnswersLine {
  /**
   * "Answers recorded during the build, 17 November 2026" or "Live: Claude, through your key"
   */
  line: string;
  live: boolean;
}
export interface OttoCheckButton {
  /**
   * "Check for updates"
   */
  button: string;
  note: string;
}
export interface OttoLiveLimit {
  label: string;
  /**
   * US dollars, e.g. "2.00"
   */
  value: string;
  save: string;
  note: string;
}
export interface OttoLiveSection {
  title: string;
  /**
   * Whether a key is set. The key itself is never sent to the screen.
   */
  key_present: boolean;
  key_line: string;
  switch: OttoLiveSwitch;
  limit: OttoLiveLimit;
  sent_line: string;
  status_line: string;
  price_line: string;
}
export interface OttoLiveSwitch {
  /**
   * "Use live Claude"
   */
  label: string;
  on: boolean;
  /**
   * Only when an API key is present on this computer.
   */
  can_turn_on: boolean;
  blocked_reason: string | null;
}
/**
 * Phase 6a: who a decision on a proposal is recorded as. A name typed once, or "You".
 */
export interface OttoName1 {
  /**
   * "Who decides"
   */
  title: string;
  /**
   * "Your name"
   */
  label: string;
  /**
   * The name a person typed; empty until then.
   */
  value: string;
  /**
   * The typed name, or "You".
   */
  recorded_as: string;
  typed: boolean;
  /**
   * "Recorded as You, with the time."
   */
  line: string;
  save: string;
  note: string;
  max: number;
  /**
   * The label of the field in the Otto panel's first Confirm step.
   */
  ask_label: string;
}
export interface OttoPackCard {
  version: string;
  built_at: string;
  /**
   * "17 November 2026"
   */
  built: string;
  signer: string;
  /**
   * Signed with a key made on this computer (a live research run).
   */
  made_here: boolean;
  advisories: number;
  tests: number;
  line: string;
  fingerprint: string;
  installed_at: string | null;
}
export interface OttoPacksSection {
  title: string;
  intro: string;
  /**
   * Oldest first. Packs are never removed.
   */
  installed: OttoPackCard[];
  installed_line: string;
  /**
   * Set when a pack installed by an earlier build can't be read by this version.
   */
  unreadable_line: string | null;
  counts_line: string | null;
  check: OttoCheckButton;
  /**
   * Set after Check for updates: what was found in the updates folder.
   */
  checked_line: string | null;
  refused: OttoRefusedPack[];
  /**
   * The pack that can be installed next, after Check for updates found one.
   */
  update: OttoUpdate | null;
  order_note: string;
}
export interface OttoRefusedPack {
  file: string;
  reason: string;
}
export interface OttoUpdate {
  version: string;
  /**
   * "Install update"
   */
  button: string;
  line: string;
  dialog: OttoUpdateDialog;
}
export interface OttoUpdateDialog {
  title: string;
  lines: string[];
  confirm: string;
  cancel: string;
}
export interface OttoProjectBlock {
  title: string;
  note: string;
  pack_line: string;
  since_title: string | null;
  rows: OttoProjectRow[];
}
export interface OttoProjectRow {
  assessment_id: number;
  title: string;
  waiting: number;
  waiting_text: string;
  link: ItemLink;
  since: string[];
}
export interface OttoProposalsView {
  plan_id: number;
  waiting: OttoWaiting;
  proposals: OttoProposal[];
  blocked_reason: string | null;
}
/**
 * Settings: Sandbox research (a prototype for Isogeny's own sandbox, 22 November 2026).
 */
export interface OttoSandboxSection {
  title: string;
  intro: string;
  switch: SandboxSwitch;
  box: SandboxBox;
  by_itself: SandboxTick;
  run_limit: SandboxLimit;
  day_limit: SandboxLimit;
  limits_note: string;
  status_line: string;
  /**
   * What research runs spent in the last 24 hours; only while the switch is on.
   */
  spent_line: string | null;
}
export interface SandboxSwitch {
  /**
   * "Sandbox research"
   */
  label: string;
  /**
   * On, and allowed to be on here.
   */
  on: boolean;
  can_turn_on: boolean;
  /**
   * Every plain reason it can't be turned on here; empty when it can.
   */
  blocked_reasons: string[];
}
/**
 * The box that opens before the switch is turned on. Nothing starts before the click in it.
 */
export interface SandboxBox {
  title: string;
  lines: string[];
  confirm: string;
  cancel: string;
}
export interface SandboxTick {
  /**
   * "Design and prove tests by itself"
   */
  label: string;
  on: boolean;
  can_turn_on: boolean;
  blocked_reason: string | null;
  line: string;
}
export interface SandboxLimit {
  label: string;
  /**
   * US dollars, e.g. "5.00"
   */
  value: string;
  save: string;
}
/**
 * Settings: the Test packs section, the two status lines and the Live Otto section (phase 5c).
 */
export interface OttoSettingsView {
  packs: OttoPacksSection;
  harness: OttoHarnessLine;
  answers: OttoAnswersLine;
  live: OttoLiveSection;
  /**
   * Phase 6a: always sent by the current backend.
   */
  name?: OttoName1 | null;
  /**
   * Sandbox research: always sent by the current backend.
   */
  sandbox?: OttoSandboxSection | null;
}
export interface PackInstallBody {
  version: string;
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
    | "mldsa_compare"
    | "advisory_cases";
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
  /**
   * Phase 5c, an advisory check only: the advisory it came from.
   */
  advisory?: CardAdvisory | null;
  /**
   * Phase 5c: "From Otto" on a check that came from an accepted proposal.
   */
  from_otto?: string | null;
  /**
   * Phase 5c: why this card has no remove button (it is undone on Advisories).
   */
  remove_blocked?: string | null;
  /**
   * 22 November 2026: where its result came from; null until it has one.
   */
  source_tag?: Source | null;
}
export interface ProjectBody {
  name: string;
  folder_id?: number | null;
}
export interface ProjectChangeBody {
  name?: string | null;
  folder_id?: number | null;
  move?: boolean;
  archived?: boolean | null;
}
export interface ProjectOverview {
  id: number;
  /**
   * Open assessments first, newest first.
   */
  rows: ProjectOverviewRow[];
  compare: Compare | null;
  shared: SharedSystem[];
  choices: SharedAssessment[];
  /**
   * Phase 5c: proposals waiting per assessment, and what changed since the newest pack.
   */
  otto?: OttoProjectBlock | null;
}
export interface ProjectOverviewRow {
  id: number;
  number: number;
  /**
   * "Assessment 2", or the name the person gave it
   */
  title: string;
  name: string | null;
  /**
   * Phase 5b: what it is for (a label only); null for one made before phase 5b.
   */
  purpose: Purpose | null;
  reference: string | null;
  status: AssessmentStatus;
  archived: boolean;
  created_at: string;
  closed_at: string | null;
  file: AssessmentFile | null;
  headline: Headline;
  has_results: boolean;
}
export interface SharedSystem {
  name: string;
  kind: "server" | "software";
  assessments: SharedAssessment[];
  note: string | null;
}
export interface SharedAssessment {
  id: number;
  title: string;
}
export interface ProjectView {
  id: number;
  name: string;
  folder_id: number | null;
  archived: boolean;
  is_demo: boolean;
  path: PathStep[];
  /**
   * Newest first.
   */
  assessments: AssessmentBrief[];
  /**
   * Phase 5b: the name the New assessment box starts with ("Assessment 3").
   */
  next_name: string;
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
export interface RelatedView {
  key: string;
  related: RelatedLine[];
}
export interface RetestBody {
  version: string;
  component?: string | null;
}
export interface SandboxBody {
  on?: boolean | null;
  by_itself?: boolean | null;
  run_limit?: string | null;
  day_limit?: string | null;
}
export interface SayBody {
  text: string;
  page: string;
  item?: string | null;
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
  /**
   * Phase 5c: one sentence. Verify is unchanged and nothing is proposed on it yet.
   */
  otto_note?: string;
}
export interface WatchAgain {
  /**
   * "Watch again"
   */
  label: string;
  can: boolean;
  blocked_reason: string | null;
}
export interface WatchAgainBody {
  item: string;
}
export interface WatchBox {
  title: string;
  lines: string[];
  confirm: string;
  cancel: string;
}
export interface WatchHistory {
  title: string;
  lines: string[];
}
export interface WatchItem {
  /**
   * The advisory's id and the library; what Stop watching and Watch again name.
   */
  key: string;
  id: string;
  title: string;
  library: string;
  /**
   * What it says about the version your files name.
   */
  yours: string;
  status: WatchStatus;
  status_line: string | null;
  since: string;
  /**
   * The newest look brought it, or changed it.
   */
  new: boolean;
  source: Source;
  panel: WatchPanel;
}
/**
 * Where a watched weakness stands. Information, never a result.
 */
export interface WatchStatus {
  key:
    | "no_fix"
    | "fix_published"
    | "being_tested"
    | "test_proposed"
    | "no_test"
    | "not_yours"
    | "withdrawn"
    | "gone"
    | "not_watched";
  /**
   * "No fix yet", "Fix published", "Being tested", "Test proposed", "No test possible", ...
   */
  word: string;
  /**
   * Only "warn" or "neutral": a status is not a result.
   */
  tone: "pass" | "fail" | "neutral" | "warn";
}
export interface WatchPanel {
  ids_line: string;
  published_line: string | null;
  quote: WatchQuote | null;
  versions: WatchVersions;
  test: WatchTest | null;
  history: WatchHistory;
  stop: WatchStop | null;
  watch: WatchAgain | null;
}
export interface WatchQuote {
  title: string;
  /**
   * Pieces of the publisher's own text, word for word.
   */
  lines: string[];
  /**
   * "quoted from the named source, not a result"
   */
  tag: string;
  source_line: string;
  url: string | null;
  link_label: string;
}
export interface WatchVersions {
  title: string;
  lines: string[];
  yours: string[];
}
export interface WatchTest {
  line: string | null;
  link: ItemLink | null;
  link_label: string | null;
}
export interface WatchStop {
  /**
   * "Stop watching"
   */
  label: string;
  reason_label: string;
  max: number;
  note: string;
  can: boolean;
  blocked_reason: string | null;
}
/**
 * Change watch, the Watch list: published weaknesses in the libraries a file names that have no fix yet. Worked
 * out from the assessment's own looks on every read. With Sandbox research off, `on` is false and nothing else is sent.
 */
export interface WatchListView {
  on: boolean;
  off_line: string | null;
  title: string;
  intro: string;
  looked_line: string | null;
  next_line: string | null;
  look: WatchLook | null;
  count_line: string | null;
  items: WatchItem[];
  /**
   * The ones a person stopped watching. Never deleted.
   */
  stopped: WatchItem[];
  empty_line: string | null;
  note: string | null;
}
export interface WatchLook {
  /**
   * "Look now"
   */
  button: string;
  can: boolean;
  blocked_reason: string | null;
  box: WatchBox1;
}
/**
 * Opens before anything is sent; says what is sent.
 */
export interface WatchBox1 {
  title: string;
  lines: string[];
  confirm: string;
  cancel: string;
}
export interface WatchStopBody {
  item: string;
  reason?: string | null;
}
export interface WhatIfTry1 {
  title: string;
  /**
   * "Retest new version": the button of Evidence it stands for.
   */
  button: string;
  offered: boolean;
  /**
   * Why it is not offered, in the page's own words where the page has them.
   */
  reason: string | null;
  component: string | null;
  version: string;
  /**
   * What a retest changes in this assessment, said before anything is pressed.
   */
  changes: string[];
}
export interface Workspace {
  organization: string;
  folders: WorkspaceFolder[];
  projects: WorkspaceProject[];
  /**
   * Phase 5b: the purposes an assessment can have, in order.
   */
  purposes: Purpose[];
  /**
   * Phase 5b: said in the Close box: who records the sign-off name.
   */
  one_login_line: string;
  /**
   * Phase 5b: plain name first, technical under it.
   */
  algorithm_names?: AlgorithmName[];
}
export interface WorkspaceFolder {
  id: number;
  name: string;
  parent_id: number | null;
  archived: boolean;
  /**
   * The folders above this one, top first.
   */
  path: PathStep[];
}
export interface WorkspaceProject {
  id: number;
  name: string;
  folder_id: number | null;
  archived: boolean;
  is_demo: boolean;
  created_at: string;
  path: PathStep[];
  assessments: number;
  /**
   * Phase 5b: open assessments (archived ones left out).
   */
  open_count: number;
  closed_count: number;
  /**
   * Phase 5b: the assessment worked on last.
   */
  latest: AssessmentBrief | null;
  counts: AssessmentCounts;
}
export interface App_Web_Otto__NameBody {
  name: string;
}
export interface App_Web_Projects__NameBody {
  name: string;
}
