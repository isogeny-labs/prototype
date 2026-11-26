import { useState, type ReactNode } from "react";
import type { RelatedLine } from "../api";
import { FoldLine } from "./foldline";
import { ItemLinkView } from "./related";
import { Icon } from "./shell/icons";

/** The design refactor (26 November 2026): every proof is shown in three layers. First the answer at a glance; then
 * what it shows and what it doesn't; then one fold that holds every record whole. Nothing here words a result or
 * decides anything: these are the frames the pages put their own words into. */

/** The fold's two names (Kevin's decision B): what was tested on a copy gets a Cryptanalysis proof; what was observed,
 * or has nothing run yet, gets a Technical record. */
export const PROOF_NAMES = { proof: "Cryptanalysis proof", record: "Technical record" } as const;
export type ProofKind = keyof typeof PROOF_NAMES;

/** Which name a result's fold takes, from the tag of what the result rests on ("Proven in the lab" is a test). */
export function proofKindOf(tag: { key: string } | null | undefined): ProofKind {
  return tag?.key === "lab" ? "proof" : "record";
}

/** Layer 1: the answer card. The page puts its result word, its one plain sentence, where it ran and its next step in. */
export function Glance({ children, testId = "glance" }: { children: ReactNode; testId?: string }) {
  return (
    <div data-testid={testId} className="min-w-0 rounded-xl border border-slate-700 bg-slate-900 px-4 py-4">
      {children}
    </div>
  );
}

/** One quiet fact under the plain sentence, with a small picture beside it (where it ran, the control). */
export function GlanceFact({ icon, children, testId }: { icon: string; children: ReactNode; testId?: string }) {
  return (
    <div
      data-testid={testId}
      className="grid grid-cols-[1.125rem_minmax(0,1fr)] items-start gap-2 text-[13px] leading-snug text-slate-300"
    >
      <Icon name={icon} className="mt-0.5 h-4 w-4 text-slate-400" />
      <div className="min-w-0 break-words">{children}</div>
    </div>
  );
}

/** Layer 3: the fold. Shut until it is opened; it holds every record whole. Its header says what is inside. */
export function ProofFold({
  kind,
  inside,
  children,
  defaultOpen = false,
  testId = "proof-fold",
}: {
  kind: ProofKind;
  /** The parts inside, in order, as short names ("What happened", "The control"). */
  inside: string[];
  children: ReactNode;
  defaultOpen?: boolean;
  testId?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details
      data-testid={testId}
      data-kind={kind}
      open={open}
      className="min-w-0 rounded-xl border border-slate-700 bg-slate-950"
    >
      <summary
        data-testid="proof-fold-toggle"
        aria-expanded={open}
        onClick={(e) => {
          // (handled here, so the fold opens the same way in every browser and in the tests)
          e.preventDefault();
          setOpen((v) => !v);
        }}
        className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden"
      >
        <span
          aria-hidden="true"
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-slate-700 bg-slate-900 text-slate-300"
        >
          <Icon name={kind === "proof" ? "layers" : "signal"} />
        </span>
        <span className="min-w-0">
          <span data-testid="proof-fold-name" className="block text-[15px] font-semibold text-slate-50">
            {PROOF_NAMES[kind]}
          </span>
          {inside.length > 0 ? (
            <span data-testid="proof-fold-inside" className="block break-words text-xs text-slate-400">
              {inside.join(" · ")}
            </span>
          ) : null}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-1.5 whitespace-nowrap text-xs font-medium text-sky-300">
          {open ? "Hide" : "Show"}
          <Icon name={open ? "chevron" : "expand"} className="h-4 w-4 text-slate-400" />
        </span>
      </summary>
      <div data-testid="proof-fold-body" className="@container border-t border-slate-800 px-4">
        {children}
      </div>
    </details>
  );
}

