# Design refactor: the report

For Kevin. Written 26 November 2026, after the build. The plan this follows is `docs/plans/design-refactor.md`.

**Nothing is merged.** The work is on the branch `claude/amazing-planck-e90m60`, in pull request 18, and it stays there until you say so.

## In one paragraph

Everything you approved today is built, with a short list of smaller items left for later (they are named below). A result, an advisory and a fix now each open short: the answer, then what it shows and doesn't, then one dropdown that holds every record whole. The sidebar is a path of six numbered steps, and observing is its own step with a new page, the Observatory, which draws your systems as a map. Evidence is a section of four views, not one screen, and it now records who pressed every button that decides or changes something. No result, check, rule or answer key was changed.

## What you will see

### 1. Every proof opens short, and the proof is one click away

A result's panel used to be one long column with everything open. Now it reads in three layers, always in the same order:

1. **At a glance.** The result word, one plain sentence, where it ran, the control, and the next step with its button.
2. **What this shows, and what it doesn't.** Always open.
3. **One dropdown**, shut until you click it. It is called **Cryptanalysis proof** when something was tested on a copy, and **Technical record** when it was observed or only read from your file. It holds every record whole: nothing was left out, it is one click away.

The same three layers are on an advisory's panel and on a fix's panel. On a library's fix the two proof rows keep their exact words ("Proven on public copies", "Proven in this assessment"), drawn as step 1 and step 2, with the note under the second.

Pictures: PICTURES_LAYERS

### 2. The sidebar is a path

Overview, then **1 Bring in** (Import), **2 Observe** (Observatory, Verify), **3 Test** (Advisories, Checks), **4 Fix** (Fixes), **5 Plan the move** (Migration plan), **6 Keep watching** (Change watch), and then **Evidence** with its four views. Every page is listed once. The four work groups are tabs on their page and no longer repeated in the sidebar, so "Migration" and "Dependencies" never appear twice.

Each tab now says how many items it holds and how many are findings ("Crypto tests 5 · ✕ 3 failed"). On Results and Fixes the rows come in labelled parts: **On your systems**, **On copies on this computer**, **Said by the maker**, **Only in your file**, and **No result yet**.

Pictures: PICTURES_SIDEBAR

### 3. The Observatory: your systems as a map

A new page under step 2. It draws the service your scanner file describes, the parts it is made of, where each part uses cryptography, and what each check found there, in the check's own words. Lines show what uses what, and the one connection the app itself made. Before anything is checked the map is drawn from the file alone and says so; it fills in as checks run. Under it is a list of what your files don't say. A box opens a panel with its checks, its fixes and the lines of the file that name it. There is also a List view of the same thing, for a screen reader or for printing.

It is not a result and not a score, and it starts nothing.

Pictures: PICTURES_OBSERVATORY

### 4. Evidence is the full record

You asked whether Evidence only took the latest run. Every run was always kept, but the page showed only the newest result of each check, and approvals, decisions and downloads were spread over five pages. Now Evidence has four views:

- **Timeline.** Everything that happened, newest first, by day. One entry for one press: "Run all: the 5 tests in the plan", with the results counted. You can filter by page (Where) and by kind (What), and search. An entry opens its story: who, the runs it started, what it rested on, what came after.
- **Results.** The page that was called Evidence. It has a new switch, **Now** or **By version**, which puts every test on every version it ran on side by side.
- **Approvals and decisions.** Every decision a person made, with who and when. Results are not in this list, and the page says why: no person decides a result.
- **Evidence files.** Every download with its fingerprint and who downloaded it, and how to check a file.

Every panel has **History of this** check, fix, system or advisory. Checks, Advisories, Fixes, Migration plan and Dependencies each have **History of** that page in their header.

Pictures: PICTURES_EVIDENCE

### 5. Who did what

Every press that decides or changes something is now recorded: who, when, which button and what it started. The name comes from one place: the logged-in account where the app has one, otherwise the name typed in Settings (Who decides), otherwise "You". These records are also in the signed evidence file, and the verify command checks them. A record made before today says "Not recorded (before names were kept)". Nothing is filled in after the fact.

A result never shows a person as its decider. Every run says "decided by the separate reviewer".

### 6. Calmer pages

Advisories opens with four numbers and then the list; its background lines are folded into one line. On Checks, an empty part (no retest yet, no fix proof yet) is one folded line. Panel titles have a line to themselves, so they no longer break one word per line.

## What the plan named that I did not build

These are smaller items. Each is listed in the SPEC as not built, so nothing claims otherwise.

| The plan said | What is there instead |
|---|---|
| The test plan on Checks drawn in two parts, by where each test runs | Each test says where it runs, in one line ("On your server, localhost:8443" or "On a copy of acme-sign 1.4.2, on this computer"). The list itself is not split. |
| "Why it matters" opening under a row | It stays on the row, as before. |
| The two research buttons in the Advisories header | They stay in the New advisories block, as before. |
| On the Overview: three cards for the three questions, a small copy of the map, one count by tag | The Overview is as it was, with a new link to the map. The Observatory has the four counts. |
| The three layers on a change of Change watch | Its panel is as it was. |
| Three shapes of label (result, what it rests on, where it came from) | Only the tag at the head of each part. The labels themselves look as before. |
| Links that jump to a part inside the dropdown | Not built. |
| The second author's asking code on a switch beside the first | It stays under the first, as before. |
| Numbers on the sidebar (proposals waiting, open fixes) | Not built. |
| "What it shows" and "what it doesn't" in two columns | One block, as before. |
| The trail on every panel | It is on a result, an advisory and a fix. Not on a system, a library or a claim. |
| "Show on the map" on every result | It is on the results of a server or a signing program on the Results page. |
| The map in the downloadable report | Not built (the plan had already left this out). |

I left these out to keep the build to what could be tested properly today. None of them changes a result. Tell me which you want and I will plan them.

One more thing to know: the Otto panel still calls the Results page "Evidence" in its sentences. The address did not change, so every old link still works.

## How it was checked

CHECKS

## What the independent review found

A separate reviewer read the whole build against the SPEC and your rules. It reported 13 findings. None was about a wrong result. What it found, and what was done:

REVIEW_TABLE

It also confirmed what it found sound: the answer keys, the reviewer, the wireframes, the research data and the package lists are untouched; no new network call; no "secure", score or severity in any new text; folding dropped no record; the new reads write nothing; the two new tables are add-only and have one writer; an older evidence file still verifies.

## What I need from you

1. Look at the pictures, or run the app (`./run-demo.sh`), and tell me what you want changed.
2. When you are happy, tell me to merge. I will not merge before you say so.
