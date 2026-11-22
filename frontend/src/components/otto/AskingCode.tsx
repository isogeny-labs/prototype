import { useState } from "react";
import type { TestProofCode } from "../../api";

const TAG =
  "inline-block whitespace-nowrap rounded border border-slate-500 bg-slate-700/40 px-2 py-0.5 text-xs font-medium text-slate-100";
/** Code as text. Long lines wrap inside the block, so a narrow panel never scrolls sideways. Nothing here runs it. */
const CODE =
  "mt-2 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border border-slate-800 bg-slate-950 p-3 font-mono text-xs leading-relaxed text-slate-200 [overflow-wrap:anywhere]";

function Source({ source, testId }: { source: string; testId: string }) {
  return (
    <pre data-testid={testId} className={CODE}>
      {source}
    </pre>
  );
}

/** Sandbox research (a prototype): the code that asked a library a test's questions, shown as text for a person to
 * read. Where Claude wrote it, it carries the tag "Written by Otto", and the second author's version stands beside it.
 * It is data on this screen: showing it runs nothing. */
export function AskingCode({ code }: { code: TestProofCode }) {
  const [shown, setShown] = useState(false);
  return (
    <div data-testid="asking-code" className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-[13px] font-semibold text-slate-100">{code.title}</h4>
        {code.label ? (
          <span data-testid="asking-code-label" className={TAG}>
            {code.label}
          </span>
        ) : null}
      </div>
      <p data-testid="asking-code-line" className="mt-1 break-words text-[13px] text-slate-300">
        {code.line}
      </p>
      {code.agree_line ? (
        <p data-testid="asking-code-agree" className="mt-1 break-words text-[13px] text-slate-300">
          {code.agree_line}
        </p>
      ) : null}
      {code.known_lines.length > 0 ? (
        <ul
          data-testid="asking-code-known"
          className="mt-1.5 list-disc space-y-1 pl-5 text-[13px] text-slate-300 marker:text-slate-500"
        >
          {code.known_lines.map((line, i) => (
            <li key={i} className="break-words">
              {line}
            </li>
          ))}
        </ul>
      ) : null}
      <button
        type="button"
        data-testid="asking-code-toggle"
        aria-expanded={shown}
        onClick={() => setShown((s) => !s)}
        className="mt-2 rounded-md border border-slate-700 px-2.5 py-1 text-xs font-medium text-slate-200 hover:border-slate-500 hover:text-slate-100"
      >
        {shown ? code.hide : code.show}
      </button>
      {shown ? (
        <div className="mt-1">
          <p className="mt-2 break-words text-xs text-slate-400">
            {code.file} · {code.author} · SHA-256{" "}
            <span className="font-mono text-slate-300" title={code.sha256}>
              {code.sha256.slice(0, 12)}
            </span>
          </p>
          <Source source={code.source} testId="asking-code-source" />
          {code.second ? (
            <div data-testid="asking-code-second">
              <p className="mt-3 break-words text-xs text-slate-400">
                {code.second.title} · {code.second.author} · SHA-256{" "}
                <span className="font-mono text-slate-300" title={code.second.sha256}>
                  {code.second.sha256.slice(0, 12)}
                </span>
              </p>
              <Source source={code.second.source} testId="asking-code-second-source" />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
