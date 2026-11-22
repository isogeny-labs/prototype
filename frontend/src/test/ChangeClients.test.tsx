import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ChangeView, TryClients } from "../api";
import { ChangeBox } from "../components/change/ChangeBox";
import { appliedMatches, readyToApply, triedPassedPicker } from "./changeFixtures";
import { mockApi, text } from "./fixtures";

afterEach(cleanup);

const DECIDES =
  "This is information. Whether the try passed is decided by the system's own measurement above, and Apply is not held off by it: you decide.";
const NOTE =
  "Stand-ins are our own OpenSSL offering what each profile says, not your devices. They check no certificate's trust, and accept only the signature types their profile lists.";
const COLUMNS = ["Client stand-in (Demo data)", "Today", "On the test copy", "Result"];

/** The Acme Pay server's TLS fix (TLS 1.3 only), tried: the old firmware breaks (phase 4e). */
export const TLS_CLIENTS: TryClients = {
  title: "Who can still connect",
  running: null,
  summary: "1 breaks, 2 connect, 1 didn't connect before either.",
  warning: "Sort out the 1 that breaks before you apply this change.",
  columns: COLUMNS,
  rows: [
    {
      id: "old-terminal",
      name: "Payment terminal, old firmware",
      offers: "TLS 1.2 only; classical key exchange (X25519, P-256); classical certificates only.",
      label: "Demo data",
      today: "TLS 1.2, classical (P-256)",
      on_copy: "Refused (protocol version)",
      word: "Breaks",
      word_key: "breaks",
      tone: "fail",
      note: null,
    },
    {
      id: "partner-classical",
      name: "Partner system, classical only",
      offers: "TLS 1.2 and 1.3; classical key exchange.",
      label: "Demo data",
      today: "TLS 1.3, classical (P-256)",
      on_copy: "TLS 1.3, classical (P-256)",
      word: "Connects",
      word_key: "connects",
      tone: "pass",
      note: null,
    },
    {
      id: "new-terminal",
      name: "Payment terminal, new firmware",
      offers: "TLS 1.2 and 1.3; hybrid first.",
      label: "Demo data",
      today: "TLS 1.3, classical (P-256)",
      on_copy: "TLS 1.3, classical (P-256)",
      word: "Connects",
      word_key: "connects",
      tone: "pass",
      note: null,
    },
    {
      id: "pq-only",
      name: "Post-quantum-only client",
      offers: "TLS 1.3 only; ML-KEM-768 by itself.",
      label: "Demo data",
      today: "Refused (handshake failure)",
      on_copy: "Refused (handshake failure)",
      word: "Didn't connect before either",
      word_key: "not_before",
      tone: "neutral",
      note: null,
    },
  ],
  note: NOTE,
  decides: DECIDES,
  control:
    "Control: the same stand-ins on our own hybrid and classical test servers, started for this run, read as they must.",
  no_answer: null,
};

const withClients = (base: ChangeView, clients: TryClients): ChangeView => ({
  ...base,
  try: { ...base.try!, clients },
});

function show(change: ChangeView) {
  const fetchMock = mockApi({});
  render(<ChangeBox change={change} planId={1} onChanged={async () => undefined} onViewFix={() => undefined} />);
  return fetchMock;
}

