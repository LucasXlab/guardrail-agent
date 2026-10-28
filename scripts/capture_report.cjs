// Optional authoring tool: install Playwright and its Chromium browser separately.
// Captures the real generated HTML unchanged, with all network requests blocked.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const input = path.resolve('assets/synthetic-report.html');
  if (!fs.existsSync(input)) throw new Error('Run scripts/showcase.py first');
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}),
  });
  const page = await browser.newPage({ viewport: { width: 1200, height: 980 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.route('**/*', route => route.request().url().startsWith('file:') ? route.continue() : route.abort());
  await page.goto('file://' + input);
  await page.waitForLoadState('load');
  const title = await page.title();
  if (!title.includes('synthetic run') || errors.length) throw new Error('Unexpected report state');
  await page.screenshot({ path: 'assets/feature-report.png', fullPage: false });
  await browser.close();
  console.log('Captured unmodified synthetic report: 1200x980 top viewport; no external requests.');
})().catch(error => { console.error(error); process.exit(1); });
