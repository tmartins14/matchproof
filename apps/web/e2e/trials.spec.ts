import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const OUT = resolve(__dirname, "../../../docs/screenshots/15");
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
  await expect(page.getByRole("heading", { level: 1 })).toContainText("4 narrator models. 6 rigged fixtures. One fixed referee.");
  await expect(page.getByRole("row")).toHaveCount(1 + 4 + 1); // head, four candidates, the divider
  await expect(page.getByText("Incomplete run")).toBeVisible();
  await expect(page.getByText("68 of 85 moments unanswered")).toBeVisible();
  await expect(page.getByText("Also the auditor; shares capacity with the referee.")).toBeVisible();
  // Use on Desk only on cleared, measured rows, and it does not open Compare.
  const buttons = page.getByRole("link", { name: "Use on Desk" });
  await expect(buttons).toHaveCount(1);
  await buttons.click();
  await expect(page).toHaveURL(/\/desk\?narrator=gpt-5-mini&fixture=fx-01$/);
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

test("fixtures placeholder", async ({ page }) => {
  await open(page, "/fixtures");
  await expect(page.getByText("Fixtures: coming in prompt 16")).toBeVisible();
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
