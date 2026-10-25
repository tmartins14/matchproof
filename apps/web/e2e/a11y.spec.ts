import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// The CHECKING pulse stops under reduced motion; axe would otherwise sample it mid-fade.
test.use({ reducedMotion: "reduce" });

const SIZES = [
  { name: "1440", width: 1440, height: 900 },
  { name: "390", width: 390, height: 844 },
  { name: "1920", width: 1920, height: 1080 },
];
const QUERIES = ["", "?setup=open", "?mode=fan"];

for (const size of SIZES) {
  for (const query of QUERIES) {
    test(`axe ${size.name} ${query || "default"}`, async ({ page }) => {
      await page.setViewportSize(size);
      await page.goto(`/${query}${query ? "&" : "?"}source=fixture`);
      const results = await new AxeBuilder({ page }).analyze();
      const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      console.log(`axe ${size.name} ${query || "default"}: ${results.violations.length} violations, ${blocking.length} serious or critical`);
      for (const v of blocking) console.log(`  ${v.impact} ${v.id}: ${v.nodes.length} nodes, e.g. ${v.nodes[0]?.target.join(" ")}`);
      expect(blocking).toEqual([]);
    });
  }
}
