// Playwright test for downloading Börse Berlin pre-trade data
// This script automates the process of downloading pre-trade data files from Börse Berlin's
// MiFID II information page. It handles potential cookie banners and dynamically finds download links.
// It is designed to be run with Playwright and can be set to debug mode to avoid
// actual downloads for testing purposes.
import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

// ✅ Debug mode: Set to true to simulate downloads (no real downloads)
const debugMode = true;

// ✅ Helper function to wait a random time between min and max milliseconds
const randomDelay = async (minSeconds, maxSeconds) => {
  const delayMs = Math.floor(Math.random() * (maxSeconds - minSeconds) * 1000) + minSeconds * 1000;
  console.log(`⏳ Waiting ${delayMs / 1000} seconds before next download...`);
  return new Promise(resolve => setTimeout(resolve, delayMs));
};

test('Download all Börse Berlin pre-trade data', async ({ page }) => {
  console.log(`🚀 Starting script (debugMode = ${debugMode})`);

  // ------------------------------------------------------------
  // STEP 1: Open the Börse Berlin pre-trade data page
  // ------------------------------------------------------------
  await page.goto('https://www.boerse-berlin.com/index.php/MiFid_2_Information/Pretrades');

  // ------------------------------------------------------------
  // STEP 2: Handle possible cookie banners or modals (futureproof)
  // ------------------------------------------------------------
  console.log('🔍 Checking for cookie banners or modals...');
  try {
    const acceptButton = await page.locator('button, text=Accept, text=OK, text=Weiter, text=Agree').first();

    if (await acceptButton.isVisible()) {
      console.log('🍪 Found a consent/OK button. Clicking it...');
      await acceptButton.click();
    } else {
      console.log('✅ No consent popup detected. Continuing...');
    }
  } catch (error) {
    console.log('⚠️ Could not detect any consent button. Continuing anyway.');
  }

  // ------------------------------------------------------------
  // STEP 3: Find all links for pre-trade downloads
  // ------------------------------------------------------------
  const preTradeLinks = await page.locator('a').filter({
    hasText: /^Download der Pretrade Daten für /i
  }).all();

  console.log(`📥 Found ${preTradeLinks.length} pre-trade download links.`);

  // ------------------------------------------------------------
  // STEP 4: Loop through each link and handle downloads
  // ------------------------------------------------------------
  for (let i = 0; i < preTradeLinks.length; i++) {
    const link = preTradeLinks[i];
    const linkText = (await link.textContent())?.trim();
    console.log(`➡️  [${i + 1}/${preTradeLinks.length}] Found link: ${linkText}`);

    if (!debugMode) {
      // Wait for the download to start after clicking the link
      const download = await Promise.all([
        page.waitForEvent('download'),
        link.click()
      ]).then(([d]) => d);

      const suggestedFileName = download.suggestedFilename();

      // Define the download folder path
      const downloadsDir = path.resolve('downloads', 'boerse-berlin-pretrade');
      fs.mkdirSync(downloadsDir, { recursive: true });

      const filePath = path.join(downloadsDir, suggestedFileName);

      // ✅ Skip download if file already exists
      if (fs.existsSync(filePath)) {
        console.log(`⚠️ File already exists, skipping: ${suggestedFileName}`);
      } else {
        console.log(`⬇️  Downloading: ${suggestedFileName}`);
        await download.saveAs(filePath);
      }

      // ✅ Wait a random time (2–10 seconds) before the next download
      await randomDelay(2, 10);
    } else {
      // ✅ In debug mode, skip real download but simulate wait
      console.log(`(DEBUG MODE) Would download: ${linkText}`);
      await randomDelay(2, 10); // Simulate wait even in debug mode
    }
  }

  console.log('✅ All pre-trade files processed.');
});
