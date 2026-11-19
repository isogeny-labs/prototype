"""The shapes of the data each screen receives.

This file is the one place these shapes are written (phase 4c+; they began as a copy of the types that were written
by hand in frontend/src/api.ts). Each route names its shape with `responses=shows(...)`; tools/api_schema.py puts
them in the API description and the frontend's types (frontend/src/api.gen.ts) are generated from that. Every JSON
answer a backend test gets is checked against them (tests/api_shapes.py). The routes do not use these models at
runtime: they keep returning plain dicts.

Conventions, matching TypeScript exactly:
  x: T          -> required, never null
  x: T | null   -> required key, may be null (no default)
  x?: T         -> key may be absent, never null when present (default None, type has no null)
  x?: T | null  -> key may be absent, may be null

Literal unions are plain module-level ``Literal`` aliases (pydantic has no named schema for a bare Literal;
the generator side names them). Object types written inline in api.ts get a small named helper class
(parent name + field name) so they can be described; the helpers are listed after "Helper classes" notes.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Shared helper for the many `{ url: string; filename: string }` objects.
class FileLink(Shape):
    url: str
    filename: str


# Shared helper for `{ label: string; value: RichText }[]` (facts).
class LabeledRichValue(Shape):
    label: str
    value: RichText


ClaimKind = Literal[
    "protocol_versions",
    "cipher_suites",
    "key_exchange",
    "certificate",
    "signature_algorithm",
    # Phase 4a: "classical", "hybrid" or "post-quantum only", checked with the migration measurement.
    "post_quantum",
]

LocationKind = Literal["server", "software", "unknown"]

ResultValue = Literal["True", "False", "Couldn't check"]


class DemoServer(Shape):
    address: str
    running: bool
    error: str | None


Mode = Literal["demo", "isolated"]


class Session(Shape):
    setup_required: bool
    logged_in: bool
    mode: Mode
    mode_line: str = Field(description="The sentence under the header saying how software is run, written by the backend.")
    demo_server: DemoServer


class Claim(Shape):
    id: int
    ref: str
    location: str
    location_kind: LocationKind
    kind: ClaimKind
    claimed_value: str
    text: str
    source: str


class Address(Shape):
    address: str
    host: str
    port: int
    resolved_ip: str | None
    is_loopback: bool
    confirmed: bool
    error: str | None


class SkippedItem(Shape):
    """Something in the file that this version doesn't check (for example a hash algorithm)."""

    name: str
    what: str
    source: str
    reason: str


class Import(Shape):
    id: int
    filename: str
    format: Literal["cyclonedx-cbom", "csv"]
    is_demo: bool
    claims: list[Claim]
    addresses: list[Address]
    skipped: list[SkippedItem] = Field(
        default=None,
        description="Always sent by the current backend; optional so an older reply doesn't break the screen.",
    )
    notices: list[str] = Field(
        default=None,
        description="Plain sentences about what the upload started on this computer (for example the demo test servers). Only on the upload reply.",
    )
    assessment_id: int | None = Field(default=None, description="Phase 5a: the assessment this import belongs to.")
    settings_title: str = Field(default=None, description='The heading of the settings list, e.g. "System settings from the file".')
    settings: list[ImportSetting] = Field(
        default=None,
        description="Settings rows the file carries (not claims: nothing checks them). Optional: older stored answers may lack it.",
    )
    otto: "ImportOtto | None" = Field(default=None, description='Phase 5c: "N checks may apply", marked From Otto. Nothing runs on import.')


class ImportSetting(Shape):
    """One settings row from the file, e.g. location "localhost:8451", text "Exposure: internet-facing. Data lifespan: long-lived." """

    location: str
    text: str


class Evidence(Shape):
    title: str
    command: str
    output: str
    started_at: str
    duration_ms: int
    tool: str
    tool_version: str


class Result(Shape):
    claim_id: int
    claim: Claim
    result: ResultValue
    found: str
    reason: str | None
    evidence: list[Evidence]
    summary: str = Field(description="One plain sentence: what was found and why that gives this result. Shown on top of the row.")
    also_noticed: list[str] = Field(
        description="Things the check saw that the file didn't ask about. Side notes, never a result. Often empty."
    )


class VerifyRun(Shape):
    id: int
    import_id: int
    started_at: str
    finished_at: str
    results: list[Result]
    otto_note: str = Field(default="", description="Phase 5c: one sentence. Verify is unchanged and nothing is proposed on it yet.")


# ---- Phase 2: test plan and Evidence Lab. All wording comes from the backend. ----

CatalogKind = Literal[
    "tls_versions",
    "certificate",
    "official_vectors",
    "bad_signatures",
    "speed_size",
    "pq_readiness",
    "mldsa_compare",
]
# Phase 5c: a test in a plan can also be an advisory check. It comes from a test pack and is never in the catalog.
TestKind = Literal[
    "tls_versions",
    "certificate",
    "official_vectors",
    "bad_signatures",
    "speed_size",
    "pq_readiness",
    "mldsa_compare",
    "advisory_cases",
]

ResultCode = Literal[
    "passed",
    "failed",
    "couldnt_run",
    "couldnt_trust",
    "measured",
    "no_slowdown",
    "slowdown",
    "offered",
    "not_offered",
]

Tone = Literal["pass", "fail", "neutral", "warn"]
JobStatus = Literal["not_run", "waiting", "running", "done"]


class RichPart(Shape):
    # "demo" is drawn as the violet "Demo data" label.
    t: Literal["text", "mono", "tag", "time", "demo"]
    v: str


RichText = list[RichPart]


class Progress(Shape):
    text: str
    percent: int | None


class Badge(Shape):
    code: ResultCode
    label: str
    tone: Tone


class TestCard(Shape):
    id: int
    kind: TestKind
    title: str
    origin: Literal["suggested", "added"]
    tag: str | None
    description: str
    why: str
    status: JobStatus
    status_text: str
    progress: Progress | None
    result: Badge | None
    can_run: bool
    can_remove: bool
    group: str | None = Field(description="The key of the group this card is under, when the plan is grouped.")
    advisory: CardAdvisory | None = Field(default=None, description="Phase 5c, an advisory check only: the advisory it came from.")
    from_otto: str | None = Field(default=None, description='Phase 5c: "From Otto" on a check that came from an accepted proposal.')
    remove_blocked: str | None = Field(default=None, description="Phase 5c: why this card has no remove button (it is undone on Advisories).")


class CardAdvisory(Shape):
    """On an advisory check's card: "From advisory CVE-...", with the link to it on the Advisories page."""

    label: str
    link: ItemLink


class PlanGroup(Shape):
    """A heading the cards (or Evidence Lab rows) are grouped under, e.g. "Server: localhost:8444"."""

    key: str
    kind: Literal["server", "software", "reference"]
    heading: str
    note: str | None


class NotTested(Shape):
    """The "Not tested, and why" box: every target or test the plan leaves out, one line each."""

    title: str
    items: list[str]


class CatalogItem(Shape):
    catalog_id: CatalogKind
    title: str
    tag: str | None
    description: str


class PlanView(Shape):
    id: int
    import_id: int
    is_demo: bool
    intro: str
    subject: RichText
    running: bool
    can_run_all: bool
    has_results: bool
    has_migration: bool = Field(description="A migration measurement exists for this plan (the Fixes step opens for it too).")
    max_parallel: int
    grouped: bool = Field(
        description="True when the file has more than one server or signing program: cards are drawn under group headings."
    )
    groups: list[PlanGroup] = Field(description="In display order. Sent even when not grouped (the screen then ignores them).")
    not_tested: NotTested | None
    tests: list[TestCard] = Field(description="When grouped, already ordered group by group, in the order of `groups`.")
    catalog_title: str
    catalog: list[CatalogItem]
    catalog_note: str


class MetaItem(Shape):
    label: str | None
    value: str
    tag: str | None
    time: str = None
    href: str = None


class TableColumn(Shape):
    label: str
    align: Literal["left", "right"]
    mono: bool = None


class EvidenceBlockTable(Shape):
    type: Literal["table"]
    title: str
    tag: str | None
    columns: list[TableColumn]
    rows: list[list[str]]
    meta: list[MetaItem]
    note: str | None


class EvidenceBlockText(Shape):
    type: Literal["text"]
    title: str
    tag: str | None
    text: str


EvidenceBlock = Annotated[Union[EvidenceBlockTable, EvidenceBlockText], Field(discriminator="type")]


class RunRecordOutput(Shape):
    title: str
    text: str


class RunRecordView(Shape):
    title: str
    command: str
    outputs: list[RunRecordOutput]
    meta: list[MetaItem]


class LockedTestField(Shape):
    label: str
    lines: list[str]


class LockedTestView(Shape):
    title: str
    fields: list[LockedTestField]
    locked_at: str
    locked_text: str
    fingerprint_label: str
    fingerprint: str
    note: str


