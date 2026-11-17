import type {
  AdvisoriesView,
  AdvisoryClaude,
  AdvisoryHereRow,
  AdvisoryLedger,
  AdvisoryQuote,
  AdvisoryRow,
  AdvisorySource,
  AdvisoryStep,
  AdvisoryTestBlock,
  AssessmentView,
  FixesView,
  LabRow,
  OttoHarnessLine,
  OttoLiveSection,
  OttoPackCard,
  OttoSettingsView,
  OttoUpdate,
  RelatedView,
} from "../api";

/** Phase 5c (Otto in Evidence Lab): the answers the Advisories page, the Otto sections of Settings and the Otto words on
 * Evidence and Fixes are drawn from. They are the backend's own answers, copied from a run of the real routes on packs
 * made for tests (which is why a signer reads "A key made for a test" and a source "A made-up advisory for a test"):
 * every exported view equals the answer it was copied from, with the parts they share written once. The states: no pack
 * installed; a pack installed and its check not added, added but not run, and failed; two packs; a closed assessment;
 * Otto not installed on this computer. The last section holds a few states that were not among those answers; they
 * are built from them with the backend's own sentences, and say so. */

// ---- Words and parts the answers share

const SUBLINE: string = "Every published advisory in the installed test packs: whether it has a test, which signing programs of this assessment it fits, and the latest result of its check here, in the reviewer's words.";

/** The standing line of the Advisories page: the only place the page says "secure". */
export const STANDING_LINE: string = "Passing these tests doesn't prove a system secure. It shows these specific checks passed.";

const ADD_NOTE: string = "Adds every pack test that fits a program in this assessment and is not in the test plan yet. It runs nothing.";

/** What every Otto screen says when Otto's harness is not on this computer. */
export const NOT_INSTALLED_LINE: string = "Otto is not installed on this computer: it has not been fetched on this computer. ./run-demo.sh fetches it; that needs read access to the isogeny-labs/otto repository once. Advisory checks can't be added or run, because their runs could not be recorded. Everything else works as before.";

const OTTO_INSTALLED: OttoHarnessLine = { installed: true, line: "Otto harness: version 0.1.0, commit aa4a6fd (pinned)." };

const OTTO_MISSING: OttoHarnessLine = { installed: false, line: NOT_INSTALLED_LINE };

const PACKS_LINK: AdvisoriesView["packs_link"] = { page: "settings", item: null, section: "test-packs" };

const FILTERS: AdvisoriesView["filters"] = {
  test: [
    { key: "all", label: "Any test" },
    { key: "ready", label: "Test ready" },
    { key: "not_offered", label: "Not offered" },
    { key: "none", label: "No test yet" },
  ],
  result: [
    { key: "all", label: "Any result" },
    { key: "fail", label: "Failed" },
    { key: "pass", label: "Passed" },
    { key: "warn", label: "Couldn't run or trust" },
    { key: "not_run", label: "Not run yet" },
    { key: "not_added", label: "Not added yet" },
    { key: "none", label: "No check" },
  ],
};

const COLUMNS: string[] = ["Advisory", "Published", "Fits", "Test", "Result here"];

// The publisher's own line, as every advisory of the test packs quotes it.
const QUOTE: AdvisoryQuote = {
  text: "accepts a signature whose two numbers are zero",
  source: "A made-up advisory for a test",
  publisher: "The test suite",
  href: "https://openjdk.org/groups/vulnerability/advisories/2022-04-19",
  read_on: "17 November 2026",
  tag: "from the advisory, not a result",
};

const SOURCES: AdvisorySource[] = [
  {
    label: "S1",
    title: "A made-up advisory for a test",
    publisher: "The test suite",
    href: "https://openjdk.org/groups/vulnerability/advisories/2022-04-19",
    read_on: "17 November 2026",
  },
];

const TEST_READY_REASON: string = "Test ready: tried on public copies before this pack was signed.";

const CONTROL: string = "A deliberately broken checker that accepts every signature. It must get every must-reject case wrong, so the selection needs at least one must-reject case.";

const RULE: string = "Passed only if every answer is right. Any wrong answer means Failed.";

const QUESTION: string = "Does the program reject the signatures that advisory CVE-2022-21449 describes?";

const JUDGED_SUPPORTED: string = "Otto's harness judged the trial against thresholds fixed before the first run: supported. A second author replayed it with the same numbers.";

// Otto's research ledger entries of a test that is offered.
const RESEARCH_LEDGER: AdvisoryLedger = {
  title: "Otto ledger entries",
  count: 1,
  entries: [{ seq: 0, kind: "question", id: "111111111111", at: "2026-11-17T12:00:00+00:00", what: "Question asked: a test" }],
  note: "From Otto's research ledger, a hash chain kept with Adam's harness: the test was registered, tried and judged before the pack was signed.",
};

const RESEARCH_LEDGER_NO_TEST: AdvisoryLedger = {
  title: "Otto ledger entries",
  count: 1,
  entries: [{ seq: 0, kind: "question", id: "111111111111", at: "2026-11-17T12:00:00+00:00", what: "Question asked: a test" }],
  note: "From Otto's research ledger, a hash chain kept with Adam's harness.",
};

const READ_STEP: AdvisoryStep = {
  step: "Read the advisory",
  source: "recorded",
  line: "Read the advisory: Written for a test, not an answer from Claude, 17 November 2026.",
  prompt_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  answer_sha256: "7d8ea9fda9d522985404df642a608ddc4ba3c841075f150dbc6c3547deb1f7f4",
};

const DESIGN_STEP: AdvisoryStep = {
  step: "Design a test",
  source: "recorded",
  line: "Design a test: Written for a test, not an answer from Claude, 17 November 2026.",
  prompt_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  answer_sha256: "7d8ea9fda9d522985404df642a608ddc4ba3c841075f150dbc6c3547deb1f7f4",
};

const FIX_STEP: AdvisoryStep = {
  step: "Propose the fix",
  source: "recorded",
  line: "Propose the fix: Written for a test, not an answer from Claude, 17 November 2026.",
  prompt_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  answer_sha256: "7d8ea9fda9d522985404df642a608ddc4ba3c841075f150dbc6c3547deb1f7f4",
};

const CLAUDE_NOTE: string = "Every prompt and answer is in Otto's research ledger, with its SHA-256. What Claude writes is data: a quote must stand in the publisher's text, a design can only pick published cases, and a fix is offered only after its proof.";

