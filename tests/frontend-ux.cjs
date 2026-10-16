/* Perceived startup and save latency with deliberately delayed guide responses. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium,webkit}=require('playwright');
const root=path.resolve('custom_components/tv_guide/frontend');
const engine=process.env.TVG_ENGINE||'chromium';
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if(url.pathname==='/'){res.setHeader('Content-Type','text/html');res.end('<style>body{margin:0}</style>');return;}
  const file=path.resolve(root,url.pathname.slice('/tv_guide/frontend/'.length));
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',({'.js':'application/javascript','.svg':'image/svg+xml','.ttf':'font/ttf'})[path.extname(file)]||'text/plain');res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await({chromium,webkit}[engine]).launch({headless:true,...(process.env.TVG_BROWSER_PATH?{executablePath:process.env.TVG_BROWSER_PATH}:{})});
  const errors=[],failures=[];
  async function mount(scenario){
    const page=await browser.newPage({viewport:{width:1100,height:1000},timezoneId:'Europe/Berlin'});
    page.on('pageerror',e=>errors.push(e.message));page.on('crash',()=>errors.push('Page crashed'));
    await page.goto(base);await page.clock.setFixedTime(new Date('2026-10-14T18:00:00Z'));
    await page.addScriptTag({url:base+'/tv_guide/frontend/tv-guide-card.js',type:'module'});
    await page.evaluate(scenario=>{
      const now=Date.now();
      window.settings={country:'de',language:'de',default_view:'now',theme_mode:'auto',columns_desktop:5,max_channels:0,refresh_minutes:180,notification_service:'persistent_notification.create'};
      const channels=['a','b'].map((id,index)=>({id,name:'Station '+id,source_country:'de',country_name:'Deutschland',logo_normalized_light:'/tv_guide/frontend/app/logos/de-ard-light.svg',logo_normalized_dark:'/tv_guide/frontend/app/logos/de-ard-dark.svg',programs:Array.from({length:7},(_,i)=>({id:id+i,title:'Programme '+id+i,start:new Date(now+(i+(index===0&&scenario!=='cache-contiguous'?2:0))*3600000).toISOString(),end:new Date(now+(i+1+(index===0&&scenario!=='cache-contiguous'?2:0))*3600000).toISOString()}))}));
      window.model={revision:'ux',country:'de',channels,main_channel_ids:['a','b'],custom_channel_ids:['a','b'],ui:{...settings},refresh_running:false};
      if(scenario==='personal'){
        channels.forEach(ch=>{ch.id='de:'+ch.id;ch.source_country='de';});
        channels.push({...structuredClone(channels[0]),id:'at:a',name:'Austria station',source_country:'at',country_name:'Österreich'});
        model.main_channel_ids=['de:a','de:b'];model.custom_channel_ids=['de:a'];
      }
      window.savedReads=0;window.order=scenario==='personal'?['de:a']:['a','b'];window.countries=['de'];window.settingsSaved=false;window.resetSaved=false;
      window.delayGuide=scenario.startsWith('cache');window.guideRequests=[];window.heldGuides=[];window.holdGuides=false;window.holdSettings=false;window.settingsPosts=0;window.notifications=[];window.holdNotification=false;window.holdSettingsReads=false;
      if(scenario.startsWith('cache'))sessionStorage.setItem('tv-guide-first-paint-v1',JSON.stringify({version:1,at:now-60000,guide:{...structuredClone(model),_preview:true}}));
      window.preparation=scenario==='preparation'?{installation_id:'ux-first',first_install:true,complete:false,logos:{completed:1,total:2,running:true,ready:false,error:false},programmes:{ready:true,running:false,sources_completed:1,error:false}}:{complete:true};
      window.hass={language:'de',themes:{darkMode:true,themes:{}},services:{tv_guide:{guide_request:{}},notify:{mobile_app_test:{}}},async callService(domain,service,payload){notifications.push({domain,service,payload});if(holdNotification)await new Promise(resolve=>window.releaseNotification=resolve);},async callWS(message){
        if(message.service==='get_ui_settings')return {response:structuredClone(settings)};
        if(message.service==='get_saved_programmes'){savedReads++;if(scenario==='saved-read')await new Promise(resolve=>window.releaseSaved=resolve);return {response:{bookmarks:[],reminders:[]}};}
        if(message.service==='get_preparation_status')return {response:structuredClone(preparation)};
        if(message.service!=='guide_request')throw Error('Unexpected UX service');
        const {endpoint,method,body}=message.service_data;
        if(endpoint==='settings'){
          if(method==='POST'){settingsPosts++;if(scenario==='held-settings'||holdSettings)await new Promise(resolve=>window.releaseSave=resolve);if(window.failSave)throw Error('Save failed');Object.assign(settings,body);model.ui={...settings};if(scenario==='switching'){model.country=settings.country;model.channels.forEach(ch=>ch.name=settings.country+' station '+ch.id);}settingsSaved=true;delayGuide=true;return {response:{ok:true,settings:structuredClone(settings)}};}
          if(holdSettingsReads)await new Promise(resolve=>window.releaseSettingsRead=resolve);
          if(window.failSettingsRead)throw Error('Settings unavailable');
          return {response:{...structuredClone(settings),...(scenario==='xmltv-menu'?{}:{countries:[{code:'de',name:'Deutschland'}]})}};
        }
        if(endpoint==='personal-channels'){
          if(scenario==='personal'){
            if(method==='POST'){
              order=[...body.order];countries=[...body.countries];model.custom_channel_ids=[...order];
              return {response:{ok:true,order:[...order],countries:[...countries]}};
            }
            return {response:{channels:structuredClone(channels),order:[...order],countries:[...countries],supported_countries:[{code:'de',name:'Deutschland'},{code:'at',name:'Österreich'}]}};
          }
          if(method==='POST'){if(scenario==='held-channels')await new Promise(resolve=>window.releaseSave=resolve);if(window.failSave)throw Error('Save failed');order=['a'];resetSaved=true;delayGuide=true;return {response:{ok:true,order,countries:['de']}};}
          return {response:{channels:structuredClone(channels),order:[...order],countries:['de'],supported_countries:[{code:'de',name:'Deutschland'}]}};
        }
        if(endpoint!=='guide')throw Error('Unexpected UX endpoint');
        guideRequests.push(message.service_data);
        if(scenario==='switching'){
          const response=structuredClone(model);
          if(holdGuides)return new Promise(resolve=>heldGuides.push(()=>resolve({response})));
          return {response};
        }
        if(delayGuide)await new Promise(resolve=>window.releaseGuide=resolve);
        return {response:structuredClone(model)};
      }};
      window.card=document.createElement('tv-guide-card');card.hass=hass;document.body.append(card);
    },scenario);
    return page;
  }
  async function check(name,test){try{await test();console.log('PASS',engine,name);}catch(error){failures.push(name+': '+error.message);console.error('FAIL',engine,name,error.message);}}
  await check('useful cached guide with one schedule gap',async()=>{
    const page=await mount('cache');try{
      await page.waitForFunction(()=>typeof releaseGuide==='function');
      assert.equal(await page.locator('.channel-card').count(),2,'A programme gap on one sender must not discard the useful first paint');
      await page.evaluate(()=>{window.firstCards=[...card.shadowRoot.querySelectorAll('.channel-card')];delayGuide=false;releaseGuide();});
      await page.waitForFunction(()=>card._app.lastGuideLoadedAt>0);
      assert.equal(await page.evaluate(()=>firstCards.every((node,i)=>card.shadowRoot.querySelectorAll('.channel-card')[i]===node)),true,'The matching live guide must retain cached station DOM');
    }finally{await page.close();}
  });
  await check('cached first paint skips redundant preview request',async()=>{
    const page=await mount('cache-contiguous');try{
      await page.waitForFunction(()=>typeof releaseGuide==='function');
      assert.equal(await page.locator('.channel-card').count(),2);
      assert.notEqual(await page.evaluate(()=>guideRequests[0].body?.preview),true,'An already visible cache must fetch full timelines directly');
      await page.evaluate(()=>{delayGuide=false;releaseGuide();});
    }finally{await page.close();}
  });
  await check('cached preview requests full schedules when changing time',async()=>{
    const page=await mount('cache-contiguous');try{
      await page.waitForFunction(()=>typeof releaseGuide==='function');
      const before=await page.evaluate(()=>guideRequests.length);
      await page.locator('.tab[data-mode="1800"]').click();
      await page.waitForFunction(before=>guideRequests.length>before,before,{timeout:1500});
      assert.equal(await page.locator('.channel-card').count(),2,'Keep the station cards visible while requesting the missing timelines');
      assert.equal(await page.evaluate(()=>guideRequests.at(-1).body?.known_revision),undefined);
      await page.evaluate(()=>{delayGuide=false;releaseGuide();});
      await page.waitForFunction(()=>card._app.lastGuideLoadedAt>0);
    }finally{await page.close();}
  });
  await check('detached preview requests full schedules when changing time',async()=>{
    const page=await mount('settings');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.evaluate(()=>{delayGuide=true;card.remove();document.body.append(card);});
      await page.waitForFunction(()=>typeof releaseGuide==='function');
      const before=await page.evaluate(()=>guideRequests.length);
      await page.locator('.tab[data-mode="2200"]').click();
      await page.waitForFunction(before=>guideRequests.length>before,before,{timeout:1500});
      await page.evaluate(()=>{delayGuide=false;releaseGuide();});
      await page.waitForFunction(()=>card._app.lastGuideLoadedAt>0);
    }finally{await page.close();}
  });
  await check('fresh settings replace a stale cached default view',async()=>{
    const page=await mount('cache-contiguous');try{
      await page.waitForFunction(()=>typeof releaseGuide==='function');
      assert.equal(await page.evaluate(()=>card._app.mode),'now');
      await page.evaluate(()=>{model.ui.default_view='2015';delayGuide=false;releaseGuide();});
      await page.waitForFunction(()=>card._app.lastGuideLoadedAt>0);
      assert.equal(await page.evaluate(()=>card._app.mode),'2015','The saved default must win over an older first-paint cache');
    }finally{await page.close();}
  });
  await check('fresh default settings do not override an explicit time choice',async()=>{
    const page=await mount('cache-contiguous');try{
      await page.waitForFunction(()=>typeof releaseGuide==='function');
      await page.locator('.tab[data-mode="2200"]').click();
      await page.evaluate(()=>{model.ui.default_view='2015';delayGuide=false;releaseGuide();});
      await page.waitForFunction(()=>card._app.lastGuideLoadedAt>0);
      assert.equal(await page.evaluate(()=>card._app.mode),'2200');
    }finally{await page.close();}
  });
  await check('saved display settings apply before delayed guide',async()=>{
    const page=await mount('settings');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      await page.evaluate(()=>{card.shadowRoot.querySelector('#settingLanguage').value='en';card.shadowRoot.querySelector('#settingColumns').value='4';});
      await page.locator('#saveAppSettings').click();await page.waitForFunction(()=>settingsSaved&&typeof releaseGuide==='function');
      const state=await page.evaluate(()=>({language:card.shadowRoot.querySelector('.guide-root').lang,columns:card.shadowRoot.querySelector('.guide-root').style.getPropertyValue('--desktop-columns'),saveDisabled:card.shadowRoot.querySelector('#saveAppSettings').disabled}));
      assert.deepEqual(state,{language:'en',columns:'4',saveDisabled:true},'Persisted settings must apply immediately and prevent duplicate saves');
      await page.locator('#appSettingsDialog').waitFor({state:'hidden',timeout:2000});
      await page.evaluate(()=>{delayGuide=false;releaseGuide();});
    }finally{await page.close();}
  });
  await check('rapid country and language commits survive out-of-order guide responses',async()=>{
    const page=await mount('switching');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.evaluate(()=>{holdGuides=true;void card._app.loadGuide();});
      await page.waitForFunction(()=>heldGuides.length===1);
      for(const [country,language,resolved] of [['at','en','en'],['fr','fr','fr'],['gb','auto','de']]){
        await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
        await page.evaluate(({country,language})=>{const root=card.shadowRoot;root.querySelector('#settingCountry').value=country;root.querySelector('#settingLanguage').value=language;},{country,language});
        await page.locator('#saveAppSettings').click();
        await page.waitForFunction(country=>settings.country===country,country);
        await page.waitForFunction(resolved=>card.shadowRoot.querySelector('.guide-root').lang===resolved,resolved,{timeout:1500});
        await page.locator('#appSettingsDialog').waitFor({state:'hidden',timeout:2000});
      }
      await page.waitForFunction(()=>heldGuides.length===4);
      await page.evaluate(()=>heldGuides.pop()());
      await page.waitForFunction(()=>card._app.guide.country==='gb');
      await page.evaluate(()=>{for(const release of heldGuides.splice(0))release();});
      await page.waitForTimeout(100);
      assert.equal(await page.evaluate(()=>card._app.guide.country),'gb');
      assert.match(await page.locator('.channel-card').first().textContent(),/gb station/);
      assert.equal(await page.evaluate(()=>card.shadowRoot.querySelector('.guide-root').lang),'de');
      await page.evaluate(()=>{card.hass={...hass,locale:{language:'nb-NO'}};});
      await page.waitForFunction(()=>card.shadowRoot.querySelector('.guide-root').lang==='nb');
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      assert.equal(await page.locator('#settingCountry').inputValue(),'gb');
      assert.equal(await page.locator('#settingLanguage').inputValue(),'auto');
    }finally{await page.close();}
  });
  await check('a guide from the previous country cannot apply during a newer save',async()=>{
    const page=await mount('switching');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.evaluate(()=>{holdGuides=true;});
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      await page.evaluate(()=>{card.shadowRoot.querySelector('#settingCountry').value='at';card.shadowRoot.querySelector('#settingLanguage').value='en';});
      await page.locator('#saveAppSettings').click();await page.waitForFunction(()=>heldGuides.length===1);
      await page.locator('#appSettingsDialog').waitFor({state:'hidden'});
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      await page.evaluate(()=>{holdSettings=true;card.shadowRoot.querySelector('#settingCountry').value='fr';card.shadowRoot.querySelector('#settingLanguage').value='fr';});
      await page.locator('#saveAppSettings').click();await page.waitForFunction(()=>typeof releaseSave==='function');
      await page.evaluate(()=>heldGuides.shift()());await page.waitForTimeout(100);
      assert.equal(await page.evaluate(()=>card._app.guide.country),'de','An older response must not replace the visible guide during a newer settings transaction');
      await page.evaluate(()=>{holdGuides=false;holdSettings=false;releaseSave();});
      await page.waitForFunction(()=>card._app.guide.country==='fr'&&card.shadowRoot.querySelector('.guide-root').lang==='fr');
    }finally{await page.close();}
  });
  await check('late settings acknowledgements cannot undo a newer country and language',async()=>{
    const page=await mount('switching');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.evaluate(()=>{
        const original=hass.callWS;
        hass.callWS=async message=>{
          const result=await original(message);
          if(message.service_data?.endpoint==='settings'&&message.service_data.method==='POST'&&message.service_data.body.country==='at'){
            await new Promise(resolve=>window.releaseAcknowledgement=resolve);
          }
          return result;
        };
      });
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      await page.evaluate(()=>{card.shadowRoot.querySelector('#settingCountry').value='at';card.shadowRoot.querySelector('#settingLanguage').value='en';});
      await page.locator('#saveAppSettings').click();await page.waitForFunction(()=>typeof releaseAcknowledgement==='function');
      await page.locator('#cancelAppSettings').click();
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      await page.evaluate(()=>{card.shadowRoot.querySelector('#settingCountry').value='fr';card.shadowRoot.querySelector('#settingLanguage').value='fr';});
      await page.locator('#saveAppSettings').click();
      await page.waitForFunction(()=>card._app.guide.country==='fr'&&card.shadowRoot.querySelector('.guide-root').lang==='fr');
      await page.evaluate(()=>releaseAcknowledgement());await page.waitForTimeout(100);
      assert.equal(await page.evaluate(()=>card._app.guide.country),'fr');
      assert.equal(await page.evaluate(()=>card.shadowRoot.querySelector('.guide-root').lang),'fr');
    }finally{await page.close();}
  });
  for(const [name,id,key,value] of [
    ['language','settingLanguage','language','en'],['columns','settingColumns','columns_desktop',3],
    ['theme','settingTheme','theme_mode','light'],['station limit','settingMaxChannels','max_channels',1],
    ['all stations','settingMaxChannels','max_channels',0],['default view','settingDefaultView','default_view','2015'],
    ['refresh interval','settingRefresh','refresh_minutes',720],['notification recipient','settingNotificationService','notification_service','notify.mobile_app_test']
  ])await check('settings round trip: '+name,async()=>{
    const page=await mount('settings');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      await page.evaluate(({id,value})=>{card.shadowRoot.querySelector('#'+id).value=String(value);},{id,value});
      await page.locator('#saveAppSettings').click();await page.waitForFunction(()=>settingsSaved&&typeof releaseGuide==='function');
      assert.equal(await page.evaluate(key=>settings[key],key),value);
      if(key==='language')assert.equal(await page.evaluate(()=>card.shadowRoot.querySelector('.guide-root').lang),value);
      if(key==='columns_desktop')assert.equal(await page.evaluate(()=>card.shadowRoot.querySelector('.guide-root').style.getPropertyValue('--desktop-columns')),String(value));
      if(key==='theme_mode')assert.equal(await page.evaluate(()=>card.shadowRoot.querySelector('.guide-root').dataset.haTheme),value);
      if(key==='max_channels')assert.equal(await page.locator('.channel-card').count(),value||2,'Apply the station limit before a slow guide response');
      await page.locator('#appSettingsDialog').waitFor({state:'hidden',timeout:2000});
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      assert.equal(await page.locator('#'+id).inputValue(),String(value));
      await page.locator('#cancelAppSettings').click();
      await page.evaluate(()=>{delayGuide=false;releaseGuide();});
      if(key==='default_view'){
        await page.evaluate(()=>{card.remove();card=document.createElement('tv-guide-card');card.hass=hass;document.body.append(card);});
        await page.waitForFunction(()=>card._app?.mode==='2015');
      }
    }finally{await page.close();}
  });
  await check('notification test uses draft recipient and language without saving',async()=>{
    const page=await mount('settings');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      await page.evaluate(()=>{const root=card.shadowRoot;root.querySelector('#settingNotificationService').value='notify.mobile_app_test';root.querySelector('#settingLanguage').value='fr';root.querySelectorAll('#appSettingsDialog details')[2].open=true;});
      await page.locator('#testNotification').click();await page.waitForFunction(()=>notifications.length===1);
      const sent=await page.evaluate(()=>notifications[0]);
      assert.equal(sent.domain,'notify');assert.equal(sent.service,'mobile_app_test');
      assert.match(sent.payload.title,/rappel/i);
      assert.equal(await page.evaluate(()=>settingsPosts),0,'Testing must not save other draft settings');
      assert.equal(await page.evaluate(()=>card.shadowRoot.querySelector('.guide-root').lang),'de','Testing a draft language must not change the saved UI language');
    }finally{await page.close();}
  });
  await check('notification test cannot run while settings are loading',async()=>{
    const page=await mount('settings');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.evaluate(()=>{holdSettingsReads=true;});
      await page.locator('#showAppSettings').click();await page.waitForFunction(()=>typeof releaseSettingsRead==='function');
      assert.equal(await page.locator('#testNotification').isEnabled(),false);
      await page.evaluate(()=>releaseSettingsRead());await page.locator('#saveAppSettings:not([disabled])').waitFor();
      assert.equal(await page.locator('#testNotification').isEnabled(),true);
    }finally{await page.close();}
  });
  await check('late notification result cannot overwrite a reopened settings dialogue',async()=>{
    const page=await mount('settings');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      await page.evaluate(()=>{holdNotification=true;card.shadowRoot.querySelectorAll('#appSettingsDialog details')[2].open=true;});
      await page.locator('#testNotification').click();await page.waitForFunction(()=>typeof releaseNotification==='function');
      await page.evaluate(()=>{card.shadowRoot.querySelector('#settingColumns').value='4';});
      await page.locator('#saveAppSettings').click();await page.waitForFunction(()=>settingsSaved&&card.shadowRoot.querySelector('.guide-root').style.getPropertyValue('--desktop-columns')==='4');
      await page.locator('#appSettingsDialog').waitFor({state:'hidden',timeout:2000});
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      assert.equal(await page.locator('#settingColumns').inputValue(),'4');
      assert.equal(await page.locator('#testNotificationStatus').textContent(),'');
      assert.equal(await page.locator('#testNotification').isEnabled(),false);
      await page.evaluate(()=>releaseNotification());await page.waitForFunction(()=>!card.shadowRoot.querySelector('#testNotification').disabled);
      assert.equal(await page.locator('#testNotificationStatus').textContent(),'');
    }finally{await page.close();}
  });
  await check('failed settings load recovers on reopening without a write',async()=>{
    const page=await mount('settings');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.evaluate(()=>{failSettingsRead=true;});
      await page.locator('#showAppSettings').click();await page.waitForFunction(()=>card.shadowRoot.querySelector('#appSettingsStatus').textContent==='Settings unavailable');
      assert.equal(await page.locator('#saveAppSettings').isEnabled(),false);
      await page.locator('#cancelAppSettings').click();await page.evaluate(()=>{failSettingsRead=false;});
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      assert.equal(await page.evaluate(()=>settingsPosts),0);
    }finally{await page.close();}
  });
  await check('cancelling draft settings leaves display and saved values unchanged',async()=>{
    const page=await mount('settings');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      await page.evaluate(()=>{const root=card.shadowRoot;root.querySelector('#settingLanguage').value='fr';root.querySelector('#settingColumns').value='3';root.querySelector('#settingTheme').value='light';});
      await page.locator('#cancelAppSettings').click();
      assert.equal(await page.evaluate(()=>settingsPosts),0);
      assert.equal(await page.evaluate(()=>card.shadowRoot.querySelector('.guide-root').lang),'de');
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      assert.equal(await page.locator('#settingLanguage').inputValue(),'de');
      assert.equal(await page.locator('#settingColumns').inputValue(),'5');
      assert.equal(await page.locator('#settingTheme').inputValue(),'auto');
    }finally{await page.close();}
  });
  for(const [scenario,unsupported] of [['settings',true],['xmltv-menu',false]])await check('XMLTV country option capability: '+scenario,async()=>{
    const page=await mount(scenario);try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      const feedOption=page.locator('#settingCountry option[value=""]');
      assert.equal(await feedOption.count(),unsupported?0:1);
      if(!unsupported){
        assert.equal(await feedOption.textContent(),'Alle Sender des eigenen Feeds');
        await page.locator('#settingCountry').evaluate(select=>select.closest('details').open=true);
        await page.selectOption('#settingCountry','');
        await page.locator('#saveAppSettings').click();await page.waitForFunction(()=>settingsSaved);
        assert.equal(await page.evaluate(()=>settings.country),'');
      }
    }finally{await page.close();}
  });
  await check('existing custom refresh interval survives unrelated settings saves',async()=>{
    const page=await mount('settings');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.evaluate(()=>{settings.refresh_minutes=90;});
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      assert.equal(await page.locator('#settingRefresh').inputValue(),'90');
      await page.evaluate(()=>{card.shadowRoot.querySelector('#settingColumns').value='4';});
      await page.locator('#saveAppSettings').click();await page.waitForFunction(()=>settingsSaved);
      assert.equal(await page.evaluate(()=>settings.refresh_minutes),90);
      await page.locator('#appSettingsDialog').waitFor({state:'hidden'});
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      assert.equal(await page.locator('#settingRefresh').inputValue(),'90');
    }finally{await page.close();}
  });
  for(const editDraft of [false,true])await check('late successful save reconciles a UI timeout; draft edits='+editDraft,async()=>{
    const page=await mount('switching');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0&&card._pending.size===0);
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      await page.evaluate(()=>{
        holdSettings=true;
        const nativeTimeout=window.setTimeout;
        window.settingsTimeouts=[];
        window.setTimeout=(callback,delay,...args)=>{if(delay===15000)settingsTimeouts.push(callback);return nativeTimeout(callback,delay,...args);};
        card.shadowRoot.querySelector('#settingColumns').value='4';
      });
      await page.locator('#saveAppSettings').click();await page.waitForFunction(()=>typeof releaseSave==='function');
      await page.evaluate(()=>settingsTimeouts[0]());
      await page.waitForFunction(()=>card.shadowRoot.querySelector('#appSettingsStatus').textContent==='Home Assistant request timed out');
      assert.equal(await page.locator('#saveAppSettings').isEnabled(),true);
      await page.evaluate(edit=>{if(edit)card.shadowRoot.querySelector('#settingColumns').value='6';holdSettings=false;releaseSave();},editDraft);
      await page.waitForFunction(()=>settings.columns_desktop===4);
      await page.waitForFunction(()=>card.shadowRoot.querySelector('.guide-root').style.getPropertyValue('--desktop-columns')==='4',null,{timeout:1500});
      if(editDraft){
        assert.equal(await page.locator('#appSettingsDialog').isVisible(),true);
        assert.equal(await page.locator('#settingColumns').inputValue(),'6','A late acknowledgement must preserve an unsaved newer draft');
        assert.equal(await page.locator('#saveAppSettings').isEnabled(),true);
      }else await page.locator('#appSettingsDialog').waitFor({state:'hidden',timeout:2000});
    }finally{await page.close();}
  });
  await check('invalid numeric settings do not commit and can be corrected',async()=>{
    const page=await mount('settings');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showAppSettings').click();await page.locator('#saveAppSettings:not([disabled])').waitFor();
      for(const [id,value] of [['settingColumns',''],['settingColumns','6.5'],['settingMaxChannels','501']]){
        await page.evaluate(({id,value})=>{const root=card.shadowRoot;root.querySelector('#settingColumns').value='5';root.querySelector('#settingMaxChannels').value='0';root.querySelector('#'+id).value=value;},{id,value});
        await page.locator('#saveAppSettings').click();
        assert.equal(await page.evaluate(()=>settingsPosts),0,'Invalid number fields must never start a settings write');
        assert.equal(await page.locator('#saveAppSettings').isEnabled(),true);
      }
      await page.evaluate(()=>{card.shadowRoot.querySelector('#settingColumns').value='4';card.shadowRoot.querySelector('#settingMaxChannels').value='1';});
      await page.locator('#saveAppSettings').click();await page.waitForFunction(()=>settingsSaved);
      assert.equal(await page.evaluate(()=>settings.columns_desktop),4);
      assert.equal(await page.locator('.channel-card').count(),1);
    }finally{await page.close();}
  });
  await check('reset controls recover before delayed guide',async()=>{
    const page=await mount('reset');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showChannelSettings').click();await page.locator('#resetChannelSettings:not([disabled])').waitFor();
      await page.locator('#resetChannelSettings').click();await page.waitForFunction(()=>resetSaved&&typeof releaseGuide==='function');
      assert.equal(await page.locator('#resetChannelSettings').isEnabled(),true,'A committed reset must not lock the dialogue until guide loading finishes');
      assert.match(await page.locator('#channelSettingsStatus').textContent(),/wiederhergestellt/);
      await page.evaluate(()=>{delayGuide=false;releaseGuide();});
    }finally{await page.close();}
  });
  await check('first installation completes without an extra close action',async()=>{
    const page=await mount('preparation');try{
      await page.locator('#preparationDialog').waitFor({state:'visible'});
      await page.evaluate(()=>{preparation.complete=true;preparation.logos={completed:2,total:2,running:false,ready:true,error:false};document.dispatchEvent(new Event('visibilitychange'));});
      await page.locator('#preparationDialog').waitFor({state:'hidden',timeout:2500});
      assert.equal(await page.locator('#preparationBadge').isVisible(),false);
    }finally{await page.close();}
  });
  await check('failed initial download stays open with retry',async()=>{
    const page=await mount('preparation');try{
      await page.locator('#preparationDialog').waitFor({state:'visible'});
      await page.evaluate(()=>{preparation.logos.error='download_failed';preparation.logos.running=false;document.dispatchEvent(new Event('visibilitychange'));});
      await page.locator('#preparationRetry').waitFor({state:'visible'});
      await page.waitForTimeout(1200);
      assert.equal(await page.locator('#preparationDialog').isVisible(),true);
      assert.equal(await page.locator('#preparationRetry').isEnabled(),true);
    }finally{await page.close();}
  });
  await check('mixed-country selection, buttons, drag order, save, reopen and removal',async()=>{
    const page=await mount('personal');try{
      await page.locator('.channel-card').first().waitFor();
      await page.locator('#showChannelSettings').click();
      await page.locator('#saveChannelSettings:not([disabled])').waitFor();
      await page.locator('#channelCountryFilters input[value="at"]').check();
      await page.locator('#availableChannelsList [data-channel-id="at:a"] input').check();
      await page.locator('#availableChannelsList [data-channel-id="de:b"] input').check();
      await page.locator('#channelSettingsList [data-channel-id="at:a"] .move-up').click();
      assert.deepEqual(await page.locator('#channelSettingsList .channel-settings-row').evaluateAll(rows=>rows.map(row=>row.dataset.channelId)),['at:a','de:a','de:b']);
      await page.evaluate(()=>{
        const root=card.shadowRoot,source=root.querySelector('#channelSettingsList [data-channel-id="de:b"]'),target=root.querySelector('#channelSettingsList [data-channel-id="at:a"]');
        const dataTransfer=new DataTransfer();dataTransfer.setData('text/plain',source.dataset.channelId);
        target.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer,clientY:target.getBoundingClientRect().top}));
      });
      await page.locator('#channelCountryFilters input[value="at"]').uncheck();
      await page.locator('#saveChannelSettings').click();
      await page.locator('#channelSettingsDialog').waitFor({state:'hidden'});
      await page.waitForFunction(()=>card.shadowRoot.querySelectorAll('.channel-card').length===3);
      assert.deepEqual(await page.locator('.channel-card').evaluateAll(rows=>rows.map(row=>row.dataset.channelId)),['de:b','at:a','de:a']);
      await page.locator('#showChannelSettings').click();
      await page.locator('#saveChannelSettings:not([disabled])').waitFor();
      assert.deepEqual(await page.locator('#channelSettingsList .channel-settings-row').evaluateAll(rows=>rows.map(row=>row.dataset.channelId)),['de:b','at:a','de:a']);
      assert.equal(await page.locator('#channelCountryFilters input[value="at"]').isChecked(),false);
      await page.locator('#channelSettingsList [data-channel-id="de:a"] .move-remove').click();
      await page.locator('#saveChannelSettings').click();
      await page.locator('#channelSettingsDialog').waitFor({state:'hidden'});
      await page.waitForFunction(()=>card.shadowRoot.querySelectorAll('.channel-card').length===2);
      assert.deepEqual(await page.locator('.channel-card').evaluateAll(rows=>rows.map(row=>row.dataset.channelId)),['de:b','at:a']);
    }finally{await page.close();}
  });
  await check('settings cannot accept unsaved edits during a pending commit',async()=>{
    const page=await mount('held-settings');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showAppSettings').click();
      await page.locator('#saveAppSettings:not([disabled])').waitFor();
      await page.locator('#saveAppSettings').click();
      await page.waitForFunction(()=>typeof releaseSave==='function');
      assert.equal(await page.locator('#settingCountry').isDisabled(),true);
      assert.equal(await page.locator('#settingLanguage').isDisabled(),true);
      await page.evaluate(()=>releaseSave());
      await page.locator('#appSettingsDialog').waitFor({state:'hidden'});
      await page.locator('#showAppSettings').click();
      await page.locator('#saveAppSettings:not([disabled])').waitFor();
      assert.equal(await page.locator('#settingCountry').isEnabled(),true);
    }finally{await page.close();}
  });
  await check('channel selection cannot accept unsaved edits during a pending commit',async()=>{
    const page=await mount('held-channels');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showChannelSettings').click();
      await page.locator('#saveChannelSettings:not([disabled])').waitFor();
      await page.locator('#saveChannelSettings').click();
      await page.waitForFunction(()=>typeof releaseSave==='function');
      assert.equal(await page.evaluate(()=>{
        const root=card.shadowRoot;
        return root.querySelector('#channelSearch').disabled &&
          ['channelCountryFilters','availableChannelsList','channelSettingsList'].every(id=>root.querySelector('#'+id).inert);
      }),true);
      await page.evaluate(()=>releaseSave());
      await page.locator('#channelSettingsDialog').waitFor({state:'hidden'});
      await page.locator('#showChannelSettings').click();
      await page.locator('#saveChannelSettings:not([disabled])').waitFor();
      assert.equal(await page.locator('#channelSearch').isEnabled(),true);
      assert.equal(await page.evaluate(()=>card.shadowRoot.querySelector('#channelSettingsList').inert),false);
    }finally{await page.close();}
  });
  for(const kind of ['settings','channels'])await check(kind+' editing recovers after a failed commit',async()=>{
    const page=await mount(kind==='settings'?'held-settings':'held-channels');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      const settings=kind==='settings';
      const open=settings?'#showAppSettings':'#showChannelSettings';
      const save=settings?'#saveAppSettings':'#saveChannelSettings';
      const dialog=settings?'#appSettingsDialog':'#channelSettingsDialog';
      await page.locator(open).click();await page.locator(save+':not([disabled])').waitFor();
      await page.evaluate(()=>window.failSave=true);
      await page.locator(save).click();await page.waitForFunction(()=>typeof releaseSave==='function');
      await page.evaluate(()=>releaseSave());
      await page.locator(save+':not([disabled])').waitFor();
      assert.equal(await page.locator(settings?'#settingCountry':'#channelSearch').isEnabled(),true);
      if(!settings)assert.equal(await page.evaluate(()=>card.shadowRoot.querySelector('#channelSettingsList').inert),false);
      await page.evaluate(()=>{failSave=false;window.releaseSave=null;});
      await page.locator(save).click();await page.waitForFunction(()=>typeof releaseSave==='function');
      await page.evaluate(()=>releaseSave());
      await page.locator(dialog).waitFor({state:'hidden'});
    }finally{await page.close();}
  });
  await check('bookmark and reminder refresh share one saved-state request',async()=>{
    const page=await mount('saved-read');try{
      await page.waitForFunction(()=>typeof releaseSaved==='function');
      assert.equal(await page.evaluate(()=>savedReads),1);
      await page.evaluate(()=>releaseSaved());
    }finally{await page.close();}
  });
  await check('reordering retains catalogue rows and decoded logos',async()=>{
    const page=await mount('personal');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showChannelSettings').click();await page.locator('#saveChannelSettings:not([disabled])').waitFor();
      await page.locator('#channelCountryFilters input[value="at"]').check();
      await page.locator('#availableChannelsList [data-channel-id="at:a"] input').check();
      await page.evaluate(()=>window.catalogueRows=[...card.shadowRoot.querySelector('#availableChannelsList').children]);
      await page.locator('#channelSettingsList [data-channel-id="at:a"] .move-up').click();
      assert.equal(await page.evaluate(()=>catalogueRows.every((row,i)=>card.shadowRoot.querySelector('#availableChannelsList').children[i]===row)),true);
    }finally{await page.close();}
  });
  await check('adding and removing stations retains catalogue logos and focus',async()=>{
    const page=await mount('personal');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      await page.locator('#showChannelSettings').click();await page.locator('#saveChannelSettings:not([disabled])').waitFor();
      await page.evaluate(()=>{
        window.catalogueRows=[...card.shadowRoot.querySelector('#availableChannelsList').children];
        window.catalogueImages=[...card.shadowRoot.querySelectorAll('#availableChannelsList img')];
      });
      const checkbox=page.locator('#availableChannelsList [data-channel-id="de:b"] input');
      await checkbox.check();
      assert.equal(await checkbox.evaluate(node=>node===node.getRootNode().activeElement),true,'Keep keyboard focus on the selected station');
      assert.equal(await page.evaluate(()=>catalogueRows.every((row,i)=>card.shadowRoot.querySelector('#availableChannelsList').children[i]===row)),true,'Adding a station must not rebuild the catalogue');
      await page.locator('#channelSettingsList [data-channel-id="de:b"] .move-remove').click();
      assert.equal(await checkbox.isChecked(),false);
      assert.equal(await page.evaluate(()=>catalogueImages.every((image,i)=>card.shadowRoot.querySelectorAll('#availableChannelsList img')[i]===image)),true,'Removing a station must retain decoded catalogue logos');
    }finally{await page.close();}
  });
  await check('post-save state does not reuse an older in-flight read',async()=>{
    const page=await mount('personal');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      const result=await page.evaluate(async()=>{
        let reads=0,release;
        const original=hass.callWS;
        hass.callWS=async message=>{
          if(message.service!=='get_saved_programmes')return original(message);
          reads++;
          if(reads===1)return await new Promise(resolve=>release=()=>resolve({response:{bookmarks:[],reminders:[]}}));
          return {response:{bookmarks:[{id:'new'}],reminders:[]}};
        };
        hass.callService=async()=>{};
        const first=card._request({endpoint:'bookmarks',method:'GET'});
        const saved=await card._request({endpoint:'bookmarks',method:'POST',body:{action:'upsert',id:'new',channelId:'de:a',title:'New',channel:'Station',start:'2026-10-14T19:00:00Z',end:'2026-10-14T20:00:00Z'}});
        const later=card._request({endpoint:'reminders',method:'GET'});
        release();await first;const refreshed=await later;
        return {reads,ids:saved.bookmarks.map(item=>item.id),refreshed:refreshed.bookmarks.map(item=>item.id)};
      });
      assert.deepEqual(result,{reads:3,ids:['new'],refreshed:['new']});
    }finally{await page.close();}
  });
  await check('saved-state refresh recovers after a shared read times out',async()=>{
    const page=await mount('personal');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0&&card._pending.size===0);
      const result=await page.evaluate(async()=>{
        let reads=0,release;
        const original=hass.callWS,nativeTimeout=window.setTimeout,callbacks=[];
        hass.callWS=async message=>{
          if(message.service!=='get_saved_programmes')return original(message);
          reads++;
          if(reads===1)return await new Promise(resolve=>release=()=>resolve({response:{bookmarks:[],reminders:[]}}));
          return {response:{bookmarks:[{id:'recovered'}],reminders:[]}};
        };
        window.setTimeout=(callback,delay,...args)=>{if(delay===15000)callbacks.push(callback);return nativeTimeout(callback,delay,...args);};
        try{
          const first=card._request({endpoint:'bookmarks',method:'GET'}).then(()=>false,()=>true);
          callbacks[0]();const timedOut=await first;
          const next=card._request({endpoint:'reminders',method:'GET'});
          release();const response=await next;
          return {reads,timedOut,ids:response.bookmarks.map(item=>item.id)};
        }finally{window.setTimeout=nativeTimeout;}
      });
      assert.deepEqual(result,{reads:2,timedOut:true,ids:['recovered']});
    }finally{await page.close();}
  });
  await check('background logo revision replaces images while keeping programmes mounted',async()=>{
    const page=await mount('personal');try{
      await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
      const result=await page.evaluate(async()=>{
        const section=card.shadowRoot.querySelector('.channel-card');
        const image=section.querySelector('img'),programme=section.querySelector('.program');
        model.revision='logos-updated';
        model.channels.forEach(channel=>{
          channel.logo_normalized_light+='?v=logos-updated';
          channel.logo_normalized_dark+='?v=logos-updated';
        });
        await card._app.loadGuide();
        return {sameCard:section===card.shadowRoot.querySelector('.channel-card'),
          sameProgramme:programme===section.querySelector('.program'),
          newImage:image!==section.querySelector('img'),url:section.querySelector('img').src};
      });
      assert.equal(result.sameCard,true);assert.equal(result.sameProgramme,true);assert.equal(result.newImage,true);
      assert.match(result.url,/v=logos-updated/);
    }finally{await page.close();}
  });
  await browser.close();server.close();assert.deepEqual(errors,[]);assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);server.close();process.exit(1);});
