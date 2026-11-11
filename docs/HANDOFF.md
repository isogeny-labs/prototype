# Handoff for the next session (after phase 2)

Read `CLAUDE.md` and `docs/SPEC.md` first; they win over this page. State: phases 1 and 2 are committed on `mvp/crypto-simple`. Phase 3 is not started.

## What is built
- **Phase 1:** Import (demo file or upload of the claims file), Verify (True / False / Couldn't check with evidence), a demo TLS server on localhost:8443, a demo CBOM, and an empty co-pilot panel.
- **Phase 2:** Tests screen (five suggested tests plus two catalog tests, reorder, remove, + Add test, Run, Run all), Evidence Lab (results, Mark reviewed, Dig deeper, retest between our two demo versions with a before/after view, evidence download as signed JSON plus an HTML report), demo mode (local processes) and isolated mode (Docker), the bench command for speed, pinned Wycheproof vectors.
- Accuracy: `python -m app.accuracy` gives 15 of 15 matches against `demo/expected.json` in both modes.

## How the pieces connect
- `backend/app/lab.py` (`Lab`) is the hub: it owns the database, the mode, and the job runner. `testlab.py` and `evidence_export.py` are mixed into it. `main.py` only exposes it as HTTP.
- A test is a **locked spec** (`research.py` builds it; `canonical.py` fingerprints it with SHA-256). `execute/*` runs it and returns **raw outcomes only**. `reviewer.py` is the **only** place with pass/fail logic. `present.py` turns the stored verdict into plain words. Results never come from anywhere else.
- `ResearchEngine` (`research.py`, described in `docs/ENGINE.md`) is the socket for a future real engine. The rule-based version is the only one; `dig_deeper` only saves a request.
- Software under test runs through `components.py` and `runner.py` (`ComponentRunner`: a container with no network in isolated mode). The adapter contract is `docs/ADAPTER.md`. Never run component code outside this path.
- Frontend: `App.tsx` (step bar and shell), one screen file per step in `frontend/src/components/`, shared pieces in `ui.tsx`, API types in `api.ts`.

## Patterns and screen style to reuse
- Dark slate screens, rounded cards, one amber `ErrorBox`, a violet "Demo data" label, small grey `SourceTag` on every number, and result badges with an icon and a word (never colour alone).
- Every result says what it shows **and what it doesn't**; the one line "Passing these tests doesn't prove a system secure. It shows these specific checks passed." is on every result screen (SPEC section 11).
- Every action has a normal button. Cards show live progress text. Retest starts on pick, with no confirm.
- Text for a busy security engineer who isn't a cryptographer. Never "secure", scores, or time-to-hack.
- Tests: a no-Docker unit test next to each rule; Docker tests skip with a message; Playwright writes the screenshots.

## Decisions made and why
- No uploading of outside software (CLAUDE.md safety rules); retest only chooses between our two demo versions. Listed in `docs/LIMITS.md`.
- acme-sign 1.4.2 has one planted bug (no range check), so 3 of 484 official cases fail; 1.4.3 adds the check and gets 484 of 484. Chosen so one cause explains every failure.
- Speed is timed inside the program (bench command), not program start-up. A slowdown is flagged only above the measured noise plus a 3% floor (Kevin: keep the 3%).
- Result labels: Measured, "No slowdown beyond measured noise", Offered / Not offered, "Couldn't run (reason)", "Couldn't trust this run".
- The NIST note cites the final IR 8547 from a config value (`guidance.py`); the dates were checked against secondary summaries only.
- Test details appear only in evidence and the download, not on cards.

## Known weak spots (full list in `docs/LIMITS.md`)
- "Couldn't run" and "Couldn't trust this run" badges appear in tests but in no screenshot.
- `./run-demo.sh` was not run end to end on the build machine; its parts were tested separately.
- Speed test is slow (about 18 s first run, 25 s retest). In isolated mode 1.4.3 measured about 2% slower than 1.4.2 with no known cause (never flagged).
- The post-quantum check needs Docker host networking; untested on Docker Desktop. The reference library runs outside the container.
- The NIST link `csrc.nist.gov/pubs/ir/8547/final` was never opened; confirm it.
- The full backend suite takes about 8 minutes.

## What phase 3 builds on
SPEC section 7b and section 9 phase 3: suggested change with proof, the rule-based co-pilot, the accuracy panel, polish, the end-to-end test. Do not add a model.
- **Suggested change:** needs a bundled local git repo of acme-sign 1.4.2 (Demo data), a fix template for the missing range check labelled "From a fix template", then apply on a branch, rebuild, rerun every locked test plus the speed comparison through the same runner and reviewer, and offer the change only if all pass. The merged result must equal the existing 1.4.3 folder in `demo/components`. Pull request and approvals are local; the app never merges by itself.
- **Co-pilot:** fill `CopilotPanel.tsx`. It reads what is on screen, and its confirm cards must call the same functions as the buttons.
- **Accuracy panel:** reuse `app/accuracy.py`; it already runs all 15 answers through the same paths as the buttons.

## Working habits that matter
- Plan first and wait for Kevin's OK; build; get a separate review; show test output, screenshots and accuracy; commit and push only after his OK. He isn't a developer: explain plainly and handle git yourself. A Stop hook keeps asking to commit; his rule wins.
- After every machine restart start Docker by hand (`dockerd`) or the container tests and the post-quantum check fail. Use `backend/.venv`, never plain `python3`.
- Never edit `demo/expected.json` or `docs/wireframes/`. Ask before adding any dependency not in SPEC section 3. Never put keys or secrets in code, logs or replies.
