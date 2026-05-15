//boerse_lange_schwarz.spec.js
//SCHEINT ZU ERLAUBEN, DIE DATEN AUTOMATISCH RUNTERZULADEN
// Playwright test for downloading Börse Berlin pre-trade data
// This script automates the process of downloading pre-trade and post-trade data files from
// Börse Berlin's MiFID II information page. It handles potential cookie banners and dynamically finds
// download links. It is designed to be run with Playwright and can be set to debug mode to avoid
// actual downloads for testing purposes.
//
 import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

// ✅ Debug mode: Set to true to simulate downloads (no real downloads)
//    Set to false for actual downloading
const debugMode = false;

// ✅ Helper function: Wait a random time between min and max seconds
const randomDelay = async (minSeconds, maxSeconds) => {
  const delayMs = Math.floor(Math.random() * (maxSeconds - minSeconds) * 1000) + minSeconds * 1000;
  console.log(`⏳ Waiting ${delayMs / 1000} seconds before next download...`);
  return new Promise(resolve => setTimeout(resolve, delayMs));
};

test('Download data from ls-x.de', async ({ page }) => {
  console.log(`🚀 Starting script (debugMode = ${debugMode})`);

  // ------------------------------------------------------------
  // STEP 1: Go to the page and handle cookies
  // ------------------------------------------------------------
  await page.goto('https://www.ls-x.de/de/download');

  // Check if "Akzeptieren" button is visible and click it
  try {
    const acceptButton = page.getByRole('button', { name: /Akzeptieren/i });
    if (await acceptButton.isVisible()) {
      console.log('🍪 Clicking cookie consent button...');
      await acceptButton.click();
    }
  } catch (err) {
    console.log('✅ No cookie consent button found. Continuing...');
  }

  // ------------------------------------------------------------
  // STEP 2: Download "Heute Download"
  // ------------------------------------------------------------
  console.log('➡️ Downloading "Heute Download"...');
  if (!debugMode) {
    const download = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('row', { name: /Heute Download/i }).getByRole('button').click()
    ]).then(([d]) => d);

    const suggestedFileName = download.suggestedFilename();
    const downloadsDir = path.resolve('downloads', 'ls-x');
    fs.mkdirSync(downloadsDir, { recursive: true });
    const filePath = path.join(downloadsDir, suggestedFileName);

    if (fs.existsSync(filePath)) {
      console.log(`⚠️ File already exists, skipping: ${suggestedFileName}`);
    } else {
      console.log(`⬇️ Saving: ${suggestedFileName}`);
      await download.saveAs(filePath);
    }

    // Wait randomly 2–5 seconds before next step
    await randomDelay(2, 5);
  } else {
    console.log('(DEBUG MODE) Would download "Heute Download"');
  }

  // ------------------------------------------------------------
  // STEP 3: Find and download all "Pretrade Daten ..." links
  // ------------------------------------------------------------
  console.log('🔍 Searching for "Pretrade Daten ..." links...');
  const pretradeLinks = await page.locator('a').filter({
    hasText: /^Pretrade Daten /i
  }).all();

  console.log(`📥 Found ${pretradeLinks.length} "Pretrade Daten ..." links.`);

  for (let i = 0; i < pretradeLinks.length; i++) {
    const link = pretradeLinks[i];
    const linkText = (await link.textContent())?.trim();
    console.log(`➡️  [${i + 1}/${pretradeLinks.length}] Processing: ${linkText}`);

    if (!debugMode) {
      const download = await Promise.all([
        page.waitForEvent('download'),
        link.click()
      ]).then(([d]) => d);

      const suggestedFileName = download.suggestedFilename();
      const downloadsDir = path.resolve('downloads', 'ls-x');
      fs.mkdirSync(downloadsDir, { recursive: true });
      const filePath = path.join(downloadsDir, suggestedFileName);

      if (fs.existsSync(filePath)) {
        console.log(`⚠️ File already exists, skipping: ${suggestedFileName}`);
      } else {
        console.log(`⬇️ Saving: ${suggestedFileName}`);
        await download.saveAs(filePath);
      }

      // Wait randomly 2–5 seconds before next download
      await randomDelay(0.02, 0.05);
    } else {
      console.log(`(DEBUG MODE) Would download: ${linkText}`);
      await randomDelay(0.02, 0.05); // Simulate wait in debug mode too
    }
  }

  console.log('✅ All downloads complete.');
});
