/* Capture the real native card with example schedules and each registered UI language.
   Run after tests/prepare_logo_fixtures.py; PNG output goes to work/gallery/captures.
   Encode dashboard-card.png as WebP (quality 88) for docs/screenshots/<language>/. */
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const serveLogo=require('../tests/logo-fixtures.cjs');
const root=path.resolve('custom_components/tv_guide/frontend');
const languages=Object.keys(JSON.parse(fs.readFileSync('custom_components/tv_guide/languages.json')));
const catalogue=JSON.parse(fs.readFileSync('custom_components/tv_guide/catalogs/channels.json')).channels.slice(0,15);
const countryOptions=Object.entries(JSON.parse(fs.readFileSync('custom_components/tv_guide/countries.json'))).map(([code,item])=>({code,name:item.name,language:item.language}));
const fixed='2026-10-14T18:00:00Z';
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost');if(serveLogo(url,res))return;
 if(url.pathname==='/'){res.setHeader('Content-Type','text/html');res.end('<style>body{margin:0;background:#1d2025}tv-guide-card{display:block}</style>');return;}
 const file=path.resolve(root,url.pathname.slice('/tv_guide/frontend/'.length));
 if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.ttf')?'font/ttf':'text/html');res.end(fs.readFileSync(file));
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({headless:true,...(process.env.TVG_BROWSER_PATH?{executablePath:process.env.TVG_BROWSER_PATH}:{})});
 try{
  for(const language of languages){
   console.log('Capturing',language);
   const page=await browser.newPage({viewport:{width:1400,height:1050},locale:language,timezoneId:'Europe/Berlin'});
   const errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.goto('http://127.0.0.1:'+server.address().port);await page.clock.setFixedTime(new Date(fixed));
   await page.addScriptTag({url:'http://127.0.0.1:'+server.address().port+'/tv_guide/frontend/tv-guide-card.js',type:'module'});
   await page.evaluate(({language,catalogue,countryOptions,fixed})=>{
    const now=Date.parse(fixed),titles=['Tagesschau','Wissen und Kultur','Film am Abend','Dokumentation','Spätprogramm','Nachtmagazin','Morgenmagazin'];
    const channels=catalogue.map((ch,index)=>({id:ch.id,name:ch.name,source_country:'de',country_name:'Deutschland',available:true,logo_normalized_light:'/tv_guide/logo/logos/channels/de/'+ch.id+'-light.svg',logo_normalized_dark:'/tv_guide/logo/logos/channels/de/'+ch.id+'-dark.svg',programs:titles.map((title,i)=>({id:ch.id+'_'+i,title,start:new Date(now+(i-1)*3600000).toISOString(),end:new Date(now+i*3600000+1800000).toISOString(),desc:'Beispielprogramm',category:'',subtitle:''}))}));
    const settings={country:'de',language,default_view:'now',theme_mode:'auto',columns_desktop:5,max_channels:0,refresh_minutes:180,notification_service:'persistent_notification.create'};
    const model={revision:'gallery',country:'de',ui:settings,refresh_running:false,channels,main_channel_ids:channels.map(ch=>ch.id),custom_channel_ids:channels.slice(0,8).map(ch=>ch.id)};
    window.hass={language,locale:{language},config:{time_zone:'Europe/Berlin'},themes:{darkMode:true,themes:{}},services:{tv_guide:{guide_request:{}}},async callService(){},async callWS(message){
     if(message.service==='get_ui_settings')return{response:settings};
     if(message.service==='get_saved_programmes')return{response:{bookmarks:[],reminders:[]}};
     if(message.service==='get_preparation_status')return{response:{complete:true}};
     const endpoint=message.service_data?.endpoint;
     if(endpoint==='guide')return{response:structuredClone(model)};
     if(endpoint==='settings')return{response:{...settings,countries:countryOptions}};
     if(endpoint==='personal-channels')return{response:{channels:structuredClone(channels.map(ch=>({...ch,id:'de:'+ch.id}))),order:model.custom_channel_ids.map(id=>'de:'+id),countries:['de'],supported_countries:countryOptions}};
     throw Error('Unexpected screenshot action: '+message.service+' '+endpoint);
    }};
    window.card=document.createElement('tv-guide-card');card.setConfig({height:1050});card.hass=hass;document.body.append(card);
   },{language,catalogue,countryOptions,fixed});
   await page.waitForFunction(language=>card._app?.lastGuideLoadedAt>0&&card.shadowRoot.querySelector('.guide-root').lang===language,language);
   await page.evaluate(async()=>{await document.fonts.ready;const images=[...card.shadowRoot.querySelectorAll('img')];images.forEach(el=>el.loading='eager');await Promise.all(images.map(el=>el.decode().catch(()=>{})));});
   const output=path.resolve('work/gallery/captures',language);fs.mkdirSync(output,{recursive:true});
   await page.screenshot({path:path.join(output,'program-overview.png')});
   await page.locator('#showChannelSettings').click();await page.locator('#channelSettingsList .channel-settings-row').first().waitFor();
   await page.screenshot({path:path.join(output,'my-channels.png')});
   await page.locator('#cancelChannelSettings').click();
   await page.locator('[data-mode="other"]').click();await page.locator('#customTimeDialog').waitFor();
   await page.screenshot({path:path.join(output,'other-times.png')});
   await page.locator('#cancelCustomTime').click();
   await page.evaluate(()=>{card.style.cssText='max-width:1100px;margin:24px auto';});
   await page.screenshot({path:path.join(output,'dashboard-card-dark.png')});
   await page.evaluate(()=>{document.body.style.background='#eef1f4';card.style.cssText='max-width:1100px;margin:24px auto';card.hass={...hass,themes:{darkMode:false,themes:{}}};});
   await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   await page.screenshot({path:path.join(output,'dashboard-card-light.png')});
   // Capture the same real card in both themes through a 45° torn-paper window.
   const light=fs.readFileSync(path.join(output,'dashboard-card-light.png')).toString('base64');
   const dark=fs.readFileSync(path.join(output,'dashboard-card-dark.png')).toString('base64');
   const composition=await browser.newPage({viewport:{width:1400,height:1050}});
   const seam=[];for(let y=0;y<=1050;y+=5)seam.push([175+y+([0,2,-2,1,-1][(y/5)%5]),y]);
   const polygon=seam.map(([x,y])=>x+'px '+y+'px').join(',');
   await composition.setContent(`<style>body{margin:0}img{position:absolute;inset:0;width:1400px;height:1050px}.dark{clip-path:polygon(0 0,${polygon},0 1050px)}svg{position:absolute;inset:0}</style><img src="data:image/png;base64,${light}"><img class="dark" src="data:image/png;base64,${dark}"><svg width="1400" height="1050"><polyline points="${seam.map(p=>p.join(',')).join(' ')}" fill="none" stroke="#f7f7f7" stroke-width="4"/></svg>`);
   await composition.evaluate(()=>Promise.all([...document.images].map(image=>image.decode())));
   await composition.screenshot({path:path.join(output,'dashboard-card.png')});
   await composition.close();
   assert.deepEqual(errors,[]);await page.close();console.log('PASS captured native UI in',language);
  }
 }finally{await browser.close();server.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
