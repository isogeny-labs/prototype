import type { AssistantAction, AssistantConfirm, AssistantDecision, AssistantEntry, AssistantStep, AssistantTab, AssistantThread, AssistantView, OttoProposal } from "../api";
import { quietAssistant } from "./fixtures";
import { acceptedProposal, proposal, rejectedProposal } from "./proposalFixtures";

/** Phase 6a: what the Otto panel reads, for screen tests. Every word here stands in for the backend's. */

export const HOME: Record<OttoProposal["kind"], { page: string; label: string; thread: AssistantThread }> = {
  check: { page: "advisories", label: "Advisories", thread: "testing" },
  fix: { page: "fixes", label: "Fixes", thread: "fixing" },
  plan: { page: "migration/systems", label: "Systems", thread: "planning" },
  dependency: { page: "migration/dependencies", label: "Dependencies", thread: "fixing" },
};

const ACCEPT_LINES: Record<OttoProposal["kind"], string[]> = {
  check: ["Adds this check to the test plan, as “+ Add test” would.", "Runs nothing.", "You can undo it until the check has run."],
  fix: ["Records your decision to take this fix.", "Runs nothing and changes nothing on any system.", "You can undo it until the fix has run or been applied."],
  plan: ["Adds this to the migration plan as something to fix first.", "Runs nothing and changes nothing on any system.", "You can undo it until a newer result of the check passes."],
  dependency: ["Marks this library “update first”.", "Runs nothing and changes nothing on any system.", "You can undo it at any time."],
};

function confirmOf(kind: OttoProposal["kind"], key: AssistantDecision["key"], label: string): AssistantConfirm {
  const lines =
    key === "accept"
      ? ACCEPT_LINES[kind]
      : key === "reject"
        ? ["It is not deleted: it stays on the record as “Not added”, with your reason, and can be taken up again later.", "Runs nothing."]
        : key === "undo"
          ? ["Takes your accept back.", "Runs nothing. The proposal is open for a decision again."]
          : ["Opens this proposal for a decision again.", "Runs nothing. The earlier decisions stay on the record."];
  const titles = { accept: `Accept this ${kind}?`, reject: `Reject this ${kind}?`, undo: "Undo this accept?", reconsider: `Take this ${kind} up again?` };
  return {
    title: titles[key],
    lines,
    names: `This is the ${label} button on ${HOME[kind].label}.`,
    confirm: "Confirm",
    cancel: "Cancel",
    reason: key === "reject" ? { label: "Reason (optional, one short line)", max: 300 } : null,
  };
}

/** A suggestion: one of Otto's proposals as the panel shows it, with the Confirm step of each button its page offers. */
export function suggestion(of: OttoProposal, over: Partial<AssistantEntry> = {}): AssistantEntry {
  return {
    id: of.id,
    kind: "suggestion",
    what: `suggestion:${of.kind}`,
    thread: HOME[of.kind].thread,
    mark: of.label,
    title: of.title,
    text: of.why,
    at: of.proposed_at,
    badge: { label: of.status.word, tone: of.status.tone },
    where: { label: `On ${HOME[of.kind].label}`, link: of.link },
    links: [],
    proposal: of,
    decisions: of.buttons.map((b) => ({ ...b, confirm: b.can ? confirmOf(of.kind, b.key, b.label) : null })),
    step: null,
    open_item: false,
    ...over,
  };
}

const NO_ACTION: AssistantAction = {
  type: "open",
  plan_id: null,
  import_id: null,
  item_id: null,
  fix_id: null,
  change: null,
  row: null,
  version: null,
  component: null,
  reviewers: null,
  link: null,
};

/** A next step: a button of a page, under that button's own name. */
export function nextStep(
  what: string,
  title: string,
  pageLabel: string,
  action: Partial<AssistantAction> & Pick<AssistantAction, "type">,
  over: Partial<AssistantStep> = {},
  entry: Partial<AssistantEntry> = {},
): AssistantEntry {
  const can = over.can ?? true;
  const step: AssistantStep = {
    needs: "confirm",
    action: { ...NO_ACTION, ...action },
    can,
    blocked_reason: null,
    running: false,
    progress: null,
    confirm: can
      ? { title: `${title}?`, lines: [`Presses ${title}.`, "It changes nothing on any system."], names: `This is the ${title} button on ${pageLabel}.`, confirm: "Confirm", cancel: "Cancel", reason: null }
      : null,
    ...over,
  };
  return {
    id: `${what}:${title}:${action.item_id ?? action.fix_id ?? action.row ?? action.version ?? ""}`,
    kind: "next",
    what,
    thread: "testing",
    mark: "Next step",
    title,
    text: "A button of the page that is worth pressing now.",
    at: null,
    badge: null,
    where: { label: `On ${pageLabel}`, link: { page: "checks", item: null } },
    links: [],
    proposal: null,
    decisions: [],
    step,
    open_item: false,
    ...entry,
  };
}

