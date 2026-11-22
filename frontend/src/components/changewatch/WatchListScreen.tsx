import { useCallback, useState, type ReactNode } from "react";
import { api, errorMessage, type WatchItem, type WatchListView } from "../../api";
import { DataTable, DetailPanel, Modal, PageHeader, TableWithPanel, type Column } from "../layout";
import { ItemLinkView } from "../related";
import { ErrorBox, PrimaryButton, SecondaryButton, StatusChip, WhereFromTag } from "../ui";

const H = "mb-1.5 text-[13px] font-semibold text-slate-100";
const BOX = "rounded-lg border border-slate-800 bg-slate-950 p-3";

interface Props {
  planId: number;
  view: WatchListView;
  /** Every action answers with the whole list as it now stands. */
  onView: (next: WatchListView) => void;
  /** An item to open (from a link: #/a/<id>/change-watch?section=watch-list&item=<key>). */
  openItem?: string | null;
  tabs: ReactNode;
}

function NewTag() {
  return (
    <span
      data-testid="watch-new"
      title="The newest look brought it, or changed it"
      className="ml-0.5 inline-block whitespace-nowrap rounded border border-sky-400/50 bg-sky-400/10 px-1.5 py-px align-middle text-[11px] font-semibold leading-tight text-sky-100"
    >
      New
    </span>
  );
}

function NameCell({ row }: { row: WatchItem }) {
  return (
    <>
      <span className="block break-words font-medium text-slate-100">
        {row.title} {row.new ? <NewTag /> : null}
      </span>
      <span className="mt-0.5 block whitespace-nowrap font-mono text-xs text-slate-400">{row.id}</span>
    </>
  );
}

function StatusCell({ row }: { row: WatchItem }) {
  return (
    <>
      <span className="flex flex-wrap items-center gap-1.5">
        <StatusChip label={row.status.word} tone={row.status.tone} size="sm" wrap testId="watch-status" />
        <WhereFromTag tag={row.source} />
      </span>
      {row.status_line ? (
        <span data-testid="watch-status-line" className="mt-1 block break-words text-xs text-slate-400">
          {row.status_line}
        </span>
      ) : null}
    </>
  );
}

/** Stop watching: the first click only opens the box that asks for an optional reason; nothing is sent before the click
 * in that box. The box belongs to one item while it is watched (it is keyed by the item and drawn only then), so a
 * half-typed reason never moves to another item, and an item that is watched again starts with the box shut. Nothing
 * here is set after a drawing: a click is never undone by the page itself. */
