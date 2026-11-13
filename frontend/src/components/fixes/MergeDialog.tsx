import { useEffect, useRef, type KeyboardEvent } from "react";
import type { FixDetail } from "../../api";
import { PrimaryButton, SecondaryButton, useDismiss } from "../ui";
import { Rich } from "./parts";

interface Props {
  dialog: NonNullable<FixDetail["merge_dialog"]>;
  onCancel: () => void;
  onConfirm: () => void;
}

/** Asks before a merge. Escape, a click outside and Cancel all close it; only the confirm button merges. */
export function MergeDialog({ dialog, onCancel, onConfirm }: Props) {
  const box = useRef<HTMLDivElement | null>(null);
  useDismiss(true, box, onCancel);

  // The keyboard starts on Cancel, so pressing Enter straight away merges nothing.
  // When the box closes, the keyboard goes back to where it was.
  useEffect(() => {
    const opener = document.activeElement;
    box.current?.querySelector("button")?.focus();
    return () => {
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, []);

  // Tab stays inside the box while it is open, so the screen behind can't be used by keyboard either.
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Tab") return;
    const buttons = Array.from(box.current?.querySelectorAll("button") ?? []);
    const first = buttons[0];
    const last = buttons[buttons.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last?.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first?.focus();
    }
  }

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-slate-950/75 px-4">
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-labelledby="merge-title"
        aria-describedby="merge-text"
        onKeyDown={onKeyDown}
        className="w-[540px] max-w-full rounded-xl border border-slate-600 bg-slate-900 p-5 shadow-2xl shadow-black/60"
      >
        <h2 id="merge-title" className="text-base font-semibold text-slate-50">
          {dialog.title}
        </h2>
        <div id="merge-text" className="mt-2 space-y-2 text-sm text-slate-300">
          {dialog.paragraphs.map((parts, i) => (
            <p key={i}>
              <Rich parts={parts} />
            </p>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap justify-end gap-2.5">
          <SecondaryButton onClick={onCancel}>{dialog.cancel}</SecondaryButton>
          <PrimaryButton onClick={onConfirm}>{dialog.confirm}</PrimaryButton>
        </div>
      </div>
    </div>
  );
}
