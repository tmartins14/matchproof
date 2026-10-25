import { expect, test, type Page, type Route } from "@playwright/test";
import { asSse, recordedStream } from "../src/live/recorded";

const API = "http://localhost:8000";
const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type, last-event-id", "access-control-allow-methods": "GET, POST" };
const stream = recordedStream();
const fullTime = stream.find((m) => m.type === "status" && (m.data as { state: string }).state === "full_time");
const finalScore = (fullTime?.data as { score: { home: number; away: number } }).score;

/** Serves the recorded stream as the API would, and records what the page asked for. */
async function serveRecording(page: Page): Promise<string[]> {
  const calls: string[] = [];
  await page.route(`${API}/**`, async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    calls.push(`${request.method()} ${url.pathname}${url.search}`);
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
    if (url.pathname === "/matches") return route.fulfill({ json: { match_id: "m-red-card-flip-3" }, headers: CORS });
    if (url.pathname.endsWith("/stream")) return route.fulfill({ body: asSse(stream), headers: { ...CORS, "content-type": "text/event-stream", "cache-control": "no-cache" } });
    return route.fulfill({ status: 404, headers: CORS });
  });
  return calls;
}

test("kicking off plays the recorded match to full time", async ({ page }) => {
  const calls = await serveRecording(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Watch cached replay" })).toBeDisabled();
  await page.getByRole("button", { name: "6×" }).click();
  await page.getByRole("button", { name: "Kick off live" }).click();

  const scorebug = page.getByRole("group", { name: "Score" });
  await expect(scorebug).toContainText("FT");
  await expect(scorebug.locator(".mp-score")).toHaveText(`${finalScore.home}–${finalScore.away}`);
  expect(calls.some((c) => c === "POST /matches")).toBe(true);
  expect(calls.some((c) => c === "GET /matches/m-red-card-flip-3/stream?speed=6")).toBe(true);
  await expect(page.getByRole("button", { name: "New match" })).toBeVisible();
  await expect(page.getByText("Connection lost.")).toHaveCount(0);
});

test("a refused stream leaves the desk in pre-match with a notice", async ({ page }) => {
  await page.route(`${API}/**`, async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/matches") return route.fulfill({ json: { match_id: "m-red-card-flip-3" }, headers: CORS });
    return route.fulfill({ status: 503, json: { fallback: "cached" }, headers: CORS });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Kick off live" }).click();
  await expect(page.getByRole("status").filter({ hasText: "The desk is full right now" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kick off live" })).toBeEnabled();
});

test("fixture mode still renders the static desk", async ({ page }) => {
  await page.goto("/?source=fixture&beat=bt-000993-territorial_spell");
  await expect(page.locator('aside .mp-stamp[data-verdict="blocked"]').first()).toHaveText("OVERTURNED");
});

const LABELS = ["9′", "63′", "42–52′", "90+4′", "45+3–52′"];

for (const size of [{ name: "1440", width: 1440, height: 900 }, { name: "390", width: 390, height: 844 }]) {
  test(`headlines line up whatever the minute label, at ${size.name}`, async ({ page }) => {
    await page.setViewportSize(size);
    await page.goto(`/?source=fixture&labels=${encodeURIComponent(LABELS.join("|"))}`);
    await page.evaluate(() => document.fonts.ready);
    const rows = page.locator(".mp-bar-head");
    expect(await rows.count()).toBeGreaterThanOrEqual(LABELS.length);
    const found = await page.locator(".mp-minute").allTextContents();
    for (const label of LABELS) expect(found).toContain(label);
    const lefts = new Set<number>();
    for (const label of LABELS) {
      const row = page.locator(".mp-bar-head", { has: page.locator(".mp-minute", { hasText: new RegExp(`^${label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) }) });
      const minute = row.locator(".mp-minute");
      const headline = await row.locator(".mp-headline").boundingBox();
      if (!headline) throw new Error(`no headline for ${label}`);
      lefts.add(Math.round(headline.x * 10) / 10);
      const fits = await minute.evaluate((el) => el.scrollWidth <= el.clientWidth);
      expect(fits, `${label} fits its block`).toBe(true);
    }
    expect([...lefts]).toHaveLength(1);
  });
}
