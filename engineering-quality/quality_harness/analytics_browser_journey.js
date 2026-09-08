// Run through Playwright browser_run_code with a local site already running.
// All API and external traffic is intercepted: never writes production telemetry.
async function journey(page) {
  const results = [];
  for (const scenario of ['default-on', 'opt-in', 'denied', 'gpc', 'closed-tab', 'different-profile', 'retry', 'expired']) {
    const context = await page.context().browser().newContext();
    const requests = [];
    let consumeAttempts = 0;
    // Policy fixtures must not accidentally inherit Brave's default GPC.
    // Production privacy signals are never changed; these are isolated contexts.
    await context.addInitScript(({gpc})=>{
      Object.defineProperty(navigator,'globalPrivacyControl',{value:gpc});
      Object.defineProperty(navigator,'doNotTrack',{value:null});
    }, {gpc:scenario==='gpc'});
    await context.route('https://**', route => route.fulfill({status:204}));
    await context.route('**/api/**', route => {
      const url = route.request().url();
      if (url.endsWith('/analytics/policy')) return route.fulfill({json:{mode:scenario==='opt-in'?'opt-in':'default-on',resolved:true}});
      if (url.endsWith('/claim/status')) return route.fulfill({json:{ok:true,state:scenario==='expired'?'expired':'pending'}});
      if (url.endsWith('/claim/consume')) {
        requests.push(route.request().postDataJSON());
        consumeAttempts++;
        return route.fulfill({status:scenario==='retry'&&consumeAttempts===1?503:200,json:{ok:!(scenario==='retry'&&consumeAttempts===1),state:'claimed'}});
      }
      return route.fulfill({status:404});
    });
    if (scenario==='denied') await context.addInitScript(()=>localStorage.setItem('vodforge-analytics-consent-v1','denied'));
    let tab = await context.newPage();
    // Seed only the original profile; a different browser/profile intentionally
    // has no campaign or browser identity from the original download.
    if (!['different-profile','denied','gpc','expired','opt-in'].includes(scenario)) {
      await tab.goto('http://127.0.0.1:4321/?ref=journey-fixture');
      await tab.waitForTimeout(300);
      await tab.close();
      tab = await context.newPage();
    }
    if(scenario==='closed-tab') {
      await context.route('**/api/attribution/claim/status', r=>r.fulfill({json:{ok:true,state:'unknown'}}));
    }
    await tab.goto('http://127.0.0.1:4321/claim/#ticket='+'j'.repeat(43));
    await tab.waitForTimeout(400);
    const before = requests.length;
    if(scenario==='opt-in') {
      if(before!==0) throw new Error('Pre-consent identity leaked');
      await tab.locator('#analytics-allow').click();
    }
    if(scenario==='closed-tab') await tab.close();
    await page.waitForTimeout(scenario==='retry'?3500:500);
    const suppressed = ['denied','gpc','closed-tab','expired'].includes(scenario);
    if(suppressed ? requests.length!==0 : requests.length===0) throw new Error('Unexpected claim result: '+scenario);
    if(scenario==='different-profile' && requests[0].source!==null) throw new Error('Guessed cross-profile source');
    if(scenario==='default-on' && requests[0].source!=='journey-fixture') throw new Error('Lost closed-tab source');
    if(scenario==='closed-tab' && context.pages().length!==0) throw new Error('Reopened tab');
    results.push({scenario,passed:true,claimAttempts:requests.length,pages:context.pages().length,source:requests[0]?.source??null});
    await context.close();
  }
  for (const late of [true, false]) {
    const context = await page.context().browser().newContext();
    await context.addInitScript(()=>{
      Object.defineProperty(navigator,'globalPrivacyControl',{value:false});
      Object.defineProperty(navigator,'doNotTrack',{value:null});
    });
    let ready = false, consumed = 0, polls = 0;
    await context.route('https://**', r=>r.fulfill({status:204}));
    await context.route('**/api/analytics/policy', r=>r.fulfill({json:{mode:'default-on'}}));
    await context.route('**/api/attribution/claim/status', r=>{
      polls++;
      return r.fulfill({json:{state:ready?'pending':'unknown'}});
    });
    await context.route('**/api/attribution/claim/consume', r=>{
      consumed++;
      return r.fulfill({json:{ok:true,state:'claimed'}});
    });
    const tab = await context.newPage();
    await tab.clock.install();
    await tab.goto('http://127.0.0.1:4321/claim/#ticket='+'r'.repeat(43));
    for(let i=0;i<11;i++) {
      await tab.clock.runFor(10000);
      await tab.waitForTimeout(50);
    }
    ready = late;
    for(let i=0;i<15;i++) {
      await tab.clock.runFor(1000);
      await tab.waitForTimeout(100);
    }
    if(consumed!==Number(late)) throw new Error('Two-minute boundary regression: '+JSON.stringify({late,consumed,polls}));
    const finalPolls = polls;
    ready = true;
    await tab.clock.runFor(60000);
    await tab.waitForTimeout(100);
    if(polls!==finalPolls) throw new Error('Polling continued after expiry');
    results.push({scenario:late?'consent-final-ten-seconds':'two-minute-expiry',passed:true,polls,consumed});
    await context.close();
  }
  return results;
}
