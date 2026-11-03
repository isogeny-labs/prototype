import { useState } from "react";
import { brand } from "@/theme/tokens";

/**
 * Brand mark. Tries the SVG first, then the supplied dark raster crop, then a text wordmark.
 * The current repo ships raster crops only (no SVG master): see docs/GAPS.md.
 */
export function Logo({ variant = "full", height = 28 }: { variant?: "full" | "symbol"; height?: number }) {
  const sources = variant === "symbol" ? [brand.symbolDarkPng] : [brand.logoSvg, brand.logoDarkPng];
  const [idx, setIdx] = useState(0);
  const src = sources[idx];
  if (!src) {
    return <span className="font-semibold tracking-wide text-ink" data-testid="wordmark" style={{ fontSize: height * 0.6 }}>{brand.wordmark}</span>;
  }
  return <img src={src} alt={brand.logoAlt} height={height} style={{ height, width: "auto" }} onError={() => setIdx((i) => i + 1)} data-testid="logo" draggable={false} />;
}
