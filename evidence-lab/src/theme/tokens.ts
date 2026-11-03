/**
 * Single theme file. Dark mode only for now; a light theme is added by giving each token a second value.
 * Palette follows the Isogeny Labs brand (near-black/navy ground, layered charcoal panels, blue primary, ivory secondary).
 */
export const colors = {
  bg: "#080C12",
  panel: "#111925",
  panelElevated: "#182233",
  border: "#29364A",
  text: "#EDF1F7",
  textMuted: "#A4B2C8",
  textFaint: "#6B7A90",
  accent: "#76B8F4",        // primary interactions
  accentInk: "#06101A",     // text on accent
  ivory: "#D8CBAE",         // secondary accent, used sparingly
  header: "#000000",        // matches the dark logo asset background
  // status colors: never the only signal; always paired with text or shape
  ok: "#5FCB8A",
  warn: "#E8B86D",
  bad: "#F08A80",
  info: "#76B8F4",
  sample: "#C9B4F0",        // sample / simulated marker
} as const;

export const tailwindColors = {
  bg: colors.bg,
  panel: colors.panel,
  "panel-2": colors.panelElevated,
  line: colors.border,
  ink: colors.text,
  muted: colors.textMuted,
  faint: colors.textFaint,
  accent: colors.accent,
  "accent-ink": colors.accentInk,
  ivory: colors.ivory,
  header: colors.header,
  ok: colors.ok,
  warn: colors.warn,
  bad: colors.bad,
  info: colors.info,
  sample: colors.sample,
};

export const fontFamilies = {
  sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
  mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
};

/** Brand asset paths (configurable). SVG is preferred; the supplied raster crops are used when no SVG master exists. */
const base = import.meta.env.BASE_URL; // "/" locally, "/prototype/" on GitHub Pages
export const brand = {
  logoSvg: `${base}brand/isogeny-logo.svg`,
  logoDarkPng: `${base}brand/isogeny-logo-dark.png`,
  symbolDarkPng: `${base}brand/isogeny-symbol-dark.png`,
  logoLightPng: `${base}brand/isogeny-logo-light.png`,
  logoAlt: "Isogeny Labs logo: blue-to-ivory mathematical linework symbol beside the ISOGENY LABS wordmark",
  wordmark: "Isogeny Labs",
};
