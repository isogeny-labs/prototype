import { useId, useState, type ReactNode } from "react";
import { Icon } from "./shell/icons";

/** A quiet folded line at the foot of a panel (earlier runs, Related, what a change touches). */
export function FoldLine({
  title,
  count,
  hint,
  children,
  testId,
  defaultOpen = false,
  onToggle,
}: {
  title: string;
  count?: number | null;
  hint?: string;
  children: ReactNode;
  testId?: string;
  defaultOpen?: boolean;
  /** Told when the line opens or closes (a line that reads its content only when it is asked for). */
  onToggle?: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();
  return (
    <div data-testid={testId} data-open={open || undefined} className="min-w-0 border-t border-slate-800 pt-3">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => {
          onToggle?.(!open);
          setOpen(!open);
        }}
        className="flex w-full items-center gap-2 text-left text-[13px] text-slate-300 hover:text-slate-100"
      >
        <Icon name={open ? "chevron" : "expand"} className="h-3.5 w-3.5 text-slate-500" />
        <span className="font-medium">{title}</span>
        {count !== undefined && count !== null ? <span className="tabular-nums text-slate-500">({count})</span> : null}
        {hint ? <span className="truncate text-xs text-slate-500">{hint}</span> : null}
      </button>
      <div id={bodyId} hidden={!open} className="mt-2">
        {children}
      </div>
    </div>
  );
}
