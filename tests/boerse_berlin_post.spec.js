//Berlin Börse post-trade data download script futureproofed
// This script downloads all post-trade data from Börse Berlin.
// It handles potential cookie banners and dynamically finds download links.
// It is designed to be run with Playwright and can be set to debug mode to avoid
// actual downloads for testing purposes.
import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

// ✅ Debug mode: Set to true for testing (no real downloads)
//    Set to false for actual downloading
const debugMode = true;

test('Download all Börse Berlin post-trade data', async ({ page }) => {
  console.log(`🚀 Starting script (debugMode = ${debugMode})`);

  // ------------------------------------------------------------
  // STEP 1: Open the Börse Berlin post-trade data page
  // ------------------------------------------------------------
  await page.goto('https://www.boerse-berlin.com/index.php/MiFid_2_Information/Post_Trade');

  // ------------------------------------------------------------
  // STEP 2: Handle possible cookie banners or modals (futureproof)
  // ------------------------------------------------------------
  console.log('🔍 Checking for cookie banners or modals...');
  try {
    // Look for any button with common consent texts
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
  // STEP 3: Find all links for downloading
  // ------------------------------------------------------------
  // Look for links with text like "Download der Daten für BERA"
  const downloadLinks = await page.locator('a').filter({
    hasText: /^Download der Daten für /i
  }).all();

  console.log(`📥 Found ${downloadLinks.length} download links on the page.`);

  // ------------------------------------------------------------
  // STEP 4: Loop through each link and handle downloads
  // ------------------------------------------------------------
  for (const link of downloadLinks) {
    const linkText = (await link.textContent())?.trim();
    console.log(`➡️  Found link: ${linkText}`);

    if (!debugMode) {
      // Wait for the download to start after clicking the link
      const download = await Promise.all([
        page.waitForEvent('download'), // Listen for download event
        link.click()                    // Click the link to start the download
      ]).then(([d]) => d); // Capture the download object

      // Get the suggested file name from the server
      const suggestedFileName = download.suggestedFilename();

      // Define the download folder path
      const downloadsDir = path.resolve('downloads', 'boerse-berlin');
      fs.mkdirSync(downloadsDir, { recursive: true }); // Create folder if it doesn’t exist

      const filePath = path.join(downloadsDir, suggestedFileName);

      // --------------------------------------------------------
      // ✅ Check if the file already exists (skip if so)
      // --------------------------------------------------------
      if (fs.existsSync(filePath)) {
        console.log(`⚠️ File already exists, skipping: ${suggestedFileName}`);
        continue; // Skip this file and move on to the next
      }

      // If the file doesn’t exist, download and save it
      console.log(`⬇️  Downloading: ${suggestedFileName}`);
      await download.saveAs(filePath);
    } else {
      // ✅ In debugMode, skip actual download and just log the action
      console.log(`(DEBUG MODE) Would download: ${linkText}`);
    }
  }

  // ------------------------------------------------------------
  // STEP 5: Done!
  // ------------------------------------------------------------
  console.log('✅ All files processed.');
});
