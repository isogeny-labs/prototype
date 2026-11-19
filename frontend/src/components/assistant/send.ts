import { api, type AssistantAction } from "../../api";

/** Phase 6a: Confirm on a next step. The panel has no request of its own: this sends the very call the page's own
 * button sends (the same function of src/api.ts, with the same arguments), so the same route, the same record and the
 * same refusals apply. `ItemLink` steps ("open") are plain links and never come here. */
export function sendStep(action: AssistantAction): Promise<unknown> {
  const plan = action.plan_id;
  switch (action.type) {
    case "verify":
      return api.verify(need(action.import_id));
    case "run":
      return api.runTest(need(plan), need(action.item_id));
    case "run_all":
      return api.runAll(need(plan));
    case "retest":
      return api.retest(need(plan), need(action.version), action.component ?? undefined);
    case "connect":
      return api.connectCode(need(plan));
    case "run_proof_again":
      return api.runProofAgain(need(plan), need(action.fix_id));
    case "open_pull_request":
      return api.openPullRequest(need(plan), need(action.fix_id), action.reviewers ?? []);
    case "retest_now":
      return api.retestNow(need(plan), need(action.fix_id));
    case "try":
      return api.changeTry(need(plan), need(action.change));
    case "ask_approval":
      return api.changeAskApproval(need(plan), need(action.change), action.reviewers ?? []);
    case "measure_library":
      return api.measureDependencies(need(plan), need(action.row));
    case "measure_all":
      return api.measureDependencies(need(plan), null);
    case "measure_status":
      return api.measureMigration(need(plan));
    case "open":
      return Promise.resolve(null);
  }
}

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("This step is missing what its page's button sends.");
  return value;
}

/** Where the page itself goes after its button's answer: Verify claims opens Verify, Retest now opens Evidence. */
export function pageAfter(action: AssistantAction): string | null {
  if (action.type === "verify") return "inventory/verify";
  if (action.type === "retest_now") return "evidence";
  return null;
}
