import { test } from '@playwright/test';
import fs from 'fs';
import path from 'path';

/* ─── SETTINGS ───────────────────────────────────────────── */
const debugMode = false; // true = log actions only, false = download files
const pauseMs   = 1200;  // short pause between clicks

/* ─── FOLDERS ────────────────────────────────────────────── */
const preDir  = path.resolve('downloads', 'bucharest', 'Pre');
const postDir = path.resolve('downloads', 'bucharest', 'Post');
fs.mkdirSync(preDir,  { recursive: true });
fs.mkdirSync(postDir, { recursive: true });

/* ─── HELPER: dismiss popups like cookie banners ─────────── */
async function dismissPopups(page) {
  for (const label of ['Accept', 'OK', 'Close', 'Got it', 'Agree']) {
    const btn = page.getByRole('button', { name: new RegExp(`^${label}$`, 'i') });
    if (await btn.isVisible().catch(() => false)) {
      console.log(`⚡ Dismissing popup "${label}"`);
      await btn.click();
      await page.waitForTimeout(400);
    }
  }
}

/* ─── TEST ───────────────────────────────────────────────── */
test('BVB – Pre and Post trade (English)', async ({ page }) => {
  /* 1️⃣ Open main page and switch to English */
  await page.goto('https://www.bvb.ro/TradingAndStatistics/Trading/MiFIDIIData');
  await dismissPopups(page);

  const enButton = page.getByText('EN', { exact: true });
  if (await enButton.isVisible()) {
    await enButton.click();
    console.log('🌐 Switched to English');
    await page.waitForTimeout(pauseMs);
  }

  /* 2️⃣ Pre-Trade: Quick download */
  const preLink = page.getByRole('link', { name: /^Quick download$/i });
  if (!(await preLink.isVisible())) throw new Error('Pre-Trade download link not found');

  if (!debugMode) {
    const preDl = await Promise.all([page.waitForEvent('download'), preLink.click()]).then(([d]) => d);
    const prePath = path.join(preDir, preDl.suggestedFilename());
    if (!fs.existsSync(prePath)) {
      await preDl.saveAs(prePath);
      console.log('⬇️ Saved Pre-Trade file:', prePath);
    } else {
      console.log('⚠️ Pre-Trade file already exists, skipped:', prePath);
    }
  } else {
    console.log('(DEBUG) Would download Pre-Trade file');
  }

  await page.waitForTimeout(pauseMs);

  /* 3️⃣ Navigate to Post-Trade page */
  const postPageLink = page.getByRole('link', { name: /Post - Trade/i });
  if (!(await postPageLink.isVisible())) throw new Error('Post-Trade page link not found');
  await postPageLink.click();
  console.log('🔀 Moved to Post-Trade section');
  await dismissPopups(page);

  /* 4️⃣ Post-Trade: Current file */
  const currentLink = page.getByRole('link', { name: /Quick download - Current/i });
  if (!(await currentLink.isVisible())) throw new Error('Post-Trade Current link not found');

  if (!debugMode) {
    const curDl = await Promise.all([page.waitForEvent('download'), currentLink.click()]).then(([d]) => d);
    const curPath = path.join(postDir, curDl.suggestedFilename());
    if (!fs.existsSync(curPath)) {
      await curDl.saveAs(curPath);
      console.log('⬇️ Saved Post-Trade Current file:', curPath);
    } else {
      console.log('⚠️ Post-Trade Current file already exists, skipped:', curPath);
    }
  } else {
    console.log('(DEBUG) Would download Post-Trade Current file');
  }

  await page.waitForTimeout(pauseMs);

  /* 5️⃣ Post-Trade: Previous file */
  const prevLink = page.getByRole('link', { name: /Quick download - Previous/i });
  if (!(await prevLink.isVisible())) throw new Error('Post-Trade Previous link not found');

  if (!debugMode) {
    const prevDl = await Promise.all([page.waitForEvent('download'), prevLink.click()]).then(([d]) => d);
    const prevPath = path.join(postDir, prevDl.suggestedFilename());
    if (!fs.existsSync(prevPath)) {
      await prevDl.saveAs(prevPath);
      console.log('⬇️ Saved Post-Trade Previous file:', prevPath);
    } else {
      console.log('⚠️ Post-Trade Previous file already exists, skipped:', prevPath);
    }
  } else {
    console.log('(DEBUG) Would download Post-Trade Previous file');
  }

  console.log('✅ All Bucharest files handled.');
});
