/** Small conveniences remembered in this browser only (phase 5a). If the browser won't store them, the app still works
 * with the defaults. Nothing here is a result or a record. */
export type Theme = "dark" | "light" | "system";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* nothing to do */
  }
}

export const prefs = {
  theme: (): Theme => {
    const v = read("evidence-lab-theme");
    return v === "light" || v === "system" ? v : "dark";
  },
  setTheme: (v: Theme) => write("evidence-lab-theme", v),
  sidebarCollapsed: () => read("evidence-lab-sidebar") === "collapsed",
  setSidebarCollapsed: (v: boolean) => write("evidence-lab-sidebar", v ? "collapsed" : "open"),
  copilotShown: () => read("evidence-lab-copilot") !== "hidden",
  setCopilotShown: (v: boolean) => write("evidence-lab-copilot", v ? "shown" : "hidden"),
  guidedDemo: () => read("evidence-lab-guided") === "on",
  setGuidedDemo: (v: boolean) => write("evidence-lab-guided", v ? "on" : "off"),
  // Phase 5b: the detail panel's width, one for every page.
  panelWidth: (): number => {
    const v = Number(read("evidence-lab-panel-width"));
    return Number.isFinite(v) && v > 0 ? v : 440;
  },
  setPanelWidth: (v: number) => write("evidence-lab-panel-width", String(Math.round(v))),
  // Phase 6a: the Otto panel's tabs, for one assessment in this browser. `closed`: a tab closed with its ×, with the
  // tab's mark at that moment (it comes back when its thread has something new). `seen`: the mark of each tab when
  // it was last open (anything newer draws a dot). Closing a tab changes nothing in the assessment.
  ottoTabs: (assessmentId: number): OttoTabs => {
    try {
      const value: unknown = JSON.parse(read(`evidence-lab-otto-tabs-${assessmentId}`) ?? "{}");
      const part = (key: string): Record<string, string> => {
        const found = typeof value === "object" && value !== null ? (value as Record<string, unknown>)[key] : null;
        const out: Record<string, string> = {};
        if (typeof found === "object" && found !== null)
          for (const [k, v] of Object.entries(found as Record<string, unknown>)) if (typeof v === "string") out[k] = v;
        return out;
      };
      return { closed: part("closed"), seen: part("seen") };
    } catch {
      return { closed: {}, seen: {} };
    }
  },
  setOttoTabs: (assessmentId: number, value: OttoTabs) => write(`evidence-lab-otto-tabs-${assessmentId}`, JSON.stringify(value)),
  // Phase 6a: the panel asks for a name once (its first Confirm of a decision). Asked or not is kept here; the name
  // itself is kept by the app, in Settings.
  ottoNameAsked: () => read("evidence-lab-otto-name") === "asked",
  setOttoNameAsked: () => write("evidence-lab-otto-name", "asked"),
};

export interface OttoTabs {
  closed: Record<string, string>;
  seen: Record<string, string>;
}

/** Puts the chosen look on the page: dark, light, or whatever this computer prefers. */
export function applyTheme(theme: Theme): void {
  let resolved: "dark" | "light" = theme === "light" ? "light" : "dark";
  if (theme === "system") {
    try {
      resolved = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    } catch {
      resolved = "dark";
    }
  }
  document.documentElement.dataset.theme = resolved;
}