const CLAUDE_THREE_STEPS: AdvisoryClaude = { title: "What Otto asked Claude", steps: [READ_STEP, DESIGN_STEP, FIX_STEP], note: CLAUDE_NOTE };

const CLAUDE_TWO_STEPS: AdvisoryClaude = { title: "What Otto asked Claude", steps: [READ_STEP, DESIGN_STEP], note: CLAUDE_NOTE };

const NO_FIX_REASON: string = "No fix is offered: there is no test for this advisory to prove one with.";

const NO_TEST_HERE: AdvisoryRow["panel"]["here"] = { title: "In this assessment", rows: [], empty: "This advisory has no test, so there is nothing to run here." };

const SENTENCE: string = "The program accepts a signature whose two numbers are zero or out of range.";

const AFFECTED_ACME: NonNullable<AdvisoryRow["panel"]["affected"]> = { line: "Affected versions, in the publisher's terms: 1.4.2 and earlier", quote: QUOTE };

const AFFECTED_ELLIPTIC: NonNullable<AdvisoryRow["panel"]["affected"]> = { line: "Affected versions, in the publisher's terms: 6.5.6 and earlier", quote: QUOTE };

// ---- The advisory whose check runs here: CVE-2022-21449, in each state of its check

// Its test: ready, with its trial on public copies and its ledger entries.
const BLANK_TEST: AdvisoryTestBlock = {
  title: "The test",
  question: QUESTION,
  cases_line: "64 published cases from Project Wycheproof, pinned by SHA-256: 64 that must be rejected.",
  control: CONTROL,
  rule: RULE,
  design_fingerprint: "7b06a70535ac437d660e31e54dd0f01dedf7dc784d79ae0fc64cffc34e5384cc",
  trial: {
    title: "How it did when tried on public copies",
    lines: [
      "acme-sign 1.4.2 (affected): 2 of 64 cases wrong.",
      "acme-sign 1.4.3 (the publisher's fixed version): 0 of 64 cases wrong.",
      "The control that must fail (a program that accepts every signature): 64 of 64 cases wrong.",
      JUDGED_SUPPORTED,
    ],
  },
  ledger: RESEARCH_LEDGER,
};

// Otto's ledger entries of the check in this assessment, once it has run.
const CHECK_LEDGER: AdvisoryLedger = {
  title: "Otto ledger entries for this check",
  count: 3,
  entries: [
    {
      seq: 0,
      kind: "objective",
      id: "028b395512ec",
      at: "2026-11-17T19:57:06+00:00",
      what: "Lock entry: the test's fingerprint, its design and its pack, written before any run",
    },
    { seq: 1, kind: "claim", id: "ea9d697236fb", at: "2026-11-17T19:57:17+00:00", what: "Run 6 (first run) bound to the locked test" },
    { seq: 2, kind: "verdict", id: "1b7d76ad81af", at: "2026-11-17T19:57:17+00:00", what: "The pinned checker: bound and consistent" },
  ],
  note: "The ledger shows that each run belongs to the test locked before it. It holds no result.",
};

// The reviewer's result of the check, as Evidence words it.
const FAILED_RESULT: NonNullable<AdvisoryHereRow["result"]> = {
  label: "Failed",
  tone: "fail",
  plain: "acme-sign 1.4.2 got 2 of the 64 published cases for advisory CVE-2022-21449 wrong: it accepted 2 signatures that must be rejected. One wrong answer is enough to fail.",
  component: "acme-sign 1.4.2",
  finished_at: "2026-11-17T19:57:17.753Z",
};

/** A pack is installed; its test fits acme-sign 1.4.2 and is not in the test plan yet. */
export const blankNotAdded: AdvisoryRow = {
  id: "CVE-2022-21449",
  name: "Blank signature accepted",
  published: "2026-11-01",
  published_text: "1 November 2026",
  package: "acme-sign (demo)",
  pack: "2026.11.1",
  fits: ["acme-sign 1.4.2"],
  fits_text: "acme-sign 1.4.2",
  test: { key: "ready", label: "Test ready", tone: "pass", reason: TEST_READY_REASON },
  result: { key: "not_added", label: "Not added yet", tone: "neutral", text: null },
  search: "cve-2022-21449 blank signature accepted acme-sign acme-sign 1.4.2",
  panel: {
    sentence: SENTENCE,
    publisher: QUOTE,
    affected: AFFECTED_ACME,
    notes: null,
    also_known_as: [],
    sources: SOURCES,
    test: BLANK_TEST,
    no_test: null,
    here: {
      title: "In this assessment",
      rows: [{ program: "acme-sign 1.4.2", status: "Not added yet", result: null, checks_link: null, evidence_link: null, ledger: null }],
      empty: null,
    },
    fix: {
      title: "Fix",
      label: "From Otto",
      state: "proven",
      lines: [
        "Otto proposes: update acme-sign to 1.4.3 or later.",
        "Update acme-sign to 1.4.3, which checks that both numbers of a signature are in range.",
        "Proven on public copies: this advisory's check passed and all 3 pass-or-fail tests read Passed.",
      ],
      quote: QUOTE,
      here: null,
    },
    claude: CLAUDE_THREE_STEPS,
    related_key: "advisory:CVE-2022-21449",
  },
};

/** Add new checks put the test in the plan; it has not run. */
export const blankNotRun: AdvisoryRow = {
  ...blankNotAdded,
  result: { key: "not_run", label: "Not run yet", tone: "neutral", text: null },
  panel: {
    ...blankNotAdded.panel,
    here: {
      ...blankNotAdded.panel.here,
      rows: [
        {
          program: "acme-sign 1.4.2",
          status: "Not run yet",
          result: null,
          checks_link: { page: "checks", item: "test-6" },
          evidence_link: null,
          ledger: {
            title: "Otto ledger entries for this check",
            count: 1,
            entries: [
              {
                seq: 0,
                kind: "objective",
                id: "028b395512ec",
                at: "2026-11-17T19:57:06+00:00",
                what: "Lock entry: the test's fingerprint, its design and its pack, written before any run",
              },
            ],
            note: "The ledger shows that each run belongs to the test locked before it. It holds no result.",
          },
        },
      ],
    },
    fix: {
      ...blankNotAdded.panel.fix,
      lines: [
        "Otto proposes: update acme-sign to 1.4.3 or later.",
        "Update acme-sign to 1.4.3, which checks that both numbers of a signature are in range.",
        "Proven on public copies: this advisory's check passed and all 3 pass-or-fail tests read Passed.",
        "For your own code, Otto writes the change in Fixes once this advisory's check has failed here; it is offered only after every locked test passes on the changed code.",
      ],
    },
  },
};

