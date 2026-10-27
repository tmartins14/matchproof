// Records the five walkthrough segments against the live site, one browser context each.
// Reads out/vo/segN.wav for target durations; writes out/clips/segN.webm and segN.json (the cuts build.sh keeps).
// Usage: npx tsx record.ts [segment numbers...]   (default: all)
import { mkdirSync, readdirSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { chromium, type Locator, type Page } from '@playwright/test';
import { segmentTexts, wavDuration } from './lib.ts';

const BASE = process.env.DEMO_BASE_URL ?? 'https://matchproof.tylermartins.com';
const SIZE = { width: 1920, height: 1080 };
const texts = segmentTexts();
const wanted = process.argv.slice(2).map(Number);
const segments = [1, 2, 3, 4, 5].filter((n) => wanted.length === 0 || wanted.includes(n));

const CURSOR_SCRIPT = `
(() => {
  const css = \`
    #mp-demo-cursor { position: fixed; left: 0; top: 0; width: 24px; height: 24px; margin: -12px 0 0 -12px; border-radius: 50%;
      background: rgba(255,255,255,.95); border: 3px solid #0b2a4a; box-shadow: 0 3px 12px rgba(0,0,0,.45); z-index: 2147483647;
      pointer-events: none; display: none; transition: transform .06s linear; }
    .mp-demo-ripple { position: fixed; width: 24px; height: 24px; margin: -12px 0 0 -12px; border-radius: 50%; border: 3px solid #d7f23c;
      z-index: 2147483646; pointer-events: none; animation: mp-demo-ripple .6s ease-out forwards; }
    @keyframes mp-demo-ripple { to { transform: scale(3.2); opacity: 0; } }
    .mp-demo-hl { outline: 4px solid #d7f23c !important; outline-offset: 5px; transform: scale(1.04); transition: transform .25s ease, outline-color .25s ease;
      position: relative; z-index: 50; box-shadow: 0 0 0 9999px rgba(0,0,0,0); }
    .mp-demo-zoom { outline: 4px solid #d7f23c !important; outline-offset: 6px; transform: scale(1.12); transform-origin: center left;
      transition: transform .35s ease; position: relative; z-index: 50; }
    #mp-demo-lower { position: fixed; left: 50%; bottom: 56px; transform: translateX(-50%); z-index: 2147483645; text-align: center;
      background: rgba(6,28,52,.94); color: #fff; padding: 18px 34px; border-left: 8px solid #d7f23c; font-family: 'Archivo', sans-serif; }
    #mp-demo-lower b { display: block; font-size: 38px; letter-spacing: .02em; }
    #mp-demo-lower span { font-size: 22px; opacity: .9; }\`;
  const boot = () => {
    const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);
    const dot = document.createElement('div'); dot.id = 'mp-demo-cursor'; document.body.appendChild(dot);
    addEventListener('mousemove', (e) => { dot.style.display = 'block'; dot.style.transform = 'translate(' + e.clientX + 'px,' + e.clientY + 'px)'; }, true);
    addEventListener('mousedown', (e) => {
      const r = document.createElement('div'); r.className = 'mp-demo-ripple'; r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
      document.body.appendChild(r); setTimeout(() => r.remove(), 700);
    }, true);
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', boot); else boot();
})();`;

interface Seg {
  n: number;
  page: Page;
  d: number; // voiceover seconds
  t0: number; // ms, page creation
  s0: number; // seconds into the video when the segment's choreography starts
  pos: { x: number; y: number };
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));
const mark = (s: Seg): number => (Date.now() - s.t0) / 1000;

/** Seconds into the segment's voiceover at which `phrase` starts, estimated from character position. */
function cueTime(s: Seg, phrase: string): number {
  const text = texts[s.n] ?? '';
  const i = text.indexOf(phrase);
  if (i < 0) throw new Error(`seg${s.n}: phrase not in voiceover: ${phrase}`);
  return (i / text.length) * s.d;
}

/** Wait until the voiceover reaches `phrase`, minus `lead` seconds so the cursor arrives as the words land. */
async function atCue(s: Seg, phrase: string, lead = 1.1): Promise<void> {
  const target = s.s0 + cueTime(s, phrase) - lead;
  const wait = (target - mark(s)) * 1000;
  if (wait > 0) await sleep(wait);
}

