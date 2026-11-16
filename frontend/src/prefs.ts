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
};

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
