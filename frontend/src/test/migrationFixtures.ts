import type {
  MigrationChooseBox,
  MigrationLine,
  MigrationOption,
  MigrationSettingField,
  MigrationStatus,
  MigrationSystem,
  MigrationView,
  RichText,
} from "../api";
import { DISCLAIMER, result } from "./fixtures";

// A realistic Migration view for the phase 4a demo file (migration-demo.csv): five local test servers and two
// signing programs, worded as in the approved mockups. Built from small helpers so each system reads clearly.

export const HYBRID_FIX = "fix-pq-hybrid-localhost-8452";
export const SIGN_FIX = "fix-pq-sign-acme-sign-1.4.2";

const t = (v: string): RichText => [{ t: "text", v }];
const tagged = (v: string, tag: string): RichText => [
  { t: "text", v: `${v} ` },
  { t: "tag", v: tag },
];
const line = (text: RichText | string, fix_id: string | null = null): MigrationLine => ({
  text: typeof text === "string" ? t(text) : text,
  fix_id,
});

const HYBRID: MigrationStatus = { code: "hybrid", label: "Hybrid" };
const PQ_ONLY: MigrationStatus = { code: "pq_only", label: "Post-quantum only" };
const CLASSICAL: MigrationStatus = { code: "classical", label: "Classical" };
const COULDNT: MigrationStatus = { code: "couldnt_check", label: "Couldn't check" };

function fields(
  lifespan: [string, string],
  exposure: [string, string],
  canChange: [string, string],
  enabled = true,
): MigrationSettingField[] {
  return [
    {
      field: "lifespan",
      label: "Data lifespan",
      help: "How long must it stay private or trusted?",
      value: lifespan[0],
      options: [
        { value: "short", label: "Short" },
        { value: "long", label: "Long-lived" },
      ],
      source: lifespan[1],
      enabled,
    },
    {
      field: "exposure",
      label: "Exposure",
      help: "Who can reach it or record its traffic?",
      value: exposure[0],
      options: [
        { value: "internet", label: "Internet-facing" },
        { value: "internal", label: "Internal" },
      ],
      source: exposure[1],
      enabled,
    },
    {
      field: "can_change",
      label: "Can it be changed?",
      help: "Can its software or settings be updated?",
      value: canChange[0],
      options: [
        { value: "yes", label: "Yes" },
        { value: "no", label: "No" },
      ],
      source: canChange[1],
      enabled,
    },
  ];
}

const settingsOf = (f: MigrationSettingField[]): MigrationSystem["settings"] => ({
  title: "About this system",
  intro: "The recommendation uses these three settings. Change any that is wrong.",
  fields: f,
});

function chooseBox(title: string, needsReason: boolean, keep: boolean): MigrationChooseBox {
  return {
    title: `Choose “${title}”`,
    needs_reason: needsReason,
    reason_label: needsReason ? "Your reason (needed, because this differs from the recommendation)" : "Your reason (optional)",
    review_date: keep
      ? {
          label: "Review date",
          value: "2027-11-14",
          min: "2026-11-15",
          max: "2030-12-31",
          help: "Starts at 12 months. Latest allowed: 31 Dec 2030, NIST's date.",
        }
      : null,
    save: "Save choice",
    cancel: "Cancel",
    note: "Your choice is recorded with the time and is never overwritten. The roadmap follows it.",
  };
}

const manage = (text: string) => ({ title: "To manage", lines: [line(text)] });

