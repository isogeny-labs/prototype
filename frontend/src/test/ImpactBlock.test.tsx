import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type DependenciesView as View, type FixesView, type Impact } from "../api";
import { DependenciesView } from "../components/dependencies/DependenciesView";
import { FixesScreen } from "../components/FixesScreen";
import { ImpactBlock } from "../components/impact/ImpactBlock";
import { LinkProvider } from "../components/related";
import { DEPENDENCIES_DEMO } from "./dependenciesFixtures";
import { TLS_FIX, fixesViews } from "./fixesFixtures";
import { mockApi } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** The block on the Acme Pay server's TLS fix, as the backend words it (phase 4e). */
export const TLS_IMPACT: Impact = {
  title: "What this change touches",
  part: "localhost:8443",
  count: 2,
  count_line: "Re-check these 2 after the change.",
  here: {
    title: "In this assessment",
    lines: [
      {
        text: "localhost:8443",
        sub: "A server in your scanner file.",
        tag: "from your file",
        chip: null,
        link: { page: "migration/systems", item: "server:localhost:8443" },
      },
      {
        text: "acme-pay-server 1.0.0",
        sub: "From your dependency list: your own software. Part of localhost:8443 (set by you).",
        tag: "from your file",
        chip: null,
        link: { page: "migration/systems", item: "server:localhost:8443" },
      },
    ],
    none: null,
  },
  elsewhere: {
    title: "Elsewhere in your organization",
    lines: [
      {
        text: "Multi-target › Assessment 1",
        sub: "Names localhost:8443 as a server (the same address).",
        tag: "from your file",
        chip: "Open",
        link: { page: "migration/systems", item: "server:localhost:8443", assessment_id: 9 },
      },
    ],
    none: null,
  },
  notes: ["Apply changes this one server for every assessment that names it."],
  compatible: null,
  connect: {
    title: "Who can still connect",
    text: "This change alters what the server offers on the network. Try on a test copy, in the change box below, also connects four demo client stand-ins and shows who can still connect.",
  },
};

const LIBRARY_IMPACT: Impact = {
  title: "Where it is used",
  part: "openssl 3.0.22",
  count: 1,
  count_line: "Re-check this one if you change it.",
  here: {
    title: "In this assessment",
    lines: [
      {
        text: "acme-pay-server 1.0.0",
        sub: "Your own software, from your dependency list. Uses it, through python 3.12.3. Part of localhost:8443 (set by you).",
        tag: "from your file",
        chip: null,
        link: { page: "migration/systems", item: "server:localhost:8443" },
      },
    ],
    none: null,
  },
  elsewhere: {
    title: "Elsewhere in your organization",
    lines: [],
    none: "No other assessment in your organization names it.",
  },
  notes: ["A dependency list says what is installed, not what a program really loads: that needs your environment."],
  compatible: null,
  connect: null,
};

