#!/usr/bin/env node
/**
 * ui-audit.mjs — optional visual audit for cp-ui (`--audit`).
 *
 * Adapted from design-audit.mjs of UI UX Pro Max (UUPM), MIT License,
 * (c) NextLevelBuilder — https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
 * Changes: removed the `--file` mode (--url is required), and the output is the cp-ui
 * report schema (report.json) instead of UUPM's markdown + JSON.
 *
 * Opens YOUR running app in Chromium (Playwright), screenshots it at 6 viewports and runs
 * heuristic checks: horizontal overflow, unsized media, img alt, tap targets, focus
 * visibility, accessible names, headings, viewport/lang meta, approximate contrast.
 * cp-ui never starts your app: start it yourself before `--audit`.
 *
 * Install (in your product):
 *   cp <cp-ui>/templates/ui-audit.mjs scripts/ui-audit.mjs
 *   npm i -D playwright && npx playwright install chromium
 *
 * .context/ui/profile.json:
 *   { "visual_audit": {
 *       "command": "node scripts/ui-audit.mjs --url http://localhost:5173 --out .ui-audit",
 *       "report": ".ui-audit/report.json",
 *       "timeout_s": 120 } }
 *
 * Usage: node scripts/ui-audit.mjs --url <http...> [--out .ui-audit] [--executable PATH]
 * Output: <out>/report.json = {"viewports": [...], "findings": [{check, severity,
 *   viewport, selector, detail, screenshot}]} and <out>/screenshots/<viewport>.png.
 * Exit code: 0 even with findings; non-zero only if this script itself crashes.
 * Contrast is approximate; treat findings as leads for the agent to verify, not verdicts.
 */
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const VIEWPORTS = [
  { name: 'mobile-360', width: 360, height: 800 },
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'laptop-1024', width: 1024, height: 768 },
  { name: 'desktop-1440', width: 1440, height: 900 },
  { name: 'wide-1920', width: 1920, height: 1080 },
];

function parseArgs(argv) {
  const args = { out: '.ui-audit' };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--url') args.url = argv[++i];
    else if (a === '--out') args.out = argv[++i];
    else if (a === '--executable') args.executable = argv[++i];
  }
  if (!args.url) {
    console.error('Provide --url <http...> (start your app first; this script never starts it)');
    process.exit(1);
  }
  return args;
}

// Runs inside the page. Returns structured findings for the current viewport.
function inPageChecks() {
  const findings = [];
  const push = (severity, check, message, detail) =>
    findings.push({ severity, check, message, detail: detail || '' });

  const vw = window.innerWidth;

  // 1. Horizontal overflow
  const docW = document.documentElement.scrollWidth;
  if (docW > vw + 1) {
    const wide = [...document.querySelectorAll('*')]
      .filter((el) => el.getBoundingClientRect().right > vw + 1)
      .slice(0, 5)
      .map((el) => el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/)[0] : ''));
    push('high', 'horizontal-overflow', `Page is ${docW}px wide at ${vw}px viewport (horizontal scroll).`, wide.join(', '));
  }

  // 2. Unsized media (CLS risk) + missing alt
  const imgs = [...document.querySelectorAll('img')];
  const unsized = imgs.filter((im) => !im.getAttribute('width') || !im.getAttribute('height'));
  if (unsized.length) push('medium', 'unsized-media', `${unsized.length}/${imgs.length} <img> lack width/height (layout-shift risk).`);
  const noAlt = imgs.filter((im) => im.getAttribute('alt') === null);
  if (noAlt.length) push('high', 'img-alt', `${noAlt.length} <img> missing alt attribute.`);

  // 3. Tap targets (mobile only)
  if (vw <= 480) {
    const small = [...document.querySelectorAll('a,button,[role=button],input,select')]
      .filter((el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && (r.width < 44 || r.height < 44); });
    if (small.length) push('medium', 'tap-target', `${small.length} interactive targets < 44×44px on mobile.`);
  }

  // 4. Focus visibility (sample of focusables)
  const focusables = [...document.querySelectorAll('a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])')].slice(0, 25);
  let noFocus = 0;
  for (const el of focusables) {
    el.focus();
    const s = getComputedStyle(el);
    const hasOutline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0;
    const hasShadow = s.boxShadow && s.boxShadow !== 'none';
    if (!hasOutline && !hasShadow) noFocus++;
    el.blur();
  }
  if (noFocus > 0) push('high', 'focus-visible', `${noFocus}/${focusables.length} sampled interactive elements show no visible focus indicator.`);

  // 5. Accessible names on controls
  const namelessBtns = [...document.querySelectorAll('button,a[href]')].filter((el) => {
    const text = (el.textContent || '').trim();
    const label = el.getAttribute('aria-label') || el.getAttribute('title');
    const hasImg = el.querySelector('img[alt]:not([alt=""]), svg[aria-label], [aria-hidden="false"]');
    return !text && !label && !hasImg;
  });
  if (namelessBtns.length) push('high', 'accessible-name', `${namelessBtns.length} buttons/links have no accessible name.`);

  // 6. Heading structure
  const h1 = document.querySelectorAll('h1');
  if (h1.length === 0) push('medium', 'headings', 'No <h1> on the page.');
  else if (h1.length > 1) push('low', 'headings', `${h1.length} <h1> elements (expected 1).`);

  // 7. Document meta
  if (!document.querySelector('meta[name=viewport]')) push('high', 'viewport-meta', 'Missing <meta name="viewport"> — mobile rendering will break.');
  if (!document.documentElement.getAttribute('lang')) push('medium', 'html-lang', 'Missing lang attribute on <html>.');

  // 8. Approximate text contrast (sampled)
  const toRgb = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map((x) => parseFloat(x)); return { r: p[0], g: p[1], b: p[2], a: p[3] ?? 1 }; };
  const lum = ({ r, g, b }) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const L1 = lum(a), L2 = lum(b); return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05); };
  const bgOf = (el) => { let n = el; while (n) { const c = toRgb(getComputedStyle(n).backgroundColor); if (c && c.a !== 0) return c; n = n.parentElement; } return { r: 255, g: 255, b: 255, a: 1 }; };
  const textEls = [...document.querySelectorAll('p,span,a,li,h1,h2,h3,h4,button,label,td')]
    .filter((el) => (el.textContent || '').trim().length > 1 && el.offsetParent !== null).slice(0, 120);
  let lowContrast = 0;
  for (const el of textEls) {
    const s = getComputedStyle(el);
    const fg = toRgb(s.color); if (!fg) continue;
    const bg = bgOf(el);
    const size = parseFloat(s.fontSize);
    const bold = parseInt(s.fontWeight, 10) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const need = large ? 3 : 4.5;
    if (ratio(fg, bg) < need - 0.05) lowContrast++;
  }
  if (lowContrast > 0) push('medium', 'contrast', `~${lowContrast}/${textEls.length} sampled text nodes below WCAG AA contrast (approximate).`);

  return findings;
}

