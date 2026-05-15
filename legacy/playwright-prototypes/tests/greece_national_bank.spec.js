import { test } from '@playwright/test';
import fs from 'fs';
import path from 'path';

/* ── SETTINGS ───────────────────────────────────────────── */
const debugMode = false;   // true = just log, false = real downloads
const waitMs = 1500;       // 1.5-second pause between the two clicks

/* ── FOLDERS ────────────────────────────────────────────── */
const preDir  = path.resolve('downloads', 'bank-of-greece', 'Pre-Trade');
const postDir = path.resolve('downloads', 'bank-of-greece', 'Post-Trade');
fs.mkdirSync(preDir,  { recursive: true });
fs.mkdirSync(postDir, { recursive: true });

/* ── HELPERS ────────────────────────────────────────────── */
// Try to click common popup buttons if present
async function dismissPopups(page) {
  const possibleButtons = [
    'Accept',
    'Accept All',
    'Agree',
    'OK',
    'Continue',
    'Reject All',
    'Got it',
    'Close',
  ];

  for (const label of possibleButtons) {
    const button = page.getByRole('button', { name: new RegExp(`^${label}$`, 'i') });
    if (await button.isVisible().catch(() => false)) {
      console.log(`⚡ Popup detected: clicking "${label}"`);
      await button.click();
      // small pause to let page update
      await page.waitForTimeout(500);
    }
  }
}

/* ── TEST ──────────────────────────────────────────────── */
test('Bank of Greece – simple pre & post trade download', async ({ page }) => {

  /* 1️⃣  PRE-TRADE PAGE */
  await page.goto(
    'https://www.bankofgreece.gr/en/main-tasks/markets/hdat/pre-trade-data#:~:text=HDAT%20makes%20pre,600%2F2014%20%28MIFIR'
  );

  await dismissPopups(page); // ✅ clear popups if they exist

  // click PreTradeHDAT.json link
  const preLink = page.getByRole('link', { name: 'PreTradeHDAT.json i' });
  if (!(await preLink.isVisible())) throw new Error('PreTrade link not found');

  if (!debugMode) {
    const download = await Promise.all([
      page.waitForEvent('download'),
      preLink.click()
    ]).then(([d]) => d);

    const dest = path.join(preDir, download.suggestedFilename());
    if (!fs.existsSync(dest)) {
      await download.saveAs(dest);
      console.log('⬇️  saved', dest);
    } else {
      console.log('⚠️  already exists, skipped', dest);
    }
  } else {
    console.log('(DEBUG) would click PreTrade link');
  }

  /* small human-like pause */
  await page.waitForTimeout(waitMs);

  /* 2️⃣  NAVIGATE TO POST-TRADE PAGE */
  await page.getByRole('link', { name: 'Electronic Secondary' }).click();
  await page.getByRole('link', { name: 'Post-trade data' }).click();

  await dismissPopups(page); // ✅ clear popups on second page if any

  /* 3️⃣  POST-TRADE DOWNLOAD */
  const postLink = page.getByRole('link', { name: 'PostTradeHDAT.json i' });
  if (!(await postLink.isVisible())) throw new Error('PostTrade link not found');

  if (!debugMode) {
    const download = await Promise.all([
      page.waitForEvent('download'),
      postLink.click()
    ]).then(([d]) => d);

    const dest = path.join(postDir, download.suggestedFilename());
    if (!fs.existsSync(dest)) {
      await download.saveAs(dest);
      console.log('⬇️  saved', dest);
    } else {
      console.log('⚠️  already exists, skipped', dest);
    }
  } else {
    console.log('(DEBUG) would click PostTrade link');
  }

  console.log('✅ done');
});
