// Runs real built site JavaScript in an isolated Windows Brave process.
// Every API/external HTTPS request is intercepted by the shared scenario suite.
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const root = path.resolve(process.argv[2]);
const receipt = process.argv[3];
const scenarioFile = process.argv[4];
const types = {'.js':'application/javascript','.css':'text/css','.html':'text/html','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2'};
const server = http.createServer((req,res)=>{
  const requested = decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  let file = path.resolve(root, '.' + requested);
  if(!file.startsWith(root + path.sep) && file !== root) {res.writeHead(403).end();return;}
  if(fs.existsSync(file) && fs.statSync(file).isDirectory()) file=path.join(file,'index.html');
  if(!fs.existsSync(file)) {res.writeHead(404).end();return;}
  res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream'});
  fs.createReadStream(file).pipe(res);
});
(async()=>{
  let browser;
  const result={passed:false,evidence:'built_site_windows_brave_intercepted_api'};
  try {
    await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(4321,'127.0.0.1',resolve);});
    browser=await chromium.launch({executablePath:'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',headless:true});
    const page=await browser.newPage();
    result.native_privacy_signals=await page.evaluate(()=>({gpc:navigator.globalPrivacyControl,dnt:navigator.doNotTrack}));
    const journey = new Function(fs.readFileSync(scenarioFile,'utf8')+'\nreturn journey;')();
    result.scenarios=await journey(page);
    // Retain a real elapsed two-minute expiry check as well as virtual boundaries.
    const context=await browser.newContext();
    let polls=0,consumes=0;
    await context.route('https://**',r=>r.fulfill({status:204}));
    await context.route('**/api/**',r=>{
      if(r.request().url().endsWith('/analytics/policy')) return r.fulfill({json:{mode:'default-on',resolved:true}});
      if(r.request().url().endsWith('/claim/status')) {polls++;return r.fulfill({json:{state:'unknown'}});}
      consumes++;return r.fulfill({status:400});
    });
    const tab=await context.newPage();
    const started=Date.now();
    await tab.goto('http://127.0.0.1:4321/claim/#ticket='+'q'.repeat(43));
    await tab.waitForTimeout(125000);
    if(polls!==13||consumes!==0) throw Error(`Real expiry mismatch: ${polls}/${consumes}`);
    await tab.waitForTimeout(10000);
    if(polls!==13) throw Error('Polling resumed after deadline');
    result.real_clock={elapsed_ms:Date.now()-started,polls,consumes};
    await context.close();
    result.passed=true;
  } catch(error) {
    result.error=String(error.stack||error);process.exitCode=1;
    result.pages=[];
    if(browser) for(const context of browser.contexts()) for(const page of context.pages()) {
      result.pages.push(await page.evaluate(()=>({url:location.href,gpc:navigator.globalPrivacyControl,dnt:navigator.doNotTrack,text:document.body.innerText.slice(0,1200)})).catch(()=>({unavailable:true})));
    }
  }
  finally {
    if(browser) await browser.close();
    server.close();
    fs.writeFileSync(receipt,JSON.stringify(result,null,2));
  }
})();
