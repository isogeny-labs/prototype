# Lint and code style tools (development only)

ESLint and Prettier for the frontend (`frontend/`) and the end-to-end tests (`e2e/`). The app never imports them, and
`./run-demo.sh` does not install them. The GitHub check "Lint and code style" (`.github/workflows/checks.yml`) runs them.

This folder has its own `package.json`, because ESLint's TypeScript parser needs TypeScript's JavaScript API. The
frontend's TypeScript 7 has no such API, so this folder carries TypeScript 6 for the parser only. The frontend's
type check stays `npm run typecheck` with its own TypeScript.

```sh
npm --prefix lint ci                                    # once
npm --prefix lint run lint -- frontend e2e lint         # ESLint (what the check runs)
python3 tools/ci_style.py origin/mvp/crypto-simple       # code style of the files you added or edited
python3 tools/ci_style.py origin/mvp/crypto-simple --fix # format those files
```

- **ESLint** (`lint/eslint.config.js`): recommended JavaScript, TypeScript and React hooks rules. The findings that
  were already there when the check was added are in `lint/eslint-suppressions.json`. A new finding fails the check.
  After a real fix, run `npm --prefix lint run lint -- --prune-suppressions frontend e2e lint` to shrink the baseline.
  Never change what code does just to satisfy a rule.
- **Code style** (`.prettierrc.json` for TypeScript, JavaScript and CSS; `backend/ruff.toml` and `ruff format` for
  Python): a file a change **adds** must be formatted, or the check fails. A file a change **edits** that is not
  formatted gets a warning only. The code that was there before is not held to the style yet; reformatting it all at
  once is the owner's decision. Formatting changes layout only.
