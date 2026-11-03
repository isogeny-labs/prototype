import type { Finding, FindingBackendStatus, FindingUserStatus } from "./findings";
import type { Run } from "./runs";

/**
 * Single mapping between the backend lifecycle and the user-facing states.
 *   new | triage | relevant | experiment_proposed -> Open
 *   reviewed                                      -> Recommendation proposed
 *   action_approved                               -> External change reported | Awaiting retest
 *   retested                                      -> Resolved within tested scope | Still failing | Inconclusive (from the latest retest)
 *   closed                                        -> Resolved within tested scope
 *   not_relevant                                  -> Not relevant
 */
export function toUserFacingStatus(finding: Finding, runsById: Record<string, Run>): FindingUserStatus {
  const s: FindingBackendStatus = finding.status;
  switch (s) {
    case "new": case "triage": case "relevant": case "experiment_proposed": return "Open";
    case "reviewed": return "Recommendation proposed";
    case "action_approved": return finding.externalChangeReported || finding.revisedArtifactVersionId ? "Awaiting retest" : "External change reported";
    case "retested": {
      const latest = latestRetest(finding, runsById);
      if (!latest || latest.status !== "completed" || latest.overallPass === null) return "Inconclusive";
      return latest.overallPass ? "Resolved within tested scope" : "Still failing";
    }
    case "closed": return "Resolved within tested scope";
    case "not_relevant": return "Not relevant";
  }
}

export function latestRetest(finding: Finding, runsById: Record<string, Run>): Run | null {
  const runs = finding.retestRunIds.map((id) => runsById[id]).filter((r): r is Run => Boolean(r));
  if (runs.length === 0) return null;
  return runs.reduce((a, b) => (a.sequence >= b.sequence ? a : b));
}

/** Can the finding move to closed? Only with a linked passing retest. */
export function canResolve(finding: Finding, runsById: Record<string, Run>): { ok: boolean; reason: string } {
  const latest = latestRetest(finding, runsById);
  if (!latest) return { ok: false, reason: "No retest run is linked to this finding." };
  if (latest.status !== "completed") return { ok: false, reason: `The latest retest is ${latest.status}, not completed.` };
  if (latest.overallPass !== true) return { ok: false, reason: "The latest retest did not pass; the finding stays open." };
  return { ok: true, reason: "The latest linked retest passed." };
}

export const USER_STATUS_ORDER: FindingUserStatus[] = [
  "Open", "Recommendation proposed", "External change reported", "Awaiting retest", "Resolved within tested scope",
];