// Scroll through the full page to trigger IntersectionObserver reveals and lazy-loaded media,
// then return to top. Without this, full-page screenshots of scroll-reveal sites capture blank
// sections (content still at opacity:0) — a common false "blank section" reading.
async function autoScroll(page) {
  await page.evaluate(async () => {
    await new Promise((res) => {
      let y = 0;
      const step = Math.max(200, Math.floor(window.innerHeight * 0.8));
      const timer = setInterval(() => {
        window.scrollBy(0, step);
        y += step;
        if (y >= document.body.scrollHeight) { clearInterval(timer); res(); }
      }, 80);
    });
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(300);
}

async function launchBrowser(executable) {
  const exe = executable || process.env.PW_EXECUTABLE_PATH;
  try {
    return await chromium.launch(exe ? { executablePath: exe } : {});
  } catch (e) {
    // Fall back to a common preinstalled path (e.g. managed CI images).
    return await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  }
}

async function main() {
  const args = parseArgs(process.argv);
  const outDir = resolve(args.out);
  await mkdir(`${outDir}/screenshots`, { recursive: true });

  const browser = await launchBrowser(args.executable);
  const out = [];

  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const consoleErrors = [];
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
    page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${e.message}`));
    await page.goto(args.url, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => page.goto(args.url, { waitUntil: 'load', timeout: 30000 }));
    await page.waitForTimeout(400);
    await autoScroll(page);
    const shot = `${args.out}/screenshots/${vp.name}.png`;
    await page.screenshot({ path: `${outDir}/screenshots/${vp.name}.png`, fullPage: true });
    const findings = await page.evaluate(inPageChecks);
    for (const f of findings) {
      out.push({
        check: f.check,
        severity: f.severity,
        viewport: vp.name,
        selector: f.detail || 'html',
        detail: f.message,
        screenshot: shot,
      });
    }
    for (const e of consoleErrors.slice(0, 5)) {
      out.push({ check: 'console-error', severity: 'medium', viewport: vp.name, selector: 'console', detail: e, screenshot: shot });
    }
    await ctx.close();
  }
  await browser.close();

  const report = { viewports: VIEWPORTS.map((v) => v.name), findings: out };
  await writeFile(`${outDir}/report.json`, JSON.stringify(report, null, 2), 'utf8');
  console.log(`ui-audit: ${out.length} finding(s) across ${VIEWPORTS.length} viewports -> ${outDir}/report.json`);
}

main().catch((e) => { console.error(e); process.exit(1); });
