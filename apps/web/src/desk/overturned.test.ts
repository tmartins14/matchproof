import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ClaimItem } from "@/components/desk/ClaimItem";
import { EvidenceRail } from "@/components/desk/EvidenceRail";
import { overturnedLines } from "./claimLines";
import { copy } from "./copy";
import { fixture } from "./fixture";
import { buildRail } from "./railModel";

const blocked = fixture.claims.find((c) => c.verdict === "blocked");
const unescape = (text: string): string => text.replace(/&#x27;/g, "\'").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
const struck = (html: string): string[] => [...html.matchAll(/class="mp-struck[^"]*"[^>]*>([^<]*)</g)].map((m) => unescape(m[1] ?? ""));

describe("overturned claim with a retry", () => {
  it("lists the first draft, then the rewrite", () => {
    expect(blocked?.draft_text).toBeTruthy();
    for (const lang of ["en", "es"] as const) {
      const lines = overturnedLines(blocked!, copy[lang]);
      expect(lines).toEqual([
        { label: copy[lang].claim.firstDraft, text: blocked!.draft_text },
        { label: copy[lang].claim.rewrite, text: blocked!.text },
      ]);
    }
  });

  it("shows the text alone when there is no draft", () => {
    const lone = { ...blocked!, draft_text: undefined };
    expect(overturnedLines(lone, copy.en)).toEqual([{ text: blocked!.text }]);
  });

  it("strikes the same sentences in the feed and the rail", () => {
    const view = { claim: blocked!, verdict: "blocked" as const, selected: true };
    const feed = renderToStaticMarkup(createElement(ClaimItem, { copy: copy.en, view, onPick: () => undefined }));
    const rail = buildRail(fixture, blocked!.fact_ids, blocked!.numbers.map((n) => n.fact_id), "en", copy.en);
    const railHtml = renderToStaticMarkup(createElement(EvidenceRail, { copy: copy.en, claim: view, rail }));
    expect(struck(feed)).toEqual([blocked!.draft_text, blocked!.text]);
    expect(struck(railHtml)).toEqual(struck(feed));
    expect(railHtml.indexOf(copy.en.claim.firstDraft)).toBeLessThan(railHtml.indexOf(copy.en.claim.rewrite));
  });
});