/** One numbered part inside the fold. */
export function ProofPart({
  n,
  title,
  extra,
  children,
  testId,
}: {
  n: number;
  title: ReactNode;
  /** A small tag or label beside the title. */
  extra?: ReactNode;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <section data-testid={testId} data-part={n} className="min-w-0 border-t border-slate-800 py-4 first:border-t-0">
      <h4 className="mb-2 flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-50">
        <span
          aria-hidden="true"
          className="grid h-5 w-5 shrink-0 place-items-center rounded-full border border-slate-600 text-[11px] font-semibold tabular-nums text-slate-300"
        >
          {n}
        </span>
        <span>{title}</span>
        {extra}
      </h4>
      {children}
    </section>
  );
}

const TRAIL_ORDER = ["claim", "advisory", "test", "fix"] as const;
const TRAIL_NAMES: Record<string, string> = { claim: "Claim", advisory: "Advisory", test: "Check", fix: "Fix" };

/** Where an item sits: claim, advisory, check, fix, with the open item marked. It is drawn from the links the Related
 * block already holds (and brings them to the top of the panel); it adds no relation of its own. */
export function Trail({
  lines,
  here,
}: {
  lines: RelatedLine[] | null;
  /** The open item: which step it is, its name and one short word under it (its result or status). */
  here: { kind: string; name: string; label: string; sub?: string | null };
}) {
  if (!lines) return null;
  const others = TRAIL_ORDER.filter((k) => k !== here.kind)
    .map((k) => lines.find((l) => l.kind === k))
    .filter((l): l is RelatedLine => Boolean(l && l.items.length > 0));
  if (others.length === 0) return null;
  const at = (TRAIL_ORDER as readonly string[]).indexOf(here.kind);
  type Step = { key: string; here: boolean; line?: RelatedLine };
  const steps: Step[] = others.map((line) => ({ key: line.kind, here: false, line }));
  const before = at < 0 ? 0 : others.filter((l) => (TRAIL_ORDER as readonly string[]).indexOf(l.kind) < at).length;
  steps.splice(before, 0, { key: "here", here: true });
  return (
    <ol
      data-testid="trail"
      aria-label="Where this sits"
      className="grid min-w-0 auto-cols-fr grid-flow-row overflow-hidden rounded-lg border border-slate-800 @md:grid-flow-col"
    >
      {steps.map((step) => {
        if (step.here) {
          return (
            <li
              key="here"
              data-testid="trail-here"
              aria-current="step"
              className="min-w-0 border-t border-slate-800 bg-sky-400/[0.08] px-3 py-2 first:border-t-0 @md:border-l @md:border-t-0 @md:first:border-l-0"
            >
              <span className="block text-[10.5px] font-semibold uppercase tracking-wider text-sky-300">
                {here.name} · you are here
              </span>
              <span className="block truncate text-[13px] font-semibold text-slate-50">{here.label}</span>
              {here.sub ? <span className="block truncate text-xs text-slate-400">{here.sub}</span> : null}
            </li>
          );
        }
        const line = step.line!;
        const first = line.items[0]!;
        const more = line.items.length - 1;
        return (
          <li
            key={step.key}
            data-testid="trail-step"
            data-kind={line.kind}
            className="min-w-0 border-t border-slate-800 px-3 py-2 first:border-t-0 @md:border-l @md:border-t-0 @md:first:border-l-0"
          >
            <span className="block text-[10.5px] font-semibold uppercase tracking-wider text-slate-500">
              {TRAIL_NAMES[line.kind] ?? line.title}
              {more > 0 ? ` · ${line.items.length}` : ""}
            </span>
            <ItemLinkView
              link={first.link}
              testId="trail-link"
              className="block truncate text-[13px] text-slate-200 underline-offset-2 hover:underline"
            >
              {first.label}
            </ItemLinkView>
            {first.sub ? <span className="block truncate text-xs text-slate-400">{first.sub}</span> : null}
          </li>
        );
      })}
    </ol>
  );
}

export { FoldLine };
