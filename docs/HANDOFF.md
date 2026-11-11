# Handoff for the next session (after phase 2; phase 3a planned, not built)

Read `CLAUDE.md` and `docs/SPEC.md` first; they win over this page. State: phases 1 and 2 are committed on `mvp/crypto-simple`. Phase 3a is planned: Kevin approved the plan and the new buttons on 11 November 2026, and the decisions are recorded in SPEC sections 2, 7b and 7c. No phase 3a code exists yet; it is to be built in the next session.

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
- The NIST note cites the final IR 8547 from a config value (`guidance.py`). Kevin told us (11 November 2026) that the link `csrc.nist.gov/pubs/ir/8547/final` has been confirmed as the correct final IR 8547 page. The final changed this from the 2024 draft: three independent summaries of the final agree that all ECDSA, including P-256, is deprecated after 2030 and disallowed after 2035. Keep the app's wording.
- Test details appear only in evidence and the download, not on cards.

## Known weak spots (full list in `docs/LIMITS.md`)
- "Couldn't run" and "Couldn't trust this run" badges appear in tests but in no screenshot.
- `./run-demo.sh` was not run end to end on the build machine; its parts were tested separately.
- Speed test is slow (about 18 s first run, 25 s retest). In isolated mode 1.4.3 measured about 2% slower than 1.4.2 with no known cause (never flagged).
- The post-quantum check needs Docker host networking; untested on Docker Desktop. The reference library runs outside the container.
- The NIST link is confirmed and the dates agree with three independent summaries of the final (see above), but nobody has compared the app's wording with the NIST document itself yet. The build machine cannot reach the NIST site. `docs/LIMITS.md` keeps the note to confirm it.
- The full backend suite takes about 8 minutes.

