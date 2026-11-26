import { useEffect, useState } from "react";
import { api, errorMessage, type DecisionRow, type DecisionsView } from "../../api";
import { usePanelStamp } from "../../changes";
import { DataTable, PageHeader, SummaryCards, TableWithPanel, type Column } from "../layout";
import { ItemLinkView } from "../related";
import { DemoDataLabel, ErrorBox, formatTime } from "../ui";
import { EntryPanel } from "./EntryPanel";
import { DayHeading, EVIDENCE_EYEBROW, FilterChips, NamesNote, Who } from "./parts";

/** The design refactor (26 November 2026): Approvals and decisions, the third view of Evidence. Every decision a
 * person made in the assessment, one row each: when, the decision, what it was on, who, and where. Results are not in
 * this list, and the page says why: no person decides one. A row opens the same story the Timeline shows. It reads
 * the records and repeats them; it decides nothing. */
export function DecisionsPage({
  planId,
  area = null,
  onArea,
  openItem = null,
}: {
  planId: number;
  area?: string | null;
  onArea?: (area: string | null) => void;
  openItem?: string | null;
}) {
  const [view, setView] = useState<DecisionsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ownArea, setOwnArea] = useState<string | null>(area);
  const [openId, setOpenId] = useState<string | null>(openItem);
  const chosenArea = onArea ? area : ownArea;
  const panelStamp = usePanelStamp();

  useEffect(() => {
    let live = true;
    api
      .getDecisions(planId, chosenArea)
      .then((next) => {
        if (!live) return;
        setView(next);
        setError(null);
      })
      .catch((e: unknown) => {
        if (live) setError(errorMessage(e));
      });
    return () => {
      live = false;
    };
  }, [planId, chosenArea, panelStamp]);

  if (!view) {
    return error ? (
      <ErrorBox title="The decisions couldn't be loaded">{error}</ErrorBox>
    ) : (
      <p role="status" className="text-sm text-slate-400">
        Loading…
      </p>
    );
  }

  const columns: Column<DecisionRow>[] = [
    {
      key: "when",
      header: "When",
      minWidth: 150,
      render: (row) => (
        <time dateTime={row.at} className="text-xs tabular-nums text-slate-400">
          {formatTime(row.at)}
        </time>
      ),
    },
    {
      key: "decision",
      header: "Decision",
      minWidth: 130,
      render: (row) => (
        <span data-testid="decision-word" data-decision={row.decision.key} className="font-medium text-slate-100">
          {row.decision.label}
        </span>
      ),
    },
    {
      key: "on",
      header: "On",
      minWidth: 200,
      render: (row) => (
        <span className="min-w-0">
          <span data-testid="decision-on" className="break-words text-slate-200">
            {row.on}
          </span>
          {row.marks.length > 0 ? (
            <span className="mt-1 flex flex-wrap gap-1">
              {row.marks.map((mark) => (
                <span
                  key={mark}
                  className="rounded border border-slate-600 px-1.5 py-0.5 text-[11px] font-medium text-slate-200"
                >
                  {mark}
                </span>
              ))}
            </span>
          ) : null}
        </span>
      ),
    },
    {
      key: "who",
      header: "Who",
      minWidth: 150,
      render: (row) => (
        <span className="text-[13px]">
          <Who who={row.who} testId="decision-who" />
          {row.pressed_by ? (
            // An approval given as a demo reviewer: the name it was recorded under, and who pressed.
            <span data-testid="decision-pressed-by" className="mt-0.5 block text-xs text-slate-400">
              pressed by <Who who={row.pressed_by} testId="decision-pressed-who" />
            </span>
          ) : null}
        </span>
      ),
    },
    {
      key: "where",
      header: "Where",
      minWidth: 120,
      render: (row) =>
        row.link ? (
          <span onClick={(e) => e.stopPropagation()}>
            <ItemLinkView link={row.link} testId="decision-where">
              {row.area.label}
            </ItemLinkView>
          </span>
        ) : (
          <span className="text-xs text-slate-300">{row.area.label}</span>
        ),
    },
  ];
  const compactColumns: Column<DecisionRow>[] = [
    { ...columns[1]!, minWidth: 110 },
    { ...columns[3]!, minWidth: 110 },
  ];

  const chooseArea = (key: string) => {
    const next = key === "all" ? null : key;
    if (onArea) onArea(next);
    else setOwnArea(next);
  };

  return (
    <section aria-label={view.title} data-testid="decisions-page">
      <PageHeader
        eyebrow={
          <>
            {EVIDENCE_EYEBROW}
            {view.is_demo ? (
              <>
                {" "}
                <DemoDataLabel />
              </>
            ) : null}
          </>
        }
        title={view.title}
        description={<span data-testid="decisions-subline">{view.subline}</span>}
      />
      {error ? (
        <div className="mb-3">
          <ErrorBox>{error}</ErrorBox>
        </div>
      ) : null}
      <SummaryCards
        label="Decisions summary"
        cards={view.cards.map((card) => ({ key: card.key, label: card.title, value: card.value, sub: card.small }))}
      />
      <p
        data-testid="decisions-results-note"
        className="mb-4 rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2 text-[13px] text-slate-300"
      >
        {view.results_note}
      </p>
      <div className="mb-4">
        <FilterChips
          label="Where"
          filters={view.areas}
          chosen={view.chosen.area}
          onChoose={chooseArea}
          testId="decisions-where"
        />
      </div>
      <TableWithPanel
        panelOpen={openId !== null}
        table={
          view.days.length === 0 ? (
            <p
              data-testid="decisions-empty"
              className="rounded-xl border border-slate-800 px-4 py-8 text-center text-sm text-slate-400"
            >
              {view.empty_text ?? "No decision matches."}
            </p>
          ) : (
            <div>
              {view.days.map((day) => (
                <section key={day.date} data-testid="decisions-day" data-date={day.date} className="mb-6">
                  <DayHeading date={day.date} count={day.count} noun={["decision", "decisions"]} />
                  <DataTable
                    label={`Decisions of ${day.date}`}
                    columns={columns}
                    compactColumns={compactColumns}
                    rows={day.rows}
                    rowKey={(row) => row.id}
                    rowTestId="decision-row"
                    rowAttrs={(row) => ({ "data-area": row.area.key })}
                    selectedKey={openId}
                    onRowClick={(row) => setOpenId((cur) => (cur === row.id ? null : row.id))}
                  />
                </section>
              ))}
            </div>
          )
        }
        panel={<EntryPanel planId={planId} entryId={openId} onClose={() => setOpenId(null)} />}
      />
      <NamesNote>{view.names_note}</NamesNote>
      <p
        data-testid="disclaimer"
        className="mt-4 rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-300"
      >
        {view.disclaimer}
      </p>
    </section>
  );
}
