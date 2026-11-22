// ESLint for the frontend and the end-to-end tests (development-only; the app never imports it).
// Run from the repository root: `npm --prefix lint run lint -- frontend e2e` (see lint/README.md).
//
// The rules read each file alone (no type information). This folder carries its own TypeScript 6 for the parser,
// because the frontend's TypeScript 7 has no JavaScript API to parse with.
//
// Findings that were already there when this check was added are in lint/eslint-suppressions.json (the baseline,
// like the "# noqa" comments of ruff). A new finding fails the check. Never change what the code does just to satisfy
// a rule; after a real fix, `npm --prefix lint run lint -- --prune-suppressions frontend e2e` shrinks the baseline.
import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/test-results/**",
      "**/playwright-report/**",
      // Generated from the backend's API description (npm run gen:api); its own check keeps it up to date.
      "frontend/src/api.gen.ts",
    ],
  },
  {
    files: ["frontend/**/*.{ts,tsx,js,mjs}", "e2e/**/*.{ts,js,mjs}", "lint/**/*.js"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    linterOptions: { reportUnusedDisableDirectives: "error" },
    rules: {
      // A leading underscore marks a name as unused on purpose, as tsc's noUnusedParameters already reads it.
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
          destructuredArrayIgnorePattern: "^_",
        },
      ],
    },
  },
  {
    files: ["frontend/src/**/*.{ts,tsx}"],
    extends: [reactHooks.configs.flat.recommended],
    languageOptions: { globals: globals.browser },
    // An error, not a warning, so that the findings already there go into the baseline and a new one fails.
    rules: { "react-hooks/exhaustive-deps": "error" },
  },
  {
    files: ["frontend/scripts/**", "frontend/vite.config.ts", "e2e/**", "lint/**"],
    languageOptions: { globals: globals.node },
  },
  // Last: switch off the rules that only argue about layout; Prettier decides layout.
  prettier,
);