async function holdUntil(s: Seg, seconds: number): Promise<void> {
  const wait = (s.s0 + seconds - mark(s)) * 1000;
  if (wait > 0) await sleep(wait);
}

async function moveTo(s: Seg, loc: Locator, dx = 0, dy = 0): Promise<void> {
  const box = await loc.boundingBox();
  if (!box) throw new Error('moveTo: element has no box');
  const x = box.x + box.width / 2 + dx;
  const y = box.y + Math.min(box.height / 2, 60) + dy;
  await s.page.mouse.move(x, y, { steps: 30 });
  s.pos = { x, y };
}

async function glide(s: Seg, x: number, y: number): Promise<void> {
  await s.page.mouse.move(x, y, { steps: 30 });
  s.pos = { x, y };
}

async function click(s: Seg, loc: Locator): Promise<void> {
  await loc.scrollIntoViewIfNeeded();
  await moveTo(s, loc);
  await sleep(250);
  await s.page.mouse.down();
  await s.page.mouse.up();
}

async function centre(loc: Locator): Promise<void> {
  await loc.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  await sleep(900);
}

async function highlight(s: Seg, loc: Locator, hold = 1800, cls = 'mp-demo-hl'): Promise<void> {
  await centre(loc);
  await moveTo(s, loc);
  await loc.evaluate((el, c) => el.classList.add(c), cls);
  await sleep(hold);
  await loc.evaluate((el, c) => el.classList.remove(c), cls);
}

async function open(s: Seg, path: string): Promise<void> {
  await s.page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' });
  await s.page.evaluate(() => document.fonts.ready);
  await s.page.mouse.move(s.pos.x, s.pos.y);
}

type Cuts = Array<[number, number]>;
interface Result { cuts: Cuts; notes?: Record<string, unknown> }

async function seg1(s: Seg): Promise<Result> {
  await open(s, '/desk?narrator=gpt-4.1&fixture=fx-01');
  await glide(s, 1500, 260);
  await click(s, s.page.getByRole('button', { name: 'Replay pack run' }));
  const stamp = s.page.locator('.mp-bar-stamp .mp-stamp').first();
  await stamp.waitFor({ timeout: 90_000 });
  const checkingAt = mark(s);
  const head = s.page.locator('.mp-bar-head').first();
  await moveTo(s, head, -120);
  await s.page.locator('.mp-bar-stamp .mp-stamp[data-verdict="verified"]').first().waitFor({ timeout: 60_000 });
  const standsAt = mark(s);
  // Zoom the claim while the stamp has just landed.
  const claim = head.locator('xpath=..');
  await click(s, head);
  await claim.evaluate((el) => el.classList.add('mp-demo-zoom'));
  await sleep(4000);
  await claim.evaluate((el) => el.classList.remove('mp-demo-zoom'));
  const start = Math.max(0, standsAt - (s.d - 3.4));
  return { cuts: [[start, start + s.d + 0.5]], notes: { checkingAt, standsAt } };
}

async function seg2(s: Seg): Promise<Result> {
  await open(s, '/');
  s.s0 = mark(s);
  await glide(s, 1500, 700);
  // Slow scroll down the rows.
  for (let i = 0; i < 24; i++) { await s.page.mouse.wheel(0, 18); await sleep(110); }
  const rows = s.page.getByRole('row');
  const grok = rows.filter({ hasText: 'grok-4.7' }).first();
  await atCue(s, 'planted traps', 1.6);
  await highlight(s, s.page.getByRole('columnheader', { name: 'Traps' }), 2200);
  await atCue(s, 'seventy seconds');
  await highlight(s, grok.getByRole('cell').filter({ hasText: '70.2 s' }).first(), 2200);
  await atCue(s, 'fell for none');
  await highlight(s, rows.filter({ hasText: 'gpt-4.1' }).first(), 2400);
  await atCue(s, "That's the live pick", 1.8);
  await highlight(s, s.page.locator('.tr-picks > *').filter({ hasText: 'Live pick' }).first(), 1800);
  await atCue(s, 'Not cleared.', 2.2);
  const nano = rows.filter({ hasText: 'gpt-5-nano' }).first();
  await highlight(s, nano.getByText('Not cleared for air', { exact: true }).first(), 2200);
  await holdUntil(s, s.d + 0.5);
  return { cuts: [[s.s0, s.s0 + s.d + 0.5]] };
}

