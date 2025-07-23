import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

// 👉 true  = “Trockenlauf”  (keine Downloads, nur Log-Ausgabe)
// 👉 false = echte Downloads
const debugMode = true;

test('Download pre-trade and post-trade data', async ({ page }) => {
  console.log(`🚀 Start (debugMode = ${debugMode})`);

  /* -------------------------------------------------
     1) PRE-TRADE
  ------------------------------------------------- */
  await page.goto('https://www.gettex.de/handel/delayed-data/');

  const prePopup = await Promise.all([
    page.waitForEvent('popup'),
    page.getByRole('link', { name: /MiFID II verzögerte pre-trade/i }).click()
  ]).then(([popup]) => popup);

  const preLinks = await prePopup
    .locator('a')
    .filter({ hasText: /^pretrade\..*\.csv\.gz$/i })
    .all();

  console.log(`📦 Pre-Trade: ${preLinks.length} Dateien gefunden`);

  for (const link of preLinks) {
    const text = (await link.textContent())?.trim();
    console.log(`➡️  ${debugMode ? 'Würde laden' : 'Lade'}: ${text}`);

    if (!debugMode) {
      const download = await Promise.all([
        prePopup.waitForEvent('download'),
        link.click()
      ]).then(([d]) => d);

      const fileName = download.suggestedFilename();
      const dir = path.resolve('downloads', 'pretrade');
      fs.mkdirSync(dir, { recursive: true });
      await download.saveAs(path.join(dir, fileName));
    }
  }

  await prePopup.close();
  console.log('✅ Pre-Trade erledigt, Popup geschlossen');

  /* -------------------------------------------------
     2) POST-TRADE
  ------------------------------------------------- */
  await page.goto('https://www.gettex.de/handel/delayed-data/');

  const postPopup = await Promise.all([
    page.waitForEvent('popup'),
    page.getByRole('link', { name: /MiFID II verzögerte post-/i }).click()
  ]).then(([popup]) => popup);

  const postLinks = await postPopup
    .locator('a')
    .filter({ hasText: /^posttrade\..*\.csv\.(gz|jz)$/i })
    .all();

  console.log(`📦 Post-Trade: ${postLinks.length} Dateien gefunden`);

  for (const link of postLinks) {
    const text = (await link.textContent())?.trim();
    console.log(`➡️  ${debugMode ? 'Würde laden' : 'Lade'}: ${text}`);

    if (!debugMode) {
      const download = await Promise.all([
        postPopup.waitForEvent('download'),
        link.click()
      ]).then(([d]) => d);

      const fileName = download.suggestedFilename();
      const dir = path.resolve('downloads', 'posttrade');
      fs.mkdirSync(dir, { recursive: true });
      await download.saveAs(path.join(dir, fileName));
    }
  }

  console.log('🏁 Fertig!');
});
