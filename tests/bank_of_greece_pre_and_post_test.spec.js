import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('https://www.bankofgreece.gr/en/main-tasks/markets/hdat/pre-trade-data#:~:text=HDAT%20makes%20pre,600%2F2014%20%28MIFIR');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'PreTradeHDAT.json i' }).click();
  const download = await downloadPromise;
  await page.getByRole('link', { name: 'Electronic Secondary' }).click();
  await page.getByRole('link', { name: 'Post-trade data' }).click();
  const download1Promise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'PostTradeHDAT.json i' }).click();
  const download1 = await download1Promise;
});