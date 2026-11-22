import { useId, useState } from "react";
import type { MigrationChooseBox, MigrationOption } from "../../api";
import { PrimaryButton, SecondaryButton } from "../ui";
import { Chip, LineView } from "./parts";

/** What Save sends; the answer is null when it was saved, or the reason it wasn't (shown in the box). */
export type SaveChoice = (reason: string, reviewDate: string | null) => Promise<{ message: string; field: string | null } | null>;

function ChooseBox({ box, onSave, onCancel }: { box: MigrationChooseBox; onSave: SaveChoice; onCancel: () => void }) {
  const id = useId();
  const [reason, setReason] = useState("");
  const [reviewDate, setReviewDate] = useState(box.review_date?.value ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<{ message: string; field: string | null } | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    const refused = await onSave(reason, box.review_date ? reviewDate : null);
    // On success the box is closed by the screen; only a refusal keeps it here.
    if (refused) {
      setError(refused);
      setSaving(false);
    }
  }

  const reasonMissing = box.needs_reason && reason.trim() === "";

  return (
    <div
      role="group"
      aria-labelledby={`${id}-title`}
      data-testid="choose-box"
      className="mt-3 rounded-lg border border-slate-400 bg-slate-800 p-3"
    >
      <p id={`${id}-title`} className="text-[13px] font-semibold text-slate-100">
        {box.title}
      </p>
      <div className="mt-2 grid gap-2">
        {box.review_date ? (
          <div>
            <label htmlFor={`${id}-date`} className="block text-xs text-slate-300">
              {box.review_date.label}
            </label>
            <input
              id={`${id}-date`}
              type="date"
              value={reviewDate}
              min={box.review_date.min}
              max={box.review_date.max}
              aria-invalid={error?.field === "review_date" || undefined}
              aria-describedby={`${id}-date-help`}
              onChange={(e) => setReviewDate(e.target.value)}
              className="mt-1 rounded-lg border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-100 [color-scheme:dark]"
            />
            <p id={`${id}-date-help`} className="mt-1 text-xs text-slate-400">
              {box.review_date.help}
            </p>
          </div>
        ) : null}
        <div>
          <label htmlFor={`${id}-reason`} className="block text-xs text-slate-300">
            {box.reason_label}
          </label>
          <textarea
            id={`${id}-reason`}
            value={reason}
            rows={2}
            aria-invalid={error?.field === "reason" || undefined}
            onChange={(e) => setReason(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-100"
          />
        </div>
      </div>
      {error ? (
        <p role="alert" data-testid="choose-error" className="mt-2 text-[13px] text-amber-200">
          {error.message}
        </p>
      ) : null}
      <div className="mt-2.5 flex flex-wrap gap-2">
        <PrimaryButton disabled={reasonMissing} busy={saving} onClick={() => void save()}>
          {box.save}
        </PrimaryButton>
        <SecondaryButton disabled={saving} onClick={onCancel}>
          {box.cancel}
        </SecondaryButton>
      </div>
      <p className="mt-2 text-xs text-slate-400">{box.note}</p>
    </div>
  );
}

interface Props {
  option: MigrationOption;
  /** This card's choose box is the one open. */
  open: boolean;
  busy: boolean;
  onOpen: () => void;
  onCancel: () => void;
  onSave: SaveChoice;
  onViewFix: (fixId: string) => void;
}

/** One of the four options, exactly as sent: its tags, cost, blockers and counts, and the Choose button when offered. */
export function OptionCard({ option, open, busy, onOpen, onCancel, onSave, onViewFix }: Props) {
  return (
    <article
      data-testid="option-card"
      data-option={option.key}
      data-highlighted={option.highlighted}
      className={`min-w-0 rounded-xl border bg-slate-950 p-3.5 ${option.highlighted ? "border-sky-400/60" : "border-slate-800"}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-[15px] font-semibold text-slate-100">{option.title}</h4>
        {option.tags.map((tag) => (
          <Chip key={tag}>{tag}</Chip>
        ))}
      </div>
      <p className="mt-1 text-[13px] text-slate-300">{option.what}</p>
      {option.sections.map((section, i) => (
        <div key={i} data-testid="option-section">
          <h5 className="mt-2.5 text-xs font-medium uppercase tracking-wide text-slate-400">{section.title}</h5>
          <ul className="mt-1 space-y-1 text-[13px] text-slate-300">
            {section.lines.map((line, j) => (
              <li key={j}>
                <LineView line={line} onViewFix={onViewFix} />
              </li>
            ))}
          </ul>
        </div>
      ))}
      {option.not_offered ? (
        <p data-testid="not-offered" className="mt-3 text-[13px] text-slate-400">
          {option.not_offered}
        </p>
      ) : option.choose ? (
        open ? (
          <ChooseBox box={option.choose} onSave={onSave} onCancel={onCancel} />
        ) : (
          <div className="mt-3">
            <SecondaryButton disabled={busy} onClick={onOpen}>
              {option.choose_label}
            </SecondaryButton>
          </div>
        )
      ) : null}
    </article>
  );
}