class ResearchField(Shape):
    label: str
    value: str


class ResearchView(Shape):
    id: int
    title: str
    badge: str
    status: str
    status_line: str
    fields: list[ResearchField]
    saved_at: str
    note: str


class AdvisoriesItem(Shape):
    id: str
    text: str
    link: str
    href: str
    covered: str


class Advisories(Shape):
    """Published advisories for the tested version. Information from the advisory, never a result."""

    title: str
    tag: str
    items: list[AdvisoriesItem]


class LabResultControl(Shape):
    outcome: Literal["as_expected", "not_as_expected", "errored", "not_run"]
    line: str
    text: str


class LabResultReviewed(Shape):
    at: str
    text: str


class LabResult(Badge):
    run_id: int
    component: str | None
    mode: Mode
    finished_at: str
    duration_ms: int
    summary: str
    short: str
    plain: str = Field(description="One plain sentence: what was found and why that gives this result.")
    also_noticed: list[str] = Field(
        description="Side notes about things the test saw that it wasn't asked about. Never a result."
    )
    also_noticed_title: str
    control: LabResultControl
    what_happened: list[str]
    shows_title: str
    shows: list[str]
    evidence: list[EvidenceBlock]
    run_record: RunRecordView
    locked_test: LockedTestView
    real: bool = Field(description="True when the component is a real library, not one of our demo components (phase 4c).")
    fix_title: str
    suggested_fix: str | None
    fix_line: FixLine | None = Field(
        description='When set, suggested_fix is null and the "Suggested fix" box is not drawn.'
    )
    reviewed: LabResultReviewed | None
    research: ResearchView | None
    advisories: Advisories | None = Field(description="Phase 4c: advisories for this version (null for our own demo code).")
    otto: OttoResultBlock | None = Field(
        default=None,
        description="Phase 5c, on a result of an advisory check only: where the check came from, the trial on public copies, "
                    "the decisions on its proposal with who and when, and its Otto ledger entries. Records, never a result.",
    )



class MeasurementResult(LabResult):
    """A result as the Migration step and a change box's try show it: the same as a test's result, but its code can
    also be a measured post-quantum status (found by the phase 4c+ check of every answer against its shape)."""

    code: ResultCode | Literal["hybrid", "pq_only", "classical", "post_quantum"]
    fix_line: FixLine | None = Field(default=None, description="Not sent here: a measurement has no fix line.")

class RowStatus(Shape):
    status: JobStatus
    status_text: str
    progress: Progress | None


class LabRow(Shape):
    item_id: int
    kind: TestKind
    title: str
    control_line: str
    result: LabResult | None
    result_status: RowStatus | None
    after: LabResult | None
    after_status: RowStatus | None
    group: str | None


class RetestVersion(Shape):
    version: str
    component: str = Field(description="Which library this version belongs to (phase 4c).")
    label: str
    tag: str
    note: str


class LabViewColumns(Shape):
    test: str
    before: str
    after: str
    before_note: RichText = Field(description="The second line under each heading: which code that side ran on.")
    after_note: RichText
    before_heading: str = Field(description="The headings of the opened details.")
    after_heading: str


class LabViewRetest(Shape):
    can_start: bool
    blocked_reason: str | None
    running: bool
    progress_text: str | None
    menu_title: str
    versions: list[RetestVersion]
    menu_note: str


class LabViewDownload(Shape):
    can_start: bool
    blocked_reason: str | None


class LabView(Shape):
    plan_id: int
    is_demo: bool
    view: Literal["results", "before_after"]
    subline: RichText
    code_line: RichText | None = Field(description='"Code they ran on: before, ...; after, ..." (before/after view only).')
    disclaimer: str
    columns: LabViewColumns | None
    grouped: bool
    groups: list[PlanGroup]
    not_tested: NotTested | None
    rows: list[LabRow] = Field(description="When grouped, already ordered group by group, in the order of `groups`.")
    retest: LabViewRetest
    download: LabViewDownload
    busy: bool = Field(
        description="Something is running for this file (tests, a retest or a proof in Fixes): ask again in a second."
    )


class EvidenceExport(Shape):
    id: int
    created_at: str
    fingerprint: str
    fingerprint_label: str
    # "json" would shadow BaseModel.json, so the attribute is json_ and the key stays "json".
    json_: FileLink = Field(alias="json")
    html: FileLink
    message: str
    verify_hint: str


# ---- Phase 3a: the Fixes step. Everything a user reads is in here as text written by the backend. ----


class FixLine(Shape):
    """The one line on a failed result that has a fix in the Fixes step."""

    fix_id: str = Field(description='which fix "View in Fixes" opens')
    lead: str = Field(description='"Fix ready:"            (drawn bold)')
    rest: str = Field(description='"3 lines added and 1 removed, proof passed"')
    look: Literal["plain", "pass", "fail", "dashed"]
    busy: bool = Field(description="true while the proof runs: a small spinner before the words")
    button: str = Field(description='"View in Fixes"')
    rows: list[str] | None = Field(default=None, description="Phase 5c: a library's fix from Otto: its two proof rows, word for word as in Fixes.")


FixStatusKey = Literal[
    "not_connected",
    "proving",
    "ready",
    "failed",
    "waiting",
    "ready_to_merge",
    "merged",
    "text_only",
]


class FixStatus(Shape):
    key: FixStatusKey
    word: str = Field(description='"Ready for review"')
    busy: bool = Field(description="true while proving: the chip shows a spinner")


class StrongLabel(Shape):
    """"Before: " + strong + rest, e.g. lead "Before:", strong "acme-sign 1.4.2", rest ", nothing removed here"."""

    lead: str
    strong: str
    rest: str


class DiffLine(Shape):
    """One line of code in a before or after block. n is the line number in that version of the file."""

    n: int
    mark: Literal[" ", "-", "+"]
    text: str


class ChangePart(Shape):
    title: str = Field(description='"1. The check: reject a signature whose numbers are out of range"')
    why: str
    before_label: StrongLabel
    before: list[DiffLine]
    after_label: StrongLabel
    after: list[DiffLine]


class ProofCell(Shape):
    """A result badge and one line under it, as in Evidence Lab's before/after cells."""

    label: str
    tone: Tone
    short: str


class ProofWaiting(Shape):
    text: str = Field(description='"Running" or "Waiting"')
    detail: str | None = Field(description='"212 of 484 cases"')
    percent: int | None


class ProofRowCheck(Shape):
    ok: bool | None
    text: str


class ProofRow(Shape):
    kind: TestKind
    title: str
    before: ProofCell | None = Field(description="the first result this is compared with")
    proof: ProofCell | None = Field(description="null while this test has no proof result yet")
    waiting: ProofWaiting | None = Field(description="set while it is waiting or running")
    control: str = Field(description="the control line under the proof cell")
    check: ProofRowCheck = Field(description='"Passed", "No slowdown", "Same as before", "Did not pass", "Not finished yet"')


class ProofTable(Shape):
    heading: str = Field(description='"Tests that run the changed code"')
    tag: str = Field(description='"measured"')
    need: str
    columns: tuple[str, str, str, str] = Field(
        description='"Test", "Before: acme-sign 1.4.2", "On the changed code", "Rule check"'
    )
    rows: list[ProofRow]


class ProofVerdictCheck(Shape):
    ok: bool
    text: str


class ProofVerdict(Shape):
    tone: Literal["pass", "fail"]
    title: str = Field(description='"Why it is ready for review" | "Why this change is not offered"')
    checks: list[ProofVerdictCheck]
    shows_title: str | None = Field(description='"What this proof shows, and what it doesn\'t"')
    shows: list[str]


class DetailFact(Shape):
    label: str
    value: RichText
    fingerprint: bool = Field(description="true: draw the value small, fixed-width, breaking anywhere")


class RanOnFingerprint(Shape):
    label: str
    value: str
    tag: str


class RanOn(Shape):
    title: str = Field(description='"What the tests ran on"')
    text: RichText
    fingerprints: list[RanOnFingerprint]
    note: str


class TextSuggestionWarning(Shape):
    title: str
    text: str


class TextSuggestionWhereRow(Shape):
    place: str
    setting: str
    lead: str
    code: str


class TextSuggestionWhere(Shape):
    title: str
    note: str
    columns: tuple[str, str, str]
    rows: list[TextSuggestionWhereRow]
    after: list[str]


class TextSuggestionOption(Shape):
    title: str
    when: str
    steps: list[str]
    note: str


class TextSuggestionOptions(Shape):
    title: str
    items: list[TextSuggestionOption]


class TextSuggestionBlock(Shape):
    place: str
    code: str


class TextSuggestionExact(Shape):
    title: str
    note: str
    blocks: list[TextSuggestionBlock]