/** The check ran and the reviewer read Failed; Fixes holds the fix. */
export const blankFailed: AdvisoryRow = {
  ...blankNotAdded,
  result: { key: "fail", label: "Failed", tone: "fail", text: null },
  panel: {
    ...blankNotAdded.panel,
    here: {
      ...blankNotAdded.panel.here,
      rows: [
        {
          program: "acme-sign 1.4.2",
          status: null,
          result: FAILED_RESULT,
          checks_link: { page: "checks", item: "test-6" },
          evidence_link: { page: "evidence", item: "test-6" },
          ledger: CHECK_LEDGER,
        },
      ],
    },
    fix: {
      ...blankNotAdded.panel.fix,
      here: {
        label: "View in Fixes",
        link: { page: "fixes", item: "fix-ecdsa-range-check" },
        line: "In this assessment: acme-sign accepts out-of-range signatures (Code not connected).",
      },
    },
  },
};

/** The same once Otto's harness is gone from this computer: the result stays, the check's ledger can't be read. */
export const blankFailedNoLedger: AdvisoryRow = {
  ...blankFailed,
  panel: {
    ...blankFailed.panel,
    here: {
      ...blankFailed.panel.here,
      rows: [
        {
          program: "acme-sign 1.4.2",
          status: null,
          result: FAILED_RESULT,
          checks_link: { page: "checks", item: "test-6" },
          evidence_link: { page: "evidence", item: "test-6" },
          ledger: null,
        },
      ],
    },
  },
};

// ---- The other advisories of the two test packs

/** No test yet: no building block can show this weakness. */
export const stopsNoTest: AdvisoryRow = {
  id: "CVE-2019-14853",
  name: "Stops on a bad signature",
  published: "2026-11-01",
  published_text: "1 November 2026",
  package: "acme-sign (demo)",
  pack: "2026.11.1",
  fits: [],
  fits_text: "",
  test: { key: "none", label: "No test yet", tone: "neutral", reason: "No test yet: no building block can show this weakness." },
  result: { key: "none", label: "No check", tone: "neutral", text: null },
  search: "cve-2019-14853 stops on a bad signature acme-sign",
  panel: {
    sentence: SENTENCE,
    publisher: QUOTE,
    affected: AFFECTED_ACME,
    notes: null,
    also_known_as: [],
    sources: SOURCES,
    test: null,
    no_test: { label: "No test yet", reason: "No test yet: no building block can show this weakness.", trial: null, ledger: RESEARCH_LEDGER_NO_TEST },
    here: NO_TEST_HERE,
    fix: { title: "Fix", label: null, state: "none", lines: ["The publisher names 1.4.3 as the fixed version.", NO_FIX_REASON], quote: QUOTE, here: null },
    claude: CLAUDE_TWO_STEPS,
    related_key: "advisory:CVE-2019-14853",
  },
};

/** From the second pack: a ready test that fits acme-sign 1.4.2 and is not added yet. */
export const zeroNotAdded: AdvisoryRow = {
  id: "CVE-2024-42460",
  name: "Missing leading zero accepted",
  published: "2026-11-01",
  published_text: "1 November 2026",
  package: "elliptic (demo)",
  pack: "2026.11.2",
  fits: ["acme-sign 1.4.2"],
  fits_text: "acme-sign 1.4.2",
  test: { key: "ready", label: "Test ready", tone: "pass", reason: TEST_READY_REASON },
  result: { key: "not_added", label: "Not added yet", tone: "neutral", text: null },
  search: "cve-2024-42460 missing leading zero accepted elliptic acme-sign 1.4.2",
  panel: {
    sentence: SENTENCE,
    publisher: QUOTE,
    affected: AFFECTED_ELLIPTIC,
    notes: null,
    also_known_as: [],
    sources: SOURCES,
    test: {
      title: "The test",
      question: QUESTION,
      cases_line: "1 published case from Project Wycheproof, pinned by SHA-256: 1 that must be rejected.",
      control: CONTROL,
      rule: RULE,
      design_fingerprint: "93533fb8868a005877cfb47e2c4ac12268b2c0d028956a11838ef58144c9e4b8",
      trial: {
        title: "How it did when tried on public copies",
        lines: [
          "elliptic 6.5.6 (affected): 2 of 1 cases wrong.",
          "elliptic 6.5.7 (the publisher's fixed version): 0 of 1 cases wrong.",
          "The control that must fail (a program that accepts every signature): 1 of 1 cases wrong.",
          JUDGED_SUPPORTED,
        ],
      },
      ledger: RESEARCH_LEDGER,
    },
    no_test: null,
    here: {
      title: "In this assessment",
      rows: [{ program: "acme-sign 1.4.2", status: "Not added yet", result: null, checks_link: null, evidence_link: null, ledger: null }],
      empty: null,
    },
    fix: {
      title: "Fix",
      label: "From Otto",
      state: "proven",
      lines: [
        "Otto proposes: update elliptic to 6.5.7 or later.",
        "Update elliptic to 6.5.7, which checks that both numbers of a signature are in range.",
        "Proven on public copies: this advisory's check passed and all 3 pass-or-fail tests read Passed.",
      ],
      quote: QUOTE,
      here: null,
    },
    claude: CLAUDE_THREE_STEPS,
    related_key: "advisory:CVE-2024-42460",
  },
};

