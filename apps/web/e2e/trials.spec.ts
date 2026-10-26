import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const OUT = resolve(__dirname, "../../../docs/screenshots/ux");
const DESK = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };
const BEAT = "bt-001374-card"; // fx-01's red card, a trap moment
const COMPARE = `/compare/fx-01/${BEAT}?focus=gpt-5-nano`;

test.beforeAll(() => mkdirSync(OUT, { recursive: true }));

async function open(page: Page, path: string, size = DESK): Promise<void> {
  await page.setViewportSize(size);
  await page.goto(path);
  await page.evaluate(() => document.fonts.ready);
}

const overflow = (page: Page): Promise<number> => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("the Table loads on a direct visit and draws the export", async ({ page }) => {
  await open(page, "/");
  await expect(page).toHaveTitle("Matchproof Narrator Trials");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Cleared for air: gpt-5-mini, overturned on \d+ of 14 traps\./);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/gpt-5-nano: \d+ of 14\. Not cleared\./);
  await expect(page.getByText("How to read this")).toBeVisible();
  await expect(page.getByText("85 scored moments each")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(1 + 4 + 1); // head, four candidates, the divider
  await expect(page.getByText("Incomplete run")).toBeVisible();
  await expect(page.getByText(/Most accurate when it answered, but \d+ of 85 moments unanswered/)).toBeVisible();
  await expect(page.getByText("Only narrator cleared for air")).toBeVisible();
  await expect(page.getByText(/\d+ of \d+ overturned/)).toHaveCount(4);
  // Use on Desk only on cleared, measured rows, and it does not open Compare.
  const buttons = page.getByRole("link", { name: "Use on Desk" });
  await expect(buttons).toHaveCount(1);
  await buttons.click();
  await expect(page).toHaveURL(/\/desk\?narrator=gpt-5-mini&fixture=fx-\d\d$/);
});

test("a row opens Compare at the candidate's worst moment, by mouse and keyboard", async ({ page }) => {
  await open(page, "/");
  await page.getByRole("link", { name: "gpt-5-nano" }).first().click();
  await expect(page).toHaveURL(/\/compare\/fx-\d\d\/bt-[^?]+\?focus=gpt-5-nano$/);
  await open(page, "/");
  await page.getByRole("link", { name: "gpt-5-mini" }).first().focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/focus=gpt-5-mini/);
});

test("Compare loads on a direct visit, focuses the card and steps through moments", async ({ page }) => {
  await open(page, COMPARE);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Same moment. 4 narrators. One referee.");
  await expect(page.locator("#card-gpt-5-nano")).toHaveClass(/tr-ncard--focus/);
  await expect(page.getByRole("article")).toHaveCount(4);
  const url = page.url();
  await page.keyboard.press("ArrowRight");
  await expect(page).not.toHaveURL(url);
  await page.keyboard.press("ArrowLeft");
  await expect(page).toHaveURL(url);
});

test("/compare opens fx-01's first trap moment", async ({ page }) => {
  await open(page, "/compare");
  await expect(page).toHaveURL(new RegExp(`/compare/fx-01/${BEAT}`));
});

test("the Desk still loads at /desk and ?source=fixture", async ({ page }) => {
  await open(page, "/desk");
  await expect(page).toHaveTitle("Matchproof live desk");
  await open(page, "/desk?source=fixture");
  await expect(page.locator(".mp-header")).toBeVisible();
});

test("a Fixtures cell shows one stamp per trap and each opens Compare at that trap", async ({ page }) => {
  await open(page, "/fixtures");
  await expect(page.getByText("Each cell shows how that narrator called this fixture's traps.")).toBeVisible();
  const stamps = page.getByRole("link", { name: /61′: RED CARD 61′, .* Compare gpt-5-mini on fixture 01/ });
  await expect(stamps).toHaveCount(1);
  await stamps.click();
  await expect(page).toHaveURL(new RegExp(`/compare/fx-01/${BEAT}\\?focus=gpt-5-mini$`));
});

test("an AMENDED card shows the struck span and the bucket with its reason", async ({ page }) => {
  await open(page, "/compare/fx-01/bt-000588-territorial_spell?focus=gpt-5-mini");
  const card = page.locator("#card-gpt-5-mini");
  await expect(card.locator("del")).toContainText("are bossing the ball");
  await expect(card.locator("ins")).toHaveText(/\S/);
  await expect(card.getByText(/^overclaim: /)).toBeVisible();
  await page.screenshot({ path: `${OUT}/compare-amended-1440.png`, fullPage: true });
});

test("screenshots", async ({ page }) => {
  for (const [name, size] of [["1440", DESK], ["390", PHONE]] as const) {
    await open(page, "/", size);
    await page.screenshot({ path: `${OUT}/table-${name}.png`, fullPage: true });
    if (size === PHONE) expect(await overflow(page), "table page scrolls sideways").toBeLessThanOrEqual(0);
    await open(page, COMPARE, size);
    await page.screenshot({ path: `${OUT}/compare-${name}.png`, fullPage: true });
    if (size === PHONE) expect(await overflow(page), "compare page scrolls sideways").toBeLessThanOrEqual(0);
  }
});
