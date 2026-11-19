/** The one way a time is written on screen (the 5c fixes, 19 November 2026): "18 November 2026, 7:46 pm EST", in the
 * viewer's own time zone. Every time the screens show goes through `formatTime`:
 *
 *   - a time the browser writes from a recorded moment (a result's "last run", a decision's "when"), and
 *   - a time inside a sentence the server words. The server can't know the viewer's zone, so the browser asks for
 *     marked times with one request header (`TIMES_HEADER`), the server writes `[[time:<moment>]]` where its UTC words
 *     would stand, and `localTimes` writes the time there. `api.ts` does that for every answer, in one place.
 *
 * Files keep UTC: the signed evidence file, the report, every download and both of Otto's ledgers are made by the
 * server without the header, and never hold a mark. A date with no time of day (a pack's build date, an advisory's
 * publication date, a review date) is not a moment and is shown as it is written. */

export const TIMES_HEADER = "X-Evidence-Lab-Times";
export const TIMES_ASK = "mark";

const MARK = /\[\[time:(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\]\]/g;

const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(timeZone: string | undefined): Intl.DateTimeFormat {
  const key = timeZone ?? "";
  let made = formatters.get(key);
  if (!made) {
    // The words are English, like the rest of the app; the zone is the viewer's own unless one is named.
    made = new Intl.DateTimeFormat("en-US", {
      day: "numeric",
      month: "long",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hourCycle: "h12",
      timeZoneName: "short",
      ...(timeZone ? { timeZone } : {}),
    });
    formatters.set(key, made);
  }
  return made;
}

/** A recorded moment as the screens write it: "18 November 2026, 7:46 pm EST". Text that is no time is returned as it
 * is: nothing is made up. `timeZone` is for tests; on screen it is always the viewer's own. */
export function formatTime(iso: string, timeZone?: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const parts: Partial<Record<Intl.DateTimeFormatPartTypes, string>> = {};
  for (const part of formatter(timeZone).formatToParts(date)) parts[part.type] = part.value;
  const { day, month, year, hour, minute, dayPeriod, timeZoneName } = parts;
  if (!day || !month || !year || !hour || !minute) return iso;
  const clock = `${hour}:${minute}${dayPeriod ? ` ${dayPeriod.toLowerCase()}` : ""}`;
  return `${day} ${month} ${year}, ${clock}${timeZoneName ? ` ${timeZoneName}` : ""}`;
}

/** A sentence from the server with each marked time written in the viewer's own zone. */
export function localTimes(text: string, timeZone?: string): string {
  if (!text.includes("[[time:")) return text;
  return text.replace(MARK, (_whole, iso: string) => formatTime(iso, timeZone));
}

/** An answer from the server with every marked time, in every sentence it holds, written in the viewer's own zone. The
 * answer is changed in place (it was just read from the network and belongs to nobody else) and returned. */
export function withLocalTimes<T>(value: T): T {
  if (typeof value === "string") return localTimes(value) as unknown as T;
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i += 1) {
      const item: unknown = value[i];
      if (typeof item === "string") {
        if (item.includes("[[time:")) value[i] = localTimes(item);
      } else if (item !== null && typeof item === "object") {
        withLocalTimes(item);
      }
    }
    return value;
  }
  if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of Object.keys(record)) {
      const item = record[key];
      if (typeof item === "string") {
        if (item.includes("[[time:")) record[key] = localTimes(item);
      } else if (item !== null && typeof item === "object") {
        withLocalTimes(item);
      }
    }
  }
  return value;
}
