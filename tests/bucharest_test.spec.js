import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('https://www.bvb.ro/TradingAndStatistics/Trading/MiFIDIIData');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Descarcare rapida' }).click();
  const download = await downloadPromise;
  await page.getByRole('link', { name: 'Post – Tranzactionare' }).click();
  const download1Promise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Descarcare rapida - Tranzactiile sedintei curente' }).click();
  const download1 = await download1Promise;
  const download2Promise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Descarcare rapida - Tranzactiile sedintei precedente' }).click();
  const download2 = await download2Promise;
});