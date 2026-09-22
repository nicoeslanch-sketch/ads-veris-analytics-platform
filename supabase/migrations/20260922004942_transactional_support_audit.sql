begin;

create or replace function public.admin_support_operation(
  p_admin_id uuid, p_operation_id uuid, p_resource_id uuid, p_action text, p_message text default ''
) returns jsonb
language plpgsql security invoker set search_path = '' as $$
declare
  allowed boolean;
  previous public.admin_audit%rowtype;
  owner_id uuid;
  current_status text;
  fingerprint jsonb;
  result jsonb;
begin
  if p_operation_id is null or p_resource_id is null or p_action is null
     or p_action not in ('support_chat_reply','support_chat_closed','support_attended','addon_attended')
     or p_message is null or length(p_message) > 4000 then
    raise exception using errcode='22023', message='invalid_support_operation';
  end if;
  select is_admin into allowed from public.profiles where id=p_admin_id for share;
  if allowed is distinct from true then raise exception using errcode='42501', message='admin_required'; end if;
  fingerprint := jsonb_build_object('resource_id',p_resource_id,
    'message_hash',encode(sha256(convert_to(p_message,'UTF8')),'hex'));
  perform pg_advisory_xact_lock(hashtextextended('admin:' || p_admin_id::text || ':' || p_operation_id::text,0));
  select * into previous from public.admin_audit where admin_id=p_admin_id and operation_id=p_operation_id;
  if found then
    if previous.action <> p_action or previous.detail -> 'payload' <> fingerprint then
      raise exception using errcode='22023', message='admin_operation_conflict';
    end if;
    return previous.detail -> 'result';
  end if;
  if p_action in ('support_chat_reply','support_chat_closed') then
    select user_id,status into owner_id,current_status from public.support_conversations where id=p_resource_id for update;
    if not found then raise exception using errcode='P0002', message='conversation_not_found'; end if;
    if p_action='support_chat_reply' then
      if current_status <> 'open' or length(btrim(p_message))=0 then
        raise exception using errcode='22023', message='conversation_not_open_or_empty_message';
      end if;
      insert into public.support_messages(conversation_id,sender_id,sender_role,body)
        values(p_resource_id,p_admin_id,'admin',btrim(p_message));
      result := jsonb_build_object('ok',true,'status','open');
    else
      if current_status <> 'closed' then
        insert into public.support_messages(conversation_id,sender_id,sender_role,body)
          values(p_resource_id,p_admin_id,'system','Conversacion cerrada por soporte ADS Veris.');
        update public.support_conversations set status='closed',closed_at=now(),closed_by=p_admin_id where id=p_resource_id;
      end if;
      result := jsonb_build_object('ok',true,'status','closed');
    end if;
  elsif p_action='support_attended' then
    if length(p_message)>2000 then raise exception using errcode='22023', message='invalid_reply'; end if;
    update public.support_requests set status='atendida',attended_at=now(),
      respuesta=case when btrim(p_message)='' then respuesta else btrim(p_message) end
      where id=p_resource_id returning user_id into owner_id;
    if not found then raise exception using errcode='P0002', message='request_not_found'; end if;
    result := jsonb_build_object('ok',true,'id',p_resource_id,'status','atendida');
  else
    update public.addon_requests set status='atendida' where id=p_resource_id returning user_id into owner_id;
    if not found then raise exception using errcode='P0002', message='request_not_found'; end if;
    result := jsonb_build_object('ok',true,'id',p_resource_id,'status','atendida');
  end if;
  -- Retain action evidence, not chat bodies beyond their 24h retention policy.
  insert into public.admin_audit(admin_id,target_user_id,action,operation_id,detail)
    values(p_admin_id,owner_id,p_action,p_operation_id,jsonb_build_object('payload',fingerprint,'result',result));
  return result;
end;
$$;
revoke all on function public.admin_support_operation(uuid,uuid,uuid,text,text) from public,anon,authenticated;
grant execute on function public.admin_support_operation(uuid,uuid,uuid,text,text) to service_role;
revoke update,delete,truncate on public.admin_audit from service_role;
revoke update,delete,truncate on public.ads_coin_transactions from service_role;

commit;
