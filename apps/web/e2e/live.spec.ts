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