class TextSuggestion(Shape):
    """The fuller text-only suggestion. Words between backticks are names: fixed width, never broken across lines."""

    intro: list[str]
    warning: TextSuggestionWarning | None
    where: TextSuggestionWhere | None
    options: TextSuggestionOptions | None
    exact: TextSuggestionExact | None


class FixSectionChange(Shape):
    key: Literal["change"]
    title: str
    line: str
    open: bool
    intro: str
    parts: list[ChangePart]


class FixSectionProof(Shape):
    key: Literal["proof"]
    title: str
    line: str = Field(description="the one-line summary shown while folded")
    open: bool
    intro: str
    tables: list[ProofTable]
    verdict: ProofVerdict | None = Field(description="null while the proof runs")


class FixSectionDetails(Shape):
    key: Literal["details"]
    title: str
    line: str
    open: bool
    facts: list[DetailFact]
    note: str
    ran_on: RanOn | None


class FixSectionSuggestion(Shape):
    key: Literal["suggestion"]
    title: str
    line: str
    open: bool
    suggestion: TextSuggestion


FixSection = Annotated[
    Union[FixSectionChange, FixSectionProof, FixSectionDetails, FixSectionSuggestion],
    Field(discriminator="key"),
]


class ReviewerOption(Shape):
    id: str = Field(description='"you" | "a" | "b"')
    name: str = Field(description='"You" | "Demo reviewer A"')
    note: str | None = Field(description='"(the person logged in)"')
    demo: bool = Field(description="true: the Demo data label follows the name")
    checked: bool = Field(description="ticked by default")


class ApprovalRowView(Shape):
    id: str
    name: str
    note: str | None
    demo: bool
    approved_at: str | None = Field(description="ISO time, or null while waiting")
    approved_text: str | None = Field(description='"Approved"')
    approve_label: str | None = Field(
        description='"Approve" | "Approve as Demo reviewer A"; null once approved or after the merge'
    )
    primary: bool = Field(description='the "You" row\'s button is the primary look')


class FixApprovers(Shape):
    text: str | None = Field(description="a plain sentence, when there is nothing to pick or approve")
    options: list[ReviewerOption] | None = Field(description='the tick list (status "ready")')
    rows: list[ApprovalRowView] | None = Field(description="once a pull request exists")
    footnote: str | None = Field(description="the one-login sentence")


FixAction = Literal["connect", "run_proof_again", "open_pull_request", "merge", "download_patch", "retest_now"]


class FixButton(Shape):
    action: FixAction
    label: str
    primary: bool
    enabled: bool


class FixDetailWhat(Shape):
    label: str
    paragraphs: list[RichText]
    server_line: str | None


class FixDetailProofBadge(Shape):
    label: str
    tone: Tone


class FixDetailProof(Shape):
    state: Literal["none", "not_started", "running", "passed", "failed"]
    badge: FixDetailProofBadge | None
    text: str
    muted: str | None = Field(description='"Not offered yet."')


class FixDetailPullRequest(Shape):
    title: str
    text: RichText


class FixDetailActions(Shape):
    buttons: list[FixButton]
    note: str | None


class FixDetailMergeDialog(Shape):
    title: str
    paragraphs: list[RichText]
    confirm: str
    cancel: str


class FixDetail(Shape):
    id: str = Field(description='"fix-ecdsa-range-check" | "fix-tls-versions"')
    kind: Literal["code", "text"]
    title: str
    list_source: str = Field(description='in the list: "Came from 2 failed tests: Official test vectors, Bad signatures"')
    source: RichText = Field(
        description='in the summary: "Came from 2 failed tests on signing component acme-sign 1.4.2: ..."'
    )
    status: FixStatus
    labels: list[str] = Field(description='["From a fix template"] for a code fix, [] for a text one')
    is_demo: bool
    what: FixDetailWhat
    proof: FixDetailProof
    pull_request: FixDetailPullRequest | None
    approvers: FixApprovers
    actions: FixDetailActions
    patch: FileLink | None
    merge_dialog: FixDetailMergeDialog | None
    sections: list[FixSection]
    sections_note: str | None = Field(description="shown instead of sections before the code is connected")
    change_box: ChangeView | None = Field(description="Phase 4b: the change box, drawn first in the fix's detail.")
    advisories: Advisories | None = Field(description="Phase 4c: advisories for a text-only fix on a real library.")
    proof_rows: list["FixProofRow"] | None = Field(default=None, description="Phase 5c: a library's fix from Otto: two rows in place of the Proof line.")
    proposal: "OttoProposal | None" = Field(default=None, description="Phase 5c: a fix of Otto's is a proposal: its state, decisions and buttons.")
    group: str = Field(default="encryption", description="Phase 5b: the work group it came from.")
    group_label: str = ""
    came_from_links: list["FixCameFrom"] = Field(default_factory=list, description="Phase 5b: where it came from, as links.")
    fix_state: Literal["open", "in_progress", "done"] = "open"


class FixesView(Shape):
    plan_id: int
    is_demo: bool
    title: str = Field(description='"Fixes"')
    subline: str
    disclaimer: str
    list_title: str = Field(description='"Open findings with a fix (2)"')
    empty_text: str | None = Field(description="when no failed test has a fix: one plain sentence, and fixes is []")
    fixes: list[FixDetail] = Field(description="in list order; the list on the left is drawn from these too")
    busy: bool = Field(description="something is running: ask again in a second")
    groups: list["FixGroup"] = Field(default_factory=list, description="Phase 5b: the four work groups, in order.")


# ---- Phase 4a: the Migration step. The screen draws only what is sent; it decides no status, recommendation or wording. ----

MigrationStatusCode = Literal["hybrid", "pq_only", "classical", "couldnt_check", "not_measured"]
# Phase 4b: a track's status adds "post_quantum" (a post-quantum signature or certificate).
TrackStatusCode = Literal["hybrid", "pq_only", "classical", "couldnt_check", "not_measured", "post_quantum"]
MigrationOptionKey = Literal["keep", "hybrid", "full_pq", "wrap"]


class MigrationStatus(Shape):
    """The status pill. Its look is picked by code; the words are the label."""

    code: MigrationStatusCode
    label: str


class MigrationLine(Shape):
    """A sentence that may be followed by "View in Fixes" (when fix_id is set)."""

    text: RichText
    fix_id: str | None


class MigrationSettingOption(Shape):
    value: str
    label: str


class MigrationSettingField(Shape):
    field: Literal["lifespan", "exposure", "can_change"]
    label: str
    help: str = Field(description="The small grey question under the control.")
    value: str
    options: list[MigrationSettingOption]
    source: str = Field(description='"from the file" | "assumed" | "set by you": a small tag beside the control.')
    enabled: bool = Field(description="False while a measurement runs.")


class MigrationCostRow(Shape):
    label: str
    cells: list[RichText]


class MigrationCostTable(Shape):
    title: str
    intro: str
    columns: list[str] = Field(description="The first is the row label column.")
    rows: list[MigrationCostRow] = Field(description="One cell per column after the first.")
    note: str | None


class MigrationReviewDate(Shape):
    label: str
    value: str
    min: str
    max: str
    help: str


class MigrationChooseBox(Shape):
    title: str
    needs_reason: bool = Field(description="True: Save stays disabled until the reason has text.")
    reason_label: str
    review_date: MigrationReviewDate | None = Field(description='ISO dates (YYYY-MM-DD); only for "keep".')
    save: str
    cancel: str
    note: str


class MigrationOptionSection(Shape):
    title: str
    lines: list[MigrationLine]


class MigrationOption(Shape):
    key: MigrationOptionKey
    title: str
    tags: list[str]
    highlighted: bool = Field(description="The sky border (the recommended or chosen one).")
    what: str
    sections: list[MigrationOptionSection]
    not_offered: str | None = Field(description="When set: no Choose button, this sentence instead.")
    choose_label: str
    choose: MigrationChooseBox | None = Field(description='The box that opens in the card when "Choose this option" is pressed.')


class MigrationSystemToday(Shape):
    title: str
    sentence: str
    file_note: str | None
    facts: list[LabeledRichValue]
    control_line: str | None
    details_label: str
    result: MeasurementResult | None = Field(description="Drawn with ResultDetail inside a closed disclosure.")


class MigrationSystemSettings(Shape):
    title: str
    intro: str
    fields: list[MigrationSettingField]


class MigrationSystemRecommendation(Shape):
    title: str
    tag: str | None
    reasons: list[RichText]
    evidence: RichText | None
    evidence_link: str | None = Field(description='"See the evidence": opens the details disclosure above and scrolls to it.')
    none_text: str | None = Field(description="Shown instead of reasons when there is no recommendation.")


class MigrationSystemChoice(Shape):
    line: str
    history: list[str]


class TrackStatus(Shape):
    code: TrackStatusCode
    label: str


class MigrationTrackBrief(Shape):
    title: str
    status: TrackStatus


