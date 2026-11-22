// Makes src/api.gen.ts, the screens' data types, from the backend's API description (src/api-schema.json).
// One source of truth: the shapes are written once, in backend/app/web/models.py; the backend writes the
// description (cd backend && .venv/bin/python tools/api_schema.py) and this script turns it into TypeScript.
//
//   npm run gen:api            write src/api.gen.ts
//   npm run gen:api -- --check only compare; exit code 1 if src/api.gen.ts is out of date
//
// Development-only (json-schema-to-typescript is a devDependency). The build itself never runs it.
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const SCHEMA = path.resolve(here, "../src/api-schema.json");
const OUT = path.resolve(here, "../src/api.gen.ts");
const check = process.argv.includes("--check");

const api = JSON.parse(readFileSync(SCHEMA, "utf8"));
const schemas = api.components?.schemas ?? {};

// The description points at its shapes as "#/components/schemas/Name"; the generator reads "#/$defs/Name".
// Pydantic also gives every property a title ("Claim Id"); without this, the generator would make a
// separate named type for each one. Only the shapes themselves keep their names.
function tidy(node, isShape) {
  if (Array.isArray(node)) return node.map((n) => tidy(n, false));
  if (node === null || typeof node !== "object") return node;
  const out = {};
  for (const [key, value] of Object.entries(node)) {
    // A list of a fixed length (a tuple) is written "prefixItems" in the description; the generator reads "items".
    if (key === "prefixItems") out.items = tidy(value, false);
    else if (key === "$ref" && typeof value === "string") out[key] = value.replace("#/components/schemas/", "#/$defs/");
    else if (key === "title" && !isShape) continue;
    else if (key === "default" || key === "discriminator") continue;
    else if (key === "properties")
      out[key] = Object.fromEntries(Object.entries(value).map(([k, v]) => [k, tidy(v, false)]));
    else out[key] = tidy(value, false);
  }
  return out;
}

const defs = Object.fromEntries(Object.entries(schemas).map(([name, s]) => [name, { ...tidy(s, true), title: name }]));
const root = { title: "ApiShapes", type: "object", additionalProperties: false, properties: {}, $defs: defs };

const body = await compile(root, "ApiShapes", {
  bannerComment: "",
  unreachableDefinitions: true,
  additionalProperties: false,
  strictIndexSignatures: true,
  format: true,
  style: { printWidth: 120, singleQuote: false, trailingComma: "all" },
});
// The empty root type is only the generator's entry point, and its "referenced by" notes say nothing useful.
const withoutRoot = body
  .replace(/export interface ApiShapes \{\s*\}\n*/, "")
  .replace(
    / \*\n \* This (?:interface|type) was referenced by `ApiShapes`'s JSON-Schema\n \* via the `definition` "[^"]+"\.\n/g,
    "",
  )
  .replace(
    /\/\*\*\n \* This (?:interface|type) was referenced by `ApiShapes`'s JSON-Schema\n \* via the `definition` "[^"]+"\.\n \*\/\n/g,
    "",
  );
const text =
  "// GENERATED from the backend's API description (src/api-schema.json). Do not edit by hand.\n" +
  "// The shapes live in backend/app/web/models.py; see scripts/gen-api-types.mjs for how to remake this file.\n\n" +
  withoutRoot.trimStart();

if (check) {
  let current = "";
  try {
    current = readFileSync(OUT, "utf8");
  } catch {
    // missing counts as out of date
  }
  if (current !== text) {
    console.error("src/api.gen.ts is out of date. Run: npm run gen:api (after tools/api_schema.py in the backend).");
    process.exit(1);
  }
  console.log("src/api.gen.ts is up to date.");
} else {
  writeFileSync(OUT, text);
  console.log(`Wrote ${path.relative(process.cwd(), OUT)} (${Object.keys(defs).length} shapes).`);
}
