import { test } from '@playwright/test';
import fs from 'fs';
import path from 'path';

/* ─────────── CONFIG ─────────── */
const debugMode = false;      // true = just log, false = real downloads
const delayMin = 0.02;           // seconds
const delayMax = 0.10;          // seconds
const home  = 'https://www.athexgroup.gr/en/market-data/data-services/delayed-feed';

const sections = [
  { name: 'AAPA-Post-Trade',
    viewBtn: '#block-athex-tradeprepost-apapost-tableblock button:has-text("View All")' },

  { name: 'ATHEX-Pre-Trade',
    viewBtn: '#block-athex-tradeprepost-athexpre-tableblock button:has-text("View All")' },

  { name: 'ATHEX-Post-Trade',
    viewBtn: '#block-athex-tradeprepost-athexpost-tableblock button:has-text("View All")' }
];

/* ─────────── HELPERS ─────────── */
const waitRandom = async () => {
  const ms = 1000 * (Math.random() * (delayMax - delayMin) + delayMin);
  console.log(`⏳  wait ${(ms/1000).toFixed(1)} s`);
  return new Promise(r => setTimeout(r, ms));
};
test.use({
  headless: false,
  viewport: { width: 1400, height: 900 },
  userAgent:
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
    '(KHTML, like Gecko) Chrome/125.0 Safari/537.36',
});
/* ─────────── TEST ─────────── */
test('ATHEX – grab every CSV in every section', async ({ page }) => {
  console.log(`🚀 start  (debugMode = ${debugMode})`);
  await page.goto(home);

  /* Handle cookie banner once */
  const reject = page.getByRole('button', { name: /Reject All/i });
  if (await reject.isVisible()) {
    await reject.click();
    console.log('🍪 cookie banner rejected');
  }

  /* Loop through AAPA-Post, ATHEX-Pre, ATHEX-Post */
  for (const { name, viewBtn } of sections) {
    console.log(`\n📂 SECTION ▶ ${name}`);

    /* open modal */
    await page.locator(viewBtn).click();

    /* wait for at least one CSV link in the modal */
    await page.waitForSelector('#athexGlobalModal a[href$=".csv"]', { timeout: 15_000 });

    /* collect every CSV anchor inside the modal */
    const anchors = await page
      .locator('#athexGlobalModal a[href$=".csv"]')
      .all();

    /* deduplicate by filename (3 anchors per row → click only one) */
    const files = new Map();          // filename → element
    for (const a of anchors) {
      const href = await a.getAttribute('href');
      const file = href?.split('/').pop();   // e.g. Daily_PostTrade_20250723_18.00.08.csv
      if (file) files.set(file, a);
    }
    console.log(`🔗  ${files.size} file(s) detected`);

    /* ensure target folder exists */
    const dir = path.resolve('downloads', 'athex', name);
    fs.mkdirSync(dir, { recursive: true });

    /* download one by one */
    let idx = 0;
    for (const [file, anchor] of files) {
      idx += 1;
      console.log(`➡️  ${idx}/${files.size}  ${file}`);

      const dest = path.join(dir, file);

      if (fs.existsSync(dest)) {
        console.log('   ↪ already exists, skipping');
      } else if (!debugMode) {
        const download = await Promise.all([
          page.waitForEvent('download'),
          anchor.click()
        ]).then(([d]) => d);
        await download.saveAs(dest);
        console.log('   ↪ saved');
      } else {
        console.log('   ↪ (debug) would download');
      }

      await waitRandom();
    }

    /* close modal, back to main page */
    await page.getByRole('button', { name: 'Close' }).click();
    await page.waitForSelector(viewBtn, { state: 'visible' });
    console.log(`✅ done with ${name}`);
  }

  console.log('\n🏁 finished all sections');
});
