import type { ComponentType } from "react";
import type { PackPanelProps } from "./types";
import { AttackAssessmentPanel } from "./crypto/AttackAssessmentPanel";
import { ModelSetupPanel } from "./engineering/ModelSetupPanel";
import { StressViewPanel } from "./engineering/StressViewPanel";
import { ConvergencePanel } from "./engineering/ConvergencePanel";
import { ChronologyPanel } from "./legal/ChronologyPanel";
import { DisputedFactsPanel } from "./legal/DisputedFactsPanel";
import { DocumentViewerPanel } from "./legal/DocumentViewerPanel";
import { ArgumentMapPanel } from "./legal/ArgumentMapPanel";
import { AuthoritiesPanel } from "./legal/AuthoritiesPanel";
import { RehearsalPanel } from "./legal/RehearsalPanel";

/** Pack templates name panels by packComponent; this is the only place those names resolve to code. */
export const PACK_PANELS: Record<string, ComponentType<PackPanelProps>> = {
  AttackAssessmentPanel, ModelSetupPanel, StressViewPanel, ConvergencePanel,
  ChronologyPanel, DisputedFactsPanel, DocumentViewerPanel, ArgumentMapPanel, AuthoritiesPanel, RehearsalPanel,
};