class MigrationSystem(Shape):
    key: str
    kind_label: str
    name: str
    status: MigrationStatus
    plan_line: str
    measuring: RowStatus | None = Field(
        description="Set while this system's measurement waits or runs (drawn in place of Today's sentence)."
    )
    today: MigrationSystemToday
    settings: MigrationSystemSettings
    cost: MigrationCostTable | None
    recommendation: MigrationSystemRecommendation
    options_title: str
    options: list[MigrationOption] = Field(
        description="In the order keep, hybrid, full_pq, wrap. Empty when there is no status."
    )
    choice: MigrationSystemChoice | None = Field(
        description="The user's saved choice (history: older choices, newest first)."
    )
    choices_note: str

    # ---- Phase 4b. Older answers lack these: draw them as empty. ----
    tracks: list[MigrationTrack] = None
    tracks_brief: list[MigrationTrackBrief] = None
    target_line: str = None
    also_noticed_title: str = None
    also_noticed: list[str] = None
    change: ChangeView | None = None
    otto: "OttoPlanBlock | None" = Field(default=None, description="Phase 5c: Otto's proposed changes to this system's plan.")


TrackKey = Literal["kex", "auth", "signatures"]


class MigrationTrack(Shape):
    key: TrackKey
    title: str
    short_title: str
    status: TrackStatus
    sentence: str
    facts: list[LabeledRichValue]
    next: RichText
    why: RichText
    next_label: str
    why_label: str


# ---- Phase 4b: the change box (Migration and Fixes) ----

ChangeAction = Literal["try", "ask_approval", "approve", "apply", "rollback", "download"]


class ChangeButton(Shape):
    action: ChangeAction
    label: str
    primary: bool
    enabled: bool
    reason: str | None


class ChangeStep(Shape):
    key: Literal["built", "tried", "approvals", "applied", "measured"]
    label: str
    state: Literal["done", "now", "off", "failed"]
    text: str


class ChangeSectionTable(Shape):
    kind: Literal["table"]
    title: str
    columns: list[str]
    rows: list[list[RichText]]


class ChangeSectionLine(Shape):
    place: str
    lead: str
    code: str


class ChangeSectionLines(Shape):
    kind: Literal["lines"]
    title: str
    rows: list[ChangeSectionLine]
    note: str | None


class ChangeSectionText(Shape):
    kind: Literal["text"]
    title: str
    paragraphs: list[RichText]


ChangeSection = Annotated[
    Union[ChangeSectionTable, ChangeSectionLines, ChangeSectionText],
    Field(discriminator="kind"),
]


class ChangeBadge(Shape):
    label: str
    look: Literal["pass", "fail", "warn", "neutral"]


class TryViewVerdict(Shape):
    label: str
    look: Literal["pass", "fail", "warn"]
    text: str


class TryViewRow(Shape):
    label: str
    cells: list[RichText]


class TryViewResult(Shape):
    label: str
    result: MeasurementResult


class TryView(Shape):
    title: str
    running: RowStatus | None
    verdict: TryViewVerdict | None
    columns: list[str]
    rows: list[TryViewRow]
    notes: list[str]
    results: list[TryViewResult]


class ApprovalsPickerOption(Shape):
    id: str
    name: str
    demo: bool
    checked: bool


class ApprovalsPicker(Shape):
    options: list[ApprovalsPickerOption]
    button: str
    enabled: bool
    reason: str | None


class ApprovalsRowApprove(Shape):
    label: str
    enabled: bool


class ApprovalsRow(Shape):
    reviewer: str
    name: str
    demo: bool
    approved_at: str | None
    status_text: str
    approve: ApprovalsRowApprove | None


class ApprovalsView(Shape):
    title: str
    picker: ApprovalsPicker | None
    rows: list[ApprovalsRow]
    footnote: str


class ApplyView(Shape):
    title: str
    badge: ChangeBadge
    paragraphs: list[RichText]
    differences: list[str]
    history: list[str]


class ChangeView(Shape):
    id: str = Field(description='The key to send back, e.g. "migration:server:localhost:8452".')
    title: str
    badge: ChangeBadge
    intro: RichText
    steps: list[ChangeStep]
    sections: list[ChangeSection]
    # "try" is a Python keyword, so the attribute is try_ and the key stays "try".
    try_: TryView | None = Field(alias="try")
    approvals: ApprovalsView | None
    applied: ApplyView | None
    buttons: list[ChangeButton]
    note: str | None
    busy: bool


class MigrationRoadmapRow(Shape):
    system_key: str
    kind_label: str
    name: str
    option: str
    plan_tag: str | None
    note: MigrationLine
    track: str = Field(
        default=None, description='Phase 4b: "Key exchange" | "Authentication" | "Signatures" | "Both tracks".'
    )
    otto: "OttoRoadmapMark | None" = Field(default=None, description="Phase 5c: the mark of a proposal of Otto's for this system.")


class MigrationRoadmapBand(Shape):
    key: str
    title: str
    sub: str
    look: Literal["plain", "highlight", "dashed"]
    rows: list[MigrationRoadmapRow]


class MigrationMeasure(Shape):
    label: str
    enabled: bool
    blocked_reason: str | None
    progress_text: str | None


class MigrationTabs(Shape):
    systems: str
    roadmap: str
    dependencies: str = Field(description="Phase 4d: the third view, the dependency list.")


class MigrationRoadmapDownload(Shape):
    label: str
    can_start: bool
    blocked_reason: str | None


class MigrationRoadmap(Shape):
    intro: str
    download: MigrationRoadmapDownload = Field(description="The same evidence download as Evidence Lab's button.")
    bands: list[MigrationRoadmapBand] = Field(description="Empty bands are not sent.")


class MigrationView(Shape):
    plan_id: int
    import_id: int
    is_demo: bool
    title: str
    subline: RichText
    disclaimer: str
    busy: bool = Field(description="True while measuring: ask again every second.")
    measure: MigrationMeasure
    tabs: MigrationTabs
    list_title: str
    empty_text: str | None = Field(description="Set when the file names no server and no signing program.")
    systems: list[MigrationSystem]
    roadmap: MigrationRoadmap


# ---- Phase 4d: the Dependencies view (a third tab of the Migration step). Every word comes from the backend; the screen
# decides no answer, label, tie or blocker. ----

DependencyQuestionKey = Literal["ml_kem_768", "x25519mlkem768", "ml_dsa_65"]
DependencyAnswer = Literal["yes", "no", "doesnt_apply", "not_in_knowledge_base", "couldnt_tell_version", "needs_your_environment"]
# "your_environment" is in the legend's vocabulary for later (Level 3) and is never sent in this version.
DependencyLabel = Literal["release_notes", "public_copy"]
DependencyState = Literal["measured", "not_measured", "couldnt_check", "couldnt_trust", "not_offered"]
DependencyTrack = Literal["kex", "auth", "signatures"]


class DependencyQuestion(Shape):
    key: DependencyQuestionKey
    title: str = Field(description='"ML-KEM-768 key exchange"')
    short: str = Field(description='"Key exchange": the column heading')


class DependencyLegendItem(Shape):
    key: DependencyLabel
    words: str = Field(description='"Release notes say" | "Measured on a public copy"')


class DependenciesUpload(Shape):
    label: str = Field(description='"Add dependency list"')
    note: str


class DependencyListInfo(Shape):
    filename: str
    format: str = Field(description='"CycloneDX 1.6" | "SPDX 2.3"')
    at: str
    sha256: str
    not_libraries_text: str | None


class DependenciesMeasureAll(Shape):
    label: str = Field(description='"Measure all"')
    enabled: bool
    blocked_reason: str | None


class DependencyBlockerLine(Shape):
    text: str
    fix_id: str | None = Field(description="the Fixes entry it opens; null on the line that says nothing blocks")


class DependencySystem(Shape):
    key: str
    name: str
    kind_label: str
    tied_from: str = Field(description="the top entries of the list tied to it")
    blocker_lines: list[DependencyBlockerLine]
    without_answer: int
    without_answer_text: str | None
    environment_line: str
    otto_lines: list[str] = Field(default_factory=list, description="Phase 5c: what a person accepted from Otto for a library of this system.")


class DependencyPickerOption(Shape):
    key: str = Field(description='"" is "None of these"')
    name: str


class DependencyPicker(Shape):
    label: str = Field(description='"Part of"')
    options: list[DependencyPickerOption]
    selected: str


class DependencyCell(Shape):
    question: DependencyQuestionKey
    answer: DependencyAnswer
    answer_words: str
    tone: Tone
    label: DependencyLabel | None = Field(description="exactly one label on a yes or a no; null on every other answer")
    label_words: str | None
    reason: str
    first_version: str | None = Field(description='on a no: the first version that can, or "none_known"')
    first_version_words: str | None
    state: DependencyState
    state_words: str
    agreement: Literal["agrees", "differs"] | None
    agreement_words: str | None
    no_reason: str | None = Field(default=None, description='Phase 5b: under a No, the reason in one line ("OpenSSL added this in 3.5.0; you have 3.0.22.").')


