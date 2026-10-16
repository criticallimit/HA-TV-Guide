/* Verify gallery language continuity and real translated screenshot assets. */
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const {chromium,webkit}=require('playwright');
const root=path.resolve('docs'),locales=JSON.parse(fs.readFileSync('docs/screenshots/locales.json'));
const languages=Object.keys(locales),engine=process.env.TVG_ENGINE||'chromium';
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost');let relative=decodeURIComponent(url.pathname.slice('/HA-TV-Guide/'.length));if(!relative||relative.endsWith('/'))relative+='index.html';
 const file=path.resolve(root,relative);
 if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
 const type={'.html':'text/html; charset=utf-8','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml','.webp':'image/webp'};
 res.setHeader('Content-Type',type[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base='http://127.0.0.1:'+server.address().port+'/HA-TV-Guide/';
 const browser=await({chromium,webkit}[engine]).launch({headless:true,...(process.env.TVG_BROWSER_PATH?{executablePath:process.env.TVG_BROWSER_PATH}:{})});
 const errors=[];
 try{
  const page=await browser.newPage({locale:'en-US'});page.on('pageerror',error=>errors.push(error.message));
  for(const code of languages){
   const home=code==='de'?'index.html':code+'.html';await page.goto(base+home);
   const link=page.locator('.header-right nav a[href="screenshots/'+code+'.html"]');assert.equal(await link.count(),1,code+' homepage gallery link');
   await link.click();assert.equal(await page.locator('html').getAttribute('lang'),code);assert.equal(await page.locator('h1').textContent(),locales[code].title);
   assert.equal(await page.locator('.shot').count(),4);
   for(const image of await page.locator('.shot-link img').all()){
    await image.scrollIntoViewIfNeeded();await image.evaluate(image=>image.decode());
    assert.ok((await image.getAttribute('src')).startsWith(code+'/'));
    assert.ok(await image.evaluate(image=>image.naturalWidth>=1000));
   }
   const menu=await page.locator('.language-menu a').allTextContents();assert.deepEqual(menu.map(s=>s.trim()),['Dansk','Deutsch','English','Español','Français','Italiano','Nederlands','Norsk','Polski','Svenska']);
   const back=page.locator('header .brand');assert.equal(await back.getAttribute('href'),'../'+home);await back.click();assert.equal(await page.locator('html').getAttribute('lang'),code);
   // Legacy links (including the immutable README URL) retain the latest page language.
   await page.goto(base+'screenshots.html');assert.equal(await page.locator('html').getAttribute('lang'),code);assert.ok(page.url().endsWith('/screenshots/'+code+'.html'));
   await page.setViewportSize({width:360,height:800});assert.equal(await page.locator('body').evaluate(el=>el.scrollWidth<=innerWidth),true,code+' mobile overflow');await page.setViewportSize({width:1280,height:900});
   console.log('PASS',engine,'gallery, translated images and return navigation',code);
  }
  await page.goto(base+'screenshots/en.html');await page.locator('.language summary').click();await page.locator('.language-menu a[lang="fr"]').click();assert.equal(await page.locator('html').getAttribute('lang'),'fr');
  await page.goto(base+'screenshots.html?lang=pl-PL');assert.equal(await page.locator('html').getAttribute('lang'),'pl');
  await page.goto(base+'manuals/it.html');await page.goto(base+'screenshots.html');assert.equal(await page.locator('html').getAttribute('lang'),'it');
  const norwegian=await browser.newPage({locale:'nb-NO'});await norwegian.goto(base+'screenshots.html');assert.equal(await norwegian.locator('html').getAttribute('lang'),'nb');await norwegian.close();
  const fallback=await browser.newPage({locale:'pt-BR'});await fallback.addInitScript(()=>Object.defineProperty(window,'localStorage',{get(){throw Error('Storage disabled')}}));await fallback.goto(base+'screenshots.html');assert.equal(await fallback.locator('html').getAttribute('lang'),'en');await fallback.close();
  const staticPage=await browser.newPage({javaScriptEnabled:false});await staticPage.goto(base+'screenshots/fr.html');assert.equal(await staticPage.locator('h1').textContent(),locales.fr.title);await staticPage.close();
  assert.deepEqual(errors,[]);console.log('PASS',engine,'language switch, query, manuals, browser fallback, blocked storage and no-JS galleries');
 }finally{await browser.close();server.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
