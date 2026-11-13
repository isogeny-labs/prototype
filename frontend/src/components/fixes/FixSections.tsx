import type { ReactNode } from "react";
import type { FixSection } from "../../api";
import { ChangeBody } from "./ChangeBody";
import { DetailsBody } from "./DetailsBody";
import { ProofBody } from "./ProofBody";
import { SuggestionBody } from "./SuggestionBody";

function Body({ section }: { section: FixSection }): ReactNode {
  switch (section.key) {
    case "change":
      return <ChangeBody section={section} />;
    case "proof":
      return <ProofBody section={section} />;
    case "details":
      return <DetailsBody section={section} />;
    case "suggestion":
      return <SuggestionBody suggestion={section.suggestion} />;
  }
}

interface Props {
  sections: FixSection[];
  isOpen: (section: FixSection) => boolean;
  onToggle: (section: FixSection) => void;
}

/** The folded parts under the summary. Each shows its title and one line; a click opens or closes it. */
export function FixSections({ sections, isOpen, onToggle }: Props) {
  return (
    <>
      {sections.map((section) => {
        const open = isOpen(section);
        const bodyId = `fix-section-${section.key}`;
        return (
          <section
            key={section.key}
            data-testid="fix-section"
            data-section={section.key}
            className="rounded-xl border border-slate-800 bg-slate-900/40"
          >
            <h3>
              <button
                type="button"
                aria-expanded={open}
                aria-controls={bodyId}
                onClick={() => onToggle(section)}
                className="grid w-full grid-cols-[16px_1fr] items-start gap-3 rounded-xl p-4 text-left"
              >
                <span aria-hidden="true" className="pt-[3px] font-mono text-xs text-slate-300">
                  {open ? "▾" : "▸"}
                </span>
                <span className="min-w-0">
                  <span className="block text-[15px] font-semibold text-slate-100">{section.title}</span>
                  <span data-testid="fix-section-line" className="mt-0.5 block text-sm text-slate-300">
                    {section.line}
                  </span>
                </span>
              </button>
            </h3>
            {open ? (
              <div id={bodyId} className="flex flex-col gap-4 border-t border-slate-800 px-4 pb-4 pt-3.5">
                <Body section={section} />
              </div>
            ) : null}
          </section>
        );
      })}
    </>
  );
}
