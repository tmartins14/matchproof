import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const OUT = resolve(__dirname, "../../../docs/screenshots/12");
const DESK = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

test.beforeAll(() => mkdirSync(OUT, { recursive: true }));

async function open(page: Page, query: string, size = DESK): Promise<void> {
  await page.setViewportSize(size);
  await page.goto(`/${query}${query ? "&" : "?"}source=fixture`);
  await page.evaluate(() => document.fonts.ready);
}

test("full-page desk shots", async ({ page }) => {
  await open(page, "");
  await page.screenshot({ path: `${OUT}/desk-1440.png`, fullPage: true });
  await open(page, "?setup=open");
  await page.screenshot({ path: `${OUT}/setup-open-1440.png`, fullPage: true });
  await open(page, "?mode=fan");
  await page.screenshot({ path: `${OUT}/fan-1440.png`, fullPage: true });
  await open(page, "?mode=producer&beat=bt-000993-territorial_spell");
  await page.screenshot({ path: `${OUT}/producer-1440.png`, fullPage: true });
  await open(page, "?beat=bt-000993-territorial_spell");
  await page.screenshot({ path: `${OUT}/analyst-overturned-1440.png`, fullPage: true });
  await open(page, "?lang=es");
  await page.screenshot({ path: `${OUT}/es-1440.png`, fullPage: true });
  await open(page, "", PHONE);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({ path: `${OUT}/desk-390.png`, fullPage: true });
});

test("key-moments column crop", async ({ page }) => {
  await open(page, `?labels=${encodeURIComponent("9′|63′|42–52′|90+4′|45+3–52′")}`);
  await page.locator("section.mp-col-feed").screenshot({ path: `${OUT}/feed-1440.png` });
});

async function controlsShot(page: Page, size: { width: number; height: number }, name: string): Promise<void> {
  await open(page, "", size);
  const header = await page.locator("header.mp-header").boundingBox();
  const setup = await page.locator("section.mp-setup").boundingBox();
  if (!header || !setup) throw new Error("no header or setup bar");
  const bottom = setup.y + setup.height;
  await page.screenshot({ path: `${OUT}/${name}`, clip: { x: 0, y: header.y, width: size.width, height: bottom - header.y + 14 } });
}

test("controls crops", async ({ page }) => {
  await controlsShot(page, DESK, "controls-1440.png");
  await controlsShot(page, PHONE, "controls-390.png");
});

const STAMPS: [string, string, string][] = [
  ["checking", "", "CHECKING"],
  ["verified", "?beat=bt-001484-card", "STANDS"],
  ["rephrased", "?claim=cl-001670-open_play_goal-01&stamp=rephrased", "AMENDED"],
  ["blocked", "?beat=bt-000993-territorial_spell", "OVERTURNED"],
  ["delayed", "?stamp=delayed", "HELD"],
];

for (const [verdict, query, label] of STAMPS) {
  test(`stamp ${label}`, async ({ page }) => {
    await open(page, query);
    const stamp = page.locator(`aside .mp-stamp[data-verdict="${verdict}"]`).first();
    await expect(stamp).toHaveText(label);
    await stamp.evaluate((el) => el.scrollIntoView({ block: "center" }));
    const box = await stamp.boundingBox();
    if (!box) throw new Error(`no box for ${label}`);
    const pad = 16;
    await page.screenshot({
      path: `${OUT}/stamp-${verdict}.png`,
      clip: { x: Math.max(0, box.x - pad), y: Math.max(0, box.y - pad), width: box.width + 2 * pad, height: box.height + 2 * pad },
    });
  });
}
