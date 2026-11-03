/**
 * Service selection. A real client replaces a mock here without touching UI code.
 * IMPL is read from VITE_SERVICES_IMPL ("mock" | "http"); only "mock" exists in this task.
 */
import type { Services } from "./types";
import { mockEvidenceLab } from "./mock/evidenceLab";
import { mockApprovals, mockAutoresearcher, mockConductor, mockPacks, mockCairn, mockAssistant, mockLearning } from "./mock/others";

const IMPL = (import.meta.env?.VITE_SERVICES_IMPL as string | undefined) ?? "mock";

function build(): Services {
  switch (IMPL) {
    case "mock":
    default:
      return { evidenceLab: mockEvidenceLab, approvals: mockApprovals, autoresearcher: mockAutoresearcher, conductor: mockConductor, packs: mockPacks, cairn: mockCairn, assistant: mockAssistant, learning: mockLearning };
  }
}

export const services: Services = build();
export { ServiceError } from "./types";
export type * from "./types";
