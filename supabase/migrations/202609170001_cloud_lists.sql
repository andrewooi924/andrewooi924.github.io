-- Personal data lives in an unexposed schema. Only narrow RPCs are exposed.
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
create table private.lists (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  local_id text not null check (length(local_id) between 1 and 100),
  kind text not null check (kind in ('wishlist','collection')),
  title text not null check (length(title) between 1 and 100),
  items jsonb not null default '[]',
  revision integer not null default 1,
  share_hash text unique,
  updated_at timestamptz not null default now(),
  unique(owner_id,kind,local_id),
  check (octet_length(items::text) <= 1000000)
);
alter table private.lists enable row level security;
-- Defense in depth; RPCs below additionally scope every access to auth.uid().
create policy owner_access on private.lists for all to authenticated
using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

create function private.validate_items(p_items jsonb) returns boolean
language plpgsql immutable set search_path = '' as $$
declare x jsonb;
begin
  if jsonb_typeof(p_items) <> 'array' or jsonb_array_length(p_items) > 2000 then return false; end if;
  for x in select value from jsonb_array_elements(p_items) loop
    if jsonb_typeof(x) <> 'object' or not (x ? 'id') or jsonb_typeof(x->'id') <> 'string'
      or (x->>'id') !~ '^[A-Za-z0-9_-]{1,100}$' then return false; end if;
    if exists(select 1 from jsonb_object_keys(x) k where k not in ('id','quantity','priority','note','pricePaid','obtainedAt','addedAt')) then return false; end if;
    if x ? 'quantity' and (jsonb_typeof(x->'quantity') <> 'number' or (x->>'quantity') !~ '^[0-9]+$' or (x->>'quantity')::numeric not between 1 and 999) then return false; end if;
    if x ? 'priority' and (jsonb_typeof(x->'priority') <> 'string' or x->>'priority' not in ('high','medium','low')) then return false; end if;
    if x ? 'note' and (jsonb_typeof(x->'note') <> 'string' or length(x->>'note') > 2000) then return false; end if;
    if x ? 'pricePaid' and x->'pricePaid' <> 'null'::jsonb and
      (jsonb_typeof(x->'pricePaid') <> 'number' or (x->>'pricePaid')::numeric not between 0 and 1000000000) then return false; end if;
    if x ? 'obtainedAt' and (jsonb_typeof(x->'obtainedAt') <> 'number' or (x->>'obtainedAt')::numeric not between 0 and 8640000000000000) then return false; end if;
    if x ? 'addedAt' and (jsonb_typeof(x->'addedAt') <> 'number' or (x->>'addedAt')::numeric not between 0 and 8640000000000000) then return false; end if;
  end loop;
  if (select count(*) from jsonb_array_elements(p_items)) <> (select count(distinct value->>'id') from jsonb_array_elements(p_items)) then return false; end if;
  return true;
exception when others then return false;
end $$;

create function public.mw_lists() returns jsonb
language sql stable security definer set search_path = '' as $$
 select coalesce(jsonb_agg(jsonb_build_object('id',id,'localId',local_id,'kind',kind,'title',title,'items',items,
 'revision',revision,'shared',share_hash is not null,'updatedAt',updated_at) order by updated_at desc),'[]'::jsonb)
 from private.lists where owner_id = auth.uid();
$$;

create function public.mw_save_list(p_local_id text,p_kind text,p_title text,p_items jsonb,p_revision integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare r private.lists; uid uuid := auth.uid();
begin
 if uid is null then raise exception 'Authentication required' using errcode='42501'; end if;
 if p_local_id is null or length(p_local_id) not between 1 and 100 or p_title is null or length(trim(p_title)) not between 1 and 100
 or p_kind is null or p_kind not in ('wishlist','collection') or p_revision is null or p_revision < 0
 or p_items is null or not private.validate_items(p_items) then raise exception 'Invalid list' using errcode='22023'; end if;
 -- Serialize writes for this owner, including quota checks and first-time saves.
 perform pg_advisory_xact_lock(hashtextextended(uid::text,0));
 select * into r from private.lists where owner_id=uid and kind=p_kind and local_id=p_local_id for update;
 if found then
   if r.revision <> p_revision then raise exception 'List changed on another device. Reload before saving.' using errcode='40001'; end if;
   update private.lists set title=trim(p_title),items=p_items,revision=revision+1,updated_at=now() where id=r.id returning * into r;
 else
   if p_revision <> 0 then raise exception 'List no longer exists' using errcode='40001'; end if;
   if (select count(*) from private.lists where owner_id=uid) >= 50 then raise exception 'List limit reached' using errcode='22023'; end if;
   insert into private.lists(owner_id,local_id,kind,title,items) values(uid,p_local_id,p_kind,trim(p_title),p_items) returning * into r;
 end if;
 return jsonb_build_object('id',r.id,'revision',r.revision,'updatedAt',r.updated_at);
end $$;

-- Tokens are generated with 128 bits of randomness by the client; store only a digest.
create function public.mw_share_list(p_id uuid,p_token text) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
 if auth.uid() is null then raise exception 'Authentication required' using errcode='42501'; end if;
 if p_token is not null and p_token !~ '^[0-9a-f]{32}$' then raise exception 'Invalid share token' using errcode='22023'; end if;
 update private.lists set share_hash=case when p_token is null then null else encode(sha256(convert_to(p_token,'UTF8')),'hex') end
 where id=p_id and owner_id=auth.uid();
 return found;
end $$;

create function public.mw_shared_list(p_token text) returns jsonb
language sql stable security definer set search_path = '' as $$
 select jsonb_build_object('kind',l.kind,'title',l.title,'updatedAt',l.updated_at,'items',
   coalesce((select jsonb_agg(jsonb_build_object('id',i->>'id','quantity',coalesce(i->'quantity','1'::jsonb),
     'priority',coalesce(i->>'priority','medium'))) from jsonb_array_elements(l.items) i),'[]'::jsonb))
 from private.lists l where length(p_token)=32 and l.share_hash=encode(sha256(convert_to(p_token,'UTF8')),'hex');
$$;

create function public.mw_delete_list(p_id uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
 delete from private.lists where id=p_id and owner_id=auth.uid();
 return found;
end $$;

revoke all on all functions in schema private from public,anon,authenticated;
revoke all on function public.mw_lists(), public.mw_save_list(text,text,text,jsonb,integer),
 public.mw_share_list(uuid,text), public.mw_shared_list(text),public.mw_delete_list(uuid) from public,anon,authenticated;
grant execute on function public.mw_lists(),public.mw_save_list(text,text,text,jsonb,integer),
 public.mw_share_list(uuid,text),public.mw_delete_list(uuid) to authenticated;
grant execute on function public.mw_shared_list(text) to anon,authenticated;
