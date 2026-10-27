#!/usr/bin/env node
// Black-box UX audit for the deployed Narrator Trials site.
// Usage: node audit-checks.mjs <baseUrl> [--out file.json] [--sample N] [--concurrency N] [--shots dir]
//   --sample N   run layout checks on N compare pages (spread across fixtures) instead of all
//   default      layout checks on every crawled page
// Resolves @playwright/test and @axe-core/playwright from NODE_PATH, the cwd, or
// apps/web/node_modules next to this repo. Prints a JSON summary to stdout.
import { createRequire } from 'node:module';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const roots = [
  ...(process.env.NODE_PATH || '').split(path.delimiter).filter(Boolean),
  path.join(process.cwd(), 'node_modules'),
  path.resolve(here, '../../apps/web/node_modules'),
];
function load(name) {
  for (const r of roots) {
    try { return createRequire(path.join(r, 'x.js'))(name); } catch { /* try next root */ }
  }
  throw new Error(`cannot resolve ${name}; set NODE_PATH to a node_modules containing it`);
}
const { chromium } = load('@playwright/test');
const AxeBuilder = load('@axe-core/playwright').default || load('@axe-core/playwright').AxeBuilder;

const args = process.argv.slice(2);
const base = (args.find((a) => /^https?:/.test(a)) || '').replace(/\/$/, '');
if (!base) { console.error('usage: node audit-checks.mjs <baseUrl> [--out f] [--sample N]'); process.exit(2); }
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const outFile = opt('--out', null);
const sample = Number(opt('--sample', 0));
const conc = Number(opt('--concurrency', 4));
const shotsDir = opt('--shots', null);
if (shotsDir) fs.mkdirSync(shotsDir, { recursive: true });

const VIEWPORTS = [1440, 1280, 1024, 768, 390];
const origin = new URL(base).origin;

// ---------- crawl + link resolution ----------
async function crawl(browser) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const seen = new Map(); // url (path+search) -> {status, notFoundText, from}
  const queue = [['/', 'start']];
  const linkEdges = [];
  while (queue.length) {
    const [u, from] = queue.shift();
    if (seen.has(u)) continue;
    let status = 0, bodyText = '', hrefs = [];
    try {
      const r = await page.goto(origin + u, { waitUntil: 'networkidle', timeout: 45000 });
      status = r ? r.status() : 0;
      bodyText = await page.innerText('body');
      hrefs = await page.$$eval('a[href]', (as) => as.map((a) => a.href));
    } catch (e) { bodyText = 'ERR ' + e.message; }
    const finalUrl = new URL(page.url());
    seen.set(u, {
      status, from, finalPath: finalUrl.pathname + finalUrl.search,
      notFoundText: /not found|404/i.test(bodyText.slice(0, 400)),
    });
    for (const h of hrefs) {
      let x; try { x = new URL(h); } catch { continue; }
      if (x.origin !== origin) continue;
      const k = x.pathname + x.search;
      linkEdges.push(k);
      if (!seen.has(k)) queue.push([k, u]);
    }
  }
  await ctx.close();
  const links = [...seen].map(([url, v]) => ({ url, ...v }));
  const bad = links.filter((l) => l.status !== 200 || l.notFoundText);
  // canonical pages: dedupe by final pathname (query like ?focus= does not change layout much)
  const pages = [...new Set(links.filter((l) => l.status === 200).map((l) => l.finalPath.split('?')[0]))];
  return { links, bad, pages };
}

