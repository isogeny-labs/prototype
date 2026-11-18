import { useState, type FormEvent } from "react";
import { api, errorMessage, type DemoProjectsLoaded, type Session, type Workspace } from "../../api";
import type { Theme } from "../../prefs";
import { PageHeader } from "../layout";
import { ErrorBox, SecondaryButton } from "../ui";
import { OttoSettings } from "./OttoSettings";
import { Section } from "./parts";

/** Settings: the organization's name, the look, Load demo projects, Otto's test packs and Live Otto (phase 5c), and how
 * software runs on this computer. */
export function SettingsPage({
  session,
  workspace,
  theme,
  onTheme,
  onChanged,
  onLoadDemo,
  loadingDemo,
  demoResult,
  section = null,
}: {
  session: Session;
  workspace: Workspace | null;
  theme: Theme;
  onTheme: (t: Theme) => void;
  onChanged: () => Promise<void> | void;
  onLoadDemo: () => void;
  loadingDemo: boolean;
  demoResult: DemoProjectsLoaded | null;
  /** Phase 5c: the section the address names (#/settings?section=test-packs), brought into view when the page opens. */
  section?: string | null;
}) {
  const [name, setName] = useState(workspace?.organization ?? "");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    try {
      await api.setOrganization(name);
      await onChanged();
      setSaved(true);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div data-testid="settings-page" className="max-w-3xl">
      <PageHeader title="Settings" description="Settings for this installation of Evidence Lab. They change no result." />

      <Section title="Organization">
        <form onSubmit={save} className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <label className="flex min-w-[16rem] flex-1 flex-col gap-1 text-xs text-slate-400">
            Organization name (shown in the sidebar and in every evidence file)
            <input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setSaved(false);
              }}
              maxLength={120}
              className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-slate-100"
            />
          </label>
          <button type="submit" className="rounded-lg bg-sky-500 px-3.5 py-1.5 text-sm font-semibold text-slate-950 hover:bg-sky-400">
            Save
          </button>
          {saved ? (
            <p role="status" className="w-full text-xs text-slate-400">
              Saved.
            </p>
          ) : null}
          {error ? (
            <div className="w-full">
              <ErrorBox>{error}</ErrorBox>
            </div>
          ) : null}
        </form>
      </Section>

      <Section title="Appearance">
        <fieldset className="flex flex-wrap gap-2 rounded-xl border border-slate-800 bg-slate-900/30 p-4">
          <legend className="sr-only">Appearance</legend>
          {(
            [
              ["dark", "Dark"],
              ["light", "Light"],
              ["system", "Match my computer"],
            ] as [Theme, string][]
          ).map(([value, label]) => (
            <label
              key={value}
              className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-sm ${
                theme === value ? "border-sky-400/60 bg-sky-400/10 text-slate-50" : "border-slate-700 text-slate-300 hover:border-slate-500"
              }`}
            >
              <input type="radio" name="theme" value={value} checked={theme === value} onChange={() => onTheme(value)} className="accent-sky-500" />
              {label}
            </label>
          ))}
        </fieldset>
      </Section>

      <Section title="Demo projects">
        <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-4 text-sm text-slate-300">
          <p>
            Adds a Demo folder with one project for each demo file (Acme Pay, Migration demo, Multi-target, Lab nginx, Real libraries,
            Real public servers), each with its first assessment and the file already imported. Running it again adds nothing.
          </p>
          <div className="mt-3">
            <SecondaryButton onClick={onLoadDemo} disabled={loadingDemo}>
              {loadingDemo ? "Loading demo projects…" : "Load demo projects"}
            </SecondaryButton>
          </div>
          {demoResult ? (
            <div role="status" className="mt-3 space-y-1 text-xs text-slate-400">
              <p className="text-slate-300">{demoResult.summary}</p>
              {demoResult.notices.map((n, i) => (
                <p key={i}>{n}</p>
              ))}
            </div>
          ) : null}
        </div>
      </Section>

      <OttoSettings section={section} />

      <Section title="How software runs here">
        <p className="rounded-xl border border-slate-800 bg-slate-900/30 p-4 text-sm text-slate-300">{session.mode_line}</p>
      </Section>
    </div>
  );
}
