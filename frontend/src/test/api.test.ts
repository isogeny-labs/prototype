import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";

/** A stand-in for fetch whose answers are given by the test, one by one, in any order. */
function slowFetch() {
  const asked: { path: string; method: string; answer: (body: unknown) => void; fail: () => void }[] = [];
  vi.stubGlobal(
    "fetch",
    (input: RequestInfo | URL, init?: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        asked.push({
          path: String(input),
          method: init?.method ?? "GET",
          answer: (body) =>
            resolve(
              new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }),
            ),
          fail: () => reject(new TypeError("network")),
        });
      }),
  );
  return asked;
}

/** Lets every promise that is ready run. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("a read that was on its way while a change was answered", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is asked again, so the page never gets what was there before a change it already has the answer to", async () => {
    const asked = slowFetch();
    const read = api.pollPlan(7);
    const change = api.runAll(7);
    await settle();
    expect(asked.map((a) => `${a.method} ${a.path}`)).toEqual(["GET /api/plans/7", "POST /api/plans/7/run-all"]);
    asked[1]!.answer({ tests: ["new"] }); // the change is answered first
    expect(await change).toEqual({ tests: ["new"] });
    asked[0]!.answer({ tests: ["old"] }); // the read was made before the change: it holds the old state
    await settle();
    expect(asked.map((a) => a.method)).toEqual(["GET", "POST", "GET"]); // asked again, the same address
    expect(asked[2]!.path).toBe("/api/plans/7");
    asked[2]!.answer({ tests: ["new"] });
    expect(await read).toEqual({ tests: ["new"] });
  });

  it("is asked again when the change failed too: nobody knows what it left behind", async () => {
    const asked = slowFetch();
    const read = api.pollPlan(7);
    const change = api.runAll(7).catch((e: unknown) => e);
    await settle();
    asked[1]!.fail();
    await change;
    asked[0]!.answer({ tests: ["old"] });
    await settle();
    expect(asked).toHaveLength(3);
    asked[2]!.answer({ tests: ["as it is now"] });
    expect(await read).toEqual({ tests: ["as it is now"] });
  });

  it("is asked again twice at most", async () => {
    const asked = slowFetch();
    const read = api.pollPlan(7);
    for (let round = 0; round < 3; round += 1) {
      const change = api.runAll(7);
      await settle();
      asked[asked.length - 1]!.answer({ round });
      await change;
      asked
        .filter((a) => a.method === "GET")
        .at(-1)!
        .answer({ read: round }); // (the newest ask of the read)
      await settle();
    }
    expect(asked.filter((a) => a.method === "GET")).toHaveLength(3); // the first, and two more
    expect(await read).toEqual({ read: 2 });
  });
});

describe("every other request", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is sent once: a read that no change crossed, and a change that another change crossed", async () => {
    const asked = slowFetch();
    const read = api.pollPlan(7);
    await settle();
    asked[0]!.answer({ tests: [] });
    expect(await read).toEqual({ tests: [] });
    expect(asked).toHaveLength(1);

    const first = api.runAll(7);
    const second = api.runAll(8);
    await settle();
    asked[2]!.answer({ second: true });
    await second;
    asked[1]!.answer({ first: true });
    expect(await first).toEqual({ first: true });
    expect(asked.map((a) => a.method)).toEqual(["GET", "POST", "POST"]);

    // A read that starts after a change was answered is fresh already.
    const later = api.pollPlan(7);
    await settle();
    asked[3]!.answer({ tests: ["fresh"] });
    expect(await later).toEqual({ tests: ["fresh"] });
    expect(asked).toHaveLength(4);
  });
});