// ---------- in-page measurement ----------
const measure = () => {
  const out = { hscroll: null, innerScroll: [], clipped: [], overlaps: [], tap: [], topbar: null };
  const de = document.documentElement;
  out.hscroll = { scrollWidth: de.scrollWidth, clientWidth: de.clientWidth, over: de.scrollWidth > de.clientWidth };
  const label = (el) => el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const visible = (el) => {
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  // clipped text
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    const clipX = ['hidden', 'clip'].includes(cs.overflowX);
    const clipY = ['hidden', 'clip'].includes(cs.overflowY);
    if (['auto', 'scroll'].includes(cs.overflowX) && el.scrollWidth > el.clientWidth + 1 && visible(el)) {
      out.innerScroll.push({ el: label(el), sw: el.scrollWidth, cw: el.clientWidth, text: (el.innerText || '').trim().slice(0, 40) });
    }
    if (!(clipX || clipY)) continue;
    if (!(el.innerText || '').trim()) continue;
    if (!visible(el)) continue;
    const xs = clipX && el.scrollWidth > el.clientWidth + 1;
    const ys = clipY && el.scrollHeight > el.clientHeight + 1;
    if (xs || ys) {
      out.clipped.push({ el: label(el), text: el.innerText.trim().slice(0, 60), sw: el.scrollWidth, cw: el.clientWidth, sh: el.scrollHeight, ch: el.clientHeight, ellipsis: cs.textOverflow === 'ellipsis' });
    }
  }
  // overlapping text line boxes from different elements
  const rects = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    if (!n.nodeValue.trim()) continue;
    const pe = n.parentElement;
    if (!pe || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(pe.tagName) || !visible(pe)) continue;
    const range = document.createRange();
    range.selectNodeContents(n);
    for (const r of range.getClientRects()) {
      if (r.width < 2 || r.height < 2) continue;
      rects.push({ el: pe, l: r.left, t: r.top, r: r.right, b: r.bottom, text: n.nodeValue.trim().slice(0, 30) });
    }
  }
  rects.sort((a, b) => a.l - b.l);
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length && rects[j].l < rects[i].r - 1; j++) {
      const a = rects[i], b = rects[j];
      if (a.el === b.el) continue;
      const w = Math.min(a.r, b.r) - Math.max(a.l, b.l);
      const h = Math.min(a.b, b.b) - Math.max(a.t, b.t);
      if (w > 1 && h > 1 && h > 0.35 * Math.min(a.b - a.t, b.b - b.t)) {
        out.overlaps.push({ a: label(a.el) + ' "' + a.text + '"', b: label(b.el) + ' "' + b.text + '"', w: +w.toFixed(1), h: +h.toFixed(1) });
      }
    }
  }
  // tap targets
  for (const el of document.querySelectorAll('a[href],button,select,input,textarea,[role=button],[role=tab]')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 44 || r.height < 44) {
      const inline = el.tagName === 'A' && getComputedStyle(el).display === 'inline' && !!el.closest('p,li,span,div') && el.parentElement && el.parentElement.innerText.trim().length > el.innerText.trim().length + 10;
      out.tap.push({ el: label(el), text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 30), w: +r.width.toFixed(0), h: +r.height.toFixed(0), inlineInProse: inline });
    }
  }
  // top bar
  const hd = document.querySelector('header');
  if (hd) { const r = hd.getBoundingClientRect(); out.topbar = { x: r.x, y: r.y, w: r.width, h: r.height, position: getComputedStyle(hd).position }; }
  return out;
};

async function checkPage(browser, pathName, width, wantShot) {
  const ctx = await browser.newContext({ viewport: { width, height: width <= 390 ? 844 : 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const consoleErrors = [], failed = [], http = [], aborted = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });
  page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + e.message.slice(0, 200)));
  page.on('requestfailed', (r) => {
    const t = r.failure() && r.failure().errorText;
    (t === 'net::ERR_ABORTED' ? aborted : failed).push((t || '') + ' ' + r.url());
  });
  page.on('response', (r) => { if (r.status() >= 400) http.push(r.status() + ' ' + r.url()); });
  const res = { page: pathName, width };
  try {
    await page.goto(origin + pathName, { waitUntil: 'networkidle', timeout: 45000 });
    await page.waitForTimeout(400);
    const m = await page.evaluate(measure);
    Object.assign(res, m);
    const ax = await new AxeBuilder({ page }).analyze();
    const pick = (imp) => ax.violations.filter((v) => v.impact === imp).map((v) => ({ id: v.id, nodes: v.nodes.length, help: v.help, sample: v.nodes[0] && v.nodes[0].target.join(' ') }));
    res.axeSerious = [...pick('serious'), ...pick('critical')];
    res.axeModerate = pick('moderate');
    if (wantShot && shotsDir) {
      await page.screenshot({ path: path.join(shotsDir, `${pathName.replace(/\W+/g, '_')}-${width}.png`), fullPage: true });
    }
  } catch (e) { res.error = e.message.slice(0, 200); }
  res.consoleErrors = consoleErrors; res.failedRequests = failed; res.httpErrors = http; res.abortedPrefetch = aborted.length;
  await ctx.close();
  return res;
}

