import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('https://www.bse-sofia.bg/en/apa-trading-data');
  await page.getByText('Got it!').click();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'SaveCSV with separator [ ; ]' }).click();
  const download = await downloadPromise;
});