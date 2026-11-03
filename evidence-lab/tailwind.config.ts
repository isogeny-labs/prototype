import type { Config } from "tailwindcss";
import { tailwindColors, fontFamilies } from "./src/theme/tokens";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: tailwindColors,
      fontFamily: fontFamilies,
      borderRadius: { panel: "8px" },
      fontSize: { "2xs": ["11px", "14px"] },
    },
  },
  plugins: [],
} satisfies Config;
