import {collectionHistory} from './valuation.js';
import { createClient } from '@supabase/supabase-js';
const cfg=window.MW_CONFIG||{};
const api=(cfg.apiUrl||'').replace(/\/$/,'');
const ready=Boolean(api&&cfg.supabaseUrl&&cfg.supabasePublishableKey);
const auth=ready?createClient(cfg.supabaseUrl,cfg.supabasePublishableKey,{auth:{flowType:'pkce',persistSession:true,detectSessionInUrl:true}}):null;
let session=null, rows=[], loadedFor=null, dialog;
const element=(tag,text,cls)=>{const e=document.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e;};
async function request(path,options={}){
  const headers=new Headers(options.headers);
  if(options.body)headers.set('content-type','application/json');
  if(path.startsWith('/v1/me/')){
    const result=await auth?.auth.getSession();
    const token=result?.data.session?.access_token;
    if(!token)throw Error('Sign in first.');
    headers.set('authorization','Bearer '+token);
  }
  const r=await fetch(api+path,{...options,headers,cache:'no-store',signal:AbortSignal.timeout(15000)});
  const data=await r.json(); if(!r.ok)throw Error(data.error||'Request failed');return data;
}
function message(text){dialog.querySelector('[role=status]').textContent=text;}
function action(label,fn){const b=element('button',label,'cloud-action');b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){message(e.message);}finally{b.disabled=false;}};return b;}
async function load(){
  if(!session){rows=[];loadedFor=null;return;}
  const owner=session.user.id;
  const next=await request('/v1/me/lists');
  if(session?.user.id!==owner)return;
  rows=next;loadedFor=owner;
}
async function save(){
  if(loadedFor!==session?.user.id)throw Error('Load your account lists first.');
  const local=await window.MWBridge.exportCurrent();
  const old=rows.find(r=>r.localId===local.localId&&r.kind===local.kind);
  await request('/v1/me/lists',{method:'PUT',body:JSON.stringify({...local,revision:old?.revision||0})});
  await load(); render();message('Saved to your account. Save again after local edits to update the cloud and shared view.');
}
function render(){
  const content=dialog.querySelector('.cloud-content');content.replaceChildren();
  if(!ready){content.append(element('p','Cloud features are not connected yet. Your lists continue to be saved on this device.'));return;}
  if(!session){
    content.append(element('p','Sign in by email to save private cloud copies and create revocable links. Local lists stay on this device until you choose to save them.'));
    const email=element('input');email.type='email';email.autocomplete='email';email.placeholder='Email address';email.required=true;
    email.setAttribute('aria-label','Email address');content.append(email);
    content.append(action('Send sign-in link',async()=>{
      if(!email.validity.valid||!email.value.trim())throw Error('Enter a valid email address.');
      const redirect=new URL(location.href);redirect.hash='';redirect.search='';
      const {error}=await auth.auth.signInWithOtp({email:email.value.trim(),options:{emailRedirectTo:redirect.href,shouldCreateUser:true}});
      if(error)throw error;
      message('Check your email for the sign-in link.');
    }));return;
  }
  content.append(element('p','Signed in as '+(session.user.email||'your account')));
  content.append(action('Save current wishlist / collection',save));
  content.append(action('Refresh cloud copies',async()=>{await load();render();message('Cloud copies refreshed.');}));
  content.append(element('p','Cloud copies update when you save. Downloading creates a new local copy; it never replaces existing local data.','cloud-hint'));
  for(const row of rows){
    const card=element('section',null,'cloud-list');
    card.append(element('strong',row.title),element('small',`${row.kind} · ${row.items.length} entries · revision ${row.revision}`));
    card.append(action('Download a local copy',async()=>{await window.MWBridge.importList(row);message('Downloaded as a new local copy.');}));
    card.append(action(row.shared?'Replace share link':'Create share link',async()=>{
      if(row.shared&&!confirm('Replace this link? The previous link will stop working.'))return;
      const bytes=crypto.getRandomValues(new Uint8Array(16));const token=Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
      await request(`/v1/me/lists/${row.id}/share`,{method:'PUT',body:JSON.stringify({token})});
      await load();render();
      const url=new URL(location.href);url.search='';url.hash='share='+token;
      const input=element('input');input.readOnly=true;input.value=url.href;input.setAttribute('aria-label','Share link');
      dialog.querySelector('.cloud-content').prepend(input);input.select();
      message('Anyone with this link can view card identities and quantities. Costs and notes remain private. Copy the selected link.');
    }));
    if(row.shared)card.append(action('Revoke sharing',async()=>{await request(`/v1/me/lists/${row.id}/share`,{method:'PUT',body:JSON.stringify({token:null})});await load();render();message('Sharing revoked.');}));
    card.append(action('Delete cloud copy',async()=>{if(!confirm('Delete this cloud copy and revoke its link? Local copies remain.'))return;await request(`/v1/me/lists/${row.id}`,{method:'DELETE'});await load();render();message('Cloud copy deleted.');}));
    content.append(card);
  }
  content.append(action('Sign out',async()=>{const {error}=await auth.auth.signOut({scope:'local'});if(error)throw error;session=null;rows=[];loadedFor=null;render();message('Signed out. Downloaded local copies remain on this device.');}));
}
async function open(){
  if(!dialog){
    dialog=element('dialog',null,'cloud-dialog');dialog.setAttribute('aria-labelledby','cloud-title');
    const title=element('h2','Account & sharing');title.id='cloud-title';
    const close=action('Close',()=>dialog.close());
    const status=element('p');status.setAttribute('role','status');
    dialog.append(title,element('div',null,'cloud-content'),status,close);document.body.append(dialog);
  }
  dialog.showModal();render();
  if(auth){try{const {data,error}=await auth.auth.getSession();if(error)throw error;session=data.session;await load();render();}catch(e){message(e.message);}}
}
if(auth)auth.auth.onAuthStateChange((_event,next)=>{if(session?.user.id!==next?.user.id){rows=[];loadedFor=null;}session=next;if(dialog?.open)render();});
let histories=null,historyFetchedAt=0;
async function showHistory(container,items){
  container.replaceChildren(element('p','Loading observed price history…'));
  try{
    if(!api)throw Error('Connect the catalog API to collect daily price history.');
    if(!histories||Date.now()-historyFetchedAt>300000){histories=await request('/v1/price-history');historyFetchedAt=Date.now();}
    const points=collectionHistory(items,histories),complete=points.filter(p=>p.complete);
    container.replaceChildren(element('p',"Today’s holdings at historical retail prices (JPY). Quantities are held constant; purchases and sales are not investment returns."));
    if(!complete.length){container.append(element('p','No dates have observed prices for every card in this collection yet. Missing prices are never counted as zero.'));return;}
    const latest=complete.at(-1);
    container.append(element('p',`${latest.date}: ¥${latest.value.toLocaleString()} · ${complete.length} complete observed days`));
    if(complete.length<2){container.append(element('p','The chart will appear after another complete daily observation.'));return;}
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
    svg.setAttribute('viewBox','0 0 600 180');svg.setAttribute('role','img');svg.setAttribute('aria-label','Observed value of current holdings over time, with gaps on missing days');svg.style.width='100%';
    const min=Math.min(...complete.map(p=>p.value)),max=Math.max(...complete.map(p=>p.value)),span=max-min||1;
    const first=Date.parse(complete[0].date),last=Date.parse(latest.date),duration=last-first||1;
    let segment=[];
    const draw=()=>{if(!segment.length)return;const line=document.createElementNS(ns,'polyline');line.setAttribute('points',segment.join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','currentColor');line.setAttribute('stroke-width','3');svg.append(line);segment=[];};
    let previous=null;
    for(const p of points){if(!p.complete){draw();previous=null;continue;}const time=Date.parse(p.date);if(previous!==null&&time-previous>86400000)draw();
      const x=15+570*(time-first)/duration,y=165-150*(p.value-min)/span;
      segment.push(`${x},${y}`);const dot=document.createElementNS(ns,'circle');dot.setAttribute('cx',String(x));dot.setAttribute('cy',String(y));dot.setAttribute('r','3');dot.setAttribute('fill','currentColor');svg.append(dot);previous=time;}
    draw();container.append(svg);
    const change=latest.value-complete[0].value;
    container.append(element('p',`${complete[0].date} → ${latest.date}: ${change>=0?'+':'−'}¥${Math.abs(change).toLocaleString()} change in retail estimate`));
    const details=element('details'),summary=element('summary','Daily values');details.append(summary);
    for(const p of points)details.append(element('div',`${p.date}: ${p.complete?'¥'+p.value.toLocaleString():`Incomplete (${p.priced}/${items.length} priced)`}`));container.append(details);
  }catch(e){container.replaceChildren(element('p',e.message));}
}
window.MWCloud={open,showHistory,enabled:Boolean(api),
  async catalog(){if(!api)return null;return request('/v1/catalog');},
  async shared(token){if(!api)throw Error('Sharing is not connected on this installation.');return request('/v1/shared/'+encodeURIComponent(token));},
  async history(id){if(!api)return [];return request('/v1/variants/'+encodeURIComponent(id)+'/price-history');}
};
