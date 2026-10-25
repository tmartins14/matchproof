import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { copy } from "@/desk/copy";
import { fixture } from "@/desk/fixture";
import { buildModel } from "@/desk/model";
import { KeyMomentRow } from "./KeyMomentRow";

const model = buildModel(fixture, { mode: "analyst", lang: "en", setupOpen: false });
const minuteClass = (label: string): string => {
  const row = { ...model.feed[0]!, beat: { ...model.feed[0]!.beat, label } };
  const html = renderToStaticMarkup(createElement(KeyMomentRow, { copy: copy.en, mode: "analyst", row, headline: "h", onBeat: () => undefined, onClaim: () => undefined }));
  return /class="(mp-minute[^"]*)"/.exec(html)?.[1] ?? "";
};

describe("key-moment minute block", () => {
  it("keeps the usual type up to six characters and the long type beyond", () => {
    for (const label of ["9′", "63′", "42–52′", "90+4′"]) expect(minuteClass(label), label).toBe("mp-minute num");
    for (const label of ["45+3–52′", "86–90+9′"]) expect(minuteClass(label), label).toBe("mp-minute mp-minute--long num");
  });
});
