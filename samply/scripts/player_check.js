#!/usr/bin/env node
// Check a Samply Player link as a logged-out listener: does it play gapless, and in what order?
//
//   node player_check.js https://samply.app/p/<share>
//
// Opens the link in a fresh headless Chromium (no login), presses Play, and prints the audio queue state.
// A good album-flow player reports gaplessAvailable: true (and usually gaplessLossless: true).
// Needs Node 18+ and Playwright (`npm i playwright && npx playwright install chromium`).
const { chromium } = require('playwright');

(async () => {
  const url = process.argv[2];
  if (!url) {
    console.error('usage: player_check.js <player link>');
    process.exit(2);
  }
  const b = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
  const page = await (await b.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(15000);
  await page.evaluate(() => {
    const bt = [...document.querySelectorAll('button')].find((x) => (x.innerText || '').trim() === 'Play');
    if (bt) bt.click();
  });
  await page.waitForTimeout(12000);
  const out = await page.evaluate(() => {
    const pin = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia;
    const q = pin._s.get('audio-queue-module');
    const am = pin._s.get('audio-module');
    return {
      gaplessAvailable: q.gaplessAvailable,
      gaplessLossless: q.gaplessLosslessAvailable,
      gapless: am.gapless,
      queue: (q.queue || []).map((x) => x.name || x.id),
    };
  });
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})().catch((e) => {
  console.error('ERR ' + e.message);
  process.exit(1);
});