/** From the second pack: a test that is not offered, because its design failed its own trial. */
export const looseNotOffered: AdvisoryRow = {
  id: "CVE-2024-42461",
  name: "Loose length accepted",
  published: "2026-11-01",
  published_text: "1 November 2026",
  package: "elliptic (demo)",
  pack: "2026.11.2",
  fits: [],
  fits_text: "",
  test: { key: "not_offered", label: "Not offered", tone: "warn", reason: "Not offered: the design failed its own trial." },
  result: { key: "none", label: "No check", tone: "neutral", text: null },
  search: "cve-2024-42461 loose length accepted elliptic",
  panel: {
    sentence: SENTENCE,
    publisher: QUOTE,
    affected: AFFECTED_ELLIPTIC,
    notes: null,
    also_known_as: [],
    sources: SOURCES,
    test: null,
    no_test: {
      label: "Not offered",
      reason: "Not offered: the design failed its own trial.",
      trial: {
        title: "How its design did when tried on public copies",
        lines: [
          "elliptic 6.5.6 (affected): 0 of 7 cases wrong.",
          "elliptic 6.5.7 (the publisher's fixed version): 0 of 7 cases wrong.",
          "The control that must fail (a program that accepts every signature): 7 of 7 cases wrong.",
          "Otto's harness judged the trial against thresholds fixed before the first run: refuted. A second author replayed it with the same numbers.",
        ],
      },
      ledger: RESEARCH_LEDGER_NO_TEST,
    },
    here: NO_TEST_HERE,
    fix: { title: "Fix", label: null, state: "none", lines: ["The publisher names 6.5.7 as the fixed version.", NO_FIX_REASON], quote: QUOTE, here: null },
    claude: CLAUDE_TWO_STEPS,
    related_key: "advisory:CVE-2024-42461",
  },
};

// ---- The Advisories page, state by state

/** No test pack is installed. */
export const advisoriesNoPack: AdvisoriesView = {
  title: "Advisories",
  subline: SUBLINE,
  standing_line: STANDING_LINE,
  packs_line: "No test pack is installed yet. Settings, Test packs, Check for updates.",
  packs_link: PACKS_LINK,
  answers_line: "Answers recorded during the build",
  otto: OTTO_INSTALLED,
  add: {
    button: "Add new checks",
    count: 0,
    can: false,
    blocked_reason: "No test pack is installed. Install one in Settings, under Test packs.",
    note: ADD_NOTE,
  },
  filters: FILTERS,
  columns: COLUMNS,
  rows: [],
  empty: "No test pack is installed yet. In Settings, under Test packs, Check for updates looks in the updates folder on this computer.",
  assessment_id: 1,
};

/** One pack is installed; one new check can be added. */
export const advisoriesNotAdded: AdvisoriesView = {
  title: "Advisories",
  subline: SUBLINE,
  standing_line: STANDING_LINE,
  packs_line: "Test packs installed: 2026.11.1.",
  packs_link: PACKS_LINK,
  answers_line: "Answers written for a test, 17 November 2026",
  otto: OTTO_INSTALLED,
  add: { button: "Add new checks (1)", count: 1, can: true, blocked_reason: null, note: ADD_NOTE },
  filters: FILTERS,
  columns: COLUMNS,
  rows: [blankNotAdded, stopsNoTest],
  empty: null,
  assessment_id: 1,
};

/** After Add new checks: the check is in the plan and has not run. */
export const advisoriesAddedNotRun: AdvisoriesView = {
  ...advisoriesNotAdded,
  add: {
    button: "Add new checks",
    count: 0,
    can: false,
    blocked_reason: "Every test of the installed packs that fits this assessment is already in the test plan.",
    note: ADD_NOTE,
  },
  rows: [blankNotRun, stopsNoTest],
};

/** The check ran: Failed. */
export const advisoriesFailed: AdvisoriesView = {
  ...advisoriesAddedNotRun,
  rows: [blankFailed, stopsNoTest],
};

/** A second pack is installed: four advisories, one new check to add. */
export const advisoriesTwoPacks: AdvisoriesView = {
  ...advisoriesNotAdded,
  packs_line: "Test packs installed: 2026.11.1, 2026.11.2.",
  rows: [blankFailed, stopsNoTest, zeroNotAdded, looseNotOffered],
};

/** The same in a closed assessment: nothing can be added. */
export const advisoriesClosed: AdvisoriesView = {
  ...advisoriesTwoPacks,
  packs_line: "Test packs installed when this assessment was closed: 2026.11.1, 2026.11.2.",
  add: { button: "Add new checks", count: 0, can: false, blocked_reason: "This assessment is closed, so nothing can be added to it.", note: ADD_NOTE },
};

/** The same on a computer without Otto's harness: nothing can be added or run. */
export const advisoriesOttoMissing: AdvisoriesView = {
  ...advisoriesTwoPacks,
  otto: OTTO_MISSING,
  add: { button: "Add new checks (1)", count: 1, can: false, blocked_reason: NOT_INSTALLED_LINE, note: ADD_NOTE },
  rows: [blankFailedNoLedger, stopsNoTest, zeroNotAdded, looseNotOffered],
};

// ---- Settings: Test packs and Live Otto, state by state

const PACKS_INTRO: string = "A test pack is a signed update, like an antivirus update: published advisories, a test for each one that has one, a proposed fix, and how each did when it was tried on public copies. Nothing in a pack runs.";

const CHECK: OttoSettingsView["packs"]["check"] = { button: "Check for updates", note: "It looks in the updates folder on this computer, never on the internet." };

const ORDER_NOTE: string = "Packs install in order and are never removed.";

const ANSWERS_RECORDED: OttoSettingsView["answers"] = { line: "Answers recorded during the build", live: false };

const ANSWERS_FOR_A_TEST: OttoSettingsView["answers"] = { line: "Answers written for a test, 17 November 2026", live: false };

const LIVE_NOTE: string = "A run is one fix request in the app, or one research command. Otto adds up each call's cost from the tokens the API reports, and does not send a request that could pass the limit.";

const SENT_LINE: string = "What is sent to Claude when this is on: the advisory text and, for a fix to your own code, the source file of the failing program and the cases it got wrong. Nothing else leaves this computer.";

const PRICE_LINE: string = "Prices used to add up the cost: Anthropic price list, as of 3 November 2026. A price list can go out of date.";

// Live Otto on a computer with no API key: the switch is off and can't be turned on.
const LIVE_NO_KEY: OttoLiveSection = {
  title: "Live Otto",
  key_present: false,
  key_line: "No API key is set on this computer. Live Otto reads it from the ANTHROPIC_API_KEY environment variable; the key is never shown, stored or sent anywhere but to Claude.",
  switch: { label: "Use live Claude", on: false, can_turn_on: false, blocked_reason: "This can be turned on only when an API key is present." },
  limit: { label: "Spending limit per run (US dollars)", value: "2.00", save: "Save", note: LIVE_NOTE },
  sent_line: SENT_LINE,
  status_line: "Live Otto is off: no API key is set on this computer. Otto works on the answers recorded during the build.",
  price_line: PRICE_LINE,
};

