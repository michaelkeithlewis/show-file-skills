#!/usr/bin/env node
// Make a Samply "Player": a share link that plays the given song stacks back to back, gapless, in this order.
// Use it for album flow, when one song cuts straight into the next but the songs stay separate tracks.
//
//   node player.js <projectId> "<player name>" <stackId> [<stackId> ...]   -> prints JSON with the share link
//
// The public API has no Player endpoint, so this drives the Samply web app in a Chrome that is already logged in.
// Start Chrome with remote debugging, log in to samply.app in it, then run this:
//   google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.samply-chrome"
//   SAMPLY_CDP=http://127.0.0.1:9222 node player.js ...
// Needs Node 18+ and Playwright (`npm i playwright`).
//
// Gotchas: a new player is created INACTIVE ("Access Denied") until it is activated, and its default sort is by
// creation time, so the script sets a custom sort plus an order map. A Player shows each stack's first upload name
// but plays the newest version. These calls use the web app's internal store and can break when Samply ships.
const { chromium } = require('playwright');

const CDP = process.env.SAMPLY_CDP || 'http://127.0.0.1:9222';
const [P, NAME, ...STACKS] = process.argv.slice(2);
if (!P || !NAME || !STACKS.length) {
  console.error('usage: player.js <projectId> "<name>" <stackId>...');
  process.exit(2);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const page = await ctx.newPage();
  await page.goto('https://samply.app/project/' + P, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.waitForTimeout(14000);
  const made = await page.evaluate(async ({ NAME, STACKS }) => {
    const st = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('');
    const r = await st.createNonCanonicalPlayer({ boxids: STACKS, name: NAME, forceCreate: true });
    const share = await st.mintShareId(r.playerid);
    await new Promise((res) => setTimeout(res, 3000));
    const d = (st.playerDocs || []).find((x) => x.id === r.playerid);
    if (d) st.activatePlayers([d]);
    return { playerid: r.playerid, share };
  }, { NAME, STACKS });
  await sleep(4000);
  await page.goto('https://samply.app/p/' + made.share, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.waitForTimeout(14000);
  const ord = await page.evaluate(async (STACKS) => {
    const st = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('player');
    const order = {};
    STACKS.forEach((id, i) => (order[id] = i));
    await st.updateSort('custom', true);
    await st.updateOrder(order);
    await new Promise((res) => setTimeout(res, 3000));
    return { sortBy: st.sortBy, sortOrder: st.sortOrder };
  }, STACKS);
  console.log(JSON.stringify({ ...made, ...ord, link: 'https://samply.app/p/' + made.share }));
  await page.close();
  await browser.close(); // detaches; the Chrome you started keeps running
})().catch((e) => {
  console.error('ERR ' + e.message);
  process.exit(1);
});