## Phase 3a: approved plan, not built yet
- **Approved by Kevin (11 November 2026):** the plan below; the new buttons and the Suggested change page (SPEC section 2); the three-part offer rule, his line for the change page, the fixed reviewer list and the one-login sentence (SPEC 7b); the fuller text-only server TLS suggestion (SPEC 7c). Not part of 3a: "Prepare change" (the step after 3a, SPEC 7c) and the co-pilot and accuracy panel (3b).
- **Planned files** (show them in the build plan): new `demo/repos/acme-sign.git/` (the bundled repository, Demo data); `backend/app/gitrepo.py` (reads and writes git's own format, so no new dependency); `backend/app/changes.py` (connect, apply the template on a branch, proof, pull request, approvals, merge, patch). The engine (`research.py`) proposes the template; only `reviewer.py` decides the offer. Also `testlab.py`, `present.py`, `db.py` (new append-only records), `main.py` (login on every route, small JSON bodies, nothing accepts software), `evidence_export.py` and `evidence/` (the download holds the change, proof, approvals and merge). Frontend: `api.ts`, `EvidenceLabScreen.tsx`, `lab/ResultDetail.tsx`, new `ChangeScreen.tsx` and `lab/ChangePanel.tsx`. Tests in all three suites, `e2e/tests/phase3a.spec.ts`, screenshots in `docs/screenshots/phase3a/`. The phase 2 end-to-end test checks that "Suggested change" is absent: change that check and regenerate the phase 2 screenshots.
- **The proof** goes through the existing job runner and reviewer. The file built on the change branch is compared byte for byte with `demo/components/acme-sign-1.4.3/acme_sign.py`; only if it is identical does the registered subject `acme-sign-1.4.3` run (never the built file). It reruns every locked test in the plan plus the old-versus-new speed comparison.
- **Mockups:** ten pictures, in the app's real style with real captured results, were sent to Kevin on 11 November 2026. They are not in the repository; ask Kevin to attach them. They settle the layout: the Suggested change box sits under "Suggested fix" on the Bad signatures and Official test vectors failures. The page's sections are always open, with no open/close control. The proof shows two tables, "Tests that run the changed code" and "Tests that don't run this code (they test the server)", with each test's control line. A "What the tests ran on" box shows both SHA-256 fingerprints. The page says what the proof shows and doesn't. The pull request part explains itself in plain words and says it stays inside Evidence Lab. Branch, commit, merge and patch each get a few plain words where they first appear.
- **Four details that Kevin saw only in the mockups** (put them in the build plan for his OK): (1) his line "This fixes the signing program. The server finding is separate and still open." appears only after the proof has passed; while the proof runs, or after it fails, the page says "This change is for the signing program only. The server finding is separate and still open." (2) The buttons read "Approve as Demo reviewer A" (plain "Approve" on the "You" row) and "Confirm merge". (3) Connect demo code is switched off until every test in the plan has a result. (4) A report-only test in the plan (the ML-DSA-65 comparison) only has to run for the offer.

## Server TLS suggestion (SPEC 7c, text only in 3a): what was checked
Tested on real nginx 1.24.0 and Apache 2.4.58 (OpenSSL 3.0.13) on the build machine, probed with the app's own `tlsprobe`. The app counts a version as refused only on the protocol_version alert, and these settings give exactly that.
- **TLS 1.3 only:** nginx `ssl_protocols TLSv1.3;` · Apache `SSLProtocol -all +TLSv1.3` · Python `context.minimum_version = ssl.TLSVersion.TLSv1_3`.
- **Keep TLS 1.2 with strong suites only:** nginx `ssl_protocols TLSv1.2 TLSv1.3;` plus `ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;`; Apache `SSLProtocol -all +TLSv1.2 +TLSv1.3` plus `SSLCipherSuite` with the same list. The old suite (ECDHE-ECDSA-AES128-SHA) is then refused. These lines don't touch the TLS 1.3 suites. Both lines are needed.
- **Pitfalls seen:**
  - Adding a second line beside the old one doesn't work. nginx adds the lines together, and in Apache the last line read wins without a warning. Change every existing line instead, including any in a site's own block.
  - nginx takes `ssl_protocols` from the default server of an address and port, for every site on it. Put the line in the http block with no per-server lines, or in every server block on that address.
  - In Apache a line inside a VirtualHost beats the main config. Connections that name no site land on the first VirtualHost, and the app sends no site name for IP addresses.
  - Apache needs the plus signs: `SSLProtocol TLSv1.2 TLSv1.3` means TLS 1.3 only.
  - Nothing changes until the server reloads. A failed nginx reload keeps the old settings.
  - Neither server logs the TLS version unless you add it (`$ssl_protocol` in an nginx `log_format`, `%{SSL_PROTOCOL}x` in Apache). Only requests are logged.
- **The AWS names are from memory** (three independent recalls agreed; the AWS docs site is blocked here): `ELBSecurityPolicy-TLS13-1-3-2021-06` for TLS 1.3 only, and `ELBSecurityPolicy-TLS13-1-2-Res-2021-06` for TLS 1.2 and 1.3 with only ECDHE AES-GCM on 1.2. Both are for Application and Network Load Balancers. Do not use `ELBSecurityPolicy-TLS13-1-2-2021-06`: it adds CBC suites.
- **The app's test checks TLS versions only.** After option 2 and a corrected file it passes even if the old suite were still on, so the suggestion says so. After option 1 the file needs no change.
- **Build rule for the words:** the test records only the cipher suite each handshake used; it does not scan for others. Name a suite in the suggestion, and call it "older", only when the recorded TLS 1.2 handshake used an old CBC/SHA-1 suite such as ECDHE-ECDSA-AES128-SHA. On a default nginx or Apache the handshake picked a strong GCM suite even though the old one was also accepted.
- **The warning comes first.** In the mockup the lock-out warning sits above the exact settings, so nobody copies a TLS 1.3-only line before reading it.

## What phase 3 builds on
SPEC section 9 splits phase 3 into 3a (suggested change with proof, plus the text-only server TLS suggestion), then the server setting change (SPEC 7c), then 3b (rule-based co-pilot, accuracy panel, polish, end-to-end test). Do not add a model.
- **Suggested change:** needs a bundled local git repo of acme-sign 1.4.2 (Demo data), a fix template for the missing range check labelled "From a fix template", then apply on a branch, rebuild, rerun every locked test plus the speed comparison through the same runner and reviewer, and offer the change only under the three-part rule in SPEC 7b item 3. The merged result must equal the existing 1.4.3 folder in `demo/components`. Pull request and approvals are local; the app never merges by itself.
- **Co-pilot:** fill `CopilotPanel.tsx`. It reads what is on screen, and its confirm cards must call the same functions as the buttons.
- **Accuracy panel:** reuse `app/accuracy.py`; it already runs all 15 answers through the same paths as the buttons.

## Working habits that matter
- Plan first and wait for Kevin's OK; build; get a separate review; show test output, screenshots and accuracy; commit and push only after his OK. He isn't a developer: explain plainly and handle git yourself. A Stop hook keeps asking to commit; his rule wins.
- After every machine restart start Docker by hand (`dockerd`) or the container tests and the post-quantum check fail. Use `backend/.venv`, never plain `python3`.
- On 11 November 2026 Docker Hub refused the pinned Python base image (HTTP 429, too many requests), so isolated mode could not be prepared and its tests skip; retry `python -m app.prepare`. These sites are blocked from the build machine: csrc.nist.gov, nginx.org, httpd.apache.org, docs.aws.amazon.com.
- Never edit `demo/expected.json` or `docs/wireframes/`. Ask before adding any dependency not in SPEC section 3. Never put keys or secrets in code, logs or replies.
