// Where it came from (22 November 2026, Kevin's decision A): a small coloured tag with its words always written out.
// Colour only helps: never green or amber (passed and failed) and never violet (Demo data). The words, the meaning on
// hover and the item's own sentence are the backend's.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { RichText, Source } from "../api";
import { DemoDataLabel, ResultBadge, RichTextView, WhereFromLine, WhereFromTag } from "../components/ui";
import { LABELS, MEANINGS, fromFile, labCopy, live, published } from "./sourceFixtures";

afterEach(cleanup);

const ALL: Source[] = [live("localhost:8443"), labCopy("acme-sign 1.4.2"), fromFile(), published()];
const CLASHING = /\b(?:border|bg|text)-(?:green|emerald|lime|amber|yellow|orange|violet|purple|fuchsia)-/;

describe("The tag of where it came from", () => {
  it("writes out its words for each of the four, keeps its key for its look, and says what it means on hover", () => {
    render(
      <>
        {ALL.map((t) => (
          <WhereFromTag key={t.key} tag={t} />
        ))}
      </>,
    );
    const tags = screen.getAllByTestId("source-tag");
    expect(tags.map((t) => t.textContent)).toEqual(["Observed live", "Proven in the lab", "From your file", "Published"]);
    expect(tags.map((t) => t.getAttribute("data-source"))).toEqual(["live", "lab", "file", "published"]);
    expect(tags.map((t) => t.getAttribute("title"))).toEqual([MEANINGS.live, MEANINGS.lab, MEANINGS.file, MEANINGS.published]);
    expect(Object.values(LABELS)).toEqual(tags.map((t) => t.textContent));
  });

  it("never uses a colour of passed, failed or Demo data, and the four look different", () => {
    render(
      <>
        {ALL.map((t) => (
          <WhereFromTag key={t.key} tag={t} />
        ))}
        <ResultBadge label="Passed" tone="pass" />
        <DemoDataLabel />
      </>,
    );
    const looks = screen.getAllByTestId("source-tag").map((t) => t.className);
    for (const look of looks) expect(look).not.toMatch(CLASHING);
    expect(new Set(looks).size).toBe(4);
    // From your file is the dashed one: it is told apart without its colour too
    expect(looks[2]).toContain("border-dashed");
  });

  it("draws nothing where there is no tag (a test that has not run, or couldn't run)", () => {
    const { container } = render(
      <>
        <WhereFromTag tag={null} />
        <WhereFromLine tag={undefined} />
      </>,
    );
    expect(container.innerHTML).toBe("");
  });

  it("in a panel, writes the item's own sentence beside the tag, or the tag's meaning where the item says nothing more", () => {
    render(
      <>
        <WhereFromLine tag={live("localhost:8443")} />
        <WhereFromLine tag={{ ...fromFile(), note: null }} />
      </>,
    );
    const notes = screen.getAllByTestId("source-note").map((n) => n.textContent);
    expect(notes).toEqual(["Read from localhost:8443, an address in your file that you confirmed, with handshakes only.", MEANINGS.file]);
    expect(screen.getAllByTestId("source-line").map((l) => l.getAttribute("data-source"))).toEqual(["live", "file"]);
  });

  it("a small tag the backend marked with its source keeps its words and only takes that source's look", () => {
    const parts: RichText = [
      { t: "text", v: "1,184 bytes " },
      { t: "tag", v: "measured on our test server", s: "lab" },
      { t: "tag", v: "published: FIPS 203", s: "published" },
      { t: "tag", v: "not measured" },
    ];
    const { container } = render(<RichTextView parts={parts} />);
    const small = Array.from(container.querySelectorAll("span.rounded"));
    expect(small.map((t) => t.textContent)).toEqual(["measured on our test server", "published: FIPS 203", "not measured"]);
    expect(small.map((t) => t.getAttribute("data-source"))).toEqual(["lab", "published", null]);
    for (const t of small) expect(t.className).not.toMatch(CLASHING);
  });
});
