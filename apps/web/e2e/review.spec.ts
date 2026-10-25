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

for (const size of SIZES) {
  for (const lang of ["en", "es"]) {
    test(`every headline beside every stamp stays inside its bar, at ${size.name} in ${lang}`, async ({ page }) => {
      await page.setViewportSize(size);
      await page.goto(`/review/key-moments?lang=${lang}`);
      await page.evaluate(() => document.fonts.ready);
      const rows = page.locator(".mp-moment-row");
      expect(await rows.count()).toBeGreaterThanOrEqual(50);
      const failures: string[] = [];
      for (let i = 0; i < (await rows.count()); i++) {
        const row = rows.nth(i);
        const bar = await row.locator(".mp-bar-head").boundingBox();
        const stamp = await row.locator(".mp-stamp").boundingBox();
        const headline = row.locator(".mp-headline");
        const text = (await headline.innerText()).replace(/\s+/g, " ");
        const stampText = await row.locator(".mp-stamp").innerText();
        if (!bar || !stamp) throw new Error(`no box for row ${i}`);
        const inside = stamp.x >= bar.x - 0.5 && stamp.x + stamp.width <= bar.x + bar.width + 0.5 && stamp.y >= bar.y - 0.5 && stamp.y + stamp.height <= bar.y + bar.height + 0.5;
        const wordsFit = await headline.evaluate((el) => el.scrollWidth <= el.clientWidth + 1);
        // The stamp keeps the right edge of the bar, less the 12 px padding.
        const atRightEdge = Math.abs(bar.x + bar.width - 12 - (stamp.x + stamp.width)) <= 1;
        if (!inside || !wordsFit || !atRightEdge) failures.push(`${text} / ${stampText}: inside ${inside}, words fit ${wordsFit}, right edge ${atRightEdge}`);
      }
      expect(failures).toEqual([]);
    });
  }
}
