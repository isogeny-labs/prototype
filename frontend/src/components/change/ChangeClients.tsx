import type { TryClients } from "../../api";
import { StatusChip, StatusView } from "../ui";

/** Phase 4e: who can still connect, in a try's result. Each demo client stand-in's handshake today and on the test copy,
 * and the reviewer's word for it. Information: it has no button, decides nothing about the try and holds Apply off
 * nothing. Every word comes from the backend. */
export function ChangeClients({ view }: { view: TryClients }) {
  return (
    <div data-testid="change-clients" className="mt-4">
      <h4 className="text-[13px] font-semibold text-slate-100">{view.title}</h4>
      {view.running ? (
        <div className="mt-2">
          <StatusView status={view.running} />
        </div>
      ) : view.no_answer ? (
        <p data-testid="clients-no-answer" className="mt-1 text-sm text-slate-300">
          {view.no_answer}
        </p>
      ) : (
        <>
          <p data-testid="clients-summary" className="mt-1 text-sm font-semibold text-slate-100">
            {view.summary}
          </p>
          {view.warning ? (
            <p
              data-testid="clients-warning"
              className="mt-2 rounded-lg border border-amber-400/60 bg-amber-400/10 px-3 py-2 text-sm text-amber-100"
            >
              {view.warning}
            </p>
          ) : null}
          {/* One stacked row per stand-in (the panel is narrow): its word first, then who it is, then its handshake today
              and on the test copy under the backend's own column names, then what its profile offers. */}
          <ul
            aria-label={view.columns[0]}
            className="mt-2 divide-y divide-slate-800 rounded-lg border border-slate-800 bg-slate-950 px-3"
          >
            {view.rows.map((row) => (
              <li key={row.id} data-testid="clients-row" data-client={row.id} data-word={row.word_key} className="py-2.5">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <StatusChip label={row.word} tone={row.tone} size="sm" wrap testId="clients-word" />
                  <span className="font-medium text-slate-100">{row.name}</span>
                  <span className="text-xs text-slate-500">{row.label}</span>
                </div>
                <dl className="mt-1 grid gap-x-3 gap-y-0.5 text-[13px] @md:grid-cols-[minmax(7rem,auto)_minmax(0,1fr)]">
                  <dt className="text-slate-400">{view.columns[1]}</dt>
                  <dd data-testid="clients-today" className="min-w-0 break-words text-slate-200">
                    {row.today}
                  </dd>
                  <dt className="text-slate-400">{view.columns[2]}</dt>
                  <dd data-testid="clients-copy" className="min-w-0 break-words text-slate-200">
                    {row.on_copy}
                  </dd>
                </dl>
                {row.note ? <p className="mt-0.5 text-xs text-slate-300">{row.note}</p> : null}
                <p className="mt-0.5 break-words text-xs text-slate-500">{row.offers}</p>
              </li>
            ))}
          </ul>
          <ul className="mt-2 space-y-0.5 text-xs text-slate-400">
            <li data-testid="clients-decides">{view.decides}</li>
            <li data-testid="clients-note">{view.note}</li>
            {view.control ? <li data-testid="clients-control">{view.control}</li> : null}
          </ul>
        </>
      )}
    </div>
  );
}
