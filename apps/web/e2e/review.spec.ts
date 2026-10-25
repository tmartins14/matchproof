import { expect, test } from "@playwright/test";

const SIZES = [
  { name: "1440", width: 1440, height: 900 },
  { name: "390", width: 390, height: 844 },
];

for (const size of SIZES) {
  for (const lang of ["en", "es"]) {
    test(`stat card names stay inside the card, at ${size.name} in ${lang}`, async ({ page }) => {
      await page.setViewportSize(size);
      await page.goto(`/review/stat-cards?lang=${lang}`);
      await page.evaluate(() => document.fonts.ready);
      const cards = page.locator(".mp-review-card");
      expect(await cards.count()).toBeGreaterThanOrEqual(50);
      for (let i = 0; i < (await cards.count()); i++) {
        const card = cards.nth(i);
        const family = await card.getAttribute("data-family");
        // The fact id under the name is the proof and keeps its underscores; the name is what a viewer reads.
        expect(await card.locator(".mp-card-label b").innerText(), family ?? "").not.toMatch(/_/);
        const box = await card.locator(".mp-card").boundingBox();
        const label = await card.locator(".mp-card-label b").boundingBox();
        if (!box || !label) throw new Error(`no box for ${family}`);
        expect(label.x, `${family} left`).toBeGreaterThanOrEqual(box.x - 0.5);
        expect(label.x + label.width, `${family} right`).toBeLessThanOrEqual(box.x + box.width + 0.5);
        expect(label.y + label.height, `${family} bottom`).toBeLessThanOrEqual(box.y + box.height + 0.5);
      }
    });
  }
}
