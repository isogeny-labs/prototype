import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { OttoSettingsView } from "../api";
import App from "../App";
import { SettingsPage } from "../components/pages/SettingsPage";
import { calls, mockApi, session, text } from "./fixtures";
import {
  NOT_INSTALLED_LINE,
  ottoEmpty,
  ottoHarnessMissing,
  ottoInstalledOne,
  ottoInstalledTwo,
  ottoLiveOff,
  ottoLiveOn,
  ottoLiveOnNoKey,
  ottoRefused,
  ottoUpdateFound,
  packMadeHere,
} from "./ottoFixtures";
import { workspace } from "./shellFixtures";

type Routes = Parameters<typeof mockApi>[0];

const OTTO = "GET /api/otto";
const CHECK = "POST /api/otto/packs/check";
const INSTALL = "POST /api/otto/packs/install";
const LIVE = "POST /api/otto/live";
const refusal = (status: number, message: string, field: string | null = null) => ({ status, body: { error: { message, line: null, field } } });

function Settings({ section = null }: { section?: string | null }) {
  return (
    <SettingsPage
      session={session}
      workspace={workspace}
      theme="dark"
      onTheme={() => undefined}
      onChanged={() => undefined}
      onLoadDemo={() => undefined}
      loadingDemo={false}
      demoResult={null}
      section={section}
    />
  );
}

async function open(view: OttoSettingsView = ottoEmpty, routes: Routes = {}, section: string | null = null) {
  const fetchMock = mockApi({ [OTTO]: { body: view }, ...routes });
  render(<Settings section={section} />);
  await screen.findByTestId("otto-installed-line");
  return fetchMock;
}

const packsSection = () => screen.getByTestId("test-packs");
const liveSection = () => screen.getByTestId("live-otto");
const packs = () => within(packsSection());
const live = () => within(liveSection());
const posts = (fetchMock: ReturnType<typeof mockApi>) => calls(fetchMock).filter((c) => c.startsWith("POST"));
/** The JSON bodies of the POSTs to one address, in order. */
function sent(fetchMock: ReturnType<typeof mockApi>, path: string): unknown[] {
  return fetchMock.mock.calls
    .filter(([url, init]) => String(url) === path && init?.method === "POST")
    .map(([, init]) => (init?.body === undefined ? undefined : JSON.parse(String(init.body))));
}
const toggle = () => screen.getByTestId("live-otto-switch") as HTMLInputElement;
const limit = () => screen.getByTestId("live-otto-limit") as HTMLInputElement;

// Every state of the samples, and the ones the backend words in the same way (see ottoFixtures).
const STATES: [string, OttoSettingsView][] = [
  ["nothing installed", ottoEmpty],
  ["an update found", ottoUpdateFound],
  ["one pack installed and the next found", ottoInstalledOne],
  ["two packs installed", ottoInstalledTwo],
  ["Use live Claude on", ottoLiveOn],
  ["Otto not installed", ottoHarnessMissing],
  ["a refused pack", ottoRefused],
  ["a key present and the switch off", ottoLiveOff],
];