function StopBox({
  row,
  stop,
  sending,
  onStop,
}: {
  row: WatchItem;
  stop: NonNullable<WatchItem["panel"]["stop"]>;
  sending: boolean;
  onStop: (row: WatchItem, reason: string | null) => void;
}) {
  const [reason, setReason] = useState("");
  const [asking, setAsking] = useState(false);
  return (
    <div data-testid="watch-stop-box" className={BOX}>
      {asking ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!sending) onStop(row, reason.trim() || null);
          }}
        >
          <label htmlFor="watch-stop-reason" className="block text-xs text-slate-400">
            {stop.reason_label}
          </label>
          <input
            id="watch-stop-reason"
            data-testid="watch-stop-reason"
            value={reason}
            maxLength={stop.max}
            onChange={(e) => setReason(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          />
          <p className="mt-1.5 break-words text-xs text-slate-400">{stop.note}</p>
          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <SecondaryButton testId="watch-stop-cancel" disabled={sending} onClick={() => setAsking(false)}>
              Cancel
            </SecondaryButton>
            <PrimaryButton type="submit" testId="watch-stop-confirm" disabled={sending} busy={sending}>
              {stop.label}
            </PrimaryButton>
          </div>
        </form>
      ) : (
        <>
          <SecondaryButton testId="watch-stop" disabled={!stop.can || sending} onClick={() => setAsking(true)}>
            {stop.label}
          </SecondaryButton>
          {stop.blocked_reason ? (
            <p data-testid="watch-stop-blocked" className="mt-1.5 break-words text-xs text-slate-400">
              {stop.blocked_reason}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}

/** One watched weakness: what its publisher says (quoted), the versions it names, where a test for it stands, its
 * history, and Stop watching or Watch again. Every word is the backend's. */
function ItemPanel({
  row,
  sending,
  onClose,
  onStop,
  onWatch,
}: {
  row: WatchItem | null;
  sending: boolean;
  onClose: () => void;
  onStop: (row: WatchItem, reason: string | null) => void;
  onWatch: (row: WatchItem) => void;
}) {
  if (!row) return null;
  const { panel } = row;
  return (
    <div data-testid="watch-panel" data-item={row.key}>
      <DetailPanel
        open
        item={row.key}
        title={row.title}
        subtitle={<span className="break-words">{panel.ids_line}</span>}
        onClose={onClose}
      >
        <div className="space-y-5 text-sm text-slate-300">
          <div>
            <span className="flex flex-wrap items-center gap-1.5">
              <StatusChip label={row.status.word} tone={row.status.tone} wrap testId="watch-panel-status" />
              <WhereFromTag tag={row.source} />
            </span>
            {row.status_line ? (
              <p className="mt-1.5 break-words text-[13px] text-slate-300">{row.status_line}</p>
            ) : null}
            {row.source.note ? (
              <p data-testid="source-note" className="mt-1 break-words text-xs text-slate-400">
                {row.source.note}
              </p>
            ) : null}
            <p className="mt-1 break-words text-xs text-slate-400">
              {row.since} {panel.published_line}
            </p>
          </div>

          {panel.quote ? (
            <div data-testid="watch-quote">
              <h3 className={H}>{panel.quote.title}</h3>
              <div className={BOX}>
                {panel.quote.lines.map((line) => (
                  <blockquote
                    key={line}
                    className="mb-2 break-words border-l-2 border-slate-600 pl-3 text-[13px] leading-snug text-slate-200 last:mb-0"
                  >
                    {line}
                  </blockquote>
                ))}
                <p className="mt-2 break-words text-xs text-slate-400">
                  <span
                    data-testid="watch-quote-tag"
                    className="rounded border border-slate-700 px-1.5 py-0.5 text-[11px]"
                  >
                    {panel.quote.tag}
                  </span>{" "}
                  {panel.quote.source_line}
                </p>
              </div>
            </div>
          ) : null}

          <div data-testid="watch-versions">
            <h3 className={H}>{panel.versions.title}</h3>
            <ul className="space-y-1 text-[13px]">
              {panel.versions.lines.map((line) => (
                <li key={line} className="break-words">
                  {line}
                </li>
              ))}
            </ul>
            <ul data-testid="watch-yours" className="mt-2 space-y-1 text-[13px] text-slate-200">
              {panel.versions.yours.map((line) => (
                <li key={line} className="break-words">
                  {line}
                </li>
              ))}
            </ul>
          </div>

          {panel.test ? (
            <div data-testid="watch-test">
              <h3 className={H}>A test for it</h3>
              {panel.test.line ? <p className="break-words text-[13px]">{panel.test.line}</p> : null}
              {panel.test.link && panel.test.link_label ? (
                <p className="mt-1 text-xs">
                  <ItemLinkView
                    link={panel.test.link}
                    testId="watch-test-link"
                    className="text-sky-300 underline-offset-2 hover:underline"
                  >
                    {panel.test.link_label}
                  </ItemLinkView>
                </p>
              ) : null}
            </div>
          ) : null}

          <div data-testid="watch-history">
            <h3 className={H}>{panel.history.title}</h3>
            <ol className="space-y-1 text-[13px]">
              {panel.history.lines.map((line, i) => (
                <li key={`${i}-${line}`} className="break-words">
                  {line}
                </li>
              ))}
            </ol>
          </div>

          {panel.stop ? <StopBox key={row.key} row={row} stop={panel.stop} sending={sending} onStop={onStop} /> : null}
          {panel.watch ? (
            <div data-testid="watch-again-box" className={BOX}>
              <SecondaryButton testId="watch-again" disabled={!panel.watch.can || sending} onClick={() => onWatch(row)}>
                {panel.watch.label}
              </SecondaryButton>
              {panel.watch.blocked_reason ? (
                <p data-testid="watch-again-blocked" className="mt-1.5 break-words text-xs text-slate-400">
                  {panel.watch.blocked_reason}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </DetailPanel>
    </div>
  );
}

/** Sandbox research (prototype): the Watch list, Change watch's second view. Published weaknesses in the libraries the
 * file names that have no fix yet, where each stands, and what changed from look to look. Reading it sends nothing.
 * Look now first opens a box that says what is sent; nothing is sent before the click in that box. Every word, status
 * and reason is the backend's: this page words no result and decides none. */
export function WatchListScreen({ planId, view, onView, openItem = null, tabs }: Props) {
  const [openKey, setOpenKey] = useState<string | null>(openItem);
  // A link that names another item while the page is open opens that item. It is done while drawing, and only when the
  // link's item changed: an effect would also run once after the first drawing, and would then undo a click that came
  // in between (seen once in the GitHub checks, 22 November 2026).
  const [named, setNamed] = useState<string | null>(openItem);
  if (named !== openItem) {
    setNamed(openItem);
    setOpenKey(openItem);
  }
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const closeBox = useCallback(() => setAsking(false), []);

  async function act(send: () => Promise<WatchListView>) {
    setSending(true);
    setError(null);
    try {
      onView(await send());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSending(false);
    }
  }

  const all = [...view.items, ...view.stopped];
  const opened = all.find((r) => r.key === openKey) ?? null;
  const columns: Column<WatchItem>[] = [
    { key: "weakness", header: "Weakness", minWidth: 190, render: (r) => <NameCell row={r} /> },
    {
      key: "library",
      header: "Library",
      minWidth: 150,
      render: (r) => <span className="break-words text-xs text-slate-300">{r.yours}</span>,
    },
    { key: "status", header: "Status", minWidth: 170, render: (r) => <StatusCell row={r} /> },
    {
      key: "since",
      header: "Since",
      minWidth: 130,
      render: (r) => <span className="break-words text-xs text-slate-400">{r.since}</span>,
    },
  ];
  const compact: Column<WatchItem>[] = [
    { key: "weakness", header: "Weakness", minWidth: 170, render: (r) => <NameCell row={r} /> },
    { key: "status", header: "Status", minWidth: 150, render: (r) => <StatusCell row={r} /> },
  ];
  const table = (rows: WatchItem[], label: string, testId: string, empty?: string | null) => (
    <div data-testid={testId}>
      <DataTable
        label={label}
        columns={columns}
        compactColumns={compact}
        rows={rows}
        rowKey={(r) => r.key}
        rowTestId="watch-row"
        rowAttrs={(r) => ({ "data-item": r.key, "data-status": r.status.key })}
        selectedKey={openKey}
        onRowClick={(r) => setOpenKey(r.key === openKey ? null : r.key)}
        empty={empty ? <span data-testid="watch-empty">{empty}</span> : undefined}
      />
    </div>
  );
  const look = view.look;

  return (
    <section data-testid="watch-list-page" aria-label="Change watch: Watch list">
      <PageHeader
        title="Change watch"
        description={view.intro}
        actions={
          look ? (
            <SecondaryButton testId="watch-look" disabled={!look.can || sending} onClick={() => setAsking(true)}>
              {look.button}
            </SecondaryButton>
          ) : undefined
        }
      />
      {tabs}
      <p data-testid="watch-looked-line" className="mb-1 break-words text-sm text-slate-300">
        {view.looked_line} {view.next_line ? <span data-testid="watch-next-line">{view.next_line}</span> : null}
      </p>
      {look?.blocked_reason ? (
        <p data-testid="watch-look-blocked" className="mb-1 break-words text-xs text-slate-400">
          {look.blocked_reason}
        </p>
      ) : null}
      {view.count_line ? (
        <p data-testid="watch-count-line" className="mb-3 break-words text-sm text-slate-200">
          {view.count_line}
        </p>
      ) : (
        <div className="mb-3" />
      )}
      {error ? (
        <div className="mb-4" data-testid="watch-error">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}

      <TableWithPanel
        panelOpen={opened !== null}
        table={
          <>
            {table(
              view.items,
              "Watch list",
              "watch-table",
              view.empty_line ?? (view.items.length === 0 ? "Nothing is being watched." : null),
            )}
            {view.stopped.length > 0 ? (
              <div className="mt-6">
                <h3 className="mb-2 text-sm font-semibold text-slate-200">Not watched ({view.stopped.length})</h3>
                {table(view.stopped, "Not watched", "watch-stopped-table")}
              </div>
            ) : null}
            {view.note ? (
              <p data-testid="watch-note" className="mt-4 break-words text-xs text-slate-400">
                {view.note}
              </p>
            ) : null}
          </>
        }
        panel={
          <ItemPanel
            row={opened}
            sending={sending}
            onClose={() => setOpenKey(null)}
            onStop={(row, reason) => void act(() => api.watchListStop(planId, row.key, reason))}
            onWatch={(row) => void act(() => api.watchListWatch(planId, row.key))}
          />
        }
      />

      {asking && look ? (
        <Modal title={look.box.title} onClose={closeBox} testId="watch-look-box">
          <ul className="list-disc space-y-2 pl-5 text-sm text-slate-300">
            {look.box.lines.map((line) => (
              <li key={line} className="break-words">
                {line}
              </li>
            ))}
          </ul>
          <div className="mt-5 flex justify-end gap-2">
            <SecondaryButton testId="watch-look-cancel" disabled={sending} onClick={closeBox}>
              {look.box.cancel}
            </SecondaryButton>
            <PrimaryButton
              testId="watch-look-confirm"
              disabled={sending}
              busy={sending}
              onClick={() => {
                // The one click that sends the look. Done or refused, the box closes: a refusal is shown on the page.
                void act(() => api.watchListLook(planId)).finally(closeBox);
              }}
            >
              {look.box.confirm}
            </PrimaryButton>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}
