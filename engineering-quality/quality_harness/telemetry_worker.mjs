// Test-only bridge. Imports the real site owner, never deploys a Worker.
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { createInterface } from "node:readline";
const site = resolve(process.argv[2]);
const require = createRequire(resolve(site, "package.json"));
const {
  Miniflare,
  Log,
  LogLevel,
  convertV4MiniflareOptions,
} = require("miniflare");
const { build } = require("esbuild");
const poolRoot = resolve(site, "node_modules/@cloudflare/vitest-pool-workers");
const poolPackage = require(resolve(poolRoot, "package.json"));
const { readD1Migrations } = await import(
  pathToFileURL(resolve(poolRoot, poolPackage.exports["."].import))
);
const source = `import {handleEnrolledTelemetry} from ${JSON.stringify(resolve(site, "src/lib/enrolled-telemetry.ts"))};
import {issueAttributionClaim} from ${JSON.stringify(resolve(site, "src/lib/attribution.ts"))};
import {recordCloudSeen,recordCloudClick,recordFirstLaunch,joinWaitlist} from ${JSON.stringify(resolve(site, "src/lib/funnel.ts"))};
import {recordProductEvents,normalizeProductEvent} from ${JSON.stringify(resolve(site, "src/lib/product-telemetry.ts"))};
export default {async fetch(request,env) {
 // Local equivalent of Cloudflare's edge-added IP header, never client authority.
 const headers=new Headers(request.headers); headers.set('CF-Connecting-IP','192.0.2.1');
 request=new Request(request,{headers});
 const action=new URL(request.url).pathname.split('/').pop();
 // Test-only entry points call production writers, not fixture INSERTs. This
 // bridge binds loopback and is never included in a deployable Worker.
 if(action==='ownership-seed') {
   const {kind,installId}=await request.json();
   const input={installId,platform:'macos',appVersion:'0.1.8'};
   if(kind==='claim') await issueAttributionClaim(env.DB,{installId,claimToken:crypto.randomUUID().replaceAll('-','')+'a'.repeat(11)});
   else if(kind==='cloud_seen') await recordCloudSeen(env.DB,input);
   else if(kind==='cloud_click') await recordCloudClick(env.DB,installId);
   else if(kind==='legacy_launch') await recordFirstLaunch(env.DB,input);
   else if(kind==='waitlist') await joinWaitlist(env.DB,{installId,email:installId+'@example.invalid'});
   else if(kind!=='fresh') return new Response('',{status:400});
   return Response.json({ok:true});
 }
 if(action==='ownership-legacy') {
   const {installId}=await request.json();
   const before=await env.DB.prepare('SELECT * FROM installations WHERE install_id=?').bind(installId).first();
   await recordCloudSeen(env.DB,{installId,platform:'windows',appVersion:'0.1.7'});
   await recordCloudClick(env.DB,installId);
   await recordFirstLaunch(env.DB,{installId,platform:'windows',appVersion:'0.1.7'});
   const event=normalizeProductEvent({install_id:installId,event_id:crypto.randomUUID(),event_name:'app_opened',occurred_at:new Date().toISOString(),app_version:'0.1.8',platform:'macos',release_channel:'production',schema_version:1});
   const accepted=await recordProductEvents(env.DB,[event]);
   const after=await env.DB.prepare('SELECT * FROM installations WHERE install_id=?').bind(installId).first();
   return Response.json({unchanged:JSON.stringify(before)===JSON.stringify(after),accepted});
 }
 if(!['enroll','launch','events','cloud_seen','cloud_click'].includes(action)) return new Response('',{status:404});
 return handleEnrolledTelemetry(request,env,action);
}};`;
const built = await build({
  stdin: { contents: source, resolveDir: site, loader: "ts" },
  bundle: true,
  write: false,
  format: "esm",
  platform: "browser",
});
const mf = new Miniflare(
  convertV4MiniflareOptions({
    modules: true,
    script: built.outputFiles[0].text,
    compatibilityDate: "2026-08-20",
    host: "127.0.0.1",
    port: 0,
    log: new Log(LogLevel.ERROR),
    d1Databases: ["DB"],
    bindings: {
      TELEMETRY_ENABLED: "true",
      INGESTION_GUARD_ENABLED: "true",
      TELEMETRY_RATE_KEY: "isolated-test-only-secret-000000000000",
    },
    ratelimits: {
      TELEMETRY_ENROLL_LIMITER: {
        namespace_id: "1001",
        simple: { limit: 120, period: 60 },
      },
      TELEMETRY_EVENT_LIMITER: {
        namespace_id: "1002",
        simple: { limit: 120, period: 60 },
      },
    },
    outboundService: () => {
      throw new Error("Harness Worker attempted outbound network");
    },
  }),
);
try {
  const db = await mf.getD1Database("DB");
  for (const migration of await readD1Migrations(resolve(site, "migrations"))) {
    await db.batch(migration.queries.map((query) => db.prepare(query)));
  }
  console.log(JSON.stringify({ url: String(await mf.ready) }));
  const lines = createInterface({ input: process.stdin });
  for await (const line of lines) {
    const { op } = JSON.parse(line);
    if (op === "stop") break;
    if (op !== "snapshot") throw new Error("Unknown harness control");
    const installations = await db
      .prepare("SELECT install_id,current_app_version,telemetry_owner,first_launched_at,last_seen_at,first_seen_at,cloud_clicked_at FROM installations")
      .all();
    const clients = await db.prepare("SELECT credential_id,install_id,revoked_at FROM telemetry_clients").all();
    const events = await db
      .prepare(
        "SELECT event_id,event_name,occurred_at,run_kind,output_type,from_version,to_version,failure_reason,failure_detail FROM product_events",
      )
      .all();
    console.log(
      JSON.stringify({
        installations: installations.results,
        clients: clients.results,
        events: events.results,
      }),
    );
  }
  lines.close();
  process.stdin.destroy();
} finally {
  await mf.dispose();
}
