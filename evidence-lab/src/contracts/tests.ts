import type { Id, PackId } from "./common";

export type TestKind = "imported" | "supported" | "proposed";

export interface ResourceLimits {
  timeoutSeconds: number;
  memoryMb: number;
  cpuSeconds?: number;
  network: "disabled" | "allowlisted" | "not_applicable";
}

export interface TestInput {
  name: string;
  description: string;
  value?: string | number | boolean;
}

export interface AcceptanceRule {
  description: string;
  metric?: string;
  operator?: "<=" | ">=" | "==" | "<" | ">";
  threshold?: number;
  unit?: string;
}

export interface TestDefinition {
  id: Id;
  packId: PackId;
  name: string;
  description: string;
  kind: TestKind;
  inputs: TestInput[];
  acceptanceRule: AcceptanceRule;
  runner: string;              // e.g. "platform_sandbox: signature-fixture v2 (simulated)"
  runnerVersion: string;
  resourceLimits: ResourceLimits;
  runnable: boolean;           // false for unsupported/imported tests; never shown as runnable
  unsupportedReason?: string;  // why it cannot run here, with the import/adapter path
  vectorSource?: string;       // e.g. "Project Wycheproof (subset, sample)"
  version: string;
}

export interface CompatibilityResult {
  testDefinitionId: Id;
  artifactVersionId: Id;
  compatible: boolean;
  reasons: string[];
  path: "run" | "import_results" | "adapter_needed";
}
