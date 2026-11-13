# Handoff for the next session (after phase 3a; next is the server setting change, SPEC 7c)

Read `CLAUDE.md` and `docs/SPEC.md` first; they win over this page. State: phases 1, 2 and 3a are on `mvp/crypto-simple`. Phase 3a (the Fixes step) was built on 13 November 2026. The order after it is fixed in SPEC 9: the server setting change (7c), then change watch (3c), then the co-pilot and accuracy panel (3b). Another session works on the same branch: pull before you start and again right before you push.

## What is built
- **Phase 1:** Import (demo file or upload of the claims file), Verify (True / False / Couldn't check with evidence), a demo TLS server on localhost:8443, a demo CBOM, and an empty co-pilot panel.
- **Phase 2:** Tests (five suggested tests plus two catalog tests, reorder, remove, + Add test, Run, Run all), Evidence Lab (results, Mark reviewed, Dig deeper, retest between our two demo versions with before and after, evidence download as signed JSON plus an HTML report), demo mode and isolated mode (Docker).
- **Phase 3a:** the fifth step, **Fixes**. A code fix for the signing bug: Connect demo code, the change (3 lines added, 1 removed), a proof that starts by itself and reruns every locked test, a pull request inside the app, approvals, a merge that a person confirms, Download patch, Retest now. A text-only suggestion for the server TLS finding. Evidence Lab shows one line per failed result that points to its fix, and every result says which code it ran on. The evidence download holds all of it.
- **Checks on 13 November 2026:** backend 904 passed (none skipped, Docker running), frontend 150 passed, end-to-end 48 passed, accuracy 15 of 15 in demo mode and in isolated mode.

## How the pieces connect
- `backend/app/lab.py` (`Lab`) is the hub: it owns the database, the mode and the job runner. Mixed into it: `testlab.py` (plans, runs, Evidence Lab), `evidence_export.py`, and for phase 3a `changes.py` (where every fix stands, and every action on it) and `fixes.py` (the views). `main.py` only exposes it as HTTP; every route needs the login.
- A test is a **locked spec** (`research.py` builds it; `canonical.py` fingerprints it). `execute/*` runs it and returns raw outcomes only. `reviewer.py` is the **only** place with pass/fail logic, and since 3a also the only place that decides whether a change is offered (`review_proof`). `present.py` and `present_fixes.py` turn stored verdicts into plain words and decide nothing.
- **A fix is worked out, never stored.** `Lab.fix_states(plan_id)` reads the append-only records (`code_connections`, `changes`, `proofs`, `proof_reviews`, `pull_requests`, `approvals`, `merges`, `run_code`) and works out the status each time. Every proof verdict passes the read gate: the review is redone from the stored rows, and if it no longer gives the stored answer the proof "can't be trusted".
- **A proof** is one `proofs` row plus ordinary `test_runs` rows with phase `proof` (the proof's id sits in `retest_id`; no column was added, so a phase 2 database still opens). It goes through the same job runner and reviewer as a first run.
- **Only our own components run.** `changes.registered_version` compares the file a change produces, byte for byte, with the registered demo components; only then does that registered component run, never the changed file.
- `gitrepo.py` reads and writes git's own format with the standard library (no git program, no dependency). `demo_repo.py` makes the bundled repository `demo/repos/acme-sign.git/` from the 1.4.2 file (`python -m app.demo_repo`; a test fails if they drift apart). Each imported file gets its own copy in `data/repos/plan-<id>/`.
- `research.propose_change` holds the one fix template (the range check). Only it and `present_fixes.TEMPLATE_WORDS` know about that particular fix.
- **Polling:** the Fixes view and the Evidence Lab view each carry `busy`, read first. The screens ask again once a second while it is true.
- Frontend: `App.tsx` (step bar and shell), one screen file per step in `frontend/src/components/`, the Fixes parts in `components/fixes/`, shared pieces in `ui.tsx`, API types in `api.ts`. The frontend draws only what it is sent: every word, status and button comes from the backend.
- More detail: `docs/ENGINE.md` (records, the offer rule, the views and routes) and `docs/ADAPTER.md`.

## Patterns and screen style to reuse
- Dark slate screens, rounded cards, one amber `ErrorBox`, a violet "Demo data" label, a small grey `SourceTag` on every number, result badges with an icon and a word (never colour alone).
- Every result says what it shows **and what it doesn't**; the line "Passing these tests doesn't prove a system secure. It shows these specific checks passed." is on every result screen.
- Every action has a normal button, shown only when it applies. A refusal is always a plain sentence saying why.
- Until a proof has passed, nothing says a change "fixes" anything or is "ready": the heading reads "What it changes" and the Evidence Lab line reads "Fix prepared".
- Text for a busy security engineer who isn't a cryptographer. Never "secure", scores or time-to-hack.
- Tests: a no-Docker unit test next to each rule; Docker tests skip with a message; Playwright writes the screenshots. For a rule about timing or order, write the test so that it fails on the old code, and check that it does.

## Decisions made and why
- No uploading of outside software (CLAUDE.md, Safety). Retest only chooses between our two demo versions, and only the bundled demo repository can be connected.
- acme-sign 1.4.2 has one planted bug (no range check): 3 of 484 official cases fail. 1.4.3 is the same file plus the check and the version line. The comments that pointed at the bug were removed in 3a; the bug stays.
- Speed is timed inside the program. A slowdown is flagged only above the measured noise plus a 3% floor (Kevin: keep the 3%).
- The NIST note cites the final IR 8547 from a config value (`guidance.py`). Kevin confirmed the link on 11 November 2026. Keep the app's wording.
- **Approved by Kevin for 3a** (11 to 13 November 2026): the Fixes step and its buttons, the eight statuses, the six Evidence Lab lines, the two server sentences, the reviewer list and the one-login sentence, "Ready for review", the twelve mockups.
- **Decided during the 3a build; Kevin was told and can overrule** (also in `docs/LIMITS.md`): the proof must hold the Speed and size test and the failed tests it answers; an open pull request does not shield an out-of-date proof, and approvals already given are kept; only a newer result that says pass or fail closes a finding; a failing test added after connecting joins the same code fix; a report-only test is not counted as passed. If he has answered since, his answer wins.

## Known weak spots (full list in `docs/LIMITS.md`)
- Three looks have no approved picture: the Proof section opened while the proof runs, a pull request whose proof is out of date, and the Fixes part of the report (screenshots 03a, 25 and 14 in `docs/screenshots/phase3a/`).
- On the Tests screen, Run and Run all are switched off while a proof runs, with no sentence saying why.
- A proof that fails because a signing test does not pass can't be reached with buttons; only backend tests cover it.
- The accuracy command does not go through the Fixes step (the end-to-end test does).
- `gitrepo.py` handles loose objects, flat repositories and UTF-8 text only, and lines up changed lines with Python's own method, which can differ from git by one line for some texts. Both matter from 3c on.
- If the app stops in the instant between the merge in the repository and writing the merge record, that pull request can no longer be merged.
- The rule engine never raises. Another engine that raises, or answers in another shape, would make the Fixes and Evidence Lab views fail (the engine is asked on every look, before and after the code is connected). Wrap that question when another engine is plugged in.
- The backend suite takes about 14 minutes and the end-to-end test about 6.
- The post-quantum check needs Docker host networking; untested on Docker Desktop. The reference library runs outside the container.
- Nobody has compared the app's NIST wording with the NIST document itself yet (the build machine cannot reach the site).

## Next: the server setting change (SPEC 7c)
- **What it adds:** a **Prepare change** button on the server TLS fix in Fixes. The app writes the setting change from a fix template ("From a fix template"), applies it to a **test copy** of the demo server, and reruns the server tests as proof. After the user approves and confirms, it applies the setting to our own demo server (Demo data) and reruns Verify and the server tests. The app never changes a customer's server. Only Prepare change is approved so far: list the other buttons in the plan and get Kevin's OK first.
- **Answer key:** `demo/expected.json` has S1 to S3 under `after_server_fix`. They are not checked yet; `app/accuracy.py` must learn them in that step. Never edit the key.
- **What 3a left ready:**
  - Fixes come from a list of sources (`changes._fix_sources`); the server TLS fix already exists as the text-only fix `fix-tls-versions`, with its full suggestion.
  - A finding closes only on a newer result that says pass or fail, by run time. After the demo server is changed, a retest or a rerun that passes closes "Server accepts TLS 1.2" by itself, and the code fix's line about the server finding goes away. Watch one thing: only the results Evidence Lab shows now count. So a finding that a passing retest closed reads as open again while the next retest is running (and stays open if that retest could not run the test), and a finding that only a retest found leaves the list as soon as the next retest starts. Decide in the 7c plan whether that is right once the server can really change; looking up the newest pass or fail across all retests would close both.
  - The backend tests already change the demo server's settings in place (`lab.demo._server._ctx.minimum_version`, see `test_changes.py`): a starting point for the test copy.
  - The read gate, the append-only records and the evidence export are general. A server change needs its own record kinds, not new rules about who decides.
- **Open design points for the plan:** what the proof of a server change is compared with (the code proof's rule 6 needs "the failed tests the change answers", which fits; its speed rule does not apply to a server); what "pull request" means for a setting; and how the demo server keeps the new setting across a restart.

## Server TLS suggestion (text only in 3a): what was checked
It shows in Fixes with the status Text only and no buttons. Tested on real nginx 1.24.0 and Apache 2.4.58 (OpenSSL 3.0.13) on the build machine, probed with the app's own `tlsprobe`. The app counts a version as refused only on the protocol_version alert, and these settings give exactly that.
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
- **Build rule for the words:** the test records only the cipher suite each handshake used; it does not scan for others. The suggestion names a suite, and calls it "older", only when the recorded TLS 1.2 handshake used an old CBC/SHA-1 suite such as ECDHE-ECDSA-AES128-SHA.
- **The warning comes first,** above the exact settings, so nobody copies a TLS 1.3-only line before reading it.

## Later: change watch (3c) and the co-pilot (3b)
- **Change watch** is designed in `docs/design/change-watch.md` by another session. That file was not on the branch on 13 November 2026; fetch and look again, and never edit it. 3c should add to what 3a built, not change it: the connected demo repository, its branches and commits, the change records (a change is a branch plus the commit it starts from, whoever made it), the proof, the "code it ran on" record of every run, and the source of every fix.
  - The safety rule stays: a change's code runs only if it is byte for byte one of our registered demo components, so any developer change used in the demo has to be bundled the same way.
  - The offer rule needs at least one failed test that the change answers. A developer's change answers none, so 3c needs its own rule in `reviewer.py`.
  - See the two `gitrepo.py` limits above.
- **Co-pilot:** fill `CopilotPanel.tsx`. It reads what is on screen, and its confirm cards must call the same functions as the buttons. SPEC 7b: it can explain a suggested change and offer Open pull request as a confirm card. Do not add a model.
- **Accuracy panel:** reuse `app/accuracy.py`; it runs all 15 answers through the same paths as the buttons.

## Working habits that matter
- Plan first and wait for Kevin's OK; build; get a separate review; show test output, screenshots and accuracy; commit and push only after his OK. He isn't a developer: explain plainly and handle git yourself. A Stop hook keeps asking to commit; his rule wins.
- After every machine restart start Docker by hand (`dockerd`) and run `cd backend && .venv/bin/python -m app.prepare`, or the container tests skip and the post-quantum check can't run. Use `backend/.venv`, never plain `python3`.
- Run the long checks one at a time. The speed test measures time, so two heavy runs at once can make it read "Couldn't trust this run".
- If the demo component files ever change, run `python -m app.demo_repo` and `python -m app.prepare` again (the image tag is made from the files).
- These sites are blocked from the build machine: csrc.nist.gov, nginx.org, httpd.apache.org, docs.aws.amazon.com.
- Never edit `demo/expected.json` or `docs/wireframes/`. Ask before adding any dependency not in SPEC section 3. Never put keys or secrets in code, logs or replies.
- Kevin keeps a gallery of the screenshots ("Evidence Lab Screens"). After a phase is committed, read it first, keep everything in it and add the new pictures.
- Another session may be working on the same branch at the same time. Pull before you start and right before you push, and change only the files you were asked to.
