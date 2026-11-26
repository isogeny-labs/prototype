import type { ReactNode } from "react";
import type { Advisories, FixSection } from "../../api";
import { ChangeBody } from "./ChangeBody";
import { DetailsBody } from "./DetailsBody";
import { ProofBody } from "./ProofBody";
import { SuggestionBody } from "./SuggestionBody";

function Body({ section, advisories }: { section: FixSection; advisories?: Advisories | null }): ReactNode {
  switch (section.key) {
    case "change":
      return <ChangeBody section={section} />;
    case "proof":
      return <ProofBody section={section} />;
    case "details":
      return <DetailsBody section={section} />;
    case "suggestion":
      return <SuggestionBody suggestion={section.suggestion} advisories={advisories} />;
  }
}

interface Props {
  sections: FixSection[];
  /** Published advisories of a text-only fix, drawn under the suggestion's intro. */
  advisories?: Advisories | null;
  isOpen: (section: FixSection) => boolean;
  onToggle: (section: FixSection) => void;
}

/** A fix's records, part by part: the suggestion, the change, its proof, the technical details. Each shows its number,
 * its title and one line; a click opens or closes it. Since the design refactor (26 November 2026) they stand inside
 * the panel's one fold ("Cryptanalysis proof" or "Technical record"), nothing left out. */
export function FixSections({ sections, advisories, isOpen, onToggle }: Props) {
  return (
    <>
      {sections.map((section, i) => {
        const open = isOpen(section);
        const bodyId = `fix-section-${section.key}`;
        return (
          <section
            key={section.key}
            data-testid="fix-section"
            data-section={section.key}
            data-part={i + 1}
            className="rounded-lg border border-slate-800 bg-slate-900/40"
          >
            <h3>
              <button
                type="button"
                aria-expanded={open}
                aria-controls={bodyId}
                onClick={() => onToggle(section)}
                className="grid w-full grid-cols-[20px_1fr_auto] items-start gap-2.5 rounded-lg px-3 py-2.5 text-left"
              >
                <span
                  aria-hidden="true"
                  data-step={i + 1}
                  className="mt-0.5 inline-flex h-[18px] w-[18px] items-center justify-center rounded-full border border-slate-600 text-[11px] font-semibold text-slate-300 before:content-[attr(data-step)]"
                />
                {/* (drawn by the style sheet, so the button's name stays its title and its line) */}
                <span
                  aria-hidden="true"
                  data-word={open ? "Hide" : "Show"}
                  className="col-start-3 row-start-1 pt-0.5 text-xs text-slate-400 before:content-[attr(data-word)]"
                />
                <span className="col-start-2 row-start-1 min-w-0">
                  <span className="block text-sm font-semibold text-slate-100">{section.title}</span>
                  <span data-testid="fix-section-line" className="mt-0.5 block text-[13px] text-slate-300">
                    {section.line}
                  </span>
                </span>
              </button>
            </h3>
            {open ? (
              <div id={bodyId} className="flex flex-col gap-4 border-t border-slate-800 px-3 pb-3 pt-3">
                <Body section={section} advisories={advisories} />
              </div>
            ) : null}
          </section>
        );
      })}
    </>
  );
}
