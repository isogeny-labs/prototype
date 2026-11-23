import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MigrationView } from "../api";
import { MigrationScreen } from "../components/MigrationScreen";
import { CLOSED_SENTENCE, ReadOnlyProvider } from "../readOnly";
import { calls, evidenceExport, mockApi, text } from "./fixtures";
import { HYBRID_FIX, SIGN_FIX, measuringView, migrationView, withSystem } from "./migrationFixtures";

const GET = "GET /api/import/7/migration";

async function open(view: MigrationView = migrationView, extra: Parameters<typeof mockApi>[0] = {}) {
  const fetchMock = mockApi({ [GET]: { body: view }, ...extra });
  const props = { onViewFix: vi.fn(), onPlanChanged: vi.fn() };
  render(<MigrationScreen importId={7} {...props} />);
  await screen.findByRole("heading", { level: 1, name: view.title });
  return { fetchMock, ...props };
}

const button = (name: string | RegExp) => screen.getByRole("button", { name }) as HTMLButtonElement;
const cards = () => screen.getAllByTestId("system-card");
const card = (name: string) => cards().find((c) => c.textContent?.includes(name))!;
const option = (key: string) =>
  screen.getAllByTestId("option-card").find((c) => c.getAttribute("data-option") === key)!;
const lastBody = (fetchMock: ReturnType<typeof mockApi>, key: string) => {
  const found = fetchMock.mock.calls.filter(([url, init]) => `${init?.method ?? "GET"} ${String(url)}` === key).at(-1);
  return JSON.parse(String(found?.[1]?.body));
};