class DependencyBlock(Shape):
    system: str
    track: DependencyTrack
    track_words: str
    fix_id: str
    system_key: str | None = Field(default=None, description="Phase 5b: the system the Blocks marker opens.")
    words: str = Field(default="", description='Phase 5b: "Blocks localhost:8443 · key exchange".')


class DependencyMeasure(Shape):
    label: str
    enabled: bool
    blocked_reason: str | None
    busy: bool


class DependencyLookup(Shape):
    question: DependencyQuestionKey
    question_words: str
    title: str
    url: str
    quote: str
    checked: str
    repeat: bool = Field(description="the same source and quote as an earlier question of this row")


class DependencyMeasurement(Shape):
    copy_label: str = Field(description="the pinned public copy that was measured")
    code: ResultCode
    run_id: int
    finished_at: str | None
    result: MeasurementResult | None = Field(description="The reviewed run, worded: its locked test, raw record and review.")
    controls: str | None
    controls_words: str


class DependencyRow(Shape):
    id: str
    label: str
    via_words: str = Field(description='"direct" | "through python 3.12.3"')
    library: str | None = Field(description="the knowledge base's name for it; null when it is not in the knowledge base")
    cells: list[DependencyCell] = Field(description="one per question, in the order of questions")
    answers_short: str = Field(default="", description='Phase 5b: the answers in a few words, for the compact table ("No to all three").')
    blocks: list[DependencyBlock]
    measure: DependencyMeasure
    same_copy_note: str | None
    lookups: list[DependencyLookup]
    measurement: DependencyMeasurement | None
    job: RowStatus | None
    advisories: list["DependencyAdvisory"] = Field(default_factory=list, description='Phase 5c: "Named by advisory X: ..." lines.')
    otto_proposals: list["OttoProposal"] = Field(default_factory=list, description="Phase 5c: the proposals to change this library's status.")
    otto_status: "DependencyOttoStatus | None" = Field(default=None, description="Phase 5c: the status a person accepted.")


class DependencyGroup(Shape):
    key: str
    label: str
    tie_words: str
    system: str | None
    tie_source: Literal["user", "name_version"] | None
    picker: DependencyPicker
    empty_text: str | None = Field(description="Set when the file lists no libraries under this entry.")
    rows: list[DependencyRow]


class DependenciesView(Shape):
    plan_id: int
    import_id: int
    is_demo: bool
    title: str
    subline: str
    disclaimer: str
    busy: bool = Field(description="True while a measurement runs: ask again every second.")
    questions: list[DependencyQuestion]
    legend: list[DependencyLegendItem]
    upload: DependenciesUpload
    list_file: DependencyListInfo | None = Field(description="The list in force: the newest one added. Null before the first.")
    measure_all: DependenciesMeasureAll | None
    systems: list[DependencySystem]
    groups: list[DependencyGroup]
    empty_text: str | None = Field(description="Set when no list has been added yet.")


# ---- Not in api.ts as a named type: the `{ ok: true }` answer of the POST routes that return nothing else. ----


class Ok(Shape):
    ok: Literal[True]


# ---- Phase 5a: folders, projects and assessments. Every count is read from the views the pages draw; null = not yet. ----

class ClaimCounts(Shape):
    checked: int
    false: int
    true: int
    couldnt_check: int


class TestCounts(Shape):
    run: int
    failed: int
    passed: int


class FixCounts(Shape):
    total: int
    open: int


class SystemCounts(Shape):
    total: int
    classical: int
    hybrid: int
    pq_only: int
    couldnt_check: int
    not_measured: int


class AssessmentCounts(Shape):
    claims: ClaimCounts | None
    tests: TestCounts | None
    fixes: FixCounts | None
    systems: SystemCounts | None


class Signoff(Shape):
    by: str = Field(description="The name typed when it was closed (the app has one login).")
    note: str | None
    at: str


class AssessmentStatus(Shape):
    key: Literal["open", "closed"]
    label: str
    closed_line: str | None = Field(description="Why it is closed, then the closed sentence; null when open.")
    signoff: Signoff | None = Field(description="Phase 5b: who signed it off and when; null when open or closed by the earlier rule.")


class Purpose(Shape):
    key: str
    label: str


class AssessmentFile(Shape):
    import_id: int
    filename: str
    format: str
    is_demo: bool
    imported_at: str


class AssessmentBrief(Shape):
    id: int
    number: int
    title: str = Field(description='"Assessment 2", or the name the person gave it')
    name: str | None
    purpose: Purpose | None = Field(description="Phase 5b: what it is for (a label only); null for one made before phase 5b.")
    reference: str | None
    status: AssessmentStatus
    archived: bool
    created_at: str
    closed_at: str | None
    file: AssessmentFile | None


class PathStep(Shape):
    id: int
    name: str


class WorkspaceFolder(Shape):
    id: int
    name: str
    parent_id: int | None
    archived: bool
    path: list[PathStep] = Field(description="The folders above this one, top first.")


class WorkspaceProject(Shape):
    id: int
    name: str
    folder_id: int | None
    archived: bool
    is_demo: bool
    created_at: str
    path: list[PathStep]
    assessments: int
    open_count: int = Field(description="Phase 5b: open assessments (archived ones left out).")
    closed_count: int
    latest: AssessmentBrief | None = Field(description="Phase 5b: the assessment worked on last.")
    counts: AssessmentCounts


class Workspace(Shape):
    organization: str
    folders: list[WorkspaceFolder]
    projects: list[WorkspaceProject]
    purposes: list[Purpose] = Field(description="Phase 5b: the purposes an assessment can have, in order.")
    one_login_line: str = Field(description="Phase 5b: said in the Close box: who records the sign-off name.")
    algorithm_names: list["AlgorithmName"] = Field(default_factory=list, description="Phase 5b: plain name first, technical under it.")


class AlgorithmName(Shape):
    technical: str
    plain: str


class Created(Shape):
    id: int
    assessment_id: int | None = Field(default=None, description="A new project's first assessment.")
    notices: list[str] | None = Field(default=None, description="Phase 5b: Rerun as new assessment, the import's notices.")


class ProjectView(Shape):
    id: int
    name: str
    folder_id: int | None
    archived: bool
    is_demo: bool
    path: list[PathStep]
    assessments: list[AssessmentBrief] = Field(description="Newest first.")
    next_name: str = Field(description='Phase 5b: the name the New assessment box starts with ("Assessment 3").')


class AssessmentProject(Shape):
    id: int
    name: str
    is_demo: bool
    archived: bool


class NextStep(Shape):
    page: str = Field(description='The page that holds the next thing to do, e.g. "inventory/import", "tests".')
    label: str
    text: str


class AssessmentView(AssessmentBrief):
    organization: str
    project: AssessmentProject
    path: list[PathStep]
    import_: Import | None = Field(alias="imp" "ort")   # written in two parts: tests/test_prepare.py scans for the bare word
    plan_id: int | None
    has_verify: bool
    has_results: bool
    has_migration: bool
    counts: AssessmentCounts
    next_step: NextStep
    blocks: "OverviewBlocks | None" = Field(default=None, description="Phase 5b: the Overview's blocks (null before a file).")
    waiting: "OttoWaiting | None" = Field(default=None, description='Phase 5c: "Waiting for you": the proposals nobody has decided yet.')


# ---- Phase 5b: one connected assessment. Every word comes from the page each item lives on. ----

GroupKey = Literal["verification", "encryption", "migration", "dependencies"]
ItemState = Literal["open", "in_progress", "done"]


class ItemLink(Shape):
    page: str = Field(description='The page that holds the item, e.g. "evidence", "fixes", "migration/systems".')
    item: str | None = Field(description="The item to open there (a check, claim, fix, system or library id); null for the page.")
    section: str | None = None
    group: str | None = Field(default=None, description="The work group to filter the page to.")
    assessment_id: int | None = Field(default=None, description="Another assessment (the Project overview links into each).")


class OverviewFact(Shape):
    label: str
    value: int
    link: ItemLink


class OverviewGroup(Shape):
    key: GroupKey
    label: str
    question: str
    checks: StateCounts | None
    fixes: StateCounts | None
    facts: list[OverviewFact]
    empty_text: str | None


class LastDownload(Shape):
    at: str
    fingerprint: str


class OverviewEvidence(Shape):
    runs: int
    last_download: LastDownload | None


class OverviewBlocks(Shape):
    groups: list[OverviewGroup]
    findings: list[OverviewFact] = Field(description="False claims, failed tests, dependency blockers: each its own count.")
    evidence: OverviewEvidence


class Headline(AssessmentCounts):
    blockers: int | None


