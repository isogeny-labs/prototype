import type { TryClients } from "../../api";
import { StatusChip, StatusView } from "../ui";

const TH = "border-b border-slate-800 px-2.5 py-1.5 text-left align-bottom text-xs font-medium uppercase tracking-wide text-slate-400";

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
          <div className="mt-2 overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 px-3 py-1">
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr>
                  {view.columns.map((column) => (
                    <th key={column} scope="col" className={TH}>
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {view.rows.map((row) => (
                  <tr key={row.id} data-testid="clients-row" data-client={row.id} data-word={row.word_key} className="border-b border-slate-800 last:border-b-0">
                    <th scope="row" className="px-2.5 py-2 text-left align-top font-medium text-slate-100">
                      {row.name}
                      <span className="mt-0.5 block text-xs font-normal text-slate-400">{row.offers}</span>
                    </th>
                    <td className="px-2.5 py-2 align-top text-slate-200">{row.today}</td>
                    <td className="px-2.5 py-2 align-top text-slate-200">{row.on_copy}</td>
                    <td className="px-2.5 py-2 align-top">
                      <StatusChip label={row.word} tone={row.tone} size="sm" wrap testId="clients-word" />
                      {row.note ? <span className="mt-1 block text-xs text-slate-400">{row.note}</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