/** The four options of a server; `recommended` gets the tag and the sky border. */
function serverOptions(recommended: MigrationOption["key"], hybridBlocker: MigrationLine | null): MigrationOption[] {
  const opt = (
    key: MigrationOption["key"],
    title: string,
    what: string,
    sections: MigrationOption["sections"],
  ): MigrationOption => ({
    key,
    title,
    tags: key === recommended ? ["Recommended"] : [],
    highlighted: key === recommended,
    what,
    sections,
    not_offered: null,
    choose_label: "Choose this option",
    choose: chooseBox(title, key !== recommended, key === "keep"),
  });
  return [
    opt("keep", "Keep classical for now", "No change now. It always has a review date, never “forever”.", [
      { title: "Cost", lines: [line(tagged("Nothing changes. Key shares stay 32 bytes", "measured"))] },
      { title: "Blockers", lines: [line("None measured.")] },
      manage("Algorithms 2 · Key sets 1 · Libraries 1"),
    ]),
    opt("hybrid", "Hybrid", "Post-quantum key exchange added to the classical one. Clients that can't do it keep working.", [
      {
        title: "Cost",
        lines: [
          line(tagged("Key shares grow from 32 to 1,216 bytes (client) and 1,120 bytes (server)", "published: FIPS 203 + X25519")),
          line("Plainly: two algorithms in every key exchange, two key shares, bigger messages, more to keep up to date."),
        ],
      },
      { title: "Blockers", lines: [hybridBlocker ?? line("None measured.")] },
      manage("Algorithms 3 · Key sets 1, plus 2 key shares per connection · Libraries 1 (a version with ML-KEM)"),
    ]),
    opt("full_pq", "Full post-quantum", "Post-quantum algorithms only. Every connected system must support them, and there is no classical fallback.", [
      { title: "Cost", lines: [line(tagged("Key shares 1,184 and 1,088 bytes; certificate key 1,952 bytes", "published: FIPS 203, FIPS 204"))] },
      { title: "Blockers", lines: [line(tagged("1. Every client must support it. This app can't see your clients", "not measured"))] },
      manage("Algorithms 2 · Key sets 1 (new) · Libraries: this server's and every client's"),
    ]),
    opt(
      "wrap",
      "Wrap the connection",
      "A gateway or network encryptor in front does the post-quantum part. It protects the connection only, not cryptography inside the application.",
      [
        { title: "Cost", lines: [line(tagged("Not measured: it depends on the gateway", "not measured"))] },
        { title: "Blockers", lines: [line("None measured. A gateway has to be bought or built, and run.")] },
        manage("Algorithms: this server's 2, plus the gateway's · Key sets +1 · Libraries +1"),
      ],
    ),
  ];
}

const serverCost: MigrationSystem["cost"] = {
  title: "Cost of going post-quantum",
  intro: "Sizes and times for this server today, and what each step would change. Every number says where it came from.",
  columns: ["", "Today (classical)", "Hybrid", "Full post-quantum"],
  rows: [
    {
      label: "Key share, client to server",
      cells: [tagged("32 bytes", "measured"), tagged("1,216 bytes", "published: FIPS 203 + X25519"), tagged("1,184 bytes", "published: FIPS 203")],
    },
    {
      label: "Handshake time, median of 10",
      cells: [tagged("1.3 ms", "measured"), tagged("+0.2 ms", "measured on our test server"), t("not measured")],
    },
  ],
  note: "This server doesn't offer hybrid yet, so the hybrid column can't be measured on it.",
};

function today(sentence: string, facts: [string, RichText][], extra: Partial<MigrationSystem["today"]> = {}): MigrationSystem["today"] {
  return {
    title: "Today",
    sentence,
    file_note: null,
    facts: facts.map(([label, value]) => ({ label, value })),
    control_line: "Control: the same check read our hybrid test server as Hybrid and our classical test server as Classical, as expected.",
    details_label: "Details and evidence",
    result: null,
    ...extra,
  };
}

function rec(title: string, reasons: RichText[], evidence: RichText | null = null): MigrationSystem["recommendation"] {
  return {
    title,
    tag: "from fixed rules, no AI model",
    reasons,
    evidence,
    evidence_link: evidence ? "See the evidence" : null,
    none_text: null,
  };
}

const CHOICES_NOTE = "Until you choose, the roadmap uses the recommendation and says so.";

function server(
  port: number,
  status: MigrationStatus,
  plan_line: string,
  rest: Partial<MigrationSystem> & Pick<MigrationSystem, "today" | "recommendation" | "options">,
): MigrationSystem {
  return {
    key: `server:localhost:${port}`,
    kind_label: "Server",
    name: `localhost:${port}`,
    status,
    plan_line,
    measuring: null,
    settings: settingsOf(fields(["long", "from the file"], ["internet", "from the file"], ["yes", "assumed"])),
    cost: serverCost,
    options_title: "The four options",
    choice: null,
    choices_note: CHOICES_NOTE,
    ...rest,
  };
}

