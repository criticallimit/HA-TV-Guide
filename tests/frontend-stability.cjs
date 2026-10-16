/* Cross-engine lifecycle and work-budget regressions for native Lovelace cards. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {chromium,webkit}=require('playwright');
const root=path.resolve(process.env.TVG_FRONTEND_ROOT||'custom_components/tv_guide/frontend');
const fixed='2026-10-14T18:00:00Z';
const engineName=process.env.TVG_ENGINE||'chromium';
const diagnostic=process.env.TVG_DIAGNOSTIC==='1';
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if(url.pathname==='/'){res.setHeader('Content-Type','text/html');res.end('<style>body{margin:0}</style>');return;}
  const file=path.resolve(root,url.pathname.slice('/tv_guide/frontend/'.length));
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',({'.js':'application/javascript','.svg':'image/svg+xml','.ttf':'font/ttf'})[path.extname(file)]||'text/plain');
  res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await({chromium,webkit}[engineName]).launch({headless:true,...(process.env.TVG_BROWSER_PATH?{executablePath:process.env.TVG_BROWSER_PATH}:{})});
  const page=await browser.newPage({viewport:{width:1436,height:1182},timezoneId:'Europe/Berlin'});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('crash',()=>errors.push('Browser page crashed'));
  await page.addInitScript(()=>{
    window.work={mutations:0,observed:0,errors:[]};
    const Original=ResizeObserver;
    window.ResizeObserver=class extends Original{
      constructor(fn){super(fn);this.targets=new Set();}
      observe(target,...args){if(!this.targets.has(target)){this.targets.add(target);work.observed++;}return super.observe(target,...args);}
      disconnect(){work.observed-=this.targets.size;this.targets.clear();return super.disconnect();}
    };
    window.addEventListener('error',e=>work.errors.push(e.message));
  });
  await page.goto(base);await page.clock.setFixedTime(new Date(fixed));
  await page.addScriptTag({url:base+'/tv_guide/frontend/tv-guide-card.js',type:'module'});
  await page.evaluate(()=>{
    window.requests=[];window.retained=[];
    const programs=Array.from({length:336},(_,i)=>({id:'p'+i,title:'Programme '+i,desc:'Programme description. '.repeat(20),start:new Date(Date.now()+(i-1)*3600000).toISOString(),end:new Date(Date.now()+i*3600000+1800000).toISOString()}));
    const channels=Array.from({length:20},(_,i)=>({id:'ch'+i,name:'Station '+i,logo_normalized_light:'/tv_guide/frontend/app/logos/de-ard-light.svg',logo_normalized_dark:'/tv_guide/frontend/app/logos/de-ard-dark.svg',programs}));
    window.model={revision:'complete-guide',country:'de',refresh_running:false,channels,main_channel_ids:channels.map(c=>c.id),custom_channel_ids:channels.map(c=>c.id),ui:{language:'de',theme_mode:'auto',default_view:'now',columns_desktop:5,max_channels:0}};
    window.hass={language:'de',themes:{darkMode:true,themes:{}},services:{tv_guide:{guide_request:{}}},async callWS(message){
      if(message.service==='get_saved_programmes')return {response:{bookmarks:[],reminders:[]}};
      if(message.service==='get_preparation_status')return {response:structuredClone(window.preparation||{complete:true})};
      if(message.service==='retry_preparation'){
        preparation.logos.error=false;preparation.logos.ready=true;preparation.complete=true;
        return {response:structuredClone(preparation)};
      }
      if(message.service!=='guide_request')throw Error('Unexpected test service');
      const request=message.service_data;requests.push(request);
      if(request.endpoint==='guide'&&window.failNextGuide){window.failNextGuide=false;throw Error('Temporary disconnect');}
      if(request.endpoint==='settings')return {response:{...model.ui,country:model.country}};
      if(request.endpoint==='personal-channels')return {response:{channels:Array.from({length:400},(_,i)=>({id:'ch'+i,name:'Station '+i,source_country:'de',country_name:'Deutschland',logo_normalized_light:channels[0].logo_normalized_light,logo_normalized_dark:channels[0].logo_normalized_dark})),order:model.custom_channel_ids,countries:['de'],supported_countries:[{code:'de',name:'Deutschland'}]}};
      const response=structuredClone(model);
      if(request.body?.preview){response._preview=true;for(const c of response.channels)c.programs=c.programs.slice(0,7);}
      return {response};
    }};
    window.mount=()=>{
      const card=document.createElement('tv-guide-card');card.setConfig({height:1000});card.hass=hass;document.body.append(card);return card;
    };
    window.card=mount();
  });
  await page.waitForFunction(()=>card._app?.guide&&!card._app.guide._preview&&card._app.lastGuideLoadedAt>0);
  await page.waitForTimeout(300);
  await page.evaluate(()=>{
    window.mutations=new MutationObserver(records=>work.mutations+=records.length);
    mutations.observe(card.shadowRoot.querySelector('.guide-root'),{subtree:true,attributes:true,childList:true,characterData:true});
  });
  await page.evaluate(async()=>{
    for(let i=0;i<24;i++){
      card.hass={...hass,states:{unrelated:i}};
      document.body.style.setProperty('--unrelated',String(i));
      await new Promise(resolve=>setTimeout(resolve,35));
    }
  });
  await page.waitForTimeout(100);
  const unchanged=await page.evaluate(()=>work.mutations);
  console.log(engineName,'DOM mutations for 24 unrelated updates:',unchanged);
  if(!diagnostic)assert.equal(unchanged,0,'Unchanged language and theme must not rewrite the view');
  await page.evaluate(()=>mutations.disconnect());
  // Time navigation must retain decoded logos, including Other times -> Now.
  await page.evaluate(async()=>{
    window.navigationModel=model;
    const channels=Array.from({length:200},(_,i)=>({...model.channels[i%20],id:'stress'+i,name:'Stress '+i}));
    model={...model,channels,main_channel_ids:channels.map(c=>c.id),custom_channel_ids:channels.map(c=>c.id)};
    await card._app.loadGuide();
    window.navigationCards=[...card.shadowRoot.querySelectorAll('.channel-card')];
    window.navigationBrands=navigationCards.map(c=>c.querySelector('.channel-brand'));
    window.navigationLogos=navigationBrands.map(c=>[...c.querySelectorAll('img')]);
    window.navigationRequests=requests.length;
    window.navigationURL=location.href;
  });
  console.log(engineName,'200-channel guide loaded');
  await page.locator('.channel-card').first().evaluate(section=>{
    section.querySelectorAll('img').forEach(image=>image.loading='eager');
  });
  await page.waitForFunction(()=>[...card.shadowRoot.querySelector('.channel-card').querySelectorAll('img')].some(image=>image.complete&&image.naturalWidth>0));
  console.log(engineName,'Logo loaded');
  await page.evaluate(async()=>{
    const root=card.shadowRoot;
    for(let i=0;i<12;i++){
      root.querySelector('[data-mode="other"]').click();
      root.querySelector('#customDate').value='2026-10-15';
      root.querySelector('#customTime').value='12:00';
      root.querySelector('#applyCustomTime').click();
      await new Promise(resolve=>setTimeout(resolve,25));
      root.querySelector('[data-mode="now"]').click();
      await new Promise(resolve=>setTimeout(resolve,25));
    }
  });
  const navigation=await page.evaluate(()=>({
    cards:navigationCards.every((c,i)=>card.shadowRoot.querySelectorAll('.channel-card')[i]===c),
    brands:navigationBrands.every((c,i)=>navigationCards[i].querySelector('.channel-brand')===c),
    logos:navigationLogos.every((images,i)=>images.every((image,j)=>navigationBrands[i].querySelectorAll('img')[j]===image)),
    requests:requests.length-navigationRequests,url:location.href===navigationURL,
    rows:card.shadowRoot.querySelectorAll('.program.current').length,
  }));
  console.log(engineName,'200-channel time navigation:',navigation);
  assert.equal(navigation.cards,true,'Time navigation must preserve station containers');
  assert.equal(navigation.brands,true,'Time navigation must preserve logo containers');
  assert.equal(navigation.logos,true,'Time navigation must retain decoded logo images');
  assert.equal(navigation.requests,0,'Complete guides switch times locally');
  assert.equal(navigation.url,true);assert.equal(navigation.rows,200);
  await page.evaluate(async()=>{model=navigationModel;await card._app.loadGuide();});
  await page.locator('[data-mode="2015"]').click();
  await page.locator('.program-link').first().click();
  await page.keyboard.press('Escape');
  await page.evaluate(()=>{window.savedRoot=card.shadowRoot.querySelector('.guide-root');card.remove();retained.push(card);});
  const detached=await page.evaluate(()=>({programmes:card._app.guide.channels.reduce((n,c)=>n+c.programs.length,0),preview:card._app.guide._preview,mode:card._app.mode,observed:work.observed}));
  console.log(engineName,'Detached view:',detached);
  if(!diagnostic){assert.equal(detached.programmes,20*7);assert.equal(detached.preview,true);assert.equal(detached.observed,0);}
  const before=await page.evaluate(()=>requests.length);
  await page.evaluate(()=>document.body.append(card));
  await page.waitForFunction(()=>!card._app.guide._preview&&card._pending.size===0);
  assert.equal(await page.evaluate(()=>card.shadowRoot.querySelector('.guide-root')===savedRoot&&card._app.mode==='2015'),true);
  if(!diagnostic)assert.equal(await page.evaluate(index=>requests[index].body?.known_revision,before),undefined,'A compacted view must request complete timelines again');
  await page.evaluate(()=>card.remove());
  for(let i=0;i<12;i++){
    await page.evaluate(()=>{window.card=mount();});
    await page.waitForFunction(()=>card._app?.guide&&!card._app.guide._preview&&card._app.lastGuideLoadedAt>0);
    if(i%3===0){await page.locator('#showAppSettings').click();await page.locator('#appSettingsDialog').waitFor({state:'visible'});await page.keyboard.press('Escape');}
    await page.evaluate(()=>{card.remove();retained.push(card);});
  }
  const retained=await page.evaluate(()=>({views:retained.length,programmes:retained.reduce((n,c)=>n+c._app.guide.channels.reduce((m,ch)=>m+ch.programs.length,0),0),observed:work.observed,pending:retained.reduce((n,c)=>n+c._pending.size,0),errors:work.errors}));
  console.log(engineName,'Retained hidden views:',retained);
  if(!diagnostic){
    assert.equal(retained.programmes,retained.views*20*7,'Hidden views must retain only their short visible window');
    assert.equal(retained.observed,0);assert.equal(retained.pending,0);assert.deepEqual(retained.errors,[]);
  }
  // Closing a large sender catalogue must release its DOM and still reopen correctly.
  await page.evaluate(()=>{window.card=mount();});
  await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
  await page.locator('#showChannelSettings').click();
  await page.waitForFunction(()=>card.shadowRoot.querySelectorAll('.available-channel-row').length===400);
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>!card.shadowRoot.querySelector('#channelSettingsDialog').open);
  await page.waitForTimeout(100);
  assert.equal(await page.locator('.available-channel-row').count(),0,'Closed sender catalogues must release their rows and images');
  await page.locator('#showChannelSettings').click();
  await page.waitForFunction(()=>card.shadowRoot.querySelectorAll('.available-channel-row').length===400);
  assert.equal(await page.locator('#personalChannelCount').textContent(),'20');
  await page.keyboard.press('Escape');
  // An empty response must clear the date limit left by a previous populated guide.
  assert.ok(await page.locator('#customDate').getAttribute('max'));
  await page.evaluate(async()=>{model.channels=[];await card._app.loadGuide();});
  assert.equal(await page.locator('#customDate').getAttribute('max'),'','Empty guides must clear the previous country date limit');
  await page.evaluate(()=>card.remove());
  // Preparation is a native card dialog; the browser viewport may be much wider.
  await page.evaluate(()=>{
    window.preparation={installation_id:'narrow-card',first_install:true,complete:false,logos:{completed:0,total:37,running:true,ready:false,error:false},programmes:{running:true,ready:false,sources_completed:0,error:false}};
    window.card=mount();card.style.width='300px';
  });
  await page.locator('#preparationDialog').waitFor({state:'visible'});
  const sizes=await page.evaluate(()=>({card:card.getBoundingClientRect().width,dialog:card.shadowRoot.querySelector('#preparationDialog').getBoundingClientRect().width}));
  assert.ok(sizes.dialog<=sizes.card-32,`Preparation dialog must fit its card: ${JSON.stringify(sizes)}`);
  await page.evaluate(()=>card.remove());
  // A bounded custom XMLTV response needs a new window after date/time navigation.
  await page.evaluate(()=>{
    window.feedCalls=[];
    const programmes=Array.from({length:48},(_,i)=>({id:'feed'+i,title:'Feed '+i,start:new Date(Date.now()+i*3600000).toISOString(),end:new Date(Date.now()+(i+1)*3600000).toISOString()}));
    const feedHass={...hass,services:{},async callWS(message){
      if(message.service==='get_saved_programmes')return {response:{bookmarks:[],reminders:[]}};
      if(message.service==='get_preparation_status')return {response:{complete:true}};
      if(message.service!=='get_guide')throw Error('Unexpected feed service');
      const at=message.service_data.at||new Date().toISOString();feedCalls.push(at);
      return {response:{_windowed:true,country:'de',ui:model.ui,feed_latest_end:programmes.at(-1).end,main_channel_ids:['feed'],custom_channel_ids:['feed'],channels:[{id:'feed',name:'Custom XMLTV',logo_normalized_light:'/tv_guide/frontend/app/logos/de-ard-light.svg',logo_normalized_dark:'/tv_guide/frontend/app/logos/de-ard-dark.svg',programs:programmes.filter(p=>Date.parse(p.end)>Date.parse(at)).slice(0,7)}]}};
    }};
    window.card=document.createElement('tv-guide-card');card.hass=feedHass;document.body.append(card);
  });
  await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
  await page.locator('[data-mode="other"]').click();
  await page.locator('#customDate').fill('2026-10-15');
  await page.locator('#customTime').fill('12:00');
  await page.locator('#applyCustomTime').click();
  await page.waitForFunction(()=>feedCalls.length===2,{},{timeout:5000});
  assert.equal(await page.locator('.program-link strong').first().textContent(),'Feed 16');
  await page.locator('[data-mode="now"]').click();
  await page.waitForFunction(()=>feedCalls.length===3);
  assert.equal(await page.locator('.program-link strong').first().textContent(),'Feed 0');
  await page.evaluate(()=>card.remove());
  // A brief tab switch must not discard a pending reconnect retry.
  await page.evaluate(()=>{window.preparation={complete:true};window.card=mount();});
  await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
  await page.evaluate(async()=>{
    window.recoveryStart=requests.length;
    window.failNextGuide=true;
    await card._app.loadGuide().catch(()=>{});
    window.testHidden=true;
    Object.defineProperty(document,'hidden',{configurable:true,get:()=>testHidden});
    document.dispatchEvent(new Event('visibilitychange'));
    window.testHidden=false;
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.waitForFunction(()=>requests.length>=recoveryStart+2,{},{timeout:3000});
  assert.equal(await page.evaluate(()=>card._app.startupReloadTimer),null);
  const recovered=await page.evaluate(()=>requests.length);
  await page.evaluate(()=>{
    testHidden=true;document.dispatchEvent(new Event('visibilitychange'));
    testHidden=false;document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>requests.length),recovered,'A successful recovery must clear the failure state');
  await page.evaluate(()=>{delete document.hidden;card.remove();});
  // A fast repair can complete between polls without changing the package count.
  await page.evaluate(()=>{
    model.channels=[{id:'logo',name:'Logo repair',logo_normalized_light:'/tv_guide/frontend/app/logos/de-ard-light.svg',logo_normalized_dark:'/tv_guide/frontend/app/logos/de-ard-dark.svg',programs:[{id:'logo-programme',title:'Programme',start:new Date().toISOString(),end:new Date(Date.now()+3600000).toISOString()}]}];
    model.main_channel_ids=model.custom_channel_ids=['logo'];
    window.preparation={installation_id:'fast-repair',first_install:false,complete:false,logos:{completed:37,total:37,ready:false,error:'damaged',running:false},programmes:{ready:true,running:false,error:false,sources_completed:1}};
    window.card=mount();
  });
  await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
  await page.locator('#preparationBadge').waitFor({state:'visible'});
  await page.evaluate(()=>{
    window.previousBrand=card.shadowRoot.querySelector('.channel-brand');
    window.previousLogo=previousBrand.querySelector('img');
    window.previousProgrammes=card.shadowRoot.querySelector('.programs');
    previousBrand.querySelectorAll('img').forEach(image=>image.style.display='none');
  });
  await page.locator('#preparationBadge').click();
  await page.locator('#preparationRetry').click();
  await page.waitForFunction(()=>card.shadowRoot.querySelector('.channel-brand img')!==previousLogo,{},{timeout:3000});
  assert.equal(await page.evaluate(()=>card.shadowRoot.querySelector('.programs')===previousProgrammes),true,'Repairing logos must preserve programme controls');
  await page.evaluate(()=>card.remove());
  // Delayed write responses must not resurrect another deleted bookmark.
  await page.evaluate(()=>{
    window.savedRows=['a','b'].map(id=>({id,title:'Saved '+id,channel:'Station',channelId:'ch0',start:new Date(Date.now()+3600000).toISOString(),end:new Date(Date.now()+7200000).toISOString()}));
    window.savedWrites=0;window.delayFirstSaved=true;
    const savedHass={...hass,async callWS(message){
      if(message.service!=='get_saved_programmes')return hass.callWS(message);
      const response={bookmarks:structuredClone(savedRows),reminders:[]};
      if(savedWrites===1&&delayFirstSaved){
        delayFirstSaved=false;
        await new Promise(resolve=>window.releaseSavedResponse=resolve);
      }
      return {response};
    },async callService(domain,service,data){
      if(service!=='remove_saved_programme')throw Error('Unexpected saved action');
      savedWrites++;
      if(window.failSavedWrite){window.failSavedWrite=false;throw Error('Temporary write failure');}
      savedRows=savedRows.filter(row=>row.id!==data.id);
    }};
    window.card=document.createElement('tv-guide-card');card.hass=savedHass;document.body.append(card);
  });
  await page.waitForFunction(()=>card.shadowRoot.querySelector('#bookmarkCount').textContent==='2');
  await page.locator('#showBookmarks').click();
  await page.locator('[data-remove="a"]').click();
  await page.waitForFunction(()=>typeof releaseSavedResponse==='function');
  await page.locator('[data-remove="b"]').click();
  await page.evaluate(()=>releaseSavedResponse());
  await page.waitForFunction(()=>savedWrites===2&&card._pending.size===0);
  await page.waitForTimeout(100);
  assert.equal(await page.locator('#bookmarkCount').textContent(),'0','Late responses must not resurrect deleted bookmarks');
  assert.equal(await page.locator('.bookmark-row').count(),0);
  const recovery=await page.evaluate(async()=>{
    window.savedRows=['a','b'].map(id=>({id}));window.failSavedWrite=true;
    const results=await Promise.allSettled(['a','b'].map(id=>card._request({endpoint:'bookmarks',method:'POST',body:{action:'remove',id}})));
    return {statuses:results.map(result=>result.status),remaining:savedRows.map(row=>row.id)};
  });
  assert.deepEqual(recovery,{statuses:['rejected','fulfilled'],remaining:['a']},'A failed write must not block subsequent saved actions');
  await page.evaluate(()=>{
    savedRows=['a','b'].map(id=>({id,title:'Saved '+id,channel:'Station',channelId:'ch0',start:new Date(Date.now()+3600000).toISOString(),end:new Date(Date.now()+7200000).toISOString()}));
    savedWrites=0;delayFirstSaved=true;delete window.releaseSavedResponse;
    window.closedWrites=Promise.allSettled(['a','b'].map(id=>card._request({endpoint:'bookmarks',method:'POST',body:{action:'remove',id}})));
  });
  await page.waitForFunction(()=>typeof releaseSavedResponse==='function');
  const closedWrites=await page.evaluate(async()=>{
    card.remove();document.body.append(card);releaseSavedResponse();
    return {statuses:(await closedWrites).map(result=>result.status),writes:savedWrites};
  });
  assert.deepEqual(closedWrites,{statuses:['rejected','rejected'],writes:1},'Closing and reopening must invalidate queued writes');
  await page.evaluate(()=>card.remove());
  console.log('PASS',engineName,'ordered saved writes, delayed responses, failure recovery and closing queued actions');
  // A UI timeout must not release write serialization while HA is still writing.
  await page.evaluate(()=>{
    window.timedWrites=[];window.timedValue='';
    const timedHass={...hass,async callService(domain,service,data){
      timedWrites.push(data.title);
      if(data.title==='old')await new Promise(resolve=>window.releaseTimedWrite=resolve);
      timedValue=data.title;
    }};
    window.card=document.createElement('tv-guide-card');card.hass=timedHass;document.body.append(card);
  });
  await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0&&card._pending.size===0);
  await page.evaluate(()=>{
    window.savedNativeTimeout=window.setTimeout;window.savedTimeoutCallbacks=[];
    window.setTimeout=(callback,delay,...args)=>{
      if(delay===15000)savedTimeoutCallbacks.push(callback);
      return savedNativeTimeout(callback,delay,...args);
    };
    const body={action:'upsert',id:'same',title:'old',channel:'Station',channelId:'ch',start:new Date(Date.now()+3600000).toISOString(),end:new Date(Date.now()+7200000).toISOString()};
    window.firstTimedWrite=card._request({endpoint:'bookmarks',method:'POST',body}).then(()=> 'fulfilled',()=> 'rejected');
    window.secondTimedBody={...body,title:'new'};
  });
  await page.waitForFunction(()=>typeof releaseTimedWrite==='function');
  const timed=await page.evaluate(async()=>{
    window.secondTimedWrite=card._request({endpoint:'bookmarks',method:'POST',body:secondTimedBody});
    savedTimeoutCallbacks[0]();
    await new Promise(resolve=>savedNativeTimeout(resolve,0));
    const beforeRelease=[...timedWrites];
    window.setTimeout=savedNativeTimeout;
    releaseTimedWrite();
    const first=await firstTimedWrite;await secondTimedWrite;
    return {beforeRelease,first,value:timedValue};
  });
  assert.deepEqual(timed,{beforeRelease:['old'],first:'rejected',value:'new'},'Timed-out writes must finish before later writes can commit');
  await page.evaluate(()=>card.remove());
  console.log('PASS',engineName,'write ordering survives UI timeout');
  // A committed settings save must not wait for the subsequent EPG transfer.
  await page.evaluate(()=>{
    const settings={...model.ui,country:'de',refresh_minutes:180,notification_service:'persistent_notification.create'};
    const settingsHass={...hass,async callWS(message){
      if(message.service==='guide_request'){
        const {endpoint,method,body}=message.service_data;
        if(endpoint==='settings'){
          if(method==='POST'){Object.assign(settings,body);window.settingsCommitted=true;}
          return {response:method==='POST'?{ok:true}:structuredClone(settings)};
        }
        if(endpoint==='guide'&&window.delaySettingsGuide){
          await new Promise(resolve=>window.releaseSettingsGuide=resolve);
        }
      }
      return hass.callWS(message);
    }};
    window.card=document.createElement('tv-guide-card');card.hass=settingsHass;document.body.append(card);
  });
  await page.waitForFunction(()=>card._app?.lastGuideLoadedAt>0);
  await page.locator('#showAppSettings').click();
  await page.locator('#saveAppSettings:not([disabled])').waitFor();
  await page.evaluate(()=>{
    card.shadowRoot.querySelector('#settingLanguage').value='en';
    window.delaySettingsGuide=true;
  });
  await page.locator('#saveAppSettings').click();
  await page.waitForFunction(()=>window.settingsCommitted&&typeof releaseSettingsGuide==='function');
  await page.locator('#appSettingsDialog').waitFor({state:'hidden',timeout:2000});
  await page.evaluate(()=>{delaySettingsGuide=false;releaseSettingsGuide();});
  await page.waitForFunction(()=>card._pending.size===0);
  await page.evaluate(()=>card.remove());
  console.log('PASS',engineName,'settings confirmation independent of delayed guide loading');
  assert.deepEqual(errors,[]);
  console.log('PASS',engineName,'closed catalogue cleanup, reopening, empty date limits, narrow preparation dialog, XMLTV date navigation, retry recovery and fast logo repair');
  await browser.close();server.close();console.log('PASS',engineName,'repeated opening, bounded inactive EPG and stable theme updates');
})().catch(error=>{console.error(error);server.close();process.exit(1);});
