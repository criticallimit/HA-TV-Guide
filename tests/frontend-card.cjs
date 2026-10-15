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
  await guidePage.addScriptTag({url:base+'/tv_guide/frontend/tv-guide-card.js',type:'module'});
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
  const frame=card;
  await frame.locator('.channel-card').first().waitFor({timeout:20000});
  await original.goto(base+'/reference/index.html?tv_guide_card=1');
  await original.locator('.channel-card').first().waitFor();
  await frame.locator('.guide-root').evaluate(async el=>{await document.fonts.ready;await Promise.all(Array.from(el.querySelectorAll('img')).filter(img=>img.getClientRects().length).map(img=>img.decode().catch(()=>{})));});
  await original.evaluate(async()=>{await document.fonts.ready;await Promise.all(Array.from(document.images).filter(img=>img.getClientRects().length).map(img=>img.decode().catch(()=>{})));});
  await frame.locator('.guide-root').evaluate(el=>el.getRootNode().activeElement?.blur());
  const first=await card.locator('.guide-root').screenshot();
  const expected=await original.screenshot({fullPage:false});
  if(process.env.TVG_SCREENSHOT){fs.writeFileSync(process.env.TVG_SCREENSHOT,first);fs.writeFileSync(process.env.TVG_SCREENSHOT.replace('.png','-reference.png'),expected);}
  assert.ok(first.equals(expected),'TV Guide main view must be pixel-identical to the reference view for the same data');
  console.log('PASS pixel-identical original card view on desktop (CSS, fonts, logos, rows, progress and toolbar)');
  await frame.locator('[data-channel-id="zdf"] [data-program-start]').nth(2).click();
  await original.locator('[data-channel-id="zdf"] [data-program-start]').nth(2).click();
  await frame.locator('.guide-root').evaluate(el=>el.getRootNode().activeElement?.blur());
  await original.evaluate(()=>document.activeElement?.blur());
  const dialogPixels=[(await frame.locator('.guide-root').screenshot()).toString('base64'),(await original.screenshot({fullPage:false})).toString('base64')];
  // Native top-layer dialog shadows can round alpha compositing by 1–2 RGB
  // levels. Text, layout, controls and all non-modal views remain strict checks.
  assert.ok(await original.evaluate(async pair=>{
    const pixels=[];
    for(const encoded of pair){
      const image=new Image();image.src='data:image/png;base64,'+encoded;await image.decode();
      const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
      const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);pixels.push(ctx.getImageData(0,0,image.width,image.height).data);
    }
    return pixels[0].length===pixels[1].length&&pixels[0].every((value,index)=>Math.abs(value-pixels[1][index])<=2);
  },dialogPixels),'Programme dialog must retain its layout and colours');
  await frame.locator('#detail .close').click();await original.locator('#detail .close').click();

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
  await frame.locator('.guide-root').evaluate(el=>el.getRootNode().activeElement?.blur());
  await original.evaluate(()=>document.activeElement?.blur());
  const evening=await card.locator('.guide-root').screenshot();
  const eveningReference=await original.screenshot({fullPage:false});
  assert.ok(evening.equals(eveningReference),'Evening view must retain original appearance');
  console.log('PASS 20:15 view retains pixel parity with immediate local navigation');
  for (const mode of ['now','1800','2200']) {
    await frame.locator(`[data-mode="${mode}"]`).click();
    await original.locator(`[data-mode="${mode}"]`).click();
    await frame.locator(`[data-mode="${mode}"].active`).waitFor();
    await frame.locator('.guide-root').evaluate(el=>el.getRootNode().activeElement?.blur());
    await original.evaluate(()=>document.activeElement?.blur());
    assert.ok((await card.locator('.guide-root').screenshot()).equals(await original.screenshot({fullPage:false})),`Header time ${mode} must match the add-on`);
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
  await frame.locator('.guide-root[data-ha-theme="dark"]').waitFor();
  await original.locator('html[data-ha-theme="dark"]').waitFor();
  await frame.locator('.guide-root').evaluate(async el=>{el.getRootNode().activeElement?.blur();await Promise.all(Array.from(el.querySelectorAll('img')).filter(img=>img.getClientRects().length).map(img=>img.decode().catch(()=>{})));});
  await original.evaluate(async()=>{document.activeElement?.blur();await Promise.all(Array.from(document.images).filter(img=>img.getClientRects().length).map(img=>img.decode().catch(()=>{})));});
  assert.ok((await card.locator('.guide-root').screenshot()).equals(await original.screenshot({fullPage:false})),'Dark theme must match the add-on');
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
  await frame.locator('.guide-root[data-ha-theme="light"]').waitFor();
  assert.equal(await guidePage.evaluate(()=>document.querySelector('tv-guide-card')._config.theme),'Dirk');
  assert.equal(await guidePage.evaluate(()=>document.querySelector('tv-guide-card')._config.height),1000);
  assert.equal(await guidePage.evaluate(()=>getComputedStyle(document.querySelector('tv-guide-card')).getPropertyValue('--primary-color').trim()),'#123456');
  assert.equal(await frame.locator('.guide-root').evaluate(el=>getComputedStyle(el).getPropertyValue('--primary-background-color').trim()),'#fff');
  await guidePage.evaluate(()=>{hass.themes.darkMode=false;document.querySelector('tv-guide-card').hass={...hass};});
  assert.equal(await guidePage.evaluate(()=>getComputedStyle(document.querySelector('tv-guide-card')).getPropertyValue('--primary-color').trim()),'#654321');
  await themeSelect.selectOption('');
  await frame.locator('.guide-root[data-ha-theme="dark"]').waitFor();
  assert.equal(await guidePage.evaluate(()=>document.querySelector('tv-guide-card').style.getPropertyValue('--primary-background-color')),'');
  assert.equal(await guidePage.evaluate(()=>Object.hasOwn(document.querySelector('tv-guide-card')._config,'theme')&&document.querySelector('tv-guide-card')._config.theme!==''),false);
  await guidePage.evaluate(()=>{document.querySelector('tv-guide-card-editor').remove();hass.themes.darkMode=true;document.querySelector('tv-guide-card').hass={...hass};});
  assert.deepEqual(errors,[]);
  console.log('PASS visual theme picker preserves card configuration, applies mode values and restores dashboard inheritance');

  await guidePage.setViewportSize({width:390,height:1000});await original.setViewportSize({width:390,height:1000});
  await guidePage.waitForTimeout(100);
  await frame.locator('.guide-root').evaluate(el=>{el.getRootNode().activeElement?.blur();el.scrollTo(0,0);});
  await original.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
  const mobile=await card.locator('.guide-root').screenshot();const mobileExpected=await original.screenshot({fullPage:false});
  assert.ok(mobile.equals(mobileExpected),'Mobile appearance must match the add-on');
  assert.equal(await frame.locator('.guide-root').evaluate(el=>el.scrollWidth<=390),true);
  console.log('PASS pixel-identical mobile card view');
  await guidePage.evaluate(()=>{const card=document.querySelector('tv-guide-card');card.remove();document.body.append(card);});
  await frame.locator('.channel-card').first().waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS card detach/reinsert preserves the directly rendered view');
  await guidePage.setViewportSize({width:1100,height:1000});
  await guidePage.evaluate(()=>{
    const previous=hass.callWS.bind(hass);
    hass.services.tv_guide={guide_request:{}};
    hass.callWS=async message=>{
      if(message.service!=='guide_request')return previous(message);
      calls.push(message);
      const {endpoint,method,body}=message.service_data;
      let response;
      if(endpoint==='guide')response=body?.known_revision && body.known_revision===model.revision ? {unchanged:true,revision:model.revision} : model;
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
  const app=()=>document.querySelector('tv-guide-card')._app;
  await guidePage.evaluate(()=>{model.revision='refresh-in-progress';model.refresh_running=true;});
  assert.equal(await card.evaluate(async el=>{await el._app.loadGuide();return el._app.startupReloadTimer!==null;}),true);
  await guidePage.evaluate(()=>{model.revision='refresh-complete';model.refresh_running=false;});
  assert.equal(await card.evaluate(async el=>{await el._app.loadGuide();return el._app.startupReloadTimer;}),null);
  assert.ok(await guidePage.evaluate(()=>calls.some(c=>c.service_data?.body?.known_revision==='refresh-in-progress')));
  console.log('PASS conditional revisions and provider completion polling');

  await guidePage.evaluate(()=>{
    const previous=hass.callWS.bind(hass);
    window.preparation={installation_id:'native-test',first_install:true,complete:false,
      logos:{running:true,ready:false,completed:2,total:37,error:null},
      programmes:{running:true,ready:false,sources_completed:1,error:false}};
    hass.callWS=async message=>{
      if(message.service==='get_preparation_status')return {response:structuredClone(preparation)};
      if(message.service==='retry_preparation'){calls.push(message);preparation.logos.error=null;preparation.complete=false;return {response:preparation};}
      return previous(message);
    };
  });
  await frame.locator('#preparationDialog').waitFor({state:'visible',timeout:15000});
  assert.match(await frame.locator('#preparationLogos').textContent(),/2 \/ 37/);
  await frame.locator('#preparationClose').click();
  assert.equal(await frame.locator('#preparationBadge').isVisible(),true);
  let downloadedLogoAvailable=false;
  await guidePage.route('**/download-logo-test.svg',route=>route.fulfill({status:downloadedLogoAvailable?200:404,
    contentType:'image/svg+xml',headers:{'Cache-Control':'no-store'},
    body:downloadedLogoAvailable?'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20" fill="red"/></svg>':''}));
  await guidePage.evaluate(()=>{
    model.channels[0].logo_normalized_light=model.channels[0].logo_normalized_dark='/download-logo-test.svg';
    model.channels[0].logo_file_light=model.channels[0].logo_file='/download-logo-test.svg';model.revision='logo-failed';
  });
  await card.evaluate(el=>el._app.loadGuide());
  await guidePage.waitForFunction(()=>Array.from(document.querySelector('tv-guide-card').shadowRoot.querySelectorAll('.channel-card:first-child .channel-logo')).some(img=>img.style.display==='none'));
  await frame.locator('.channel-card .program-link').first().focus();
  await card.evaluate(el=>{window.retained=el.shadowRoot.querySelector('.channel-card .programs');window.retainedFocus=el.shadowRoot.activeElement;});
  downloadedLogoAvailable=true;
  await guidePage.evaluate(()=>{preparation.logos.completed=3;});
  await guidePage.waitForFunction(()=>Array.from(document.querySelector('tv-guide-card').shadowRoot.querySelectorAll('.channel-card:first-child .channel-logo')).some(img=>img.complete&&img.naturalWidth>0&&img.style.display!=='none'));
  assert.equal(await card.evaluate(el=>el.shadowRoot.querySelector('.channel-card .programs')===retained&&el.shadowRoot.activeElement===retainedFocus),true);
  await frame.locator('#preparationBadge').click();
  await guidePage.evaluate(()=>{preparation.logos.error='download_failed';preparation.logos.running=false;preparation.complete=true;});
  await frame.locator('#preparationRetry').waitFor({state:'visible'});
  await frame.locator('#preparationRetry').click();
  await guidePage.waitForFunction(()=>calls.some(c=>c.service==='retry_preparation'));
  await guidePage.evaluate(()=>{preparation.complete=true;preparation.logos.completed=37;preparation.logos.ready=true;preparation.programmes={running:false,ready:true,sources_completed:3,error:false};});
  await frame.locator('#preparationBadge').waitFor({state:'hidden',timeout:15000});
  await frame.locator('#preparationClose').click();
  console.log('PASS preparation progress, downloaded logos, focus preservation and failure recovery');

  await guidePage.addScriptTag({url:base+'/tv_guide/frontend/tv-guide-panel.js',type:'module'});
  await guidePage.waitForFunction(()=>customElements.get('tv-guide-panel'));
  await guidePage.evaluate(()=>{
    document.querySelector('tv-guide-card').remove();const panel=document.createElement('tv-guide-panel');panel.hass=hass;document.body.append(panel);
  });
  const panelCard=guidePage.locator('tv-guide-panel').locator('tv-guide-card');
  await panelCard.locator('.channel-card').first().waitFor();
  assert.equal(await guidePage.locator('iframe').count(),0);
  await guidePage.setViewportSize({width:390,height:700});
  await guidePage.waitForFunction(()=>document.querySelector('tv-guide-panel').shadowRoot.querySelector('tv-guide-card').shadowRoot.querySelector('.guide-root').clientHeight<=700);
  await guidePage.setViewportSize({width:700,height:390});
  await guidePage.waitForFunction(()=>document.querySelector('tv-guide-panel').shadowRoot.querySelector('tv-guide-card').shadowRoot.querySelector('.guide-root').clientHeight<=390);
  console.log('PASS sidebar panel directly renders the shared component');

  const countryInfo=JSON.parse(fs.readFileSync(path.join(reference,'..','data','countries.json'),'utf8'));
  const languageFor={at:'de',be:'fr',dk:'da',fr:'fr',de:'de',nl:'nl',no:'nb',se:'sv',ch:'it',gb:'en'};
  const baseline=structuredClone(fixture);
  for(const [country,language] of Object.entries(languageFor)){
    const catalogue=JSON.parse(fs.readFileSync(path.join(reference,'..','data',country==='de'?'channels.json':countryInfo[country].catalog),'utf8'));
    const rows=catalogue.channels.slice(0,5);
    const data={...structuredClone(baseline),country,ui:{...baseline.ui,language,theme_mode:'light'},main_channel_ids:rows.map(ch=>ch.id),custom_channel_ids:rows.map(ch=>ch.id),channels:rows.map(ch=>({...ch,available:true,logo_normalized_light:`/tv_guide/frontend/app/logos/${country}-${ch.id}-light.svg`,logo_normalized_dark:`/tv_guide/frontend/app/logos/${country}-${ch.id}-dark.svg`,programs:structuredClone(baseline.channels[0].programs)}))};
    Object.assign(fixture,data);
    const host=await browser.newPage({viewport:{width:1100,height:1000},timezoneId:'Europe/Berlin'});
    const ref=await browser.newPage({viewport:{width:1100,height:1000},timezoneId:'Europe/Berlin'});
    host.on('pageerror',error=>errors.push(error.message));
    await host.clock.setFixedTime(new Date(fixed));await ref.clock.setFixedTime(new Date(fixed));
    await host.goto(base);await host.addScriptTag({url:base+'/tv_guide/frontend/tv-guide-card.js',type:'module'});
    await host.evaluate(data=>{
      const hass={language:data.ui.language,themes:{darkMode:false,themes:{}},services:{tv_guide:{guide_request:{}}},async callWS(message){return {response:message.service==='get_saved_programmes'?{bookmarks:[],reminders:[]}:data};}};
      const card=document.createElement('tv-guide-card');card.setConfig({height:1000});card.hass=hass;document.body.append(card);
    },data);
    const view=host.locator('tv-guide-card').locator('.guide-root');
    await view.locator('.channel-card').first().waitFor();await ref.goto(base+'/reference/index.html?tv_guide_card=1');await ref.locator('.channel-card').first().waitFor();
    const ready=async el=>{await document.fonts.ready;const root=el||document;await Promise.all(Array.from(root.querySelectorAll('img')).filter(img=>{const r=img.getBoundingClientRect();return r.width&&r.height&&r.top<innerHeight&&r.bottom>0;}).map(img=>img.decode().catch(()=>{})));(el?.getRootNode()||document).activeElement?.blur();};
    await view.evaluate(ready);await ref.evaluate(ready);
    assert.equal(await view.getAttribute('lang'),language);
    assert.ok((await view.screenshot()).equals(await ref.screenshot({fullPage:false})),`Country ${country} and language ${language} retain original pixels`);
    await host.close();await ref.close();
  }
  console.log('PASS pixel parity for all ten countries');

  // Delayed initial data must leave a usable native toolbar, never a hidden iframe.
  for(const scenario of ['cached','expired','cold','storage-blocked','error','empty']){
    const page=await browser.newPage({viewport:{width:1100,height:1000},timezoneId:'Europe/Berlin'});
    page.on('pageerror',error=>errors.push(error.message));await page.clock.setFixedTime(new Date(fixed));
    if(scenario==='storage-blocked')await page.addInitScript(()=>{Storage.prototype.getItem=Storage.prototype.setItem=()=>{throw Error('Storage disabled');};});
    await page.goto(base);await page.addScriptTag({url:base+'/tv_guide/frontend/tv-guide-card.js',type:'module'});
    await page.evaluate(({data,scenario})=>{
      const snapshot=structuredClone(data);
      for(const ch of snapshot.channels){ch.programs[0].end=new Date(Date.now()-60000).toISOString();ch.programs[1].start=new Date(Date.now()-60000).toISOString();}
      if(['cached','expired'].includes(scenario)){
        const cached=structuredClone(snapshot);
        if(scenario==='expired')for(const ch of cached.channels)for(const p of ch.programs){p.start=new Date(Date.parse(p.start)-86400000).toISOString();p.end=new Date(Date.parse(p.end)-86400000).toISOString();}
        sessionStorage.setItem('tv-guide-first-paint-v1',JSON.stringify({version:1,at:Date.now()-5*60000,guide:cached}));
      }
      window.gate=new Promise(resolve=>window.release=resolve);
      window.hass={language:'de',themes:{darkMode:true,themes:{}},services:{tv_guide:{guide_request:{}}},async callWS(message){
        if(message.service==='get_saved_programmes')return {response:{bookmarks:[],reminders:[]}};
        if(message.service==='get_preparation_status')return {response:{complete:true}};
        window.startupReads=(window.startupReads||0)+1;
        await gate;if(scenario==='error')throw Error('Guide unavailable');
        return {response:{...snapshot,channels:scenario==='empty'?[]:snapshot.channels}};
      }};
      document.body.style.setProperty('--primary-background-color','#101820');
      const card=document.createElement('tv-guide-card');card.setConfig({height:1000});card.hass=hass;document.body.append(card);
    },{data:baseline,scenario});
    const card=page.locator('tv-guide-card'),view=card.locator('.guide-root');
    await view.locator('.guide-topbar').waitFor({state:'visible'});
    assert.equal(await card.locator('iframe').count(),0);
    assert.equal(await view.getAttribute('data-ha-theme'),'dark');
    if(scenario==='cached')assert.equal(await view.locator('.program.current strong').first().textContent(),'Film am Abend');
    else assert.equal(await view.locator('.channel-card').count(),0);
    if(scenario==='cold'){
      await card.evaluate(el=>{el.remove();document.body.append(el);});
      await page.waitForFunction(()=>startupReads===2);
      assert.equal(await view.locator('.empty-channel-list').count(),0,'Cancelling startup must not paint a spurious error');
      await page.evaluate(()=>new Promise(resolve=>setTimeout(resolve,50)));
      assert.equal(await page.evaluate(()=>startupReads),2,'A cancelled startup must not issue a stale fallback after reconnect');
    }
    await page.evaluate(()=>release());
    if(['error','empty'].includes(scenario))await view.locator('.empty-channel-list').waitFor();
    else await view.locator('.channel-card').first().waitFor();
    await page.close();
  }
  console.log('PASS immediate toolbar, valid snapshots, programme rollover, expired data, disabled storage and errors');
  // Two cards must not share translations, selected times, themes or host DOM.
  const isolated=await browser.newPage({viewport:{width:1400,height:1000},timezoneId:'Europe/Berlin'});
  isolated.on('pageerror',error=>errors.push(error.message));await isolated.clock.setFixedTime(new Date(fixed));
  await isolated.goto(base);await isolated.addScriptTag({url:base+'/tv_guide/frontend/tv-guide-card.js',type:'module'});
  await isolated.evaluate(data=>{
    sessionStorage.clear();window.nativeReads=[0,0];window.releasePending=null;
    document.documentElement.lang='en';document.body.style.fontSize='22px';
    for(const [index,language] of ['de','fr'].entries()){
      const snapshot=structuredClone(data);snapshot.ui.language='auto';snapshot.revision='native-'+index;
      const hass={language,themes:{darkMode:index===1,themes:{}},services:{tv_guide:{guide_request:{}}},async callWS(message){
        if(message.service==='get_saved_programmes')return {response:{bookmarks:[],reminders:[]}};
        if(message.service==='get_preparation_status')return {response:{complete:true}};
        nativeReads[index]++;
        if(window.holdNative&&index===0)await new Promise(resolve=>window.releasePending=resolve);
        return {response:structuredClone(snapshot)};
      }};
      const card=document.createElement('tv-guide-card');card.id='native-'+index;
      card.style.width='500px';card.style.setProperty('--primary-background-color',index?'#101820':'#fff');
      card.setConfig({height:600});card.hass=hass;document.body.append(card);
    }
  },baseline);
  const left=isolated.locator('#native-0'),right=isolated.locator('#native-1');
  await left.locator('.channel-card').first().waitFor();await right.locator('.channel-card').first().waitFor();
  assert.equal(await left.locator('.guide-root').getAttribute('lang'),'de');
  assert.equal(await right.locator('.guide-root').getAttribute('lang'),'fr');
  assert.equal(await left.locator('.guide-root').getAttribute('data-ha-theme'),'light');
  assert.equal(await right.locator('.guide-root').getAttribute('data-ha-theme'),'dark');
  assert.equal(await isolated.locator('html').getAttribute('lang'),'en','A card must not change Home Assistant language');
  assert.equal(await isolated.locator('body').evaluate(el=>getComputedStyle(el).fontSize),'22px');
  assert.equal(await left.locator('.guide-root').evaluate(el=>getComputedStyle(el).fontSize),'16px');
  await left.locator('[data-mode="2015"]').click();
  assert.equal(await right.locator('[data-mode="now"]').getAttribute('class'),'tab active');
  await left.locator('.program-link').first().click();
  await left.locator('#detail').waitFor({state:'visible'});
  assert.equal(await right.locator('dialog[open]').count(),0);
  assert.ok(await left.locator('#detail').evaluate(el=>el.getBoundingClientRect().width<=472),'A native dialog must stay within its 500px card width');
  assert.ok(await left.locator('.guide-root').evaluate(el=>el.scrollWidth<=500),'Responsive layout must use card width rather than browser width');
  await isolated.keyboard.press('Escape');await left.locator('#detail').waitFor({state:'hidden'});
  assert.equal(await isolated.locator('iframe').count(),0);
  await left.evaluate(el=>{window.savedCard=el;window.savedRoot=el.shadowRoot.querySelector('.guide-root');window.savedProgram=el.shadowRoot.querySelector('.program-link');});
  const readsBefore=await isolated.evaluate(()=>nativeReads[0]);
  await left.evaluate(el=>el.remove());
  assert.equal(await isolated.evaluate(()=>savedCard._app.suspended),true);
  await isolated.clock.fastForward(6*60*1000);
  assert.equal(await isolated.evaluate(()=>nativeReads[0]),readsBefore,'Detached cards must not poll');
  await isolated.evaluate(()=>document.body.prepend(savedCard));
  await left.locator('.channel-card').first().waitFor();
  assert.equal(await left.evaluate(el=>el.shadowRoot.querySelector('.guide-root')===savedRoot),true,'Reconnect must reuse the view');
  assert.equal(await left.evaluate(el=>el._app.mode),'2015','Reconnect must keep the selected time');
  await isolated.waitForFunction(()=>nativeReads[0]>0&&savedCard._pending.size===0);
  await isolated.evaluate(()=>{window.holdNative=true;void savedCard._app.loadGuide().catch(()=>{});});
  await isolated.waitForFunction(()=>typeof releasePending==='function');
  await left.evaluate(el=>el.remove());
  assert.equal(await isolated.evaluate(()=>savedCard._pending.size),0,'Disconnect must cancel owned pending requests');
  await isolated.evaluate(()=>{holdNative=false;releasePending();document.body.prepend(savedCard);});
  await left.locator('.channel-card').first().waitFor();
  await isolated.waitForFunction(()=>savedCard._pending.size===0);
  assert.equal(await left.evaluate(el=>el._app.mode),'2015');
  await isolated.close();
  console.log('PASS multiple-card isolation, keyboard dialogs, scoped styles, state retention and pending-request cleanup');

  assert.deepEqual(errors,[]);
  await browser.close();server.close();
})().catch(error=>{console.error(error);server.close();process.exit(1);});