async function seg3(s: Seg): Promise<Result> {
  await open(s, '/compare/fx-02/bt-001815-set_piece_goal?focus=gpt-5-nano');
  s.s0 = mark(s);
  await glide(s, 1500, 420);
  // Pan the cards.
  for (const id of ['grok-4.7', 'gpt-4.1', 'gpt-5.4-mini', 'gpt-5-mini']) {
    await moveTo(s, s.page.locator(`[id="card-${id}"] h3, [id="card-${id}"] h2, [id="card-${id}"]`).first(), 0, 20);
    await sleep(700);
  }
  await atCue(s, "But nano couldn't", 2.4);
  const reason = s.page.locator('[id="card-gpt-5-nano"]').getByText('without citing the fact that names him');
  await highlight(s, reason, 2600);
  await atCue(s, 'And when the referee', 1.6);
  const moment = s.page.getByLabel('Moment', { exact: true });
  await moveTo(s, moment);
  await sleep(300);
  await moment.selectOption('bt-000894-momentum_swing');
  await s.page.waitForURL(/bt-000894/);
  const del = s.page.locator('[id="card-gpt-5-nano"] del').first();
  await del.waitFor();
  await highlight(s, del.locator('xpath=..'), 3000);
  await holdUntil(s, s.d + 0.5);
  return { cuts: [[s.s0, s.s0 + s.d + 0.5]] };
}

const FAILURE = /Live narration unavailable|desk is full|Connection lost/i;

async function seg4(s: Seg): Promise<Result> {
  await open(s, '/compare/fx-02/bt-000894-momentum_swing?focus=gpt-4.1');
  s.s0 = mark(s);
  await glide(s, 1300, 400);
  await click(s, s.page.locator('[id="card-gpt-4.1"]').getByRole('link', { name: 'Use on Desk' }));
  await s.page.waitForURL(/\/desk\?narrator=gpt-4\.1/);
  await s.page.waitForLoadState('networkidle');
  await sleep(600);
  const fixture = s.page.locator('select').nth(1);
  await moveTo(s, fixture);
  await sleep(300);
  await fixture.selectOption('fx-05');
  await sleep(700);
  const runStart = mark(s);
  await click(s, s.page.getByRole('button', { name: 'Run live' }));
  const preEnd = mark(s) + 1.0;

  const stampSel = '.mp-bar-stamp .mp-stamp:not([data-verdict="checking"])';
  const deadline = Date.now() + 90_000;
  let verdictAt = 0;
  let failure = '';
  let checkingAt = 0;
  while (Date.now() < deadline) {
    if (await s.page.locator('.mp-bar-stamp .mp-stamp').count() > 0 && !checkingAt) checkingAt = mark(s);
    if (await s.page.locator(stampSel).count() > 0) { verdictAt = mark(s); break; }
    const status = (await s.page.getByRole('status').allTextContents()).join(' ');
    if (FAILURE.test(status)) { failure = status.trim(); break; }
    await sleep(150);
  }
  if (!verdictAt) {
    return { cuts: [], notes: { fallback: true, reason: failure || 'no verdict within 90 s', runStart } };
  }
  const stamp = s.page.locator(stampSel).first();
  await sleep(500);
  await highlight(s, stamp, 2400);
  await highlight(s, s.page.locator('.mp-pitch'), 2400);
  await sleep(600);
  const post = s.d - (preEnd - s.s0);
  const postStart = verdictAt - (post - 6.4);
  return {
    cuts: [[s.s0, preEnd], [postStart, postStart + post + 0.5]],
    notes: { runClickedAt: runStart - s.s0, firstClaimAt: checkingAt - runStart, firstVerdictAfterRunClickSeconds: +(verdictAt - runStart).toFixed(1), verdict: await stamp.getAttribute('data-verdict') },
  };
}

