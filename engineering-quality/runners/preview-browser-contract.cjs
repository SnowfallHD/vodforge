// Live preview D1, real built browser JS. HeyCatch is explicitly excluded.
// Input is a disposable, unconsumed packaged-app claim receipt, never production.
const {chromium} = require('playwright');
const fs = require('node:fs');
const receiptPath = process.argv[2], output = process.argv[3];
const url = JSON.parse(fs.readFileSync(receiptPath)).events.find(e=>e.kind==='browser_requested').url;
const origin = 'https://vodforge-preview.little-mountain-f558.workers.dev';
if(new URL(url).origin!==origin) throw Error('Only the fixed preview origin is allowed');
(async()=>{
 const browser = await chromium.launch({headless:true, ...(process.platform==='win32' ? {executablePath:'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe'} : {})});
 const results = {provider:'excluded', passed:false, cases:[]};
 try {
  for(const mode of ['denied','gpc','allowed']) {
   const context = await browser.newContext();
   await context.addInitScript(mode=>{
    Object.defineProperty(navigator,'globalPrivacyControl',{get:()=>mode==='gpc'});
    Object.defineProperty(navigator,'doNotTrack',{get:()=>null});
    if(mode==='denied') localStorage.setItem('vodforge-analytics-consent-v1','denied');
   },mode);
   await context.route('**/*',r=>new URL(r.request().url()).origin===origin ? r.continue() : r.abort());
   const page=await context.newPage(); let consumes=0, payload;
   page.on('request',r=>{if(r.url().endsWith('/claim/consume')) {consumes++; payload=r.postDataJSON();}});
   const delivered = mode==='allowed' ? page.waitForResponse(r=>r.url().endsWith('/claim/consume')&&r.status()===200,{timeout:20000}) : null;
   await page.goto(url);
   if(mode==='allowed') {
    await delivered;
    if(consumes!==1) throw Error('Expected one consume');
    const same=await context.request.post(origin+'/api/attribution/claim/consume',{data:payload});
    const other=await context.request.post(origin+'/api/attribution/claim/consume',{data:{...payload,browser_id:require('node:crypto').randomUUID()}});
    if(same.status()!==200||other.status()!==404) throw Error('Replay isolation failed');
    results.cases.push({mode,consumes,same_identity_retry:same.status(),different_identity_replay:other.status()});
   } else {
    await page.waitForTimeout(2500);
    if(consumes!==0) throw Error('Denied browser attempted attribution');
    results.cases.push({mode,consumes});
   }
   await context.close();
  }
  results.passed=true;
 } catch(e) {results.error=String(e);process.exitCode=1;}
 finally {await browser.close();fs.writeFileSync(output,JSON.stringify(results,null,2));}
})();
