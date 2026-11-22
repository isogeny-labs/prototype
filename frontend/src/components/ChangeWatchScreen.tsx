import { useEffect, useRef, useState } from "react";
import { usePanelStamp } from "../changes";
import { api, errorMessage, type ChangeRow, type ChangeWatchView } from "../api";
import { ChangePanelView } from "./changewatch/ChangePanelView";
import { DataTable, PageHeader, TableWithPanel, type Column } from "./layout";
import { ItemLinkView } from "./related";
import { DemoDataLabel, ErrorBox, SecondaryButton, StatusChip, useDismiss } from "./ui";

const POLL_MS = 1000;

interface Props {
  planId: number;
  /** A change to open (from a link: #/a/<id>/change-watch?item=<change id>). */
  openItem?: string | null;
}

/** The status word of a change, with the count of its flags under it. The word is the backend's. */
function StatusCell({ row }: { row: ChangeRow }) {
  return (
    <>
      <StatusChip label={row.status.word} tone={row.status.tone} size="sm" wrap testId="change-status" />
      {row.flags_count > 0 ? (
        <span data-testid="change-flags-count" className="mt-1 block text-xs text-slate-400">
          {row.flags_count === 1 ? "1 flag" : `${row.flags_count} flags`}
        </span>
      ) : null}
    </>
  );
}

function NameCell({ row }: { row: ChangeRow }) {
  return (
    <>
      <span className="block break-words font-medium text-slate-100">{row.title}</span>
      <span className="mt-0.5 block break-words font-mono text-xs text-slate-400">{row.branch}</span>
      {row.is_demo ? (
        <span className="mt-1 block">
          <DemoDataLabel />
        </span>
      ) : null}
    </>
  );
}

/** Phase 6d: Change watch, the Changes view. Every developer's change in the connected demo repository, the tests
 * picked for it and why, and (after a click) what they show beside the results on the code before. Reading this page
 * runs nothing. Every word, status and reason is the backend's: this page words no result and decides none. */
