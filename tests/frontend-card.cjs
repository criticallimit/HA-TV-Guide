const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({headless:true, ...(process.env.TVG_BROWSER_PATH ? {executablePath:process.env.TVG_BROWSER_PATH} : {})});
  const page = await browser.newPage({viewport:{width:1000,height:900}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setContent('<style>body{font-family:Arial;background:#eef2f5;margin:24px;--primary-text-color:#192b38;--secondary-text-color:#526571;--primary-color:#087f8c;--divider-color:#ccd6dd;--card-background-color:white}ha-card{display:block;background:white;border-radius:12px}</style>');
  await page.addScriptTag({path:path.resolve('custom_components/tv_guide/frontend/tv-guide-native-card.js')});
  await page.evaluate(() => {
    window.calls = [];
    window.fail = '';
    window.saved = {bookmarks:[],reminders:[]};
    window.channels = [{id:'ard', name:'Das Erste', xmltv_id:'DasErste.de', selected:true, available:true}, {id:'zdf', name:'ZDF', xmltv_id:null, selected:true, available:false}];
    const start = new Date(Date.now() + 3600000).toISOString();
    window.programme = {id:'native_test', channel:'DasErste.de', channel_name:'Das Erste', start, stop:new Date(Date.now()+7200000).toISOString(), title:'Film <img src=x onerror="window.injected=true">', description:'A & B <script>alert(1)</script>'};
    window.hass = {
      language:'de', config:{time_zone:'Europe/Berlin'}, connection:{},
      async callWS(message) {
        calls.push(message);
        if (fail === message.service) throw new Error('Simulated service failure');
        const response = message.service === 'get_saved_programmes' ? saved : message.service === 'get_channels' ? {channels} : {programmes:[programme],count:1,truncated:false};
        return {context:{},response:structuredClone(response)};
      },
      async callService(domain,service,data) {
        calls.push({domain,service,service_data:data});
        if (fail === service) throw new Error('Simulated write failure');
        if (service === 'save_bookmark' || service === 'save_reminder') {
          const key = service === 'save_bookmark' ? 'bookmarks' : 'reminders';
          saved[key].push({...data,channelId:data.channel_id});
        } else if (service === 'remove_saved_programme') {
          const key = data.kind === 'bookmark' ? 'bookmarks' : 'reminders';
          saved[key] = saved[key].filter(item => item.id !== data.id);
        } else if (service === 'set_channels') {
          channels.forEach(item => item.selected = !data.channels.length || data.channels.includes(item.id));
        }
      },
    };
    const card = document.createElement('tv-guide-native-card');
    card.setConfig({type:'custom:tv-guide-native-card'});
    card.hass = hass;
    document.body.append(card);
  });
  const ready = () => page.waitForFunction(() => !document.querySelector('tv-guide-native-card')._busy);
  const card = page.locator('tv-guide-native-card');
  await ready();
  assert.equal(await card.locator('article strong').textContent(), 'Film <img src=x onerror="window.injected=true">');
  assert.equal(await card.locator('img,script').count(), 0);
  await card.locator('[data-bookmark="0"]').click();
  await ready();
  await card.locator('[data-remind="0"]').click();
  await ready();
  assert.equal(await page.evaluate(() => saved.bookmarks[0].id), 'native_test');
  assert.equal(await page.evaluate(() => saved.reminders[0].minutes), 10);
  assert.equal(await page.evaluate(() => saved.reminders[0].channel_id), 'DasErste.de');
  await card.locator('[data-tab="bookmarks"]').click();
  await card.locator('[data-remove="0"]').click();
  await ready();
  assert.equal(await page.evaluate(() => saved.bookmarks.length), 0);
  console.log('PASS programme/bookmark/reminder/removal and escaped feed content');

  await card.locator('[data-tab="channels"]').click();
  await card.locator('[data-move="zdf"][data-direction="-1"]').click();
  await card.locator('#save-channels').click();
  await ready();
  assert.deepEqual(await page.evaluate(() => calls.findLast(call => call.service === 'set_channels').service_data.channels), ['zdf','ard']);
  await card.locator('[data-channel="ard"]').uncheck();
  await card.locator('#save-channels').click();
  await ready();
  assert.deepEqual(await page.evaluate(() => calls.findLast(call => call.service === 'set_channels').service_data.channels), ['zdf']);
  await card.locator('#all-channels').click();
  await ready();
  assert.deepEqual(await page.evaluate(() => calls.findLast(call => call.service === 'set_channels').service_data.channels), []);
  console.log('PASS sender selection, reordering, unavailable channels and all-channel reset');

  await page.evaluate(() => fail = 'get_channels');
  await card.locator('#refresh').click();
  await ready();
  await card.locator('[data-tab="reminders"]').click();
  assert.equal(await card.locator('article').count(), 1);
  await card.locator('[data-tab="programme"]').click();
  assert.match(await card.locator('ha-card').textContent(), /Kein EPG verfügbar/);
  console.log('PASS saved lists remain accessible without EPG');

  await page.evaluate(() => fail = 'get_saved_programmes');
  await card.locator('#refresh').click();
  await ready();
  assert.match(await card.locator('[role="alert"]').textContent(), /Simulated service failure/);
  await page.evaluate(() => fail = '');
  await card.locator('#refresh').click();
  await ready();
  await page.evaluate(() => fail = 'save_bookmark');
  await card.locator('[data-bookmark="0"]').click();
  await ready();
  assert.match(await card.locator('[role="alert"]').textContent(), /Simulated write failure/);
  assert.equal(await page.evaluate(() => saved.bookmarks.length), 0);
  console.log('PASS read and write errors stay visible and controls recover');

  await page.evaluate(() => {fail='';hass.language='en';document.querySelector('tv-guide-native-card').hass={...hass};});
  await card.locator('#refresh').click();
  await ready();
  assert.match(await card.locator('ha-card').textContent(), /Schedule/);
  await page.evaluate(() => {const card=document.querySelector('tv-guide-native-card');card.remove();document.body.append(card);});
  await ready();
  assert.equal(await page.evaluate(() => calls.filter(call => call.type === 'call_service').every(call => call.return_response && call.domain === 'tv_guide')), true);
  assert.deepEqual(errors, []);
  if (process.env.TVG_SCREENSHOT) await page.screenshot({path:process.env.TVG_SCREENSHOT,fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await card.evaluate(el => el.getBoundingClientRect().width <= 390), true);
  console.log('PASS language, reconnect, native WebSocket response contract and mobile layout');
  await browser.close();
})().catch(error => {console.error(error);process.exit(1);});

