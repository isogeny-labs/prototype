import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { services, ServiceError } from "@/services";
import { useAppStore } from "@/store";
import type { AssistantContext, AssistantSuggestedAction } from "@/contracts";
import { useProjectCtx } from "./ProjectContext";

const NO_MESSAGES: never[] = [];
const CHIPS: Record<string, string[]> = {
  default: ["Summarize the evidence", "What should we test next?", "What's waiting on me?", "Review the orchestration", "Review the executions", "Review the proposals"],
  overview: ["Summarize the evidence", "What should we test next?", "What's waiting on me?", "hide the recent activity panel"],
  conductor: ["Review the orchestration", "What's waiting on me?", "What should we test next?"],
  runs: ["Review the executions", "only failed", "reset the view", "What should we test next?"],
  run: ["Review the executions", "Summarize the evidence"],
  research: ["Review the proposals", "What should we test next?", "What's waiting on me?"],
  findings: ["Summarize the findings", "Where is the evidence thin?", "What's waiting on me?"],
  finding: ["Summarize this finding", "What should we test next?"],
  approvals: ["What's waiting on me?", "Summarize the evidence"],
  tests: ["Review the executions", "show tests matching latency", "reset the view"],
  intake: ["Summarize the evidence", "set the latency threshold to 3 ms"],
  reports: ["Summarize the evidence", "Where is the evidence thin?"],
};

function pageContext(pathname: string): AssistantContext {
  const m = /^\/p\/[^/]+\/?([^/]*)\/?([^/]*)/.exec(pathname);
  if (!m) return { page: pathname === "/" ? "home" : "other" };
  const [, section = "", id = ""] = m;
  if (section === "") return { page: "overview" };
  if (section === "runs") return id ? { page: "run", entityId: id } : { page: "runs" };
  if (section === "findings") return id ? { page: "finding", entityId: id } : { page: "findings" };
  const known = ["intake", "artifacts", "tests", "research", "conductor", "approvals", "changes", "reports", "settings", "memory"] as const;
  return { page: (known as readonly string[]).includes(section) ? (section as AssistantContext["page"]) : "other" };
}

/**
 * Simulated assistant: reads the project, summarises, proposes actions. Nothing it proposes happens until a human
 * presses Confirm; the action then runs as that human and the usual approval gates apply.
 */