class ProjectOverviewRow(AssessmentBrief):
    headline: Headline
    has_results: bool


class CompareItem(Shape):
    label: str
    sub: str
    link: ItemLink


class CompareList(Shape):
    key: Literal["new", "gone", "moved", "single"]
    title: str
    items: list[CompareItem]


class Compare(Shape):
    from_id: int
    to_id: int
    lists: list[CompareList]


class SharedAssessment(Shape):
    id: int
    title: str


class SharedSystem(Shape):
    name: str
    kind: Literal["server", "software"]
    assessments: list[SharedAssessment]
    note: str | None


class ProjectOverview(Shape):
    id: int
    rows: list[ProjectOverviewRow] = Field(description="Open assessments first, newest first.")
    compare: Compare | None
    shared: list[SharedSystem]
    choices: list[SharedAssessment]
    otto: "OttoProjectBlock | None" = Field(default=None, description="Phase 5c: proposals waiting per assessment, and what changed since the newest pack.")


class StateCounts(Shape):
    open: int
    in_progress: int
    done: int


class CameFrom(Shape):
    key: str
    label: str = Field(description='"Verify", "Test plan", "Retest", "Fix proof", "Try on a test copy", "After Apply", ...')


class CheckResult(Shape):
    label: str
    tone: Tone
    code: str


class SameMeasurement(Shape):
    id: str
    name: str
    ran_on: str
    group_label: str
    link: ItemLink = Field(description="The other check on Checks.")
    evidence_link: ItemLink


class CheckRow(Shape):
    id: str = Field(description='"claim-3", "test-12", "retest-12", "proof-12", "try-<change>-try", "system-<key>", "library-<row>"')
    group: GroupKey
    kind: str
    name: str
    ran_on: str
    came_from: CameFrom
    link: ItemLink = Field(description="Open where it started.")
    evidence_link: ItemLink
    state: ItemState
    status: RowStatus | None = Field(description="Set while it waits or runs.")
    result: CheckResult | None = Field(description="Its newest result, in the words of the page it came from.")
    plain: str | None
    last_run_at: str | None
    runs: int
    same_as: list[SameMeasurement] = Field(default_factory=list,
                                           description="Phase 5b: the same measurement made elsewhere (decisions 3 and 4); each keeps its own run.")
    from_otto: "CheckFromOtto | None" = Field(default=None, description='Phase 5c: "From Otto" on an advisory check, with the way to its advisory.')
    mark: str | None = Field(default=None, description='The 5c fixes, in a retest\'s block: "tested again as it is" for a server, or a '
                                                       "program the retest did not move.")
    alias: str | None = Field(default=None, description='The 5c fixes: the older id of this row ("retest-12"), which still opens it '
                                                        "while this is the newest block of its test.")


class StartedOn(Shape):
    label: str
    page: str


class CheckBlock(Shape):
    """The 5c fixes: one version a retest ran on, or one proof of a change, with the rows of its own runs."""
    key: str = Field(description='"on-3" (the block retest 3 opened) or "proof-2".')
    title: str = Field(description='"acme-sign 1.4.3", or "acme-sign 1.4.3-otto (the changed code)".')
    line: str
    newest: bool = Field(description="The newest block is open; older ones are folded.")
    rows: list[CheckRow]


class CheckPart(Shape):
    """The 5c fixes: one labelled, foldable part of the Encryption tests group on Checks, with its count."""
    key: Literal["plan", "retests", "proofs", "tries"]
    label: str
    count: int
    count_label: str = Field(description='"8 tests", "1 version", "2 proofs", "1 try".')
    note: str | None
    empty_text: str | None = Field(description='Set when the part has nothing yet: "No retest yet. ..."')
    blocks: list[CheckBlock] = Field(description="Retests by version and Fix proofs: one block for each version, or each proof.")
    rows: list[CheckRow] = Field(description="Tries on a test copy: a plain list.")


class EncryptionParts(Shape):
    """The 5c fixes: Checks shows the Encryption tests group in four parts. A run shows in one part only."""
    plan: CheckPart = Field(description="The test plan itself (drawn from the plan view); its heading names the version the file names.")
    retests: CheckPart
    proofs: CheckPart
    tries: CheckPart | None = Field(description="Only when a server change was tried on a test copy.")


class CheckGroup(Shape):
    key: GroupKey
    label: str
    question: str
    counts: StateCounts
    empty_text: str | None = Field(description="Set when the group has no rows: why it is empty.")
    note: str | None
    started_on: StartedOn
    rows: list[CheckRow]
    also: list[SameMeasurement] = Field(default_factory=list,
                                        description="Checks of another group linked from this group's foot (\"Also relates to this group\").")
    parts: "EncryptionParts | None" = Field(default=None, description="The 5c fixes: set on the Encryption tests group only.")


class LibraryEvidenceRow(Shape):
    id: str
    row_id: str
    name: str
    via_words: str
    answers_short: str
    blocks: list[DependencyBlock]
    measured: bool
    state: ItemState
    lookups: list[DependencyLookup] = Field(default_factory=list, description="Each lookup's source, quoted line and date checked.")
    cells: list[DependencyCell] = Field(default_factory=list, description="Its answers as Dependencies words them.")


class ChecksView(Shape):
    plan_id: int
    title: str
    subline: str
    groups: list[CheckGroup] = Field(description="Always the four groups, in order.")
    busy: bool
    came_from_options: list[CameFrom]
    libraries: list[LibraryEvidenceRow] = Field(description="For Evidence's Dependencies group: one row per library.")
    evidence_counts: dict[str, StateCounts]


class CheckRun(Shape):
    run_id: int | None
    verify_run_id: int | None
    at: str | None
    came_from: str
    label: str | None
    tone: Tone
    fingerprint: str | None = Field(description="The run record's SHA-256 (a Verify run has none).")


class RelatedItem(Shape):
    key: str
    label: str
    sub: str
    link: ItemLink
    also: ItemLink | None


class RelatedLine(Shape):
    kind: Literal["claim", "test", "fix", "system", "library", "advisory"]
    title: str = Field(description='"Claim", "Checks", "Fix", "System and track", "Library", "Advisory" (phase 5c)')
    items: list[RelatedItem]


class CheckDetail(Shape):
    check: CheckRow
    result: LabResult | None = Field(description="The newest run, worded as its page words it (null for a claim).")
    verify: Result | None = Field(description="For a claim: its newest Verify result.")
    runs: list[CheckRun] = Field(description="Newest first.")
    related: list[RelatedLine]


class RelatedView(Shape):
    key: str
    related: list[RelatedLine]


class FixCameFrom(Shape):
    label: str
    link: ItemLink


class FixGroupAlso(Shape):
    fix_id: str
    title: str
    group_label: str


class FixGroup(Shape):
    key: GroupKey
    label: str
    question: str
    counts: StateCounts
    fix_ids: list[str]
    empty_text: str | None
    also: list[FixGroupAlso] = Field(description='"Also relates to this group": fixes listed in another group.')


class DemoProjectsLoaded(Shape):
    added: list[str]
    summary: str
    notices: list[str]
    open_assessment_id: int | None


# ---------------------------------------------------------------- phase 5c: Otto (test packs, Live Otto, Advisories)

class OttoPackCard(Shape):
    version: str
    built_at: str
    built: str = Field(description='"17 November 2026"')
    signer: str
    made_here: bool = Field(description="Signed with a key made on this computer (a live research run).")
    advisories: int
    tests: int
    line: str
    fingerprint: str
    installed_at: str | None


class OttoUpdateDialog(Shape):
    title: str
    lines: list[str]
    confirm: str
    cancel: str


class OttoUpdate(Shape):
    version: str
    button: str = Field(description='"Install update"')
    line: str
    dialog: OttoUpdateDialog


class OttoRefusedPack(Shape):
    file: str
    reason: str


class OttoCheckButton(Shape):
    button: str = Field(description='"Check for updates"')
    note: str


class OttoPacksSection(Shape):
    title: str
    intro: str
    installed: list[OttoPackCard] = Field(description="Oldest first. Packs are never removed.")
    installed_line: str
    unreadable_line: str | None = Field(description="Set when a pack installed by an earlier build can't be read by this version.")
    counts_line: str | None
    check: OttoCheckButton
    checked_line: str | None = Field(description="Set after Check for updates: what was found in the updates folder.")
    refused: list[OttoRefusedPack]
    update: OttoUpdate | None = Field(description="The pack that can be installed next, after Check for updates found one.")
    order_note: str


class OttoHarnessLine(Shape):
    installed: bool
    line: str


class OttoAnswersLine(Shape):
    line: str = Field(description='"Answers recorded during the build, 17 November 2026" or "Live: Claude, through your key"')
    live: bool


class OttoLiveSwitch(Shape):
    label: str = Field(description='"Use live Claude"')
    on: bool
    can_turn_on: bool = Field(description="Only when an API key is present on this computer.")
    blocked_reason: str | None


