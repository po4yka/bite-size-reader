#!/usr/bin/env node
/**
 * check-api-types.mjs
 *
 * CI guard: verifies that the three core API modules do NOT declare hand-written
 * interfaces for types that must be derived from generated.ts.
 *
 * Exits 1 (with an explanation) if any of the banned patterns are found.
 * Exits 0 if all checks pass.
 *
 * Extend RULES below as more modules are migrated.
 */

import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const API_DIR = resolve(__dirname, "../src/api");

/**
 * Each rule describes a file + a list of interface names that must NOT appear
 * as hand-written `interface <Name>` declarations in that file.
 *
 * The pattern matches:
 *   interface SummaryCompact {
 *   export interface SummaryCompact {
 * but NOT:
 *   // interface SummaryCompact (comment)
 *   type SummaryCompact = ...  (type alias — allowed)
 *   import type { SummaryCompact } (import — allowed)
 */
const RULES = [
  {
    file: "summaries.ts",
    bannedInterfaces: ["SummaryCompact", "SummaryDetail"],
  },
  {
    file: "auth.ts",
    bannedInterfaces: ["SummaryCompact", "SummaryDetail", "Request"],
  },
  {
    file: "requests.ts",
    bannedInterfaces: ["SummaryCompact", "SummaryDetail"],
  },
];

let failed = false;

for (const { file, bannedInterfaces } of RULES) {
  const filePath = resolve(API_DIR, file);
  let source;
  try {
    source = readFileSync(filePath, "utf8");
  } catch (err) {
    console.error(`check-api-types: cannot read ${filePath}: ${err.message}`);
    process.exit(1);
  }

  const lines = source.split("\n");

  for (const name of bannedInterfaces) {
    // Match `interface Name` preceded only by optional `export` and whitespace.
    // The leading ^ (after stripping) ensures we skip commented-out lines.
    const pattern = new RegExp(`^\\s*(?:export\\s+)?interface\\s+${name}\\b`);

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      // Skip comment lines
      if (/^\s*\/\//.test(line) || /^\s*\*/.test(line)) continue;
      if (pattern.test(line)) {
        console.error(
          `\ncheck-api-types FAIL: ${file}:${i + 1}\n` +
            `  Found hand-written \`interface ${name}\` — this type must be\n` +
            `  derived from generated.ts (components["schemas"]) instead.\n` +
            `  Replace with:\n` +
            `    export type ${name} = components["schemas"]["<SchemaName>"];\n` +
            `  See docs/reference/frontend-web.md §Generated API Types for guidance.\n`,
        );
        failed = true;
      }
    }
  }
}

if (failed) {
  process.exit(1);
} else {
  console.log("check-api-types: all checks passed.");
  process.exit(0);
}
