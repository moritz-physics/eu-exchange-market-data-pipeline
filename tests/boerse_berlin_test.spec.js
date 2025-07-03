import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('https://www.boerse-berlin.com/index.php/MiFid_2_Information/Post_Trade#:~:text=The%20timestamps%20are%20displayed%20in,csv%20format');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download der Daten für BERA' }).click();
  const download = await downloadPromise;
  const download1Promise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download der Daten für BERB' }).click();
  const download1 = await download1Promise;
  const download2Promise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download der Daten für BERC' }).click();
  const download2 = await download2Promise;
});