class OttoLiveLimit(Shape):
    label: str
    value: str = Field(description='US dollars, e.g. "2.00"')
    save: str
    note: str


class OttoLiveSection(Shape):
    title: str
    key_present: bool = Field(description="Whether a key is set. The key itself is never sent to the screen.")
    key_line: str
    switch: OttoLiveSwitch
    limit: OttoLiveLimit
    sent_line: str
    status_line: str
    price_line: str


class OttoName(Shape):
    """Phase 6a: who a decision on a proposal is recorded as. A name typed once, or "You"."""

    title: str = Field(description='"Who decides"')
    label: str = Field(description='"Your name"')
    value: str = Field(description="The name a person typed; empty until then.")
    recorded_as: str = Field(description='The typed name, or "You".')
    typed: bool
    line: str = Field(description='"Recorded as You, with the time."')
    save: str
    note: str
    max: int
    ask_label: str = Field(description="The label of the field in the Otto panel's first Confirm step.")


class OttoSettingsView(Shape):
    """Settings: the Test packs section, the two status lines and the Live Otto section (phase 5c)."""

    packs: OttoPacksSection
    harness: OttoHarnessLine
    answers: OttoAnswersLine
    live: OttoLiveSection
    name: OttoName | None = Field(default=None, description="Phase 6a: always sent by the current backend.")


class AdvisoryQuote(Shape):
    """A line of the publisher's own text, word for word. Information from the advisory, never a result."""

    text: str
    source: str
    publisher: str
    href: str = Field(description='An https link to a known publisher, or "" (then the source is shown as text).')
    read_on: str
    tag: str


class AdvisoryLedgerEntry(Shape):
    seq: int
    kind: str
    id: str
    at: str
    what: str


class AdvisoryLedger(Shape):
    title: str
    count: int
    entries: list[AdvisoryLedgerEntry]
    note: str


class AdvisoryTrial(Shape):
    title: str
    lines: list[str]


class AdvisoryTestBlock(Shape):
    title: str
    question: str
    cases_line: str
    control: str
    rule: str
    design_fingerprint: str
    trial: AdvisoryTrial
    ledger: AdvisoryLedger


class AdvisoryNoTest(Shape):
    label: str = Field(description='"No test yet" or "Not offered"')
    reason: str
    trial: AdvisoryTrial | None
    ledger: AdvisoryLedger | None


class AdvisoryHereResult(Shape):
    """The reviewer's result for this advisory's check in this assessment, as Evidence Lab words it."""

    label: str
    tone: Tone
    plain: str
    component: str | None
    finished_at: str | None
    ran_on: str | None = Field(default=None, description="After a retest: which version this result is of, and what the first run read.")


class AdvisoryHereRow(Shape):
    program: str
    status: str | None = Field(description='The proposal\'s word ("Proposed", "Not added (reason)") or "Not run yet"; null once there is a result.')
    proposal: "OttoProposal | None" = Field(description="Otto's proposed check for this program, with its state, decisions and buttons.")
    result: AdvisoryHereResult | None
    checks_link: ItemLink | None = Field(description="Open in Checks.")
    evidence_link: ItemLink | None = Field(description="See the evidence.")
    ledger: AdvisoryLedger | None


class AdvisoryHere(Shape):
    title: str
    rows: list[AdvisoryHereRow]
    empty: str | None
    note: str | None = None


class AdvisoryFixHere(Shape):
    label: str = Field(description='"View in Fixes"')
    link: ItemLink
    line: str


class AdvisoryFix(Shape):
    title: str
    label: str | None = Field(description='"From Otto" when the pack proposes a fix.')
    state: Literal["proven", "not_proven", "none"]
    lines: list[str]
    quote: AdvisoryQuote | None
    here: AdvisoryFixHere | None


class AdvisoryStep(Shape):
    step: str
    source: Literal["recorded", "live"]
    line: str
    prompt_sha256: str
    answer_sha256: str


class AdvisoryClaude(Shape):
    title: str
    steps: list[AdvisoryStep]
    note: str


class AdvisoryAffected(Shape):
    line: str
    quote: AdvisoryQuote


class AdvisorySource(Shape):
    label: str
    title: str
    publisher: str
    href: str
    read_on: str


class AdvisoryNotes(Shape):
    """What Claude noted when it read the advisory. Information, never a result."""

    title: str
    kind_line: str
    text: str | None
    caption: str


class AdvisoryPanel(Shape):
    sentence: str
    publisher: AdvisoryQuote | None
    affected: AdvisoryAffected | None
    notes: AdvisoryNotes | None
    also_known_as: list[str]
    sources: list[AdvisorySource]
    test: AdvisoryTestBlock | None
    no_test: AdvisoryNoTest | None
    here: AdvisoryHere
    fix: AdvisoryFix
    claude: AdvisoryClaude
    related_key: str


class AdvisoryTestCell(Shape):
    key: Literal["ready", "not_offered", "none"]
    label: str = Field(description='"Test ready", "Not offered" or "No test yet"')
    tone: Tone
    reason: str


class AdvisoryResultCell(Shape):
    key: str = Field(description='"pass", "fail", "warn", "neutral", "not_run", "not_added" or "none" (for the Result filter)')
    label: str
    tone: Tone
    text: str | None


class AdvisoryProposalCell(Shape):
    key: str = Field(description='"proposed", "accepted", "rejected", "mixed" or "none" (for the Decision filter)')
    label: str = Field(description='"Proposed", "Added", "Not added (reason)", "Mixed" or "Nothing proposed"')
    tone: Tone
    text: str | None = Field(description="With several programs: the counts, never merged.")
    keys: list[str] = Field(default_factory=list, description="With several programs: every state among them.")


class AdvisoryNew(Shape):
    """The 5c fixes: the tag beside an advisory that first arrived with the most recently installed test pack."""
    label: str = Field(description='"New"')
    title: str = Field(description='Said on hover and to a screen reader: "Arrived with test pack 2026.11.2".')


class AdvisoryRow(Shape):
    id: str
    name: str
    new: AdvisoryNew | None = Field(description="Null for an advisory of an earlier pack (also one a later pack only updates).")
    published: str
    published_text: str
    package: str
    pack: str
    fits: list[str]
    fits_text: str
    test: AdvisoryTestCell
    proposal: AdvisoryProposalCell
    result: AdvisoryResultCell
    search: str
    panel: AdvisoryPanel


class AdvisoryFilterOption(Shape):
    key: str
    label: str


class AdvisoryFilters(Shape):
    test: list[AdvisoryFilterOption]
    decision: list[AdvisoryFilterOption]
    result: list[AdvisoryFilterOption]


class AdvisoryWaiting(Shape):
    """Above the table: how many proposed checks nobody has decided yet. There is no button that decides several."""

    count: int
    blocked_reason: str | None = Field(description="Why nothing can be decided here right now (closed, or Otto not installed).")
    line: str
    note: str


class AdvisoriesView(Shape):
    """The Advisories page of an assessment (phase 5c). It words no result and decides none."""

    title: str
    subline: str
    standing_line: str
    packs_line: str
    packs_link: ItemLink
    answers_line: str
    otto: OttoHarnessLine
    waiting: AdvisoryWaiting
    filters: AdvisoryFilters
    columns: list[str]
    rows: list[AdvisoryRow]
    empty: str | None
    assessment_id: int | None


# ---- Phase 5c, second part: Otto proposes, a person decides. Every word comes from the backend. ----


class FixProofRow(Shape):
    """One of the two proof rows of a library's fix: "Proven on public copies" or "Proven on your system"."""

    key: Literal["public", "here"]
    label: str
    badge: FixDetailProofBadge = Field(description='"Passed", "Not proven" or "Not yet"')
    text: str
    line: str = Field(description="The row in one line, the same words wherever it is shown.")
    links: list["LabeledLink"]
    ledger: AdvisoryLedger | None = Field(description="The research ledger's entries behind the first row.")
    note: str | None = Field(default=None, description="Under the second row: what a retest here runs on (a public copy, not your system).")


class LabeledLink(Shape):
    label: str
    link: ItemLink


class OttoProposalStatus(Shape):
    key: Literal["proposed", "accepted", "rejected"]
    word: str = Field(description='"Proposed", "Added" or "Accepted", "Not added (reason)"')
    tone: Tone


class OttoProposalButton(Shape):
    key: Literal["accept", "reject", "undo", "reconsider"]
    label: str
    can: bool
    blocked_reason: str | None = Field(description="Why the button is off right now.")


class OttoRejectDialog(Shape):
    title: str
    line: str
    reason_label: str
    max: int
    confirm: str
    cancel: str


class OttoDecisionLine(Shape):
    number: int
    word: str
    by: str
    at: str
    at_text: str
    reason: str | None
    ledger_entry: str | None
    line: str