describe("Settings, the Otto sections", () => {
  it("loads them when the page opens, beside the other settings, and starts nothing", async () => {
    const fetchMock = await open();
    const page = within(screen.getByTestId("settings-page"));
    // The two new sections sit among the others, under the titles the view gives.
    expect(page.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Organization",
      "Appearance",
      "Demo projects",
      ottoEmpty.packs.title,
      ottoEmpty.live.title,
      "How software runs here",
    ]);
    expect(packsSection().id).toBe("test-packs");
    expect(calls(fetchMock)).toEqual([OTTO]);
  });

  it.each(STATES)("draws every line of the view as the backend words it: %s", async (_name, view) => {
    await open(view);
    const p = view.packs;
    expect(text(packsSection())).toContain(p.intro);
    expect(screen.getByTestId("otto-installed-line").textContent).toBe(p.installed_line);
    expect(packs().queryByTestId("otto-counts-line")?.textContent ?? null).toBe(p.counts_line);
    // One card per installed pack: its line, who signed it, and its fingerprint cut short with the whole value on hover.
    const cards = packs().queryAllByTestId("otto-pack-card");
    expect(cards.map((c) => c.getAttribute("data-version"))).toEqual(p.installed.map((c) => c.version));
    p.installed.forEach((pack, i) => {
      const card = cards[i]!;
      expect(text(card), pack.version).toContain(pack.line);
      expect(text(card), pack.version).toContain(pack.signer);
      const fingerprint = within(card).getByTitle(pack.fingerprint);
      expect(fingerprint.textContent, pack.version).toBe(pack.fingerprint.slice(0, 12));
      expect(text(card), pack.version).not.toContain(pack.fingerprint);
    });
    const check = screen.getByTestId("otto-check-updates") as HTMLButtonElement;
    expect(check.textContent).toBe(p.check.button);
    expect(check.disabled).toBe(false);
    expect(text(packsSection())).toContain(p.check.note);
    expect(packs().queryByTestId("otto-checked-line")?.textContent ?? null).toBe(p.checked_line);
    expect(packs().queryAllByTestId("otto-refused-item")).toHaveLength(p.refused.length);
    expect(packs().queryByTestId("otto-update-line")?.textContent ?? null).toBe(p.update?.line ?? null);
    expect(packs().queryByTestId("otto-install-update")?.textContent ?? null).toBe(p.update?.button ?? null);
    expect(screen.getByTestId("otto-order-note").textContent).toBe(p.order_note);
    expect(screen.getByTestId("otto-harness-line").textContent).toBe(view.harness.line);
    expect(screen.getByTestId("otto-answers-line").textContent).toBe(view.answers.line);
    // Nothing is open or wrong before a button is pressed.
    expect(screen.queryByTestId("otto-install-dialog")).toBeNull();
    expect(screen.queryByTestId("otto-error")).toBeNull();

    const l = view.live;
    expect(live().getByRole("heading", { level: 2, name: l.title })).not.toBeNull();
    expect(screen.getByTestId("live-otto-key-line").textContent).toBe(l.key_line);
    const sw = live().getByRole("switch", { name: l.switch.label }) as HTMLInputElement;
    expect(sw).toBe(toggle());
    expect(sw.checked).toBe(l.switch.on);
    // Off and can't be turned on: disabled. Anything else can be changed.
    expect(sw.disabled).toBe(!l.switch.on && !l.switch.can_turn_on);
    expect(live().queryByTestId("live-otto-switch-reason")?.textContent ?? null).toBe(l.switch.blocked_reason);
    expect(live().getByLabelText(l.limit.label)).toBe(limit());
    expect(limit().value).toBe(l.limit.value);
    expect(screen.getByTestId("live-otto-save").textContent).toBe(l.limit.save);
    expect(text(liveSection())).toContain(l.limit.note);
    expect(screen.getByTestId("live-otto-sent-line").textContent).toBe(l.sent_line);
    expect(screen.getByTestId("live-otto-status-line").textContent).toBe(l.status_line);
    expect(screen.getByTestId("live-otto-price-line").textContent).toBe(l.price_line);
  });

  it.each(STATES)("never shows or asks for the API key, and uses no score or 'secure': %s", async (_name, view) => {
    await open(view);
    // The only things to type into or switch are the spending limit and Use live Claude.
    expect(packsSection().querySelectorAll("input, textarea, select")).toHaveLength(0);
    expect(Array.from(liveSection().querySelectorAll("input, textarea, select")).map((el) => el.getAttribute("data-testid"))).toEqual([
      "live-otto-switch",
      "live-otto-limit",
    ]);
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(limit().getAttribute("type") ?? "text").toBe("text");
    const words = `${text(packsSection())} ${text(liveSection())}`;
    expect(words).not.toMatch(/secure|\bscore|\bgrade\b|time.to.hack/i);
    expect(words).not.toMatch(/sk-ant|made-up-key/);
    // And the only buttons are the approved ones.
    const buttons = [...packs().getAllByRole("button"), ...live().getAllByRole("button")].map((b) => b.getAttribute("data-testid"));
    expect(buttons).toEqual(["otto-check-updates", ...(view.packs.update ? ["otto-install-update"] : []), "live-otto-save"]);
  });

  it("says so in a plain error box when the settings can't be loaded", async () => {
    mockApi({ [OTTO]: refusal(500, "The test packs could not be read.") });
    render(<Settings />);
    const error = await screen.findByTestId("otto-error");
    expect(text(error)).toBe("The test packs could not be read.");
    expect(within(error).getByRole("alert")).not.toBeNull();
    expect(packsSection().contains(error)).toBe(true);
    expect(screen.queryByTestId("live-otto")).toBeNull();
    // The rest of Settings is there as before.
    expect(screen.getByRole("heading", { level: 2, name: "Organization" })).not.toBeNull();
  });
});