export function AssistantPanel({ onClose }: { onClose: () => void }) {
  const { project, projectId } = useProjectCtx();
  const location = useLocation();
  const navigate = useNavigate();
  const context = useMemo(() => pageContext(location.pathname), [location.pathname]);
  const user = useAppStore((s) => s.user);
  const viewConfig = useAppStore((s) => (projectId ? s.viewConfig[projectId] : undefined));
  const setViewConfig = useAppStore((s) => s.setViewConfig);
  const messagesRaw = useAppStore((s) => (projectId ? s.assistantMessages[projectId] : undefined));
  const messages = messagesRaw ?? NO_MESSAGES;
  const append = useAppStore((s) => s.appendAssistantMessages);
  const clear = useAppStore((s) => s.clearAssistant);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Record<string, "confirmed" | "dismissed">>({});
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages.length, busy]);

  async function send(input: string) {
    if (!projectId || !input.trim() || busy) return;
    setBusy("send"); setError(null); setText("");
    append(projectId, [{ id: `u-${Date.now()}`, role: "user", text: input, at: new Date().toISOString(), context }]);
    try {
      const vc = viewConfig ?? { panelOrder: [], hiddenPanels: [], filters: {}, chosenTestIds: [] };
      const { reply, viewConfig: next } = await services.assistant.send(projectId, vc, input, { id: user.id, name: user.name }, context);
      if (reply.action?.kind === "view_change") setViewConfig(projectId, next);
      append(projectId, [reply]);
    } catch (e) { setError(e instanceof ServiceError ? `${e.message} (${e.code})` : String(e)); }
    finally { setBusy(null); }
  }
  async function confirm(a: AssistantSuggestedAction) {
    if (!projectId || busy) return;
    if (a.kind === "navigate" && a.href) { setDone((d) => ({ ...d, [a.id]: "confirmed" })); navigate(a.href); return; }
    setBusy(a.id); setError(null);
    try {
      const { reply } = await services.assistant.confirm(projectId, a, { id: user.id, name: user.name });
      setDone((d) => ({ ...d, [a.id]: "confirmed" }));
      append(projectId, [reply]);
    } catch (e) { setError(e instanceof ServiceError ? `${e.message} (${e.code})` : String(e)); }
    finally { setBusy(null); }
  }

  const chips = CHIPS[context.page] ?? CHIPS["default"]!;
  return (
    <aside aria-label="Assistant" data-testid="assistant-panel" className="flex h-full w-96 shrink-0 flex-col border-l border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <span className="h2">Assistant</span>
        <span className="tag border-sample/60 text-sample">Simulated</span>
        <button type="button" className="btn-ghost btn-sm ml-auto" onClick={onClose} aria-label="Close assistant panel">Close</button>
      </div>
      <div className="border-b border-line px-3 py-2 text-xs text-muted">
        Reads {project ? project.name : "the project"} and answers, summarises evidence, orchestration, runs and proposals, and drafts next steps as cards. <strong className="text-ink">You confirm every action</strong>; it then runs as you and approval gates still apply. It never starts a run, approves anything, or changes criteria, permissions or tests on its own.
        <div className="mt-1 text-faint">Looking at: {context.page}{context.entityId ? ` ${context.entityId}` : ""} · acting as {user.name}</div>
      </div>
      {!projectId ? <div className="p-3 text-sm text-muted">Open a project to use the assistant.</div> : (
        <>
          <div className="flex-1 overflow-y-auto p-3 text-sm" data-testid="assistant-transcript">
            {messages.length === 0 ? <div className="text-faint">No messages yet. Try a suggestion below or ask anything about this project.</div> : null}
            {messages.map((m) => (
              <div key={m.id} className={`mb-2 rounded-md px-2.5 py-2 ${m.role === "user" ? "ml-6 bg-panel-2" : "mr-2 border border-line"}`} data-testid={`assistant-msg-${m.role}`} data-action={m.action?.kind ?? "none"}>
                <div className="text-2xs uppercase tracking-wide text-faint">{m.role === "user" ? user.name : "Assistant (simulated)"}</div>
                <div className="mt-0.5 whitespace-pre-wrap">{m.text}</div>
                {m.action?.kind === "refused" ? <div className="callout-bad mt-2 text-xs" role="alert" data-testid="assistant-refusal"><strong>Not done directly.</strong> {m.action.reason}. {m.action.approvalRequestId ? <>An approval request was created: <Link to={`/p/${projectId}/approvals`}>open Approvals</Link>.</> : m.suggestions?.length ? "A draft you can confirm is below." : null}</div> : null}
                {m.action?.kind === "view_change" ? <div className="mt-1 text-2xs text-ok">▲ View configuration changed · logged to audit</div> : null}
                {m.action?.kind === "confirmed" ? <div className="mt-1 text-2xs text-ok">▲ Confirmed by {user.name} · logged to audit</div> : null}
                {m.suggestions?.length ? (
                  <div className="mt-2 space-y-2" data-testid="assistant-suggestions">
                    {m.suggestions.map((a) => { const st = done[a.id]; return (
                      <div key={a.id} className={`rounded border px-2 py-1.5 text-xs ${st ? "border-line opacity-60" : "border-accent/50"}`} data-testid="assistant-suggestion" data-kind={a.kind} data-state={st ?? "open"}>
                        <div className="font-semibold text-ink">{a.label}</div>
                        <div className="text-muted">{a.why}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-2">
                          {a.gate ? <span className="tag whitespace-normal border-warn/60 text-warn">then: {a.gate}</span> : <span className="tag">no further gate</span>}
                          {st === "confirmed" ? <span className="tag border-ok/60 text-ok">✓ confirmed</span> : st === "dismissed" ? <span className="tag">dismissed</span> : (<>
                            <button type="button" className="btn btn-sm ml-auto" disabled={busy !== null} onClick={() => confirm(a)} data-testid="assistant-confirm">{busy === a.id ? "Working…" : a.kind === "navigate" ? "Open" : "Confirm"}</button>
                            <button type="button" className="btn-ghost btn-sm" disabled={busy !== null} onClick={() => setDone((d) => ({ ...d, [a.id]: "dismissed" }))} data-testid="assistant-dismiss">Dismiss</button>
                          </>)}
                        </div>
                      </div>
                    ); })}
                  </div>
                ) : null}
              </div>
            ))}
            {busy === "send" ? <div className="text-xs text-faint">Assistant is reading the project…</div> : null}
            {error ? <div className="callout-bad text-xs" role="alert" data-testid="assistant-error">{error}</div> : null}
            <div ref={endRef} />
          </div>
          <div className="border-t border-line p-2">
            <div className="mb-2 flex flex-wrap gap-1">{chips.map((s) => <button key={s} type="button" className="tag hover:border-accent hover:text-accent" onClick={() => send(s)} disabled={busy !== null}>{s}</button>)}</div>
            <form className="flex gap-1" onSubmit={(e) => { e.preventDefault(); send(text); }}>
              <input className="input" placeholder="Ask about the evidence, runs, proposals, orchestration…" value={text} onChange={(e) => setText(e.target.value)} aria-label="Message to the assistant" data-testid="assistant-input" />
              <button type="submit" className="btn btn-sm" disabled={busy !== null || !text.trim()} data-testid="assistant-send">Send</button>
            </form>
            <div className="mt-1 flex justify-between text-2xs text-faint"><span>Rule-based, no model connected</span><button type="button" className="underline" onClick={() => clear(projectId)}>Clear transcript</button></div>
          </div>
        </>
      )}
    </aside>
  );
}
