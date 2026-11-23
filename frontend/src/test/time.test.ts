import { describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { formatTime, localTimes, TIMES_ASK, TIMES_HEADER, withLocalTimes } from "../time";
import { mockApi } from "./fixtures";

// The 5c fixes: one formatter for every time on screen, in the viewer's own time zone. These tests are a viewer in
// New York (vite.config.ts sets TZ), so the same moment reads the same on every machine.

describe("formatTime", () => {
  it("writes a moment as day, month in words, year, the clock with am or pm, and the zone", () => {
    expect(formatTime("2026-11-18T19:46:03Z")).toBe("18 November 2026, 2:46 pm EST");
    expect(formatTime("2026-11-19T00:46:03.512Z")).toBe("18 November 2026, 7:46 pm EST"); // the day is the viewer's too
  });

  it("follows summer time", () => {
    expect(formatTime("2026-07-04T16:05:00Z")).toBe("4 July 2026, 12:05 pm EDT");
    expect(formatTime("2026-03-08T06:59:00Z")).toBe("8 March 2026, 1:59 am EST");
    expect(formatTime("2026-03-08T07:00:00Z")).toBe("8 March 2026, 3:00 am EDT"); // the clock jumps an hour
  });

  it("writes midnight and noon as 12", () => {
    expect(formatTime("2026-11-18T05:00:00Z")).toBe("18 November 2026, 12:00 am EST");
    expect(formatTime("2026-11-18T17:00:00Z")).toBe("18 November 2026, 12:00 pm EST");
  });

  it("can be asked for another zone, and says which", () => {
    expect(formatTime("2026-11-18T19:46:03Z", "UTC")).toBe("18 November 2026, 7:46 pm UTC");
    expect(formatTime("2026-11-18T19:46:03Z", "America/Los_Angeles")).toBe("18 November 2026, 11:46 am PST");
    expect(formatTime("2026-11-18T19:46:03Z", "Asia/Kolkata")).toMatch(/^19 November 2026, 1:16 am (GMT\+5:30|IST)$/);
  });

  it("leaves text that is no time as it is", () => {
    expect(formatTime("not a time")).toBe("not a time");
    expect(formatTime("")).toBe("");
  });
});

describe("localTimes", () => {
  it("writes each marked time in a sentence in the viewer's zone", () => {
    expect(localTimes("Accepted by You on [[time:2026-11-18T19:46:03Z]].")).toBe(
      "Accepted by You on 18 November 2026, 2:46 pm EST.",
    );
    expect(
      localTimes("Rolled back [[time:2026-11-18T19:46:03Z]]. Measured again [[time:2026-11-18T19:47:10Z]]: Classical."),
    ).toBe("Rolled back 18 November 2026, 2:46 pm EST. Measured again 18 November 2026, 2:47 pm EST: Classical.");
  });

  it("changes nothing else: plain text, a date, and a mark that is not whole", () => {
    expect(localTimes("Pack 2026.11.1, built 18 November 2026.")).toBe("Pack 2026.11.1, built 18 November 2026.");
    expect(localTimes("[[time:yesterday]] and [[time:2026-11-18]]")).toBe("[[time:yesterday]] and [[time:2026-11-18]]");
    expect(localTimes("18 November 2026, 19:46 UTC")).toBe("18 November 2026, 19:46 UTC");
  });
});

describe("withLocalTimes", () => {
  it("reaches every sentence of an answer, however deep, and leaves recorded moments as they are", () => {
    const answer = {
      decided_line: "Accepted by You on [[time:2026-11-18T19:46:03Z]].",
      history: { rows: [{ at: "2026-11-18T19:46:03Z", at_text: "[[time:2026-11-18T19:46:03Z]]", number: 1 }] },
      lines: ["Tried [[time:2026-11-18T19:46:03Z]].", "No time here."],
      nothing: null,
      count: 3,
    };
    expect(withLocalTimes(answer)).toEqual({
      decided_line: "Accepted by You on 18 November 2026, 2:46 pm EST.",
      history: { rows: [{ at: "2026-11-18T19:46:03Z", at_text: "18 November 2026, 2:46 pm EST", number: 1 }] },
      lines: ["Tried 18 November 2026, 2:46 pm EST.", "No time here."],
      nothing: null,
      count: 3,
    });
    expect(withLocalTimes("[[time:2026-11-18T19:46:03Z]]")).toBe("18 November 2026, 2:46 pm EST");
    expect(withLocalTimes(null)).toBeNull();
  });
});

describe("every request", () => {
  it("asks the server for marked times, and every answer has them written in the viewer's zone", async () => {
    const fetchMock = mockApi({
      "GET /api/session": {
        body: { needs_setup: false, logged_in: true, note: "Started [[time:2026-11-18T19:46:03Z]]." },
      },
      "POST /api/login": {
        status: 409,
        body: { error: { message: "Closed on [[time:2026-11-18T19:46:03Z]].", line: null, field: null } },
      },
    });
    const session = (await api.getSession()) as unknown as { note: string };
    expect(session.note).toBe("Started 18 November 2026, 2:46 pm EST.");
    const sent = fetchMock.mock.calls[0]![1]!.headers as Record<string, string>;
    expect(sent[TIMES_HEADER]).toBe(TIMES_ASK);
    // a refusal's sentence is an answer too
    await expect(api.login("x")).rejects.toThrow("Closed on 18 November 2026, 2:46 pm EST.");
    const posted = fetchMock.mock.calls[1]![1]!.headers as Record<string, string>;
    expect(posted[TIMES_HEADER]).toBe(TIMES_ASK);
    expect(posted["Content-Type"]).toBe("application/json");
    vi.unstubAllGlobals();
  });
});
