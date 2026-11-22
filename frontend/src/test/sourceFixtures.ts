// Where it came from (22 November 2026): the four tags as the backend sends them (backend/app/present/source.py), with
// each item's own sentence. The words are the backend's; the pages only draw them.
import type { Source } from "../api";

export const LABELS = {
  live: "Observed live",
  lab: "Proven in the lab",
  file: "From your file",
  published: "Published",
} as const;
export const MEANINGS = {
  live: "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
  lab: "Run on a copy on this computer, never on your live system.",
  file: "Nothing has been observed or run for it yet: it rests only on your file.",
  published: "Said by the library's maker or a published standard. The app has not measured it.",
} as const;

const tag = (key: Source["key"], note: string | null = null): Source => ({
  key,
  label: LABELS[key],
  meaning: MEANINGS[key],
  note,
});

export const live = (where: string) =>
  tag("live", `Read from ${where}, an address in your file that you confirmed, with handshakes only.`);
export const labCopy = (what: string) =>
  tag(
    "lab",
    `Run on a copy of ${what} on this computer, in demo mode (a plain process on this computer, not isolated). Your live system was not touched.`,
  );
export const labTry = () =>
  tag("lab", "Run on a test copy of the server on this computer, with the change. Your live server was not changed.");
export const labProof = () =>
  tag("lab", "Run on the changed code, a copy on this computer. Nothing was merged or deployed.");
export const afterChange = (where: string) =>
  tag("live", `Measured again on ${where} right after the change was applied there, with handshakes only.`);
export const fromFile = (note = "Nothing has been observed or run for it yet: it rests only on what your file says.") =>
  tag("file", note);
export const published = (
  note = "From the maker's release notes, quoted under Details and evidence. The app has not measured it.",
) => tag("published", note);
export const couldntCheck = () =>
  fromFile("The app couldn't check this claim, so it rests only on what your file says.");
export const ofClaim = (file: string) => fromFile(`Taken from ${file}. The app has not checked it here: Verify does.`);

/** A Dependencies answer's tag by the backend's rule (of_answer): its label decides, and an answer with none rests on the list. */
export function ofAnswer(label: string | null | undefined, answer: string): Source {
  if (label === "release_notes") return published();
  if (label === "public_copy")
    return tag(
      "lab",
      "Measured on a public copy of this version on this computer, in its own locked-down container. Your live system was not touched.",
    );
  if (answer === "doesnt_apply")
    return published(
      "This question is not asked of this kind of library, by what its maker publishes. The app has not measured it.",
    );
  return fromFile("The app has no answer for this yet: it rests only on your dependency list.");
}
export const ofLibrary = () =>
  fromFile("Listed in your dependency list. The app has not checked that your system loads it.");