const PACK_ONE: OttoPackCard = {
  version: "2026.11.1",
  built_at: "2026-11-17T12:00:00Z",
  built: "17 November 2026",
  signer: "A key made for a test",
  made_here: false,
  advisories: 2,
  tests: 1,
  line: "Pack 2026.11.1, built 17 November 2026: 2 advisories, 1 test.",
  fingerprint: "7c9db0682e14f3896d6f29aade9c60cc674c058e6f5ab82744188faede3a5bfd",
  installed_at: "2026-11-17T19:57:06.563Z",
};

const PACK_TWO: OttoPackCard = {
  version: "2026.11.2",
  built_at: "2026-11-17T12:00:00Z",
  built: "17 November 2026",
  signer: "A key made for a test",
  made_here: false,
  advisories: 2,
  tests: 1,
  line: "Pack 2026.11.2, built 17 November 2026: 2 advisories, 1 test.",
  fingerprint: "548fbcf1ef2f5e33c5a1dbaf1f5c4ec6487d7b18895c1b2db40bd86e84292c61",
  installed_at: "2026-11-17T19:57:18.191Z",
};

const UPDATE_ONE: OttoUpdate = {
  version: "2026.11.1",
  button: "Install update",
  line: "Test pack 2026.11.1 is in the updates folder.",
  dialog: {
    title: "Install test pack 2026.11.1?",
    lines: [
      "Pack 2026.11.1, built 17 November 2026: 2 advisories, 1 test.",
      "Signed by: A key made for a test.",
      "It adds:",
      "Blank signature accepted (CVE-2022-21449): Test ready",
      "Stops on a bad signature (CVE-2019-14853): No test yet",
      "Nothing in a pack runs. Installing adds no check to any assessment: you add its checks on the Advisories page.",
      ORDER_NOTE,
    ],
    confirm: "Install",
    cancel: "Cancel",
  },
};

const UPDATE_TWO: OttoUpdate = {
  version: "2026.11.2",
  button: "Install update",
  line: "Test pack 2026.11.2 is in the updates folder.",
  dialog: {
    title: "Install test pack 2026.11.2?",
    lines: [
      "Pack 2026.11.2, built 17 November 2026: 2 advisories, 1 test.",
      "Signed by: A key made for a test.",
      "It adds:",
      "Missing leading zero accepted (CVE-2024-42460): Test ready",
      "Loose length accepted (CVE-2024-42461): Not offered",
      "Nothing in a pack runs. Installing adds no check to any assessment: you add its checks on the Advisories page.",
      ORDER_NOTE,
    ],
    confirm: "Install",
    cancel: "Cancel",
  },
};

/** Settings as they open: no pack installed, nothing checked yet. */
export const ottoEmpty: OttoSettingsView = {
  packs: {
    title: "Test packs",
    intro: PACKS_INTRO,
    installed: [],
    installed_line: "No test pack is installed yet.",
    counts_line: null,
    check: CHECK,
    checked_line: null,
    refused: [],
    update: null,
    order_note: ORDER_NOTE,
  },
  harness: OTTO_INSTALLED,
  answers: ANSWERS_RECORDED,
  live: LIVE_NO_KEY,
};

/** After Check for updates: the first pack can be installed. */
export const ottoUpdateFound: OttoSettingsView = {
  ...ottoEmpty,
  packs: {
    ...ottoEmpty.packs,
    checked_line: "Test pack 2026.11.1 is ready to install. 1 more pack follows it; packs install in order.",
    update: UPDATE_ONE,
  },
};

/** After Install: one pack installed, and the next one found. */
export const ottoInstalledOne: OttoSettingsView = {
  ...ottoEmpty,
  packs: {
    ...ottoEmpty.packs,
    installed: [PACK_ONE],
    installed_line: "Installed: pack 2026.11.1, built 17 November 2026, signed by A key made for a test.",
    counts_line: "2 advisories and 1 test in 1 installed pack.",
    checked_line: "Test pack 2026.11.2 is ready to install.",
    update: UPDATE_TWO,
  },
  answers: ANSWERS_FOR_A_TEST,
};

/** Both packs installed. */
export const ottoInstalledTwo: OttoSettingsView = {
  ...ottoInstalledOne,
  packs: {
    ...ottoInstalledOne.packs,
    installed: [PACK_ONE, PACK_TWO],
    installed_line: "Installed: pack 2026.11.2, built 17 November 2026, signed by A key made for a test.",
    counts_line: "4 advisories and 2 tests in 2 installed packs.",
    checked_line: null,
    update: null,
  },
};

/** An API key is on this computer and Use live Claude is on, with a limit of 3.50. */
export const ottoLiveOn: OttoSettingsView = {
  ...ottoInstalledTwo,
  answers: { line: "Live: Claude, through your key", live: true },
  live: {
    ...ottoInstalledTwo.live,
    key_present: true,
    key_line: "An API key is set on this computer.",
    switch: { label: "Use live Claude", on: true, can_turn_on: true, blocked_reason: null },
    limit: { label: "Spending limit per run (US dollars)", value: "3.50", save: "Save", note: LIVE_NOTE },
    status_line: "Live Otto is on: when Otto needs an answer, it asks Claude through your key, within the spending limit.",
  },
};

/** Otto's harness is not on this computer. */
export const ottoHarnessMissing: OttoSettingsView = {
  ...ottoInstalledTwo,
  harness: OTTO_MISSING,
};

// ---- Related, Evidence, Fixes and the Overview's next step

/** GET /api/plans/<id>/related?key=advisory:CVE-2022-21449 once its check has failed. */
export const relatedOfAdvisory: RelatedView = {
  key: "advisory:CVE-2022-21449",
  related: [
    {
      kind: "test",
      title: "Checks",
      items: [
        {
          key: "test:6",
          label: "Advisory check: Blank signature accepted (CVE-2022-21449)",
          sub: "acme-sign 1.4.2 \u00b7 Failed",
          link: { page: "evidence", item: "test-6" },
          also: null,
        },
      ],
    },
    {
      kind: "fix",
      title: "Fix",
      items: [
        {
          key: "fix:fix-ecdsa-range-check",
          label: "acme-sign accepts out-of-range signatures",
          sub: "Code not connected",
          link: { page: "fixes", item: "fix-ecdsa-range-check" },
          also: null,
        },
      ],
    },
  ],
};

