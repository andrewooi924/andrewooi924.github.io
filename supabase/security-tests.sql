set role authenticated;
set request.jwt.claim.sub='11111111-1111-1111-1111-111111111111';
select public.mw_save_list('local-1','collection','Secret collection','[{"id":"op01_1","quantity":2,"note":"SECRET","pricePaid":123}]',0);
do $$ begin
 if jsonb_array_length(public.mw_lists()) <> 1 then raise exception 'Owner cannot read list'; end if;
 begin
  perform public.mw_save_list('local-1','collection','Stale','[]',0);
  raise exception 'Stale revision accepted';
 exception when serialization_failure then null; end;
 begin
  perform public.mw_save_list('bad','collection','Bad','[{"id":"x","quantity":-1}]',0);
  raise exception 'Invalid item accepted';
 exception when invalid_parameter_value then null; end;
 begin
  perform public.mw_save_list('bad','collection','Bad','[{"id":"x","quantity":null}]',0);
  raise exception 'Null quantity accepted';
 exception when invalid_parameter_value then null; end;
 perform public.mw_share_list((public.mw_lists()->0->>'id')::uuid,'0123456789abcdef0123456789abcdef');
end $$;
set request.jwt.claim.sub='22222222-2222-2222-2222-222222222222';
do $$ begin
 if public.mw_lists() <> '[]'::jsonb then raise exception 'Cross-account read'; end if;
 if public.mw_delete_list('00000000-0000-0000-0000-000000000000') then raise exception 'Deleted other list';end if;
 begin
  perform 1 from private.lists;
  raise exception 'Direct private table access';
 exception when insufficient_privilege then null;end;
end $$;
reset role;
set role anon;
set request.jwt.claim.sub='';
do $$ declare result jsonb;begin
 result:=public.mw_shared_list('0123456789abcdef0123456789abcdef');
 if result is null or result->>'title'<>'Secret collection' then raise exception 'Share unavailable';end if;
 if result::text like '%SECRET%' or result::text like '%pricePaid%' or result::text like '%owner_id%' then raise exception 'Private fields leaked';end if;
 if public.mw_shared_list('bad') is not null then raise exception 'Invalid token accepted';end if;
 begin perform public.mw_lists();raise exception 'Anonymous list enumeration';exception when insufficient_privilege then null;end;
end $$;
reset role;
set role authenticated;
set request.jwt.claim.sub='11111111-1111-1111-1111-111111111111';
select public.mw_share_list((public.mw_lists()->0->>'id')::uuid,null);
reset role;
set role anon;
set request.jwt.claim.sub='';
do $$ begin
 if public.mw_shared_list('0123456789abcdef0123456789abcdef') is not null then raise exception 'Revocation failed';end if;
end $$;
reset role;
