# Design refactor: evidence a busy security engineer can read at a glance

**Status: a plan and mockups only. Nothing is built.** Round 1 written 25 November 2026. Round 2 written 26 November 2026, after Kevin's answers; it waits for his OK. No app code, result, rule, answer key or reviewer was changed to make it.

## Round 2: your answers, and what I added

**Decided by Kevin on 26 November 2026.**

- **A. Yes:** three layers, with every record folded whole under one dropdown.
- **B. Yes:** the dropdown is called **Cryptanalysis proof** for what was tested, and **Technical record** for what was only observed.
- **C. Yes:** a numbered sidebar. Round 2 adds one step to it, Observe, so it has six steps (decision F below).

**D and E in plain words. Neither needs a decision from you.**

- **D, "SPEC edits".** `docs/SPEC.md` is the written description of every screen and button the app is allowed to have. Your own rule in `CLAUDE.md` says nothing new goes on screen unless it is written there or you have said OK. So once you approve a design, that description is rewritten to match it. It follows from your yes. I will show you the changed paragraphs together with the build plan, so you can see that nothing else slipped in.
- **E, "small additions outside the screens".** Almost all of this redesign moves around what the app already shows. A few details need the app to hand the screen its words in a slightly different shape. For example, today "What this shows" and "What it doesn't" arrive as one list, so to put them in two columns side by side, the app would have to send two lists. No result changes. I am taking my own recommendation: move things around first, and add these small details afterwards, one at a time.

**Your new idea: observing apart from testing, and a map of your systems.** My answer as the designer, in short. Section 5 has the whole design.

- **Yes. Observing and testing become two separate steps, and observing gets its own section, the Observatory.** An observation says what your running system does today. A test says what a piece of software does when we try it on a copy. They lead to different actions, so they should not be mixed in one list.
- **The Observatory's main view is the map you asked for:** your systems as your files describe them, where the cryptography is in them, and what each check found there. It is drawn as soon as a file comes in, and it fills in after every check, observed or tested.
- **The map draws only what your files and checks show.** Where your files are silent (which software answers on an address, who connects, what data flows where), it lists the gap under the map instead of guessing.
- **What I would not do:** split the four work groups, or keep two copies of a result. Evidence stays the one complete record, because it is what the signed evidence file holds. The map shows each finding on the system it belongs to and opens its record.

The map after the checks have run, and a system opened from it:

![The Observatory's map after the checks have run](design-refactor/mockups/11-observatory-map-dark.png)

---


## The plan on one page

**The problem.** The product's promise is: prove your crypto continuously, with evidence a busy security engineer can read. Today the proof screens are written for a cryptographer and shown to the engineer. Two examples, measured on the app's own screenshots:

- **A test result on Evidence opens 4,265 pixels tall** at 1440 pixels wide. That is nearly five screens, all of it open at once: the answer, the technical summary, the table of cases, the run record, the locked test, the control, the advisory, where the check came from, the fix. Nothing says which of those is the answer.
- **A proposed check on Advisories writes the same three counts five times** ("1 of 64 wrong, none wrong, the control failed"): three times in the open and twice more inside its proof. Its proof is already behind a fold today, but opened it is 4,053 pixels of paragraphs in a single column.

**What I propose, in six changes.**

1. **Three layers for every proof.** First the answer in plain English. Then what it shows and what it doesn't. Then one dropdown, folded shut, that holds every record a cryptographer or an auditor wants, whole: the published cases, the control, the locked test, the run record, the code, the fingerprints. It is called **Cryptanalysis proof** where something was tested and **Technical record** where it was observed. The same three layers on every result, every proposed check and every fix.
2. **Observe and test, apart.** Two steps in the sidebar. On Checks, Evidence and Fixes every list comes in two labelled parts: what was observed on your systems, and what was proven on copies. A new page, the **Observatory**, draws a map of your systems that shows where the cryptography is and fills in with every check.
3. **One tab strip, the same everywhere.** The four work groups stay as they are. Each tab gains a count and says how many findings it holds. The sidebar stops repeating the tabs.
4. **A sidebar that tells the story.** Six numbered steps: Bring in, Observe, Test, Fix, Plan the move, Keep watching. Ten entries where there are up to seventeen today.
5. **One fixed place for each kind of label.** The result, what it rests on, and where it came from stop competing for the same spot.
6. **Calm pages.** Every page in the same order: title, a few numbers, the table, and the detail in a side panel.

**What it does to the two examples.** The same test result opens at 1,195 pixels in the mockup, with every record one click away. The proposed check says its counts once in the open and once, as a table, inside the proof.

**What does not change.** No result, no check, no test, no rule, no answer key, no evidence file. The reviewer is not touched. Every product rule in `CLAUDE.md` stands: no "secure", no score, no severity, plain words. No record is shortened: what is folded is shown whole when opened.

**What I need from Kevin.** Two decisions on round 2, F and G, in [section 10](#10-decisions-for-kevin).

**See it first.** All the pictures are in [section 9](#9-the-mockups). For the three layers, the one that shows the idea fastest is the same result, as it opens today and as it would open:

![Before and after: one result, as it opens](design-refactor/mockups/compare-result-proof-dark.png)

---

## 1. Why: who uses this and what they decide

**The user** is one security engineer at a company that handles payments or sensitive data. They are busy and they are not a cryptographer (SPEC, "Why this exists"). They open the app with three questions, always in this order:

| Their question | What answers it | Where it sits in the new layout |
|---|---|---|
| **What did you find?** | The reviewer's word (Passed, Failed, True, False) and one plain sentence | Layer 1, top of every panel |
| **Can I trust that?** | What it rests on (observed on my system, or proven on a copy), and that the test caught a deliberately broken program | Layer 1 says it in two lines. The full record is one click away in layer 3. |
| **What do I do next?** | The fix, or the decision that waits for me | The bottom line of layer 1, with its one button |

**The second reader** is the person the engineer has to convince: an auditor, or a cryptographer on their own team. That reader wants the opposite: every case, the control, the exact code, every fingerprint. Today's screens are built for this second reader and shown to the first. The redesign keeps everything the second reader needs, whole, in one named place, and stops making the first reader wade through it.

**How this serves "proof, continuously".**

- *Proof* is never more than one click away, and it is always in the same place under the same name. That consistency is what makes it believable: the engineer learns once where the proof lives.
- *Continuously* shows in three things. The map of your systems fills in with every check, so the user watches the picture of their own system change. A short line of links at the top of every panel (claim, advisory, check, result, fix) shows where this item sits in the loop; this plan calls it the trail. And the sidebar's last step is "Keep watching".
- *Readable* means the first screen of any item answers the three questions.

**The business case.** The demo has to land in five minutes (SPEC). Today a presenter who opens a result gets nearly five screens at once. One who opens a proposed check's proof to show it has to scroll through four screens of fingerprints and code to get back to Accept. After the change the demo is four beats: here is the finding, here is why you can trust it, click here to see the cryptanalysis, here is the fix. The same screens also put the honest limits ("what this does not show") where a technical buyer will see them, and that is what earns their trust.

---

## 2. The journey, and where it is confusing today

**The journey in five steps.**

| Step | Pages | What the user does | What they leave with |
|---|---|---|---|
| 1. Bring in | Import | Upload the scanner's file, and the dependency list if there is one. | A map of their systems, drawn from the files |
| 2. Observe | Observatory, Verify | Look at the map. Check each claim against the real system. | True, False or Couldn't check for every claim, shown on the map |
| 3. Test | Advisories, Checks, Evidence | Accept or reject proposed checks. Run the tests. Read what each one found. | A result for every test, each with its record |
| 4. Fix | Fixes | See the fix for each finding and its proof. Approve, merge or apply. | A fix that is proven before it is offered |
| 5. Plan the move | Migration plan | See where each system stands on post-quantum and what must change. | A plan with measured costs |
| 6. Keep watching | Change watch | See what a developer's change, or a newly published weakness, means for all of the above. | The loop starts again |

**Where today's flow loses people.** Each point is taken from the current screens.

1. **The sidebar is a list, not a path.** It shows up to seventeen entries inside one assessment with no sign of order. When Evidence is open, the words "Migration" and "Dependencies" each appear twice in the sidebar at the same time: once as tabs of Evidence and once as the Migration pages. (See `docs/screenshots/group-tabs/evidence-2-encryption-panel-open-light.png`.)
2. **Two ways to do the same thing.** The four work groups are tabs on the page and also entries in the sidebar. Migration's three views (Systems, Roadmap, Dependencies) are tabs on the page and also entries in the sidebar. A user cannot tell whether these are the same thing.
3. **Checks and Evidence look like the same page.** Both list the same items in the same four groups. The difference (Checks is what runs; Evidence is what it showed) is not visible in the layout.
4. **One finding lives on four pages, and the links between them are at the bottom.** The Related block that ties a claim to its check, result and fix sits at the very end of the longest panels. On the result pictured above it is about 4,000 pixels down.
5. **Panel titles are crushed.** The buttons "Open in new tab", "Wider", "Narrower" and × share a line with the title and take most of it. Titles break one or two words per line. On the Watch list a title runs to eight lines (`docs/screenshots/sandbox/06-watch-list-the-item-open-dark.png`).
6. **On Advisories the list starts far down the page.** Background text comes first: the standing line, the installed packs, where answers were recorded, the harness version, the waiting count, and the New advisories block with its run report and a long paragraph on what the loop covers. The table of advisories begins about 1,200 pixels down, on the second screen (`docs/screenshots/sandbox/13-the-proposal-how-this-test-was-proven-dark.png`).
7. **"Verify" and "Verification" are different things with nearly the same name.** Verify is the page where claims are checked. Verification is the tab that lists those checks.
8. **Nothing shows the user's own system.** Every page is a list of checks. The scanner file describes a service and what it is made of, and the dependency list adds the parts and libraries inside it, but no page draws that. The difference between "seen on my server" and "proven on a copy" is a small tag on each row.

**What fixes each of these** is in sections 3, 5 and 6. In short: a six-step sidebar (1, 2), one sentence that separates Checks from Evidence and different columns for each (3), the trail at the top of every panel (4), a panel header where the title has the full width (5), a calm Advisories page (6), the group's own question shown under the tab (7), and the Observatory with its map (8).

---

## 3. Tabs and tags: the cleanest structure

### The four work-group tabs

**My finding: the four groups are right. The trouble is around them.** Verification, Crypto tests, Migration and Dependencies are the same names in the same order on Checks, Evidence, Fixes and the Overview. That is worth keeping exactly. What I would change:

| Today | Proposed | Why |
|---|---|---|
| A tab shows its name. Only while a search or a filter is on does it also show how many of its rows match. | A tab always shows its name, how many items it holds, and how many of them are findings: "Crypto tests 6 · ✕ 4 failed". While a search or a filter is on, the number is the matching rows, as today. | The user sees where the findings are before clicking. |
| The group's question and its counts sit in a separate strip, and four summary cards sit above the tabs. | One band under the tabs holds the group's question ("Is the cryptography built right?"), its Open, In progress and Done counts, and its numbers. | One place to look. The numbers belong to the open tab, so they sit under it. |
| The sidebar repeats the four groups under whichever page is open. | The sidebar does not repeat them. | One way to move between groups, not two. It also removes the doubled "Migration" and "Dependencies". |
| The sidebar entry is "Migration"; the page it opens is titled "Migration plan". | The sidebar entry is "Migration plan" too. Its three views stay as tabs on the page only. | "Migration" then always means the work group, and "Migration plan" always means the page. |
| Checks and Evidence show near-identical tables. | Checks has the columns of a to-do list: test, runs on, latest result, Run. Evidence has the columns of a record: test, result, fix, last run. Each page says its role in one sentence under the title. Inside every tab, both come in two labelled parts: on your systems, and on copies (section 5). | The two pages stop looking like copies. |

**The numbers on a tab are the page's own counts and decide nothing.** They are counted the way the page already counts. Anything the rules keep out of every count stays out: on Fixes, the entry that comes from Change watch is counted nowhere today and would not be counted on a tab either.

![The proposed tabs on Evidence](design-refactor/mockups/03-evidence-tabs-light.png)

The same strip on Checks, with the test plan as compact rows ("Why it matters" opens under a row, shown here on the first one):

![The proposed tabs on Checks](design-refactor/mockups/02-checks-tabs-dark.png)

On the Overview the four groups stay side by side as four cards, as today, each with its question and its counts in the reviewer's words (picture in section 9).

### The source tags and the other labels

**Are four source tags too many? No.** Observed live, Proven in the lab, From your file and Published each answer a different question, and Kevin approved their words and colours on 22 November. They stay exactly as they are.

**The real problem is that every label looks alike and sits wherever it fits.** One fix on today's Fixes page opens with four pills of the same shape (Proven in the lab, Ready for review, From a fix template, Demo data). The proposal is three kinds of label, each with its own shape and its own fixed place, and at most one of each on a row:

| Kind | What it tells you | Shape | Fixed place | Examples |
|---|---|---|---|---|
| **1. The result or status** | What the check decided, or where a fix stands | A filled pill with a symbol. The loudest thing on the row. | The Result column in a table. Top left of the summary in a panel. | Passed, Failed, True, False, Measured, Proposed, Ready for review |
| **2. What it rests on** | Whether it was observed, tested on a copy, read from the file, or published | A quiet outlined pill with a small picture (a signal, a flask, a page, a quote mark) | The heading of the part of the list it sits in ("On your systems", "On copies on this computer"). Beside the result in a panel. | Observed live, Proven in the lab, From your file, Published |
| **3. Where it came from** | Who or what produced the item | A small square label after the name | After the item's name | From Otto, Demo data, New, Sandbox copy, Written by Otto |

In round 1 the tag had a column of its own. Round 2 does better: each list is split into labelled parts by what its results rest on, so the tag is said once, at the head of its part, with one line on what it means. A part is a heading, not a filter: every row is still on the page, and there is no filter by source, as the SPEC says.

The many small tags inside the evidence ("measured", "demo", "reference", "assumed", "from the file") keep their words and stay on the facts they label. Those facts are in the Cryptanalysis proof, so the small tags no longer sit next to the answer.

---

## 4. The layered proof (the centrepiece)

### What happens today

- **A result on Evidence** is one long column with everything open. Nothing is folded.
- **A proposed check on Advisories** already folds "How this test was proven". But the same counts are written three times above the fold as well, and inside the fold everything is paragraphs in one column.
- **A library's fix on Fixes** states the update six times and its two proof rows three times.

So the app already has folds. What it lacks is one rule for what goes above the fold and what goes below it. That rule is the proposal.

### The pattern

Three layers, always in this order, with the same names and the same position on every screen that shows a proof.

| Layer | What it is | What it holds | Open or folded |
|---|---|---|---|
| **1. At a glance** | The answer, for the security engineer | The result and what it rests on. One plain sentence. Two short lines: where it ran, and the control. The next step with its one button. | Always open |
| **2. What this shows, and what it doesn't** | The honest limits | The app's own lines on what the result shows and what it does not. | Always open |
| **3. Cryptanalysis proof** | The deep record, for the cryptographer and the auditor | Every record, whole: the technical summary, the published cases and the answers given, the control, the test as it was locked before the run, the run record, the code, the fingerprints and the ledger entries. | **Folded.** One click opens it. Its header says what is inside. |

This is also what the SPEC already asks of a result: "one plain sentence... with the technical text and the evidence folded under it". Today's Evidence panel shows the technical text and the evidence open. The pattern puts them where the SPEC says.

Inside the Cryptanalysis proof the parts are numbered, each has a plain heading, and short links at the top jump to each. A list that has columns becomes a table. The heaviest parts (the list of frozen files, the ledger entries, the second author's code) stay folded one level further, as they are today.

### Where the pattern applies

| Place | Layer 1, the answer | Layer 3, the Cryptanalysis proof |
|---|---|---|
| A test result on Evidence | The reviewer's word, the plain sentence, where it ran, the control line, the fix line | What happened in technical words, the control, the locked test, the run record, the advisory, where the check came from |
| A proposed check on Advisories ("How this test was proven") | Why it applies, the test's status with its reason, three counts (affected version, fixed version, the control), what it does not show, Accept and Reject | The test, the trial part by part, what was frozen before the first run, the code that asked the library, the public copies, the records |
| A library's fix on Fixes | What is proposed and why, the **two proof rows** with the note under the second, who approves, Accept and Reject | The suggestion in full, the advisory, the ledger entries |
| A code fix's proof on Fixes | Proof passed or failed, and the one-sentence summary | The table of every test rerun on the changed code, the commits and fingerprints |
| A change on Change watch | The status ("Passed before, fails now"), the plain sentence | The picked tests and the rule that picked each, before and now, the diff |

### Mockup: a test result, collapsed and expanded

Collapsed. The engineer's whole answer is on one screen:

![A result with the Cryptanalysis proof collapsed](design-refactor/mockups/04-result-proof-collapsed-dark.png)

Expanded. Every record from today's screen is here, whole, in six numbered parts:

![A result with the Cryptanalysis proof expanded](design-refactor/mockups/05-result-proof-expanded-dark.png)

### Mockup: a proposed check ("How this test was proven"), collapsed and expanded

Collapsed. Why it applies, the three counts that matter, what it does not show, and the decision:

![A proposed check with the Cryptanalysis proof collapsed](design-refactor/mockups/06-test-proof-collapsed-light.png)

Expanded. The trial as a table, the frozen record, the code that asked the library, the public copies:

![A proposed check with the Cryptanalysis proof expanded](design-refactor/mockups/07-test-proof-expanded-dark.png)

Opened, the proposed check is about as long as it is today, on purpose: nothing was left out. The difference is the order. Today's proof opened, beside the mockup opened the same way:

![Before and after: one proposed check, both opened](design-refactor/mockups/compare-test-proof-dark.png)

### Mockup: a fix with its two proof rows

The two rows keep their exact words ("Proven on public copies", "Proven in this assessment"), and the note that says what the second row is about stays right under it, as the SPEC requires. They become a two-step ladder, so it is plain that the second step is still to do:

![A fix with its two proof rows](design-refactor/mockups/08-fix-two-proof-rows-light.png)

### The fluff to cut

I sorted what repeats into three kinds, because they are not the same decision.

**Kind A: drawn twice today, drawn once after.** These are true cuts on the screen. Each is a second copy of something that stays. No record loses anything.

| # | Where | What is drawn twice today | What stays |
|---|---|---|---|
| A1 | A proposed check | The trial's three counts as a bullet list ("How it did when tried on public copies") and again as the rows of "How this test was proven". | The table, inside the dropdown. Where an advisory has only the bullet list (a test tried on our pinned copies), the list stays. |
| A2 | A proposed check | The test's question, its cases and its control: once under "The test", and again as the proposal's own bullets. | "The test", inside the dropdown. The proposal keeps its bullets on pages where it stands alone. |
| A3 | A proposed check | "Accepting adds the check to the test plan and runs nothing": above the proposal and again under its buttons. | The sentence under the buttons. |
| A4 | A library's fix | The two proof rows: as a bullet in the proposal, as the two rows, and again as sentences. | The two rows in the open. The sentences stay inside "The suggestion", in the dropdown, because that text is one record. |
| A5 | A library's fix | The fix's title, written again as the proposal's own title directly under it. | The panel's title. |
| A6 | A library's fix | "This is other people's code: the app offers no code change and no pull request": as a bullet and again under "What it suggests". | Once, in the open. |
| A7 | Advisories | The standing line "Passing these tests doesn't prove a system secure..." at the top of the page and again at the foot of the panel. | Once on every screen, as a quiet line. Every page that has it today keeps it. |
| A8 | Every panel | Boxes inside boxes: the page, the block, the card, the proof, the list. Up to five levels of border. | Two levels at most. Spacing and thin lines do the rest. |

**Kind B: said in the open today, moved into the dropdown.** Nothing is cut. It is one click away, whole.

| # | Where | What moves into the Cryptanalysis proof |
|---|---|---|
| B1 | A result | The "Technical summary" line and "What happened". They are the technical telling of the plain sentence. They become part 1. |
| B2 | A result | The table of wrong cases, the run record and the locked test, each whole. |
| B3 | A result | The "Control" paragraph. One line about the control stays in the open, moved from under the title into layer 1. |
| B4 | A result | The advisory box and "Where this check came from", each whole, with its own note. |
| B5 | A proposed check | "The test": its question, cases, control, pass rule and design fingerprint. |
| B6 | A proposed check | The two quoted version lines (`"introduced": "0"` and `"fixed": "2.0.1"`), folded into one line. The publisher's own sentence stays in the open with its caption. |
| B7 | A library's fix | "The suggestion" in full, and the advisory it answers. |
| B8 | Advisories, the page | The lines about installed packs, recorded answers and the harness, and the paragraph on what the loop covers: folded into one line, "Where this page's facts come from", directly above the list. |
| B9 | Checks | Each test's "Why it matters": it opens under the row. |

**Kind C: the same fact worded twice by the app. Not in this plan.** These would shorten the screens further, but the screens cannot tell that two differently worded sentences say the same thing. Cutting one means changing which sentences the app writes, and that is more than presentation. I list them so you can decide later; this plan leaves all of them as they are.

| # | The pair |
|---|---|
| C1 | "Test ready: tried on public copies before this pack was signed..." and "Tried on public copies of starkbank-ecdsa fetched from PyPI...": the same three counts in two sentences. In the mockup the first is in the open and the second opens the trial inside the dropdown. |
| C2 | Three notes that the result comes only from the test, each worded differently, one on each block of a result. |
| C3 | "Update the library, then press Retest." and "To prove it here: whoever owns the software updates it; then press Retest new version..." on a library's fix. |
| C4 | The plain sentence and the "Technical summary" of a result, where the second adds only the number of the first wrong case. |

**After A and B, the five copies from the top of this plan become two:** one in the open (a sentence, with its three counts drawn under it) and one inside the dropdown (a sentence, with the full table under it).

### What to keep

Everything that carries a fact stays. In particular:

- The reviewer's word and the one plain sentence, unchanged.
- "What this shows, and what it doesn't" and "What this does not show". These are the product's honesty. They stay in the open, not behind the fold.
- The control line. It is the shortest answer to "can I trust this?", so it stays in layer 1. It gets a plain mark, not a tick: a tick would read as a second result.
- The source tag and its one sentence ("Run on a copy... Your live system was not touched").
- Every record, whole: the locked test with all its fields, the run record with its full summary, the ledger entries, the decisions, the quoted lines, the code.
- The exact sentences the rules require: that the screen of the asking code is "a filter for mistakes and plain tricks, not a proof"; that a replay was "not by an outside party"; who wrote the code; whose counts are the reviewer's.
- The words the app chooses by case. The label of the fixed version is the app's own, so where the publisher named no fixed version it still says so.
- The two proof rows of a library's fix, word for word, with the note under the second row and its link to Checks.
- On an advisory's Fix block, where the fix becomes a proposal with Accept and Reject.
- Accept and Reject on each proposal by itself, with the sentence that accepting runs nothing.

### The naming rule (decided 26 November 2026)

"Cryptanalysis proof" fits where cryptography was tested against published cases with a control: test results, advisory checks, test proofs and fix proofs. For an item that was only *observed* (a handshake with your server on Verify, a migration measurement) the name would claim more than happened. For those the same dropdown sits in the same place under the name **Technical record**. This matches the source tags: "Proven in the lab" gets a Cryptanalysis proof, "Observed live" gets a Technical record. Kevin decided it on 26 November 2026 (decision B).

An observed result with its Technical record, folded and open. It also says where it sits on your map:

![An observed result, Technical record collapsed](design-refactor/mockups/13-observed-result-record-collapsed-dark.png)

![An observed result, Technical record expanded](design-refactor/mockups/14-observed-result-record-expanded-light.png)

---

## 5. Observe and test apart: the Observatory and its map

### My answer: yes, two steps, and observing gets its own section

**Why.**

- **They answer different questions.** An observation says what your running system does today: we made a handshake with it from this computer. A test says what a piece of software does when we try it on a copy, with published cases and a control that must fail.
- **They lead to different actions.** A finding observed on a server is fixed by changing that server. A finding proven on a copy is fixed by changing the software, everywhere it runs.
- **The product already has the words for it.** The SPEC says: "Live = observe; lab = test." Today that sits in a small tag on each row. Making it the structure means nobody has to read tags to see the most important difference in the app.
- **It gives the map a natural home.** The map is a picture of your systems, and observing is about your systems.

**What goes where.**

| | Observe | Test |
|---|---|---|
| The question | What do my systems do right now? | Is the software built right? |
| How | Handshakes with an address in your file that you confirmed. Nothing else is sent. | Run on a copy on this computer, with published cases and a control that must fail. |
| Pages | Observatory (new), Verify | Advisories, Checks, Evidence |
| The tag | Observed live | Proven in the lab |
| The dropdown | Technical record | Cryptanalysis proof |

**The sidebar becomes six steps:** 1 Bring in (Import), 2 Observe (Observatory, Verify), 3 Test (Advisories, Checks, Evidence), 4 Fix (Fixes), 5 Plan the move (Migration plan), 6 Keep watching (Change watch).

**What I would not do, and why.**

- **Move the two server tests out of the test plan.** Old TLS versions and Certificate strength are observations, but they sit in the one test plan with its one Run all. Moving them would give two places to start the same run. Instead the plan is drawn in two labelled parts, "On your systems" and "On copies on this computer". Evidence and Fixes get the same two parts inside each work-group tab.
- **Replace the four work groups.** They say *what question* a check answers; observe and test say *how we know*. Both stay, at two levels: the tab is the question, the part inside it is how we know.
- **Keep two copies of a result.** Evidence stays the one complete record of every result, observed or tested, because it is what the signed evidence file holds. The Observatory shows each result where it belongs on your system, in the checks' own words, and opens its record.
- **Put Verify under Test.** Verify checks your file's claims, and most of them are about live systems, so it sits under Observe. A claim about a signing program is checked on a copy, and its tag says so ("Proven in the lab").

Evidence, with its two parts inside the Crypto tests tab:

![Evidence with observed and tested results in two parts](design-refactor/mockups/03-evidence-tabs-light.png)

### The map

**What it shows, and where each piece comes from.** Every box and every line on it comes from your files or from a check. In the demo:

| On the map | Where it comes from |
|---|---|
| **The boxes:** your service and the parts it is made of | Your scanner file names the service (Acme Pay token-signing service) and what it contains: a token-signing endpoint and acme-sign 1.4.2. Your dependency list names the same service and adds two more parts, acme-pay-server 1.0.0 and acme-ledger 5.1.0, with the libraries inside each. |
| **Where the cryptography is** | Each box lists the places it uses cryptography: the endpoint's TLS versions, certificate and key exchange; how acme-sign signs and checks signatures; each library's post-quantum answers. |
| **One algorithm in two places** | Your scanner file says the endpoint's certificate and acme-sign both use ECDSA P-256. The map draws both lines into one box, so it is plain that the same algorithm sits in two places. |
| **What each check found** | The checks' own words on each spot (True or False, Passed or Failed, Classical), and on each box the tag of what it rests on: Observed live on the endpoint, Proven in the lab on acme-sign. |
| **The lines** | A solid grey line: your files say one uses the other. A blue arrow: a connection we made, with what we saw ("TLS · 1.3 and 1.2 accepted"). A dashed line with "?": your files don't say. |

**The rule: the map draws no line it can't show from your files or a check.** Where it doesn't know, it says so under the map, in a list called "What your files don't say", with where each gap can be filled:

- which software answers on localhost:8450 (the dependency list names acme-pay-server 1.0.0 but doesn't tie it to that address; Dependencies already has **Part of** to tie them);
- which system acme-ledger 5.1.0 is part of;
- who connects to the endpoint, and which data flows between the parts (a scanner file can name data flows; the demo file names none).

That list is useful on its own: it shows the gaps in the customer's inventory, which a scanner's list never does.

**How it fills in.**

- When the file comes in, every spot reads "From your file": what the file claims, nothing checked yet. The page says so, and points to Verify.

![The Observatory just after the file comes in](design-refactor/mockups/10-observatory-just-brought-in-light.png)

- After Verify and Run all, every spot carries what its checks found (the picture at the top of this plan).
- After any later check of the assessment (a retest, Apply and the measurement right after it), the spot shows the newest result. Change watch's runs are kept apart from the assessment's own results by the rules, so they do not change the map.
- The map is drawn from the records each time the page opens. It keeps no copy of its own.

**Opening a box** opens its panel over the right side of the map: what each spot's checks found, in their own words, the next step, what your files don't say about it, and the way to each Technical record or Cryptanalysis proof.

![A system opened from the map](design-refactor/mockups/12-observatory-a-system-open-dark.png)

**From every result back to the map.** Layer 1 of every result says where it sits: "On your map: Acme Pay token-signing service › Token-signing endpoint › TLS versions", with **Show on the map**. On the Overview, a small copy of the map, "Your systems", opens the Observatory (picture 01 in section 9).

**Map and List.** A **List** view shows the same boxes and spots as a table: for a screen reader, for printing, and for an estate too big to draw. A map stays readable up to a few dozen boxes; beyond that the List is the way in and the map shows one service at a time. The mockup draws only the map.

**What the map is not.**

- **Not a result.** It repeats the checks' own words and decides nothing. There is no score, no colour that means "safe", and no overall verdict on a box.
- **Not a start button.** Looking at it runs nothing; every check is still started where it is today. One idea for later, not in this plan: a single "Observe again" button that reruns every live observation.
- **Not a scanner.** It doesn't discover systems; it draws what your files describe. About "our PQ scanner": the app has no scanner of its own today. An open-source post-quantum scanner is on the SPEC's list for later. When it exists, its file comes in like any scanner's file, and the map is drawn from it the same way.

---

## 6. Calm pages

**Every page in the same order.**

1. **The title, one sentence, and the page's one or two main buttons.**
2. **A few numbers**, counted from what the page shows.
3. **The tabs**, where the page has groups.
4. **Search and filters**, on one line.
5. **The table.** One row per item. A name, one line of plain words, the result, what it rests on.
6. **The side panel**, when a row is clicked. Never everything at once on the page.

**Every side panel in the same order.**

1. **A slim tool row**: where you are ("Result · Crypto tests"), then Open in new tab, Wider, Narrower and ×. The buttons no longer share a line with the title.
2. **The title on its own line**, at the panel's full width.
3. **The trail**: up to four short steps (claim, advisory, check or result, fix), the current one marked, each a link. It is built from the links the Related block already holds, and brings them from the bottom of the panel to the top. The Related block itself stays, folded, at the foot.
4. **Layer 1, layer 2, layer 3.**
5. **Folded lines** at the foot: earlier runs, Related, what this change touches.

**Five rules that keep a page calm.**

- **One answer per screen.** The top of a panel answers the three questions.
- **No box inside a box inside a box.** Two levels of border at most.
- **Text no wider than a comfortable line** (about 70 characters), so a sentence reads in one glance.
- **Tables for anything with columns.** The trial's six parts and the wrong cases are tables, not stacked paragraphs.
- **A fold is only a fold.** It opens on a click and holds whole records. Nothing clever.

**What this does to three busy pages.**

- **Advisories.** Four numbers and the top of the list are on the first screen. A row's panel opens on the proposal and its decision. (Mockup 06.)
- **Checks.** The test plan is a compact table. Retests and fix proofs are single folded lines until there is something in them. (Mockup 02.)
- **Overview.** Three cards answer the three questions (the next step, the open findings, what the results rest on), then the four groups. No score, no bar, no trend line. (Mockup 01.)

---

## 7. Benefits

| Change | What the user gets | What the product gets |
|---|---|---|
| Three layers for every proof | The answer in five seconds. The proof in one click. | A demo that reaches the point before the audience drifts. Proof that looks deliberate instead of dumped. |
| A result that opens short | The same result opens at 1,195 pixels instead of 4,265. | The first thing an investor sees on Evidence is a finding, not a wall. |
| Each headline fact said once in the open | No hunting for which of five copies is the real one. | Fewer places for two sentences to drift apart when wording changes. |
| "What it doesn't show" always in the open | They know the limits before they rely on a result. | Honesty is visible. That is the product's edge over tools that only assert. |
| Observe and test apart | They see at once what was seen on their real systems and what was proven on a copy, and so which kind of fix each finding needs. | The app's most important trust difference is visible without reading tags. |
| The map of their systems | Their own system in one picture: where the cryptography is, what each check found there, and what their files leave out. | A picture an investor understands in seconds. The "continuously" in the promise becomes visible as the map fills in. |
| One tab strip with counts | They see where the findings are without clicking through four tabs. | The four work groups become the product's recognisable backbone. |
| A six-step sidebar | They always know where they are and what comes next. | The sidebar itself tells the story: bring in, observe, test, fix, plan the move, keep watching. |
| One place for each kind of label | A row reads left to right: what, result, rests on. | The four source tags finally do their job. They are the "live or lab" story at a glance. |
| A panel title with room | Names are readable. | Screenshots and demos look finished. |
| Advisories with the list on the first screen | They see what waits for them at once. | "Otto proposes, a person decides" is visible in one screen. |

**What it does not buy.** An opened proof is not shorter than today. On the proposed check it is about the same length, because every record is kept whole. The gain there is order, not length.

**What it costs.** Almost all the work is in the screens, but it is not small. The map is the one part that also needs new work on the server side (section 8). The screen tests (about 40 files) and the end-to-end walks (20 files) that read these panels have to follow the new layout, and the layout walk that measures every table page at 1440 pixels wide has to pass again. Most reference screenshots would be retaken.

---

## 8. Scope: what this is and is not

**Presentation only.** This plan changes where things sit on the screen and whether a second copy is drawn. It does not change:

- any result, check, test, verdict or count;
- the reviewer (`backend/app/engine/reviewer.py`), the runner, or any rule;
- the answer keys in `demo/`;
- the signed evidence file, the report, the ledgers or the verify command;
- what Otto may do, and what needs a person's click;
- `docs/wireframes/` (the folder is not in this repository, so nothing there was read or touched).

**The product rules, and how the mockups keep them.**

| Rule | In the mockups |
|---|---|
| Never "secure", no score, no severity | None appears. The one use of the word is the app's own standing line, kept word for word on every screen. The Overview has counts only. |
| Results come only from checks and tests | Every result chip is the reviewer's word as today. Tab numbers are counts of rows. No tick or cross is drawn on anything the reviewer did not decide. An empty Fix cell says nothing; it does not say that no fix is needed. |
| "How this test was proven" shows counts and never Passed or Failed | The three counts and the trial table show counts and what had to happen. No pass or fail mark is drawn on them. |
| The screen of the asking code is never called a proof | The sentence "a filter for mistakes and plain tricks, not a proof" is kept, inside part 4. See the naming note below. |
| A fixed version the publisher did not name is never called the publisher's | The label on each count is the app's own, which already changes its words in that case. |
| A library's fix carries its two proof rows in the same words | Kept word for word, with the note under the second row. |
| Each proposal is decided by itself, and accepting runs nothing | Accept and Reject are on each proposal, with that sentence beside them. |
| Plain-language text | Layer 1 uses only the app's own plain sentences. |

**What the screens can do alone, and what needs a little more.** "Presentation only" has an edge, and I want to be exact about it.

*The screens can do these with what the app already sends:*

- The three layers. Each block that moves is already a separate piece on the screen.
- The trail. It uses the links the Related block already has.
- The numbers on the tabs, the sidebar, the panel header.
- The trial as a table (each part already arrives with its name, its count and what had to happen) and the wrong cases as a table (already one).

*These need a small addition to the part of the app that turns stored results into sentences* (`backend/app/present/`). It decides nothing and changes no result, but it is not the screens alone:

1. **Two columns for "what this shows" and "what it doesn't".** Today the app sends those lines as one list. To split them cleanly it has to send two. Without this, layer 2 stays one block under today's heading, which is fine.
2. **The public copies as a table.** Each copy arrives as one sentence, with its version, date and fingerprint also sent apart. A table of version, date and fingerprint can be drawn today; the file's name and where it was fetched from stay in the sentence, folded under the table.
3. **A few fixed labels**: "Cryptanalysis proof" and the one line under it, "Where this page's facts come from". These are fixed words like today's "Technical summary".
4. **Numbers on the sidebar** (proposals waiting, open fixes). They are the Overview's own counts, read on every page.

*The map needs one new piece on the server side.* It is like "Where it is used" today:

1. **One new read** that gathers, into one picture, the structure of the kept scanner file, the dependency list with its ties, and each check's latest result. It reads only. It decides nothing, writes nothing and runs nothing. (The app already keeps a copy of each scanner file and already reads its "depends on" lines to find where each certificate is used. It just doesn't keep them as a picture yet.)
2. **Data flows** are not read today. A CycloneDX file can name the data that flows between services, but the importer doesn't read those lines. Reading them would be an importer change (data only; nothing in the file runs). Until then the map draws no data-flow arrows, and says that your file names none.

*Not proposed:*

- Any of Kind C above (choosing between two sentences the app writes).
- A tick or cross on each row of a trial. It would read as a result.
- The math in symbols. The app says what a test checks in words ("zero or outside the allowed range"). A line of symbols would be new content and would need its source, like every other fact.
- Merging Checks and Evidence into one page. It would undo the flow in the SPEC.
- Any change to the Otto panel. Its layout beside a detail panel deserves its own look later.
- The map in the downloadable report. The signed evidence file stays as it is.
- An "Observe again" button, or any other new way to start a check.
- Showing Change watch's runs on the map. The rules keep them apart from the assessment's own results.

**The SPEC would need these edits on approval.** `CLAUDE.md` says every screen element must be in SPEC section 2, so each of these is a change you would be approving. I would write out the exact new wording for your OK before any build.

| # | What changes in SPEC section 2 |
|---|---|
| 1 | A new paragraph: the three layers and the Cryptanalysis proof dropdown. |
| 2 | The sidebar: six numbered steps, ten entries, with Observe (Observatory, Verify) and Test (Advisories, Checks, Evidence), and "Migration plan". It no longer "lists the four under the page that is open". |
| 3 | The tabs: a count on each, always. |
| 4 | Where the source tag sits: at the head of its part of each list ("On your systems", "On copies on this computer"), and beside the result in a panel. Checks, Evidence and Fixes are drawn in those parts inside each tab. |
| 5 | The order of a result's panel on Evidence, and of an advisory's panel. |
| 6 | Advisories: the top blocks folded into one line; the two research buttons in the page header. |
| 7 | The trail at the top of every panel (new). |
| 8 | Checks: the test plan is drawn in the two parts, by where each test runs; a test's "Why it matters" opens under its row instead of standing on the card. |
| 9 | Overview: one count by tag for the whole assessment (new), and a small copy of the map, "Your systems" (new). Each group's own count by tag stays on its card, though the mockup does not draw it. |
| 10 | The code that asked the library: the second author's version on a switch beside the first instead of under it. "Show the code" stays. |
| 11 | The publisher's two version lines folded on an advisory's panel. |
| 12 | A new page, the Observatory: four counts by tag, the map with its Map and List views, and "What your files don't say". |
| 13 | The panel of a box on the map, which opens over the right side of the map. |
| 14 | "On your map" with **Show on the map** in the first layer of every result. |

**A naming note.** The rules say the screening of the asking code is "never called a proof". In the mockups that part sits inside a dropdown named "Cryptanalysis proof". The name describes the whole record, and the sentence that the screen is a filter and not a proof is kept inside it. If that still reads as too close, the dropdown can be named "Cryptanalysis record" at no cost. It is part of decision B.

---

## 9. The mockups

One throwaway file, [`design-refactor/mockups/mockups.html`](design-refactor/mockups/mockups.html), holds every screen. It is not the app and is not connected to it. Open it in a browser: the purple bar at the top switches the screen, the dark or light look, and the dropdown open or closed. The pictures below were taken from it with the repo's Playwright, at 1440 pixels wide.

Sentences are the app's own wherever the app has one, read from the existing screenshots and from the app's code, and the demo data is the same. The map's boxes and lines are the demo files' own (`demo/acme-pay-cbom.json` and `demo/dependencies-demo.cdx.json`). A few short lines are stand-ins where I shortened the app's sentence or where the app has no sentence yet (the sentence under each page title, the one-line test descriptions on Checks, the Observatory's own lines, and the run record of the observed result); a build would use the app's own words.

| # | Screen | Dark | Light |
|---|---|---|---|
| 01 | Overview | [picture](design-refactor/mockups/01-overview-dark.png) | [picture](design-refactor/mockups/01-overview-light.png) |
| 02 | Checks, with the proposed tabs and a compact test plan | [picture](design-refactor/mockups/02-checks-tabs-dark.png) | [picture](design-refactor/mockups/02-checks-tabs-light.png) |
| 03 | Evidence, with the proposed tabs | [picture](design-refactor/mockups/03-evidence-tabs-dark.png) | [picture](design-refactor/mockups/03-evidence-tabs-light.png) |
| 04 | A result, Cryptanalysis proof **collapsed** | [picture](design-refactor/mockups/04-result-proof-collapsed-dark.png) | [picture](design-refactor/mockups/04-result-proof-collapsed-light.png) |
| 05 | A result, Cryptanalysis proof **expanded** | [picture](design-refactor/mockups/05-result-proof-expanded-dark.png) | [picture](design-refactor/mockups/05-result-proof-expanded-light.png) |
| 06 | A proposed check, Cryptanalysis proof **collapsed** | [picture](design-refactor/mockups/06-test-proof-collapsed-dark.png) | [picture](design-refactor/mockups/06-test-proof-collapsed-light.png) |
| 07 | A proposed check, Cryptanalysis proof **expanded** | [picture](design-refactor/mockups/07-test-proof-expanded-dark.png) | [picture](design-refactor/mockups/07-test-proof-expanded-light.png) |
| 08 | A fix with its two proof rows, collapsed | [picture](design-refactor/mockups/08-fix-two-proof-rows-dark.png) | [picture](design-refactor/mockups/08-fix-two-proof-rows-light.png) |
| 09 | A fix, Cryptanalysis proof expanded | [picture](design-refactor/mockups/09-fix-proof-expanded-dark.png) | [picture](design-refactor/mockups/09-fix-proof-expanded-light.png) |
| 10 | The Observatory, just after the file comes in | [picture](design-refactor/mockups/10-observatory-just-brought-in-dark.png) | [picture](design-refactor/mockups/10-observatory-just-brought-in-light.png) |
| 11 | The Observatory, after the checks have run | [picture](design-refactor/mockups/11-observatory-map-dark.png) | [picture](design-refactor/mockups/11-observatory-map-light.png) |
| 12 | The Observatory, a system opened from the map | [picture](design-refactor/mockups/12-observatory-a-system-open-dark.png) | [picture](design-refactor/mockups/12-observatory-a-system-open-light.png) |
| 13 | An observed result, Technical record **collapsed** | [picture](design-refactor/mockups/13-observed-result-record-collapsed-dark.png) | [picture](design-refactor/mockups/13-observed-result-record-collapsed-light.png) |
| 14 | An observed result, Technical record **expanded** | [picture](design-refactor/mockups/14-observed-result-record-expanded-dark.png) | [picture](design-refactor/mockups/14-observed-result-record-expanded-light.png) |
| | Before and after: the tabs on Evidence | [picture](design-refactor/mockups/compare-tabs-dark.png) | [picture](design-refactor/mockups/compare-tabs-light.png) |
| | Before and after: one result, as it opens | [picture](design-refactor/mockups/compare-result-proof-dark.png) | [picture](design-refactor/mockups/compare-result-proof-light.png) |
| | Before and after: one proposed check, both opened | [picture](design-refactor/mockups/compare-test-proof-dark.png) | [picture](design-refactor/mockups/compare-test-proof-light.png) |

**How the before-and-after pictures compare.** Each sets like beside like. The result is shown as it opens today and as it would open. The proposed check is shown with its proof opened on both sides. The mockup's pictures also carry the page's header and the list beside the panel, which the "before" picture of the proposed check does not (it was taken on a page of its own).

The Overview, where the three cards answer the three questions, and a small copy of the map opens the Observatory:

![Overview](design-refactor/mockups/01-overview-dark.png)

The "before" pictures are the app's own screenshots, already in the repository:
`docs/screenshots/phase5c/3-00-evidence-result-where-the-check-came-from-*.png`,
`docs/screenshots/sandbox/15-the-proposal-with-its-whole-proof-*.png`,
`docs/screenshots/phase5c/9-01-real-library-fix-two-proof-rows-*.png` and
`docs/screenshots/group-tabs/evidence-2-encryption-panel-closed-*.png`.

**Not mocked, and how they would follow.** Verify, the Migration plan, Dependencies, Change watch, Settings, the Otto panel and the Observatory's List view were studied but not drawn. Each would take the same page order and the same panel order from section 6. Verify and the Migration plan would take the three layers with the dropdown named as decision B settles.

The mockups, their pictures and the small script that takes them (`shoot.mjs`) are disposable. Delete the folder `docs/plans/design-refactor/` once a decision is made.

---

## 10. Decisions for Kevin

**Decided on 26 November 2026.** A: yes. B: yes ("Cryptanalysis proof" for what was tested, "Technical record" for what was observed). C: yes (a numbered sidebar; with F it has six steps). D and E need no decision; the top of this plan says why.

**Round 2, for your OK:**

| | Decision | My recommendation |
|---|---|---|
| **F** | Observe and test as two steps: the six-step sidebar (Bring in, Observe, Test, Fix, Plan the move, Keep watching), and every list on Checks, Evidence and Fixes in two labelled parts, "On your systems" and "On copies on this computer". | Yes. |
| **G** | The Observatory as drawn: a map built only from your files and the checks, the list of what your files don't say, a panel for each box, "Show on the map" on every result, and the small map on the Overview. | Yes, built after the three layers (section 11), with a short plan of its own first, because it is the one part that needs new work on the server side. |

---

## 11. If approved: how it would be built

Not started. Each step would get its own short plan, be built, reviewed, and shown to you with tests and screenshots before the next, as `CLAUDE.md` asks.

1. **The proof on Evidence.** The three layers on a test result, with both dropdowns (Cryptanalysis proof and Technical record). This is the smallest step that proves the idea in the real app.
2. **The proof on Advisories and Fixes.** "How this test was proven" and the two proof rows, in the same three layers.
3. **Observe and test apart in the lists.** The two parts on Checks, Evidence and Fixes, and the six-step sidebar.
4. **The tabs and the labels.** Counts on the tabs, the three kinds of label.
5. **The panel header and the trail.**
6. **The Observatory.** Its own plan first. Then the map's read on the server side, the page, a box's panel, Show on the map, and the small map on the Overview.
7. **The calm pages** (Advisories, Checks, Overview), with the SPEC edits.

After each step: the screen tests, the end-to-end walks, the layout walk at 1440 pixels, and the accuracy check, which must match the answer keys exactly as it does today, because nothing behind the screens will have changed.