function pickSample(pages, n) {
  const fixed = pages.filter((p) => !p.startsWith('/compare/'));
  const cmp = pages.filter((p) => p.startsWith('/compare/'));
  if (!n || n >= cmp.length) return pages;
  const step = cmp.length / n;
  return [...fixed, ...Array.from({ length: n }, (_, i) => cmp[Math.floor(i * step)])];
}

async function pool(items, fn, n) {
  const results = [];
  let i = 0;
  await Promise.all(Array.from({ length: n }, async () => {
    while (i < items.length) { const k = i++; results[k] = await fn(items[k]); }
  }));
  return results;
}

const browser = await chromium.launch();
const crawlRes = await crawl(browser);
const pages = pickSample(crawlRes.pages, sample);
const jobs = pages.flatMap((p) => VIEWPORTS.map((w) => ({ p, w })));
const results = await pool(jobs, (j) => checkPage(browser, j.p, j.w, !j.p.startsWith('/compare/')), conc);
await browser.close();

// ---------- summary ----------
const perViewport = {};
for (const w of VIEWPORTS) {
  const rs = results.filter((r) => r.width === w);
  const tops = rs.filter((r) => r.topbar).map((r) => `${Math.round(r.topbar.w)}x${Math.round(r.topbar.h)}@${Math.round(r.topbar.y)}`);
  perViewport[w] = {
    pagesChecked: rs.length,
    hscrollPages: rs.filter((r) => r.hscroll && r.hscroll.over).length,
    innerScrollContainers: rs.reduce((s, r) => s + (r.innerScroll || []).length, 0),
    clippedElements: rs.reduce((s, r) => s + (r.clipped || []).length, 0),
    overlapPairs: rs.reduce((s, r) => s + (r.overlaps || []).length, 0),
    tapTargetsUnder44: w === 390 ? rs.reduce((s, r) => s + (r.tap || []).filter((t) => !t.inlineInProse).length, 0) : null,
    tapTargetsUnder44InlineProse: w === 390 ? rs.reduce((s, r) => s + (r.tap || []).filter((t) => t.inlineInProse).length, 0) : null,
    axeSeriousCritical: rs.reduce((s, r) => s + (r.axeSerious || []).reduce((a, v) => a + v.nodes, 0), 0),
    axeModerate: rs.reduce((s, r) => s + (r.axeModerate || []).reduce((a, v) => a + v.nodes, 0), 0),
    consoleErrors: rs.reduce((s, r) => s + (r.consoleErrors || []).length, 0),
    failedRequests: rs.reduce((s, r) => s + (r.failedRequests || []).length + (r.httpErrors || []).length, 0),
    abortedPrefetch: rs.reduce((s, r) => s + (r.abortedPrefetch || 0), 0),
    loadErrors: rs.filter((r) => r.error).length,
    topBarDistinctBoxes: [...new Set(tops)],
  };
}
const summary = {
  base, when: new Date().toISOString(), pagesCrawled: crawlRes.pages.length, linksResolved: crawlRes.links.length,
  layoutChecksRunOn: pages.length === crawlRes.pages.length ? 'all crawled pages' : `${pages.length} pages (sample)`,
  brokenLinks: crawlRes.bad, perViewport,
  topBar: Object.fromEntries(VIEWPORTS.map((w) => [w, [...new Set(results.filter((r) => r.width === w && r.topbar).map((r) => JSON.stringify({ w: Math.round(r.topbar.w), h: Math.round(r.topbar.h), y: Math.round(r.topbar.y), pos: r.topbar.position })))].map((s) => JSON.parse(s))])),
};
const json = JSON.stringify({ summary, pages: crawlRes.pages, links: crawlRes.links, results }, null, 1);
if (outFile) fs.writeFileSync(outFile, json);
console.log(JSON.stringify(summary, null, 1));
