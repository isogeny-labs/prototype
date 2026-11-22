import type { WatchItem, WatchListView } from "../api";

/** Sandbox research (prototype): the Watch list as the backend sends it. The words are the backend's. */
export const ITEM = "CVE-2024-23342~python-ecdsa";
export const FIXED_ITEM = "CVE-2021-43572~starkbank-ecdsa";
const PUBLISHED = {
  key: "published" as const,
  label: "Published",
  meaning: "Said by the library's maker or a published standard. The app has not measured it.",
  note: "Said by the publisher, as the source gives it. The app has not measured it, and it does not say that the fix works.",
};
const STOP = {
  label: "Stop watching",
  reason_label: "Reason (optional)",
  max: 300,
  note: "It stays on the record and can be watched again. Nothing about the weakness changes.",
  can: true,
  blocked_reason: null,
};
export const QUOTE_TAG = "quoted from the named source, not a result";

export const noFix: WatchItem = {
  key: ITEM,
  id: "CVE-2024-23342",
  title: "Minerva timing attack on P-256 in python-ecdsa",
  library: "python-ecdsa",
  yours: "Your version is named: python-ecdsa 0.13.2, which your file lists.",
  status: { key: "no_fix", word: "No fix yet", tone: "warn" },
  status_line: "No fix published for 670 days.",
  since: "First seen here on 22 November 2026, 09:12 UTC.",
  new: true,
  source: PUBLISHED,
  panel: {
    ids_line: "CVE-2024-23342, also known as GHSA-WJ6H-64FC-37MP.",
    published_line: "Published on 22 January 2024.",
    quote: {
      title: "What the publisher says",
      lines: [
        "Minerva timing attack on P-256 in python-ecdsa",
        "python-ecdsa has been found to be subject to a Minerva timing attack on the P-256 curve.",
      ],
      tag: QUOTE_TAG,
      source_line: "GitHub Advisory Database, read on 22 November 2026.",
      url: "https://osv.dev/vulnerability/GHSA-wj6h-64fc-37mp",
      link_label: "Open the record at its source",
    },
    versions: {
      title: "The versions it names",
      lines: ["Every version. No fixed version is named."],
      yours: ["Your version is named: python-ecdsa 0.13.2, which your file lists."],
    },
    test: null,
    history: {
      title: "History",
      lines: ["First seen here on 22 November 2026, 09:12 UTC, with no fixed version named."],
    },
    stop: STOP,
    watch: null,
  },
};

export const fixPublished: WatchItem = {
  key: FIXED_ITEM,
  id: "CVE-2021-43572",
  title: "Demo data: Improper Verification of Cryptographic Signature in starkbank-ecdsa",
  library: "starkbank-ecdsa",
  yours: "Your version is named: starkbank-ecdsa 2.0.0, which your file lists. Fixed in 2.0.1.",
  status: { key: "fix_published", word: "Fix published", tone: "neutral" },
  status_line: "Fixed in 2.0.1, first seen here on 23 November 2026, 09:12 UTC.",
  since: "First seen here on 22 November 2026, 09:12 UTC.",
  new: true,
  source: PUBLISHED,
  panel: {
    ids_line: "CVE-2021-43572, also known as GHSA-92VM-MXJF-JQF3.",
    published_line: "Published on 10 November 2021.",
    quote: null,
    versions: {
      title: "The versions it names",
      lines: ["Every version before 2.0.1. Fixed in 2.0.1."],
      yours: ["Your version is named: starkbank-ecdsa 2.0.0, which your file lists. Fixed in 2.0.1."],
    },
    test: {
      line: "A test can now be designed and proven (Design and prove tests, on Advisories).",
      link: { page: "advisories", item: null },
      link_label: "On Advisories",
    },
    history: {
      title: "History",
      lines: [
        "First seen here on 22 November 2026, 09:12 UTC, with no fixed version named.",
        "23 November 2026, 09:12 UTC: the source names a fixed version: 2.0.1.",
      ],
    },
    stop: STOP,
    watch: null,
  },
};

export const stopped: WatchItem = {
  ...noFix,
  status: { key: "not_watched", word: "Not watched", tone: "neutral" },
  status_line: "No fix yet.",
  new: false,
  panel: {
    ...noFix.panel,
    history: {
      title: "History",
      lines: [
        ...noFix.panel.history.lines,
        "22 November 2026, 10:00 UTC: You stopped watching it (We do not sign with it.).",
      ],
    },
    stop: null,
    watch: { label: "Watch again", can: true, blocked_reason: null },
  },
};

const LOOK = {
  button: "Look now",
  can: true,
  blocked_reason: null,
  box: {
    title: "Look now?",
    lines: [
      "Asks OSV (osv.dev), a public database of published advisories, about the libraries this assessment names.",
      "What is sent: these package names, and nothing else: ecdsa (PyPI) and starkbank-ecdsa (PyPI).",
      "No version, no address and no file leaves this computer.",
      "Looking is free: Claude is not asked, nothing runs, and nothing is proposed by looking.",
    ],
    confirm: "Look",
    cancel: "Cancel",
  },
};
const NOTE =
  '"Fix published" repeats the publisher\'s statement, as the source gives it. It is not a result. A test for it is designed and proven on public copies before anything is proposed, and every proposal waits for your Accept.';

export const watchOff: WatchListView = {
  on: false,
  off_line: "The Watch list belongs to Sandbox research, which is off. It is turned on in Settings.",
  title: "Watch list",
  intro: "Published weaknesses in the libraries your files name that have no fix yet.",
  looked_line: null,
  next_line: null,
  look: null,
  count_line: null,
  items: [],
  stopped: [],
  empty_line: null,
  note: null,
};

export const watchEmpty: WatchListView = {
  ...watchOff,
  on: true,
  off_line: null,
  looked_line: "Not looked at yet.",
  next_line: "It is looked at again by itself, about once a day.",
  look: LOOK,
  empty_line: "Nothing is on the Watch list yet. Look now reads what has been published about your libraries.",
  note: NOTE,
};

export const watchOne: WatchListView = {
  ...watchEmpty,
  looked_line: "Looked on 22 November 2026, 09:12 UTC by You.",
  count_line: "1 published weakness in your libraries has no fix yet.",
  items: [noFix],
  empty_line: null,
};

export const watchTwo: WatchListView = {
  ...watchOne,
  looked_line: "Looked on 23 November 2026, 09:12 UTC, by itself.",
  count_line: "1 published weakness in your libraries has no fix yet and 1 that was watched has a fix published since.",
  items: [fixPublished, { ...noFix, new: false }],
};

export const watchStopped: WatchListView = { ...watchOne, count_line: null, items: [], stopped: [stopped] };

const CLOSED = "This assessment is closed. Its Watch list stands as it was when it was signed off.";
export const watchClosed: WatchListView = {
  ...watchOne,
  next_line: CLOSED,
  look: { ...LOOK, can: false, blocked_reason: CLOSED },
  items: [{ ...noFix, new: false, panel: { ...noFix.panel, stop: { ...STOP, can: false, blocked_reason: CLOSED } } }],
};
