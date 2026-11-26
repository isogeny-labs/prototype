import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { ObservatoryPage } from "../components/observatory/ObservatoryPage";
import { LinkProvider } from "../components/related";
import { calls, mockApi, text } from "./fixtures";
import { observatoryChecked, observatoryFileOnly, serverPanel, testPlace } from "./observatoryFixtures";

// The design refactor (26 November 2026): the Observatory. It draws the systems the files describe, marks where each
// uses cryptography, and puts every check where it belongs, in the check's own words. It only reads: these tests hold
// it to the words of its read and to sending nothing but reads.

const MAP = "GET /api/assessments/101/observatory";
const boxes = observatoryChecked.services.flatMap((s) => s.boxes);
const server = boxes.find((b) => b.kind === "server")!;
const program = boxes.find((b) => b.kind === "program")!;
const boxRoute = (key: string) =>
  `GET /api/plans/${observatoryChecked.plan_id}/observatory/${key.split("/").map(encodeURIComponent).join("/")}`;
const posts = (fetchMock: ReturnType<typeof mockApi>) => calls(fetchMock).filter((c) => !c.startsWith("GET"));

beforeEach(() => {
  window.localStorage.clear();
});

async function open(
  view = observatoryChecked,
  routes: Parameters<typeof mockApi>[0] = {},
  openItem: string | null = null,
) {
  const fetchMock = mockApi({ [MAP]: { body: view }, ...routes });
  render(
    <LinkProvider assessmentId={101} planId={view.plan_id}>
      <ObservatoryPage assessmentId={101} openItem={openItem} />
    </LinkProvider>,
  );
  await screen.findByTestId("observatory-page");
  return fetchMock;
}

const box = (key: string) => screen.getAllByTestId("map-box").find((b) => b.getAttribute("data-node") === key)!;

