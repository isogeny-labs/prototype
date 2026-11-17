import { plainNameFor } from "../plainNames";

/** Phase 5b: an algorithm name drawn plain name first, the technical name under it in small type ("Classical
 * signatures" over "ECDSA P-256"). Anything else is drawn as it is. Used in table cells, column headings and panel
 * titles; sentences stay as they are. */
export function AlgoName({ text }: { text: string }) {
  const found = plainNameFor(text);
  if (!found) return <>{text}</>;
  return (
    <span data-testid="algo-name" className="inline-flex flex-col leading-tight">
      <span>{found.plain}</span>
      <span className="text-[11px] font-normal text-slate-400">{text}</span>
    </span>
  );
}
