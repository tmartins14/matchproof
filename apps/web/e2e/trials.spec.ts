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
  await expect(page.getByText("How to read this")).toHaveCount(0);
  await expect(page.getByText("Click a narrator to see its worst moment beside the others. Use on Desk puts a cleared narrator on air.")).toBeVisible();
  await expect(page.getByText("85 scored moments each")).toBeVisible();
  await expect(page.getByRole("row")).toHaveCount(1 + 4 + 1); // head, four candidates, the divider
  await expect(page.getByText("Not ranked: missed more than 1 in 10 moments")).toBeVisible();
  await expect(page.getByText(/Most accurate when it answered, but missed \d+ of 85 moments and takes \d+\.\d s per claim\. Also the auditor\./)).toBeVisible();
  const heads = await page.getByRole("columnheader").allTextContents();
  expect(heads.filter(Boolean)).toEqual(["#", "Narrator", "Stands", "Amended", "Overturned", "Pts", "Clean", "Traps", "p90", "$ / match", "Fail profile"]);
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
  await expect(page.getByText(/Each cell shows how that narrator called this fixture's \d+ traps/)).toBeVisible();
  const stamps = page.getByRole("link", { name: /61′: RED CARD 61′, .* Compare gpt-5-mini on fixture 01/ });
  await expect(stamps).toHaveCount(1);
  await stamps.click();
  await expect(page).toHaveURL(new RegExp(`/compare/fx-01/${BEAT}\\?focus=gpt-5-mini$`));
});

test("an AMENDED card shows the struck span and the bucket with its reason", async ({ page }) => {
  await open(page, "/compare/fx-01/bt-000588-territorial_spell?focus=gpt-5-mini");
  const card = page.locator("#card-gpt-5-mini");
  await expect(card.locator("del").first()).toHaveText(/\S/);
  await expect(card.locator("ins").first()).toHaveText(/\S/);
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

test("Compare reaches every match: the Fixture select goes to its first trap, the Moment select lists every moment", async ({ page }) => {
  await open(page, COMPARE);
  const fixture = page.getByLabel("Fixture", { exact: true });
  await fixture.selectOption("fx-03");
  await expect(page).toHaveURL(/\/compare\/fx-03\/bt-[^?]+\?focus=gpt-5-nano$/);
  const moment = page.getByLabel("Moment", { exact: true });
  const options = await moment.locator("option").allTextContents();
  expect(options.length).toBeGreaterThan(5);
  expect(options.filter((o) => o.includes("TRAP · "))).toHaveLength(2); // fx-03 plants two traps
  expect(options.some((o) => /^\d+′? .*TRAP · STOPPAGE-TIME PENALTY$/.test(o) || o.includes("TRAP · STOPPAGE-TIME PENALTY"))).toBe(true);
  const other = (await moment.locator("option:not(:checked)").first().getAttribute("value")) ?? "";
  await moment.selectOption(other);
  await expect(page).toHaveURL(new RegExp(`/compare/fx-03/${other}\\?focus=gpt-5-nano$`));
});

test("every page has the Desk's angled-stripe backdrop, below the top bar", async ({ page }) => {
  for (const path of ["/", "/fixtures", COMPARE, "/desk"]) {
    await open(page, path);
    await expect(page.locator(".mp-backdrop")).toHaveCount(1);
    const bar = await page.locator("header.tr-bar").boundingBox();
    const back = await page.locator(".mp-backdrop").boundingBox();
    expect(back?.y, path).toBeGreaterThanOrEqual((bar?.y ?? 0) + (bar?.height ?? 0) - 1);
  }
});

test("the top bar is pixel-identical on every page apart from the active nav item and stepper step", async ({ page }) => {
  for (const [name, size] of [["1440", DESK], ["390", PHONE]] as const) {
    const shots: Buffer[] = [];
    for (const path of ["/", "/fixtures", COMPARE, "/desk"]) {
      await open(page, path, size);
      await page.evaluate(() => window.scrollTo(0, 0));
      // Only the lit item and step may differ, so draw them as the unlit ones.
      await page.addStyleTag({ content: '.tr-nav-link[aria-current]{background:var(--mp-raised)!important;color:var(--mp-text)!important}.tr-step[aria-current]{color:var(--mp-muted)!important;border-bottom-color:transparent!important}' });
      shots.push(await page.locator("header.tr-bar").screenshot({ animations: "disabled" }));
    }
    for (const shot of shots) expect(shot.equals(shots[0]!), `top bar pixels at ${name}`).toBe(true);
    const boxes: number[][] = [];
    for (const path of ["/", "/fixtures", COMPARE, "/desk"]) {
      await open(page, path, size);
      await page.evaluate(() => window.scrollTo(0, 0));
      const box = await page.locator("header.tr-bar").boundingBox();
      boxes.push([box?.x ?? -1, box?.y ?? -1, box?.width ?? -1, box?.height ?? -1]);
    }
    for (const b of boxes) expect(b, `top bar box at ${name}`).toEqual(boxes[0]);
  }
  await open(page, "/desk");
  const strip = await page.locator(".mp-header--strip").boundingBox();
  const bar = await page.locator("header.tr-bar").boundingBox();
  expect(strip?.y).toBe((bar?.y ?? 0) + (bar?.height ?? 0));
  // No Desk backdrop behind the bar, and one bar on the page.
  await expect(page.locator("header.tr-bar")).toHaveCount(1);
  expect(await page.locator("header.tr-bar").evaluate((el) => el.closest(".mp-root") === null)).toBe(true);
});

for (const width of [1440, 1280, 1024]) {
  test(`no two text boxes in a Table row intersect at ${width}`, async ({ page }) => {
    await open(page, "/", { width, height: 900 });
    const clashes = await page.evaluate(() => {
      const out: string[] = [];
      for (const row of Array.from(document.querySelectorAll('[role="row"]'))) {
        const boxes: { cell: number; text: string; r: DOMRect }[] = [];
        Array.from(row.children).forEach((cell, i) => {
          const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
          for (let n = walker.nextNode(); n; n = walker.nextNode()) {
            if (!n.textContent?.trim()) continue;
            const range = document.createRange();
            range.selectNodeContents(n);
            for (const r of Array.from(range.getClientRects())) boxes.push({ cell: i, text: n.textContent.trim().slice(0, 30), r });
          }
        });
        for (let a = 0; a < boxes.length; a++)
          for (let b = a + 1; b < boxes.length; b++) {
            const x = boxes[a]!, y = boxes[b]!;
            if (x.cell === y.cell) continue;
            if (Math.min(x.r.right, y.r.right) - Math.max(x.r.left, y.r.left) > 1 && Math.min(x.r.bottom, y.r.bottom) - Math.max(x.r.top, y.r.top) > 1) out.push(`${x.text} / ${y.text}`);
          }
      }
      return out;
    });
    expect(clashes).toEqual([]);
  });
}