/** The Related block of the advisory's check (test:6): its sixth line is the advisory. */
export const relatedOfAdvisoryCheck: RelatedView = {
  key: "test:6",
  related: [
    {
      kind: "claim",
      title: "Claim",
      items: [
        {
          key: "claim:3",
          label: "signing component is acme-sign 1.4.2 implementing ECDSA P-256",
          sub: "Not verified yet",
          link: { page: "inventory/import", item: "claim-3" },
          also: null,
        },
      ],
    },
    {
      kind: "fix",
      title: "Fix",
      items: [
        {
          key: "fix:fix-ecdsa-range-check",
          label: "acme-sign accepts out-of-range signatures",
          sub: "Code not connected",
          link: { page: "fixes", item: "fix-ecdsa-range-check" },
          also: null,
        },
      ],
    },
    {
      kind: "system",
      title: "System and track",
      items: [
        {
          key: "system:software:lib-acme-sign",
          label: "acme-sign 1.4.2",
          sub: "Not measured yet",
          link: { page: "migration/roadmap", item: "software:lib-acme-sign" },
          also: { page: "migration/systems", item: "software:lib-acme-sign" },
        },
      ],
    },
    {
      kind: "advisory",
      title: "Advisory",
      items: [
        {
          key: "advisory:CVE-2022-21449",
          label: "Blank signature accepted (CVE-2022-21449)",
          sub: "Test ready",
          link: { page: "advisories", item: "CVE-2022-21449" },
          also: null,
        },
      ],
    },
  ],
};

// The kind of an advisory check: a test from a test pack (phase 5c).
const ADVISORY_CASES: LabRow["kind"] = "advisory_cases";

/** Evidence: the advisory check's row, with the advisory it is for in its advisories box. */
export const advisoryCheckRow: LabRow = {
  item_id: 6,
  kind: ADVISORY_CASES,
  title: "Advisory check: Blank signature accepted (CVE-2022-21449)",
  control_line: "Control: a deliberately broken signer failed this test, as expected.",
  result: {
    run_id: 6,
    component: "acme-sign 1.4.2",
    mode: "demo",
    finished_at: "2026-11-17T19:57:17.753Z",
    duration_ms: 1378,
    code: "failed",
    label: "Failed",
    tone: "fail",
    plain: "acme-sign 1.4.2 got 2 of the 64 published cases for advisory CVE-2022-21449 wrong: it accepted 2 signatures that must be rejected. One wrong answer is enough to fail.",
    also_noticed: [],
    also_noticed_title: "Also noticed",
    summary: "2 of 64 advisory cases wrong. First: case 168, r=0 and s=0 (a signature made of zeros) was accepted.",
    short: "2 of 64 advisory cases wrong (168, 171).",
    control: {
      outcome: "as_expected",
      line: "Control: a deliberately broken signer failed this test, as expected.",
      text: "The deliberately broken signer got all 64 invalid cases wrong, so it failed as expected. That tells us this check can catch a faulty signer, and the result above can be trusted.",
    },
    what_happened: [
      "acme-sign 1.4.2 was shown the 64 published signatures that match advisory CVE-2022-21449 (Blank signature accepted) and asked \u201cis this one genuine?\u201d. It gave the wrong answer 2 times.",
    ],
    shows_title: "What this shows, and what it doesn't",
    shows: [
      "It shows this version gives the wrong answer on published cases of the kind advisory CVE-2022-21449 describes.",
      "It doesn't show whether anyone has used this, or how your systems use this program.",
      "The advisory's text is its publisher's. This result comes only from running these cases.",
    ],
    evidence: [
      {
        type: "table",
        title: "The 2 cases it got wrong",
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
        ],
        meta: [],
        note: null,
      },
    ],
    run_record: {
      title: "Run record",
      command: "acme-sign verify (once per case, JSON in, JSON out), 64 cases from ecdsa_secp256r1_sha256_test.json",
      outputs: [
        {
          title: "Output summary",
          text: "advisory: CVE-2022-21449   test pack: 2026.11.1   design fingerprint: 7b06a70535ac437d660e31e54dd0f01dedf7dc784d79ae0fc64cffc34e5384cc\ncases run: 64   right: 62   wrong: 2\ntcId 168  \"Signature with special case values r=0 and s=0\"  expected: invalid  got: valid  WRONG\ntcId 171  \"Signature with special case values r=0 and s=n\"  expected: invalid  got: valid  WRONG\ncontrol (broken signer): wrong on 64 of 64 invalid cases\nreference library: 64 of 64 right\nharness: python -I demo/components/harness/driver.py    (job on stdin: verify_batch: 64 cases, one verify call per case, on acme-sign-1.4.2, control-accept-all)\nSummary written by the app from the stored run. The full raw output is in the downloaded evidence JSON.",
        },
      ],
      meta: [
        { label: "Time", value: "", time: "2026-11-17T19:57:16.374Z", tag: null },
        { label: "Duration", value: "1.4 s", tag: "measured" },
        { label: "Component", value: "acme-sign 1.4.2", tag: "demo" },
        { label: "Code", value: "the bundled demo version of acme-sign 1.4.2", tag: "demo" },
        { label: "Mode", value: "Demo mode, not isolated", tag: null },
        {
          label: "Vectors",
          value: "Project Wycheproof, C2SP/wycheproof commit dab4ea2",
          tag: "reference",
          href: "https://github.com/C2SP/wycheproof/tree/dab4ea2ed021eb633874959ca601004f3457d911/testvectors_v1",
        },
        { label: "Test pack", value: "2026.11.1 (fingerprint 7c9db0682e14...)", tag: "reference" },
      ],
    },
    locked_test: {
      title: "Test details, locked before the run",
      fields: [
        { label: "Question", lines: ["Does acme-sign reject the signatures that advisory CVE-2022-21449 describes?"] },
        { label: "Method", lines: ["Run the verify command once per case and compare its answer with the published one."] },
        {
          label: "Inputs",
          lines: [
            "64 cases from Wycheproof testvectors_v1/ecdsa_secp256r1_sha256_test.json, pinned to commit dab4ea2: 64 that must be rejected.",
            "Chosen for advisory CVE-2022-21449 by test pack 2026.11.1 (design fingerprint 7b06a70535ac), and tried on public copies before the pack was signed.",
          ],
        },
        { label: "Control", lines: ["The same cases run against a deliberately broken signer, which must get every invalid case wrong."] },
        { label: "Pass/fail rule", lines: ["Passed only if all 64 answers are right. Any wrong answer means Failed."] },
      ],
      locked_at: "2026-11-17T19:57:06.696Z",
      locked_text: "before the run started",
      fingerprint_label: "Fingerprint of these details (SHA-256)",
      fingerprint: "cfe30deeb64237591b6fce89eb66664a42adafbb7e96a2422a30af8f7a063edf",
      note: "The details can't change after locking. The run record carries the same fingerprint, so anyone can confirm the test wasn't adjusted to fit the result.",
    },
    real: false,
    advisories: {
      title: "The advisory this check is for",
      tag: "from the advisory, not a result",
      items: [
        {
          id: "CVE-2022-21449",
          text: "\u2018accepts a signature whose two numbers are zero\u2019",
          link: "A made-up advisory for a test",
          href: "https://openjdk.org/groups/vulnerability/advisories/2022-04-19",
          covered: "This check reruns the 64 published test cases that match it, from test pack 2026.11.1. The words above are the publisher's; the result comes only from the test.",
        },
      ],
    },
    fix_title: "Suggested fix",
    suggested_fix: null,
    reviewed: null,
    research: null,
    fix_line: { fix_id: "fix-ecdsa-range-check", lead: "Fix available,", rest: "code not connected", look: "plain", busy: false, button: "View in Fixes" },
  },
  result_status: null,
  after: null,
  after_status: null,
  group: "software:lib-acme-sign",
};

