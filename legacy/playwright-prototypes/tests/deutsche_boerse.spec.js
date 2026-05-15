import { test, expect } from '@playwright/test';

test('Download all .json.gz links on popup page with delay and user-agent', async ({ browser }) => {
  // Launch context with custom user agent
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115 Safari/537.36',
    acceptDownloads: true
  });

  const page = await context.newPage();

  // Step 1: Go to the base page
  await page.goto('https://www.mds.deutsche-boerse.com/mds-en/real-time-data/MiFID-II-Disaggregated-Information-Products-delayed--1520116');
  await page.pause(); // Pause for debugging if needed

  // Step 2: Click the row that opens the popup
  const page1Promise = page.waitForEvent('popup');
  await page.getByRole('row', { name: 'Xetra – Pre-Trade File service' }).getByRole('link').click();
  const page1 = await page1Promise;

  // Step 3: Accept cookie/AGB if shown
  try {
    await page1.getByRole('button', { name: /I agree|Accept all|OK/i }).click({ timeout: 5000 });
    console.log('✓ Cookie banner accepted');
  } catch {
    console.log('⏭ No cookie banner');
  }

  // Step 4: Collect all download links ending with .json.gz
  const downloadLinks = page1.locator('a[href$=".json.gz"]');
  const count = await downloadLinks.count();
  console.log(`📄 Found ${count} .json.gz links`);

  for (let i = 0; i < count; i++) {
    const downloadPromise = page1.waitForEvent('download');
    await downloadLinks.nth(i).click({ force: true });  // Force click in case overlays exist
    const download = await downloadPromise;

    const suggestedFileName = download.suggestedFilename();
    await download.saveAs(`downloads/${suggestedFileName}`);
    console.log(`✅ Downloaded: ${suggestedFileName}`);

    // Random delay between 2 and 4 seconds
    const wait = Math.floor(Math.random() * 2000) + 200;
    console.log(`⏳ Waiting ${wait} ms before next download...`);
    await new Promise(res => setTimeout(res, wait));
  }

  await context.close();
});