describe("the Observatory, the map", () => {
  it("draws the service with its parts, where each uses cryptography, and what it is built from, and sends one read", async () => {
    const fetchMock = await open();
    expect(screen.getByRole("heading", { level: 1, name: observatoryChecked.title })).not.toBeNull();
    expect(screen.getByTestId("observatory-subline").textContent).toBe(observatoryChecked.subline);
    const service = observatoryChecked.services[0]!;
    const shown = within(screen.getByTestId("map-service"));
    expect(shown.getByRole("heading", { level: 3, name: service.title! })).not.toBeNull();
    expect(shown.getByTestId("map-service-sub").textContent).toBe(service.sub);
    // One box for each part the file names, each with its places in the file's order.
    expect(screen.getAllByTestId("map-box").map((b) => b.getAttribute("data-node"))).toEqual(boxes.map((b) => b.key));
    expect(
      within(box(server.key))
        .getAllByTestId("map-spot")
        .map((s) => s.getAttribute("data-spot")),
    ).toEqual(server.spots.map((s) => s.key));
    // What is outside, and what they use.
    expect(screen.getAllByTestId("map-outside").map((o) => o.getAttribute("data-node"))).toEqual([
      "clients",
      "this_computer",
    ]);
    expect(screen.getByTestId("map-algorithm-used").textContent).toBe(observatoryChecked.algorithms[0]!.used);
    expect(text(screen.getByTestId("observatory-built-from"))).toContain("Built from acme-pay-cbom.json");
    expect(calls(fetchMock)).toEqual([MAP]);
  });

  it("puts every check where it belongs, by name, in the check's own word, as a link to where the result lives", async () => {
    await open();
    for (const b of boxes)
      for (const spot of b.spots) {
        const shown = within(box(b.key))
          .getAllByTestId("map-spot")
          .find((s) => s.getAttribute("data-spot") === spot.key)!;
        expect(within(shown).getByTestId("map-spot-file").textContent, spot.key).toBe(`· ${spot.file_says}`);
        expect(
          within(shown)
            .getAllByTestId("map-check")
            .map((c) => [c.getAttribute("data-check"), within(c).getByTestId("map-check-word").textContent]),
          spot.key,
        ).toEqual(spot.checks.map((c) => [c.id, c.word]));
      }
    // A result's look is its own page's (False and Failed are failures there); a check that has not run has none.
    const tls = within(box(server.key)).getAllByTestId("map-check");
    const claim = tls.find((c) => c.getAttribute("data-check") === "claim-1")!;
    expect(within(claim).getByTestId("map-check-word").getAttribute("data-tone")).toBe("fail");
    expect(within(claim).getByTestId("map-check-link").getAttribute("href")).toBe(
      "#/a/101/inventory/verify?item=claim-1",
    );
    const status = tls.find((c) => c.getAttribute("data-kind") === "status")!;
    expect(within(status).getByTestId("map-check-word").getAttribute("data-tone")).toBeNull();
    expect(within(status).getByTestId("map-check-word").textContent).toBe("Not measured yet");
  });

  it("says what a box's results rest on once, on the box: observed on the server, proven on a copy", async () => {
    await open();
    expect(within(box(server.key)).getByTestId("map-box-tag").textContent).toBe("Observed live");
    expect(within(box(program.key)).getByTestId("map-box-tag").textContent).toBe("Proven in the lab");
    // (a check of a tagged box does not repeat the tag)
    expect(within(box(server.key)).queryAllByTestId("source-tag")).toHaveLength(0);
    expect(box(server.key).getAttribute("data-observed")).toBe("true");
  });

  it("shows the four counts by tag, in their fixed order, as the Overview counts them", async () => {
    await open();
    expect(
      screen
        .getAllByTestId("observatory-count")
        .map((c) => [c.getAttribute("data-source"), c.getAttribute("data-count")]),
    ).toEqual(observatoryChecked.counts.map((c) => [c.key, String(c.count)]));
    expect(screen.getByTestId("observatory-counts-note").textContent).toBe(observatoryChecked.counts_note);
  });

  it("has no score, no overall verdict on a box, and nothing that starts a check", async () => {
    const fetchMock = await open();
    const page = screen.getByTestId("observatory-page");
    expect(text(page)).not.toMatch(/\bscore\b|\bsecure\b|\bsafe\b|\brisk\b|severity/i);
    // The only buttons are the two views and the boxes' names (each opens its panel).
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Map",
      "List",
      ...boxes.map((b) => b.title),
    ]);
    expect(posts(fetchMock)).toEqual([]);
  });

  it("lists what the files don't say, each with where it can be filled in where the app has a place for it", async () => {
    await open();
    const gaps = screen.getAllByTestId("observatory-gap");
    expect(gaps.map((g) => g.getAttribute("data-gap"))).toEqual(observatoryChecked.gaps.items.map((g) => g.key));
    observatoryChecked.gaps.items.forEach((gap, i) => {
      expect(text(gaps[i]!), gap.key).toContain(gap.text);
      expect(within(gaps[i]!).queryByTestId("observatory-gap-link") !== null, gap.key).toBe(gap.link !== null);
    });
    // The legend says what each kind of line means, in the read's words.
    expect(
      within(screen.getByTestId("map-legend"))
        .getAllByRole("listitem")
        .map((li) => text(li)),
    ).toEqual([...observatoryChecked.legend.map((l) => l.text), observatoryChecked.legend_note]);
  });
});

describe("the Observatory, before anything was checked", () => {
  it("says so, draws every box as not observed, and words every check as not checked yet", async () => {
    await open(observatoryFileOnly);
    expect(screen.getByTestId("observatory-page").getAttribute("data-state")).toBe("file_only");
    const banner = screen.getByTestId("observatory-banner");
    expect(text(banner)).toBe(
      `${observatoryFileOnly.banner!.strong} ${observatoryFileOnly.banner!.text} ${observatoryFileOnly.banner!.link_label}`,
    );
    expect(within(banner).getByTestId("observatory-banner-link").getAttribute("href")).toBe("#/a/101/inventory/verify");
    for (const b of screen.getAllByTestId("map-box")) {
      expect(b.getAttribute("data-observed")).toBe("false");
      expect(within(b).getByTestId("map-box-tag").textContent).toBe("From your file");
      for (const word of within(b).getAllByTestId("map-check-word")) {
        expect(word.getAttribute("data-tone")).toBeNull();
        expect(word.textContent).toMatch(/^Not (checked|measured) yet$/);
      }
    }
  });

  it("shows the way to Import when no file is in yet, and draws no map", async () => {
    await open({
      ...observatoryFileOnly,
      state: "empty",
      plan_id: null,
      banner: null,
      empty: {
        text: "Bring in a scanner file to see your systems here.",
        link: { page: "inventory/import", item: null },
        link_label: "Open Import",
      },
      services: [],
      algorithms: [],
      lines: [],
    });
    expect(text(screen.getByTestId("observatory-empty"))).toBe(
      "Bring in a scanner file to see your systems here. Open Import",
    );
    expect(screen.getByTestId("observatory-empty-link").getAttribute("href")).toBe("#/a/101/inventory/import");
    expect(screen.queryByTestId("observatory-map")).toBeNull();
    expect(screen.queryByRole("group", { name: "Observatory view" })).toBeNull();
  });
});

