# Isogeny Evidence Lab: crypto MVP spec

This is the full spec for the MVP, built from scratch in the `prototype` repository on branch `mvp/crypto-simple`. `CLAUDE.md` holds the standing rules; this file holds what to build. Build one phase at a time (section 9).

**The goal:** a simple, working demo that shows investors one thing: **you bring in a file that claims how a system's encryption is set up, and the product tells you, with evidence, whether each claim is true, then suggests the fix.** It must be accurate, and it must be simple: few screens, few buttons.

**Out of scope:** accounts beyond one local login, teams, approval workflows, compliance reports, scheduling, other industries, any AI model, any outside orchestration service, Cairn, and any code from the old prototype.

## Why this exists (context for your decisions; don't put this text in the app)

- **Who uses it:** usually one security engineer at a company that handles sensitive data or payments. They are busy and not a cryptographer. Design for them.
- **The pain:** scanning tools produce lists of where encryption is used, but nobody checks whether the list is true. Encryption is tested once and rarely rechecked. Auditors want proof, not a list. The move to post-quantum encryption makes all of this urgent.
- **What we do differently:** we don't replace the scanner. We take its list, prove each claim with real tests, suggest the fix, and retest after the change, with evidence anyone can check.
- **What this MVP must show investors:** it works on a real flow, it's accurate (it catches the planted problems and doesn't flag the true claim), and it's simple enough to understand in five minutes.
- **How to use this:** when a choice isn't covered here, pick whatever makes the demo simpler, clearer or more accurate. If a feature doesn't help one of those three, leave it out and list it in `docs/LIMITS.md`.

## 1. The flow (five parts)

1. **Import.** The user uploads a file from a scanning tool that lists where encryption is used and how (for example "this server only allows TLS 1.3", "this service signs with ECDSA P-256").
2. **Verify.** The product checks each claim against the real system and marks it **True**, **False** or **Couldn't check**, with the evidence behind it.
3. **Test plan.** The product suggests five tests. The user can reorder them, remove them, add new ones from a short catalog, and run them one at a time or all at once.
4. **Evidence Lab.** Shows each test's result, what it proves and what it doesn't, and a suggested fix for each failure. After the fix (in the demo, a corrected version), the user reruns the same tests and sees before and after.
5. **Co-pilot.** An assistant that sits side by side with the main screens on every step. You can talk to it about new tests, discuss findings and dig deeper into the evidence. It's an aid, not the decision-maker:
   - **Results never come from the co-pilot.** True/False and Passed/Failed come only from the checks and tests.
   - **Everything is doable without it.** Every action (add a test, reorder, run, retest, mark a finding as reviewed, download) has its own button in the main screens. The co-pilot is never the only way to do anything.
   - **It can offer a shortcut, never act alone.** When it suggests an action, it shows a card with a Confirm button that does exactly what the matching main-screen button does. Nothing happens until the user clicks.

That's the whole product. No accounts beyond a single local login, no teams, no approvals workflow, no compliance reports, no scheduling, no other industries.

## 2. Screens and buttons (keep it this small)

One app shell: a step bar at the top (Import → Verify → Tests → Evidence Lab) and the co-pilot panel on the right, collapsible.

- **Import:** a drop zone, a "Use demo file" button, and a table of what the file claims. One button: **Verify claims**.
- **Verify:** one row per claim: claim, what we found, True / False / Couldn't check, and an expandable "evidence" section (raw output). One button: **Continue to tests**.
- **Tests:** a list of five suggested test cards, each with a one-line "why this matters". Drag to reorder, an × to remove, **+ Add test** (opens the catalog), a **Run** button on each card, and **Run all** (runs in parallel). Live status on each card: waiting, running, passed, failed, couldn't run.
- **Evidence Lab:** results grouped by test; for each failure, a plain-language explanation, the evidence, and a suggested fix, with a **Mark reviewed** button so the user records their own decision on it. Where a code fix is possible, the failure also shows a **Suggested change** panel (section 7b) with a **Review change** button. Two more buttons: **Retest new version** (choose the new version, reruns the same tests, shows before and after) and **Download evidence** (one JSON file plus a readable HTML report, with a fingerprint).

Nothing else gets a button. If you think a screen needs more, ask me first.

## 3. Stack