export const hybridEvidence = {
  ...result(41, "offered", "Hybrid", "pass", "The server asked for X25519MLKEM768 in its first answer."),
  component: null,
};

const s8451 = server(8451, HYBRID, "Plan: Hybrid · already there", {
  today: today("It asked for a hybrid key exchange, and a classical-only client still connects, so it is Hybrid.", [
    ["Hybrid key exchange", tagged("Offered: X25519MLKEM768", "measured")],
    ["A classical-only client connects", tagged("Yes, with TLS 1.3", "measured")],
  ]),
  recommendation: rec("Recommended: Hybrid, already in place", [t("It measured Hybrid.")]),
  options: serverOptions("hybrid", null).map((o) => (o.key === "hybrid" ? { ...o, tags: ["In place today"], choose: null } : o)),
});

const s8452 = server(8452, CLASSICAL, "Plan: Hybrid · Phase 1", {
  today: today(
    "It refused every post-quantum key exchange we offered and completed a classical handshake, so it is Classical.",
    [
      ["Hybrid key exchange", tagged("Refused: X25519MLKEM768 and two others", "measured")],
      ["Classical key exchange", tagged("Accepted: X25519", "measured")],
      ["Certificate", tagged("ECDSA P-256", "measured")],
    ],
    { file_note: "The file says: this server is Hybrid. Verify marked that claim False.", result: hybridEvidence },
  ),
  recommendation: rec(
    "Recommended: Hybrid",
    [
      [
        { t: "text", v: "Long-lived data " },
        { t: "tag", v: "from the file" },
        { t: "text", v: ": traffic recorded today could be decrypted later." },
      ],
      tagged("NIST dates: deprecated after 2030 and disallowed after 2035", "reference: NIST IR 8547"),
    ],
    tagged("Evidence: this server measured Classical", "measured"),
  ),
  options: serverOptions("hybrid", line(tagged("1. It doesn't offer a hybrid key exchange yet", "measured"), HYBRID_FIX)),
});

const s8453 = server(8453, CLASSICAL, "Plan: Keep classical · review 14 Nov 2027", {
  settings: settingsOf(fields(["short", "from the file"], ["internal", "from the file"], ["yes", "assumed"])),
  today: today("It refused every post-quantum key exchange we offered and completed a classical handshake, so it is Classical.", [
    ["Classical key exchange", tagged("Accepted: X25519", "measured")],
  ]),
  recommendation: rec("Recommended: Keep classical for now", [t("Short-lived data, internal.")]),
  options: serverOptions("keep", null),
});

const s8454 = server(8454, CLASSICAL, "Plan: Wrap the connection", {
  settings: settingsOf(fields(["long", "from the file"], ["internal", "from the file"], ["no", "from the file"])),
  today: today("It only speaks TLS 1.2 with a classical key exchange, so it is Classical.", [
    ["TLS versions", tagged("1.2 only", "measured")],
  ]),
  recommendation: rec("Recommended: Wrap the connection", [t("It can't be changed and its data is long-lived.")]),
  options: serverOptions("wrap", line(tagged("1. TLS 1.3 is off", "measured"))),
});

const s8455 = server(8455, PQ_ONLY, "Plan: Full post-quantum · already there", {
  today: today("It accepted ML-KEM by itself and refused the hybrid and the classical hello, so it is Post-quantum only.", [
    ["ML-KEM by itself", tagged("Accepted: ML-KEM-768", "measured")],
    ["Certificate", tagged("ML-DSA-65", "measured")],
  ]),
  recommendation: rec("Recommended: Full post-quantum, already in place", [t("It measured Post-quantum only.")]),
  options: serverOptions("full_pq", null),
});

