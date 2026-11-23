import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { OttoSettingsView } from "../api";
import { SettingsPage } from "../components/pages/SettingsPage";
import { calls, mockApi, session } from "./fixtures";
import { ottoInstalledTwo } from "./ottoFixtures";
import {
  NOT_MARKED,
  sandboxBlocked,
  sandboxByItself,
  sandboxOff,
  sandboxOn,
  sandboxOnLive,
  settingsWith,
} from "./sandboxFixtures";
import { workspace } from "./shellFixtures";

type Routes = Parameters<typeof mockApi>[0];
const OTTO = "GET /api/otto";
const SANDBOX = "POST /api/otto/sandbox";

async function open(view: OttoSettingsView, routes: Routes = {}) {
  const fetchMock = mockApi({ [OTTO]: { body: view }, ...routes });
  render(
    <SettingsPage
      session={session}
      workspace={workspace}
      theme="dark"
      onTheme={() => undefined}
      onChanged={() => undefined}
      onLoadDemo={() => undefined}
      loadingDemo={false}
      demoResult={null}
      section={null}
    />,
  );
  await screen.findByTestId("otto-installed-line");
  return fetchMock;
}

const block = () => within(screen.getByTestId("sandbox-research"));
const posts = (fetchMock: ReturnType<typeof mockApi>) => calls(fetchMock).filter((c) => c.startsWith("POST"));
function sent(fetchMock: ReturnType<typeof mockApi>): unknown[] {
  return fetchMock.mock.calls
    .filter(([input, init]) => String(input) === "/api/otto/sandbox" && init?.method === "POST")
    .map(([, init]) => JSON.parse(String(init?.body)));
}