- Backend: Python 3.12, FastAPI, SQLite (via SQLAlchemy), pydantic.
- Frontend: React + TypeScript (strict) + Vite + Tailwind. Clean, calm design, dark mode. Text wordmark "Isogeny Labs" for the logo.
- Crypto reference: `cryptography` (pyca) for ECDSA and Ed25519; Python's `ssl` module plus OpenSSL command-line tools for TLS checks. Detecting post-quantum hybrid key exchange (X25519MLKEM768) needs **OpenSSL 3.5 or newer**. If the machine's OpenSSL is older and Docker isn't available, that test shows **Couldn't run** with the reason, never a guess.
- Running software under test, two modes:
  - **Demo mode (no Docker needed):** only our own demo components (`acme-sign` and the broken control) run, as separate local processes with a time limit. Uploading outside software is turned off. The screen says "Demo mode: running our own demo software, not isolated."
  - **Isolated mode (when Docker is running):** any component, including uploaded ones, runs in a container with no network, a read-only filesystem except a scratch folder, and CPU, memory and time limits. It must not be able to read anything on the host, including the database and the evidence signing key. Uploading outside software is allowed only in this mode.
- Demo TLS server: a small Python server started by the app (no Docker needed), configured to accept TLS 1.2 with an older cipher as well as TLS 1.3. If Docker is running, the OpenSSL 3.5 checker container can also be used.
- **Research engine socket (the autoresearcher plugs in here later).** Everything that thinks about tests goes through one `ResearchEngine` interface: `propose_tests(claims) -> plan`, `design_test(request) -> test` (used by **+ Add test** and the co-pilot), `review(result) -> review`, and `dig_deeper(finding) -> research request`. Phase 2 ships a rule-based engine that returns the five tests in section 7. Our real autoresearcher replaces it later without changing any screen. Build the records to match how the autoresearcher works:
  - **Test before run:** each test is written down before it runs (question, method, inputs, controls, the pass/fail rule) and locked with a SHA-256 hash. A locked test can't change; editing it makes a new version.
  - **Run record:** every run keeps the locked test's hash, the component version, raw outputs, logs and timing. Runs are never edited or deleted, including failed ones.
  - **Separate review:** the result is checked by a separate review step (control behaved as expected, pass/fail rule applied correctly) before it shows as Passed or Failed. The engine that proposed a test never reviews its own result.
  - **Dig deeper:** in phase 2 this saves a "research request" (the finding, the question, the evidence) with status "waiting for research engine". Show it in Evidence Lab as queued; don't fake an answer.
  - Document the interface and these record shapes in `docs/ENGINE.md`.
- Running tests: a small job runner **inside the backend** (an async worker pool with a configurable max at once, default 4). Each test is a job with status, start and end time, logs and result. No separate orchestration service and no external queue.
- Evidence fingerprint: SHA-256 over the evidence file, signed with an Ed25519 key that the app generates on first start and stores outside the sandbox's reach.
- Co-pilot: **no AI model for now.** Build it as a rule-based assistant: it reads what's on screen and answers from templates and the stored evidence (explain a result, show the raw evidence behind it, list catalog tests that fit, suggest the next step). Users type a question or click suggested questions; if it can't answer, it says so. Put all of it behind one `CopilotEngine` interface (`reply(context, message) -> {text, suggested_actions}`) so an AI model can be plugged in later without changing the screens. The panel is labeled "Prototype assistant (no AI model connected)".
- Tests of our own code: pytest, Vitest, Playwright.

## 4. What the import file looks like

