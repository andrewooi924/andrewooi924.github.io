export interface Env {
  DATA: R2Bucket;
  ASSETS: R2Bucket;
  ALLOWED_ORIGINS: string;
  SUPABASE_URL: string;
  SUPABASE_PUBLISHABLE_KEY: string;
  RATE_LIMITER?: {limit(input: {key: string}): Promise<{success: boolean}>};
}
class HttpError extends Error { status: number; constructor(status: number, message: string) { super(message); this.status=status; } }
const TOKEN = /^[a-f0-9]{32}$/;
const MAX_BODY = 1_000_000;
function json(value: unknown, status=200) { return Response.json(value,{status}); }
async function body(request: Request): Promise<Record<string,unknown>> {
  if (!(request.headers.get('content-type')||'').startsWith('application/json')) throw new HttpError(415,'JSON required');
  if (Number(request.headers.get('content-length')) > MAX_BODY) throw new HttpError(413,'Request too large');
  const reader = request.body?.getReader(); if (!reader) throw new HttpError(400,'Body required');
  let size=0; const parts: Uint8Array[]=[];
  for (;;) { const {done,value}=await reader.read(); if(done) break; size+=value.length;
    if(size>MAX_BODY) { await reader.cancel(); throw new HttpError(413,'Request too large'); } parts.push(value); }
  const bytes=new Uint8Array(size); let offset=0; for(const part of parts){bytes.set(part,offset);offset+=part.length;}
  try {const parsed=JSON.parse(new TextDecoder().decode(bytes)); if(!parsed||Array.isArray(parsed)||typeof parsed!=='object') throw 0; return parsed;}
  catch {throw new HttpError(400,'Invalid JSON');}
}
async function rpc(env: Env, name: string, args: unknown, authorization?: string) {
  if (!env.SUPABASE_URL || !env.SUPABASE_PUBLISHABLE_KEY) throw new HttpError(503,'Account service is not configured');
  const headers: Record<string,string>={'apikey':env.SUPABASE_PUBLISHABLE_KEY,'content-type':'application/json'};
  if(authorization) headers.authorization=authorization;
  const response=await fetch(`${env.SUPABASE_URL.replace(/\/$/,'')}/rest/v1/rpc/${name}`,{
    method:'POST',headers,body:JSON.stringify(args),signal:AbortSignal.timeout(10000)});
  if(!response.ok){
    const error=await response.json().catch(()=>({})) as {code?:string};
    if(error.code==='40001') throw new HttpError(409,'The cloud copy changed. Download it before saving again.');
    if(response.status===401 || response.status===403) throw new HttpError(401,'Sign in again');
    if(response.status>=500) throw new HttpError(503,'Account service unavailable');
    throw new HttpError(400,'Invalid request or account limit reached');
  }
  return response.json();
}
async function publicData(path: string, env: Env) {
  const pointer=await env.DATA.get('published.json');
  if(!pointer) throw new HttpError(503,'No catalog has been published yet');
  const manifest=await pointer.json<{version:string}>();
  if(!/^[a-f0-9]{16,64}$/.test(manifest.version)) throw new HttpError(503,'Invalid catalog version');
  let key='',variantRequest: RegExpMatchArray | null=null;
  if(path==='/v1/manifest') key=`snapshots/${manifest.version}/manifest.json`;
  else if(path==='/v1/price-history') key=`snapshots/${manifest.version}/price-history.json`;
  else if(path==='/v1/catalog') key=`snapshots/${manifest.version}/catalog.json`;
  else {
    variantRequest=path.match(/^\/v1\/variants\/([A-Za-z0-9_-]{1,100})(?:\/(offers|price-history))?$/);
    if(!variantRequest) throw new HttpError(404,'Endpoint not found');
    key=`snapshots/${manifest.version}/catalog.json`;
  }
  const object=await env.DATA.get(key); if(!object) throw new HttpError(404,'Variant not found');
  if(variantRequest){
    const catalog=await object.json<Array<{id:string;variantId?:string}>>();
    const card=catalog.find(c=>c.id===variantRequest![1]||c.variantId===variantRequest![1]);
    if(!card) throw new HttpError(404,'Variant not found');
    if(!variantRequest[2]) return new Response(JSON.stringify(card),{headers:{'content-type':'application/json; charset=utf-8',
      'cache-control':'public, max-age=60','x-data-version':manifest.version}});
    const indexName=variantRequest[2]==='offers'?'offers':'history';
    const index=await env.DATA.get(`snapshots/${manifest.version}/${indexName}.json`);
    if(!index) throw new HttpError(503,'Snapshot incomplete');
    const rows=await index.json<Record<string,unknown[]>>();
    return new Response(JSON.stringify(rows[card.id]||[]),{headers:{'content-type':'application/json; charset=utf-8',
      'cache-control':'public, max-age=60','x-data-version':manifest.version}});
  }
  return new Response(object.body,{headers:{'content-type':'application/json; charset=utf-8','etag':object.httpEtag,
    'cache-control':'public, max-age=60','x-data-version':manifest.version}});
}
async function publicImage(path: string, env: Env) {
  const match=path.match(/^\/v1\/images\/([a-f0-9]{64})\/(thumb|detail)\.webp$/);
  if(!match) throw new HttpError(404,'Image not found');
  const object=await env.ASSETS.get(`cards/${match[1]}/${match[2]}.webp`);
  if(!object) throw new HttpError(404,'Image not found');
  return new Response(object.body,{headers:{'content-type':'image/webp','etag':object.httpEtag,
    'cache-control':'public, max-age=31536000, immutable'}});
}
export async function handle(request: Request, env: Env): Promise<Response> {
  const url=new URL(request.url), origin=request.headers.get('origin');
  const allowed=env.ALLOWED_ORIGINS.split(',').map(x=>x.trim());
  let result: Response;
  try {
    if(origin&&!allowed.includes(origin)) throw new HttpError(403,'Origin not allowed');
    if(request.method==='OPTIONS') result=new Response(null,{status:204});
    else {
      const ip=request.headers.get('cf-connecting-ip') || 'local';
      if(env.RATE_LIMITER && !(await env.RATE_LIMITER.limit({key:ip})).success) throw new HttpError(429,'Too many requests');
      const path=url.pathname;
      if(path==='/health'&&request.method==='GET') result=json({status:'ok',apiVersion:'v1'});
      else if(path.startsWith('/v1/me/')) {
        const auth=request.headers.get('authorization');
        if(!auth || !/^Bearer [A-Za-z0-9._-]+$/.test(auth) || auth.length>8192) throw new HttpError(401,'Sign in required');
        // Pass the user's JWT through: Supabase validates it and RPCs use auth.uid(). No service key.
        if(path==='/v1/me/lists' && request.method==='GET') result=json(await rpc(env,'mw_lists',{},auth));
        else if(path==='/v1/me/lists' && request.method==='PUT') {
          const b=await body(request);
          result=json(await rpc(env,'mw_save_list',{p_local_id:b.localId,p_kind:b.kind,p_title:b.title,p_items:b.items,p_revision:b.revision},auth));
        } else {
          const m=path.match(/^\/v1\/me\/lists\/([a-f0-9-]{36})(\/share)?$/);
          if(!m) throw new HttpError(404,'Endpoint not found');
          if(m[2] && request.method==='PUT') {
            const b=await body(request); if(b.token!==null && (typeof b.token!=='string'||!TOKEN.test(b.token))) throw new HttpError(400,'Invalid share token');
            const changed=await rpc(env,'mw_share_list',{p_id:m[1],p_token:b.token},auth);
            if(!changed) throw new HttpError(404,'List not found'); result=json({ok:true});
          } else if(!m[2] && request.method==='DELETE') {
            const changed=await rpc(env,'mw_delete_list',{p_id:m[1]},auth); if(!changed) throw new HttpError(404,'List not found');result=json({ok:true});
          } else throw new HttpError(405,'Method not allowed');
        }
      } else if(path.startsWith('/v1/shared/') && request.method==='GET') {
        const token=path.slice('/v1/shared/'.length); if(!TOKEN.test(token)) throw new HttpError(404,'List not found');
        const data=await rpc(env,'mw_shared_list',{p_token:token}); if(!data) throw new HttpError(404,'List is private, revoked, or missing'); result=json(data);
      } else if(path.startsWith('/v1/images/') && request.method==='GET') result=await publicImage(path,env);
      else if(path.startsWith('/v1/') && request.method==='GET') result=await publicData(path,env);
      else throw new HttpError(404,'Endpoint not found');
    }
  } catch(error) {result=json({error:error instanceof HttpError?error.message:'Service temporarily unavailable'},error instanceof HttpError?error.status:503);}
  const headers=new Headers(result.headers);
  // Private and shared responses must never enter browser or intermediary caches.
  if(!headers.has('cache-control')) headers.set('cache-control','no-store');
  headers.set('x-content-type-options','nosniff'); headers.set('referrer-policy','no-referrer');
  headers.set('vary','Origin');
  if(origin&&allowed.includes(origin)) headers.set('access-control-allow-origin',origin);
  headers.set('access-control-allow-methods','GET, PUT, DELETE, OPTIONS');
  headers.set('access-control-allow-headers','Authorization, Content-Type');
  headers.set('access-control-expose-headers','ETag, X-Data-Version');
  if(result.status===429) headers.set('retry-after','60');
  return new Response(result.body,{status:result.status,headers});
}
export default {fetch:handle};
