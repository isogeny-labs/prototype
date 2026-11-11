# Limits: what is real, what is demo, what is not built

Written at the end of **phase 1** (Import and Verify). Updated each phase.

## What is real

- **The TLS checks are real handshakes.** Verify connects to the address and records what the server actually
  accepts and refuses. Nothing is simulated, and the result comes only from that output.
- **The certificate check is real.** It reads the certificate the server actually serves (key type, curve, key size).
- **The signing component check is real.** The app runs the component's `info` command, does one normal
  sign-and-verify round trip, and has an independent library (`cryptography`) confirm the key and signature.
- **Both import formats are parsed for real** (CycloneDX 1.6 CBOM JSON and our CSV template), with errors that name the line or field.
  Nothing in an imported file is ever executed.
- **Evidence is stored for every result:** what was run, the raw output, the time, the duration and the tool version.
- **Login is real:** you create a password on first run; only a scrypt hash is stored.

## What is demo

- **The demo file** (`demo/acme-pay-cbom.json`) describes a fictional "Acme Pay" service. It is labelled *Demo data* in the app.
- **The demo TLS server** is a small server the app starts on `localhost:8443`. It is deliberately set up to accept
  TLS 1.2 with an older cipher as well as TLS 1.3, so the "TLS 1.3 only" claim comes back False.
- **The demo certificate** is a self-signed test certificate the app generates on first start (ECDSA P-256).
  It and its test key live in `data/` and are never shown in evidence.
- **`acme-sign` 1.4.2** is our own deliberately flawed demo software (its verifier accepts r = 0, s = 0).
  Verify does not look for that flaw; phase 2's tests do. So Verify correctly says "True" for the claim
  "acme-sign 1.4.2 implementing ECDSA P-256".
- **Demo mode is not isolated.** The demo component runs as a normal local process with a time limit, not in a container.
  The screen says so. Only our own demo components can run; other software named in a file gets "Couldn't check".

## Things done early or differently, by owner decision

- **`acme-sign` 1.4.2 and a tiny demo-only runner were built in phase 1** (they belong to phase 2 in the spec) so
  that all three Verify answers (V1 to V3) could be checked now. Nothing else from phase 2 was built.
- **The answer key is a DRAFT.** `demo/expected.json` says Adam has still to confirm every entry. Phase 1 was built
  against V1 to V3 as written and the app agrees with all three (3 of 3). If Adam changes an entry, the app's
  answer for it must be looked at again. The build has not edited the key.
- **Login:** a "create your password" screen on first run instead of a preset password. There is no logout button,
  no password reset and no limit on login attempts. A forgotten password means deleting `data/evidence-lab.sqlite3`
  (which also deletes imports and results).
- **"Verify claims" stays switched off until every address is ticked.** If the app is asked to verify anyway,
  unticked addresses come back "Couldn't check" and are not contacted.

## Not built yet

- **Phase 2:** the Tests screen, the Evidence Lab screen, the job runner, the five tests and their controls,
  `acme-sign` 1.4.3, retest with before and after, evidence download, the signed fingerprint, `docs/ADAPTER.md`,
  uploading outside software.
- **Isolated mode (Docker) is not built and not tested.** Docker's program is installed on the build machine but the
  Docker service is not running there, so nothing could be run in a container. When it is built, its tests will be
  skipped with a clear message wherever Docker isn't running.
- **Phase 3:** the rule-based assistant (the panel is there but empty, with no input box), the accuracy panel in the
  app (the accuracy check is a command for now), polish, and the full end-to-end run from the spec's section 12.
- **Post-quantum detection will be "Couldn't run" on the build machine.** Detecting X25519MLKEM768 needs OpenSSL 3.5
  or newer. The build machine has OpenSSL 3.0.13 and no running Docker, so the phase 2 post-quantum readiness test
  will report "Couldn't run (needs OpenSSL 3.5 or newer)" there, never a guess.

## Limits of the phase 1 checks

- **The demo only exercises three kinds of claim** (TLS versions, certificate, signature algorithm of a component).
  Cipher-suite and key-exchange claims are implemented and unit-tested against local test servers, but no demo claim uses them.
- **Key-exchange groups are checked on TLS 1.3 only.** For TLS 1.2 the app does not list the groups a server
  supports; a key-exchange claim about a server without TLS 1.3 comes back "Couldn't check".
  Groups tried: X25519, P-256, P-384, P-521, X448, ffdhe2048, ffdhe3072. No post-quantum groups (see above).
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
  No check against NIST guidance yet (that is phase 2's certificate test).
- **Always "Couldn't check" for now:** signature-algorithm claims about a server, key-exchange claims about software,
  protocols other than TLS, and any software that isn't one of our demo components.
- **Some items in a CBOM are not checked, and the Import screen lists them** under the claims as
  "N items skipped: not checked in this version": algorithms that are not signatures or key exchange (hashes,
  encryption, MACs, key derivation), keys and other crypto material that no certificate claim was read from,
  signature or key-exchange algorithms that are only named inside a certificate or protocol entry, and cipher
  suite entries without a usable name or TLS version. They don't fit any claim type we check.
- **A wrong version of a demo component is "Couldn't check", not "False",** because only an exact name-and-version
  match is allowed to run in demo mode (for example "acme-sign 1.4.3" today). A wrong algorithm for 1.4.2 is "False".
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
- Frontend unit tests use a mocked API; the real frontend-to-backend path is covered by the end-to-end test.
- Dark mode only; no light theme. The layout was checked at 1440 x 900 only.
- Two type-only frontend packages (`@types/react`, `@types/react-dom`) are installed that are not listed in the spec.
  Strict TypeScript needs them; the owner should confirm.