const signOptions: MigrationOption[] = [
  {
    key: "keep",
    title: "Keep classical for now",
    tags: [],
    highlighted: false,
    what: "No change now. It always has a review date, never “forever”.",
    sections: [{ title: "Cost", lines: [line("Nothing changes.")] }, manage("Algorithms 1 · Key sets 1 · Libraries 1")],
    not_offered: null,
    choose_label: "Choose this option",
    choose: chooseBox("Keep classical for now", true, true),
  },
  {
    key: "hybrid",
    title: "Hybrid: sign with both",
    tags: ["Recommended"],
    highlighted: true,
    what: "Every signature is made twice: ECDSA P-256 and ML-DSA-65. Checkers that only know ECDSA keep working.",
    sections: [
      { title: "Cost", lines: [line(tagged("Signatures grow from 71 to 3,380 bytes", "measured + published"))] },
      { title: "Blockers", lines: [line(tagged("1. It can't make post-quantum signatures", "measured"), SIGN_FIX)] },
      manage("Algorithms 2 · Key sets 2 · Libraries 1, with ML-DSA added"),
    ],
    not_offered: null,
    choose_label: "Choose this option",
    choose: chooseBox("Hybrid: sign with both", false, false),
  },
  {
    key: "full_pq",
    title: "Full post-quantum",
    tags: [],
    highlighted: false,
    what: "ML-DSA-65 only. Every system that checks these signatures must support it.",
    sections: [{ title: "Blockers", lines: [line(tagged("1. It can't make post-quantum signatures", "measured"))] }],
    not_offered: null,
    choose_label: "Choose this option",
    choose: chooseBox("Full post-quantum", true, false),
  },
  {
    key: "wrap",
    title: "Wrap the connection",
    tags: [],
    highlighted: false,
    what: "A gateway protects a connection, not signatures made inside the application.",
    sections: [],
    not_offered: "Doesn't apply to a signing program.",
    choose_label: "Choose this option",
    choose: null,
  },
];

const sign142: MigrationSystem = {
  key: "software:acme-sign-1.4.2",
  kind_label: "Signing program",
  name: "acme-sign 1.4.2",
  status: { code: "classical", label: "Classical: ECDSA P-256" },
  plan_line: "Plan: Hybrid · Phase 2",
  measuring: null,
  today: today(
    "It says it signs with ECDSA P-256, and a signature it made checked out as ECDSA P-256 in an independent library, so it is Classical.",
    [["Signs with", tagged("ECDSA P-256", "measured")]],
    { control_line: null },
  ),
  settings: settingsOf(fields(["long", "from the file"], ["internal", "assumed"], ["yes", "assumed"])),
  cost: {
    title: "Cost of going post-quantum",
    intro: "Sizes and times for this program today.",
    columns: ["", "Today (ECDSA P-256)", "Hybrid: both signatures", "Full post-quantum (ML-DSA-65)"],
    rows: [{ label: "Signature size", cells: [tagged("71 bytes", "measured"), tagged("3,380 bytes", "measured + published"), tagged("3,309 bytes", "published: FIPS 204")] }],
    note: null,
  },
  recommendation: rec("Recommended: Hybrid: sign with both", [t("Long-lived signatures.")]),
  options_title: "The four options",
  options: signOptions,
  choice: null,
  choices_note: CHOICES_NOTE,
};

const sign99: MigrationSystem = {
  key: "software:acme-sign-9.9",
  kind_label: "Signing program",
  name: "acme-sign 9.9",
  status: COULDNT,
  plan_line: "No plan yet: status not measured",
  measuring: null,
  today: today("Couldn't check: only our own demo components can run in this version.", [], { control_line: null }),
  settings: settingsOf(fields(["long", "assumed"], ["internal", "assumed"], ["yes", "assumed"])),
  cost: null,
  recommendation: {
    title: "No recommendation yet",
    tag: null,
    reasons: [],
    evidence: null,
    evidence_link: null,
    none_text: "There is no recommendation until its status can be measured.",
  },
  options_title: "The four options",
  options: [],
  choice: null,
  choices_note: CHOICES_NOTE,
};

export const migrationSystems: MigrationSystem[] = [s8451, s8452, s8453, s8454, s8455, sign142, sign99];