describe("Migration, header and Systems view", () => {
  it("draws the header, the disclaimer, the two view switches and every system card as sent", async () => {
    const { onPlanChanged } = await open();
    expect(screen.getByText("Demo data")).not.toBeNull();
    expect(text(screen.getByTestId("migration-subline"))).toBe(
      "Where each system in migration-demo.csv stands on the move to post-quantum cryptography, what each option costs, and a plan.",
    );
    expect(screen.getByTestId("disclaimer").textContent).toBe(migrationView.disclaimer);
    expect(button("Measure again").disabled).toBe(false);
    expect(button("Systems · 7").getAttribute("aria-pressed")).toBe("true");
    expect(button("Roadmap").getAttribute("aria-pressed")).toBe("false");
    // The first answer tells the app, which loads the plan again (the GET may have made it).
    // The screen tells the app from an effect just after it draws: wait for the call itself.
    await waitFor(() => expect(onPlanChanged).toHaveBeenCalledTimes(1));

    expect(screen.getByRole("heading", { level: 2, name: "Systems in the file (7)" })).not.toBeNull();
    expect(cards().map((c) => c.getAttribute("data-system"))).toEqual(migrationView.systems.map((s) => s.key));
    expect(cards().map((c) => within(c).getByTestId("migration-status").getAttribute("data-code"))).toEqual([
      "hybrid",
      "classical",
      "classical",
      "classical",
      "pq_only",
      "classical",
      "couldnt_check",
    ]);
    // Each pill has a symbol as well as its words, so it doesn't rely on colour.
    expect(text(within(card("localhost:8451")).getByTestId("migration-status"))).toBe("◑Hybrid");
    expect(text(within(card("acme-sign 9.9")).getByTestId("migration-status"))).toBe("?Couldn't check");
    // Beside the open panel, a row is the system with its plan line, then its status and where it came from.
    expect(text(card("localhost:8452"))).toBe("localhost:8452Plan: Hybrid · Phase 1○Classical Observed live");
    // As before the panel, Systems opens on the first system; the panel shows it.
    expect(cards().map((c) => c.getAttribute("aria-current"))).toEqual(["true", null, null, null, null, null, null]);
    expect(screen.getByRole("heading", { level: 2, name: "localhost:8451" })).not.toBeNull();
    expect(within(screen.getByTestId("detail-panel")).getByTestId("migration-system").getAttribute("data-system")).toBe(
      "server:localhost:8451",
    );
    expect(document.body.textContent).not.toMatch(/score/i);
    // With the panel closed, the full row comes back.
    fireEvent.click(within(screen.getByTestId("detail-panel")).getByRole("button", { name: "Close details" }));
    expect(text(card("localhost:8452"))).toBe("Serverlocalhost:8452○Classical Observed livePlan: Hybrid · Phase 1");
  });

  it("selecting a system draws its Today box, settings, cost table, recommendation and four options", async () => {
    await open();
    fireEvent.click(card("localhost:8452"));
    expect(card("localhost:8452").getAttribute("aria-current")).toBe("true");
    const detail = screen.getByTestId("migration-system");
    expect(detail.getAttribute("data-system")).toBe("server:localhost:8452");

    const today = within(screen.getByTestId("migration-today"));
    expect(today.getByRole("heading", { level: 3, name: "Today" })).not.toBeNull();
    expect(screen.getByTestId("today-sentence").textContent).toBe(
      "It refused every post-quantum key exchange we offered and completed a classical handshake, so it is Classical.",
    );
    expect(screen.getByTestId("file-note").textContent).toBe(
      "The file says: this server is Hybrid. Verify marked that claim False.",
    );
    expect(today.getAllByRole("term").map((d) => d.textContent)).toEqual([
      "Hybrid key exchange",
      "Classical key exchange",
      "Certificate",
    ]);
    expect(text(today.getAllByRole("definition")[0])).toBe("Refused: X25519MLKEM768 and two others measured");
    expect(screen.getByTestId("today-control").textContent).toMatch(/^Control: /);

    // The evidence is folded until opened, and then drawn with Evidence Lab's own detail, without its buttons.
    const details = today.getByRole("button", { name: "Details and evidence" });
    expect(details.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByTestId("result-detail")).toBeNull();
    fireEvent.click(details);
    expect(screen.getByTestId("result-detail").getAttribute("data-run-id")).toBe("41");
    expect(screen.queryByRole("button", { name: "Mark reviewed" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Dig deeper" })).toBeNull();
    fireEvent.click(details);
    expect(screen.queryByTestId("result-detail")).toBeNull();

    const settings = screen.getAllByTestId("migration-setting");
    expect(settings.map((s) => (within(s).getByRole("combobox") as HTMLSelectElement).value)).toEqual([
      "long",
      "internet",
      "yes",
    ]);
    expect((screen.getByLabelText("Data lifespan") as HTMLSelectElement).value).toBe("long");
    expect(screen.getAllByTestId("setting-source").map((s) => s.textContent)).toEqual([
      "from the file",
      "from the file",
      "assumed",
    ]);
    expect(screen.getByText("Who can reach it or record its traffic?")).not.toBeNull();

    const cost = within(screen.getByTestId("migration-cost"));
    expect(cost.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "",
      "Today (classical)",
      "Hybrid",
      "Full post-quantum",
    ]);
    expect(cost.getAllByRole("rowheader").map((h) => h.textContent)).toEqual([
      "Key share, client to server",
      "Handshake time, median of 10",
    ]);
    expect(cost.getByText("published: FIPS 203 + X25519")).not.toBeNull();

    const recBox = within(screen.getByTestId("migration-recommendation"));
    expect(recBox.getByRole("heading", { level: 3, name: "Recommended: Hybrid" })).not.toBeNull();
    expect(recBox.getByText("from fixed rules, no AI model")).not.toBeNull();
    expect(screen.getAllByTestId("recommendation-reason")).toHaveLength(2);
    // "See the evidence" opens the folded evidence above.
    fireEvent.click(recBox.getByRole("button", { name: "See the evidence" }));
    expect(details.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("result-detail")).not.toBeNull();

    expect(screen.getByRole("heading", { level: 3, name: "The four options" })).not.toBeNull();
    const options = screen.getAllByTestId("option-card");
    expect(options.map((o) => o.getAttribute("data-option"))).toEqual(["keep", "hybrid", "full_pq", "wrap"]);
    expect(options.map((o) => o.getAttribute("data-highlighted"))).toEqual(["false", "true", "false", "false"]);
    expect(within(option("hybrid")).getByText("Recommended")).not.toBeNull();
    expect(
      within(option("hybrid"))
        .getAllByTestId("option-section")
        .map((s) => within(s).getByRole("heading").textContent),
    ).toEqual(["Cost", "Blockers", "To manage"]);
    expect(within(option("keep")).getByRole("button", { name: "Choose this option" })).not.toBeNull();
    expect(screen.getByTestId("choices-note").textContent).toBe(migrationView.systems[1]!.choices_note);
    expect(screen.queryByTestId("migration-choice")).toBeNull();
  });

  it("keeps the selected system and the open view when the data is refreshed", async () => {
    let n = 0;
    mockApi({
      [GET]: () => {
        n += 1;
        return { body: n === 1 ? measuringView : migrationView };
      },
    });
    render(<MigrationScreen importId={7} onViewFix={vi.fn()} onPlanChanged={vi.fn()} />);
    await screen.findByRole("heading", { level: 1, name: "Migration plan" });
    fireEvent.click(card("localhost:8453"));
    await waitFor(() => expect(screen.queryByTestId("job-status")).toBeNull(), { timeout: 3000 });
    expect(card("localhost:8453").getAttribute("aria-current")).toBe("true");
    expect(screen.getByRole("heading", { level: 2, name: "localhost:8453" })).not.toBeNull();
  });

  it("draws a signing program's Wrap option as not offered, with no Choose button", async () => {
    await open();
    fireEvent.click(card("acme-sign 1.4.2"));
    const wrap = within(option("wrap"));
    expect(wrap.getByTestId("not-offered").textContent).toBe("Doesn't apply to a signing program.");
    expect(wrap.queryByRole("button")).toBeNull();
    expect(text(within(card("acme-sign 1.4.2")).getByTestId("migration-status"))).toBe("○Classical: ECDSA P-256");
  });

  it("draws nothing the view doesn't send: no options, cost or evidence for a system it couldn't check", async () => {
    await open();
    fireEvent.click(card("acme-sign 9.9"));
    expect(screen.getByTestId("recommendation-none").textContent).toBe(
      "There is no recommendation until its status can be measured.",
    );
    expect(screen.queryByTestId("option-card")).toBeNull();
    expect(screen.queryByTestId("migration-options")).toBeNull();
    expect(screen.queryByText("The four options")).toBeNull();
    expect(screen.queryByTestId("choices-note")).toBeNull();
    expect(screen.queryByTestId("migration-cost")).toBeNull();
    expect(screen.queryByTestId("recommendation-reason")).toBeNull();
    expect(screen.queryByRole("button", { name: "Details and evidence" })).toBeNull();
    expect(screen.queryByTestId("today-facts")).toBeNull();
    expect(screen.queryByTestId("today-control")).toBeNull();
    expect(screen.queryByTestId("file-note")).toBeNull();
    expect(screen.queryByRole("button", { name: "View in Fixes" })).toBeNull();
  });

  it("shows the empty text when the file names no system", async () => {
    await open({ ...migrationView, systems: [], empty_text: "This file names no server and no signing program." });
    expect(screen.getByTestId("migration-empty").textContent).toBe("This file names no server and no signing program.");
    expect(screen.queryByTestId("system-card")).toBeNull();
  });
});

describe("Migration, settings", () => {
  it("saves a changed setting at once and redraws from the answer", async () => {
    const field = migrationView.systems[1]!.settings.fields[0]!;
    const answer = withSystem(migrationView, "server:localhost:8452", {
      settings: {
        ...migrationView.systems[1]!.settings,
        fields: migrationView.systems[1]!.settings.fields.map((f) =>
          f.field === "lifespan" ? { ...f, value: "short", source: "set by you" } : f,
        ),
      },
      plan_line: "Plan: Hybrid · Phase 2",
    });
    const { fetchMock, onPlanChanged } = await open(migrationView, {
      "POST /api/plans/1/migration/settings": { body: answer },
    });
    fireEvent.click(card("localhost:8452"));
    fireEvent.change(screen.getByLabelText(field.label), { target: { value: "short" } });
    await waitFor(() => expect(screen.getAllByTestId("setting-source")[0]!.textContent).toBe("set by you"));
    expect(lastBody(fetchMock, "POST /api/plans/1/migration/settings")).toEqual({
      system: "server:localhost:8452",
      field: "lifespan",
      value: "short",
    });
    expect((screen.getByLabelText("Data lifespan") as HTMLSelectElement).value).toBe("short");
    expect(text(card("localhost:8452"))).toContain("Plan: Hybrid · Phase 2");
    // The screen tells the app from an effect just after it draws: wait for the call itself.
    await waitFor(() => expect(onPlanChanged).toHaveBeenCalledTimes(2));
  });

  it("locks the settings while a measurement runs", async () => {
    await open(measuringView, { [GET]: { body: measuringView } });
    fireEvent.click(cards()[0]!);
    const settings = within(screen.getByTestId("detail-panel")).getAllByRole("combobox");
    expect(settings.length).toBeGreaterThan(0);
    for (const select of settings) expect((select as HTMLSelectElement).disabled).toBe(true);
  });
});

describe("Migration, choosing an option", () => {
  it("opens one choose box at a time, needs a reason when asked, and Cancel closes it", async () => {
    await open();
    fireEvent.click(card("localhost:8452"));
    fireEvent.click(within(option("keep")).getByRole("button", { name: "Choose this option" }));
    let box = within(screen.getByTestId("choose-box"));
    expect(box.getByText("Choose “Keep classical for now”")).not.toBeNull();
    const date = box.getByLabelText("Review date") as HTMLInputElement;
    expect([date.type, date.value, date.min, date.max]).toEqual(["date", "2027-11-14", "2026-11-15", "2030-12-31"]);
    expect((box.getByRole("button", { name: "Save choice" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(box.getByLabelText(/^Your reason/), { target: { value: "Replaced next year." } });
    expect((box.getByRole("button", { name: "Save choice" }) as HTMLButtonElement).disabled).toBe(false);

    // Opening another option's box closes the first.
    fireEvent.click(within(option("full_pq")).getByRole("button", { name: "Choose this option" }));
    expect(screen.getAllByTestId("choose-box")).toHaveLength(1);
    box = within(within(option("full_pq")).getByTestId("choose-box"));
    expect(box.queryByLabelText("Review date")).toBeNull();
    fireEvent.click(box.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByTestId("choose-box")).toBeNull();
    expect(within(option("full_pq")).getByRole("button", { name: "Choose this option" })).not.toBeNull();
  });

  it("lets the recommended option be saved without a reason", async () => {
    await open();
    fireEvent.click(card("localhost:8452"));
    fireEvent.click(within(option("hybrid")).getByRole("button", { name: "Choose this option" }));
    expect((within(option("hybrid")).getByRole("button", { name: "Save choice" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("sends the reason and the review date, closes the box and draws the saved choice and its history", async () => {
    const answer = withSystem(migrationView, "server:localhost:8452", {
      choice: {
        line: "Your choice: Keep classical for now, review by 14 May 2027. Your reason: “Replaced next year.”",
        history: ["Earlier: Hybrid, 14 Nov 2026, 5:10 PM"],
      },
    });
    const { fetchMock, onPlanChanged } = await open(migrationView, {
      "POST /api/plans/1/migration/choice": { body: answer },
    });
    fireEvent.click(card("localhost:8452"));
    fireEvent.click(within(option("keep")).getByRole("button", { name: "Choose this option" }));
    fireEvent.change(screen.getByLabelText("Review date"), { target: { value: "2027-05-14" } });
    fireEvent.change(screen.getByLabelText(/^Your reason/), { target: { value: "Replaced next year." } });
    fireEvent.click(button("Save choice"));
    await waitFor(() => expect(screen.queryByTestId("choose-box")).toBeNull());
    expect(lastBody(fetchMock, "POST /api/plans/1/migration/choice")).toEqual({
      system: "server:localhost:8452",
      option: "keep",
      reason: "Replaced next year.",
      review_date: "2027-05-14",
    });
    expect(
      within(screen.getByTestId("migration-choice")).getByText(/^Your choice: Keep classical for now/),
    ).not.toBeNull();
    expect(screen.getAllByTestId("choice-history").map((h) => h.textContent)).toEqual([
      "Earlier: Hybrid, 14 Nov 2026, 5:10 PM",
    ]);
    // The screen tells the app from an effect just after it draws: wait for the call itself.
    await waitFor(() => expect(onPlanChanged).toHaveBeenCalledTimes(2));
  });

  it("sends no review date for an option without one", async () => {
    const { fetchMock } = await open(migrationView, { "POST /api/plans/1/migration/choice": { body: migrationView } });
    fireEvent.click(card("localhost:8452"));
    fireEvent.click(within(option("hybrid")).getByRole("button", { name: "Choose this option" }));
    fireEvent.click(button("Save choice"));
    await waitFor(() => expect(screen.queryByTestId("choose-box")).toBeNull());
    expect(lastBody(fetchMock, "POST /api/plans/1/migration/choice")).toEqual({
      system: "server:localhost:8452",
      option: "hybrid",
      reason: "",
      review_date: null,
    });
  });

  it("shows a refusal in the box and keeps it open", async () => {
    const { onPlanChanged } = await open(migrationView, {
      "POST /api/plans/1/migration/choice": {
        status: 400,
        body: { detail: "The review date can't be later than 31 December 2030.", field: "review_date" },
      },
    });
    fireEvent.click(card("localhost:8453"));
    fireEvent.click(within(option("hybrid")).getByRole("button", { name: "Choose this option" }));
    fireEvent.change(screen.getByLabelText(/^Your reason/), { target: { value: "Because." } });
    fireEvent.click(button("Save choice"));
    const box = within(screen.getByTestId("choose-box"));
    expect((await box.findByTestId("choose-error")).textContent).toBe(
      "The review date can't be later than 31 December 2030.",
    );
    expect((box.getByLabelText(/^Your reason/) as HTMLTextAreaElement).value).toBe("Because.");
    expect((box.getByRole("button", { name: "Save choice" }) as HTMLButtonElement).disabled).toBe(false);
    // The screen tells the app from an effect just after it draws: wait for the call itself.
    await waitFor(() => expect(onPlanChanged).toHaveBeenCalledTimes(1));
  });
});

describe("Migration, View in Fixes", () => {
  it("passes the fix of a blocker line and of a roadmap note to the app", async () => {
    const { onViewFix } = await open();
    fireEvent.click(card("localhost:8452"));
    fireEvent.click(within(option("hybrid")).getByRole("button", { name: "View in Fixes" }));
    expect(onViewFix).toHaveBeenLastCalledWith(HYBRID_FIX);

    fireEvent.click(button("Roadmap"));
    const phase2 = screen.getAllByTestId("roadmap-band").find((b) => b.getAttribute("data-band") === "phase2")!;
    fireEvent.click(within(phase2).getByRole("button", { name: "View in Fixes" }));
    expect(onViewFix).toHaveBeenLastCalledWith(SIGN_FIX);
    expect(
      within(screen.getByTestId("migration-roadmap")).getAllByRole("button", { name: "View in Fixes" }),
    ).toHaveLength(2);
  });
});

describe("Migration, Roadmap view", () => {
  it("draws the intro, the download button and every band and row as sent", async () => {
    await open();
    fireEvent.click(button("Roadmap"));
    expect(button("Roadmap").getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByTestId("system-card")).toBeNull();
    expect(screen.getByTestId("roadmap-intro").textContent).toBe(migrationView.roadmap.intro);
    expect(button("Download evidence").disabled).toBe(false);

    const bands = screen.getAllByTestId("roadmap-band");
    expect(bands.map((b) => within(b).getByRole("heading", { level: 2 }).textContent)).toEqual([
      "Already there",
      "Phase 1",
      "Phase 2",
      "Later",
      "Wrapped",
      "Not placed yet",
    ]);
    expect(bands.map((b) => b.getAttribute("data-look"))).toEqual([
      "plain",
      "highlight",
      "plain",
      "plain",
      "plain",
      "dashed",
    ]);
    expect(bands.map((b) => within(b).getAllByTestId("roadmap-row").length)).toEqual([2, 1, 1, 1, 1, 1]);
    const phase1 = within(bands[1]!);
    expect(text(phase1.getByTestId("roadmap-row"))).toBe(
      "Serverlocalhost:8452Hybrid recommended, not yet chosen by youTo do: turn on hybrid key exchange. View in Fixes",
    );
    expect(text(within(bands[5]!).getByTestId("roadmap-row"))).toBe(
      "Signing programacme-sign 9.9No option yetCouldn't check: only our own demo components can run in this version.",
    );
  });

  it("has no buttons the spec does not list: Download, View in Fixes, and one button on each row that opens its panel", async () => {
    await open();
    fireEvent.click(button("Roadmap"));
    const roadmap = screen.getByTestId("migration-roadmap");
    const rowButtons = within(roadmap)
      .getAllByTestId("roadmap-row")
      .map((r) => within(r).getAllByRole("button")[0]!);
    const others = within(roadmap)
      .getAllByRole("button")
      .filter((b) => !rowButtons.includes(b))
      .map((b) => b.textContent);
    expect(new Set(others)).toEqual(new Set(["Download evidence", "View in Fixes"]));
    // A row button is the system's name, and it opens that system in the panel.
    expect(screen.queryByTestId("detail-panel")).toBeNull();
    fireEvent.click(within(roadmap).getByRole("button", { name: /acme-sign 1\.4\.2/ }));
    expect(within(screen.getByTestId("detail-panel")).getByTestId("migration-system").getAttribute("data-system")).toBe(
      "software:acme-sign-1.4.2",
    );
  });

  it("beside an open panel, a row is the system with its track, the plan, and only a note that points to a fix", async () => {
    await open();
    fireEvent.click(button("Roadmap"));
    const roadmap = screen.getByTestId("migration-roadmap");
    expect(roadmap.getAttribute("data-compact")).toBeNull();
    fireEvent.click(within(roadmap).getByRole("button", { name: /localhost:8452/ }));
    expect(roadmap.getAttribute("data-compact")).toBe("true");
    const bands = within(roadmap).getAllByTestId("roadmap-band");
    // The note with a fix stays (it is the step to take); a note without one waits for the full row. The plan's tag
    // sits under the option.
    expect(text(within(bands[1]!).getByTestId("roadmap-row"))).toBe(
      "localhost:8452Hybridrecommended, not yet chosen by youTo do: turn on hybrid key exchange. View in Fixes",
    );
    expect(text(within(bands[5]!).getByTestId("roadmap-row"))).toBe("acme-sign 9.9No option yet");
    fireEvent.click(within(screen.getByTestId("detail-panel")).getByRole("button", { name: "Close details" }));
    expect(roadmap.getAttribute("data-compact")).toBeNull();
    expect(text(within(bands[5]!).getByTestId("roadmap-row"))).toBe(
      "Signing programacme-sign 9.9No option yetCouldn't check: only our own demo components can run in this version.",
    );
  });

  it("downloads the same evidence as Evidence Lab and shows its fingerprint", async () => {
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      saved.push(String(this.getAttribute("href")));
    });
    const { fetchMock } = await open(migrationView, { "POST /api/plans/1/evidence": { body: evidenceExport } });
    fireEvent.click(button("Roadmap"));
    fireEvent.click(button("Download evidence"));
    const status = await screen.findByTestId("download-status", undefined, { timeout: 3000 });
    expect(saved).toEqual(["/api/evidence/3/json", "/api/evidence/3/html"]);
    expect(within(status).getByTestId("evidence-fingerprint").textContent).toBe(evidenceExport.fingerprint);
    expect(calls(fetchMock)).toEqual([GET, "POST /api/plans/1/evidence"]);
  });

  it("disables the download and says why while it can't start", async () => {
    await open(measuringView, { [GET]: { body: measuringView } });
    fireEvent.click(button("Roadmap"));
    expect(button("Download evidence").disabled).toBe(true);
    expect(screen.getByTestId("download-blocked").textContent).toBe("A measurement is running.");
  });
});

describe("Migration, measuring", () => {
  it("starts a measurement with the measure button", async () => {
    const { fetchMock } = await open(migrationView, {
      "POST /api/plans/1/migration/measure": {
        body: { ...migrationView, measure: { ...migrationView.measure, label: "Measure again" } },
      },
    });
    fireEvent.click(button("Measure again"));
    await waitFor(() => expect(calls(fetchMock)).toContain("POST /api/plans/1/migration/measure"));
    expect(lastBody(fetchMock, "POST /api/plans/1/migration/measure")).toEqual({});
  });

  it("disables the measure button with its reason and shows the progress while measuring, and draws each system's status", async () => {
    await open(measuringView, { [GET]: { body: measuringView } });
    fireEvent.click(cards()[0]!);
    expect(button("Measure again").disabled).toBe(true);
    expect(screen.getByTestId("measure-blocked").textContent).toBe("A measurement is running.");
    expect(screen.getByTestId("measure-progress").textContent).toBe("Measuring: 2 of 7 systems finished.");
    // The running status is drawn in place of Today's sentence.
    expect(screen.getByTestId("job-status").getAttribute("data-status")).toBe("running");
    expect(screen.queryByTestId("today-sentence")).toBeNull();
  });

  it("shows the reason when measuring can't start", async () => {
    await open({
      ...migrationView,
      measure: {
        label: "Measure status",
        enabled: false,
        blocked_reason: "Tick each address on Import first.",
        progress_text: null,
      },
    });
    expect(button("Measure status").disabled).toBe(true);
    expect(screen.getByTestId("measure-blocked").textContent).toBe("Tick each address on Import first.");
    expect(screen.queryByTestId("measure-progress")).toBeNull();
  });

  it("asks again every second while busy, stops when it is done, and tells the app", async () => {
    let n = 0;
    const fetchMock = mockApi({
      [GET]: () => {
        n += 1;
        return { body: n < 3 ? measuringView : migrationView };
      },
    });
    const onPlanChanged = vi.fn();
    render(<MigrationScreen importId={7} onViewFix={vi.fn()} onPlanChanged={onPlanChanged} />);
    await screen.findByRole("heading", { level: 1, name: "Migration plan" });
    // The screen tells the app from an effect that runs just after it draws, so wait for the call itself: on a busy
    // machine that moment can come a little after the new screen is already there.
    await waitFor(() => expect(onPlanChanged).toHaveBeenCalledTimes(1));
    // Two asks a second apart, then the answer that is not busy: wait for that on screen, however slow the machine.
    await waitFor(() => expect(button("Measure again").disabled).toBe(false), { timeout: 15_000 });
    expect(calls(fetchMock)).toEqual([GET, GET, GET]);
    await waitFor(() => expect(onPlanChanged).toHaveBeenCalledTimes(2));
    // Nothing asks again once it is done (an absence can only be checked by waiting past the next tick).
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(calls(fetchMock)).toHaveLength(3);
    expect(onPlanChanged).toHaveBeenCalledTimes(2);
  });

  it("does not ask again when nothing runs", async () => {
    const { fetchMock } = await open();
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(calls(fetchMock)).toEqual([GET]);
  });
});

describe("Migration, the systems table and its detail panel", () => {
  it("opens a system in the panel on a row click, shows the whole detail there, and closes with the close button or Escape", async () => {
    await open();
    // The first system is open to begin with; a row click opens another one in the same panel.
    expect(within(screen.getByTestId("detail-panel")).getByTestId("migration-system").getAttribute("data-system")).toBe(
      "server:localhost:8451",
    );
    fireEvent.click(card("localhost:8452"));
    const panel = within(screen.getByTestId("detail-panel"));
    expect(panel.getByTestId("migration-today")).not.toBeNull();
    expect(panel.getByTestId("migration-settings")).not.toBeNull();
    expect(panel.getByTestId("migration-recommendation")).not.toBeNull();
    expect(panel.getAllByTestId("option-card")).toHaveLength(4);
    expect(card("localhost:8452").getAttribute("aria-selected")).toBe("true");
    fireEvent.click(panel.getByRole("button", { name: "Close details" }));
    expect(screen.queryByTestId("detail-panel")).toBeNull(); // closed stays closed: no fall back to the first system
    fireEvent.click(card("localhost:8452"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("detail-panel")).toBeNull();
  });

  it("filters the table by status and by search", async () => {
    await open();
    // The open system (the first one) stays listed whatever the filter, as before the panel.
    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "couldnt_check" } });
    expect(cards()).toHaveLength(2);
    expect(cards()[0]!.getAttribute("aria-current")).toBe("true");
    // With the panel closed, the filter alone decides.
    fireEvent.click(within(screen.getByTestId("detail-panel")).getByRole("button", { name: "Close details" }));
    expect(cards()).toHaveLength(1);
    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "all" } });
    fireEvent.change(screen.getByRole("searchbox", { name: "Search systems" }), { target: { value: "8452" } });
    expect(cards()).toHaveLength(1);
  });

  it("opens the same panel from a Roadmap row", async () => {
    await open();
    fireEvent.click(button("Roadmap"));
    fireEvent.click(screen.getAllByTestId("roadmap-row")[0]!);
    const panel = within(screen.getByTestId("detail-panel"));
    expect(panel.getByTestId("migration-system")).not.toBeNull();
    expect(panel.getByTestId("migration-today")).not.toBeNull();
  });

  it("turns the panel's changing buttons off in a closed assessment", async () => {
    mockApi({ [GET]: { body: migrationView } });
    render(
      <ReadOnlyProvider readOnly>
        <MigrationScreen importId={7} onViewFix={vi.fn()} onPlanChanged={vi.fn()} />
      </ReadOnlyProvider>,
    );
    await screen.findByRole("heading", { level: 1, name: migrationView.title });
    fireEvent.click(card("localhost:8452"));
    const choose = within(option("keep")).getByRole("button", { name: "Choose this option" }) as HTMLButtonElement;
    expect(choose.disabled).toBe(true);
    expect(choose.getAttribute("title")).toBe(CLOSED_SENTENCE);
  });
});

// 22 November 2026: where each system's status came from, beside its status: read from a server, measured on a copy of
// a signing program here, or only the file before a measurement. The Today box says what that means for the system.
describe("Migration, where each status came from", () => {
  it("draws one tag on each system card, in the backend's words", async () => {
    const { fetchMock } = await open();
    expect(
      cards().map((c) =>
        within(c)
          .getAllByTestId("source-tag")
          .map((t) => t.textContent),
      ),
    ).toEqual([...Array.from({ length: 5 }, () => ["Observed live"]), ["Proven in the lab"], ["From your file"]]);
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("the Today box of a system says what its tag means for it", async () => {
    await open();
    fireEvent.click(card("acme-sign 1.4.2"));
    const line = within(screen.getByTestId("migration-today")).getByTestId("source-line");
    expect(text(line)).toBe(
      "Proven in the lab Measured by running a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.",
    );
  });
});
