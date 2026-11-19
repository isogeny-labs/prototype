# Limits: what is real, what is demo, what is not built

Updated at the end of **phase 5c** (Otto in Evidence Lab: advisories, signed test packs, advisory checks, Otto's use of Claude; and its second part of 18 November 2026: Otto proposes and a person decides, on every tab). Most phases have their own section below. Phases 4d and 5a have none here; phase 4d's limits are in `docs/HANDOFF.md`, under "Known weak spots".

## What is real

- **The TLS checks are real handshakes.** Verify and the two server tests connect to the address and record what
  the server actually accepts and refuses. Nothing is simulated.
- **The certificate checks are real.** They read the certificate the server actually serves (key type, curve, key size).
- **The signing component really runs.** Verify runs its `info` command and one sign-and-verify round trip. The tests
  run its `verify` and `bench` commands on real inputs and record what it answered.
- **The official test vectors are the real Project Wycheproof files** (`ecdsa_secp256r1_sha256_test.json` and
  `ed25519_test.json`, C2SP/wycheproof commit `dab4ea2`, Apache-2.0), stored in `demo/vectors/wycheproof/` and
  read as data. A test refuses to run if a file's SHA-256 differs from the pinned value.
- **Every test runs a control that must fail for the stated reason.** A control that passes, crashes or fails for
  another reason makes the result "Couldn't trust this run".
- **Results come only from a review of the raw outputs.** The test is written down and fingerprinted before it runs;
  the run record is kept; a separate review step applies the rule. The database refuses changes to locked tests,
  runs, reviews and the records of a fix. Shapes are in [ENGINE.md](ENGINE.md).
- **Isolated mode really is a locked-down container** when Docker is running and the images are prepared: no
  network, read-only files except a scratch folder, a non-root user, no extra permissions, memory, processor and
  process limits, a time limit, and nothing from this computer mounted in. Tests of our own code check this.
- **The speed numbers are measured** on this computer, by the component timing itself. The slowdown rule and the
  measured noise band are written into the locked test.
- **The evidence file is really signed** and `python -m evidence verify` fails on any one-byte change.
- **Both import formats are parsed for real** (CycloneDX 1.6 CBOM JSON and our CSV template). Nothing in an
  imported file is ever executed.
- **Login is real:** you create a password on first run; only a scrypt hash is stored.
- **The demo repository is a real git repository.** `demo/repos/acme-sign.git/` is in git's own format, and so is
  the working copy the app makes of it in `data/repos/` when you press Connect demo code. The branch of the
  change, its commit and the merge commit (with two parents) are real objects that git itself can read. The app
  reads and writes them with its own small code; no git program is needed or run.
- **The suggested change is a real change to real code:** 3 lines added and 1 removed in `acme_sign.py`, written
  on a new branch of that copy. The before and after lines on the screen are read from the copy.
- **The proof really reruns the tests.** Every test in the locked plan runs again, through the same test runner and
  the same automatic review as a first run, with the old and the new version timed side by side. Whether the
  change is offered is decided by the review step from the stored records, never by the fix template. That
  decision is worked out again every time it is shown: if the stored records no longer give the same answer, the
  screen says the proof can't be trusted and the change is not offered.
- **The patch is a real patch.** Download patch gives a file that git can apply. Our end-to-end test applies it
  with git to a copy of 1.4.2 and gets our 1.4.3, byte for byte.
- **Nothing is merged without a person.** A merge happens only when every picked reviewer's approval is on record
  and someone presses Merge pull request and then Confirm merge. The app deploys nothing.
- **Every result says which code it ran on:** the "Code" item in its run record, and the notes under the before
  and after headings. Each run writes this down when it starts.

## What is demo

- **The demo file** (`demo/acme-pay-cbom.json`) describes a fictional "Acme Pay" service. It is labelled *Demo data*.
- **The demo TLS server** is a small server the app starts on `localhost:8443`. It is deliberately set up to accept
  TLS 1.2 with an older cipher as well as TLS 1.3.
- **The demo certificate** is a self-signed test certificate the app makes on first start (ECDSA P-256).
  It and its test key live in `data/` and are never shown in evidence.
- **`acme-sign` 1.4.2 and 1.4.3** are our own small demo programs written for this demo. 1.4.2 has one planted bug
  (it never checks that the two signature numbers are in range, so it accepts r = 0, s = 0). 1.4.3 is the same file
  plus that check and its own version number. They are slow, simple Python and are not production software.
- **The bug is still planted, but the code no longer points at it.** In phase 3a the comments in 1.4.2 that said
  where the bug is ("DELIBERATELY FLAWED", "PLANTED BUG") and the two maths comments that explained how r = 0,
  s = 0 gets through were removed; 1.4.3 lost the same comments. The bug itself stays, on purpose, and the screens
  label `acme-sign` *Demo data*. No answer changed: the accuracy check still matches all 15.
- **The demo repository** (`demo/repos/acme-sign.git/`) is bundled demo data: one commit that holds `acme-sign`
  1.4.2. It is the only code that can be connected.
- **The suggested change comes from one fix template,** for one kind of bug (the missing range check), written for
  `acme-sign`'s code. It is labelled "From a fix template" and is not written by an AI model. What it produces is
  exactly our bundled 1.4.3. (Since phase 5c Otto writes a change of its own when an advisory check has failed. Since
  18 November 2026 the demo offers that change, as a proposal, and the template is the fallback where Otto is not
  installed: see "Limits of phase 5c".)
- **Pull requests live inside the app only.** Nothing is sent to any code host. "Merged" means the main branch of
  the app's own copy in `data/repos/` moved to a merge commit. Nothing is deployed, and no other program on this
  computer changes.
- **"Demo reviewer A" and "Demo reviewer B" are *Demo data*, not people.** The app has one login and no separate
  accounts, so whoever is at the keyboard records each approval of a pull request, under the reviewer name shown.
  The screen, the evidence file and the report say so too.
- **The controls are ours too:** an accept-everything signer, a deliberately slowed signer (6 ms added to every
  sign and verify), a test server that accepts an older TLS version, a test server with a deliberately weak
  RSA 1024-bit test certificate, and a test server that does offer the post-quantum key exchange.
- **The bad-signature list** (16 cases: 14 that must be rejected, 2 genuine ones that must be accepted) was built
  once by us from a throwaway test key that was then discarded. It is fixed data, not an official set.
- **Demo mode is not isolated.** Without Docker, or before the images are prepared, the demo components run as
  normal local programs with a time limit. The line under the step bar says which mode is in use and why.
- **The server TLS suggestion** was text only in 3a. Since phase 4b it is also a change box that can be tried on a test copy
  and applied to our own Acme Pay demo server (see "Limits of phase 4b"); on any other server it is text and a download. The nginx and Apache lines in it were tried on real servers on the build machine. The two AWS
  policy names are from memory, because the AWS documentation could not be reached from the build machine. The
  app's server test checks TLS versions only, so it cannot show whether an old cipher suite has gone.
- **The "Suggested fix" text in Evidence Lab is a fixed sentence.** A failed result whose fix is in the Fixes step
  shows one line that points there instead. Every other result keeps its fixed sentence (for example "None needed").

## Not built, or not connected, in this version

- **Uploading outside software is not in this version** (owner decision in phase 2). There is no screen, button or
  API address that accepts software. What runs is fixed in the app: our own demo components, the pinned lab images,
  and since phase 4c the real libraries listed in "Limits of phase 4c" below, each in an exact version, in isolated
  mode only. Retest chooses only between the versions the app knows for a program (our two demo versions, 1.4.2 and
  1.4.3; the affected and the fixed version of a real library). A file that names any other software gets
  "Couldn't check" in Verify and "Couldn't run (only our demo components can be run in this version)" in the tests,
  and "Not tested, and why" says so on the Tests and Evidence Lab screens. (That sentence is older than phase 4c: read
  it as "only the software this version knows".)
- **The engines that propose and review are fixed rules.** Tests are proposed by fixed rules and reviewed by fixed
  rules. Both are code from this same build, written by the same people: the review is a separate step with
  its own module, not an independent second opinion. Until phase 5c no AI model was connected at all. Since
  phase 5c Otto uses Claude for four named jobs and decides nothing: see "Limits of phase 5c". The assistant
  panel still has no AI model.
- **Dig deeper answers nothing.** It saves a research request marked "waiting for research engine" and shows it as
  queued. Nothing looks into it, and there is no screen for an answer yet.
- **Connecting real code hosts (GitHub and others) is not in this version.** Only the bundled demo repository can
  be connected, and only for a file that names our demo component `acme-sign` 1.4.2.
- **The assistant panel is still empty** (phase 3b). Also not built yet: the server setting change with proof
  (SPEC 7c, the next step), change watch (phase 3c) and the accuracy panel inside the app (phase 3b). The accuracy
  check is a command for now (`python -m app.accuracy`).
- **Change watch (phase 3c) is only prepared for.** Fixes record where they came from, every result records which
  code it ran on, and the repository, branch and proof code is not tied to the 1.4.2 fix. The spec names its
  design file, `docs/design/change-watch.md`; that file was not on this branch when phase 3a was finished
  (13 November 2026).
- **Mark reviewed** only records that you looked at a result, with the time. There is no undo and no name (there
  is one local login).
- **The catalog has two extra tests** (post-quantum readiness and the ML-DSA-65 comparison). No others.
- **No Ed25519 signing component exists in the demo.** `acme-sign` only does ECDSA P-256, so the official Ed25519
  file is run against the reference library only. That shows the file and the reference agree; it says nothing
  about any Ed25519 software of yours.

## Limits of the migration plan (phase 4a; 14 November 2026)

What is real:
- **The status is measured.** For a server: three hand-built first messages (hybrid only, ML-KEM by itself only,
  classical only, each with no key attached), the TLS version handshakes, one full hybrid handshake and one as a
  classical-only client. It needs no Docker and no OpenSSL program. For a signing program: what it reports,
  confirmed by an independent library checking one signature.
- **Hybrid is only ever said on positive proof** (the server asks for a hybrid key, or completes a hybrid
  handshake). Classical needs a TLS refusal of every post-quantum attempt and a classical handshake that completed. Silence,
  a time-out or an unreadable answer is "Couldn't check", never a status.
- **Every measurement has a control:** the same check must read our own hybrid test server as Hybrid and our own
  classical one as Classical in the same run, or the run is not trusted.
- The nginx and Apache lines in the "turn on hybrid" how-to were checked on real software during the build
  (nginx 1.31.8 and Apache 2.4.71, both with OpenSSL 3.5.9, in containers; nginx 1.24.0 with OpenSSL 3.0.13 for
  the "stops it starting" warning). Every other config line is labelled "Not checked on real software".

What is demo:
- The five servers of `demo/migration-demo.csv` are test servers this app starts on this computer (8451 to 8455),
  with test certificates made at start. The hybrid and the post-quantum-only one are run by the copy of OpenSSL
  inside the `cryptography` library, pinned to version 50.0.2.
- `acme-sign 1.4.2` is our own demo program. `acme-sign 9.9` is not one of ours and can't run: Couldn't check.
- The five test servers start only for exactly that file: the same claims and the same settings rows. A file of
  your own that makes the same claims starts nothing, and its addresses are checked like any other.

Limits to know:
- **The three public servers in `demo/migration-real-servers.csv` were not measured by the build.** The build
  machine has no direct internet. Kevin runs that file by hand and compares with Cloudflare Radar. What the app
  is expected to say is in the phase 4a plan, not in a checked answer.
- **The migration answer key** (`demo/expected-migration.json`, written by Isogeny Labs and added to the branch
  as commit `f961f66` while this phase was being built) is compared by the accuracy command: its 28 numbered
  answers (MV, MS, MR, MP), the two expected Fixes suggestions, "text only, nothing else", and the controls.
  The app matched all 32 without being changed to fit. The command reads exactly that file's layout: anything
  in the key it does not understand is reported as a mismatch, never passed over. The key's line about the Acme
  Pay demo is checked by the other half of the command (`demo/expected.json`).
- **The post-quantum engine is a private part of a library.** The test servers and the full handshakes use
  OpenSSL through `cryptography`'s internal bindings, which that library does not promise to keep. The version is
  pinned. If that part stops working, the app says "Couldn't check" for every server status, the hybrid and
  post-quantum-only demo servers don't start (and say so), and nothing crashes or is guessed. The hand-built
  hellos alone are not used to give a status in that case.
- **A status is about key exchange only** (and, for a program, the signature algorithm it reports). It says
  nothing about cipher suites, certificates' chains, or what real clients negotiate. "Post-quantum only" is the
  server refusing our classical and hybrid hellos; a group this version doesn't offer could still be accepted.
- **Groups tried:** X25519MLKEM768, SecP256r1MLKEM768, SecP384r1MLKEM1024; ML-KEM-768, -1024, -512; X25519,
  P-256, P-384. A server that offers only some other hybrid reads as Classical or Couldn't check.
- **A server that accepts ML-KEM by itself and classical, but no hybrid,** reads "Couldn't check": this version
  has no name for that status.
- **Costs:** sizes are measured on the system where it already does the thing, otherwise published (FIPS 203,
  FIPS 204) or "measured on our test server" (this computer, loopback). Handshake times are medians of 10 on
  loopback: they show scale, not what a real network adds. Full post-quantum handshake time is not measured.
  For a signing program the ML-DSA-65 column is the reference library, not software of yours.
- **The recommendation is a small fixed table** (`migration/rules.py`): status, data lifespan, exposure, can it
  be changed. It knows nothing else about your systems. Defaults are the careful reading and are labelled
  "assumed": long-lived data; internet-facing for a public address, internal otherwise.
- **Full post-quantum is never recommended** unless the system is already there, because the app can't see the
  clients. "Wrap the connection" names no product and measures nothing about a gateway.
- **Blockers checked:** no TLS 1.3, a certificate below the NIST minimum, a program that can't make post-quantum
  signatures. Nothing else (firewalls that drop large first messages, client support) is measured; the how-to
  warns about the first two in words.
- **Fixes entries from the migration plan** were text only in phase 4a. Since phase 4b each is a change box (see "Limits of
  phase 4b"). The app still never tests the suggested lines on your own server. An entry closes when a new
  measurement shows it done or the plan for it changes.
- **Choices:** one login, so a choice is recorded for "whoever is at the keyboard". A choice is never changed by
  the app; a newer choice is a new record and the older ones stay. If a later measurement makes a choice
  impossible (the system now measures Hybrid and the choice was "keep classical"), the roadmap goes back to the
  recommendation and the choice stays in the record.
- **Review dates** are checked against the computer's clock (UTC date) when saved. Nothing reminds you when one
  passes.
- **A program that can't run** now has no test cards and no result rows (only its line under "Not tested, and
  why"). A plan made before this change keeps the cards it had.
- **Post-quantum readiness (the catalog test)** now uses the same measurement, so it gives a result without
  Docker. A test of that kind locked before phase 4a keeps its old checker and rule, and its stored results read
  as before.

## Limits of phase 5c (Otto in Evidence Lab; 17 November 2026)

### What is real

- **The six advisories are real and published.** Every quoted line is an exact piece of a page or file downloaded on
  17 November 2026, kept with the SHA-256 of what was downloaded (`research/snapshot/2026-11-17/`; its `README.md`
  lists every source, its licence and the pinned commits). They are not Demo data.
- **Every shipped test and fix was tried before it shipped.** Each trial ran on public copies of the affected and
  the fixed version, in isolated mode, through the app's own runner and reviewer, as an experiment registered in
  Otto's harness before its first run. The harness judged the numbers against thresholds frozen in that
  registration. The research ledger (`research/lab/`, 103 entries: six registered trials, three of tests and three
  of fixes) holds all of it and passes Otto's own audit; a test of our own code runs that audit.
- **The packs are really signed** (Ed25519). A pack with one byte changed, a pack signed by an unknown key and a pack
  out of order are refused, each with one plain sentence.
- **Results still come only from the runner and the reviewer.** An advisory check is an ordinary locked test with a
  control that must fail. Advisories, the packs and Otto's ledgers only repeat or bind. None of them words a result.
- **An advisory check uses no network.** It hands published signatures to a program or a library copy and reads its
  yes or no. Otto never touches a live system, and the research side has no way into an assessment.
- **The Otto part of the evidence file is inside what is signed.** `python -m evidence verify` checks the file, the
  packs and the assessment's ledger together.
- **The harness is Adam's code, unchanged,** at one pinned commit, checked by its fingerprint before it is used.

### What the packs hold, and what the checks catch (measured, not tuned)

These are the build's own measurements, as the packs and the recorded runs hold them. The fifth answer key is
written independently and must not be copied from this section (`docs/OTTO-KEY.md` says what to work from).

- **CVE-2022-21449** ("Missing ECDSA signature range check", Java): 77 cases. `openjdk` 17.0.2 got 10 wrong, 17.0.3
  none, and the accept-everything control all 77.
- **CVE-2019-14859** ("Badly encoded signature accepted", python-ecdsa): 9 cases. 0.13.2 got 8 wrong, 0.13.3 none.
- **CVE-2019-14853** ("Malformed signature raises unexpected error", python-ecdsa) reads **No test yet.** Its
  recorded design picked exactly the nine cases of the check for CVE-2019-14859, an advisory about the same
  library, so it was refused before any trial as the same check under a second name (see the limits below).
- **CVE-2024-42460** ("Wrongly encoded signature accepted", elliptic): 1 case, case 6. 6.5.6 got it wrong, 6.5.7 right.
- **CVE-2024-42461** and **CVE-2024-42459** (elliptic) read **No test yet.** Claude's design step answered that no
  test fits the building blocks of this version, and gave its reason: the first needs a longer signature from a
  larger curve, the second is in EdDSA.
- **The fixes.** "Update python-ecdsa to 0.13.3" (for CVE-2019-14859; all 4 pass-or-fail tests passed on 0.13.3, 3
  failed on 0.13.2) and "update elliptic to 6.5.7" (all 5 passed on 6.5.7, 2 failed on 6.5.6) are **proven**: on
  the fixed version the advisory check passed and every other pass-or-fail test passed too. "Update Java to 17.0.3"
  is **not proven** (see the limits below).
- **On the Acme Pay demo** the three ready tests all fit `acme-sign` 1.4.2. The check for CVE-2022-21449 fails on
  it (3 of 77 cases wrong: 168, 171 and 364, the planted bug). The other two pass.

### Limits

- **The first advisory checks find nothing the full exam would miss.** Each one reruns a slice of the Independent
  exam (the same Wycheproof file of 484 cases). What they add is the link from a published advisory to measured
  behaviour, your own code included, and a reason to look again when a pack arrives. New detection needs a new
  building block.
- **One building block: "run these published signature cases".** ECDSA P-256 signatures, checking only. It can't
  test another curve, hash or signature scheme, signing, timing, or a crash that the program turns into a plain
  rejection. An advisory that needs any of those reads "No test yet", with the reason.
- **Signing programs and libraries only.** An advisory about a server can't become a test yet. That needs a
  handshake building block (phase 5d).
- **CVE-2019-14853 has no test, because its design was a copy of another advisory's check.** The advisory is about
  the kind of error python-ecdsa raises for a malformed signature. The one building block can't show that: by the
  owner's rule an error raised by the library counts as "not accepted" (phase 4c). The recorded design therefore
  picked the nine badly encoded signatures that the check for CVE-2019-14859, an advisory about the same library,
  already uses. Such a check would pass or fail together with that one and could not tell the two weaknesses apart,
  yet its name would say it measured this advisory. So the design was refused before any trial, the advisory reads
  "No test yet" with that reason, and no fix is offered for it.
- **What the duplicate rule does, and what it leaves.** A design is refused only when another advisory about the
  same library has a check with exactly the same published cases: a test of an earlier pack, or a design of the
  same build whose own trial held. The advisory that comes first keeps the check; the order is the order of the
  snapshot. A design with one case more or one case fewer is not refused, so two checks can still overlap. The
  same cases for another library are allowed on purpose (the same weakness in two libraries is two advisories, each
  with its own fix), so on a program of your own two such checks would rerun the same cases under two names.
- **The packs in the repository are the third build.** The independent reviews changed the research script twice,
  and a pack names its scripts by fingerprint, so each time the research was run again from an empty ledger with
  the same recorded answers. The first build (17 November 2026) shipped the duplicate check above as "Test ready"
  (four tests in all); the second added the rule; the third (18 November 2026) corrected it as described above.
  Every trial that is in more than one build gave the same numbers each time. The two earlier builds are kept in
  this branch's git history (commits `370a380` and `8789c4b`), not in the working files; if the branch is squashed
  when it is merged, they stay reachable through pull request #6. Nothing had shipped. From the merge of this
  phase on, a pack that is in the repository is never rebuilt. Whether building again before the merge was right
  is the owner's call: the rule in `CLAUDE.md` says "a shipped pack is never rebuilt".
- **One sentence inside pack 2026.11.2 has a wording slip.** The pack's own line about the test for CVE-2024-42460
  reads "elliptic 6.5.6 got 1 of 1 cases wrong". It is part of the signed pack, so it stays as it is, and the
  Advisories panel shows it that way. The lines the app words itself say "1 of 1 case wrong", and the pack builder
  words the next pack right (`ottolab/build.ready_reason`).
- **No shipped advisory reads "Not offered".** The plan expected one design to be tried and refuted. In the real
  build no design was refuted: for CVE-2024-42461 the design step answered "no test fits" instead, and for
  CVE-2019-14853 the design was refused before it could be tried. The refuted path is real and tested on a made-up
  snapshot, where a design that can't catch the affected version comes out refuted and stays out of the pack
  (`backend/tests/otto/test_research.py`).
- **"Update Java to 17.0.3" reads "not proven", by the strict reading of "every other locked test still passes".**
  On 17.0.3 the check for CVE-2022-21449 passes, but the Independent exam still fails (the three cases listed under
  phase 4c), so 1 of the 4 pass-or-fail tests did not pass. The screen says what was measured and nothing about how
  serious it is. Counting only the tests that failed before the fix would call this fix proven. Which reading to
  keep is the owner's decision.
- **A check can fail on a library its advisory does not name.** Case 6 (a number written without its leading zero)
  is the one case of the check for CVE-2024-42460, an elliptic advisory. Java gets that case wrong too: the
  accuracy walk in isolated mode (17 November 2026) read that check as Failed on Java 17.0.2 and still Failed on
  Java 17.0.3, although no advisory names Java for it. The research trials did not run that pair, so no pack
  states it: the app's own run on the Real libraries file is what shows it. Such a result says which case got the
  wrong answer, and nothing more. A pack's fix is for the library its advisory names, so for another library Fixes
  says that the test pack holds no fix for it, and that entry carries no "From Otto" label.
- **Otto's own change for `acme-sign` is offered because its program was registered by hand.** The recorded answer
  is a clean change that names all three failed tests, and the program it gives is one line different from our own
  `acme-sign` 1.4.3 (the same range check, written another way). Only our registered demo programs may run. In the
  first build that program was not one of them, so the change was not offered. On 18 November 2026 Kevin decided to
  register it as a demo program of its own, `acme-sign 1.4.3-otto`
  (`demo/components/acme-sign-1.4.3-otto/acme_sign.py`). So the demo now shows a fix labelled "Written by Otto"
  going the whole way: proposed, accepted, proven on that program, approved, merged, retested. What this is, and
  what it is not: the file is exactly what the app's own change checker gives when it applies the recorded answer
  to 1.4.2 (a test of our own code holds it to that); it is in the repository, where anyone can read its one line of
  difference; it was added once, by a decision, not by the app. The app still decides nothing about code it has not
  got: a live answer that differs by one character from every registered program is still refused. The program is
  not in the general list of versions; a retest can choose it only in an assessment where its change is merged.
- **Where Otto is not installed, the fix template stands in for Otto's change.** A decision on a proposal is
  recorded in Otto's ledger, which the harness keeps. Without it no decision can be recorded, so Otto's change is
  not offered and Fixes says so; the fix template is offered, as before phase 5c.
- **Running a program that Claude wrote, and that is not registered, is not in this version.** A live answer will
  usually not be one of our registered programs. With Live Otto on, such an answer is refused at the click and nothing is connected, although the
  request was made on the key and is paid for; the fix template is offered afterwards where it answers the
  failure. Until the click, Fixes lists that fix as "Not written yet" (never as written by Otto) and its card says
  all of this before anyone presses the button. Proving a change that is not a registered program would mean
  running code Claude wrote. That needs the owner's decision and a sandbox design first.
- **The recorded answers were not made through the API.** No API key exists in the build environment. Every answer
  shipped in `research/recorded/` was made during the build by giving the exact prompt to Claude in a fresh helper
  session with nothing else, and was stored word for word. Each is labelled "Recorded during the build, not through
  the API" and names no model. Tests, screenshots and the accuracy check use only these. A prompt with no recorded
  answer gets "No recorded answer: this needs Live Otto."
- **Some words on screen were written by Claude.** An advisory's plain name, the one plain sentence about its
  weakness, the affected versions, its notes, the test's question and why-line, the reason given for "No test yet"
  and a fix's summary are Claude's words, from the recorded answers. So is the title of an advisory check, which
  carries the plain name. They are checked for their shape and for words this app never says about a system, and
  every line quoted from a publisher must stand in the publisher's text, character for character. Nothing else
  checks that such a sentence is right, which is why the publisher's own line is shown beside it. The notes are
  folded in the panel under "Otto's notes on reading it" and labelled as Claude's words; they can be long, and they
  name sources by their short labels (S1, S2), which the Sources list above them spells out. No result is
  worded by Claude: the sentences of a check's result are fixed templates.
- **A recorded answer belongs to one exact prompt.** If one word of a research prompt changes, its recorded answer
  no longer fits: new answers must be recorded and new packs built, and a test of our own code fails until then. If
  the app's own prompt changes, Fixes says "No recorded answer: this needs Live Otto." until a new answer is
  recorded.
- **The live path is not proven by a real call.** It could be tested here only with no key present and with a
  stand-in for the network. No real call has been made by the tests.
- **Live Otto sends source code out.** For a fix to your own code, the source file of the failing program and the
  cases it got wrong go to Claude through your key, with the advisory text. Live Otto is off by default, also when a
  key is present, and the setting says what is sent.
- **Cost.** The spending limit (2 US dollars per run until changed) stops a run before the request that could pass
  it, also a request that is sent again. It counts the worst case of that request (a full-length answer at the
  dearest price that could apply, twice where a declined request may be answered by another model), so a run can
  stop early. A request that got no answer that can be read (a time-out, an answer cut off part-way, an answer
  that is not what the API sends) may still have been billed, so the most it could have cost counts against the
  limit too, and in the research command that is carried from step to step. The price list is a config value and can go out of date; Settings shows its source and
  date. One model answers every step.
- **The live call is made with Python's standard library,** not with Anthropic's official package. Adding that
  package would be a new dependency and needs the owner's OK.
- **Otto is private, so not every computer can run the Otto checks.** GitHub's checks can't fetch it (they use no
  secrets): the tests that need it are skipped there, with one line that says how many, and run only where the
  harness is installed. Someone who checks an evidence file without the harness gets the verify command's own
  checks and "not confirmed" for Otto's audit, which is not a pass. A new Codespace needs the access that
  `.devcontainer/devcontainer.json` asks for.
- **Otto is version 0.1.0.** A newer version may change its record formats, and a ledger written under this one
  could then fail its audit. The pin, and an audit at every move of the pin, guard against that. There is no
  promise yet about reading older ledgers.
- **Otto's harness starts programs with no sandbox of its own.** In this version it starts only five small scripts
  of ours (the research agent command, the trial script, and three record checkers: one on the research side, and in
  an assessment's folder one for runs and Claude steps and one for decisions). The trial script calls the app's own lock, run and review path, so a real library still runs only in its
  locked-down container.
- **Otto does not run on Windows.** Its ledger locks files the Linux and macOS way. On Windows the app says Otto is
  not installed.
- **The harness's fingerprint covers the files of the pinned commit, and nothing else in its folder.** Python's own
  cache folders (`__pycache__`), compiled `.pyc` files and links in that folder are left out, so that running Otto
  does not change the fingerprint. Someone who can write to that folder can therefore change what runs without
  changing the fingerprint, as they could change the app's own code. The check guards what was fetched, not a
  computer that someone else can write to. `EVIDENCE_LAB_OTTO_HOME` lets that folder be anywhere; the same holds
  there.
- **A data folder that holds packs from an earlier build of this phase can't go on.** The form of a pack changed
  during the build (a source now says where its text was read from), and the two packs were built again under the
  same version numbers. A data folder that installed an earlier build's packs can't read them and can't install
  the new ones after them. Settings says so in one line. Start with a new data folder: stop the app, move the folder
  `data/` away and start the app again. A new Codespace starts with a new one.
- **A ledger can't be rebuilt byte for byte.** Clock times are inside its hashes. So the research ledger in the
  repository is audited, never made again and compared, and a shipped pack is never rebuilt.
- **The demo pack key can sign nothing more.** It was made when the packs were built and its private half was
  thrown away. Who holds a real release key is not decided. A pack built on this computer by the research command
  is signed with a key made here (kept in the data folder, readable by this user only) and is trusted by this
  installation only.
- **Authors in Otto's ledgers are plain names.** Otto signs nothing. The "second author" who replays a trial is a
  second role of the same build on the same computer, not a second person or a second machine, and the Advisories
  panel words the replay that way ("run again as a separate replay step of the same build, on the same computer"). The evidence
  signature covers the assessment's ledger. The research ledger is named by the pack (its latest entry) and stays
  in the repository.
- **The assessment's Otto ledger confirms binding, not results.** It shows that a run belongs to a test locked
  earlier and that the reviewer was not the proposer. It does not redo the review; Evidence Lab's own read gate
  does that each time a result is shown.
- **Without Otto, advisory checks can't be added or run,** because their runs could not be recorded. A check added
  earlier then reads "Couldn't run (Otto is not installed on this computer)". Everything else works as before.
- **"Keeps checking" means on events.** There is no timer. A check reruns when a person clicks, and where the app
  already reruns by itself (fix proofs and retests). A new pack never adds or runs anything by itself.
- **Packs come from a folder on this computer.** Check for updates never uses the internet. There is no update
  channel yet.
- **A real library's advisory check needs isolated mode.** In demo mode it reads "Couldn't run (needs isolated
  mode)".
- **Speed is not part of a fix trial on public copies.** Timings hold only for the computer they are measured on.
  Retest measures speed on yours.
- **Evidence files grow.** The pack files (whole), the assessment's ledger, every bound run and every Claude step
  with its full prompt and answer travel inside the file.
- **A source's link opens what was read, which is not always a web page.** The quoted text was downloaded from the
  files themselves (the advisory database's records and the libraries' source files, at pinned commits), and the
  link beside a quote opens that address, so "Read on 17 November 2026" is true of what it opens. For a file in a
  repository that is the raw file at its pinned commit, not the repository's web page. A pack also keeps a page
  address for each source, written from the record's id or from the repository, the tag and the path; those pages
  were not opened by the build and are not what the links open. The web pages of github.com, nvd.nist.gov and
  cve.org could not be reached from the build machine (the snapshot's `README.md` has the full list).
- **A quoted line is not always from the advisory page.** Oracle's and OpenJDK's pages for CVE-2022-21449 do not
  put the weakness into words, so its quoted line is the range check in the fixed JDK source. Some quotes are a
  raw field of an advisory record (`"fixed": "0.13.3"`). Each quote names its source and publisher, and its tag
  reads "quoted from the named source, not a result".
- **The verify command runs nothing that a file names.** A ledger inside an evidence file is data. Otto's harness,
  asked to check entries again, starts the verifier an entry names, and it finds that entry by its id whatever its
  kind. So the command never asks it to. Every entry must first be in the exact form this app writes (its kind,
  its fields, the one checker an objective may name, each pointer to an earlier entry of the right kind); the
  harness then audits the chain and the records without running any verifier; and the app runs its own pinned
  checker again on every checked entry. Two independent reviews of the phase found holes here before it shipped:
  first, that the command would have started what an objective named; then, after that was closed, that an entry
  of another kind could still pose as an objective. Both are closed, and tests plant such files to show that
  nothing runs (`backend/tests/otto/test_verify_reads_data.py`). What this rests on: the harness's audit without
  re-verification starts nothing. That is true of the pinned commit and must be looked at again when the pin moves.
- **The research audit command reads a lab folder as data too.** `python -m ottolab.build audit` no longer asks the
  harness to run anything: the harness checks the chain and the records and derives every decision again, and the
  command runs the research side's own pinned checker itself. A lab folder that holds a link is refused before
  anything is done. A fourth review found that the folder's own copy of the checker could be made to stand for
  another program; nothing from the audited folder is started now, and tests plant such folders
  (`backend/tests/otto/test_research_audit.py`).
- **The checkers in an assessment's Otto folder are made the app's own before each use.** There are two since
  18 November 2026: `recheck.py` (runs and Claude steps; unchanged, so earlier ledgers read as before) and
  `decisions.py` (decisions on proposals). The harness starts the file
  in that folder when a run, a Claude step or a decision is recorded. If someone who can write to the data folder puts another
  program or a link there, the app replaces it with its own checker first. The check guards the file at that moment;
  it does not make a computer safe that someone else can write to.
- **What the verify command binds, and its limits.** A run shown in the file must match the SHA-256 the ledger
  holds for its record and its review; the words that describe the result beside it are covered by the file's own
  signature, not by the ledger. A ledger of more than 20,000 entries is refused, and checking entries again stops
  after five minutes with a failure, so a very large honest ledger would need those limits raised.
- **The fifth answer key is not written yet.** `demo/expected-otto.json` is written independently of the build.
  Until it is in the repository, `python -m app.accuracy --only otto` shows the app's answers and grades nothing
  (exit code 2, which is not a pass; 3 when Otto is not installed). `docs/OTTO-KEY.md` lists its questions.
- **Verify still has no locked test and no separate review** (phase 5d), and Verify runs are not entered in Otto's
  ledger.
- **Not built, in the order planned:** Verify under a locked test and the reviewer, then Otto's server checks by
  handshake (5d); running code that Claude wrote; Otto as the assistant in the side panel, answers to Dig deeper and
  proposals for the knowledge base; moving the seven built-in
  tests into the pack library; separate accounts, so that "who" is more than one name; a timer; packs over the internet and a real release signing key; Otto's sealed
  claims, its Lean proofs and its model judge.

### Limits of the second part: Otto proposes, a person decides (18 November 2026)

- **"Who" is one name.** The app has one login and no separate accounts. Every accept, reject, undo and reconsider
  is recorded as made by "You", the name the app already records for approvals, with the time. It shows that a
  person at the keyboard decided, and when; it can't show which person. Every list of decisions says so.
- **Proposals are worked out, not stored.** Each time a page is read the app works out what Otto proposes from the
  installed packs, the file and the results. Only a person's decisions are stored, each with a copy of the proposal
  as it stood and that copy's SHA-256. So a proposal that was decided and that Otto would no longer make stays on
  the record, marked as no longer proposed. A proposal that nobody decided and that no longer applies is simply no
  longer shown: nothing records that it was once proposed. The time a proposal says it was made is worked out too
  (the later of the pack's installation and the file's import).
- **A decision is a record, not a result.** The second pinned checker confirms that a decision entry is whole and
  that the step was allowed from where the proposal stood. It can't confirm who pressed the button, and its answer
  is never shown as a decision or as a result.
- **What the ledger binds of a proposal, and what it does not.** A decision's ledger entry holds the SHA-256 of the
  proposal as it stood when the person decided, and the file carries that copy. A proposal nobody decided on is not
  in the ledger at all: in an evidence file it is covered by the file's own signature only. The same goes for the
  present wording of a proposal that was decided earlier and that Otto still makes (its `why` can change with a
  newer result); the copy each decision was made on is what the ledger holds.
- **Two stores, written one after the other.** A decision goes into Otto's ledger and then into the database. The
  app shows the entry to its own checker before it writes anything, so a refused entry changes nothing. If the app
  is stopped in the moment between the two writes, the ledger holds a decision that the database does not, and an
  evidence file of that assessment then fails the verify command, which says which decision the file does not
  show. There is no repair tool in this version. If the ledger's own check of the entry gives no answer in time,
  the decision is not recorded, the attempt stays in the ledger marked as not accepted, and the verify command
  says that it is no decision.
- **Undo has an end.** A check can be taken out again until it has a run; a change to your own code until the code
  is connected; a library's update until a retest on the updated version is running or has run; a plan change until
  a newer result of its check has passed. After that the accept stands, and the button says why. A check that was
  added with the earlier **Add new checks** button has no decision on record: it reads "Added before decisions were
  recorded", can't be undone from Advisories, and keeps its own × in the test plan.
- **A rejected fix has no stand-in.** When a person rejects Otto's change for their own code, the fix template is
  not offered in its place: the fix reads "Not added (reason)" until someone presses **Reconsider**. The template
  stands in only where Otto's change is not offered at all.
- **Proposals for the migration plan: one rule.** An advisory check whose newest result on a signing program is
  Failed proposes "Fix *program* before its signatures move to post-quantum" on that program's Signatures track.
  No other test proposes anything, and nothing is proposed for a server (Otto's server checks are phase 5d).
  Accepting lists it on the plan as something to fix first. It changes no status, no recommendation, no roadmap
  band and no measured fact, so everything the migration answer key grades reads exactly as before. "Accept
  updates the plan" is built as that listed line, and nothing more. A plan change needs a plan: it is proposed only
  once **Measure status** has given that system a status. A failed advisory check on a program whose status was
  never measured proposes a fix (on Fixes) and no plan change, and no page says that one will follow. (The second
  review found the earlier form proposing a change to a plan that the Roadmap said did not exist.)
- **Proposals for a dependency: one rule.** A library of the dependency list is "named by an advisory" when the
  knowledge base has recognised it as the package an advisory of the installed packs is about (by its package
  address; a bare name only where the list gives no address and the knowledge base lists that name as safe), and the
  version in the list reads as lower than the publisher's fixed version. A package of the same name from another
  ecosystem is not named, a library the knowledge base has no file for is not named, and a version the app can't
  read is not named. A decision belongs to the library in that version and to the advisory, not to a place in the
  list. Where the pack carries an update for it,
  Otto proposes it. Accepted, the library reads "Update first", and the box of the system it is tied to says so.
  It is never counted among the blockers, and no answer about what a library can do changes, so everything the
  dependencies answer key grades reads exactly as before.
- **"Measured affected" is rare by design.** "Measured" is only this assessment's own reviewed result of that
  advisory's check on the same library and version. An advisory check runs on the signing programs the scanner
  file names, not on a library that is only in the dependency list. On the Acme Pay demo the dependency list names
  three such libraries (openjdk 17.0.2, python-ecdsa 0.13.2, elliptic 6.5.6) and the scanner file names none of
  them, so all three read "not yet checked", each with that reason. The trial on public copies is not counted as a
  measurement of your library: it is said where the fix is.
- **"Proven on your system" is a retest on a public copy.** The row's name is the owner's wording. What stands
  behind it: this assessment's own retest of the same locked tests on the fixed version, which the app runs on a
  public copy of that version in its own container. The app has no connector to the system a customer runs, and
  the row says so right under its sentence, at the size of the text ("This row is about a public copy, not the
  system you run ... The app has not checked that your own system was updated"). "Passed" therefore means the
  fixed version passes the locked tests here, not that anyone's deployed system was updated. A reader who takes
  in only the row's name and the green word can still read more into it than it says; another name for the row
  (for example "Proven in this assessment") is the owner's call. After such a retest the scanner file still names
  the old version, so Verify still reads that claim as true of the file.
- **A library's fix that passed its retest still counts as Open.** Its status word stays "Text only", by the
  owner's rule that the app never calls other people's software fixed, and the page counts by that word. The two
  proof rows say what was shown.
- **Two entries for one update.** Where the Independent exam and an advisory check both fail on a real library,
  Fixes lists the entry for the failed tests (phase 4c) and Otto's proposal. They answer different tests and only
  Otto's is a proposal, so they stay two entries; each names the other and says "It is one update, not two."
- **The pack does not name the other test that still fails.** For Java the first row reads "another locked test
  still fails on 17.0.3". The shipped pack records the counts of its fix trial (1 of 4 on 17.0.3), not which test,
  and a shipped pack is never rebuilt. A retest in the assessment names it.
- **The Overview builds each of its blocks afresh.** On a large assessment (eight tests, a proof, a retest, a
  dependency list, two test packs) its data takes about a second and a half to build on the build machine, and
  Otto's proposals are about a quarter of that. Nothing is kept between the blocks of one read. Closing such an
  assessment shows "Closed" as soon as the close itself has answered; the rest of the page follows a moment later.
- **A check added after a retest first runs on the old version.** Run runs a test on the version the scanner file
  names. A check accepted after a retest therefore has a first result on that version and no result after, until
  the next retest. Evidence then counts the tests that have a result after, and Advisories says of each result
  which version it is of.
- **The second row is as strict as the first.** It reads "Passed" only when the advisory check and every other
  pass-or-fail test the plan holds for that library has a result in the same retest and passed. While that retest
  runs, or after it was interrupted, it stays "Not yet" and says how many tests have a result. For Java it would
  read "Not proven" after a retest on 17.0.3, because the Independent exam still fails there, as the pack's own
  trial found. (The first independent review found that an earlier form counted only the runs that existed, so
  the row could read "Passed" part-way through a retest; it is fixed and tested.)
- **The "next step" is a pointer, not a proposal.** Kevin's list of what Otto produces names "a next step". The
  Overview's next step has no Accept or Reject: it opens the page that holds the next thing to do, and since this
  part it names Otto's waiting proposals. Nothing happens by following it or by ignoring it.
- **No button accepts everything,** by Kevin's decision. With many programs and many advisories that is many
  clicks.
- **A closed assessment gets no proposals to decide.** It shows the packs that were installed when it was signed
  off and the decisions made until then; every button is off.
- **Where the Otto part of an evidence file starts.** An assessment now gets its Otto part with its first decision,
  also a rejection, before any check has run.

## Limits of phase 6c, first half (six fixed questions, answered by rules; 19 November 2026)

- **Six questions, and only those.** "Why did this check fail?", "What does this result show, and what doesn't
  it?", "Where did this suggestion come from?", "What happens if I accept this?", "What is this page for?" and
  "What should I do next?". Fixed rules read them in a few common wordings each
  (`backend/app/assistant/questions.py`). Any other question gets "I can't do that." and the list of what can be
  said on the page. The plan's second half, an answer in free words by Claude from a fact sheet, is not built, so
  there is no "Hypothesis" part, no "Facts used" fold and no "What was sent" fold yet, and no model is asked for a
  question with Live Otto on or off.
- **An answer is a list of the app's own sentences.** Nothing is explained beyond what a page already says about
  the item. For a failed check that is the reviewer's result, its plain sentence, up to three lines of what
  happened, the control, where an advisory check came from and the fix; it does not list the single cases the
  program got wrong (the link opens the result, where they are). Two kinds of sentence are the assistant's own: the
  opening line that names the item and repeats its result word, and one standing sentence for each page ("What is
  this page for?"). Those ten page sentences are new wording, in `backend/app/assistant/words.py`.
- **"This check" is the open item.** With no item open, "Why did this check fail?" is about the one failed check
  if there is exactly one; with several it asks "Which one?". A check that did not fail gets its result word and
  plain sentence ("did not fail: it reads Passed"). On Advisories an open advisory stands for its accepted check.
- **Where an answer shows.** The newest answer shows above the text box and stays there while you move around,
  until the next sentence. The panel does not switch to the tab the answer belongs to; the kept answer is listed
  in that tab under "This thread so far", with its facts as they were when asked. A fact is not refreshed later:
  the kept answer says what the records said then.
- **What is kept** is the question, the answer's one line and its facts. Like every exchange it is not in the
  evidence file. A closed assessment answers and keeps nothing.
- **The status line is unchanged**: "Live Otto is off." with the link to Settings, or "Live Otto is on.". The plan's
  longer line ("Otto answers the fixed questions from this assessment's records. Free-form answers need Live
  Otto.") is left for the second half: it promises free-form answers that are not built, and its wording says what
  Otto does, which the wording rule of 19 November does not allow. This is on the list for Kevin.
- **The text box's label** changed to "Ask Otto, or tell it what to do", as the plan words it for 6c.
- **A title with a colon** ("Advisory check: ...") is said without the colon in the sentence behind a "Which one?"
  option, because in a typed sentence the first colon starts a reason. Typed by hand with its colon after a
  command ("reject Advisory check: Blank signature accepted"), what follows the colon is read as the reason; the
  Confirm step shows it before anything is sent.

## Limits of phase 6b, first half (commands by fixed rules; 19 November 2026)

- **Only fixed rules read a sentence.** The plan's second half, passing other wording to Claude with Live Otto on,
  is not built. A sentence the rules can't read gets "I can't do that." and the list of what can be said on the
  page. The rules know a fixed set of verbs, page names and filter words; they are in
  `backend/app/assistant/commands.py`, and each example the list shows is read by them.
- **Names.** A thing is found by the words of its title and of what it is about (the advisory's id, the library,
  the program), and by a few everyday names (Java for openjdk, Python or ecdsa for python-ecdsa). A name that fits
  nothing gets "I can't do that."; one that fits several gets "Which one?". Nothing is guessed, so a short name
  that two things share always asks.
- **"The second suggestion"** counts the suggestions shown under "On this page" beside the page the sentence was
  typed on, in the panel's own order. On a page with no suggestions there is nothing to count.
- **Filters by a command** are: failed and passed (Checks, Evidence), true, false and couldn't check (Checks),
  proposed, accepted and rejected (Advisories), and retests, fix proofs and tries (Checks). The count in the answer
  ("2 checks") is worked out for Checks and Advisories; for Evidence the answer names the filter without a count.
- **The Result filter on Checks now also narrows the test plan's cards.** Before, it filtered the rows under the
  plan only. While it is on, moving a card with the arrow keys still moves it in the whole plan, past cards that
  are not listed.
- **The address holds the page's own filter value** (`result=Failed` on Checks, `result=failed` on Evidence,
  `decision=proposed` on Advisories). A value the page does not have lists nothing. Fixes has no such filter.
- **What is kept** is the sentence, the one line of the answer, the page, the thread and where it led. The card an
  answer showed is not kept: the thread shows the line only. What was said is not in the evidence file (the plan
  puts only Claude's steps there, and there are none yet).
- **Done on its page only.** For Merge pull request, Apply and Roll back the answer repeats the page's own reason
  where exactly one fix has that button; for Approve it says how many approvals are missing. For the others it
  only says that it is done on the page.
- **In a closed assessment** the box moves around and lists what can be said. Since phase 6c (first half) it also
  answers the six fixed questions there.
- **Eleven of the thirteen next-step screen tests** still compare the panel's request with a typed request, not
  with the real page component (found by the reviewer of 6a; the two that do are Run and Run all).


## Limits of Otto's research loop (phase 6; 19 November 2026)

Built in the overnight run of 19 November 2026 from Kevin's brief ("Otto researches by itself"). SPEC section 7f,
point 14, has the rules. What it does not do, plainly:

- **The public source has not been read for real from the build machine.** The machine this was built on could not
  reach `api.osv.dev`. The reader was written against the shape OSV documents and is tested with answers written in
  that shape and with damaged copies of them (a seeded fuzz test). The first real look is Kevin's to make: one click
  on **Look for new advisories** on a computer with internet, as the 15-minute live check list says. If OSV answers
  in a way the reader does not expect, the look says "... is not in the shape it documents" and nothing is listed.
- **Which libraries are asked about.** Only libraries the assessment names and OSV keeps by name: packages of npm,
  PyPI, Go, Maven, crates.io, NuGet and RubyGems. Of the six libraries the app knows today that is python-ecdsa
  (PyPI, as `ecdsa`), elliptic (npm) and Go's standard library (Go, as `stdlib`). Java (OpenJDK), OpenSSL and
  BoringSSL are not packages of those ecosystems, so they are not asked about, and the box says so before the look.
  Their advisories still come only from the built-in packs. A library the app does not know is not asked about
  either, whatever a dependency list says: a look is about the libraries the app can say something about.
- **Only the package's name is sent**, with its ecosystem. No version is sent, so the answer lists every advisory of
  that package; which ones name a version you have is worked out here from the record's version ranges. A record
  that gives its range only as source-code commits can't be matched to a version number: it reads "It could not be
  told whether it names ..." and nothing is guessed.
- **How much is read.** At most 3 pages of an answer for one package (each up to 8 MB); every record on them is
  read. A look keeps 40 advisories: first those that name a version you have (or might: where a version can't be
  read), then the newest of the others. The cut comes after that ranking, so an older advisory that fits is not
  pushed out by newer ones that do not. When more pages existed, or more than 40 were read, the look says which.
  A record that is taken back by its publisher, that says nothing about a version of the package, or that is not
  in the documented shape is left out and counted ("N records were left out"). At most 200 version ranges of one
  record are kept for matching.
- **One fixed address, and no other.** The request goes to `https://api.osv.dev/v1/query`. A redirect is not
  followed: it comes back as "answered with an error (HTTP 302)".
- **A publisher's summary that rates the advisory is not shown as its title** (a line with "severity", "CVSS",
  "critical" or a score). The title then reads "<publisher> record <id>"; the publisher's line stays among its
  quoted text, which is shown as the publisher's.
- **A file in the folder of recorded advisories is data.** Each advisory in it is held to the snapshot's exact
  shape and used byte for byte, or left out; a damaged file lists nothing and breaks no page. Links must be https.
- **No severity.** A record's rating of how serious a weakness is, and its score, are not read and not shown.
- **A test can be proven only for a library with pinned public copies of an affected and of the fixed version**:
  today openjdk 17.0.2 and 17.0.3, python-ecdsa 0.13.2 and 0.13.3, elliptic 6.5.6 and 6.5.7. An advisory fixed in
  any other version reads "No test yet: a test is proven against the fixed version, ..., and this version of the
  app has no public copy of it". So with today's pinned versions **most newly published advisories read "No test
  yet"**. Pinning more versions (for example elliptic 6.6.0 and 6.6.1) needs a new container image and Kevin's OK,
  like any dependency change.
- **Only one kind of test can be designed**: published ECDSA P-256 signature cases (the building block of phase
  5c). An advisory about anything else gets "No test yet" with the design's own reason.
- **Proving needs isolated mode.** In demo mode **Design and prove tests** is off and says why: a real library runs
  only in its own locked-down container.
- **With Live Otto off, only the advisories of the dated snapshot have recorded answers.** A research run on any
  other advisory leaves it open: it reads "Still open", with "No recorded answer: this needs Live Otto.", nothing
  is signed about it, and it can be tried again (for example with Live Otto on). With Live Otto on, the run asks
  Claude (read, design, propose a fix) within the spending limit per run; what is sent is the advisory's published
  text. A live research run was not made during the build (no key on the build machine; no test may reach Claude).
- **What a run settles, and what it leaves open.** Settled, and signed into the pack with its reason: a test that
  was proven; a design that failed its trial; "no test fits"; no public copies to try on; an answer the pinned
  checker refused. Left open, out of the pack, to be tried again: no answer for the reading or the design (no
  recorded answer; or, with Live Otto on, a call that failed, was refused or met the spending limit), and a trial
  on public copies that did not finish. A run that settles nothing makes no pack and says so. One thing is not
  asked again: where the test was proven and no answer came for the publisher's fix, the pack says "No fix is
  offered: There is no proposal for this advisory yet." and later runs leave that advisory alone.
- **A pack made here is installed by the click that started the run**, after any built-in pack that is not
  installed yet. This is the one case where a pack is installed without a click of its own; the box says so before
  the run starts. A pack made here is signed with a key made on this computer and is trusted on this computer only.
- **A pack made here becomes the newest pack, and a built-in pack published later can then not be installed.**
  Test packs install in one order, each naming the one before. After a run made a pack, a built-in pack that
  follows the last built-in one is refused ("does not follow the installed pack") in that data folder. The box
  says so before the run starts. A pack made here also takes the next version number of its month (2026.11.3
  after the built-in 2026.11.2), so a later built-in pack could carry the same number; the two differ by signer
  and fingerprint, which the evidence file holds. Letting a built-in pack follow the last built-in one, and
  giving packs made here names of their own, is a decision for Kevin.
- **A pack made here that was never installed** (made by hand with the research command, or by a run that was cut
  off after signing) is not installed by a later click: **Design and prove tests** is off and says "Test pack ...,
  made on this computer, is waiting to be installed. Install it first: Settings, Test packs, Check for updates."
  The click installs only the pack its own run made, and only if that pack holds nothing but advisories of that
  run.
- **One research run at a time**, for the whole app (two clicks at the same moment start one run; the second is
  refused). It can take several minutes for each advisory. A run that is still going after four hours is ended.
  If the app is stopped while a run goes on, the run is lost: the block says it was interrupted and made no
  pack, names the built-in packs the click had installed before it started, and it can be started again. The research ledger of runs made here is in the data folder (`otto-research-lab/`), apart
  from the shipped one in `research/lab/`, which is never written by the app.
- **The proof is the research side's own**, as for a shipped pack: the trial on public copies and its replay by a
  second author, which is a second role of the same build on the same computer and not an outside party.
- **What the evidence file holds about a look and a run.** Each look: when, by whom, the source, the names sent,
  the fingerprint of each answer, how many records were left out, and for each advisory found its id, its
  library, the day it was published and the fingerprint of the page it was read from (not its text). Each
  research run: its start and its end, the advisories, whether Live Otto was on, and the pack it made. That pack
  is in the file whole, with its signature, whether or not one of its checks was accepted: the proof of a test is
  in its pack. An assessment where a person only looked has an Otto part with the look and nothing else; its
  Otto ledger has no entries, so the verify command has nothing to audit there and passes also on a computer
  where Otto is not installed. The report (the readable copy) lists the looks and the runs too.
- **The demonstration** (`backend/tools/research_demo.py`) uses the three elliptic advisories of the dated snapshot
  as a recorded source, with only the first built-in pack present, so that the recorded answers fit. It shows the
  loop end to end with no internet and no key: one advisory is proven and proposed, two read "No test yet".


## Limits of phase 6a (the Otto assistant: suggestions and three tabs; 19 November 2026)

What is real:

- **The panel's one read is real, and it only reads.** It is worked out on every read from the same views the pages
  draw from, so a button in the panel can be pressed exactly when its page's button can, and reads the same reason
  when it cannot. A test compares every table row and every file of the data folder before and after a read, and
  another reads the panel's code and fails if it imports or calls anything that decides, runs or changes.
- **A decision in the panel is the page's own request.** There is one decision route. A test makes the same two
  decisions on two copies of one assessment, on the page and in the panel, and compares the database rows, the Otto
  ledger's entries and the evidence part field for field.
- **The name you type is really recorded.** It goes into the database row, the Otto ledger entry and the evidence
  file of each decision made after it was typed.

What is limited:

- **No AI model is in the panel in this phase.** It does not take commands or questions yet (phases 6b and 6c), and
  it has no text box. Its suggestions, next steps and "What this means" come from fixed rules.
- **The typed name is not an identity.** The app has one login. It does not check who is at the keyboard, and says
  so where the name is asked for and in Settings. A decision recorded before a name was typed stays "You". Approvals
  of a pull request and of a server change still use "You" and the two demo reviewers.
- **The name is asked for once per browser.** If you leave it empty, the field does not come back in that browser;
  Settings, **Who decides**, is where to type it later.
- **Closed tabs and the dot are remembered in the browser, not by the app.** In another browser, or after clearing
  the browser's data, every tab is open again and nothing counts as seen. Nothing about tabs is in the evidence.
- **"This thread so far" is a list, not a history of everything.** It holds decided suggestions, the reviewed result
  of each test (the first run and, where there is one, the newest retest, as Evidence shows them) and where each fix
  stands now. Earlier states of a fix and older runs of a test are on their pages, not in the thread.
- **A next step is offered for the buttons listed in the spec only.** Approve, Merge pull request, Apply, Roll back,
  Close and sign off, the "I own this system" tick, a migration option, Mark reviewed and the downloads are never
  in the panel. Open pull request and Ask for approval are sent with the reviewers the page ticks by default; to
  pick others, use the page.
- **The panel knows the open item only where the page has a side panel.** On pages without one (the Overview, the
  Roadmap's bands) it knows the page only.
- **A page's own first read can still write.** Opening the Migration page writes each system's measurement down and
  locks it, once, as it has since phase 4a. The panel's read does not do that in its place: beside any page it
  writes nothing (a test opens the panel on an assessment whose pages nobody has opened and compares everything).
- **Two sentences differ from the plan's wording.** The plan had "Otto has nothing to suggest on this page." and
  "Bring in a scanner file to start. Otto has nothing to suggest yet." Since the 5c fixes no sentence says what Otto
  did or has, so the panel says "Nothing is suggested on this page." and "Bring in a scanner file to start. Nothing
  is suggested yet." This is for Kevin to confirm.
- **The panel's read takes about a quarter of a second on the Acme Pay demo**, because it works everything out
  again each time. While something runs it asks again every two seconds, not every second.

## Limits of the 5c fixes (19 November 2026)

Six fixes after Kevin's review of phase 5c: a new Codespace starts the app, Checks in four parts, Open in new tab,
wording, times, and the "New" tag. What they do is in `docs/SPEC.md` section 2. What they do not do:

- **Times.** Only a time with a time of day is written in the viewer's own zone. A date with no time of day (a
  pack's build date, an advisory's publication date, a review date) is shown as it is written, which for a build
  date is the UTC day. The zone's short name is the browser's: United States zones read "EST" or "PDT"; many others
  read as an offset ("GMT+1"). The evidence file, the report, every download and both of Otto's ledgers keep UTC,
  and so does every answer to a script, because only the browser asks the server to mark its times
  (`backend/app/present/times.py`). A time that a person typed into a reason is their text and is never changed.
- **Open in new tab.** The item's own page keeps the list it belongs to loaded and hidden, so the page asks the
  server for the same things as the list does. The Overview has no items, so it has no such page. A page that has
  no list to look in (for example Import with no file) says "This item is not here" after about four seconds.
  Since the review of the fixes, an item's own page carries the line every result screen carries ("Passing these
  tests doesn't prove a system secure. It shows these specific checks passed."), on every page but Import, which
  shows what a file says and no result. This includes an item of Checks, whose list page has no such line. The
  reason a click was refused, which the hidden list would have shown, is drawn above the item.
- **Checks.** While a retest runs, its block fills as each test finishes: a test that has not finished is not
  listed in it yet, and the line above the blocks says how far the retest is. A block is one program in one
  version: two retests on the same version share a block, and each row lists that block's runs. The older address
  of a retest's check (`retest-12`) opens the newest block's row. Only the Encryption tests group has parts.
  The **Came from** filter goes by each row's own "Came from": a retest's test whose newest run came right after
  an Apply is found by "After Apply", in its block, and not by "Retest". With any filter on, a block that holds a
  match is open and a block that holds none is left out.
- **The test plan's two lists** are a way of showing one plan. The plan still has one order (Evidence lists results
  in it); moving a card changes the order among the cards of its own list and nothing else.
- **Wording.** The rule is about the listed phrases ("Otto wrote", "Otto proposes", "in Otto's words", "Why Otto
  proposes it", "Otto found", "Otto has", "Otto's proposal", "Otto asked", "Otto no longer") and the same verbs in
  another tense. Seven sentences that were not on the list also named Otto as the one acting. The separate review
  of the fixes found them, and they were reworded the same way (Kevin, say so if any should go back): the Live
  Otto status lines ("Otto works on the answers recorded during the build" is now "Only the answers recorded
  during the build are used"; "when Otto needs an answer, it asks Claude" is now "when an answer is needed, Claude
  is asked"), "Otto adds up each call's cost" ("Each call's cost is added up"), "Otto goes on working with the
  answers recorded during the build" ("The answers recorded during the build go on being used"), "An advisory
  Otto could not read" ("An advisory that could not be read"), "Otto's own change is not offered here" ("A change
  “Written by Otto” is not offered here"), and in the evidence file's note about the app "test packs made by
  Otto, which uses Claude to read advisories" ("test packs. For a pack, Claude is used to read advisories"). Three
  reasons the pack builder writes into a new pack said "Otto has no answer / design / proposal for this advisory
  yet" and now say "There is no …"; the two shipped packs hold none of them and were not rebuilt. The wording
  test now reads the pack builder too. "Live Otto" is the name of a setting and stays ("Live Otto needs an API
  key"). Titles kept their words ("Otto's notes on reading it", "Otto's proposed check, in this assessment",
  "Have Otto write a change for …"). A decision recorded before
  the fixes keeps the copy of the proposal it was made on, so the history of an older decision, in the app and in
  an evidence file, shows the older words. The sentence the assessment's Otto ledger keeps about a proposal
  ("Every decision a person records on Otto's proposal …") is a record and was not changed; no screen shows it.
- **The "New" tag** goes by the order packs were installed on this computer. It does not know what a person has
  already looked at, and it stays until a newer pack is installed.
- **A Codespace.** The image and the three add-ons are pinned by fingerprint; what an add-on downloads when the
  Codespace is built (the current Node.js 22, Docker, Git LFS) is not. On the build machine the add-ons could not
  be installed (it may not reach the host their packages come from), so Docker inside a Codespace and isolated
  mode there were not rehearsed: Kevin's own check in a new Codespace covers them (`docs/HANDOFF-overnight.md`).
  The address `./run-demo.sh` prints (`http://127.0.0.1:8000`) is inside the Codespace; README says to use the
  box GitHub shows, or the Ports tab.
- **The fast test set.** To keep it under five minutes, the tests that read the three oldest shared walks still
  in it (the phase 3a fix, the phase 4a migration demo, a phase 4b change) moved to the full set. They run with
  `--full` and in the nightly checks.

## Limits of phase 5b (one connected assessment; 17 November 2026)

- **The sign-off name is typed, not checked.** This app has one login, so whoever is at the keyboard records the name
  in Close assessment. It is kept with the time, in the assessment and in its evidence, and can't be changed or undone.
- **Rerun as new assessment brings in the scanner file only:** no dependency list, no results, no choices; each address
  must be confirmed again. A file brought in before phase 5b was not kept, so Rerun says so and asks for the file again.
- **The new pages only read.** The Overview, the Project overview, Checks and the Related block never write anything
  down by being looked at: before Migration is opened, its systems are named from the file, "Not measured yet", and
  no measurement of them is locked.
- **Related shows recorded links only:** the claim a test targets, the results a fix came from, a system's address or
  program, a migration system's fixes, a library's tie and blockers. A link the app never recorded is not guessed, so
  a line can be missing (for example a library that is not tied to a system has no System line).
- **Counts, never a score.** The Overview, the Project overview and every group heading count what the pages say (Open,
  In progress, Done); there is no trend line and no rating. The status word "Applied · matches the try", which the
  plan did not name, counts as In progress (applied, and not yet the last word). The Dependencies group counts the
  list's libraries on every page: done once answered (from release notes or a measurement), in progress while one is
  measured, open otherwise. "Open" fixes on the Projects table and the Project overview mean the same as on the group
  headings (not started on yet); a fix in review or being tried is in progress there too.
- **One measurement in more than one place is kept, and marked.** Verify's post-quantum claim on a server, that
  server's Post-quantum readiness test and Measure status use the same probe and rule; a signing program's Verify claim
  and its Measure status run the same `info` and round trip. Each keeps its own run and its own result (each answer key
  grades its own); Checks marks them "the same measurement as" each other, and Migration links the two from other
  groups from its foot. Running it once and reusing the answer is left for a later phase.
- **What changed** compares two assessments of one project by what each item is (a claim by where it is, its kind and
  its claimed value; a test by its kind, target and title; a track by its system's name; a blocker by library, system
  and track). An item that changed any of these between the two reads as one gone and one new.
- **The layout is measured at 1440 pixels wide** with the sidebar and the assistant showing and the panel at its
  default width. A panel made much wider leaves less room, and a table beside it can then scroll sideways. A name with
  one very long unbroken part (a 40-character commit id) is cut short with "…" in a table cell; the full name is on
  hover and in the panel. Inside the panel, at its default width (440 pixels), a wide evidence table (for example a
  library's answers by copy and control) scrolls sideways in its own box; Wider shows it whole.
- **Verify has no locked test and no separate review**, unlike every other check (see Next in the phase 5b report).
  Its results are what Verify measured, as before; Checks and Evidence only repeat them.
- **Earlier runs in the evidence file** cover a test's first results and retests. A fix's proof runs are in the `fixes`
  part, as before; a try's and a measurement's runs are listed in `checks`.

## Limits of phase 4b (make it real)

The new rule: the app changes a system only when a person presses Apply, after a passing try on a test copy and every
approval asked for. It measures again right after, and can roll back. What follows is where that stops.

- **An applied change stays in force across imports.** Our demo servers are shared by every import of a file, so a change that
  was applied and not rolled back is still there when the file is imported again: Verify and the tests then show the server as
  changed, and differ from the answer key. Import says so, and the new import's Fixes step lists the change with its Roll back.
  After a Roll back the demo gives its starting results again.
- **Apply works only on our own servers:** the five migration demo test servers (localhost:8451 to 8455), the lab nginx
  (`demo/lab-nginx.csv`, localhost:8461, isolated mode only) and the Acme Pay demo server (localhost:8443, its TLS 1.2
  fix only). For any other server, Try and Apply are off and say that a connector to that server comes in a later phase.
  **Download change** still works.
- **The Acme Pay demo server and the multi-target demo's extra servers can't take a post-quantum change.** They run on
  Python's built-in TLS, which can't be set to post-quantum key exchange.
- **The test copy is our own lab server with the same settings.** It is not a copy of your software, your load balancer
  or your certificates. A pass shows that these settings do what the change promises on our lab server, and (in isolated
  mode) on real nginx. It doesn't show it on your server. In demo mode there is no real nginx run, and the column says so.
- **Real nginx is pinned:** `nginx@sha256:fed7e14be83cbd2661a75cdc5b872d936cf155d46c327084d30b8df19ae88d72`
  (nginx 1.31.8, OpenSSL 3.5.9), pulled only by `cd backend && .venv/bin/python -m app.prepare`. It runs locked down:
  read-only, no capabilities, user 101, 64 MB, 32 processes, host network on 127.0.0.1 only.
- **"Checked on" lines were checked during the build, not at each run.** "Checked on nginx 1.31.8 with OpenSSL 3.5.9" and
  "Checked on Apache 2.4.71 with OpenSSL 3.5.9" were true when the change builder was made. Only real nginx in isolated
  mode is run again at each try. Application lines say "Not checked on real software."
- **One login for approvals.** Whoever is at the keyboard records each approval, under the name shown. Demo reviewer A
  and B are demo data, not people. Apply is one click with no confirm box: it is off until the latest try passed and every
  picked reviewer approved.
- **A try is out of date after an Apply or a Roll back.** Try again first.
- **Fresh test certificates after a restart.** The settings in force are worked out by replaying the applies and roll
  backs, so they survive a restart. The test certificate and key of a changed test server live only in memory, so
  after a restart the server gets a new test certificate of the same kind (and Roll back then also gives a new one of the
  earlier kind). Test keys are never shown, stored or exported, and downloads never hold a private key.
- **The ML-DSA test certificate comes only with Full post-quantum for now.** Serving two certificates as an interim step
  comes later. Hybrid changes the key exchange only, so authentication stays Classical.
- **Keep classical, Wrap and a signing program's change are text.** The app gives a review date and what to recheck, what a
  gateway in front must do, or the steps for whoever looks after the program (download only). It applies nothing for them,
  and Keep classical and Wrap text appears only once the person chooses that option. A signing program's change stays
  text after phase 4c too: the lab runs and tests signing libraries, but it does not hold your program that calls one.
- **The default-choice check is one hello offering both key shares in each order.** It shows what the server picks in those
  two handshakes. It is not a model of every browser or client, and it is information, not a pass or a fail. The controls
  must also read it right, or the measurement says Couldn't check.
- **Authentication reads Couldn't check** when the certificate key and the handshake signature (CertificateVerify in
  TLS 1.3, ServerKeyExchange in TLS 1.2) disagree, or one of them can't be read. It never guesses.
- **A measurement from phase 4a must be measured again.** The rule changed (`pq_status_tracks`), so the locked-spec
  fingerprint is new. Old stored results keep their phase 4a rule and words.
- **Also noticed** (for example TLS 1.0 or 1.1 accepted) never changes a status.
- **After Apply the app only says whether the new measurement matches the try.** If not, it says so and offers Roll
  back; it never rolls back by itself. The Fixes entry reads "In place (measured)" only when a new measurement shows the change in place.
- **Roll back undoes the server change, not your choice** (Kevin's decision on answer MC7, 15 November 2026). After Roll
  back of Full post-quantum the server is back as it was, but the choice of Full post-quantum stays recorded, so its key
  exchange track stays in "Phase 2" until you choose again.

## Limits of phase 4c (real code; 15 November 2026)

### What is real

- **The libraries are real, in exact published versions:** Java (OpenJDK, the Temurin build) 17.0.2 and 17.0.3,
  python-ecdsa 0.13.2 and 0.13.3, elliptic (npm) 6.5.6 and 6.5.7, and OpenSSL 3.5.9. Their files come from pinned
  sources (container images by digest, packages by SHA-256 or npm's integrity value) and are checked before they
  are used. None of them is stored in this repository.
- **The crypto is the library's.** Each has one short wrapper that turns the adapter's JSON into the library's own
  call and back. The wrappers hold no crypto of ours. Two details to know: elliptic does not hash, so its wrapper
  hashes with `hash.js`, elliptic's own dependency; and each wrapper wraps a raw public key in the standard
  envelope its library expects (a fixed prefix, no maths).
- **They run only in isolated mode,** each family in its own locked-down container (no network, read-only, not
  root, the same limits as our demo components). In demo mode nothing of theirs runs: Verify says Couldn't check,
  the tests say Couldn't run (needs isolated mode), and Import, Tests, Evidence Lab and Migration say why.
- **The right answers are not ours.** The Independent exam is the Project Wycheproof file the app already used.
  The two post-quantum exams use NIST's ACVP files and Project Wycheproof's ML-KEM-768 and ML-DSA-65 files,
  stored whole and pinned by SHA-256 (`demo/vectors/`, with NIST's notice in `demo/vectors/acvp/NOTICE.md`).
- **The post-quantum exams compare fingerprints.** The test harness reports the SHA-256 of each answer and the
  reviewer compares it with the SHA-256 of the published answer. No key or shared secret is stored, although
  they are published test values.
- **Every part of an exam has a control that must fail:** a copy of the OpenSSL wrapper that changes one byte of
  every answer; a copy that skips two key checks the standard requires (it must wrongly accept all 117 public keys
  that hold a number that is too large, and the 6 private keys whose fingerprint is wrong); and for ML-DSA
  verification the accept-everything signer. The controls always run in the OpenSSL image.
- **The advisories shown beside a result are the publisher's,** with their links. They are information: no result
  is ever set from an advisory, and the result says which advisories its test does not catch.
- **A real before and after:** Retest new version can move one library to its fixed version. The others are tested
  again as they are.

### What the tests catch, and what they miss (measured, not tuned)

- **Java 17.0.2:** the Independent exam finds 13 wrong answers of 484, the blank signature (r = 0, s = 0) among
  them; our short list finds the blank signature too. This is CVE-2022-21449.
- **Java 17.0.3, the fixed version, still fails the Independent exam on 3 cases:** it accepts a number written
  without its leading zero (case 6) and rejects two genuine signatures (cases 350 and 479). We found no
  published advisory for these in one search. The app shows them as wrong answers on official cases and says no
  fixed version is known to it. It makes no claim about how serious they are.
- **python-ecdsa 0.13.2:** the exam finds 24 malformed signatures accepted, our short list one. This is
  CVE-2019-14859. On about 67 more cases the library stops with a general program error. By the owner's rule
  (an error raised by the library means "not accepted") those count as rejected and are shown under Also noticed.
  That is CVE-2019-14853, which these tests therefore **note but do not fail**.
- **python-ecdsa 0.13.3** passes both tests and still stops with a general error on 5 cases, noted the same way.
- **elliptic 6.5.6:** the exam finds exactly one wrong answer, case 6 (CVE-2024-42460). **Our short list finds
  nothing on elliptic:** it has no missing-zero case, and we did not add one, because that would be tuning a test to
  one library. **CVE-2024-42461 is not caught:** the loose length form it allows needs a signature longer than
  127 bytes, and a P-256 signature is at most 72; it would need a test on a larger curve. **CVE-2024-42459 is
  not caught:** it is in EdDSA, and the wrapper covers ECDSA P-256 only.
- **OpenSSL 3.5.9** passes everything it is given: 484 and 16 for ECDSA, 655 for ML-KEM-768, 475 for ML-DSA-65.

### Limits

- **Timing attacks are out of scope.** The post-quantum exams compare answers. They say nothing about how long a
  step takes, so a fault such as KyberSlash (a secret-dependent timing in ML-KEM) would not be found. Each result
  says so.
- **The pre-hash variant of ML-DSA (HashML-DSA) is not tested.** OpenSSL 3.5 does not offer it and the adapter
  does not cover it, so 45 NIST cases are left out for every library. The locked test and the result say so.
- **One parameter set each:** ML-KEM-768 and ML-DSA-65 only. One curve for ECDSA: P-256.
- **Only OpenSSL is tested for post-quantum.** The exams would run on any library whose wrapper offers the
  algorithm; in this version that is one. Their controls are broken copies of the OpenSSL wrapper and always run
  in the OpenSSL image, so an exam on another library still needs the OpenSSL image to be prepared.
- **For OpenSSL, Verify's second opinion is not an outside one.** Verify (and the Migration measurement) confirm a
  round trip with the app's reference library, `cryptography`, which is itself built on a release of OpenSSL
  (4.0.3 on the build machine). So for `openssl 3.5.9` that check shows two releases of OpenSSL agree; a fault
  shared by both would pass it. The result says so. The two exams and the Independent exam are the outside
  check: their right answers are NIST's and Wycheproof's. For Java, python-ecdsa and elliptic the reference library
  is a different implementation.
- **"An error means no" is a choice.** It is the owner's rule (decision 1, 15 November 2026). A stricter rule would
  count a crash as a wrong answer; python-ecdsa 0.13.3 would then fail on 5 cases.
- **A wrapper could be wrong.** It is our code. Each is short enough to read, each reports the version from the
  library itself, and Verify checks one round trip against an independent library, but a wrapper is not proven.
- **Java is the Temurin build of OpenJDK.** Other builds of the same OpenJDK version were not tried. Its images
  are for Intel and AMD processors; on an Apple Silicon Mac Docker runs them through emulation, slower.
- **The Java versions are timed on the same test key; the wrapper is given both halves of it,** because the JDK
  can't work out a public key from a private one without maths of our own.
- **The slowed control of a real library is its own wrapper told to wait 6 ms** inside every timed step, as our
  slowed demo control does.
- **Retest moves one library at a time,** and Evidence Lab shows the latest retest only. To see another library's
  before and after, retest it; the earlier retest's runs stay in the records and in the evidence file.
- **No code fix for a real library.** The fix is its publisher's fixed version, as a text-only entry in Fixes with
  the advisory link. The app writes no patch and opens no pull request for other people's code.
- **Migration:** a real signing library's track says whether it can make an ML-DSA-65 signature today, by having
  it make one. The key exchange row (ML-KEM-768) has no Migration track in this version. A signing program's
  change is still text: the lab holds the library, not the program that calls it.
- **Preparing takes longer.** The first `./run-demo.sh` with Docker downloads what the images are built from (a
  few hundred MB) and uses about 3 GB of disk. A library whose image could not be prepared is named, and the
  others still run.
- **The first run of the real-libraries file takes about 5 minutes, and each retest about 5 more,** on the build
  machine (15 tests; the speed tests run one at a time).
- **The blind test has not been run.** Its procedure is in `docs/BLIND-TEST.md`; the three commands were rehearsed
  on our own demo program only.
- **The advisory links were taken from search results;** the build did not open each page. The NIST site is blocked
  from the build machine.
- **A sentence older than this phase is still on screen** for a program the app does not know: "Only our own demo
  components can run in this version." Read it as "only the software this version knows".

## Limits of the Fixes step (phase 3a)

- **A passed proof shows that these tests passed on the changed code.** It doesn't show that the change is free of
  other faults, and it says nothing about how the code behaves once it is deployed. The screen says so too.
- **The proof never runs the changed file itself.** Only our own demo software may run. So the app first checks,
  byte for byte, that the file the change produces is identical to one of our registered demo components (the
  bundled `acme-sign` 1.4.3), and then runs that registered component. If it is not identical, nothing is run, the
  status is "Proof failed" with "Nothing was run", and the change is not offered. Technical details shows the two
  fingerprints that were compared.
- **When a change is offered.** All of these must hold, and the review step decides it from the stored records:
  - the changed code is ours, byte for byte;
  - every pass-or-fail test that runs the changed code passed, and there is at least one;
  - the failed tests the change is for are in the proof and passed;
  - the proof holds a "Speed and size" test and it reads "No slowdown beyond measured noise";
  - a report-only test in the plan (the ML-DSA-65 comparison) ran; it has no pass or fail;
  - every control behaved as expected;
  - the server tests came out the same as before (the same result for the same reason).

  So a plan from which "Speed and size" or the failed signing tests were removed gets "Proof failed", with a
  sentence that names the test to add back. Requiring the speed test in the plan is our reading of "plus the
  speed comparison" in SPEC 7b; the owner can change it.
- **"Proof failed" covers five different causes,** and the screen names which one: "Proof did not pass",
  "Proof did not finish" (the app was closed while it ran), "Proof out of date" (the test plan changed after the
  proof), "Proof can't be trusted" (the stored records no longer match their fingerprints) and "Nothing was run"
  (the changed code is not one of ours). Only the picture of a proof that did not pass was approved beforehand;
  the wording of the other four was written during the build.
- **Changing the test plan puts a proof out of date,** also while a pull request is open. Adding or removing a test
  does it; reordering does not. The status goes back to "Proof failed"; Approve, Merge pull request and Download
  patch are refused until Run proof again has passed on the plan as it is now. Approvals that were already
  recorded stay on record and count again after the new proof; their times show that they were given before it.
  After a merge nothing changes: "Merged" is a fact.
- **Approvals can't be withdrawn, and a pull request can't be closed** without merging it. The reviewers are picked
  when the pull request is opened and can't be changed afterwards. There is one pull request per change and one
  code fix per imported file. To start over, import the file again: it gets its own fresh copy of the repository.
- **Records of a fix are only ever added.** The change, the proofs, the pull request, the approvals and the merge
  can't be edited or removed, whatever code asks. Someone with direct access to the database file could still
  change it; the screen would then say the proof can't be trusted.
- **The server finding is separate.** The code change does nothing about the server. The proof reruns the server
  tests only to show they come out the same as before, which for the demo means "Failed" both times.
- **When a finding counts as open.** A text-only suggestion is listed until a newer result of its test says
  something other than "Failed". Only a pass or a fail counts: "Couldn't run", "Couldn't trust this run" and
  results that only report ("Measured", "Not offered") are passed over, so a retest that could not reach the
  server does not close a finding that comes from a first result. Only the results Evidence Lab shows now are
  looked at (the newest first result and the newest result of the latest retest). That has two effects:
  - A finding that a passing retest closed reads as open again while the next retest is running, and stays open
    if that retest could not run the test.
  - A finding that only a retest found (its failed result stands in the After column: a "Slowdown found", or a
    server test that passed at first) leaves the list as soon as the next retest starts, and stays off it if
    that retest could not run the test.

  Neither can happen in the normal demo walk: the demo server's settings never change, and a slowdown needs a
  busy computer or a slower version. Both matter for the server setting step (SPEC 7c). A code fix stays listed
  once its change is on record.
- **A failing test added after the code was connected joins the same code fix,** when the fix template answers
  it (for example "Official test vectors" removed before connecting and added back later). The plan has changed,
  so the fix reads "Proof failed" with "Proof out of date" until Run proof again has passed with that test in
  it. After a merge the line on such a result reads "Fix merged ..., proof passed", and Fixes, the report and the
  evidence file read "Came from 2 failed tests", although that proof was run before the test was added. The
  Proof section and the proof record list exactly the tests that ran; Retest now shows the result on the
  merged code.
- **While a proof runs, nothing else can start for that file:** Run, Run all, Retest new version and Download
  evidence are switched off, and come back by themselves. Evidence Lab says why. The Tests screen switches its
  buttons off without a sentence saying why.
- **How long it takes.** The proof reruns every test, including the speed test: about half a minute in demo mode
  and about a minute in isolated mode on the build machine.
- **If the app is closed while a proof runs,** the proof reads "Proof did not finish" after the restart and has to
  be run again with Run proof again. If it is closed in the instant after the last test finished and before the
  proof was checked, the screen says the same ("interrupted before every test had run: 4 of 4 tests finished"),
  which is not exact: every test ran, but the proof was never checked. Run proof again is the remedy.
- **If the app is stopped in the instant between merging in the repository and writing the merge record,** the
  pull request can no longer be merged ("The repository has changed since this change was proved"). Import the
  file again. We did not see this happen; it follows from the order of the two steps.
- **The app's own git code is small on purpose.** It reads and writes plain ("loose") objects only, files at the
  top level of the repository only, and text files in UTF-8. That is all the bundled demo repository needs. A
  repository copied from a code host normally has packed objects and folders, and would be refused. This matters
  once real code hosts are connected, not in this version.
- **How changed lines are lined up.** The app lines up old and new lines with Python's standard library, not with
  git's own method. For the demo change the result is identical to what git shows. For other texts an added
  block can be shown one line earlier or later than git would show it; the patch would still apply. This matters
  from phase 3c on, when changes come from developers.
- **Results made before phase 3a say nothing about the code they ran on,** because nothing was written down then.
  A data folder from phase 2 still opens and works; its older results simply have no "Code" item, and before and
  after then has no "Code they ran on" sentence.
- **Each imported file keeps its own copy of the demo repository** in `data/repos/`. The app never deletes these
  copies; they are a few kilobytes each.
- **Three looks were built without an approved picture:** the Proof section opened while the proof is still
  running; a pull request whose proof is out of date (Run proof again, with Merge pull request and Download patch
  shown switched off); and the Fixes part of the HTML report. They are in `docs/screenshots/phase3a/` (03a, 25, 14).

## Limits of the 3a fixes (every target, plain sentences, Also noticed; 14 November 2026)

- **Grouping by target shows only when the file names more than one server or more than one signing program.**
  With one of each (the Acme Pay demo) the list stays flat, as before (Kevin's decision).
- **Retest and the code fix work on one program only: the plan's own.** That is the first program in the file
  that is one of our demo components (else the first program). Every other server and program is tested again
  as it is on a retest or in a proof, and is recorded as running our bundled file. In a proof, tests of another
  program only have to come out the same as before, like the server tests. A file that names both demo versions
  can't retest the second one to another version.
- **Programs that are not ours can't run.** A file naming `acme-sign 9.9` (or any other software) gets its tests
  in the plan, each showing "Couldn't run", and a line in "Not tested, and why" says so up front.
- **"Not tested, and why" lists:** a suggested test a target doesn't get (with the reason), a program that isn't
  ours, a server not confirmed yet, and a claim no test covers (cipher suites, key exchange). It does not list a
  test you removed: that one is back in the catalog. A test that ran and couldn't run says why on its own card.
- **A test plan made before these fixes is not remade.** If its file names several servers or programs, the
  missing tests are listed under "Not tested, and why" with "Import the file again to test it". Its locked tests
  also keep the old why-lines (the new titles show anyway: titles come from the app, not from the locked test).
- **The plain sentences are fixed templates**, written from the stored result and run record; no AI model writes
  them. For cipher-suite and key-exchange claims that come back False, the sentence reuses the technical
  finding. A Verify row stored before these fixes gets a plain fallback ("This matches the claim." plus the
  technical text), not a new sentence. (Since phase 5c the sentence of an advisory check names its advisory by a
  plain name that Claude wrote: see "Limits of phase 5c".)
- **"Also noticed" covers one case:** a certificate check (in Verify or the Certificate strength test) whose
  handshakes show the server accepts TLS 1.0 or 1.1. It is not shown when the same file also claims that
  server's TLS versions (the TLS row already says it). It is words only: the reviewer never reads it.
- **The three test servers (8444, 8445, 8446) are demo only.** They start only when the bundled
  `demo/multi-target-demo.csv` is imported unchanged (line endings and trailing spaces aside); an edited copy
  starts nothing. After the app restarts they start again when that import is verified or tested. Each makes a
  throwaway test certificate when it starts, and Verify and the tests check that certificate, so another program
  on one of those ports is never reported on as ours ("Couldn't check" instead). Moving the demo server with
  `EVIDENCE_LAB_DEMO_TLS_PORT` does not move them. The note that they started (or that a port was taken) shows
  once, right after the upload.
- **Text-only fixes are one per failed test.** In a file with several targets the Fixes list names the server or
  program, and the fix id carries the test's number (`fix-tls-versions-<n>`); with one test of a kind it is
  `fix-tls-versions`, as before. The suggestion for a failed certificate is the plain suggested fix, not the
  fuller server-setting text the TLS finding has.
- **Screenshots of phases 1 to 3a were not retaken** (Kevin's instruction). The end-to-end run rewrites them, so
  they were put back to the committed pictures afterwards; the changed screens are in
  `docs/screenshots/phase3a-fixes/`. Some earlier pictures therefore show the old titles and rows without the
  plain sentence.

## Limits of the tests (phase 2)

- **Passing these tests doesn't prove a system secure. It shows these specific checks passed.** A component can
  get all 484 official cases right and still have faults those cases don't cover.
- **The reference library runs outside the sandbox.** The `cryptography` library is our trusted reference; it
  runs inside the app itself, also in isolated mode. Only the demo components and controls run in the container.
- **Verify runs the signing component in the same mode as the tests.** In isolated mode the Verify step's check
  (`info` and one sign-and-verify) runs `acme-sign` in the container; the test key is made and used inside the
  harness and never comes back to the app. If isolated mode was asked for but is not available, that claim reads
  "Couldn't check"; the component is not run as a local program instead. In demo mode it runs as a local program,
  as before. The independent check with the `cryptography` library runs inside the app in both modes.
- **Some "Run record" boxes hold a summary, and say so.** For the official vectors, bad signatures and speed
  tests the box is titled "Output summary": the app wrote it from the stored run, because the full output is
  hundreds of lines. The full raw output is in the downloaded evidence JSON. The server tests, the post-quantum
  check and the ML-DSA comparison show the stored output itself under "Raw output".
- **Closing the app while tests run.** A test that has not finished about 20 seconds after Ctrl+C is dropped: it
  writes no record and reads "Not run yet" next time. The app can take up to a minute to exit while a
  measurement that was already running comes to its end.
- **Leftover containers.** A test container left behind by a crash is removed at a later start of the app, once
  it is more than 15 minutes old. Younger ones are left alone, because they may belong to a test that another
  copy of the app (the accuracy command, the tests) is running right now. A leftover has no network and the same
  CPU and memory limits, and normally ends by itself.
- **Server tests are not "in" either mode.** TLS and certificate checks are handshakes made by the app itself in
  both modes; they record no component.
- **Speed timings are for this computer only.** They don't predict speed on your servers or under load.
  - The components are plain Python, so times are in milliseconds and vary from run to run. On the build machine
    one run of the same program was sometimes 20 to 30% faster or slower than the next, for no cause we found.
  - The slowdown rule therefore compares old and new side by side in the same run (200 matched pairs, in 40 short
    alternating rounds), and only flags a slowdown that is bigger than the measured noise plus 3%. A small real
    slowdown, under about 3% plus the noise band (often 2 to 6% here), is **not** flagged. The noise band is
    always shown.
  - In the container, 1.4.3 measured about 2% slower than 1.4.2 on the build machine. That is under the rule's
    floor, so it reads "No slowdown beyond measured noise"; we did not find the cause.
  - Between the noise band and "noise plus 3%" a retest still reads "No slowdown beyond measured noise", because
    that is the locked rule. The text under the result then says the measured difference is above the noise but
    below the level the test calls a slowdown; it does not call it noise. Whether the 3% floor and that label
    should stay for this zone is an open question for the owner (SPEC section 7 item 5 does not mention a floor).
  - **Signature size is one signature per run.** An ECDSA P-256 signature in this format is 70 to 72 bytes long
    depending on the individual signature, and each run makes a fresh test key. So the size shown can differ by
    1 or 2 bytes between runs, or from the reference library, without anything having changed. In a retest both
    versions sign the same message with the same key, so their "Change" is exact.
  - Numbers from different modes, or from different runs, are never compared with each other.
  - The first-run numbers and the "before" column after a retest come from two different measurements (the retest
    measures both versions again), so they can differ slightly.
  - The reference library figures are shown "for scale only". It is a heavily optimised production library; it
    is not a like-for-like comparison and is not part of the rule.
  - The speed test waits until it has the computer's test runner to itself, and other tests wait for it. That
    only covers this app: other programs on the computer still add noise. Running the accuracy command while the
    app is also running tests means two measurements can overlap.
  - The speed test takes longer than first planned: about 15 seconds on a first run and 25 on a retest in demo
    mode, about 25 and 35 in isolated mode (build machine, 4 cores).
- **Post-quantum readiness needs OpenSSL 3.5 or newer.** The app uses the `openssl` program on this computer if it
  is 3.5 or newer; otherwise, if Docker is running and the pinned `alpine/openssl` image is present, it runs the
  check in that container. If neither is available the result is "Couldn't run (needs OpenSSL 3.5 or newer)",
  never a guess.
  - "Not offered" is only reported when the server refused the post-quantum-only request with the expected
    alert, a normal handshake to the same server worked, **and** the control server was detected as "Offered".
  - It checks one key exchange (X25519MLKEM768) by one handshake. It says nothing about certificates or
    signatures being post-quantum.
  - The path that uses a local OpenSSL 3.5 was tested with recorded outputs only: the build machine has
    OpenSSL 3.0.13, so real runs there went through the container.
  - **Docker Desktop (Mac, Windows):** the checker container needs "host networking" to reach a server on this
    computer. On Docker Desktop that may not reach `localhost`. The result is then
    "Couldn't run (the checker could not reach the server)". Isolated mode and this check were only run on Linux.
- **The ML-DSA-65 comparison is "reference, not production".** The figures come from the `cryptography` library's
  ML-DSA code run inside the app. It reports numbers only; it is not a test of any ML-DSA software of yours,
  and it was only run in demo mode.
- **The NIST guidance is a stored value with its source links** (`backend/app/engine/guidance.py`): minimum key sizes from
  SP 800-131A Rev. 2 and the retirement note from NIST IR 8547. It is not fetched or kept up to date by the app.
  - The note on the certificate result reads: "Under NIST IR 8547 (final, Oct 2026), ECDSA including P-256 is
    deprecated after 2030 and disallowed after 2035." The final report was published October 27, 2026, as the
    owner told us.
  - **The link is confirmed.** The owner told us on 11 November 2026 that
    `https://csrc.nist.gov/pubs/ir/8547/final` has been confirmed as the correct page for the final IR 8547.
    (The build machine still cannot reach the NIST site, so the build did not open the page itself.)
  - **The dates are checked against summaries, not yet against the NIST document itself.** The final report
    changed this from the 2024 draft. Three independent summaries of the final agree that all ECDSA, including
    P-256, is deprecated after 2030 and disallowed after 2035 (as the owner told us on 11 November 2026). Nobody
    has yet compared the app's wording with the NIST document itself. Confirm it there before relying on it,
    and update the value in `backend/app/engine/guidance.py` if it differs.
- **Old TLS versions:** the control accepts the version just below the oldest claimed one. SSL 3.0 and older are not tried.
- **Isolated mode needs the images prepared.** `./run-demo.sh` prepares them once when Docker is running (it
  downloads two pinned base images the first time, which needs internet). The app itself never downloads or builds.
  If Docker is running but the images are missing, the app stays in demo mode and says so. The mode is decided
  once when the app starts and never changes mid-run; if isolated mode stops working, tests show
  "Couldn't run (isolated mode is not available)" and do not fall back.
- **Isolated mode was built and tested on Linux with Docker Engine only.**
- **A changed locked test reads "Couldn't trust this run"**, not "Couldn't run": the job refuses to run it, and the
  review's first rule (the fingerprint no longer matches) decides the label.
- **Job state is kept in memory.** If the app is stopped while tests are waiting or running, those tests show
  "Not run yet" after a restart and must be run again. Finished results are kept.
- **One plan per imported file.** Running a test again keeps the old run in the database, but the screens and the
  download show the latest run only.

## Limits of the evidence download

- **The signing key is a local app key**, made on first start in `data/evidence-signing-key.pem` (readable by
  your user only). It proves a file was written by this copy of the app and not changed since. It does **not**
  prove who you are, it is not issued by anyone, and anyone who can read the `data/` folder can sign with it.
- **`python -m evidence verify` trusts the public key in this app's own `data/` folder by default** (or the one you
  give with `--public-key`). Someone checking a file on another computer needs that public key from you by a
  route they trust. With no key to compare with, the command says the signer could not be confirmed and does
  not report a pass. If `data/` is deleted, a new key is made and older files no longer verify against it.
- **The JSON file is the record. The HTML report is a readable copy and is not signed.** The report prints the
  JSON's fingerprint. The JSON does not contain the report's own SHA-256: the report prints the JSON's
  fingerprint, so each cannot contain the other.
- **The fingerprint does not include a trusted time.** Times in the file come from this computer's clock.
- **The evidence holds what Evidence Lab shows:** the claims, the latest Verify, and for each test in the plan the
  locked test, the latest reviewed run (and the retest run), its review and the worded result. Tests removed
  from the plan and older runs are left out. Raw outputs are included in full, so the file is a few hundred KB.
- **It also holds every fix as the Fixes step showed it** (phase 3a): the status with the reason beside it, the
  change (files, sizes, commit ids, SHA-256s), every proof with its runs in full and the review's answer, the
  pull request, each approval with name and time ("Demo data" beside a demo reviewer, and the one-login
  sentence), the merge, and the code every run ran on.
  - The ready-to-apply patch is in the file only while Download patch itself is allowed.
  - The fingerprint shown on the pull request is the fingerprint of the proof's record. It is listed inside the
    evidence file; it is not the fingerprint of the file.
  - For a proof, the first result each test was compared with is given by its run id, its fingerprint and its
    result. Its full record is in the file only while it is still that test's latest first result; if the test
    was run again afterwards, the newer run is the one in the file.
  - A pull request names the proof it was opened on. If the proof was run again later, the status and the
    fingerprint on screen follow the latest proof; the file holds every proof.
- **Private keys are masked before anything is stored or downloaded** (any field whose name contains "private", and
  any PEM private-key block). A secret in some other form inside a tool's output would not be recognised. The
  demo only ever uses throwaway test keys.
- **Since phase 5c a file can hold an Otto part** (the test packs, the assessment's Otto ledger, Claude's steps), and
  the verify command checks it too. Its last check, Otto's own audit, needs the Otto harness on the computer that
  runs the command; without it the command ends "not confirmed", which is not a pass. See "Limits of phase 5c".

## Things done early or differently, by owner decision

- **`acme-sign` 1.4.2 and a tiny demo-only runner were built in phase 1** so that all three Verify answers could be
  checked then.
- **`acme-sign` 1.4.2 was made stricter in phase 2** (it now rejects badly formed signature encodings), so that it
  has exactly one planted bug and gets exactly 3 of 484 official cases wrong (168, 171, 364).
- **The answer key is a DRAFT.** `demo/expected.json` says Adam has still to review it. The app agrees with all
  15 entries (V1 to V3, T1 to T5, R1 to R5, the controls, A1) in demo mode and in isolated mode on the build
  machine. The key also holds three answers (S1 to S3, under `after_server_fix`) for the server-setting step;
  they are not checked until that step is built. The build has not edited the key.
- **The Retest chooser starts the retest as soon as a version is picked** (no extra confirm button).
- **Login:** a "create your password" screen on first run instead of a preset password. There is no logout button,
  no password reset and no limit on login attempts. A forgotten password means deleting `data/evidence-lab.sqlite3`
  (which also deletes imports and results).
- **"Verify claims" stays switched off until every address is ticked.** Before every network test, at run time and
  again at retest time, the address is checked again: an address that is no longer ticked, or a name that now
  points somewhere else, is not contacted and the test shows "Couldn't run (address not confirmed)".

## Decided during the phase 3a build (approved by Kevin, 14 November 2026)

Kevin accepted every rule below after testing phase 3a end to end. They stand until he changes them.

- **The speed comparison is required.** A change is not offered unless the proof holds a "Speed and size" test
  that reads "No slowdown beyond measured noise" (see "When a change is offered" above).
- **An open pull request does not shield an out-of-date proof.** If the plan changes, the proof must pass again
  before anyone can approve, merge or download the patch. Approvals already given are kept, not cleared.
- **Only a newer result that says pass or fail closes a finding that a first result found.** "Couldn't run" and
  "Measured" do not close it. Only the results shown now are looked at, with the two effects described under
  "When a finding counts as open" above.
- **A failing test added after connecting joins the same code fix** instead of getting a text-only entry.
- **The proof needs the failed tests it answers.** If they were removed from the plan, the proof shows nothing
  about the fix and the change is not offered.
- **A report-only test is not counted as passed.** With the ML-DSA-65 comparison in the plan the sentence reads
  "... passed, the 1 report-only test ran, ...". Without one, the approved sentence is unchanged.

## Limits of the phase 1 checks

- **The demo only exercises three kinds of claim** (TLS versions, certificate, signature algorithm of a component).
  Cipher-suite and key-exchange claims are implemented and unit-tested against local test servers, but no demo claim uses them.
- **Key-exchange groups are checked on TLS 1.3 only.** For TLS 1.2 the app does not list the groups a server
  supports; a key-exchange claim about a server without TLS 1.3 comes back "Couldn't check".
  Groups tried: X25519, P-256, P-384, P-521, X448, ffdhe2048, ffdhe3072. No post-quantum groups in Verify
  (the post-quantum readiness test covers X25519MLKEM768).
- **An "only these groups" or "only these cipher suites" claim can come back False or "Couldn't check", never True.**
  The app tries a fixed list of groups, and only the cipher suites this computer's OpenSSL can offer. That is not
  every group or suite a server could accept, so the app can show such a claim is wrong (an unclaimed one was
  accepted, or a claimed one was refused) but cannot show the server uses nothing else.
- **"TLS 1.3 only" style claims can be True,** because all four TLS versions (1.0 to 1.3) are tried. SSL 3.0 and
  older are not tried.
- **TLS 1.3 cipher suites and groups need the `openssl` command-line tool.** Without it, those claims are "Couldn't check".
- **Older TLS versions depend on the local OpenSSL.** If the local library cannot offer TLS 1.0 to 1.2, the app falls
  back to a minimal hand-built hello that can only tell "refused because of the version" from "unknown".
- **Only clear refusals count as "refuses".** A dropped or reset connection is "unknown", and unknown never becomes True.
- **A TLS version counts as refused only when the server answers with the "protocol version" alert.** Any other
  "no" (for example "handshake failure" or "insufficient security") could be about the cipher suites offered rather
  than the version, so that version is "unknown" and the claim comes back "Couldn't check". Servers that refuse old
  versions with a different alert will therefore get "Couldn't check" rather than True.
- **Certificate claims compare key type, curve and key size.** The signature algorithm on the certificate is shown but not compared.
  Verify does not compare with NIST guidance; the Certificate strength test does.
- **Always "Couldn't check" for now:** signature-algorithm claims about a server, key-exchange claims about software,
  protocols other than TLS, and any software that isn't one of our demo components.
- **Some items in a CBOM are not checked, and the Import screen lists them** under the claims as
  "N items skipped: not checked in this version": algorithms that are not signatures or key exchange (hashes,
  encryption, MACs, key derivation), keys and other crypto material that no certificate claim was read from,
  signature or key-exchange algorithms that are only named inside a certificate or protocol entry, and cipher
  suite entries without a usable name or TLS version. They don't fit any claim type we check.
- **A wrong version of a demo component is "Couldn't check", not "False",** because only an exact name-and-version
  match is allowed to run (for example "acme-sign 1.4.4"). A wrong algorithm for 1.4.2 is "False".
- **A TLS protocol entry with no version in a CBOM** is kept as a claim that comes back "Couldn't check".
- **Up to 80 handshakes per address per run**, one at a time; the demo uses 4. If the first connection to an address
  fails, the rest are not attempted.
- **Network scope:** localhost, or addresses you tick. The tick is your statement that you may test it; the app cannot verify that.
- **Importing a file looks up no names.** Only IP addresses and `localhost` are shown with their IP straight away.
  Any other name is looked up when you tick its box, so a name that can't be found shows its error then, not on import.
- **The *Demo data* label follows what the file points at,** not which button was used: any file that names the
  demo server's address (`localhost:8443`) or one of our demo components (for example an uploaded
  `demo/claims-template.csv`) is labelled *Demo data*. For such a file the app reports on `localhost:8443` only if
  our demo server is what answers there; your own server on that port gets "Couldn't check". `127.0.0.1:8443`
  written as an IP address is not labelled.
- **CBOM components nested more than 50 levels deep** are refused with an error naming the field.
- **After a failed upload, nothing is imported:** the previous file's claims are cleared and only the error shows.
  Import the file (or the demo) again to carry on.
- **Files up to 1 MB and 500 claims.**
- **Some evidence items have a description instead of a shell command,** because the check was done inside the app
  (Python's `ssl` module) and no command was run. Command-line items show the real arguments.
- **The demo CBOM was checked against the CycloneDX 1.6 schema once by hand** (0 errors); that check is not an automated test.

## Limits of the tests of our own code

- The end-to-end test needs port 8443 free, so the app must be stopped while it runs.
- Tests that need real containers are skipped, with a message saying so, when Docker is not running or the images
  are not prepared.
- Tests that need the Otto harness (phase 5c) are skipped, with one line that says how many, where the harness is
  not installed. That includes GitHub's checks, which can't fetch a private repository.
- No test reaches Claude's API. Tests replay the recorded answers or answers written for the test; the live path is
  tested with a stand-in for the network.
- The backend tests use fewer timing repeats than the app (100 pairs instead of 200) to keep the run short. With
  much smaller counts the slowed control was sometimes missed; a missed control shows as "Couldn't trust this
  run", never as a wrong pass.
- The secrets scan looks for the keys it knows about (the evidence signing key, the demo TLS test key, the test
  key a component hands back during Verify) and for private-key markers. Test keys made inside the test harness
  never reach the app, so the scan checks what the harness sent back instead.
- Frontend unit tests use a mocked API; the real frontend-to-backend path is covered by the end-to-end test.
- **The accuracy command does not go through the Fixes step.** It checks the 15 answers with Retest on 1.4.3, as
  before. The Fixes flow is covered by the backend tests and by the end-to-end test, which presses Retest now
  after the merge and compares before and after with the answer key, entry by entry.
- The end-to-end test drives the Fixes step in demo mode. In isolated mode the proof has one backend test with
  real containers, and the whole flow was clicked through once by hand in a browser on the build machine
  (13 November 2026: proof passed after 56 seconds, before and after as the answer key says).
- A proof that fails because a signing test does not pass can't be produced with the buttons, so it has no
  end-to-end test and no screenshot. Backend tests cover it by making a test run out of time. The two failed
  states that buttons can reach (address no longer confirmed; plan changed) are in the end-to-end test.
- Most backend tests of the Fixes step play back made-up speed timings, so that they are quick and come out the
  same on a busy machine. The speed rule itself, the two full flows and the isolated-mode test time the real
  programs.
- The whole backend suite (`--full`) takes about 24 minutes and the end-to-end test about 20 since phase 4c (build machine, 4 cores, Docker ready); the accuracy check in isolated mode takes about 35. Since phase 4c+ the everyday run leaves the slow tests out and takes a few minutes; the slow ones run nightly on GitHub ("Slow checks") and by hand with `--full`.
- Dark mode only; no light theme. The layout was checked at 1440 x 900 only.
- Two type-only frontend packages (`@types/react`, `@types/react-dom`) are installed that are not listed in the spec.
  Strict TypeScript needs them; the owner should confirm.