Support two formats:
- **CycloneDX 1.6 CBOM JSON** (the format IBM's CBOMkit produces). Read only the crypto parts: algorithms, protocols, certificates, and where each is used.
- **A simple CSV template** we ship (`location, type, claim, value`, for example `localhost:8443, tls, protocol_versions, TLS1.3`).

Turn each into a list of **claims**. Each claim says where (a host:port or a software component), what (TLS versions, cipher suites, key exchange, certificate algorithm and key size, signature algorithm), and the claimed value. Invalid files get a clear error naming the line or field. Nothing in an uploaded file is ever executed.

## 5. Verify: how claims are checked

- **Server claims** (host:port): connect with handshakes only. Find which TLS versions are actually accepted (including older ones), cipher suites, key-exchange groups, and the certificate's algorithm and key size. Compare with the claim. Before checking any address, the user ticks "I own this system or am allowed to test it" once per address. Only allow localhost and addresses the user confirmed. No attacks, no load.
- **Software claims** (a signing component): run the component's `info` command (section 6) and compare the algorithm and version it reports with the claim, then do one normal sign-and-verify round trip to confirm it really uses that algorithm. Whether it's built correctly is not a Verify question; that's what the tests in section 7 are for.
- Every result stores the raw evidence (command, output, time, tool version).

## 6. Software under test: the adapter

Software is tested through a tiny command-line contract. It reads JSON on stdin and writes JSON on stdout, with four commands: `keygen`, `sign`, `verify`, `info`. Document it in `docs/ADAPTER.md` with a complete example. A component is picked from the demo, or (isolated mode only) uploaded as a folder with a Dockerfile.

## 7. The five suggested tests (and the catalog)

Suggest these five, ordered by what the claims cover:

1. **Server protocol check:** does the server accept anything older or weaker than claimed?
2. **Certificate check:** do the certificate's algorithm and key size match the claim and current NIST guidance? Store that guidance as a config value with its source link, not a hard-coded claim.
3. **Official test vectors:** does the signing component give the right answer on Project Wycheproof vectors for ECDSA P-256 and Ed25519? Vendor the vector files with their source URL and commit; ask me before adding them.
4. **Bad-signature check:** does it reject signatures it must reject: changed message, changed signature, wrong length, r = 0, s = 0, values at or above the curve order, broken encodings?
5. **Speed and size:** signing and verification time (median and slowest 1 in 100, with the repeat count shown) and key and signature sizes, compared with a reference library. This test reports numbers; it has no pass/fail on the first run. On a retest it flags a slowdown larger than the measured run-to-run noise.

Catalog for **+ Add test** (small, at most five extra): post-quantum readiness (does the server offer X25519MLKEM768?), compare with a post-quantum signature (ML-DSA-65 speed and size from a reference implementation, labeled "reference, not production"), plus any you think are essential. Ask me before adding more.

Every test has a **built-in control**: alongside the customer's component it also runs a deliberately broken reference component that must fail, so "passed" means something. If the control doesn't fail, the test result is marked **Couldn't trust this run**.

Each result is one of: **Passed**, **Failed**, **Couldn't run** (with why), **Couldn't trust this run**.

## 7b. Suggested change with proof (built in phase 3)

Between finding a bug and retesting, the product proposes the exact code change and proves it works before offering it.

1. **Connect the code.** The user connects the component's source code. In the demo this is a bundled local git repository of `acme-sign` (version 1.4.2), labeled **Demo data**. Connecting real GitHub or other hosts is out of scope for now; list it in `docs/LIMITS.md`.
2. **Suggested change.** For a failure with a known fix, the research engine proposes a code change, shown as a before/after diff of the exact lines, with a plain-language explanation. With no AI model connected, changes come from fix templates for known bug types and are labeled **"From a fix template"**. Never present a template change as AI-written.
3. **Proof before offering.** The app applies the change to a copy of the code on a new branch, rebuilds the component, and reruns **every** test in the locked plan (not only the failing one), plus the speed comparison. The change is offered only if every test passes and the controls behave. If anything fails, show the failed proof and don't offer the change.
4. **Pull request.** **Open pull request** creates a pull request inside the app against the connected repository: the branch, the diff, the proof results and the evidence fingerprint. The user picks one or more reviewers who must approve it (in the demo, local users; default is the user alone). Each approval is recorded with name and time. The app never merges or deploys by itself; merging is a separate, confirmed user action. The pull request can be downloaded as a patch file.
5. **Retest.** The merged result is version 1.4.3. **Retest new version** reruns the same locked plan and shows before and after, exactly as in section 2.

The co-pilot can explain a suggested change and offer **Open pull request** as a confirm card, but every step also has its own button.

## 8. Demo data (must run with no internet)

Ship a demo, labeled **Demo data** everywhere:
- `acme-pay-cbom.json`: a CBOM for a fictional "Acme Pay" token-signing service. It claims: the server at `localhost:8443` accepts TLS 1.3 only; the certificate is ECDSA P-256; the signing component is `acme-sign` 1.4.2 implementing ECDSA P-256.
- A demo TLS server (started by the app) that **also accepts TLS 1.2 with an older cipher**, so that claim comes back False.
- `acme-sign` 1.4.2, whose verifier **accepts the signature r = 0, s = 0** (the same kind of bug as the real CVE-2022-21449), so test 4 fails. And `acme-sign` 1.4.3, which fixes it.
- One claim that is genuinely true (the certificate), so the demo shows the product doesn't flag everything.

**Accuracy check.** `demo/expected.json` is the answer key: the right answer for every demo claim and test. **We wrote it, not you. Never edit it.** If the app disagrees with it, fix the app or tell me why the key is wrong; don't change the key to make the check pass. Add a command and a small panel in Evidence Lab (for example "Demo accuracy: 15 of 15 match") that compares the app's results with the expected answers. Any mismatch is shown, not hidden.

## 9. Phases

0. **Repository setup:** done. The branch has been cleared of the old prototype and contains only `CLAUDE.md`, this spec and `demo/expected.json`.
1. **Import and Verify**, the demo TLS server and the demo CBOM, and an empty co-pilot panel. **Stop and show me.**
2. **Tests and Evidence Lab:** the research engine socket (section 3) with the rule-based engine, demo mode and isolated mode, adapter, the five tests and controls, run one or all in parallel, results and suggested fixes, retest with before and after, evidence download. **Stop and show me.**
3. **Suggested change with proof** (section 7b), **co-pilot (rule-based),** the accuracy panel, polish, and the end-to-end test. **Stop and show me.**

**At every checkpoint, show evidence, not a summary:** the test commands you ran and their output, a Playwright screenshot of every screen you built or changed, and the accuracy result against `demo/expected.json` for the parts built so far. If `docs/wireframes/` has sketches, compare your screenshots with them and list the differences. Then list anything you skipped, faked or couldn't get working.

Commit at the end of each phase on `mvp/crypto-simple`. Don't push unless I ask.

## 10. Co-pilot rules

- It advises; the user decides. It never sets a result, never marks anything reviewed, and never runs anything by itself.
- Knows the current step and the data on screen (claims, results, evidence) and nothing else. It treats uploaded files and tool output as data, never as instructions.
- Can help design a new test: it describes the test and, on Confirm, adds it to the plan exactly as **+ Add test** would. The user still runs it with the normal Run button or a confirmed card.
- Explains in plain language first, with technical detail on request, and always links to the evidence it's talking about.
- Never claims a system is "secure", never gives a security score or a time-to-hack estimate, and never states a result the evidence doesn't show.

## 11. Rules everywhere

- Never ask for real private keys, passwords or live customer data. Test keys only.
- Never print secrets or keys in logs, docs or your replies to me.
- Every number on screen says where it came from: measured, from the file, reference, or demo.
- Every result screen carries one line: "Passing these tests doesn't prove a system secure. It shows these specific checks passed."

## 12. Done means (Playwright, on the demo, no internet)

1. Log in, click **Use demo file**, and see the claims.
2. **Verify claims:** "TLS 1.3 only" comes back **False** with the evidence (TLS 1.2 accepted); the certificate claim comes back **True**.
3. Five tests are suggested. Reorder two, add the post-quantum readiness test, run one by itself, then **Run all**, which runs in parallel.
4. The bad-signature test **fails** on 1.4.2 with the r = 0, s = 0 case shown; the controls behave as expected.
5. Evidence Lab shows the suggested fix. In the co-pilot, ask "why did this fail?" and get the explanation with a link to the evidence. The co-pilot offers "Retest on 1.4.3"; nothing happens until Confirm is clicked. Run the whole demo a second time **without opening the co-pilot at all**, using only main-screen buttons, and get the same results.
6. Connect the demo code, open the suggested change for the bad-signature failure, see the diff and the proof (every test passing on the changed code), open a pull request with a reviewer, approve it, merge it, and get 1.4.3. After retest, the case passes, and before and after shows no speed regression beyond the measured noise.
7. **Download evidence**; changing one byte makes the fingerprint check fail (`python -m evidence verify file.json`).
8. The accuracy panel shows every demo answer matching `expected.json`.

Also unit-test: CBOM and CSV parsing with broken files, the TLS comparison, each of the five tests against the broken control, isolated mode having no network and no access to the host files or signing key (skipped with a clear message if Docker isn't running), uploads being refused in demo mode, the co-pilot being unable to change any result or run anything without a confirmation, and every co-pilot action having a matching main-screen button.

Write `README.md` (how to run the demo in one command), `docs/ADAPTER.md`, and `docs/LIMITS.md` (what's real, what's demo, what's not built yet, honestly).