/** Fixes after the advisory check failed: the code fix it led to (here from a fix template, because no answer of
 * Otto's was recorded for it) and the server fix beside it. */
export const fixesWithTemplate: FixesView = {
  plan_id: 1,
  is_demo: true,
  title: "Fixes",
  subline: "Fixes for the findings in Evidence Lab. A code change is ready for review only after its proof has passed.",
  disclaimer: STANDING_LINE,
  list_title: "Open findings with a fix (2)",
  empty_text: null,
  fixes: [
    {
      id: "fix-ecdsa-range-check",
      kind: "code",
      title: "acme-sign accepts out-of-range signatures",
      list_source: "Came from 3 failed tests: Independent exam (Wycheproof), Attacker tricks (our short list), Advisory check: Blank signature accepted (CVE-2022-21449)",
      source: [
        { t: "text", v: "Came from 3 failed tests on signing component " },
        { t: "mono", v: "acme-sign 1.4.2" },
        {
          t: "text",
          v: ": Independent exam (Wycheproof), Attacker tricks (our short list) and Advisory check: Blank signature accepted (CVE-2022-21449).",
        },
      ],
      status: { key: "not_connected", word: "Code not connected", busy: false },
      labels: ["From a fix template"],
      is_demo: true,
      what: {
        label: "What it changes",
        paragraphs: [
          [
            {
              t: "text",
              v: "A fix template exists for this failure: a ready-made change for a missing range check on the two signature numbers (r and s), written for ",
            },
            { t: "mono", v: "acme-sign" },
            { t: "text", v: "'s code. Connect the code to prepare the change and prove it." },
          ],
          [
            {
              t: "text",
              v: "Otto's own change is not offered here: No recorded answer: this needs Live Otto. The fix template is offered in its place.",
            },
          ],
        ],
        server_line: "This change is for the signing program only. The server finding is separate and still open.",
      },
      proof: {
        state: "not_started",
        badge: null,
        muted: null,
        text: "Not started. It starts by itself once the code is connected: every locked test in your plan is rerun on the changed code. This takes about a minute.",
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
      advisories: null,
      change_box: null,
      group: "encryption",
      group_label: "Encryption tests",
      came_from_links: [
        { label: "Independent exam (Wycheproof)", link: { page: "evidence", item: "test-3" } },
        { label: "Attacker tricks (our short list)", link: { page: "evidence", item: "test-4" } },
        { label: "Advisory check", link: { page: "evidence", item: "test-6" } },
      ],
      fix_state: "open",
    },
    {
      id: "fix-tls-versions",
      kind: "text",
      title: "Server accepts TLS 1.2",
      list_source: "Came from 1 failed test: Old TLS versions",
      source: [
        { t: "text", v: "Came from 1 failed test on server " },
        { t: "mono", v: "localhost:47135" },
        { t: "text", v: ": Old TLS versions. The file claims TLS 1.3 only." },
      ],
      status: { key: "text_only", word: "Ready to try", busy: false },
      labels: [],
      is_demo: true,
      what: {
        label: "What it suggests",
        paragraphs: [
          [
            {
              t: "text",
              v: "A server setting, not a code change: stop accepting TLS 1.2, or keep it with strong settings only and correct the scanner file. The suggestion below says where the setting lives and gives two ways to do it.",
            },
          ],
        ],
        server_line: null,
      },
      proof: {
        state: "none",
        badge: null,
        muted: null,
        text: "In the change box below: a try on a test copy of the demo server comes first, then the approvals, then Apply.",
      },
      pull_request: null,
      approvers: {
        text: "Pick them in the change box below. The app changes the demo server only when a person presses Apply.",
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
          suggestion: {
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
                  setting: "the security policy (also called a TLS or SSL policy) on the load balancer's HTTPS or TLS listener, the part that accepts incoming connections",
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
                {
                  place: "nginx",
                  code: "ssl_protocols TLSv1.2 TLSv1.3;\nssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;",
                },
                {
                  place: "Apache",
                  code: "SSLProtocol -all +TLSv1.2 +TLSv1.3\nSSLCipherSuite ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305",
                },
                { place: "AWS Application or Network Load Balancer (security policy)", code: "ELBSecurityPolicy-TLS13-1-2-Res-2021-06" },
              ],
            },
          },
        },
      ],
      sections_note: null,
      change_box: {
        id: "tls:server:localhost:47135",
        title: "Your change: switch TLS 1.2 off on localhost:47135",
        badge: { label: "Ready to try", look: "neutral" },
        intro: [
          {
            t: "text",
            v: "Built from the failed Old TLS versions test. It switches TLS 1.2 (and anything older) off on the demo server, so it accepts TLS 1.3 only, as the file claims. It can be tried and applied on the demo server on localhost:47135.",
          },
        ],
        steps: [
          { key: "built", label: "Built", state: "done", text: "from the finding" },
          { key: "tried", label: "Tried on a test copy", state: "off", text: "not yet" },
          { key: "approvals", label: "Approvals", state: "off", text: "not asked yet" },
          { key: "applied", label: "Apply", state: "off", text: "not applied" },
          { key: "measured", label: "Measured after", state: "off", text: "the app measures again by itself" },
        ],
        sections: [
          {
            kind: "table",
            title: "What it changes on the demo server on localhost:47135",
            columns: ["Setting", "Now", "With the change"],
            rows: [
              [[{ t: "text", v: "Key-exchange groups" }], [{ t: "text", v: "P-256" }], [{ t: "text", v: "P-256 (no change)" }]],
              [[{ t: "text", v: "TLS versions" }], [{ t: "text", v: "1.2 and 1.3" }], [{ t: "text", v: "1.3" }]],
              [[{ t: "text", v: "Certificate" }], [{ t: "text", v: "ECDSA P-256" }], [{ t: "text", v: "ECDSA P-256 (no change)" }]],
            ],
          },
          {
            kind: "lines",
            title: "The same change on your own server software",
            rows: [
              { place: "nginx", lead: "Checked on nginx 1.31.8 with OpenSSL 3.5.9:", code: "ssl_protocols TLSv1.3;" },
              { place: "Apache", lead: "Checked on Apache 2.4.71 with OpenSSL 3.5.9:", code: "SSLProtocol -all +TLSv1.3" },
              {
                place: "Your own application",
                lead: "Not checked on real software. For example:",
                code: "SSL_CTX_set_min_proto_version(ctx, TLS1_3_VERSION);",
              },
            ],
            note: "Change every existing line rather than adding another one, then reload the server.",
          },
          {
            kind: "text",
            title: "Before you change it",
            paragraphs: [[{ t: "text", v: "Older clients and partner systems that can't use TLS 1.3 will no longer be able to connect." }]],
          },
        ],
        try: null,
        approvals: {
          title: "Who must approve before Apply",
          picker: {
            options: [
              { id: "you", name: "You", demo: false, checked: true },
              { id: "a", name: "Demo reviewer A", demo: true, checked: false },
              { id: "b", name: "Demo reviewer B", demo: true, checked: false },
            ],
            button: "Ask for approval",
            enabled: false,
            reason: "A try on a test copy must pass before approval can be asked for.",
          },
          rows: [],
          footnote: "This version has one login and no separate accounts. Whoever is at the keyboard records each approval, under the name shown.",
        },
        applied: null,
        buttons: [
          { action: "try", label: "Try on a test copy", primary: true, enabled: true, reason: null },
          {
            action: "apply",
            label: "Apply to localhost:47135",
            primary: false,
            enabled: false,
            reason: "Apply unlocks after a try on a test copy has passed.",
          },
          { action: "download", label: "Download change", primary: false, enabled: true, reason: null },
        ],
        note: "The app changes a system only when a person presses Apply, after a passing try on a test copy and every approval asked for. It measures again right after, and Roll back is then always there.",
        busy: false,
      },
      advisories: null,
      group: "encryption",
      group_label: "Encryption tests",
      came_from_links: [{ label: "Old TLS versions", link: { page: "evidence", item: "test-1" } }],
      fix_state: "open",
    },
  ],
  busy: false,
  groups: [
    {
      key: "verification",
      label: "Verification",
      question: "Is the scanner file true?",
      counts: { open: 0, in_progress: 0, done: 0 },
      fix_ids: [],
      empty_text: "Verification has no fixes of its own. A false claim's fix sits with the test that checks it, under Encryption tests.",
      also: [],
    },
    {
      key: "encryption",
      label: "Encryption tests",
      question: "Is the encryption built right?",
      counts: { open: 2, in_progress: 0, done: 0 },
      fix_ids: ["fix-ecdsa-range-check", "fix-tls-versions"],
      empty_text: null,
      also: [],
    },
    {
      key: "migration",
      label: "Migration",
      question: "Where does each system stand on the move to post-quantum, and what must change?",
      counts: { open: 0, in_progress: 0, done: 0 },
      fix_ids: [],
      empty_text: "No system's plan needs a change yet.",
      also: [],
    },
    {
      key: "dependencies",
      label: "Dependencies",
      question: "What can your libraries do?",
      counts: { open: 0, in_progress: 0, done: 0 },
      fix_ids: [],
      empty_text: "No library blocks a track.",
      also: [],
    },
  ],
};

