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
  channels:stations.map(([id,name],index) => ({id,name,source_country:'de',available:true, logo_normalized_light:`/tv_guide/frontend/app/logos/de-${id}-light.svg`,logo_normalized_dark:`/tv_guide/frontend/app/logos/de-${id}-dark.svg`,programs:Array.from({length:7},(_,i)=>({id:`guide_${id}_${i}`,title:['Nachrichten','Film am Abend','Wissen und Kultur','Dokumentation','Spätprogramm','Nachtmagazin','Morgenprogramm'][i],start:new Date(Date.parse(fixed)+(i-1)*3600000).toISOString(),end:new Date(Date.parse(fixed)+i*3600000+1800000).toISOString(),desc:'Beschreibung der Sendung.',category:'Information',subtitle:''}))})),
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
  const guidePage=await browser.newPage({viewport:{width:1100,height:1000},timezoneId:'Europe/Berlin'});
  const original=await browser.newPage({viewport:{width:1100,height:1000},timezoneId:'Europe/Berlin'});
  await guidePage.clock.setFixedTime(new Date(fixed));await original.clock.setFixedTime(new Date(fixed));
  const errors=[];guidePage.on('pageerror',e=>{errors.push(e.message);console.error('Browser error',e.message);});
  const requests=[];guidePage.on('request',r=>{requests.push(r.url());if(process.env.TVG_DEBUG)console.log('Resource',r.url());});
  console.log('Pages ready');
  await guidePage.goto(base);console.log('TV Guide host ready');
  await guidePage.addScriptTag({path:path.join(root,'tv-guide-card.js')});
  await guidePage.waitForFunction(()=>customElements.get('tv-guide-card'));
  assert.equal(await guidePage.evaluate(()=>window.customCards.find(c=>c.type==='tv-guide-card')?.name),'TV Guide');
  await guidePage.evaluate(data=>{
    window.calls=[];window.model=structuredClone(data);window.saved={bookmarks:[],reminders:[]};window.fail='';
    localStorage.setItem('tvguide-guidePage-bookmarks',JSON.stringify([{id:'old-cache-record',title:'Old cache',start:'2040-10-14T20:00:00Z',end:'2040-10-14T21:00:00Z'}]));
    window.hass={language:'de',locale:{language:'de'},config:{time_zone:'Europe/Berlin'},themes:{darkMode:false,themes:{}},services:{notify:{mobile_app_test:{},send_message:{}}},connection:{},
      async callWS(message){
        calls.push(message);if(fail===message.service)throw new Error('Simulated service failure');
        let response;
        if(message.service==='get_guide')response=model;
        else if(message.service==='get_saved_programmes')response=saved;
        else if(message.service==='get_personal_channels')response={channels:model.channels,order:model.custom_channel_ids,countries:['de'],supported_countries:[{code:'de',name:'Deutschland'}]};
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
    const card=document.createElement('tv-guide-card');card.setConfig({height:1000});card.hass=hass;document.body.append(card);
  },fixture);console.log('TV Guide card mounted');
  const card=guidePage.locator('tv-guide-card');
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
  assert.ok(first.equals(expected),'TV Guide main view must be pixel-identical to the reference view for the same data');
  console.log('PASS pixel-identical original card view on desktop (CSS, fonts, logos, rows, progress and toolbar)');
  assert.equal(await frame.locator('#bookmarkCount').textContent(),'0');
  assert.equal(await guidePage.evaluate(()=>calls.some(call=>call.service==='save_bookmark'&&call.service_data.id==='old-cache-record')),false);

  await frame.locator('[data-channel-id="zdf"] [data-program-start]').nth(2).click();
  await frame.locator('#bookmarkProgram').click();
  await guidePage.waitForFunction(()=>saved.bookmarks.length===1);
  assert.equal(await guidePage.evaluate(()=>saved.bookmarks[0].id),'guide_zdf_2');
  await frame.locator('#reminderEnabled').check();
  await guidePage.waitForFunction(()=>saved.reminders.length===1);
  assert.equal(await guidePage.evaluate(()=>saved.reminders[0].minutes),10);
  await frame.locator('#detail .close').click();
  await frame.locator('#showBookmarks').click();
  await frame.locator('#bookmarksBody [data-remove]').click();
  await guidePage.waitForFunction(()=>saved.bookmarks.length===0&&saved.reminders.length===0);
  await frame.locator('#bookmarksDialog .close').click();
  console.log('PASS original programme detail, bookmark/reminder controls and atomic removal using TV Guide actions');

  await frame.locator('#showChannelSettings').click();
  await frame.locator('#channelSettingsList .channel-settings-row').first().waitFor();
  assert.equal(await frame.locator('#channelSettingsList .channel-settings-row').count(),5);
  await frame.locator('#saveChannelSettings').click();
  await guidePage.waitForFunction(()=>calls.some(call=>call.service==='set_channels'));
  await frame.locator('#channelSettingsDialog').waitFor({state:'hidden'});
  await frame.locator('#showAppSettings').click();
  await frame.locator('#saveAppSettings').waitFor({state:'visible'});
  await guidePage.waitForFunction(()=>calls.some(call=>call.service==='get_ui_settings'));
  await frame.locator('#cancelAppSettings').click();
  console.log('PASS original sender picker and settings dialogue route to TV Guide storage');

  const guideReadsBefore = await guidePage.evaluate(() => calls.filter(call => call.service === 'get_guide' || (call.service === 'guide_request' && call.service_data?.endpoint === 'guide')).length);
  await frame.locator('[data-mode="2015"]').click();
  await frame.locator('[data-mode="2015"].active').waitFor();
  await original.locator('[data-mode="2015"]').click();
  await frame.locator('[data-channel-view="main"]').click();
  await frame.locator('body').evaluate(()=>document.activeElement?.blur());
  await original.evaluate(()=>document.activeElement?.blur());
  const evening=await card.locator('iframe').screenshot();
  const eveningReference=await original.screenshot({fullPage:false});
  assert.ok(evening.equals(eveningReference),'Evening view must retain original appearance');
  console.log('PASS 20:15 view retains pixel parity with immediate local navigation');
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
  await frame.locator('[data-mode="other"].active').waitFor();
  await frame.locator('[data-channel-view="custom"]').click();
  await frame.locator('[data-channel-view="custom"].active').waitFor();
  assert.equal(await frame.locator('.channel-card').count(),5);
  await frame.locator('[data-channel-view="main"]').click();
  await frame.locator('[data-mode="2015"]').click();
  await original.locator('[data-mode="2015"]').click();
  const guideReadsAfter = await guidePage.evaluate(() => calls.filter(call => call.service === 'get_guide' || (call.service === 'guide_request' && call.service_data?.endpoint === 'guide')).length);
  assert.equal(guideReadsAfter, guideReadsBefore, 'Time-only navigation must not request the EPG again');
  console.log('PASS every header time button and custom time without extra backend queries');

  await frame.locator('[data-channel-id="ard"] [data-program-start]').first().click();
  await guidePage.evaluate(()=>fail='save_bookmark');
  await frame.locator('#bookmarkProgram').click();
  await frame.locator('#reminderStatus').filter({hasText:'Simulated write failure'}).waitFor();
  await frame.locator('#detail .close').click();
  await guidePage.evaluate(()=>fail='');
  assert.equal(await guidePage.evaluate(()=>calls.every(call=>call.type!=='supervisor/api')),true);
  assert.equal(requests.some(url=>url.includes('/app/api/')),false);
  const before=await guidePage.evaluate(()=>calls.length);
  await guidePage.evaluate(()=>window.postMessage({type:'tv-guide-request',id:'spoof',endpoint:'settings',method:'POST',body:{country:'fr'}},location.origin));
  await guidePage.waitForTimeout(100);
  assert.equal(await guidePage.evaluate(()=>calls.length),before);
  assert.deepEqual(errors,[]);
  console.log('PASS service errors visible; no add-on/Ingress/API fetches; unrelated window messages cannot write settings');

  const darkVars={"--primary-background-color":"#111318","--secondary-background-color":"#191c22","--card-background-color":"#191c22","--primary-text-color":"#f4f6f8","--secondary-text-color":"#acb3bd","--divider-color":"#343a44"};
  await guidePage.evaluate(vars=>{
    for(const [key,value] of Object.entries(vars))document.documentElement.style.setProperty(key,value);
    hass.themes.darkMode=true;document.querySelector('tv-guide-card').hass={...hass};
  },darkVars);
  await original.evaluate(vars=>window.postMessage({type:'tv-guide-theme',vars,darkMode:true},location.origin),darkVars);
  await frame.locator('html[data-ha-theme="dark"]').waitFor();
  await original.locator('html[data-ha-theme="dark"]').waitFor();
  await frame.locator('body').evaluate(async()=>{document.activeElement?.blur();await Promise.all(Array.from(document.images).filter(img=>img.getClientRects().length).map(img=>img.decode().catch(()=>{})));});
  await original.evaluate(async()=>{document.activeElement?.blur();await Promise.all(Array.from(document.images).filter(img=>img.getClientRects().length).map(img=>img.decode().catch(()=>{})));});
  assert.ok((await card.locator('iframe').screenshot()).equals(await original.screenshot({fullPage:false})),'Dark theme must match the add-on');
  console.log('PASS pixel-identical dark theme and original dark logo variants');

  await guidePage.evaluate(()=>{
    hass.themes.themes={Dirk:{'primary-background-color':'#fff','primary-text-color':'#111',modes:{dark:{'primary-color':'#123456'},light:{'primary-color':'#654321'}}},'A <B> & "C"':{}};
    document.querySelector('tv-guide-card').hass={...hass};
    const editor=customElements.get('tv-guide-card').getConfigElement();
    editor.hass=hass;editor.setConfig({type:'custom:tv-guide-card',height:1000});
    editor.addEventListener('config-changed',event=>document.querySelector('tv-guide-card').setConfig(event.detail.config));
    document.body.append(editor);
  });
  const themeSelect=guidePage.locator('tv-guide-card-editor').locator('#theme');
  assert.deepEqual(await themeSelect.locator('option').allTextContents(),['Home Assistant / Dashboard','A <B> & "C"','Dirk']);
  await themeSelect.selectOption('Dirk');
  assert.equal(await guidePage.evaluate(()=>{
    const editor=document.querySelector('tv-guide-card-editor'),select=editor.shadowRoot.getElementById('theme');
    select.focus();editor.setConfig({...editor._config});editor.hass={...hass,states:{updated:{state:'on'}}};
    return editor.shadowRoot.getElementById('theme')===select&&editor.shadowRoot.activeElement===select&&select.value==='Dirk';
  }),true);
  await frame.locator('html[data-ha-theme="light"]').waitFor();
  assert.equal(await guidePage.evaluate(()=>document.querySelector('tv-guide-card')._config.theme),'Dirk');
  assert.equal(await guidePage.evaluate(()=>document.querySelector('tv-guide-card')._config.height),1000);
  assert.equal(await guidePage.evaluate(()=>getComputedStyle(document.querySelector('tv-guide-card')).getPropertyValue('--primary-color').trim()),'#123456');
  assert.equal(await frame.locator('html').evaluate(el=>getComputedStyle(el).getPropertyValue('--primary-background-color').trim()),'#fff');
  await guidePage.evaluate(()=>{hass.themes.darkMode=false;document.querySelector('tv-guide-card').hass={...hass};});
  assert.equal(await guidePage.evaluate(()=>getComputedStyle(document.querySelector('tv-guide-card')).getPropertyValue('--primary-color').trim()),'#654321');
  await themeSelect.selectOption('');
  await frame.locator('html[data-ha-theme="dark"]').waitFor();
  assert.equal(await guidePage.evaluate(()=>document.querySelector('tv-guide-card').style.getPropertyValue('--primary-background-color')),'');
  assert.equal(await guidePage.evaluate(()=>Object.hasOwn(document.querySelector('tv-guide-card')._config,'theme')&&document.querySelector('tv-guide-card')._config.theme!==''),false);
  await guidePage.evaluate(()=>{document.querySelector('tv-guide-card-editor').remove();hass.themes.darkMode=true;document.querySelector('tv-guide-card').hass={...hass};});
  assert.deepEqual(errors,[]);
  console.log('PASS visual theme picker preserves card configuration, applies mode values and restores dashboard inheritance');

  await guidePage.setViewportSize({width:390,height:1000});await original.setViewportSize({width:390,height:1000});
  await guidePage.waitForTimeout(100);
  await frame.locator('body').evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
  await original.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
  const mobile=await card.locator('iframe').screenshot();const mobileExpected=await original.screenshot({fullPage:false});
  assert.ok(mobile.equals(mobileExpected),'Mobile appearance must match the add-on');
  assert.equal(await frame.locator('html').evaluate(el=>el.scrollWidth<=390),true);
  console.log('PASS pixel-identical mobile card view');
  await guidePage.evaluate(()=>{const card=document.querySelector('tv-guide-card');card.remove();document.body.append(card);});
  await frame.locator('.channel-card').first().waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS guidePage card detach/reinsert rebuilds the original frontend');
  await guidePage.setViewportSize({width:1100,height:1000});
  await guidePage.evaluate(()=>{
    const previous=hass.callWS.bind(hass);
    hass.services.tv_guide={guide_request:{}};
    hass.callWS=async message=>{
      if(message.service!=='guide_request')return previous(message);
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
    document.querySelector('tv-guide-card').hass=hass;
  });
  await frame.locator('#showChannelSettings').click();
  await frame.locator('#channelSettingsList .channel-settings-row').first().waitFor();
  await frame.locator('#saveChannelSettings').click();
  await guidePage.waitForFunction(()=>calls.some(call=>call.service==='guide_request'&&call.service_data.endpoint==='personal-channels'&&call.service_data.method==='POST'));
  await frame.locator('#channelSettingsDialog').waitFor({state:'hidden'});
  await frame.locator('#showAppSettings').click();
  await frame.locator('#saveAppSettings').waitFor({state:'visible'});
  await frame.locator('#saveAppSettings:not([disabled])').waitFor();
  assert.equal(await frame.locator('[data-sensor-option], .lovelace-setup').count(),0);
  assert.equal(await frame.locator('summary').filter({hasText:'Auf dem Dashboard'}).count(),0);
  await frame.locator('details:has(#settingRefresh) > summary').click();
  await frame.locator('#settingRefresh').selectOption('360');
  await frame.locator('details:has(#testNotification) > summary').click();
  assert.equal(await frame.locator('#settingNotificationService option[value="notify.send_message"]').count(),0);
  await frame.locator('#settingNotificationService').selectOption('notify.mobile_app_test');
  await frame.locator('#saveAppSettings').click();
  await guidePage.waitForFunction(()=>calls.some(call=>call.service==='guide_request'&&call.service_data.endpoint==='settings'&&call.service_data.method==='POST'));
  assert.equal(await guidePage.evaluate(()=>model.ui.refresh_minutes),360);
  await frame.locator('#appSettingsDialog').waitFor({state:'hidden'});
  await frame.locator('#showAppSettings').click();
  await frame.locator('#saveAppSettings:not([disabled])').waitFor();
  await frame.locator('details:has(#testNotification) > summary').click();
  await frame.locator('#testNotification').click();
  await guidePage.waitForFunction(()=>calls.some(call=>call.domain==='notify'&&call.service==='mobile_app_test'));
  const notification=await guidePage.evaluate(()=>calls.find(call=>call.domain==='notify'&&call.service==='mobile_app_test').service_data);
  assert.equal(notification.title,'TV Guide – Erinnerung');
  assert.match(notification.message,/Testbenachrichtigung/);
  await frame.locator('#cancelAppSettings').click();
  console.log('PASS automatic setup settings omit manual controls; refresh and guidePage test notification work');
  assert.deepEqual(errors,[]);
  console.log('PASS full reference engine route for country picker and persisted settings');
  await guidePage.evaluate(()=>{
    const previous=hass.callWS.bind(hass);
    window.preparation={installation_id:'browser-test',first_install:true,complete:false,
      logos:{running:true,ready:false,completed:2,total:37,error:null},
      programmes:{running:true,ready:false,sources_completed:1,error:false}};
    hass.callWS=async message=>{
      if(message.service==='get_preparation_status')return {response:structuredClone(preparation)};
      if(message.service==='retry_preparation'){calls.push(message);preparation.logos.error=null;return {response:preparation};}
      return previous(message);
    };
  });
  await frame.locator('#preparationDialog').waitFor({state:'visible',timeout:15000});
  assert.match(await frame.locator('#preparationLogos').textContent(),/2 \/ 37/);
  await frame.locator('#preparationClose').click();
  await frame.locator('#preparationDialog').waitFor({state:'hidden'});
  assert.equal(await frame.locator('#preparationBadge').isVisible(),true);
  await frame.locator('#preparationBadge').click();
  await guidePage.evaluate(()=>{preparation.logos.error='download_failed';preparation.logos.running=false;});
  await frame.locator('#preparationRetry').waitFor({state:'visible'});
  await frame.locator('#preparationRetry').click();
  await guidePage.waitForFunction(()=>calls.some(c=>c.service==='retry_preparation'));
  await guidePage.evaluate(()=>{preparation.complete=true;preparation.logos.completed=37;preparation.logos.ready=true;preparation.programmes={running:false,ready:true,sources_completed:3,error:false};});
  await frame.locator('#preparationBadge').waitFor({state:'hidden',timeout:15000});
  await frame.locator('#preparationClose').click();
  console.log('PASS initial preparation progress, dismissal, reopening, failure retry and completion');
  await guidePage.addScriptTag({url:base+'/tv_guide/frontend/tv-guide-panel.js',type:'module'});
  await guidePage.waitForFunction(()=>customElements.get('tv-guide-panel'));
  await guidePage.evaluate(()=>{
    document.querySelector('tv-guide-card').remove();
    const panel=document.createElement('tv-guide-panel');panel.hass=hass;panel.narrow=false;document.body.append(panel);
  });
  const panelFrame=guidePage.locator('tv-guide-panel').locator('tv-guide-card').locator('iframe').contentFrame();
  await panelFrame.locator('.channel-card').first().waitFor();
  assert.equal(await guidePage.locator('tv-guide-panel').locator('header').count(),0);
  await guidePage.setViewportSize({width:390,height:700});
  await guidePage.waitForFunction(()=>parseInt(document.querySelector('tv-guide-panel').shadowRoot.querySelector('tv-guide-card').shadowRoot.querySelector('iframe').style.height)<=700);
  assert.ok(await guidePage.locator('tv-guide-panel').locator('iframe').evaluate(el=>parseInt(el.style.height)<=700));
  await guidePage.setViewportSize({width:700,height:390});
  await guidePage.waitForFunction(()=>parseInt(document.querySelector('tv-guide-panel').shadowRoot.querySelector('tv-guide-card').shadowRoot.querySelector('iframe').style.height)<=390);
  assert.ok(await guidePage.locator('tv-guide-panel').locator('iframe').evaluate(el=>parseInt(el.style.height)<=390));
  assert.equal(await guidePage.evaluate(()=>{const card=document.createElement('tv-guide-card');card.setConfig({height:'auto'});return card.getCardSize();}),20);
  assert.deepEqual(errors,[]);
  console.log('PASS automatic sidebar panel loads the guide and adapts to mobile');

  const countryInfo=JSON.parse(fs.readFileSync(path.join(reference,'..','data','countries.json'),'utf8'));
  const languageFor={at:'de',be:'fr',dk:'da',fr:'fr',de:'de',nl:'nl',no:'nb',se:'sv',ch:'it',gb:'en'};
  for(const [country,language] of Object.entries(languageFor)){
    const catalogue=JSON.parse(fs.readFileSync(path.join(reference,'..','data',country==='de'?'channels.json':countryInfo[country].catalog),'utf8'));
    const rows=catalogue.channels.slice(0,5);
    const data={...structuredClone(fixture),country,ui:{...fixture.ui,language,theme_mode:'light',default_view:'now'},main_channel_ids:rows.map(ch=>ch.id),custom_channel_ids:rows.map(ch=>ch.id),channels:rows.map(ch=>({...ch,source_country:country,available:true,logo_normalized_light:`/tv_guide/frontend/app/logos/${country}-${ch.id}-light.svg`,logo_normalized_dark:`/tv_guide/frontend/app/logos/${country}-${ch.id}-dark.svg`,programs:structuredClone(fixture.channels[0].programs)}))};
    Object.assign(fixture,data);
    const host=await browser.newPage({viewport:{width:1100,height:1000},timezoneId:'Europe/Berlin'});
    const ref=await browser.newPage({viewport:{width:1100,height:1000},timezoneId:'Europe/Berlin'});
    host.on('pageerror',error=>errors.push(error.message));
    await host.clock.setFixedTime(new Date(fixed));await ref.clock.setFixedTime(new Date(fixed));
    await host.goto(base);await host.addScriptTag({path:path.join(root,'tv-guide-card.js')});
    await host.evaluate(data=>{
      const hass={language:data.ui.language,locale:{language:data.ui.language},themes:{darkMode:false,themes:{}},services:{tv_guide:{guide_request:{}}},async callWS(message){return {response:message.service==='get_saved_programmes'?{bookmarks:[],reminders:[]}:data};}};
      const card=document.createElement('tv-guide-card');card.setConfig({height:1000});card.hass=hass;document.body.append(card);
    },data);
    const countryCard=host.locator('tv-guide-card'),countryFrame=countryCard.locator('iframe').contentFrame();
    await countryFrame.locator('.channel-card').first().waitFor();await ref.goto(base+'/reference/index.html?tv_guide_card=1');await ref.locator('.channel-card').first().waitFor();
    const ready=async()=>{await document.fonts.ready;await Promise.all(Array.from(document.images).filter(img=>{const r=img.getBoundingClientRect();return r.width&&r.height&&r.top<innerHeight&&r.bottom>0;}).map(img=>img.decode().catch(()=>{})));document.activeElement?.blur();};
    await countryFrame.locator('body').evaluate(ready);await ref.evaluate(ready);
    assert.equal(await countryFrame.locator('html').getAttribute('lang'),language);
    assert.ok((await countryCard.locator('iframe').screenshot()).equals(await ref.screenshot({fullPage:false})),`Country ${country} and language ${language} must retain original pixels`);
    await host.close();await ref.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS pixel parity for all ten countries and all eight interface languages');
  await browser.close();server.close();
})().catch(error=>{console.error(error);server.close();process.exit(1);});
