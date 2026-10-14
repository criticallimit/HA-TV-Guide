/* Behaviour and pixel parity against the pinned, unchanged add-on frontend. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {chromium} = require('playwright');
const root = path.resolve('custom_components/tv_guide/frontend');
const reference = path.resolve(process.env.TVG_REFERENCE || '../TV-Guide', 'tv-guide/www');
const fixed = '2026-10-14T18:00:00Z';
const stations = [['ard','Das Erste'],['zdf','ZDF'],['arte','arte'],['3sat','3sat'],['wdr','WDR']];
const fixture = {
  country:'de', ui:{language:'de',default_view:'now',columns_desktop:5,max_channels:0,theme_mode:'auto',refresh_minutes:180,notification_service:'persistent_notification.create'}, refresh_running:false,
  main_channel_ids:stations.map(item=>item[0]), custom_channel_ids:stations.map(item=>item[0]),
  channels:stations.map(([id,name],index) => ({id,name,source_country:'de',available:true, logo_normalized_light:`/tv_guide/frontend/app/logos/de-${id}-light.svg`,logo_normalized_dark:`/tv_guide/frontend/app/logos/de-${id}-dark.svg`,programs:Array.from({length:7},(_,i)=>({id:`native_${id}_${i}`,title:['Nachrichten','Film am Abend','Wissen und Kultur','Dokumentation','Spätprogramm','Nachtmagazin','Morgenprogramm'][i],start:new Date(Date.parse(fixed)+(i-1)*3600000).toISOString(),end:new Date(Date.parse(fixed)+i*3600000+1800000).toISOString(),desc:'Beschreibung der Sendung.',category:'Information',subtitle:''}))})),
};
const server = http.createServer((req,res) => {
  const url = new URL(req.url,'http://localhost');
  if (url.pathname === '/') {res.setHeader('Content-Type','text/html');res.end('<style>body{margin:0}</style>');return;}
  if (url.pathname.startsWith('/reference/api/')) {
    const endpoint=url.pathname.split('/').at(-1);
    res.setHeader('Content-Type','application/json');
    res.end(JSON.stringify(endpoint==='guide' ? fixture : endpoint==='bookmarks' ? {bookmarks:[]} : {reminders:[]}));return;
  }
  const base=url.pathname.startsWith('/reference/') ? reference : root;
  const relative=url.pathname.startsWith('/reference/') ? url.pathname.slice('/reference/'.length) : url.pathname.slice('/tv_guide/frontend/'.length);
  const file=path.resolve(base,relative);
  if (!file.startsWith(base+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {res.writeHead(404);res.end();return;}
  const mime={'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.ttf':'font/ttf','.json':'application/json'};
  res.setHeader('Content-Type',mime[path.extname(file)] || 'application/octet-stream');res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`; console.log('Test server ready',base);
  const launchOptions={headless:true,timeout:20000,...(process.env.TVG_BROWSER_PATH?{executablePath:process.env.TVG_BROWSER_PATH}:{})};
  let browser;
  if(process.env.TVG_BROWSER_PROFILE){
    const context=await chromium.launchPersistentContext(process.env.TVG_BROWSER_PROFILE,{...launchOptions,viewport:{width:1100,height:1000},timezoneId:'Europe/Berlin'});
    browser={newPage:()=>context.newPage(),close:()=>context.close()};
  }else browser=await chromium.launch(launchOptions);
  console.log('Browser ready');
  const native=await browser.newPage({viewport:{width:1100,height:1000},timezoneId:'Europe/Berlin'});
  const original=await browser.newPage({viewport:{width:1100,height:1000},timezoneId:'Europe/Berlin'});
  await native.clock.setFixedTime(new Date(fixed));await original.clock.setFixedTime(new Date(fixed));
  const errors=[];native.on('pageerror',e=>{errors.push(e.message);console.error('Browser error',e.message);});
  const requests=[];native.on('request',r=>{requests.push(r.url());if(process.env.TVG_DEBUG)console.log('Resource',r.url());});
  console.log('Pages ready');
  await native.goto(base);console.log('Native host ready');
  await native.addScriptTag({path:path.join(root,'tv-guide-native-card.js')});
  await native.evaluate(data=>{
    window.calls=[];window.model=structuredClone(data);window.saved={bookmarks:[],reminders:[]};window.fail='';
    window.hass={language:'de',locale:{language:'de'},config:{time_zone:'Europe/Berlin'},themes:{darkMode:false,themes:{}},services:{notify:{mobile_app_test:{}}},connection:{},
      async callWS(message){
        calls.push(message);if(fail===message.service)throw new Error('Simulated service failure');
        let response;
        if(message.service==='get_native_guide')response=model;
        else if(message.service==='get_saved_programmes')response=saved;
        else if(message.service==='get_native_channels')response={channels:model.channels,order:model.custom_channel_ids,countries:['de'],supported_countries:[{code:'de',name:'Deutschland'}]};
        else if(message.service==='get_ui_settings')response={...model.ui,country:'de'};
        else if(message.service==='set_ui_settings'){Object.assign(model.ui,message.service_data.options);response={ok:true};}
        else throw new Error('Unexpected service');
        return {response:structuredClone(response)};
      },
      async callService(domain,service,data){
        calls.push({domain,service,service_data:data});if(fail===service)throw new Error('Simulated write failure');
        if(service==='save_bookmark'||service==='save_reminder'){
          const key=service==='save_bookmark'?'bookmarks':'reminders';saved[key]=saved[key].filter(item=>item.id!==data.id);saved[key].push({...data,channelId:data.channel_id,sent:false});
        }else if(service==='remove_saved_programme'){
          for(const key of data.kind==='programme'?['bookmarks','reminders']:data.kind==='bookmark'?['bookmarks']:['reminders'])saved[key]=saved[key].filter(item=>item.id!==data.id);
        }else if(service==='set_channels')model.custom_channel_ids=data.channels.length?data.channels:model.main_channel_ids;
      }};
    const card=document.createElement('tv-guide-native-card');card.setConfig({height:1000});card.hass=hass;document.body.append(card);
  },fixture);console.log('Native card mounted');
  const card=native.locator('tv-guide-native-card');
  const frame=card.locator('iframe').contentFrame();
  await frame.locator('.channel-card').first().waitFor({timeout:20000});
  await original.goto(base+'/reference/index.html?tv_guide_card=1');
  await original.locator('.channel-card').first().waitFor();
  await frame.locator('body').evaluate(async()=>{await document.fonts.ready;await Promise.all(Array.from(document.images).filter(img=>img.getClientRects().length).map(img=>img.decode().catch(()=>{})));});
  await original.evaluate(async()=>{await document.fonts.ready;await Promise.all(Array.from(document.images).filter(img=>img.getClientRects().length).map(img=>img.decode().catch(()=>{})));});
  await frame.locator('body').evaluate(()=>document.activeElement?.blur());
  const first=await card.locator('iframe').screenshot();
  const expected=await original.screenshot({fullPage:false});
  if(process.env.TVG_SCREENSHOT){fs.writeFileSync(process.env.TVG_SCREENSHOT,first);fs.writeFileSync(process.env.TVG_SCREENSHOT.replace('.png','-reference.png'),expected);}
  assert.ok(first.equals(expected),'Native main view must be pixel-identical to the original add-on for the same data');
  console.log('PASS pixel-identical original card view on desktop (CSS, fonts, logos, rows, progress and toolbar)');

  await frame.locator('[data-channel-id="zdf"] [data-program-start]').nth(2).click();
  await frame.locator('#bookmarkProgram').click();
  await native.waitForFunction(()=>saved.bookmarks.length===1);
  assert.equal(await native.evaluate(()=>saved.bookmarks[0].id),'native_zdf_2');
  await frame.locator('#reminderEnabled').check();
  await native.waitForFunction(()=>saved.reminders.length===1);
  assert.equal(await native.evaluate(()=>saved.reminders[0].minutes),10);
  await frame.locator('#detail .close').click();
  await frame.locator('#showBookmarks').click();
  await frame.locator('#bookmarksBody [data-remove]').click();
  await native.waitForFunction(()=>saved.bookmarks.length===0&&saved.reminders.length===0);
  await frame.locator('#bookmarksDialog .close').click();
  console.log('PASS original programme detail, bookmark/reminder controls and atomic removal using native actions');

  await frame.locator('#showChannelSettings').click();
  await frame.locator('#channelSettingsList .channel-settings-row').first().waitFor();
  assert.equal(await frame.locator('#channelSettingsList .channel-settings-row').count(),5);
  await frame.locator('#saveChannelSettings').click();
  await native.waitForFunction(()=>calls.some(call=>call.service==='set_channels'));
  await frame.locator('#channelSettingsDialog').waitFor({state:'hidden'});
  await frame.locator('#showAppSettings').click();
  await frame.locator('#saveAppSettings').waitFor({state:'visible'});
  await native.waitForFunction(()=>calls.some(call=>call.service==='get_ui_settings'));
  await frame.locator('#cancelAppSettings').click();
  console.log('PASS original sender picker and settings dialogue route to native storage');

  await frame.locator('[data-mode="2015"]').click();
  await native.waitForFunction(()=>calls.some(call=>call.service==='get_native_guide'&&call.service_data.at?.includes('18:15')));
  await original.locator('[data-mode="2015"]').click();
  await frame.locator('[data-channel-view="main"]').click();
  await frame.locator('body').evaluate(()=>document.activeElement?.blur());
  await original.evaluate(()=>document.activeElement?.blur());
  const evening=await card.locator('iframe').screenshot();
  const eveningReference=await original.screenshot({fullPage:false});
  assert.ok(evening.equals(eveningReference),'Evening view must retain original appearance');
  console.log('PASS 20:15 view retains pixel parity and requests the native time window');
  for (const mode of ['now','1800','2200']) {
    await frame.locator(`[data-mode="${mode}"]`).click();
    await original.locator(`[data-mode="${mode}"]`).click();
    await frame.locator(`[data-mode="${mode}"].active`).waitFor();
    await frame.locator('body').evaluate(()=>document.activeElement?.blur());
    await original.evaluate(()=>document.activeElement?.blur());
    assert.ok((await card.locator('iframe').screenshot()).equals(await original.screenshot({fullPage:false})),`Header time ${mode} must match the add-on`);
  }
  await frame.locator('[data-mode="other"]').click();
  await frame.locator('#customDate').fill('2026-10-14');
  await frame.locator('#customTime').fill('21:30');
  await frame.locator('#applyCustomTime').click();
  await native.waitForFunction(()=>calls.some(call=>call.service==='get_native_guide'&&call.service_data.at?.includes('19:30')));
  await frame.locator('[data-channel-view="custom"]').click();
  await frame.locator('[data-channel-view="custom"].active').waitFor();
  assert.equal(await frame.locator('.channel-card').count(),5);
  await frame.locator('[data-channel-view="main"]').click();
  await frame.locator('[data-mode="2015"]').click();
  await original.locator('[data-mode="2015"]').click();
  console.log('PASS every header time button, custom date/time and main/personal view');

  await frame.locator('[data-channel-id="ard"] [data-program-start]').first().click();
  await native.evaluate(()=>fail='save_bookmark');
  await frame.locator('#bookmarkProgram').click();
  await frame.locator('#reminderStatus').filter({hasText:'Simulated write failure'}).waitFor();
  await frame.locator('#detail .close').click();
  await native.evaluate(()=>fail='');
  assert.equal(await native.evaluate(()=>calls.every(call=>call.type!=='supervisor/api')),true);
  assert.equal(requests.some(url=>url.includes('/app/api/')),false);
  const before=await native.evaluate(()=>calls.length);
  await native.evaluate(()=>window.postMessage({type:'tv-guide-native-request',id:'spoof',endpoint:'settings',method:'POST',body:{country:'fr'}},location.origin));
  await native.waitForTimeout(100);
  assert.equal(await native.evaluate(()=>calls.length),before);
  assert.deepEqual(errors,[]);
  console.log('PASS service errors visible; no add-on/Ingress/API fetches; unrelated window messages cannot write settings');

  const darkVars={"--primary-background-color":"#111318","--secondary-background-color":"#191c22","--card-background-color":"#191c22","--primary-text-color":"#f4f6f8","--secondary-text-color":"#acb3bd","--divider-color":"#343a44"};
  await native.evaluate(vars=>{
    for(const [key,value] of Object.entries(vars))document.documentElement.style.setProperty(key,value);
    hass.themes.darkMode=true;document.querySelector('tv-guide-native-card').hass={...hass};
  },darkVars);
  await original.evaluate(vars=>window.postMessage({type:'tv-guide-theme',vars,darkMode:true},location.origin),darkVars);
  await frame.locator('html[data-ha-theme="dark"]').waitFor();
  await original.locator('html[data-ha-theme="dark"]').waitFor();
  await frame.locator('body').evaluate(async()=>{document.activeElement?.blur();await Promise.all(Array.from(document.images).filter(img=>img.getClientRects().length).map(img=>img.decode().catch(()=>{})));});
  await original.evaluate(async()=>{document.activeElement?.blur();await Promise.all(Array.from(document.images).filter(img=>img.getClientRects().length).map(img=>img.decode().catch(()=>{})));});
  assert.ok((await card.locator('iframe').screenshot()).equals(await original.screenshot({fullPage:false})),'Dark theme must match the add-on');
  console.log('PASS pixel-identical dark theme and original dark logo variants');

  await native.setViewportSize({width:390,height:1000});await original.setViewportSize({width:390,height:1000});
  await native.waitForTimeout(100);
  await frame.locator('body').evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
  await original.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
  const mobile=await card.locator('iframe').screenshot();const mobileExpected=await original.screenshot({fullPage:false});
  assert.ok(mobile.equals(mobileExpected),'Mobile appearance must match the add-on');
  assert.equal(await frame.locator('html').evaluate(el=>el.scrollWidth<=390),true);
  console.log('PASS pixel-identical mobile card view');
  await native.evaluate(()=>{const card=document.querySelector('tv-guide-native-card');card.remove();document.body.append(card);});
  await frame.locator('.channel-card').first().waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS native card detach/reinsert rebuilds the original frontend');
  await native.setViewportSize({width:1100,height:1000});
  await native.evaluate(()=>{
    const previous=hass.callWS.bind(hass);
    hass.services.tv_guide={native_request:{}};
    hass.callWS=async message=>{
      if(message.service!=='native_request')return previous(message);
      calls.push(message);
      const {endpoint,method,body}=message.service_data;
      let response;
      if(endpoint==='guide')response=model;
      else if(endpoint==='personal-channels'&&method==='GET')response={channels:model.channels.map(ch=>({...ch,id:'de:'+ch.id})),order:model.main_channel_ids.map(id=>'de:'+id),countries:['de'],supported_countries:[{code:'de',name:'Deutschland'},{code:'gb',name:'Großbritannien'}]};
      else if(endpoint==='personal-channels')response={ok:true,order:body.order,countries:body.countries};
      else if(endpoint==='settings'&&method==='GET')response={...model.ui,country:'de'};
      else if(endpoint==='settings'){Object.assign(model.ui,body);response={ok:true};}
      else throw new Error('Unexpected original runtime route');
      return {response:structuredClone(response)};
    };
    document.querySelector('tv-guide-native-card').hass=hass;
  });
  await frame.locator('#showChannelSettings').click();
  await frame.locator('#channelSettingsList .channel-settings-row').first().waitFor();
  await frame.locator('#saveChannelSettings').click();
  await native.waitForFunction(()=>calls.some(call=>call.service==='native_request'&&call.service_data.endpoint==='personal-channels'&&call.service_data.method==='POST'));
  await frame.locator('#channelSettingsDialog').waitFor({state:'hidden'});
  await frame.locator('#showAppSettings').click();
  await frame.locator('#saveAppSettings').waitFor({state:'visible'});
  await frame.locator('#saveAppSettings:not([disabled])').waitFor();
  assert.equal(await frame.locator('[data-sensor-option], .lovelace-setup').count(),0);
  assert.equal(await frame.locator('summary').filter({hasText:'Auf dem Dashboard'}).count(),0);
  await frame.locator('details:has(#settingRefresh) > summary').click();
  await frame.locator('#settingRefresh').selectOption('360');
  await frame.locator('details:has(#testNotification) > summary').click();
  await frame.locator('#settingNotificationService').selectOption('notify.mobile_app_test');
  await frame.locator('#saveAppSettings').click();
  await native.waitForFunction(()=>calls.some(call=>call.service==='native_request'&&call.service_data.endpoint==='settings'&&call.service_data.method==='POST'));
  assert.equal(await native.evaluate(()=>model.ui.refresh_minutes),360);
  await frame.locator('#appSettingsDialog').waitFor({state:'hidden'});
  await frame.locator('#showAppSettings').click();
  await frame.locator('#saveAppSettings:not([disabled])').waitFor();
  await frame.locator('details:has(#testNotification) > summary').click();
  await frame.locator('#testNotification').click();
  await native.waitForFunction(()=>calls.some(call=>call.domain==='notify'&&call.service==='mobile_app_test'));
  await frame.locator('#cancelAppSettings').click();
  console.log('PASS automatic setup settings omit manual controls; refresh and native test notification work');
  assert.deepEqual(errors,[]);
  console.log('PASS full reference engine route for country picker and persisted settings');
  await native.addScriptTag({url:base+'/tv_guide/frontend/tv-guide-native-panel.js',type:'module'});
  await native.waitForFunction(()=>customElements.get('tv-guide-native-panel'));
  await native.evaluate(()=>{
    document.querySelector('tv-guide-native-card').remove();
    const panel=document.createElement('tv-guide-native-panel');panel.hass=hass;panel.narrow=false;document.body.append(panel);
  });
  const panelFrame=native.locator('tv-guide-native-panel').locator('tv-guide-native-card').locator('iframe').contentFrame();
  await panelFrame.locator('.channel-card').first().waitFor();
  assert.equal(await native.locator('tv-guide-native-panel').locator('header').textContent(),'TV Guide');
  await native.setViewportSize({width:390,height:700});
  await native.waitForFunction(()=>parseInt(document.querySelector('tv-guide-native-panel').shadowRoot.querySelector('tv-guide-native-card').shadowRoot.querySelector('iframe').style.height)<=700);
  assert.ok(await native.locator('tv-guide-native-panel').locator('iframe').evaluate(el=>parseInt(el.style.height)<=700));
  assert.deepEqual(errors,[]);
  console.log('PASS automatic sidebar panel loads the native guide and adapts to mobile');
  await browser.close();server.close();
})().catch(error=>{console.error(error);server.close();process.exit(1);});
