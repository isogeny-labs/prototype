import type { Project } from "@/contracts";
import { useAppStore } from "@/store";

/** Sample mode: switch the acting user among this project's members, to exercise roles and separation of duties. */
export function MemberSwitcher({ project }: { project: Project }) {
  const user = useAppStore((s) => s.user);
  const setUser = useAppStore((s) => s.setUser);
  const members = project.permissions.members.map((m) => ({ m, p: project.people.find((x) => x.id === m.personId) })).filter((x) => x.p);
  const myRole = project.permissions.members.find((m) => m.personId === user.id)?.role ?? "not a member";
  return (
    <label className="flex flex-wrap items-center gap-2 text-xs text-muted">
      <span>Acting as</span>
      <select className="input w-auto" value={user.id} onChange={(e) => { const x = members.find((y) => y.m.personId === e.target.value); if (x?.p) setUser({ id: x.p.id, name: x.p.name, role: `${x.p.role} (${x.p.org}) · ${x.m.role}` }); }} data-testid="member-switcher" aria-label="Acting user (sample mode)">
        {members.map(({ m, p }) => <option key={m.personId} value={m.personId}>{p!.name} · {m.role}</option>)}
        {!members.some((x) => x.m.personId === user.id) ? <option value={user.id}>{user.name} · not a member</option> : null}
      </select>
      <span className="tag">{myRole}</span>
      <span className="text-faint">sample mode; sign-in replaces this</span>
    </label>
  );
}
