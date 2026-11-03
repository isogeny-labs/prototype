import { useState } from "react";
import { useAppStore } from "@/store";
import { Marker, PageHeader } from "@/components";

export function SampleDataSettingsPage() {
  const db = useAppStore((s) => s.db);
  const mock = useAppStore((s) => s.mock);
  const setMock = useAppStore((s) => s.setMock);
  const user = useAppStore((s) => s.user);
  const setUser = useAppStore((s) => s.setUser);
  const reset = useAppStore((s) => s.resetToSampleData);
  const version = useAppStore((s) => s.version);
  const [confirm, setConfirm] = useState(false);
  const SWITCHABLE_USERS = db.projects.flatMap((p) => p.people.map((x) => ({ id: x.id, name: x.name, role: `${x.role} (${x.org}) · ${p.permissions.members.find((m) => m.personId === x.id)?.role ?? "not a member"} of ${p.name}` })));
  const counts: Array<[string, number]> = [["projects", db.projects.length], ["artifacts", db.artifacts.length], ["tests", db.tests.length], ["runs", db.runs.length], ["checks", db.checks.length], ["findings", db.findings.length], ["approvals", db.approvals.length], ["proposals", db.proposals.length], ["tasks", db.tasks.length], ["evidence records", db.evidence.length], ["audit events", db.audit.length]];
  return (
    <>
      <PageHeader title="Sample data" subtitle="The app runs entirely on in-memory sample data loaded from src/fixtures. Mutations live until reload or reset. The mock layer's latency and failure injection are controlled here." />
      <div className="grid gap-4 xl:grid-cols-2">
        <section className="panel text-sm">
          <div className="flex items-center gap-2"><h2 className="h2">Loaded fixtures</h2><Marker kind="sample" /></div>
          <table className="tbl mt-2"><tbody>{counts.map(([k, v]) => <tr key={k}><td>{k}</td><td className="font-mono">{v}</td></tr>)}</tbody></table>
          <div className="mt-2 text-xs text-faint">Store version {version} (increments on every mutation).</div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {!confirm ? <button type="button" className="btn-danger btn-sm" onClick={() => setConfirm(true)} data-testid="reset-sample">Reset to sample data</button>
              : <><span>Discard every change made in this session?</span><button type="button" className="btn-danger btn-sm" onClick={() => { reset(); setConfirm(false); }} data-testid="reset-confirm">Yes, reset</button><button type="button" className="btn-ghost btn-sm" onClick={() => setConfirm(false)}>Cancel</button></>}
          </div>
        </section>
        <section className="panel text-sm">
          <h2 className="h2 mb-2">Acting as</h2>
          <p className="text-muted">Sample mode lets you switch who is acting, to exercise roles and separation of duties. In a connected deployment this comes from sign-in.</p>
          <select className="input mt-2" value={user.id} data-testid="user-switcher" onChange={(e) => { const u = SWITCHABLE_USERS.find((x) => x.id === e.target.value); if (u) setUser(u); }}>
            {SWITCHABLE_USERS.map((u) => <option key={u.id} value={u.id}>{u.name} · {u.role}</option>)}
          </select>
          <h2 className="h2 mb-2 mt-4">Mock service behaviour</h2>
          <label className="block">Latency per call: <strong>{mock.latencyMs} ms</strong><input type="range" min={0} max={2000} step={50} value={mock.latencyMs} onChange={(e) => setMock({ latencyMs: Number(e.target.value) })} className="mt-1 w-full" data-testid="latency" /></label>
          <label className="mt-3 block">Random failure rate: <strong>{Math.round(mock.failureRate * 100)}%</strong><input type="range" min={0} max={1} step={0.05} value={mock.failureRate} onChange={(e) => setMock({ failureRate: Number(e.target.value) })} className="mt-1 w-full" data-testid="failure-rate" /></label>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span>Fail the next call to</span>
            <select className="input w-auto" value={mock.failNext ?? ""} onChange={(e) => setMock({ failNext: e.target.value || null })} data-testid="fail-next">
              <option value="">— none —</option>
              {["listProjects", "getProject", "listRuns", "getRun", "listFindings", "getFinding", "approvals.list", "approvals.decide", "requestRun", "assistant.send", "conductor.listTasks"].map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="mt-2 text-xs text-faint">Latency and failure rate persist in this browser (localStorage, guarded). "Fail next" is one-shot.</div>
        </section>
      </div>
    </>
  );
}
