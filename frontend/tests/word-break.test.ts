import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const css = readFileSync(fileURLToPath(new URL("../src/app/globals.css", import.meta.url)), "utf8");
const htmlRule = css.match(/\bhtml\s*\{([^}]*)\}/)?.[1] ?? "";

describe("korean line breaking", () => {
  it("keeps korean words whole and breaks only words longer than a line", () => {
    expect(htmlRule).toMatch(/\bword-break:\s*keep-all;/);
    expect(htmlRule).toMatch(/\boverflow-wrap:\s*break-word;/);
  });
});
