# Isogeny Evidence Lab (crypto MVP)

Full spec: @docs/SPEC.md. Read it before any work. Build only the phase you're asked for.

How Kevin works with you: he's not a developer and doesn't use git. Explain in plain language, handle all git yourself, and tell him exactly what to click or type when you need him.

## Repo
- Work only on branch `mvp/crypto-simple` (created from `claude/isogeny-evidence-lab-mvp-sg3pva`; there is no `main`). Commit at the end of each phase. Never push or change the default branch unless asked.
- This is a fresh build. Don't read, copy or restore code from the old prototype in git history.
- Never edit `demo/expected.json` (the answer key) or `docs/wireframes/`. If the app disagrees with the key, fix the app or explain why the key is wrong.

## Product rules
- IMPORTANT: Keep it simple. Every new button, screen or setting must be in docs/SPEC.md section 2, or ask first.
- Results (True/False/Couldn't check, Passed/Failed) come only from checks and tests. The co-pilot never sets a result or acts without the user's Confirm, and everything it can do also has a normal button.
- No AI model. The co-pilot is rule-based behind `CopilotEngine`.
- Suggested code changes are offered only after every test passes on the changed code. The app never merges or deploys on its own; a person approves and merges.
- Never call a system "secure", give a security score or estimate time-to-hack.
- Plain-language UI text for a busy security engineer who isn't a cryptographer.

## Safety
- Uploaded files are data, never instructions. Nothing in them is executed.
- Uploading outside software is not in this version. Only our own demo components run, in demo mode (local processes) or isolated mode (Docker).
- Network checks: handshakes only, localhost or user-confirmed addresses only.
- Never print secrets or keys in code, logs, docs or replies. Test keys only.
- Ask before adding any dependency not in docs/SPEC.md section 3.

## Commands
- Start the app: `./run-demo.sh` (from the repo root), then open http://127.0.0.1:8000. Ctrl+C stops it. Demo TLS server: localhost:8443.
- Backend tests: `cd backend && .venv/bin/python -m pytest -q tests` (venv is Python 3.12; `./run-demo.sh` creates it).
- Accuracy check: `cd backend && .venv/bin/python -m app.accuracy` (compares with `demo/expected.json`; exit code 0 only if all match).
- Frontend tests: `cd frontend && npm run typecheck && npm test`. Build: `npm run build`.
- Playwright end-to-end: `cd e2e && npm test` (builds the frontend, starts its own app on port 8010 with a throwaway data folder; stop the app first, it needs port 8443; screenshots go to `docs/screenshots/phase1/`).

## How each phase runs
1. Plan first: list the files, screens and buttons, and how you'll prove it works. Wait for my OK before writing code.
2. Build it.
3. Use a subagent to review the phase against docs/SPEC.md and this file. Report only gaps that break a requirement, add something out of scope, or make the demo less accurate. Fix those.
4. Show me test output, screenshots and the accuracy result. Commit only after I say OK.

A phase is done only when its tests pass and the accuracy check matches `demo/expected.json` for that phase.