describe("Settings, Test packs", () => {
  it("says so plainly when a pack installed by an earlier build can't be read, and is silent otherwise", async () => {
    const line =
      "Test pack 2026.11.1, installed here earlier, can't be read by this version of the app: it was made by an earlier build.";
    await open({
      ...ottoEmpty,
      packs: { ...ottoEmpty.packs, installed_line: "No installed test pack can be read by this version of the app.", unreadable_line: line },
    });
    expect(screen.getByTestId("otto-unreadable-line").textContent).toBe(line);
    expect(screen.getByTestId("otto-installed-line").textContent).toBe("No installed test pack can be read by this version of the app.");
  });

  it("shows no such line when every installed pack reads", async () => {
    await open(ottoEmpty);
    expect(screen.queryByTestId("otto-unreadable-line")).toBeNull();
  });

  it("Check for updates calls the API once and shows what was found", async () => {
    const fetchMock = await open(ottoEmpty, { [CHECK]: { body: ottoUpdateFound } });
    expect(packs().queryByTestId("otto-checked-line")).toBeNull();
    fireEvent.click(screen.getByTestId("otto-check-updates"));
    expect((await screen.findByTestId("otto-checked-line")).textContent).toBe(ottoUpdateFound.packs.checked_line);
    expect(posts(fetchMock)).toEqual([CHECK]);
    expect(sent(fetchMock, "/api/otto/packs/check")).toEqual([undefined]);
    expect(screen.getByTestId("otto-update-line").textContent).toBe(ottoUpdateFound.packs.update!.line);
    expect(screen.getByTestId("otto-install-update").textContent).toBe(ottoUpdateFound.packs.update!.button);
    // Finding an update installs nothing.
    expect(packs().queryAllByTestId("otto-pack-card")).toHaveLength(0);
    expect(screen.queryByTestId("otto-install-dialog")).toBeNull();
  });

  it("waits for the answer: the button is off while the check runs", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(input)}`;
      if (key === CHECK) await gate;
      const body = key === CHECK ? ottoUpdateFound : key === OTTO ? ottoEmpty : null;
      if (body === null) throw new Error(`Unexpected request: ${key}`);
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<Settings />);
    const check = (await screen.findByTestId("otto-check-updates")) as HTMLButtonElement;
    fireEvent.click(check);
    await waitFor(() => expect(check.disabled).toBe(true));
    fireEvent.click(check);
    // Every other button of the two sections waits for the answer too.
    expect((screen.getByTestId("live-otto-save") as HTMLButtonElement).disabled).toBe(true);
    release();
    await screen.findByTestId("otto-checked-line");
    expect((screen.getByTestId("otto-check-updates") as HTMLButtonElement).disabled).toBe(false);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("Install update opens a box with the view's words; Cancel and Escape close it and call nothing", async () => {
    const fetchMock = await open(ottoUpdateFound);
    const dialog = ottoUpdateFound.packs.update!.dialog;
    fireEvent.click(screen.getByTestId("otto-install-update"));
    const box = screen.getByTestId("otto-install-dialog");
    expect(box.getAttribute("role")).toBe("dialog");
    expect(within(box).getByRole("heading", { name: dialog.title })).not.toBeNull();
    expect(Array.from(box.querySelectorAll("p")).map((p) => p.textContent)).toEqual(dialog.lines);
    expect(within(box).getAllByRole("button").map((b) => [b.getAttribute("data-testid"), b.textContent])).toEqual([
      ["otto-install-cancel", dialog.cancel],
      ["otto-install-confirm", dialog.confirm],
    ]);
    // The keyboard starts on Cancel, so pressing Enter straight away installs nothing.
    expect(document.activeElement).toBe(screen.getByTestId("otto-install-cancel"));
    // Opening the box installed nothing.
    expect(posts(fetchMock)).toEqual([]);

    fireEvent.click(screen.getByTestId("otto-install-cancel"));
    expect(screen.queryByTestId("otto-install-dialog")).toBeNull();
    fireEvent.click(screen.getByTestId("otto-install-update"));
    expect(screen.getByTestId("otto-install-dialog")).not.toBeNull();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("otto-install-dialog")).toBeNull();
    expect(posts(fetchMock)).toEqual([]);
    // The update is still offered.
    expect(screen.getByTestId("otto-install-update")).not.toBeNull();
  });

  it("only Install in the box installs: it sends the version once, closes the box and shows the view it answers with", async () => {
    const fetchMock = await open(ottoUpdateFound, { [INSTALL]: { body: ottoInstalledOne } });
    fireEvent.click(screen.getByTestId("otto-install-update"));
    fireEvent.click(screen.getByTestId("otto-install-confirm"));
    await waitFor(() => expect(packs().queryAllByTestId("otto-pack-card")).toHaveLength(1));
    expect(posts(fetchMock)).toEqual([INSTALL]);
    expect(sent(fetchMock, "/api/otto/packs/install")).toEqual([{ version: ottoUpdateFound.packs.update!.version }]);
    expect(screen.queryByTestId("otto-install-dialog")).toBeNull();
    expect(screen.getByTestId("otto-installed-line").textContent).toBe(ottoInstalledOne.packs.installed_line);
    expect(packs().getByTestId("otto-counts-line").textContent).toBe(ottoInstalledOne.packs.counts_line);
    // The next pack in order is offered now, with its own box.
    expect(screen.getByTestId("otto-update-line").textContent).toBe(ottoInstalledOne.packs.update!.line);
    fireEvent.click(screen.getByTestId("otto-install-update"));
    expect(within(screen.getByTestId("otto-install-dialog")).getByRole("heading", { name: ottoInstalledOne.packs.update!.dialog.title })).not.toBeNull();
  });

  it("closes the box and shows the backend's reason, once, when an install is refused", async () => {
    const reason = "Test pack 2026.11.1 can't be installed now. No newer test pack in the updates folder.";
    const fetchMock = await open(ottoUpdateFound, { [INSTALL]: refusal(409, reason) });
    fireEvent.click(screen.getByTestId("otto-install-update"));
    fireEvent.click(screen.getByTestId("otto-install-confirm"));
    const error = await screen.findByTestId("otto-error");
    expect(text(error)).toBe(reason);
    expect(packsSection().contains(error)).toBe(true);
    expect(screen.getAllByTestId("otto-error")).toHaveLength(1);
    expect(screen.queryByTestId("otto-install-dialog")).toBeNull();
    expect(posts(fetchMock)).toEqual([INSTALL]);
    expect(packs().queryAllByTestId("otto-pack-card")).toHaveLength(0);
  });

  it("lists a pack file that was not taken with the backend's reason, as a calm warning", async () => {
    await open(ottoEmpty, { [CHECK]: { body: ottoRefused } });
    fireEvent.click(screen.getByTestId("otto-check-updates"));
    const list = await screen.findByTestId("otto-refused");
    expect(list.tagName).toBe("UL");
    const items = within(list).getAllByTestId("otto-refused-item");
    expect(items.map((li) => Array.from(li.children).map((c) => c.textContent))).toEqual(ottoRefused.packs.refused.map((r) => [r.file, r.reason]));
    expect(items[0]!.children[0]!.className).toContain("font-mono");
    // Calm: not an error box, and nothing is offered to install.
    expect(screen.queryByRole("alert")).toBeNull();
    expect(list.className).not.toMatch(/amber/);
    expect(screen.getByTestId("otto-checked-line").textContent).toBe(ottoRefused.packs.checked_line);
    expect(screen.queryByTestId("otto-install-update")).toBeNull();
  });

  it("marks nothing by itself on a pack made on this computer: the pack's own line says so", async () => {
    const view: OttoSettingsView = { ...ottoInstalledTwo, packs: { ...ottoInstalledTwo.packs, installed: [ottoInstalledTwo.packs.installed[0]!, packMadeHere] } };
    await open(view);
    const [shipped, made] = packs().getAllByTestId("otto-pack-card");
    expect(text(made)).toContain(packMadeHere.line);
    expect(text(made)).toContain(packMadeHere.signer);
    expect(text(made).match(/made on this computer/gi)).toHaveLength(2);
    expect(text(shipped)).not.toMatch(/made on this computer/i);
  });

  it("says calmly that Otto is not installed, in the backend's words", async () => {
    await open(ottoHarnessMissing);
    const line = screen.getByTestId("otto-harness-line");
    expect(line.textContent).toBe(NOT_INSTALLED_LINE);
    expect(line.getAttribute("data-installed")).toBe("false");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(line.className).not.toMatch(/amber/);
    // The packs stay listed; nothing else on the page changes.
    expect(packs().getAllByTestId("otto-pack-card")).toHaveLength(2);
  });

  it("is not scrolled to when the address names no section", async () => {
    const scrolled: string[] = [];
    Element.prototype.scrollIntoView = function scrollIntoView(this: Element) {
      scrolled.push(this.id);
    };
    try {
      await open(ottoInstalledTwo);
      expect(scrolled).toEqual([]);
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });
});

describe("Settings, Live Otto", () => {
  it("keeps Use live Claude off and disabled without an API key, with the backend's reason", async () => {
    const fetchMock = await open(ottoEmpty);
    expect(toggle().checked).toBe(false);
    expect(toggle().disabled).toBe(true);
    expect(toggle().getAttribute("aria-checked")).toBe("false");
    const reason = screen.getByTestId("live-otto-switch-reason");
    expect(reason.textContent).toBe(ottoEmpty.live.switch.blocked_reason);
    expect(toggle().getAttribute("aria-describedby")).toBe(reason.id);
    fireEvent.click(toggle());
    expect(posts(fetchMock)).toEqual([]);
  });

  it("turns Use live Claude on and off through the API when a key is present", async () => {
    let on = false;
    const fetchMock = await open(ottoLiveOff, {
      [LIVE]: (init) => {
        on = (JSON.parse(String(init?.body)) as { on: boolean }).on;
        return { body: on ? ottoLiveOn : ottoLiveOff };
      },
    });
    expect(toggle().disabled).toBe(false);
    expect(toggle().checked).toBe(false);
    expect(screen.queryByTestId("live-otto-switch-reason")).toBeNull();
    fireEvent.click(toggle());
    await waitFor(() => expect(toggle().checked).toBe(true));
    expect(screen.getByTestId("live-otto-status-line").textContent).toBe(ottoLiveOn.live.status_line);
    expect(screen.getByTestId("otto-answers-line").textContent).toBe(ottoLiveOn.answers.line);
    fireEvent.click(toggle());
    await waitFor(() => expect(toggle().checked).toBe(false));
    expect(screen.getByTestId("live-otto-status-line").textContent).toBe(ottoLiveOff.live.status_line);
    // Each change sent only the switch.
    expect(sent(fetchMock, "/api/otto/live")).toEqual([{ on: true }, { on: false }]);
  });

  it("lets a switch that was left on be turned off after the key has gone", async () => {
    const fetchMock = await open(ottoLiveOnNoKey, { [LIVE]: { body: ottoInstalledTwo } });
    expect(toggle().checked).toBe(true);
    expect(toggle().disabled).toBe(false);
    expect(screen.getByTestId("live-otto-switch-reason").textContent).toBe(ottoLiveOnNoKey.live.switch.blocked_reason);
    fireEvent.click(toggle());
    await waitFor(() => expect(toggle().checked).toBe(false));
    expect(sent(fetchMock, "/api/otto/live")).toEqual([{ on: false }]);
    // Now it is off with no key: it can't be turned on again.
    expect(toggle().disabled).toBe(true);
  });

  it("shows the backend's reason when turning it on is refused, and leaves the switch as it was", async () => {
    const reason = "Live Otto needs an API key on this computer, and none is set (ANTHROPIC_API_KEY). Otto goes on working with the answers recorded during the build.";
    await open(ottoLiveOff, { [LIVE]: refusal(409, reason) });
    fireEvent.click(toggle());
    const error = await screen.findByTestId("otto-error");
    expect(text(error)).toBe(reason);
    expect(liveSection().contains(error)).toBe(true);
    expect(toggle().checked).toBe(false);
  });

  it("saves the spending limit as typed, and then shows the amount the backend answers with", async () => {
    const saved: OttoSettingsView = { ...ottoEmpty, live: { ...ottoEmpty.live, limit: { ...ottoEmpty.live.limit, value: "3.50" } } };
    const fetchMock = await open(ottoEmpty, { [LIVE]: { body: saved } });
    expect(limit().value).toBe("2.00");
    fireEvent.change(limit(), { target: { value: "3.5" } });
    expect(limit().value).toBe("3.5");
    fireEvent.click(screen.getByTestId("live-otto-save"));
    await waitFor(() => expect(limit().value).toBe("3.50"));
    expect(posts(fetchMock)).toEqual([LIVE]);
    // Only the limit is sent, as typed: the backend reads the amount.
    expect(sent(fetchMock, "/api/otto/live")).toEqual([{ limit: "3.5" }]);
    expect(screen.queryByTestId("otto-error")).toBeNull();
    expect(text(live().getByRole("status"))).toBe("Saved.");
  });

  it("keeps what Check for updates found when the switch or the limit changes", async () => {
    // A Live Otto call answers without looking in the updates folder again: its answer has no found update.
    const fetchMock = await open(ottoUpdateFound, { [LIVE]: { body: { ...ottoEmpty, live: { ...ottoEmpty.live, limit: { ...ottoEmpty.live.limit, value: "3.50" } } } } });
    expect(text(packs().getByTestId("otto-update-line"))).toBe(ottoUpdateFound.packs.update!.line);
    fireEvent.change(limit(), { target: { value: "3.5" } });
    fireEvent.click(screen.getByTestId("live-otto-save"));
    await waitFor(() => expect(limit().value).toBe("3.50"));
    expect(sent(fetchMock, "/api/otto/live")).toEqual([{ limit: "3.5" }]);
    // the found update, its button and the checked line are still there
    expect(text(packs().getByTestId("otto-update-line"))).toBe(ottoUpdateFound.packs.update!.line);
    expect((packs().getByTestId("otto-install-update") as HTMLButtonElement).disabled).toBe(false);
    expect(text(packs().getByTestId("otto-checked-line"))).toBe(ottoUpdateFound.packs.checked_line!);
  });

  it("shows the backend's refusal in a plain error box when the amount is refused, and keeps what was typed", async () => {
    const reason = "The spending limit must be more than 0 and at most 1000 US dollars.";
    const fetchMock = await open(ottoEmpty, { [LIVE]: refusal(422, reason, "limit") });
    fireEvent.change(limit(), { target: { value: "5000" } });
    fireEvent.click(screen.getByTestId("live-otto-save"));
    const error = await screen.findByTestId("otto-error");
    expect(text(error)).toBe(reason);
    expect(within(error).getByRole("alert")).not.toBeNull();
    expect(liveSection().contains(error)).toBe(true);
    expect(packsSection().contains(error)).toBe(false);
    expect(limit().value).toBe("5000");
    expect(live().queryByRole("status")).toBeNull();
    expect(sent(fetchMock, "/api/otto/live")).toEqual([{ limit: "5000" }]);
    // The box goes once the amount is corrected and saved.
    fetchMock.mockImplementation(async () => new Response(JSON.stringify(ottoEmpty), { status: 200, headers: { "Content-Type": "application/json" } }));
    fireEvent.change(limit(), { target: { value: "2" } });
    fireEvent.click(screen.getByTestId("live-otto-save"));
    await waitFor(() => expect(screen.queryByTestId("otto-error")).toBeNull());
    expect(limit().value).toBe("2.00");
  });

  it("shows an error once, in the section where it happened", async () => {
    const fetchMock = await open(ottoEmpty, {
      [LIVE]: refusal(422, "The spending limit is a number of US dollars, for example 2 or 2.50.", "limit"),
      [CHECK]: refusal(500, "The updates folder could not be read."),
    });
    fireEvent.change(limit(), { target: { value: "two" } });
    fireEvent.click(screen.getByTestId("live-otto-save"));
    await waitFor(() => expect(liveSection().contains(screen.getByTestId("otto-error"))).toBe(true));
    fireEvent.click(screen.getByTestId("otto-check-updates"));
    await waitFor(() => expect(packsSection().contains(screen.getByTestId("otto-error"))).toBe(true));
    expect(screen.getAllByTestId("otto-error")).toHaveLength(1);
    expect(text(screen.getByTestId("otto-error"))).toBe("The updates folder could not be read.");
    expect(posts(fetchMock)).toEqual([LIVE, CHECK]);
  });
});

describe("Settings, the names the end-to-end walk looks for", () => {
  const present = (ids: string[]) => ids.filter((id) => screen.queryAllByTestId(id).length > 0);

  it("has every test id of the two sections, the box and an error", async () => {
    await open(ottoInstalledOne, { [CHECK]: { body: { ...ottoRefused, packs: { ...ottoRefused.packs, update: ottoInstalledOne.packs.update } } }, [LIVE]: refusal(422, "Refused.", "limit") });
    fireEvent.click(screen.getByTestId("otto-check-updates"));
    await screen.findByTestId("otto-refused");
    fireEvent.click(screen.getByTestId("live-otto-save"));
    await screen.findByTestId("otto-error");
    fireEvent.click(screen.getByTestId("otto-install-update"));
    const ids = [
      "test-packs",
      "otto-installed-line",
      "otto-pack-card",
      "otto-check-updates",
      "otto-checked-line",
      "otto-refused",
      "otto-update-line",
      "otto-install-update",
      "otto-install-dialog",
      "otto-install-confirm",
      "otto-install-cancel",
      "otto-order-note",
      "otto-harness-line",
      "otto-answers-line",
      "live-otto",
      "live-otto-key-line",
      "live-otto-switch",
      "live-otto-switch-reason",
      "live-otto-limit",
      "live-otto-save",
      "live-otto-sent-line",
      "live-otto-status-line",
      "live-otto-price-line",
      "otto-error",
    ];
    expect(present(ids)).toEqual(ids);
    // The two sections are sections of the page, and the box is a dialog with its two buttons inside.
    expect(packsSection().tagName).toBe("SECTION");
    expect(liveSection().tagName).toBe("SECTION");
    expect(within(screen.getByTestId("otto-install-dialog")).getAllByRole("button").map((b) => b.getAttribute("data-testid"))).toEqual([
      "otto-install-cancel",
      "otto-install-confirm",
    ]);
    expect(limit().tagName).toBe("INPUT");
  });
});

describe("Settings in the app", () => {
  const routes = (extra: Record<string, unknown> = {}): Routes =>
    ({ "GET /api/session": { body: session }, "GET /api/workspace": { body: workspace }, [OTTO]: { body: ottoInstalledTwo }, ...extra }) as Routes;

  beforeEach(() => {
    window.localStorage.clear();
  });

  it("opens on the Test packs section when the address names it, and brings it into view once it is drawn", async () => {
    const scrolled: string[] = [];
    Element.prototype.scrollIntoView = function scrollIntoView(this: Element) {
      scrolled.push(`${this.id}:${this.querySelector('[data-testid="otto-installed-line"]') ? "drawn" : "loading"}`);
    };
    try {
      window.history.replaceState(null, "", "#/settings?section=test-packs");
      mockApi(routes());
      render(<App />);
      await screen.findByTestId("otto-installed-line");
      expect(screen.getByTestId("settings-page")).not.toBeNull();
      // (the section is brought into view just after it is drawn: on a busy machine that is a moment later)
      await waitFor(() => expect(scrolled.at(-1)).toBe("test-packs:drawn"));
      expect(scrolled.every((s) => s.startsWith("test-packs:"))).toBe(true);
      expect(within(screen.getByRole("navigation", { name: "Workspace" })).getByRole("link", { name: "Settings" }).getAttribute("aria-current")).toBe("page");
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });

  it("opens Settings as before when the address names no section", async () => {
    window.history.replaceState(null, "", "#/settings");
    const fetchMock = mockApi(routes());
    render(<App />);
    await screen.findByTestId("otto-installed-line");
    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).not.toBeNull();
    expect(calls(fetchMock).filter((c) => c === OTTO)).toHaveLength(1);
    expect(calls(fetchMock).filter((c) => c.startsWith("POST"))).toEqual([]);
  });
});

// ---- Phase 6a: the name a person types once, for the decisions they record

describe("Settings, Who decides", () => {
  const name = (typed: string | null): NonNullable<OttoSettingsView["name"]> => ({
    title: "Who decides",
    label: "Your name",
    value: typed ?? "",
    recorded_as: typed ?? "You",
    typed: typed !== null,
    line: `Recorded as ${typed ?? "You"}, with the time.`,
    save: "Save",
    note: "Decisions on proposals are recorded under this name, with the time. This app has one login and does not check who is at the keyboard. Left empty, a decision is recorded as “You”. A decision already recorded keeps the name it was made under.",
    max: 60,
    ask_label: "Your name (asked once; kept in Settings)",
  });
  const NAME = "POST /api/otto/name";

  it("shows who a decision is recorded as, and Save keeps the typed name", async () => {
    const fetchMock = mockApi({ [OTTO]: { body: { ...ottoEmpty, name: name(null) } }, [NAME]: { body: { ...ottoEmpty, name: name("Kevin Singuyen") } } });
    render(<Settings />);
    const section = await screen.findByTestId("your-name");
    expect(within(section).getByRole("heading", { name: "Who decides" })).not.toBeNull();
    expect(text(within(section).getByTestId("otto-your-name-line"))).toBe("Recorded as You, with the time.");
    expect(text(section)).toContain("This app has one login and does not check who is at the keyboard.");
    const field = within(section).getByLabelText("Your name") as HTMLInputElement;
    expect(field.value).toBe("");
    expect(field.maxLength).toBe(60);
    expect(calls(fetchMock)).toEqual([OTTO]); // looking sends nothing
    fireEvent.change(field, { target: { value: "Kevin Singuyen" } });
    fireEvent.click(within(section).getByTestId("otto-your-name-save"));
    await waitFor(() => expect(text(within(section).getByTestId("otto-your-name-line"))).toBe("Recorded as Kevin Singuyen, with the time."));
    expect(calls(fetchMock)).toEqual([OTTO, NAME]);
    const sent = fetchMock.mock.calls.find(([input]) => String(input) === "/api/otto/name")?.[1];
    expect(JSON.parse(String(sent?.body))).toEqual({ name: "Kevin Singuyen" });
    expect(within(section).getByRole("status").textContent).toBe("Saved.");
  });

  it("shows the backend's reason when a name is refused, and keeps what was typed", async () => {
    mockApi({ [OTTO]: { body: { ...ottoEmpty, name: name(null) } }, [NAME]: refusal(422, "Keep the name to 60 characters or fewer.", "name") });
    render(<Settings />);
    const section = await screen.findByTestId("your-name");
    fireEvent.change(within(section).getByLabelText("Your name"), { target: { value: "A name" } });
    fireEvent.click(within(section).getByTestId("otto-your-name-save"));
    expect(text(await within(section).findByTestId("otto-error"))).toContain("Keep the name to 60 characters or fewer.");
    expect((within(section).getByLabelText("Your name") as HTMLInputElement).value).toBe("A name");
  });
});
