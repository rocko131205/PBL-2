// Synthetic users for the monitoring demo: headless Chrome sessions that open FinVeritas
// through the edge proxy, sign in, and click through pages, so the dashboard shows real
// browser traffic (page loads, WebSocket sessions, logins). Runs until stopped.
//
// About 1 in 4 visits tries an unknown email instead, which records a failed login without
// tripping the per-account lockout on the synthetic user.
//
// In Docker it uses the puppeteer image's bundled Chrome. Outside Docker (npm install puppeteer-core):
//   BROWSER_URL=http://localhost:9222 node user.js       attach to a running Chrome, e.g. a
//                                                         chromedp/headless-shell container
//   BROWSER_PATH=/path/to/chrome node user.js            launch a locally installed Chrome
let puppeteer;
try { puppeteer = require('puppeteer'); } catch { puppeteer = require('puppeteer-core'); }

const BASE = process.env.TARGET_URL || 'http://edge:8080/';
const EMAIL = process.env.SYNTHETIC_EMAIL;
const PASSWORD = process.env.SYNTHETIC_PASSWORD;
const USERS = Number(process.env.SYNTHETIC_USERS || 2);
const PAGES = ['Financial Analysis', 'My File History', 'Security Settings', 'Upload Statement', 'Basel III Alignment'];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// textContent, not innerText: the app's CSS uppercases some labels (e.g. "NAVIGATION").
const pageText = (page, text, timeout = 30000) =>
  page.waitForFunction((t) => document.body.textContent.includes(t), { timeout }, text);

async function fill(page, label, value) {
  const input = await page.waitForSelector(`input[aria-label="${label}"]`, { timeout: 30000 });
  await input.click({ clickCount: 3 });
  await input.type(value);
}

async function visit(browser) {
  const context = await browser.createBrowserContext();   // fresh cookies = a new user session
  const page = await context.newPage();
  try {
    await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30000 });
    const stranger = Math.random() < 0.25;
    await fill(page, 'Email', stranger ? `nobody-${Date.now()}@example.invalid` : EMAIL);
    await fill(page, 'Password', stranger ? 'Wrong!Passw0rd' : PASSWORD);
    await (await page.waitForSelector('::-p-xpath(//button[contains(., "Login")])')).click();
    if (stranger) {
      await pageText(page, 'Invalid email or password');
      return 'failed login';
    }
    await pageText(page, 'Navigation');
    for (const name of [...PAGES].sort(() => Math.random() - 0.5).slice(0, 3)) {
      const option = await page.waitForSelector(
        `::-p-xpath(//section[@data-testid="stSidebar"]//label[contains(., "${name}")])`, { timeout: 15000 });
      await option.click();
      await sleep(1500 + Math.random() * 1500);
    }
    return 'signed in, visited 3 pages';
  } finally {
    await context.close();
  }
}

(async () => {
  if (!EMAIL || !PASSWORD) throw new Error('SYNTHETIC_EMAIL and SYNTHETIC_PASSWORD are required');
  const browser = process.env.BROWSER_URL
    ? await puppeteer.connect({ browserURL: process.env.BROWSER_URL })
    : await puppeteer.launch({ args: ['--no-sandbox'], executablePath: process.env.BROWSER_PATH || undefined });
  await Promise.all([...Array(USERS).keys()].map(async (n) => {
    for (;;) {
      const started = Date.now();
      try {
        console.log(`user${n}: ${await visit(browser)} (${Date.now() - started} ms)`);
      } catch (err) {
        console.log(`user${n}: error after ${Date.now() - started} ms: ${String(err.message).split('\n')[0]}`);
      }
      await sleep(2000 + Math.random() * 3000);
    }
  }));
})();