/** Same beats as seg4 but with the cached pack run; used only when the live run fails. */
async function seg4Replay(s: Seg): Promise<Result> {
  await open(s, '/compare/fx-02/bt-000894-momentum_swing?focus=gpt-4.1');
  s.s0 = mark(s);
  await glide(s, 1300, 400);
  await click(s, s.page.locator('[id="card-gpt-4.1"]').getByRole('link', { name: 'Use on Desk' }));
  await s.page.waitForURL(/\/desk\?narrator=gpt-4\.1/);
  await s.page.waitForLoadState('networkidle');
  const fixture = s.page.locator('select').nth(1);
  await moveTo(s, fixture);
  await fixture.selectOption('fx-01'); // cached packs play pack fixtures only
  await click(s, s.page.getByRole('button', { name: 'Replay pack run' }));
  const preEnd = mark(s) + 1.0;
  const stampSel = '.mp-bar-stamp .mp-stamp[data-verdict="verified"]';
  await s.page.locator(stampSel).first().waitFor({ timeout: 90_000 });
  const verdictAt = mark(s);
  await sleep(500);
  await highlight(s, s.page.locator(stampSel).first(), 2400);
  await highlight(s, s.page.locator('.mp-pitch'), 2400);
  const post = s.d - (preEnd - s.s0);
  const postStart = verdictAt - (post - 6.4);
  return { cuts: [[s.s0, preEnd], [postStart, postStart + post + 0.5]], notes: { replay: true } };
}

async function seg5(s: Seg): Promise<Result> {
  await open(s, '/');
  await s.page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await sleep(500);
  s.s0 = mark(s);
  await glide(s, 1500, 520);
  await s.page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await sleep(1400);
  await s.page.evaluate(() => {
    const d = document.createElement('div');
    d.id = 'mp-demo-lower';
    d.innerHTML = '<b>matchproof.tylermartins.com</b><span>Microsoft Foundry · Agent Framework · Azure</span>';
    document.body.appendChild(d);
  });
  await holdUntil(s, s.d + 0.5);
  return { cuts: [[s.s0, s.s0 + s.d + 0.5]] };
}

const bodies: Record<number, (s: Seg) => Promise<Result>> = { 1: seg1, 2: seg2, 3: seg3, 4: seg4, 5: seg5 };

async function record(n: number, body: (s: Seg) => Promise<Result>): Promise<Result> {
  const d = wavDuration(`out/vo/seg${n}.wav`);
  const tmp = `out/clips/.raw${n}`;
  rmSync(tmp, { recursive: true, force: true });
  mkdirSync(tmp, { recursive: true });
  const browser = await chromium.launch({ headless: false, args: ['--hide-scrollbars', '--force-device-scale-factor=1', '--window-size=1920,1200'] });
  const context = await browser.newContext({ viewport: SIZE, deviceScaleFactor: 1, recordVideo: { dir: tmp, size: SIZE } });
  await context.addInitScript(CURSOR_SCRIPT);
  const page = await context.newPage();
  const s: Seg = { n, page, d, t0: Date.now(), s0: 0, pos: { x: 960, y: 700 } };
  let result: Result;
  try {
    result = await body(s);
  } finally {
    await context.close(); // flushes the video
    await browser.close();
  }
  const file = readdirSync(tmp).find((f) => f.endsWith('.webm'));
  if (!file) throw new Error(`seg${n}: no video written`);
  renameSync(`${tmp}/${file}`, `out/clips/seg${n}.webm`);
  rmSync(tmp, { recursive: true, force: true });
  console.log(`seg${n}: vo ${d.toFixed(2)} s`, JSON.stringify(result.notes ?? {}));
  return result;
}

mkdirSync('out/clips', { recursive: true });
for (const n of segments) {
  let result = await record(n, bodies[n]!);
  if (n === 4 && result.notes?.fallback) {
    console.log(`seg4: LIVE RUN FAILED (${String(result.notes.reason)}); falling back to Replay pack run`);
    result = await record(n, seg4Replay);
    result.notes = { ...result.notes, fallback: true };
  }
  writeFileSync(`out/clips/seg${n}.json`, JSON.stringify(result, null, 2));
}