describe("Settings: Sandbox research (prototype)", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("is not drawn by a backend that sends no such block", async () => {
    await open(ottoInstalledTwo);
    expect(screen.queryByTestId("sandbox-research")).toBeNull();
  });

  it("is off and greyed, with every reason, where it can't be turned on", async () => {
    const fetchMock = await open(settingsWith(sandboxBlocked));
    const sw = block().getByTestId("sandbox-switch") as HTMLInputElement;
    expect(sw.checked).toBe(false);
    expect(sw.disabled).toBe(true);
    const reasons = within(block().getByTestId("sandbox-switch-reasons")).getAllByRole("listitem");
    expect(reasons.map((r) => r.textContent)).toEqual([NOT_MARKED, "It needs isolated mode. Docker is not running."]);
    expect(block().getByTestId("sandbox-status-line").textContent).toBe(
      "Sandbox research is off, and can't be turned on here.",
    );
    fireEvent.click(sw);
    expect(screen.queryByTestId("sandbox-box")).toBeNull();
    expect(posts(fetchMock)).toEqual([]);
    // the tick is off too, with its reason, and no spending is shown for a switch that is off
    expect((block().getByTestId("sandbox-by-itself") as HTMLInputElement).disabled).toBe(true);
    expect(block().queryByTestId("sandbox-spent-line")).toBeNull();
  });

  it("turning it on opens a box first: nothing is sent before the click in that box", async () => {
    const fetchMock = await open(settingsWith(sandboxOff), { [SANDBOX]: { body: settingsWith(sandboxOn) } });
    fireEvent.click(block().getByTestId("sandbox-switch"));
    const box = within(await screen.findByTestId("sandbox-box"));
    expect(box.getByRole("heading").textContent).toBe("Turn on Sandbox research?");
    expect(box.getAllByRole("listitem").map((li) => li.textContent)).toEqual(sandboxOff.box.lines);
    expect(posts(fetchMock)).toEqual([]);
    // Cancel closes it and sends nothing; the switch stays off
    fireEvent.click(box.getByTestId("sandbox-box-cancel"));
    await waitFor(() => expect(screen.queryByTestId("sandbox-box")).toBeNull());
    expect(posts(fetchMock)).toEqual([]);
    expect((block().getByTestId("sandbox-switch") as HTMLInputElement).checked).toBe(false);
    // Escape does the same
    fireEvent.click(block().getByTestId("sandbox-switch"));
    await screen.findByTestId("sandbox-box");
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByTestId("sandbox-box")).toBeNull());
    expect(posts(fetchMock)).toEqual([]);
    // Turn on: one request, and the view it answers with is shown
    fireEvent.click(block().getByTestId("sandbox-switch"));
    fireEvent.click(within(await screen.findByTestId("sandbox-box")).getByTestId("sandbox-box-confirm"));
    await waitFor(() => expect((block().getByTestId("sandbox-switch") as HTMLInputElement).checked).toBe(true));
    expect(sent(fetchMock)).toEqual([{ on: true }]);
    expect(screen.queryByTestId("sandbox-box")).toBeNull();
    expect(block().getByTestId("sandbox-spent-line").textContent).toBe(sandboxOn.spent_line);
    expect(block().getByTestId("sandbox-status-line").textContent).toBe(sandboxOn.status_line);
  });

  it("a refusal to turn on closes the box and is shown in the block", async () => {
    const fetchMock = await open(settingsWith(sandboxOff), {
      [SANDBOX]: {
        status: 409,
        body: {
          error: {
            message: "Sandbox research can't be turned on here. It needs isolated mode. Docker is not running.",
            line: null,
            field: null,
          },
        },
      },
    });
    fireEvent.click(block().getByTestId("sandbox-switch"));
    fireEvent.click(within(await screen.findByTestId("sandbox-box")).getByTestId("sandbox-box-confirm"));
    expect((await block().findByTestId("otto-error")).textContent).toContain("can't be turned on here");
    expect(screen.queryByTestId("sandbox-box")).toBeNull();
    expect((block().getByTestId("sandbox-switch") as HTMLInputElement).checked).toBe(false);
    expect(sent(fetchMock)).toEqual([{ on: true }]);
  });

  it("turning it off needs no box and is sent at once", async () => {
    const fetchMock = await open(settingsWith(sandboxOn), { [SANDBOX]: { body: settingsWith(sandboxOff) } });
    fireEvent.click(block().getByTestId("sandbox-switch"));
    await waitFor(() => expect((block().getByTestId("sandbox-switch") as HTMLInputElement).checked).toBe(false));
    expect(screen.queryByTestId("sandbox-box")).toBeNull();
    expect(sent(fetchMock)).toEqual([{ on: false }]);
  });

  it("the tick is greyed with its reason until Live Otto is on, then one click sets it", async () => {
    const first = await open(settingsWith(sandboxOn));
    const tick = block().getByTestId("sandbox-by-itself") as HTMLInputElement;
    expect(tick.disabled).toBe(true);
    expect(block().getByTestId("sandbox-by-itself-reason").textContent).toBe(
      "This can be ticked only while Live Otto is on.",
    );
    expect(block().getByTestId("sandbox-by-itself-line").textContent).toContain(
      "within the limit for one run and the limit for a day",
    );
    fireEvent.click(tick);
    expect(posts(first)).toEqual([]);
  });

  it("with Live Otto on the tick is set by a click and unset by another", async () => {
    let now = settingsWith(sandboxOnLive, true);
    const fetchMock = await open(now, {
      [SANDBOX]: (init) => {
        const body = JSON.parse(String(init?.body)) as { by_itself: boolean };
        now = settingsWith(body.by_itself ? sandboxByItself : sandboxOnLive, true);
        return { body: now };
      },
    });
    const tick = () => block().getByTestId("sandbox-by-itself") as HTMLInputElement;
    expect(tick().disabled).toBe(false);
    expect(block().queryByTestId("sandbox-by-itself-reason")).toBeNull();
    fireEvent.click(tick());
    await waitFor(() => expect(tick().checked).toBe(true));
    expect(block().getByTestId("sandbox-status-line").textContent).toBe(sandboxByItself.status_line);
    fireEvent.click(tick());
    await waitFor(() => expect(tick().checked).toBe(false));
    expect(sent(fetchMock)).toEqual([{ by_itself: true }, { by_itself: false }]);
  });

  it("each limit is saved by its own Save, as typed, and a refused amount is shown", async () => {
    const saved = settingsWith({ ...sandboxOn, day_limit: { ...sandboxOn.day_limit, value: "7.00" } });
    const fetchMock = await open(settingsWith(sandboxOn), {
      [SANDBOX]: (init) => {
        const body = JSON.parse(String(init?.body)) as { day_limit?: string; run_limit?: string };
        if (body.run_limit !== undefined)
          return {
            status: 400,
            body: {
              error: {
                message: "A spending limit is an amount in US dollars, like 5 or 2.50.",
                line: null,
                field: "limit",
              },
            },
          };
        return { body: saved };
      },
    });
    const day = block().getByTestId("sandbox-day-limit") as HTMLInputElement;
    expect(day.value).toBe("10.00");
    fireEvent.change(day, { target: { value: "7" } });
    expect(posts(fetchMock)).toEqual([]); // typing sends nothing
    fireEvent.click(block().getByTestId("sandbox-day-save"));
    await block().findByTestId("sandbox-day-saved");
    expect((block().getByTestId("sandbox-day-limit") as HTMLInputElement).value).toBe("7.00");
    fireEvent.change(block().getByTestId("sandbox-run-limit"), { target: { value: "lots" } });
    fireEvent.click(block().getByTestId("sandbox-run-save"));
    expect((await block().findByTestId("otto-error")).textContent).toContain("an amount in US dollars");
    expect(block().queryByTestId("sandbox-run-saved")).toBeNull();
    expect(sent(fetchMock)).toEqual([{ day_limit: "7" }, { run_limit: "lots" }]);
  });

  it("uses none of the words this app never says about a system", async () => {
    await open(settingsWith(sandboxByItself, true));
    const words = (screen.getByTestId("sandbox-research").textContent ?? "").toLowerCase();
    for (const word of ["secure", "score", "severity", "critical"]) expect(words).not.toContain(word);
  });
});
