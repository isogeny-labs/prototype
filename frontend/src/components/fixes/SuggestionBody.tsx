import type { TextSuggestion } from "../../api";
import { H } from "./parts";

/** Words between backticks are names (a setting, a cipher suite): fixed width and never broken across lines. */
function Words({ text }: { text: string }) {
  return (
    <>
      {text.split("`").map((piece, i) =>
        i % 2 === 1 ? (
          <span key={i} className="whitespace-nowrap font-mono text-[0.92em] text-slate-100">
            {piece}
          </span>
        ) : (
          <span key={i}>{piece}</span>
        ),
      )}
    </>
  );
}

/** A long setting wraps only after a colon or a space, never inside a name. The copied text has no extra characters. */
function CodeBlock({ code }: { code: string }) {
  return (
    <pre className="mt-1 whitespace-pre-wrap rounded bg-slate-900 p-2 font-mono text-xs leading-5 text-slate-200">
      {code.split("\n").map((line, i) => (
        <span key={i} className="block" style={{ paddingLeft: "2ch", textIndent: "-2ch" }}>
          {line.split(":").map((piece, j, all) => (
            <span key={j}>
              <span className="whitespace-nowrap">
                {piece}
                {j < all.length - 1 ? ":" : ""}
              </span>
              {j < all.length - 1 ? <wbr /> : null}
            </span>
          ))}
        </span>
      ))}
    </pre>
  );
}

/** A suggestion in words only. The app has not applied or tested it, and it gets no buttons. */
export function SuggestionBody({ suggestion }: { suggestion: TextSuggestion }) {
  const { warning, where, options, exact } = suggestion;
  return (
    <div data-testid="text-suggestion">
      <div className="space-y-1.5 text-sm text-slate-300">
        {suggestion.intro.map((line, i) => (
          <p key={i}>
            <Words text={line} />
          </p>
        ))}
      </div>

      {warning ? (
        <div data-testid="suggestion-warning" className="mt-4 rounded-lg border border-slate-400 bg-slate-800 px-3 py-2.5">
          <p className="flex items-start gap-2 text-sm text-slate-100">
            <span aria-hidden="true" className="font-mono font-semibold">
              !
            </span>
            <span>
              <span className="font-semibold">{warning.title}</span> <Words text={warning.text} />
            </span>
          </p>
        </div>
      ) : null}

      {where ? (
        <>
          <h4 className={`mb-1 mt-4 ${H}`}>{where.title}</h4>
          <p className="text-xs text-slate-400">
            <Words text={where.note} />
          </p>
          <div className="mt-1.5 overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 px-3 py-1">
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr>
                  {where.columns.map((column, i) => (
                    <th
                      key={i}
                      scope="col"
                      className="whitespace-nowrap border-b border-slate-800 px-2.5 py-1.5 text-left align-bottom text-xs font-medium uppercase tracking-wide text-slate-400"
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {where.rows.map((row, i) => (
                  <tr key={i} className="border-b border-slate-800 last:border-b-0">
                    <td className="whitespace-nowrap px-2.5 py-2 align-top font-medium text-slate-100">{row.place}</td>
                    <td className="px-2.5 py-2 align-top text-slate-300">
                      <Words text={row.setting} />
                    </td>
                    <td className="px-2.5 py-2 align-top text-slate-200">
                      {row.lead ? (
                        <span className="mb-1 block">
                          <Words text={row.lead} />
                        </span>
                      ) : null}
                      {row.code ? (
                        <code className="whitespace-nowrap rounded bg-slate-900 px-1.5 py-0.5 font-mono text-xs text-slate-100">
                          {row.code}
                        </code>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {where.after.map((line, i) => (
            <p key={i} className="mt-2 text-[13px] text-slate-300">
              <Words text={line} />
            </p>
          ))}
        </>
      ) : null}

      {options ? (
        <>
          <h4 className={`mb-1.5 mt-4 ${H}`}>{options.title}</h4>
          <div className="grid gap-3 md:grid-cols-2">
            {options.items.map((option, i) => (
              <div key={i} data-testid="suggestion-option" className="min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
                <p className="text-sm font-medium text-slate-100">{option.title}</p>
                <p className="mt-0.5 text-xs text-slate-400">
                  <Words text={option.when} />
                </p>
                <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-[13px] text-slate-300">
                  {option.steps.map((step, j) => (
                    <li key={j}>
                      <Words text={step} />
                    </li>
                  ))}
                </ol>
                {option.note ? (
                  <p className="mt-2 text-xs text-slate-400">
                    <Words text={option.note} />
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </>
      ) : null}

      {exact ? (
        <div data-testid="suggestion-exact" className="mt-3 min-w-0 rounded-lg border border-slate-800 bg-slate-950 p-3">
          <p className="text-sm font-medium text-slate-100">{exact.title}</p>
          <p className="mt-0.5 text-xs text-slate-400">
            <Words text={exact.note} />
          </p>
          {exact.blocks.map((block, i) => (
            <div key={i} className="mt-2">
              <p className="text-xs text-slate-400">{block.place}</p>
              <CodeBlock code={block.code} />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