const row = (
  s: MigrationSystem,
  option: string,
  note: MigrationLine,
  plan_tag: string | null = "recommended, not yet chosen by you",
) => ({ system_key: s.key, kind_label: s.kind_label, name: s.name, option, plan_tag, note });

export const migrationView: MigrationView = {
  plan_id: 1,
  import_id: 7,
  is_demo: true,
  title: "Migration plan",
  subline: [
    { t: "text", v: "Where each system in " },
    { t: "mono", v: "migration-demo.csv" },
    { t: "text", v: " stands on the move to post-quantum cryptography, what each option costs, and a plan." },
  ],
  disclaimer: DISCLAIMER,
  busy: false,
  measure: { label: "Measure again", enabled: true, blocked_reason: null, progress_text: null },
  tabs: { systems: "Systems · 7", roadmap: "Roadmap" },
  list_title: "Systems in the file (7)",
  empty_text: null,
  systems: migrationSystems,
  roadmap: {
    intro: "Built from your choices: 0 of 7 chosen, so the rest use the recommendation.",
    download: { label: "Download evidence", can_start: true, blocked_reason: null },
    bands: [
      {
        key: "already",
        title: "Already there",
        sub: "Measured in place. Nothing to do now.",
        look: "plain",
        rows: [
          row(s8451, "Hybrid", line(tagged("Offers X25519MLKEM768; a classical-only client still connects", "measured"))),
          row(s8455, "Full post-quantum", line(tagged("Accepts only ML-KEM-768, with an ML-DSA-65 certificate", "measured"))),
        ],
      },
      {
        key: "phase1",
        title: "Phase 1",
        sub: "Hybrid key exchange on internet-facing, long-lived systems.",
        look: "highlight",
        rows: [row(s8452, "Hybrid", line("To do: turn on hybrid key exchange.", HYBRID_FIX))],
      },
      {
        key: "phase2",
        title: "Phase 2",
        sub: "Hybrid or post-quantum on the other systems, once their blockers are fixed.",
        look: "plain",
        rows: [row(sign142, "Hybrid: sign with both", line(tagged("Blocker: it can't make post-quantum signatures", "measured"), SIGN_FIX))],
      },
      {
        key: "later",
        title: "Later",
        sub: "Kept classical for now, each with a review date.",
        look: "plain",
        rows: [row(s8453, "Keep classical for now", line(tagged("Review by 14 Nov 2027", "assumed: 12 months")))],
      },
      {
        key: "wrapped",
        title: "Wrapped",
        sub: "Protected at the connection by a gateway. Shown separately.",
        look: "plain",
        rows: [row(s8454, "Wrap the connection", line("It can't be changed. Protects the connection only."))],
      },
      {
        key: "not_placed",
        title: "Not placed yet",
        sub: "The status couldn't be measured, so there is no plan.",
        look: "dashed",
        rows: [row(sign99, "No option yet", line("Couldn't check: only our own demo components can run in this version."), null)],
      },
    ],
  },
};

/** The same view while a measurement runs: settings locked, one system waiting, one running. */
export const measuringView: MigrationView = {
  ...migrationView,
  busy: true,
  measure: {
    label: "Measure again",
    enabled: false,
    blocked_reason: "A measurement is running.",
    progress_text: "Measuring: 2 of 7 systems finished.",
  },
  systems: migrationSystems.map((s, i) => ({
    ...s,
    settings: { ...s.settings, fields: s.settings.fields.map((f) => ({ ...f, enabled: false })) },
    measuring:
      i === 0
        ? { status: "running", status_text: "Running", progress: { text: "hello 2 of 3", percent: null } }
        : { status: "waiting", status_text: "Waiting", progress: null },
  })),
  roadmap: { ...migrationView.roadmap, download: { ...migrationView.roadmap.download, can_start: false, blocked_reason: "A measurement is running." } },
};

/** Replaces one system in a view. */
export function withSystem(view: MigrationView, key: string, change: Partial<MigrationSystem>): MigrationView {
  return { ...view, systems: view.systems.map((s) => (s.key === key ? { ...s, ...change } : s)) };
}