class OttoProposalHistory(Shape):
    title: str
    count: int
    rows: list[OttoDecisionLine]
    footnote: str
    ledger: AdvisoryLedger | None


class OttoResultDecisions(Shape):
    title: str
    count: int
    rows: list[OttoDecisionLine]
    footnote: str
    empty: str | None


class OttoResultBlock(Shape):
    """Evidence, on a result of an advisory check: what stands behind the check. Records only; it words no result."""

    label: str = Field(description='"From Otto"')
    title: str
    line: str
    advisory: LabeledLink
    design: AdvisoryTrial
    trial: AdvisoryTrial | None
    decisions: OttoResultDecisions
    ledger: AdvisoryLedger
    note: str


class OttoProposal(Shape):
    """One proposal of Otto's as a screen shows it. It words no result; a decision is recorded with who and when."""

    id: str
    kind: Literal["check", "fix", "plan", "dependency"]
    kind_label: str
    label: str = Field(description='"From Otto"')
    title: str
    why: str
    why_label: str
    lines: list[str]
    status: OttoProposalStatus
    decided_line: str | None
    effect: str | None = Field(description="What an accepted proposal has led to so far.")
    buttons: list[OttoProposalButton]
    note: str | None
    reject_dialog: OttoRejectDialog | None
    history: OttoProposalHistory
    link: ItemLink
    proposed_at: str | None


class OttoWaitingItem(Shape):
    kind: Literal["check", "fix", "plan", "dependency"]
    count: int
    text: str
    link: ItemLink
    page_label: str


class OttoWaiting(Shape):
    """The Overview's "Waiting for you": the proposals nobody has decided yet, each kind linking to its page."""

    title: str
    total: int
    items: list[OttoWaitingItem]
    line: str
    note: str


class OttoProposalsView(Shape):
    plan_id: int
    waiting: OttoWaiting
    proposals: list[OttoProposal]
    blocked_reason: str | None


class OttoPlanBlock(Shape):
    title: str
    note: str
    proposals: list[OttoProposal]


class OttoRoadmapMark(Shape):
    label: str
    text: str
    tone: Tone
    waiting: int


class OttoProjectRow(Shape):
    assessment_id: int
    title: str
    waiting: int
    waiting_text: str
    link: ItemLink
    since: list[str]


class OttoProjectBlock(Shape):
    title: str
    note: str
    pack_line: str
    since_title: str | None
    rows: list[OttoProjectRow]


class ImportOtto(Shape):
    """Import: "N checks may apply", marked From Otto, with the way to Advisories. Nothing runs on import."""

    count: int
    label: str
    text: str
    note: str
    link: ItemLink
    link_label: str


class CheckFromOtto(Shape):
    label: str
    advisory: str
    link: ItemLink


class DependencyAdvisoryState(Shape):
    key: Literal["affected", "not_affected", "not_checked"]
    label: str
    tone: Tone


class DependencyAdvisory(Shape):
    id: str
    name: str
    line: str = Field(description='"Named by advisory CVE-...: measured affected"')
    state: DependencyAdvisoryState
    detail: str
    fixed_line: str
    advisory_link: ItemLink
    evidence_link: ItemLink | None
    fix_link: ItemLink | None
    fix_label: str | None


class DependencyOttoStatus(Shape):
    label: str
    tone: Tone
    lines: list[str]


# ---- Phase 6a: the Otto panel beside every page of an assessment. One read; every word comes from the backend, and the
# panel decides nothing: on Confirm the browser sends the request of the page's own button, which `step.action` names. ----

AssistantThread = Literal["testing", "fixing", "planning"]


class AssistantStatus(Shape):
    """The one line under the title: what Settings says about Live Otto, with the way there when it is off."""

    text: str = Field(description='"Live Otto is off." or "Live Otto is on."')
    live: bool
    link: LabeledLink | None


class AssistantReason(Shape):
    label: str = Field(description='"Reason (optional, one short line)"')
    max: int


class AssistantConfirm(Shape):
    """The Confirm step: what will happen and what will not, and which button of which page it presses."""

    title: str
    lines: list[str]
    names: str = Field(description='"This is the Run all button on Checks."')
    confirm: str = Field(description='"Confirm"')
    cancel: str = Field(description='"Cancel"')
    reason: AssistantReason | None = Field(description="Reject only: the optional reason.")


class AssistantDecision(Shape):
    """One button of a suggestion: the page's own button, with the page's own reason when it is off."""

    key: Literal["accept", "reject", "undo", "reconsider"]
    label: str
    can: bool
    blocked_reason: str | None
    confirm: AssistantConfirm | None = Field(description="Null when the button is off: there is nothing to confirm.")


class AssistantAction(Shape):
    """The request of the page's own button. The browser sends it on Confirm, through the same call the page uses."""

    type: Literal["verify", "run", "run_all", "retest", "connect", "run_proof_again", "open_pull_request", "retest_now", "try", "ask_approval",
                  "measure_library", "measure_all", "measure_status", "open"]
    plan_id: int | None
    import_id: int | None
    item_id: int | None = Field(description="A test of the plan (Run).")
    fix_id: str | None
    change: str | None = Field(description="A server change's key (Try on a test copy, Ask for approval).")
    row: str | None = Field(description="A library row (Measure on a public copy).")
    version: str | None
    component: str | None
    reviewers: list[str] | None = Field(description="The reviewers the page ticks by default.")
    link: ItemLink | None = Field(description='"open": where it goes. Opening a page needs no Confirm.')


class AssistantStep(Shape):
    needs: Literal["confirm", "nothing"] = Field(description='"nothing": it only opens a page, at once.')
    action: AssistantAction
    can: bool
    blocked_reason: str | None = Field(description="The page's own reason when its button is off.")
    running: bool
    progress: str | None
    confirm: AssistantConfirm | None


class AssistantBadge(Shape):
    label: str
    tone: Tone


class AssistantEntry(Shape):
    """One entry of the panel: a suggestion (one of Otto's proposals), a next step (a button of a page) or what a
    result means; and, in a thread so far, a reviewed result or where a fix stands."""

    id: str
    kind: Literal["suggestion", "next", "meaning", "result", "fix_step"]
    what: str = Field(description='Its line in the one table of kinds, e.g. "next:run_all".')
    thread: AssistantThread | None
    mark: str = Field(description='"From Otto", "Next step", "What this means", "Result" or "Fix"')
    title: str
    text: str | None
    at: str | None = Field(description="When its cause happened (ISO): the order of a thread so far.")
    badge: AssistantBadge | None
    where: LabeledLink | None = Field(description='Where it lives: "On Advisories", with the link.')
    links: list[LabeledLink]
    proposal: OttoProposal | None = Field(description="A suggestion: the proposal exactly as its page shows it.")
    decisions: list[AssistantDecision]
    step: AssistantStep | None
    open_item: bool = Field(description="It is about the item that is open on the page.")


class AssistantTab(Shape):
    key: AssistantThread
    label: str
    waiting: int = Field(description="How many of this thread's suggestions nobody has decided yet.")
    mark: str = Field(description="Changes when the thread gets a new entry: the browser keeps it for a closed tab and for the dot.")
    so_far_title: str
    so_far: list[AssistantEntry]
    so_far_empty: str | None


class AssistantOnPage(Shape):
    title: str
    entries: list[AssistantEntry]
    empty: str | None
    empty_link: LabeledLink | None


class AssistantElsewhereLine(Shape):
    text: str = Field(description='"Fixes: 1 proposed fix, Update elliptic to 6.5.7"')
    count: int
    link: ItemLink
    thread: AssistantThread


class AssistantElsewhere(Shape):
    title: str = Field(description='"Elsewhere: 2 more"')
    count: int
    lines: list[AssistantElsewhereLine]
    empty: str | None = Field(description='"Nothing from Otto is waiting for a decision." when nothing waits anywhere.')


class AssistantView(Shape):
    assessment_id: int
    plan_id: int | None
    title: str = Field(description='"Otto"')
    status: AssistantStatus
    notices: list[str] = Field(description="The closed sentence, and what Settings says when Otto is not installed.")
    note: str
    recorded_as: OttoName = Field(description="Who a decision is recorded as, and whether a name has been typed yet.")
    page: str
    page_label: str
    thread: AssistantThread | None = Field(description="The tab this page selects (null on the Overview).")
    tabs: list[AssistantTab] = Field(description="At most three, and only the open ones.")
    on_page: AssistantOnPage
    elsewhere: AssistantElsewhere
    waiting: int = Field(description="Undecided suggestions on this page plus elsewhere.")
    busy: bool = Field(description="Something is running: ask again in a second.")


def _rebuild_all() -> None:
    for _model in list(globals().values()):
        if isinstance(_model, type) and issubclass(_model, BaseModel) and _model is not BaseModel:
            _model.model_rebuild()


_rebuild_all()