describe("Where it is used (phase 4e)", () => {
  it("draws every place, sentence and count exactly as sent, with its source tag", () => {
    render(
      <LinkProvider assessmentId={3} planId={1}>
        <ImpactBlock impact={TLS_IMPACT} />
      </LinkProvider>,
    );
    const block = screen.getByTestId("impact");
    expect(within(block).getByRole("heading", { name: "What this change touches" })).toBeTruthy();
    expect(within(block).getByTestId("impact-count").textContent).toBe("Re-check these 2 after the change.");
    const here = within(screen.getByTestId("impact-here"));
    expect(here.getAllByTestId("impact-line").map((l) => l.textContent)).toEqual([
      "localhost:8443from your fileA server in your scanner file.",
      "acme-pay-server 1.0.0from your fileFrom your dependency list: your own software. Part of localhost:8443 (set by you).",
    ]);
    const elsewhere = within(screen.getByTestId("impact-elsewhere"));
    expect(elsewhere.getByTestId("impact-chip").textContent).toContain("Open");
    expect(
      within(block)
        .getAllByTestId("impact-note")
        .map((n) => n.textContent),
    ).toEqual(["Apply changes this one server for every assessment that names it."]);
    expect(within(block).getByTestId("impact-connect").textContent).toBe(TLS_IMPACT.connect!.text);
    expect(within(block).queryByTestId("impact-compatible")).toBeNull();
  });

  it("links each place to its item, in this assessment or in the other one it names", () => {
    render(
      <LinkProvider assessmentId={3} planId={1}>
        <ImpactBlock impact={TLS_IMPACT} />
      </LinkProvider>,
    );
    const links = screen.getAllByTestId("impact-link").map((a) => a.getAttribute("href"));
    expect(links[0]).toBe("#/a/3/migration/systems?item=server%3Alocalhost%3A8443");
    expect(links[2]).toBe("#/a/9/migration/systems?item=server%3Alocalhost%3A8443");
  });

  it("has no button, no score and no 'secure': it only opens pages", () => {
    const fetchMock = mockApi({});
    render(
      <LinkProvider assessmentId={3} planId={1}>
        <ImpactBlock
          impact={{ ...TLS_IMPACT, compatible: { title: "Can the parts that use it take 1.4.3?", text: "Not known." } }}
        />
      </LinkProvider>,
    );
    const block = screen.getByTestId("impact");
    expect(within(block).queryAllByRole("button")).toHaveLength(0);
    expect(block.textContent).not.toMatch(/secure|score|severity/i);
    expect(within(block).getByTestId("impact-compatible").textContent).toBe("Not known.");
    fireEvent.click(screen.getAllByTestId("impact-link")[0]!);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says why a part is empty, and draws nothing without a block", () => {
    const { container } = render(<ImpactBlock impact={null} />);
    expect(container.textContent).toBe("");
    render(
      <ImpactBlock
        impact={{
          ...LIBRARY_IMPACT,
          here: {
            title: "In this assessment",
            lines: [],
            none: "Nothing in this assessment's scanner file or dependency list names it.",
          },
        }}
      />,
    );
    expect(screen.getAllByTestId("impact-none").map((n) => n.textContent)).toEqual([
      "Nothing in this assessment's scanner file or dependency list names it.",
      "No other assessment in your organization names it.",
    ]);
  });

  it("sits in a fix's panel on Fixes, under the summary", async () => {
    const base = fixesViews.ready;
    const view: FixesView = {
      ...base,
      fixes: base.fixes.map((f) => (f.id === TLS_FIX ? { ...f, impact: TLS_IMPACT } : f)),
    };
    mockApi({ "GET /api/plans/1/fixes": { body: view } });
    render(
      <FixesScreen
        planId={1}
        selectedId={TLS_FIX}
        onSelect={() => undefined}
        onRetestStarted={() => undefined}
        group={null}
      />,
    );
    await screen.findByTestId("fix-summary");
    const panel = screen.getByTestId("detail-panel");
    const block = within(panel).getByTestId("impact");
    expect(block.textContent).toContain("Re-check these 2 after the change.");
    // after the summary, in the order of the panel
    expect(
      within(panel).getByTestId("fix-summary").compareDocumentPosition(block) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("sits in a library's panel on Dependencies", async () => {
    const view: View = {
      ...DEPENDENCIES_DEMO,
      groups: DEPENDENCIES_DEMO.groups.map((g) => ({
        ...g,
        rows: g.rows.map((r) => (r.label === "openssl 3.0.22" ? { ...r, impact: LIBRARY_IMPACT } : r)),
      })),
    };
    vi.spyOn(api, "getDependencies").mockResolvedValue(view);
    render(<DependenciesView importId={1} onViewFix={vi.fn()} onChanged={vi.fn()} />);
    await screen.findByTestId("dependencies-subline");
    const row = screen
      .getAllByTestId("dependency-row")
      .find((r) => r.querySelector("p.font-mono")?.textContent === "openssl 3.0.22")!;
    fireEvent.click(row);
    const panel = within(screen.getByTestId("detail-panel"));
    expect(panel.getByTestId("impact").textContent).toContain("Re-check this one if you change it.");
    expect(panel.getByRole("heading", { name: "Where it is used" })).toBeTruthy();
  });
});