/** The Overview's next step when the sample was taken (the claims were not verified yet). */
export const nextStepVerify: AssessmentView["next_step"] = { page: "inventory/import", label: "Verify claims", text: "Check each claim in the file against the real system." };

// ---- Not among the samples: states the backend words in the same way, written with its own sentences

/** The Overview's next step once a test of an installed pack fits this assessment and is not in its plan. */
export const nextStepAdvisories: AssessmentView["next_step"] = {
  page: "advisories",
  label: "Open advisories",
  text: "1 new advisory check is ready to add from the installed test packs. Adding them runs nothing.",
};

/** After Check for updates met files it would not take: each file with the backend's one plain reason. */
export const ottoRefused: OttoSettingsView = {
  ...ottoInstalledOne,
  packs: {
    ...ottoInstalledOne.packs,
    checked_line: "A newer pack is in the updates folder, but it does not follow the installed one.",
    refused: [
      { file: "2026.11.9.json", reason: "The file is not a signed test pack." },
      { file: "2026.11.3.json", reason: "Pack 2026.11.3 does not follow the installed pack 2026.11.1. Packs install in order." },
    ],
    update: null,
  },
};

/** An API key is on this computer and Use live Claude is off. */
export const ottoLiveOff: OttoSettingsView = {
  ...ottoLiveOn,
  answers: ANSWERS_FOR_A_TEST,
  live: {
    ...ottoLiveOn.live,
    switch: { ...ottoLiveOn.live.switch, on: false },
    status_line: "Live Otto is off: Otto works on the answers recorded during the build.",
  },
};

/** Use live Claude was left on and the key has since gone from this computer: it can still be turned off. */
export const ottoLiveOnNoKey: OttoSettingsView = {
  ...ottoInstalledTwo,
  live: {
    ...LIVE_NO_KEY,
    switch: { ...LIVE_NO_KEY.switch, on: true },
    status_line: "Live Otto is switched on, but no API key is set on this computer, so Otto works on the answers recorded during the build.",
  },
};

/** A pack built on this computer by the live research command: its line and its signer say so. */
export const packMadeHere: OttoPackCard = {
  ...PACK_TWO,
  signer: "A key made on this computer by the live research command",
  made_here: true,
  line: "Pack 2026.11.2, built 17 November 2026: 2 advisories, 1 test. Made on this computer.",
};
