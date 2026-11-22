import type { OttoSandboxSection, OttoSettingsView } from "../api";
import { ottoInstalledTwo, ottoLiveOn } from "./ottoFixtures";

/** Sandbox research (prototype): the Settings block in the states the backend sends. The words are the backend's. */
const BOX = {
  title: "Turn on Sandbox research?",
  lines: [
    "While it is on, the app looks for published weaknesses in the libraries your files name by itself, about once a day. This sends each library's name and where it is published, and nothing else.",
    "For a weakness with a fix, public copies of the library can be fetched from its public package registry and run in locked containers on this computer, with no network.",
    'Designing and proving a test still starts on a click, unless "Design and prove tests by itself" is ticked.',
    "Nothing is added to an assessment without your Accept.",
  ],
  confirm: "Turn on",
  cancel: "Cancel",
};
const TICK_LINE =
  "Uses Claude, within the limit for one run and the limit for a day. A proven test is proposed; you accept or reject it. A test pack such a run makes is installed without a click of its own, as the pack of a run you start is.";

export const NOT_MARKED =
  "This computer is not marked as Isogeny's own sandbox: the EVIDENCE_LAB_SANDBOX_RESEARCH setting is not set where the app starts. Sandbox research can be turned on only there.";

/** Can be turned on: marked, isolated, Otto installed; still off. */
export const sandboxOff: OttoSandboxSection = {
  title: "Sandbox research (prototype)",
  intro:
    "A prototype for Isogeny's own sandbox. While it is on, the app looks for published weaknesses in the libraries your files name by itself, and a test can be designed and proven on public copies of a library that are fetched from its public package registry. Nothing is added to an assessment without your Accept.",
  switch: { label: "Sandbox research", on: false, can_turn_on: true, blocked_reasons: [] },
  box: BOX,
  by_itself: {
    label: "Design and prove tests by itself",
    on: false,
    can_turn_on: false,
    blocked_reason: "This can be ticked only while Sandbox research is on.",
    line: TICK_LINE,
  },
  run_limit: { label: "Most to spend in one research run (US dollars)", value: "5.00", save: "Save" },
  day_limit: { label: "Most to spend in a day (US dollars)", value: "10.00", save: "Save" },
  limits_note:
    "A run is one research command. Each call's cost is added up from the tokens the API reports, and a request that could pass a limit is not sent. When the day's limit is reached, no run starts by itself until the next day.",
  status_line:
    "Sandbox research is off. The app behaves as it did before: nothing is looked for by itself, and only the pinned public copies can run.",
  spent_line: null,
};

/** An ordinary install: not marked, demo mode. */
export const sandboxBlocked: OttoSandboxSection = {
  ...sandboxOff,
  switch: { label: "Sandbox research", on: false, can_turn_on: false, blocked_reasons: [NOT_MARKED, "It needs isolated mode. Docker is not running."] },
  status_line: "Sandbox research is off, and can't be turned on here.",
};

/** On; Live Otto is off, so the tick can't be set. */
export const sandboxOn: OttoSandboxSection = {
  ...sandboxOff,
  switch: { label: "Sandbox research", on: true, can_turn_on: true, blocked_reasons: [] },
  by_itself: { ...sandboxOff.by_itself, blocked_reason: "This can be ticked only while Live Otto is on." },
  status_line:
    "Sandbox research is on. The app looks for published weaknesses by itself. Designing and proving a test starts on a click (Design and prove tests, on Advisories).",
  spent_line: "0.00 of 10.00 US dollars spent on research runs in the last 24 hours.",
};

/** On, Live Otto ready: the tick can be set. */
export const sandboxOnLive: OttoSandboxSection = {
  ...sandboxOn,
  by_itself: { ...sandboxOff.by_itself, can_turn_on: true, blocked_reason: null },
};

/** On, and designing and proving by itself. */
export const sandboxByItself: OttoSandboxSection = {
  ...sandboxOnLive,
  by_itself: { ...sandboxOnLive.by_itself, on: true },
  status_line:
    "Sandbox research is on. The app looks for published weaknesses by itself, and designs and proves tests by itself within the spending limits. Every proposal waits for your Accept.",
};

export const settingsWith = (sandbox: OttoSandboxSection, live = false): OttoSettingsView => ({ ...(live ? ottoLiveOn : ottoInstalledTwo), sandbox });