describe("the Observatory, a box opened", () => {
  it("opens the box's panel with its summary, its checks with their sentences, its fixes, and the file's lines folded", async () => {
    const fetchMock = await open(observatoryChecked, { [boxRoute(server.key)]: { body: serverPanel } });
    fireEvent.click(within(box(server.key)).getByTestId("map-box-open"));
    const panel = within(await screen.findByTestId("box-panel"));
    expect(screen.getByRole("heading", { level: 2, name: serverPanel.title })).not.toBeNull();
    expect(panel.getByTestId("box-part-of").textContent).toBe(`Part of ${serverPanel.part_of}`);
    expect(panel.getByTestId("box-summary").textContent).toBe(serverPanel.summary);
    // Each place with its checks: the word of the check's own page and its plain sentence.
    const spots = panel.getAllByTestId("box-spot");
    expect(spots.map((s) => s.getAttribute("data-spot"))).toEqual(serverPanel.spots.map((s) => s.key));
    const first = serverPanel.spots[0]!.checks[0]!;
    const check = within(within(spots[0]!).getAllByTestId("box-check")[0]!);
    expect(check.getByTestId("box-check-word").textContent).toBe(first.word);
    expect(text(spots[0]!)).toContain(first.plain!);
    expect(check.getAllByTestId("box-check-link").map((a) => a.textContent)).toEqual(first.links.map((l) => l.label));
    // Its fixes, as links; and the lines of the file that name it, as data, behind one fold: a Technical record.
    expect(panel.getAllByTestId("box-fix").map((a) => a.textContent)).toEqual(serverPanel.fixes.map((f) => f.label));
    const fold = panel.getByTestId("box-record") as HTMLDetailsElement;
    expect(fold.open).toBe(false);
    expect(within(fold).getByTestId("proof-fold-name").textContent).toBe("Technical record");
    expect(text(fold)).toContain(serverPanel.file_lines[0]!.lines[0]!.where);
    expect(text(fold)).toContain("Read from the file as data. Nothing in it is run.");
    expect(calls(fetchMock)).toEqual([MAP, boxRoute(server.key)]);
    expect(posts(fetchMock)).toEqual([]);
    // The open box is marked on the map; a second click closes its panel.
    expect(within(box(server.key)).getByTestId("map-box-open").getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(within(box(server.key)).getByTestId("map-box-open"));
    expect(screen.queryByTestId("box-panel")).toBeNull();
  });

  it("says the Migration plan's next step once for the box, with the way to it, and nothing where no status was measured", async () => {
    const next = {
      text: "Next: hybrid key exchange · Phase 2",
      label: "The system on Migration plan",
      link: { page: "migration/systems", item: server.key },
    };
    await open(observatoryChecked, { [boxRoute(server.key)]: { body: { ...serverPanel, next } } });
    fireEvent.click(within(box(server.key)).getByTestId("map-box-open"));
    const panel = within(await screen.findByTestId("box-panel"));
    expect(text(panel.getByTestId("box-next"))).toBe(`${next.text} ${next.label}`);
    expect(panel.getByTestId("box-next-link").getAttribute("href")).toBe(
      `#/a/101/migration/systems?item=${encodeURIComponent(server.key)}`,
    );
    cleanup();
    await open(observatoryChecked, { [boxRoute(server.key)]: { body: serverPanel } });
    fireEvent.click(within(box(server.key)).getByTestId("map-box-open"));
    expect(within(await screen.findByTestId("box-panel")).queryByTestId("box-next")).toBeNull();
  });

  it("opens the box the address names, and finds the box of an item of another page (Show on the map)", async () => {
    const place = `GET /api/plans/${observatoryChecked.plan_id}/observatory/place?key=${encodeURIComponent(testPlace.key)}`;
    const fetchMock = await open(
      observatoryChecked,
      {
        [boxRoute(server.key)]: { body: serverPanel },
        [place]: { body: { ...testPlace, place: { ...testPlace.place!, box: server.key } } },
      },
      testPlace.key,
    );
    expect((await screen.findByTestId("box-panel")).getAttribute("data-box")).toBe(serverPanel.key);
    expect(calls(fetchMock)).toEqual([MAP, place, boxRoute(server.key)]);
  });
});

describe("the Observatory, as a list", () => {
  it("lists what the map shows and no less: each service's own line, the ties, and the libraries of the dependency list", async () => {
    // (26 November 2026, the review: Map and List show the same thing.) The sample walk had no dependency list, so a
    // group of libraries, a tie and a line to them are written here in the read's own form.
    const published = {
      key: "published" as const,
      label: "Published",
      meaning: "Said by the library's maker.",
      note: null,
    };
    const withList = {
      ...observatoryChecked,
      libraries_note: null,
      services: observatoryChecked.services.map((service) => ({
        ...service,
        sub: "Named in both files, with the same name and version",
        boxes: service.boxes.map((b) =>
          b.key === program.key
            ? {
                ...b,
                ties: [
                  {
                    label: "acme-sign 1.4.2",
                    source: "name_version",
                    words: "In both files: the same name and version.",
                  },
                ],
              }
            : b,
        ),
      })),
      libraries: [
        {
          key: "libraries:acme-ledger",
          kind_label: "Libraries",
          title: "acme-ledger 5.1.0's libraries · 8",
          sub: "From your dependency list",
          owner: null,
          count: 8,
          tag: published,
          rows: [
            {
              id: "row-1",
              label: "openssl 3.5.9",
              via_words: "used directly",
              answers_short: "Yes to all three",
              tag: published,
              link: { page: "migration/dependencies", item: "row-1" },
            },
          ],
          more: {
            count: 7,
            label: "7 more",
            link: { page: "migration/dependencies", item: null },
            link_label: "on Dependencies",
          },
        },
      ],
      lines: [
        ...observatoryChecked.lines,
        { start: program.key, end: "libraries:acme-ledger", kind: "uses" as const, label: "uses 8 libraries" },
      ],
    };
    await open(withList);
    fireEvent.click(screen.getByRole("button", { name: "List" }));
    const list = within(screen.getByTestId("observatory-list"));
    expect(text(list.getAllByTestId("list-service")[0]!)).toContain(
      "Named in both files, with the same name and version",
    );
    expect(list.getByTestId("list-tie").textContent).toBe("In both files: the same name and version.");
    const libraries = within(list.getByRole("table", { name: "Libraries, as a list" }));
    expect(text(libraries.getByTestId("list-library"))).toBe(
      "acme-ledger 5.1.0's libraries · 8From your dependency list7 more on Dependenciesopenssl 3.5.9used directlyYes to all three Published",
    );
    // The line to the libraries is said in words too.
    expect(text(list.getByTestId("list-lines"))).toContain(
      "Your files say one uses the other: acme-sign 1.4.2 to acme-ledger",
    );
    // No sentence of the list's own stands where the map's read says nothing.
    expect(text(screen.getByTestId("observatory-list"))).not.toContain("Nothing in your files");
  });

  it("shows the same boxes, places and checks as a table, and the map's lines in words", async () => {
    await open();
    fireEvent.click(screen.getByRole("button", { name: "List" }));
    await waitFor(() => expect(screen.queryByTestId("observatory-map")).toBeNull());
    const list = within(screen.getByTestId("observatory-list"));
    expect(list.getByRole("table", { name: "Your systems, as a list" })).not.toBeNull();
    // One row for each place of each box, and every check of the map is in the list.
    expect(list.getAllByTestId("list-row")).toHaveLength(boxes.reduce((n, b) => n + Math.max(b.spots.length, 1), 0));
    expect(list.getAllByTestId("map-check").map((c) => c.getAttribute("data-check"))).toEqual(
      boxes.flatMap((b) => b.spots.flatMap((s) => s.checks.map((c) => c.id))),
    );
    const words = text(list.getByTestId("list-lines"));
    expect(words).toContain(observatoryChecked.algorithms[0]!.used);
    expect(words).toContain("A connection we made from this computer (handshakes only): This computer to");
    expect(words).toContain("Your files don't say: Clients to");
  });
});
