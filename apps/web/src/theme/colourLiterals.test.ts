import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// ADR 0006: components read tokens only. Fail on colour literals in components and viz.
const ROOTS = ["src/components", "src/viz"];
const LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\(|(?<![-\w])(?:white|black|red|green|blue|yellow|orange|purple|pink|grey|gray|cyan|magenta|lime|navy|teal)(?![-\w])(?=\s*[;"'`,)])/;

function walk(dir: string): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
  return entries.flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return walk(path);
    return /\.(tsx?|css)$/.test(name) && !name.endsWith(".test.ts") && !name.endsWith(".test.tsx") ? [path] : [];
  });
}

export function findColourLiterals(roots: string[] = ROOTS): string[] {
  const hits: string[] = [];
  for (const file of roots.flatMap(walk)) {
    readFileSync(file, "utf8").split("\n").forEach((line, index) => {
      if (LITERAL.test(line)) hits.push(`${file}:${index + 1}: ${line.trim()}`);
    });
  }
  return hits;
}

describe("colour literals", () => {
  it("none in src/components or src/viz", () => {
    expect(findColourLiterals()).toEqual([]);
  });
});