export function ChangeWatchScreen({ planId, openItem = null }: Props) {
  const [view, setView] = useState<ChangeWatchView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [pollTick, setPollTick] = useState(0);
  const [sending, setSending] = useState(false);
  const [openId, setOpenId] = useState<string | null>(openItem);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useDismiss(menuOpen, menuRef, () => setMenuOpen(false));
  // The newest request for the page's view: an answer that comes back after a newer one was asked for is dropped.
  const asked = useRef(0);
  // A start sent from the Otto panel (Run the picked tests, behind its Confirm): this page reads its view again.
  const panelStamp = usePanelStamp();

  useEffect(() => setOpenId(openItem), [openItem]);

  useEffect(() => {
    const mine = ++asked.current;
    api
      .getChangeWatch(planId)
      .then((next) => {
        if (asked.current !== mine) return;
        setView(next);
        setError(null);
      })
      .catch((e: unknown) => {
        if (asked.current === mine) setError(errorMessage(e));
      });
    return () => {
      asked.current += 1;
    };
  }, [planId, panelStamp]);

  // While anything runs for this assessment, ask again every second (the page shows the progress of a change's picked
  // tests, then the results). A read that fails is said on the page, and the page asks again all the same: it must not
  // stay on "Running" after the run has finished.
  const busy = view?.busy === true;
  useEffect(() => {
    if (!busy) {
      setPollError(null);
      return;
    }
    let live = true;
    const mine = asked.current;
    const timer = setTimeout(() => {
      api
        .getChangeWatch(planId)
        .then((next) => {
          if (!live) return;
          if (asked.current === mine) {
            setView(next);
            setPollError(null);
          }
          setPollTick((n) => n + 1);
        })
        .catch((e: unknown) => {
          if (!live) return;
          if (asked.current === mine) setPollError(errorMessage(e));
          setPollTick((n) => n + 1);
        });
    }, POLL_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [busy, pollTick, planId]);

  /** One of the page's two actions. Its answer is the whole view as it now stands. */
  async function act(send: () => Promise<ChangeWatchView>, then?: (next: ChangeWatchView) => void) {
    setSending(true);
    setActionError(null);
    asked.current += 1; // (an older read of the page must not land on top of this answer)
    try {
      const next = await send();
      setView(next);
      then?.(next);
    } catch (e) {
      setActionError(errorMessage(e));
    } finally {
      setSending(false);
    }
  }

  if (!view) {
    return (
      <section data-testid="change-watch-page" aria-label="Change watch">
        <PageHeader title="Change watch" />
        {error ? (
          <ErrorBox>{error}</ErrorBox>
        ) : (
          <p role="status" className="text-sm text-slate-400">
            Loading…
          </p>
        )}
      </section>
    );
  }

  const opened = view.changes.find((c) => c.id === openId) ?? null;
  const columns: Column<ChangeRow>[] = [
    { key: "change", header: "Change", minWidth: 170, render: (r) => <NameCell row={r} /> },
    {
      key: "who",
      header: "Who and when",
      minWidth: 130,
      render: (r) => (
        <span className="text-xs text-slate-300">
          <span className="block">{r.author ?? "Unknown"}</span>
          {r.when ? <span className="block text-slate-400">{r.when}</span> : null}
          <span className="block font-mono text-slate-400">commit {r.commit}</span>
        </span>
      ),
    },
    { key: "files", header: "Files", minWidth: 130, render: (r) => <span className="break-words text-xs text-slate-300">{r.files_line ?? "None read"}</span> },
    { key: "picked", header: "Tests picked", minWidth: 96, render: (r) => <span className="text-xs text-slate-300">{r.picked_line}</span> },
    { key: "status", header: "Status", minWidth: 140, render: (r) => <StatusCell row={r} /> },
  ];
  const compactColumns: Column<ChangeRow>[] = [
    { key: "change", header: "Change", minWidth: 150, render: (r) => <NameCell row={r} /> },
    { key: "status", header: "Status", minWidth: 130, render: (r) => <StatusCell row={r} /> },
  ];

  return (
    <section data-testid="change-watch-page" aria-label={view.title}>
      <PageHeader
        title={view.title}
        description={view.subline}
        actions={
          <div ref={menuRef} className="relative">
            <SecondaryButton expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)} testId="demo-change-button">
              {view.menu.button}
            </SecondaryButton>
            {menuOpen ? (
              <div
                role="menu"
                aria-label={view.menu.button}
                data-testid="demo-change-menu"
                className="absolute right-0 z-20 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-700 bg-slate-900 p-2 shadow-xl"
              >
                <p className="flex flex-wrap items-center gap-2 px-2 pb-2 pt-1 text-xs text-slate-400">
                  <DemoDataLabel />
                  <span className="min-w-0 break-words">{view.menu.note}</span>
                </p>
                {view.menu.items.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    role="menuitem"
                    data-testid="demo-change-item"
                    data-key={item.key}
                    disabled={!item.can || sending}
                    onClick={() => {
                      setMenuOpen(false);
                      void act(
                        () => api.bringInDemoChange(planId, item.key),
                        (next) => setOpenId(next.changes[0]?.id ?? null),
                      );
                    }}
                    className="block w-full rounded-lg px-2 py-2 text-left text-sm text-slate-100 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-500 disabled:hover:bg-transparent"
                  >
                    <span className="block font-medium">{item.title}</span>
                    <span className="mt-0.5 block text-xs text-slate-400">{item.what_it_does}</span>
                    {item.blocked_reason ? (
                      <span data-testid="demo-change-blocked" className="mt-0.5 block text-xs text-slate-400">
                        {item.blocked_reason}
                      </span>
                    ) : null}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        }
      />

      {view.code.line ? (
        <p data-testid="change-watch-code-line" role="note" className="mb-5 break-words rounded-xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-slate-200">
          {view.code.line}{" "}
          {view.code.link ? (
            <ItemLinkView link={view.code.link} testId="change-watch-code-link" className="text-sky-300 underline-offset-2 hover:underline">
              Open Fixes
            </ItemLinkView>
          ) : null}
        </p>
      ) : null}
      {view.code.connected_line ? (
        <p data-testid="change-watch-connected" className="mb-4 text-xs text-slate-400">
          {view.code.connected_line}
        </p>
      ) : null}
      {actionError ? (
        <div className="mb-4">
          <ErrorBox>{actionError}</ErrorBox>
        </div>
      ) : null}
      {pollError ? (
        <div className="mb-4" data-testid="change-watch-stale">
          <ErrorBox title="This page could not be read again, so it may be behind. It asks again every second.">{pollError}</ErrorBox>
        </div>
      ) : null}

      {view.code.state === "connected" ? (
        <TableWithPanel
          panelOpen={opened !== null}
          table={
            <div data-testid="changes-table">
              <DataTable
                label="Changes"
                columns={columns}
                compactColumns={compactColumns}
                rows={view.changes}
                rowKey={(r) => r.id}
                rowTestId="change-row"
                rowAttrs={(r) => ({ "data-change": r.id, "data-status": r.status.key })}
                selectedKey={openId}
                onRowClick={(r) => setOpenId(r.id === openId ? null : r.id)}
                empty={view.empty ? <span data-testid="changes-empty">{view.empty}</span> : undefined}
              />
            </div>
          }
          panel={
            <ChangePanelView
              row={opened}
              sending={sending}
              onClose={() => setOpenId(null)}
              onRun={(row) => void act(() => api.runPickedTests(planId, row.id))}
            />
          }
        />
      ) : null}
    </section>
  );
}
