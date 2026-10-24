import { describe, expect, it } from "vitest";
import { themes, tokenCssVars } from "./tokens";

describe("tokens", () => {
  it("has no undefined or empty value", () => {
    for (const [theme, tokens] of Object.entries(themes)) {
      for (const [name, value] of Object.entries(tokens)) {
        expect(value, `${theme}.${name}`).toBeTypeOf("string");
        expect(value.trim(), `${theme}.${name}`).not.toBe("");
      }
    }
  });

  it("writes one --mp- variable per token", () => {
    const vars = tokenCssVars("broadcast");
    expect(Object.keys(vars)).toHaveLength(Object.keys(themes.broadcast).length);
    expect(vars["--mp-lime"]).toBe("#D7F35B");
  });
});
