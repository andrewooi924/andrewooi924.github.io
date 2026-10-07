import test from 'node:test';
import assert from 'node:assert/strict';
import {handle, type Env} from '../src/index.ts';
function env(overrides:Partial<Env>={}):Env {return {ALLOWED_ORIGINS:'https://app.example',SUPABASE_URL:'https://project.supabase.co',SUPABASE_PUBLISHABLE_KEY:'publishable-test',DATA:{get:async()=>null} as unknown as R2Bucket,ASSETS:{get:async()=>null} as unknown as R2Bucket,...overrides};}
test('rejects hostile origins before any database request',async()=>{
 const r=await handle(new Request('https://api.example/v1/me/lists',{headers:{origin:'https://evil.example'}}),env());assert.equal(r.status,403);assert.equal(r.headers.get('access-control-allow-origin'),null);
});
test('requires bearer token for all personal routes',async()=>{
 const r=await handle(new Request('https://api.example/v1/me/lists'),env());assert.equal(r.status,401);assert.equal(r.headers.get('cache-control'),'no-store');
});
test('passes user JWT to Supabase without a privileged key',async()=>{
 const old=globalThis.fetch;let seen=false;
 globalThis.fetch=(async(_url,options)=>{const h=options?.headers as Record<string,string>;assert.equal(h.authorization,'Bearer user.jwt.token');assert.equal(h.apikey,'publishable-test');seen=true;return Response.json([]);}) as typeof fetch;
 try{const r=await handle(new Request('https://api.example/v1/me/lists',{headers:{authorization:'Bearer user.jwt.token'}}),env());assert.equal(r.status,200);assert.equal(r.headers.get('cache-control'),'no-store');assert.ok(seen);}finally{globalThis.fetch=old;}
});
test('rejects oversized writes before contacting Supabase',async()=>{
 const r=await handle(new Request('https://api.example/v1/me/lists',{method:'PUT',headers:{authorization:'Bearer x','content-type':'application/json'},body:JSON.stringify({data:'x'.repeat(1_000_000)})}),env());assert.equal(r.status,413);
});
test('rejects malformed share keys and never caches shared data',async()=>{
 const r=await handle(new Request('https://api.example/v1/shared/short'),env());assert.equal(r.status,404);assert.equal(r.headers.get('cache-control'),'no-store');
});
test('rate limits unauthenticated callers too',async()=>{
 const r=await handle(new Request('https://api.example/health'),env({RATE_LIMITER:{limit:async()=>({success:false})}}));assert.equal(r.status,429);
});
test('serves pinned snapshot with data version, never arbitrary R2 keys',async()=>{
 const keys:string[]=[];const data={get:async(key:string)=>{keys.push(key);return key==='published.json'?{json:async()=>({version:'a'.repeat(24)})}:key.endsWith('/catalog.json')?{json:async()=>[{id:'op01_10151',variantId:'canonical-1'}]}:{json:async()=>({op01_10151:[{price:100}]})};}} as unknown as R2Bucket;
 const r=await handle(new Request('https://api.example/v1/variants/op01_10151/offers'),env({DATA:data}));assert.equal(r.status,200);assert.equal(r.headers.get('x-data-version'),'a'.repeat(24));assert.equal(keys[1],`snapshots/${'a'.repeat(24)}/catalog.json`);assert.equal(keys[2],`snapshots/${'a'.repeat(24)}/offers.json`);
 assert.deepEqual(await r.json(),[{price:100}]);
 const alias=await handle(new Request('https://api.example/v1/variants/canonical-1'),env({DATA:data}));assert.equal(alias.status,200);
 const bad=await handle(new Request('https://api.example/v1/archives/secret'),env({DATA:data}));assert.equal(bad.status,404);
});
test('serves only content-addressed artwork from the private assets bucket',async()=>{
 const keys:string[]=[];const assets={get:async(key:string)=>{keys.push(key);return {body:'webp-bytes',httpEtag:'"image-hash"'};}} as unknown as R2Bucket;
 const hash='a'.repeat(64);
 const ok=await handle(new Request(`https://api.example/v1/images/${hash}/thumb.webp`),env({ASSETS:assets}));
 assert.equal(ok.status,200);assert.equal(ok.headers.get('content-type'),'image/webp');
 assert.equal(keys[0],`cards/${hash}/thumb.webp`);
 const bad=await handle(new Request('https://api.example/v1/images/../../private.txt'),env({ASSETS:assets}));
 assert.equal(bad.status,404);assert.equal(keys.length,1);
});
test('revision conflicts are distinct from service failures',async()=>{
 const old=globalThis.fetch;globalThis.fetch=(async()=>Response.json({code:'40001'},{status:409})) as typeof fetch;
 try{const r=await handle(new Request('https://api.example/v1/me/lists',{method:'PUT',headers:{authorization:'Bearer x','content-type':'application/json'},body:'{}'}),env());assert.equal(r.status,409);}finally{globalThis.fetch=old;}
});
