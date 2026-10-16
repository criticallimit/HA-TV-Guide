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
      window.order=scenario==='personal'?['de:a']:['a','b'];window.countries=['de'];window.settingsSaved=false;window.resetSaved=false;
      window.delayGuide=scenario.startsWith('cache');window.guideRequests=[];
      if(scenario.startsWith('cache'))sessionStorage.setItem('tv-guide-first-paint-v1',JSON.stringify({version:1,at:now-60000,guide:{...structuredClone(model),_preview:true}}));
      window.preparation=scenario==='preparation'?{installation_id:'ux-first',first_install:true,complete:false,logos:{completed:1,total:2,running:true,ready:false,error:false},programmes:{ready:true,running:false,sources_completed:1,error:false}}:{complete:true};
      window.hass={language:'de',themes:{darkMode:true,themes:{}},services:{tv_guide:{guide_request:{}}},async callWS(message){
        if(message.service==='get_saved_programmes')return {response:{bookmarks:[],reminders:[]}};
        if(message.service==='get_preparation_status')return {response:structuredClone(preparation)};
        if(message.service!=='guide_request')throw Error('Unexpected UX service');
        const {endpoint,method,body}=message.service_data;
        if(endpoint==='settings'){
          if(method==='POST'){if(scenario==='held-settings')await new Promise(resolve=>window.releaseSave=resolve);if(window.failSave)throw Error('Save failed');Object.assign(settings,body);model.ui={...settings};settingsSaved=true;delayGuide=true;return {response:{ok:true,settings:structuredClone(settings)}};}
          return {response:structuredClone(settings)};
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
  await browser.close();server.close();assert.deepEqual(errors,[]);assert.deepEqual(failures,[]);
})().catch(error=>{console.error(error);server.close();process.exit(1);});