describe("Who can still connect, in a try (phase 4e)", () => {
  it("draws each stand-in's handshake today and on the copy, with the reviewer's word, exactly as sent", () => {
    show(withClients(triedPassedPicker, TLS_CLIENTS));
    const block = within(screen.getByTestId("change-clients"));
    expect(block.getByText("Who can still connect")).toBeTruthy();
    expect(block.getByTestId("clients-summary").textContent).toBe(
      "1 breaks, 2 connect, 1 didn't connect before either.",
    );
    expect(block.getByTestId("clients-warning").textContent).toBe(
      "Sort out the 1 that breaks before you apply this change.",
    );
    expect(block.getByRole("list", { name: COLUMNS[0] })).toBeTruthy();
    const rows = block.getAllByTestId("clients-row");
    expect(rows.map((r) => r.getAttribute("data-word"))).toEqual(["breaks", "connects", "connects", "not_before"]);
    const first = within(rows[0]!);
    expect(first.getByTestId("clients-word").textContent).toContain("Breaks");
    expect(first.getByTestId("clients-word").getAttribute("data-tone")).toBe("fail");
    expect(first.getAllByRole("term").map((t) => t.textContent)).toEqual(["Today", "On the test copy"]);
    expect([first.getByTestId("clients-today").textContent, first.getByTestId("clients-copy").textContent]).toEqual([
      "TLS 1.2, classical (P-256)",
      "Refused (protocol version)",
    ]);
    // the word comes first in the row, before the name
    expect(rows[0]!.textContent!.indexOf("Breaks")).toBeLessThan(
      rows[0]!.textContent!.indexOf("Payment terminal, old firmware"),
    );
    expect(block.getByTestId("clients-decides").textContent).toBe(DECIDES);
    expect(block.getByTestId("clients-note").textContent).toBe(NOTE);
  });

  it("has no button of its own, and a Breaks leaves the change box's buttons as the backend sent them", () => {
    show(withClients(readyToApply, TLS_CLIENTS));
    const block = screen.getByTestId("change-clients");
    expect(within(block).queryAllByRole("button")).toHaveLength(0);
    const apply = screen.getByRole("button", { name: /^Apply to/ }) as HTMLButtonElement;
    expect(apply.disabled).toBe(false); // the warning holds nothing off: the person decides
    expect(block.textContent).not.toMatch(/secure|score|severity/i);
  });

  it("says when it is running, and when the stand-ins gave no answer", () => {
    show(
      withClients(triedPassedPicker, {
        ...TLS_CLIENTS,
        running: {
          status: "running",
          status_text: "Running",
          progress: { text: "connecting the client stand-ins", percent: null },
        },
        rows: [],
      }),
    );
    expect(within(screen.getByTestId("change-clients")).queryByTestId("clients-row")).toBeNull();
    cleanup();
    show(
      withClients(triedPassedPicker, {
        ...TLS_CLIENTS,
        summary: null,
        warning: null,
        rows: [],
        no_answer: "No answer from the client stand-ins: the control did not behave as it must.",
      }),
    );
    expect(screen.getByTestId("clients-no-answer").textContent).toBe(
      "No answer from the client stand-ins: the control did not behave as it must.",
    );
  });

  it("draws nothing for a try made before this check", () => {
    show(triedPassedPicker);
    expect(screen.queryByTestId("change-clients")).toBeNull();
    expect(screen.getByTestId("change-try")).toBeTruthy();
  });
});

// 22 November 2026: where a server change's steps came from. Before is a reading of the server (Observed live), the try
// a test copy on this computer (Proven in the lab), and After Apply a new reading of the server itself (Observed live).
describe("A server change, where each step came from", () => {
  it("tags the try's columns and its verdict, and After Apply, each beside its own word", () => {
    const fetchMock = show(appliedMatches);
    const tryBox = within(screen.getByTestId("change-try"));
    expect(
      tryBox.getAllByTestId("column-source-tag").map((t) => [t.textContent, t.getAttribute("data-source")]),
    ).toEqual([
      ["Observed live", "live"],
      ["Proven in the lab", "lab"],
    ]);
    const verdict = tryBox.getByTestId("change-verdict");
    expect(within(verdict).getByTestId("source-tag").textContent).toBe("Proven in the lab");
    expect(text(verdict)).toContain("Try passed. Proven in the lab The copy measures what Hybrid promises");
    expect(text(within(verdict).getByTestId("source-note"))).toBe(
      "Run on a test copy of the server on this computer, with the change. Your live server was not changed.",
    );
    const applied = screen.getByTestId("change-applied-badge").parentElement!;
    expect(within(applied).getByTestId("source-tag").textContent).toBe("Observed live");
    expect(within(applied).getByTestId("source-tag").getAttribute("title")).toContain("handshakes only");
    expect(fetchMock.mock.calls).toEqual([]);
  });

  it("a try that gave no answer has no tag, and a copy that measured nothing has none above its column", () => {
    const noAnswer: ChangeView = {
      ...appliedMatches,
      applied: null,
      try: {
        ...appliedMatches.try!,
        verdict: {
          label: "No answer from the try.",
          look: "warn",
          text: "A copy could not be measured, or its control did not behave.",
        },
        source_tag: null,
        column_source_tags: [null, appliedMatches.try!.column_source_tags![1]!, null],
      },
    };
    show(noAnswer);
    const tryBox = within(screen.getByTestId("change-try"));
    expect(within(tryBox.getByTestId("change-verdict")).queryAllByTestId("source-tag")).toEqual([]);
    expect(tryBox.getAllByTestId("column-source-tag").map((t) => t.textContent)).toEqual(["Observed live"]);
  });
});
