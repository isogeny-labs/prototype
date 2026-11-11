# Limits: what is real, what is demo, what is not built

Updated at the end of **phase 2** (Tests and Evidence Lab). Updated each phase.

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
  runs and reviews. Shapes are in [ENGINE.md](ENGINE.md).
- **Isolated mode really is a locked-down container** when Docker is running and the images are prepared: no
  network, read-only files except a scratch folder, a non-root user, no extra permissions, memory, processor and
  process limits, a time limit, and nothing from this computer mounted in. Tests of our own code check this.
- **The speed numbers are measured** on this computer, by the component timing itself. The slowdown rule and the
  measured noise band are written into the locked test.
- **The evidence file is really signed** and `python -m evidence verify` fails on any one-byte change.
- **Both import formats are parsed for real** (CycloneDX 1.6 CBOM JSON and our CSV template). Nothing in an
  imported file is ever executed.
- **Login is real:** you create a password on first run; only a scrypt hash is stored.

## What is demo

- **The demo file** (`demo/acme-pay-cbom.json`) describes a fictional "Acme Pay" service. It is labelled *Demo data*.
- **The demo TLS server** is a small server the app starts on `localhost:8443`. It is deliberately set up to accept
  TLS 1.2 with an older cipher as well as TLS 1.3.
- **The demo certificate** is a self-signed test certificate the app makes on first start (ECDSA P-256).
  It and its test key live in `data/` and are never shown in evidence.
- **`acme-sign` 1.4.2 and 1.4.3** are our own small demo programs written for this demo. 1.4.2 has one planted bug
  (it never checks that the two signature numbers are in range, so it accepts r = 0, s = 0). 1.4.3 is the same code
  plus that check. They are slow, simple Python and are not production software.
- **The controls are ours too:** an accept-everything signer, a deliberately slowed signer (6 ms added to every
  sign and verify), a test server that accepts an older TLS version, a test server with a deliberately weak
  RSA 1024-bit test certificate, and a test server that does offer the post-quantum key exchange.
- **The bad-signature list** (16 cases: 14 that must be rejected, 2 genuine ones that must be accepted) was built
  once by us from a throwaway test key that was then discarded. It is fixed data, not an official set.
- **Demo mode is not isolated.** Without Docker, or before the images are prepared, the demo components run as
  normal local programs with a time limit. The line under the step bar says which mode is in use and why.
- **Suggested fixes are fixed sentences** ("update to acme-sign 1.4.3 ..."), not a code change. The suggested
  change with proof is phase 3.

## Not built, or not connected, in this version

- **Uploading outside software is not in this version** (owner decision in phase 2). There is no screen, button or
  API address that accepts software. Only our own demo components run. Retest chooses only between our two demo
  versions, 1.4.2 and 1.4.3. A file that names any other software gets "Couldn't check" in Verify and
  "Couldn't run (only our demo components can be run in this version)" in the tests.
- **No AI model and no research engine are connected.** Tests are proposed by fixed rules and reviewed by fixed
  rules. Both are code from this same build, written by the same people: the review is a separate step with
  its own module, not an independent second opinion.
- **Dig deeper answers nothing.** It saves a research request marked "waiting for research engine" and shows it as
  queued. Nothing looks into it, and there is no screen for an answer yet.
- **The assistant panel is still empty** (phase 3), as are the suggested change with proof, pull requests, and the
  accuracy panel inside the app. The accuracy check is a command for now (`python -m app.accuracy`).
- **Mark reviewed** only records that you looked at a result, with the time. There is no undo and no name (there
  is one local login).
- **The catalog has two extra tests** (post-quantum readiness and the ML-DSA-65 comparison). No others.
- **No Ed25519 signing component exists in the demo.** `acme-sign` only does ECDSA P-256, so the official Ed25519
  file is run against the reference library only. That shows the file and the reference agree; it says nothing
  about any Ed25519 software of yours.

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
- **The NIST guidance is a stored value with its source links** (`backend/app/guidance.py`): minimum key sizes from
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
    and update the value in `backend/app/guidance.py` if it differs.
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
- **Private keys are masked before anything is stored or downloaded** (any field whose name contains "private", and
  any PEM private-key block). A secret in some other form inside a tool's output would not be recognised. The
  demo only ever uses throwaway test keys.

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
- The backend tests use fewer timing repeats than the app (100 pairs instead of 200) to keep the run short. With
  much smaller counts the slowed control was sometimes missed; a missed control shows as "Couldn't trust this
  run", never as a wrong pass.
- The secrets scan looks for the keys it knows about (the evidence signing key, the demo TLS test key, the test
  key a component hands back during Verify) and for private-key markers. Test keys made inside the test harness
  never reach the app, so the scan checks what the harness sent back instead.
- Frontend unit tests use a mocked API; the real frontend-to-backend path is covered by the end-to-end test.
- Dark mode only; no light theme. The layout was checked at 1440 x 900 only.
- Two type-only frontend packages (`@types/react`, `@types/react-dom`) are installed that are not listed in the spec.
  Strict TypeScript needs them; the owner should confirm.