export function meaning(over: Partial<AssistantEntry> = {}): AssistantEntry {
  return {
    id: "meaning:result:12",
    kind: "meaning",
    what: "meaning:result",
    thread: "testing",
    mark: "What this means",
    title: "Bad signatures",
    text: "acme-sign 1.4.2 accepted 2 of our 14 forged signatures. A fix is suggested: see Fixing.",
    at: "2026-11-18T10:05:00Z",
    badge: { label: "Failed", tone: "fail" },
    where: null,
    links: [
      { label: "See the evidence", link: { page: "evidence", item: "test-4" } },
      { label: "View in Fixes", link: { page: "fixes", item: "fix-ecdsa-range-check" } },
    ],
    proposal: null,
    decisions: [],
    step: null,
    open_item: false,
    ...over,
  };
}

export function result(n: number, label = "Passed", tone: "pass" | "fail" = "pass"): AssistantEntry {
  return meaning({
    id: `result:${n}`,
    kind: "result",
    what: "result",
    mark: "Result",
    title: `Test ${n} on acme-sign 1.4.2`,
    text: `What test ${n} found.`,
    at: `2026-11-18T10:${String(10 + n).padStart(2, "0")}:00Z`,
    badge: { label, tone },
    links: [{ label: "See the evidence", link: { page: "evidence", item: `test-${n}` } }],
  });
}

export function tab(key: AssistantThread, over: Partial<AssistantTab> = {}): AssistantTab {
  const labels = { testing: "Testing", fixing: "Fixing", planning: "Planning" };
  return { key, label: labels[key], waiting: 0, mark: `${key}-mark-1`, so_far_title: "This thread so far", so_far: [], so_far_empty: "Nothing has been decided or run in this thread yet.", ...over };
}

export function panel(page: string, over: Partial<AssistantView> = {}): AssistantView {
  const labels: Record<string, string> = { checks: "Checks", advisories: "Advisories", evidence: "Evidence", fixes: "Fixes", overview: "Overview", "migration/systems": "Systems", "migration/dependencies": "Dependencies", "inventory/import": "Import", "inventory/verify": "Verify", "migration/roadmap": "Roadmap" };
  const threads: Record<string, AssistantThread | null> = { checks: "testing", advisories: "testing", evidence: "testing", "inventory/import": "testing", "inventory/verify": "testing", fixes: "fixing", "migration/dependencies": "fixing", "migration/systems": "planning", "migration/roadmap": "planning", overview: null };
  return quietAssistant({ page, page_label: labels[page] ?? page, thread: threads[page] ?? null, ...over });
}

export function onPage(entries: AssistantEntry[]): AssistantView["on_page"] {
  return { title: "On this page", entries, empty: entries.length ? null : "Nothing is suggested on this page.", empty_link: null };
}

export function elsewhere(lines: AssistantView["elsewhere"]["lines"]): AssistantView["elsewhere"] {
  const count = lines.reduce((n, line) => n + line.count, 0);
  return { title: `Elsewhere: ${count} more`, count, lines, empty: null };
}

// ---- the proposals of the three threads, as their pages word them

export const checkProposal: OttoProposal = proposal();
export const checkAccepted: OttoProposal = acceptedProposal();
export const checkRejected: OttoProposal = rejectedProposal("Not this quarter");

export const fixProposal: OttoProposal = proposal({
  id: "fix-code-otto-cve-2022-21449",
  kind: "fix",
  kind_label: "fix",
  title: "Reject signatures whose r or s is out of range (acme-sign)",
  why: "The advisory check for CVE-2022-21449 (Missing ECDSA signature range check) failed on acme-sign 1.4.2, which is your own code.",
  why_label: "Why it is proposed",
  link: { page: "fixes", item: "fix-otto-cve-2022-21449" },
});

export const planProposal: OttoProposal = proposal({
  id: "plan-0123456789ab",
  kind: "plan",
  kind_label: "plan change",
  title: "Fix acme-sign 1.4.2 before its signatures move to post-quantum",
  why: "acme-sign 1.4.2 gave the wrong answer on 3 published cases of the kind CVE-2022-21449 describes.",
  why_label: "Why it is proposed",
  link: { page: "migration/systems", item: "software:lib-acme-sign" },
});

export const dependencyProposal: OttoProposal = proposal({
  id: "dep-0123456789ab",
  kind: "dependency",
  kind_label: "dependency update",
  title: "Update elliptic 6.5.6 to 6.5.7 before the move",
  why: "Your dependency list has elliptic 6.5.6. Advisory CVE-2024-42460 is about elliptic, and its publisher names 6.5.7 as the fixed version.",
  why_label: "Why it is proposed",
  link: { page: "migration/dependencies", item: "row-5" },
});

/** The same proposal after a decision, as its page then words it. */
export function decided(of: OttoProposal, how: "accepted" | "rejected", reason = "Not this quarter"): OttoProposal {
  const base = how === "accepted" ? acceptedProposal() : rejectedProposal(reason);
  const word = how === "accepted" ? (of.kind === "check" ? "Added" : "Accepted") : base.status.word;
  return { ...base, id: of.id, kind: of.kind, kind_label: of.kind_label, title: of.title, why: of.why, why_label: of.why_label, link: of.link, status: { ...base.status, word } };
}
