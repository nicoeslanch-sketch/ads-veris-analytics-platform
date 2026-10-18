"""Real PostgreSQL/PostgREST security tests. Refuses non-loopback databases."""

import argparse
import base64
import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import threading
import time
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'api'))


def loopback(url):
    parsed = urlsplit(url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Only disposable loopback infrastructure is permitted")
    return parsed


class SecurityLab:
    def __init__(self, status):
        self.base = status["API_URL"].rstrip("/")
        loopback(self.base)
        db = loopback(status["DB_URL"])
        self.env = {**os.environ, "PGHOST": db.hostname, "PGPORT": str(db.port or 5432),
                    "PGUSER": unquote(db.username or ""), "PGPASSWORD": unquote(db.password or ""),
                    "PGDATABASE": unquote(db.path.lstrip("/")), "PGCONNECT_TIMEOUT": "5",
                    "PGOPTIONS": "-c statement_timeout=10000"}
        self.headers = {"apikey": status["SERVICE_ROLE_KEY"],
                        "Authorization": "Bearer " + status["SERVICE_ROLE_KEY"]}
        self.anon_key = status['ANON_KEY']
        self.http = httpx.Client(timeout=20, trust_env=False)
        self.checks = {}

    def sql(self, query):
        result = subprocess.run(["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", query],
                                env=self.env, capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise AssertionError("Local SQL failed: " + result.stderr[:1500])
        return result.stdout.strip()

    def rpc(self, name, payload, expected=200):
        r = self.http.post(self.base + "/rest/v1/rpc/" + name, headers=self.headers, json=payload)
        assert r.status_code == expected, (name, r.status_code, r.text[:500])
        return r.json()

    def concurrent(self, fn, count=8):
        with ThreadPoolExecutor(max_workers=count) as executor:
            return list(executor.map(fn, range(count)))

    def account(self, plan="basico", admin=False):
        uid = str(uuid4())
        self.sql(f"insert into auth.users (id,email,raw_user_meta_data) values "
                 f"('{uid}','{uid}@example.invalid','{{}}'); "
                 f"update public.profiles set plan='{plan}', is_admin={'true' if admin else 'false'} where id='{uid}';")
        return uid

    def reserve(self, uid, kind="summary", limit=2):
        return self.rpc("reserve_ai_quota", {"p_user_id": uid, "p_reservation_id": str(uuid4()),
                        "p_kind": kind, "p_limits": {"basico": limit, "analista": limit, "gold": limit}})

    def synthetic_session(self, uid):
        sid = str(uuid4())
        self.sql(f"insert into auth.sessions(id,user_id,created_at,updated_at) "
                 f"values('{sid}','{uid}',now(),now());")
        return sid

    def test_mfa(self):
        # All credentials are synthetic, short-lived and never included in the report.
        email, password = f'{uuid4()}@example.invalid', f'Lab-{uuid4()}!'
        r = self.http.post(self.base + '/auth/v1/admin/users', headers=self.headers,
                           json={'email': email, 'password': password, 'email_confirm': True})
        assert r.status_code in (200, 201), ('create synthetic account', r.status_code)
        uid = r.json()['id']
        r = self.http.post(self.base + '/auth/v1/token?grant_type=password', headers={'apikey': self.anon_key},
                           json={'email': email, 'password': password})
        assert r.status_code == 200, ('synthetic sign in', r.status_code)
        aal1 = {'apikey': self.anon_key, 'Authorization': 'Bearer ' + r.json()['access_token']}
        def profile(headers):
            r = self.http.get(self.base + '/rest/v1/profiles', headers=headers,
                              params={'id': 'eq.' + uid, 'select': 'id'})
            assert r.status_code == 200, ('profile query', r.status_code)
            return r.json()
        assert profile(aal1) == [{'id': uid}]
        r = self.http.post(self.base + '/auth/v1/factors', headers=aal1,
                           json={'factor_type': 'totp', 'friendly_name': 'Synthetic lab'})
        assert r.status_code == 200, ('synthetic enrollment', r.status_code)
        factor, secret = r.json()['id'], r.json()['totp']['secret']
        assert profile(aal1) == [{'id': uid}], 'An unverified factor must not lock out a customer'
        challenge_url = self.base + '/auth/v1/factors/' + factor + '/challenge'
        verify_url = self.base + '/auth/v1/factors/' + factor + '/verify'
        r = self.http.post(challenge_url, headers=aal1, json={})
        assert r.status_code == 200, ('challenge', r.status_code)
        rejected = self.http.post(verify_url, headers=aal1, json={'challenge_id': r.json()['id'], 'code': 'invalid'})
        assert rejected.status_code in (400, 422), ('invalid code', rejected.status_code)
        r = self.http.post(challenge_url, headers=aal1, json={})
        assert r.status_code == 200, ('fresh challenge', r.status_code)
        digest = hmac.new(base64.b32decode(secret), struct.pack('>Q', int(time.time()) // 30), hashlib.sha1).digest()
        offset = digest[-1] & 15
        code = f'{(struct.unpack(">I", digest[offset:offset+4])[0] & 0x7fffffff) % 1000000:06d}'
        r = self.http.post(verify_url, headers=aal1, json={'challenge_id': r.json()['id'], 'code': code})
        assert r.status_code == 200, ('TOTP verification', r.status_code)
        aal2 = {'apikey': self.anon_key, 'Authorization': 'Bearer ' + r.json()['access_token']}
        assert profile(aal1) == []
        assert profile(aal2) == [{'id': uid}]
        r = self.http.get(self.base + '/rest/v1/profiles', headers=aal2, params={'select': 'id'})
        assert r.status_code == 200 and r.json() == [{'id': uid}]
        self.checks['real_totp_enrollment_wrong_code_aal1_denial_aal2_ownership'] = True
        context = self.rpc('session_security_context', {'p_user_id': uid})
        assert context == {'is_admin': False, 'has_mfa': True}
        # A valid signature is insufficient after logout, even for an AAL2 token.
        token_payload = aal2['Authorization'].split(' ')[1].split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(token_payload + '=' * (-len(token_payload) % 4)))
        payload = {'p_user_id': uid, 'p_session_id': claims['session_id']}
        assert self.rpc('verified_session_context', payload)['session_active'] is True
        assert self.rpc('verified_session_context', {**payload, 'p_user_id': self.account()})['session_active'] is False
        object_url = self.base + '/storage/v1/object/datasets/' + uid + '/session-test.csv'
        object_content = b'id,amount\n1,10\n'
        r = self.http.post(object_url, headers={**self.headers, 'Content-Type': 'text/csv'}, content=object_content)
        assert r.status_code in (200, 201), ('synthetic storage upload', r.status_code)
        r = self.http.get(object_url, headers=aal2)
        assert r.status_code == 200 and r.content == object_content, ('active storage access', r.status_code)
        for headers in (aal1, aal2, {'apikey': self.anon_key}):
            r = self.http.post(self.base + '/rest/v1/rpc/session_security_context', headers=headers,
                               json={'p_user_id': uid})
            assert r.status_code in (401, 403), ('private MFA lookup', r.status_code)
            r = self.http.post(self.base + '/rest/v1/rpc/verified_session_context', headers=headers, json=payload)
            assert r.status_code in (401, 403), ('private session lookup', r.status_code)
        self.checks['mfa_context_rpc_not_public'] = True
        r = self.http.post(self.base + '/auth/v1/logout?scope=global', headers=aal2)
        assert r.status_code in (200, 204), ('synthetic logout', r.status_code)
        assert self.rpc('verified_session_context', payload)['session_active'] is False
        assert profile(aal2) == [], 'A revoked AAL2 token must lose direct data access immediately'
        assert profile(aal1) == []
        r = self.http.get(object_url, headers=aal2)
        assert r.status_code in (400, 401, 403, 404) and r.content != object_content, ('revoked storage access', r.status_code)
        r = self.http.request('DELETE', self.base + '/storage/v1/object/datasets', headers=self.headers,
                             json={'prefixes': [uid + '/session-test.csv']})
        assert r.status_code in (200, 204), ('synthetic storage cleanup', r.status_code)
        self.checks['real_global_logout_denies_unexpired_aal1_and_aal2_tokens'] = True
        self.checks['real_storage_download_denied_after_global_logout'] = True
        admin = self.account(admin=True)
        admin_sid = self.synthetic_session(admin)
        result = self.sql(f"begin; set local role authenticated; "
                         f"select set_config('request.jwt.claims','{{\"sub\":\"{admin}\",\"session_id\":\"{admin_sid}\",\"aal\":\"aal1\"}}',true); "
                         f"select count(*) from public.profiles where id='{admin}'; rollback;")
        assert '\n0\n' in result
        self.checks['admin_without_factor_has_no_direct_data_access'] = True
        missing = self.sql("select count(*) from pg_tables t where schemaname='public' and rowsecurity "
                           "and not exists (select 1 from pg_policies p where p.schemaname=t.schemaname "
                           "and p.tablename=t.tablename and p.policyname='account_mfa_guard' and p.permissive='RESTRICTIVE');")
        assert missing == '0', 'New RLS tables must also include the MFA guard'
        assert self.sql("select count(*) from pg_policies where schemaname='storage' and tablename='objects' "
                        "and policyname='account_mfa_guard' and permissive='RESTRICTIVE'") == '1'
        self.checks['all_public_rls_tables_and_storage_have_restrictive_mfa_guard'] = True

    def test_session_lifecycle(self):
        r = self.http.post(self.base + '/auth/v1/admin/users', headers=self.headers,
            json={'email': f'{uuid4()}@example.invalid', 'email_confirm': True})
        assert r.status_code in (200, 201), ('create lifecycle account', r.status_code)
        uid = r.json()['id']
        sid = self.synthetic_session(uid)
        payload = {'p_user_id': uid, 'p_session_id': sid}
        assert self.rpc('verified_session_context', payload)['session_active'] is True
        def visible(session_id):
            result = self.sql(f"begin; set local role authenticated; select set_config('request.jwt.claims',"
                f"'{{\"sub\":\"{uid}\",\"session_id\":\"{session_id}\",\"aal\":\"aal2\"}}',true); "
                f"select count(*) from public.profiles where id='{uid}'; rollback;")
            return '\n1\n' in result
        assert visible(sid)
        assert not visible('invalid')
        assert not visible('')
        self.sql(f"update auth.sessions set not_after=now()-interval '1 second' where id='{sid}'")
        assert not self.rpc('verified_session_context', payload)['session_active']
        assert not visible(sid)
        self.sql(f"update auth.sessions set not_after=null where id='{sid}'; "
                 f"update auth.users set banned_until=now()+interval '1 day' where id='{uid}'")
        assert not self.rpc('verified_session_context', payload)['session_active']
        assert not visible(sid)
        self.sql(f"update auth.users set banned_until=null where id='{uid}'")
        assert visible(sid)
        self.sql(f"update auth.users set deleted_at=now() where id='{uid}'")
        assert not self.rpc('verified_session_context', payload)['session_active']
        assert not visible(sid)
        self.sql(f"update auth.users set deleted_at=null where id='{uid}'")
        r = self.http.delete(self.base + '/auth/v1/admin/users/' + uid, headers=self.headers)
        assert r.status_code == 200, ('synthetic account deletion', r.status_code)
        assert not self.rpc('verified_session_context', payload)['session_active']
        assert not visible(sid)
        self.checks['expired_banned_deleted_and_malformed_sessions_fail_closed'] = True

    def test_account_limits(self):
        bucket = hashlib.sha256(str(uuid4()).encode()).hexdigest()
        limits = self.concurrent(lambda _: self.rpc('consume_request_budget', {
            'p_bucket_hash': bucket, 'p_limit': 5, 'p_window_seconds': 600}), 16)
        assert sum(r['allowed'] for r in limits) == 5
        assert all(1 <= r['retry_after'] <= 600 for r in limits if not r['allowed'])
        self.checks['distributed_account_budget_five_of_sixteen'] = True
        uid = self.account()
        requests = self.concurrent(lambda i: self.rpc('create_support_request_guarded', {
            'p_user_id': uid, 'p_message': f'Synthetic request {i}', 'p_page': '/lab'}))
        assert sum(r['created'] for r in requests) == 3
        uid = self.account()
        requests = self.concurrent(lambda i: self.rpc('create_support_request_guarded', {
            'p_user_id': uid, 'p_message': 'Same synthetic request', 'p_page': '/lab'}))
        assert sum(r['created'] for r in requests) == 1
        self.checks['support_pending_limit_and_duplicate_atomic_under_concurrency'] = True
        for function in ['consume_request_budget(text,integer,integer)', 'create_support_request_guarded(uuid,text,text)']:
            for role in ['anon', 'authenticated']:
                assert self.sql(f"select has_function_privilege('{role}','public.{function}','execute')") == 'f'
        self.checks['request_budget_and_support_rpc_service_only'] = True

    def test_privacy(self):
        owner, foreign, admin = self.account(), self.account(), self.account(admin=True)
        assert not self.rpc('account_privacy_state', {'p_user_id': owner})['accepted']
        accepted = self.rpc('accept_account_legal', {'p_user_id': owner, 'p_version': '2026-09-28'})
        assert accepted['accepted']
        original_time = self.sql(f"select accepted_at from public.legal_acceptances where user_id='{owner}'")
        self.rpc('accept_account_legal', {'p_user_id': owner, 'p_version': '2026-09-28'})
        assert self.sql(f"select accepted_at from public.legal_acceptances where user_id='{owner}'") == original_time
        self.rpc('accept_account_legal', {'p_user_id': foreign, 'p_version': 'old'}, expected=400)
        requests = self.concurrent(lambda _: self.rpc('create_privacy_request', {
            'p_user_id': owner, 'p_kind': 'erasure', 'p_message': 'Synthetic erasure request'}), 8)
        rid = requests[0]['id']
        assert all(r['id'] == rid and r['status'] == 'pending' for r in requests)
        assert self.rpc('account_privacy_state', {'p_user_id': foreign})['requests'] == []
        assert self.sql(f"select count(*) from auth.users where id='{owner}'") == '1'
        self.rpc('admin_privacy_requests', {'p_admin_id': foreign}, expected=403)
        self.rpc('resolve_privacy_request', {'p_admin_id': foreign, 'p_request_id': rid,
            'p_status': 'resolved', 'p_response': 'Unauthorized answer'}, expected=403)
        self.rpc('resolve_privacy_request', {'p_admin_id': admin, 'p_request_id': rid,
            'p_status': 'reviewing', 'p_response': 'Synthetic request acknowledged'})
        assert self.sql(f"select count(*) from public.admin_audit where detail->>'request_id'='{rid}'") == '1'
        foreign_sid = self.synthetic_session(foreign)
        owner_sid = self.synthetic_session(owner)
        visible = self.sql(f"begin; set local role authenticated; select set_config('request.jwt.claims',"
            f"'{{\"sub\":\"{foreign}\",\"session_id\":\"{foreign_sid}\",\"aal\":\"aal1\"}}',true); "
            f"select count(*) from public.privacy_requests where id='{rid}'; rollback;")
        assert '\n0\n' in visible
        visible = self.sql(f"begin; set local role authenticated; select set_config('request.jwt.claims',"
            f"'{{\"sub\":\"{owner}\",\"session_id\":\"{owner_sid}\",\"aal\":\"aal1\"}}',true); "
            f"select count(*) from public.privacy_requests where id='{rid}'; rollback;")
        assert '\n1\n' in visible
        for table in ('privacy_requests', 'legal_acceptances'):
            assert self.sql(f"select has_table_privilege('authenticated','public.{table}','insert')") == 'f'
            assert self.sql(f"select has_table_privilege('authenticated','public.{table}','update')") == 'f'
        for func in ('account_privacy_state(uuid)', 'accept_account_legal(uuid,text)',
                     'create_privacy_request(uuid,text,text)', 'admin_privacy_requests(uuid)',
                     'resolve_privacy_request(uuid,uuid,text,text)'):
            for role in ('anon', 'authenticated'):
                assert self.sql(f"select has_function_privilege('{role}','public.{func}','execute')") == 'f'
        uid = str(uuid4())
        self.sql(f"insert into auth.users(id, raw_user_meta_data) values ('{uid}',"
                 "'{\"legal_version\":\"2026-09-28\",\"service_data_consent\":true}');")
        assert self.rpc('account_privacy_state', {'p_user_id': uid})['accepted']
        self.sql(f"update auth.users set raw_user_meta_data='{{\"legal_version\":\"2026-09-28\","
                 f"\"service_data_consent\":true}}' where id='{foreign}';")
        assert not self.rpc('account_privacy_state', {'p_user_id': foreign})['accepted']
        self.checks['privacy_isolation_concurrent_idempotency_server_evidence_and_admin_audit'] = True

    def run(self):
        assert self.sql("select count(*) from auth.users") == "0", "Refusing populated database"
        owner, foreign, admin = self.account(), self.account(), self.account(admin=True)
        own_dataset, foreign_dataset, source = (str(uuid4()) for _ in range(3))
        self.sql(f"insert into public.datasets(id,user_id,name) values "
                 f"('{own_dataset}','{owner}','own.csv'),('{foreign_dataset}','{foreign}','foreign.csv'); "
                 f"insert into public.google_sheet_sources(id,user_id,dataset_id,source_url,sheet_id,display_name) "
                 f"values('{source}','{owner}','{own_dataset}','https://docs.google.com','synthetic','test');")
        r = self.http.patch(self.base + "/rest/v1/google_sheet_sources", headers=self.headers,
                            params={"id": "eq." + source}, json={"dataset_id": foreign_dataset})
        assert r.status_code == 409 and r.json()["code"] == "23503", r.text
        self.checks["cross_owner_link_rejected_even_with_service_role"] = True
        self.sql(f"delete from public.datasets where id='{own_dataset}';")
        assert self.sql(f"select dataset_id is null and user_id='{owner}' from public.google_sheet_sources where id='{source}'") == "t"
        self.checks["deleting_dataset_detaches_source_without_deleting_owner"] = True
        owner_sid = self.synthetic_session(owner)
        visible = self.sql(f"begin; set local role authenticated; "
                           f"select set_config('request.jwt.claims','{{\"sub\":\"{owner}\",\"session_id\":\"{owner_sid}\",\"role\":\"authenticated\"}}',true); "
                           f"select count(*) from public.datasets where id='{foreign_dataset}'; rollback;")
        assert "\n0\n" in visible
        self.checks["dataset_rls_isolates_accounts"] = True
        functions = ["reserve_ai_quota(uuid,uuid,text,jsonb)", "settle_ai_quota(uuid,uuid,boolean)",
                     "admin_commercial_operation(uuid,uuid,uuid,text,jsonb)",
                     "adjust_ads_coins(uuid,bigint,text,text,jsonb)", "ensure_monthly_ads_allowance(uuid)",
                     "admin_support_operation(uuid,uuid,uuid,text,text)"]
        for func in functions:
            for role in ("anon", "authenticated"):
                assert self.sql(f"select has_function_privilege('{role}','public.{func}','execute')") == "f"
        self.checks["privileged_rpcs_not_callable_by_clients"] = True
        reservations = self.concurrent(lambda _: self.reserve(owner))
        allowed = [r for r in reservations if r["allowed"]]
        assert len(allowed) == 2
        self.checks["monthly_quota_two_slots_eight_concurrent_requests"] = True
        self.rpc("reserve_ai_quota", {"p_user_id": owner, "p_reservation_id": allowed[0]["reservation_id"],
                                     "p_kind": "summary", "p_limits": {"basico": 2}}, expected=409)
        self.rpc("settle_ai_quota", {"p_user_id": owner, "p_reservation_id": allowed[0]["reservation_id"],
                                    "p_success": False}, expected=400)
        self.checks["replay_and_ambiguous_provider_refund_rejected"] = True
        burst = self.concurrent(lambda _: self.reserve(admin, limit=1000), count=16)
        assert sum(r["allowed"] for r in burst) == 12
        self.checks["distributed_burst_twelve_of_sixteen_including_admin"] = True
        cleaner = self.account("analista")
        self.sql(f"insert into public.plan_addons(user_id,credits) values('{cleaner}',1);")
        clean = self.concurrent(lambda _: self.reserve(cleaner, "cleaning", 1))
        clean_ok = [r for r in clean if r["allowed"]]
        assert len(clean_ok) == 2 and sum(r["consume_addon"] for r in clean_ok) == 1
        assert self.rpc("cleaning_addons_balance", {"p_user_id": cleaner}) == 0
        addon = next(r for r in clean_ok if r["consume_addon"])
        for _ in range(2):
            self.rpc("settle_ai_quota", {"p_user_id": cleaner, "p_reservation_id": addon["reservation_id"], "p_success": False})
        assert self.rpc("cleaning_addons_balance", {"p_user_id": cleaner}) == 1
        self.checks["cleaning_addon_atomic_reservation_and_single_refund"] = True
        op = {"p_admin_id": owner, "p_operation_id": str(uuid4()), "p_target_user_id": foreign,
              "p_action": "set_plan", "p_payload": {"plan": "gold"}}
        self.rpc("admin_commercial_operation", op, expected=403)
        self.checks["non_admin_actor_rejected_by_database"] = True
        op.update(p_admin_id=admin, p_action="grant_credits", p_payload={"credits": 3, "note": "lab"})
        grants = self.concurrent(lambda _: self.rpc("admin_commercial_operation", op))
        assert all(g["saldo"] == 3 for g in grants)
        assert self.rpc("cleaning_addons_balance", {"p_user_id": foreign}) == 3
        assert self.sql(f"select count(*) from public.admin_audit where operation_id='{op['p_operation_id']}'") == "1"
        self.checks["admin_grant_and_audit_idempotent_under_concurrency"] = True
        self.sql("create function app_private.lab_reject_audit() returns trigger language plpgsql "
                 "as $$ begin raise exception 'injected audit failure'; end $$; "
                 "create trigger lab_reject_audit before insert on public.admin_audit "
                 "for each row execute function app_private.lab_reject_audit();")
        for action, payload in [("set_plan", {"plan": "gold"}), ("grant_credits", {"credits": 5}),
                                ("grant_ads_coins", {"amount": 10})]:
            self.rpc("admin_commercial_operation", {**op, "p_operation_id": str(uuid4()),
                     "p_action": action, "p_payload": payload}, expected=400)
        assert self.sql(f"select plan from public.profiles where id='{foreign}'") == "basico"
        assert self.rpc("cleaning_addons_balance", {"p_user_id": foreign}) == 3
        assert self.sql(f"select count(*) from public.ads_coin_transactions where user_id='{foreign}'") == "0"
        conversation = str(uuid4())
        self.sql(f"insert into public.support_conversations(id,user_id) values('{conversation}','{foreign}');")
        for action in ("support_chat_reply", "support_chat_closed"):
            self.rpc("admin_support_operation", {"p_admin_id": admin, "p_operation_id": str(uuid4()),
                "p_resource_id": conversation, "p_action": action, "p_message": "Synthetic reply"}, expected=400)
        assert self.sql(f"select count(*) from public.support_messages where conversation_id='{conversation}'") == "0"
        assert self.sql(f"select status from public.support_conversations where id='{conversation}'") == "open"
        self.checks["support_reply_and_close_roll_back_if_audit_fails"] = True
        self.sql("drop trigger lab_reject_audit on public.admin_audit; drop function app_private.lab_reject_audit();")
        self.checks["audit_failure_rolls_back_plan_credits_and_coins"] = True
        coin = {"p_user_id": foreign, "p_amount": 10, "p_reason": "lab", "p_reference_key": str(uuid4()), "p_metadata": {}}
        coin_results = self.concurrent(lambda _: self.rpc("adjust_ads_coins", coin))
        assert sum(r[0]["applied"] for r in coin_results) == 1
        self.checks["coin_ledger_replay_concurrency"] = True
        for plan in ["basico", "analista", "basico", "analista"]:
            self.sql(f"update public.profiles set plan='{plan}' where id='{owner}';")
            self.concurrent(lambda _: self.rpc("ensure_monthly_ads_allowance", {"p_user_id": owner}))
        assert self.sql(f"select balance from public.ads_coin_wallets where user_id='{owner}'") == "500"
        self.checks["plan_upgrade_only_grants_difference_and_downgrade_no_regrant"] = True
        reply = {"p_admin_id": admin, "p_operation_id": str(uuid4()), "p_resource_id": conversation,
                 "p_action": "support_chat_reply", "p_message": "Synthetic reply"}
        self.concurrent(lambda _: self.rpc("admin_support_operation", reply))
        assert self.sql(f"select count(*) from public.support_messages where conversation_id='{conversation}'") == "1"
        self.checks["support_reply_idempotent"] = True
        for privilege in ("update", "delete", "truncate"):
            assert self.sql(f"select has_table_privilege('service_role','public.admin_audit','{privilege}')") == "f"
        self.checks["backend_cannot_rewrite_audit_history"] = True
        self.test_mfa()
        self.test_session_lifecycle()
        self.test_account_limits()
        self.test_privacy()
        self.test_operational_health()
        self.test_maintenance()
        self.test_initial_import_queue()
        self.test_concurrent_restore_snapshots()
        self.test_account_erasure_recovery()

    def test_concurrent_restore_snapshots(self):
        owner, foreign = self.account(), self.account()
        # One unique arbiter, still enforced by the original primary key.
        assert self.sql("select count(*) from pg_index where indrelid="
                        "'public.dataset_restore_states'::regclass and indisunique") == '1'
        assert self.sql("select count(*) from pg_constraint where conrelid="
                        "'public.dataset_restore_states'::regclass and contype='p' "
                        "and pg_get_constraintdef(oid)='PRIMARY KEY (dataset_id)'") == '1'
        sheets = [f'Sheet_{i}' for i in range(8)]
        for version in (1, 2):
            function = 'store_restore_snapshot_guarded' + ('_v2' if version == 2 else '')
            signature = 'uuid,uuid,text,jsonb,bigint,text,text,text,text,text,jsonb,jsonb,boolean,text'
            if version == 2:
                signature += ',jsonb,jsonb,jsonb'
            for role in ('anon', 'authenticated'):
                assert self.sql(f"select has_function_privilege('{role}',"
                                f"'public.{function}({signature})','execute')") == 'f'
            for _ in range(8):
                dataset = str(uuid4())
                self.sql(f"insert into public.datasets(id,user_id,name) "
                         f"values('{dataset}','{owner}','concurrent.xlsx');")
                revision = self.rpc('reserve_restore_snapshot_revision',
                                    {'p_dataset_id': dataset, 'p_user_id': owner})
                def payload(index, current_revision=revision):
                    snapshot = {'revision': current_revision, 'source_sha256': 'a' * 64,
                                'rules_hash': 'b' * 16, 'mapping_hash': 'c' * 16,
                                'sheet': sheets[index], 'engine_version': 'concurrency-lab'}
                    data = {f'p_{key}': value for key, value in snapshot.items()}
                    data.update(p_dataset_id=dataset, p_user_id=owner, p_sheet_key=sheets[index],
                                p_snapshot=snapshot, p_active_sheet=sheets[0],
                                p_available_sheets=sheets, p_excluded_sheets=[], p_combine_sheets=False)
                    if version == 2:
                        data.update(p_selected_sheets=sheets, p_sheet_errors={}, p_analysis_scope={})
                    return data
                barrier = threading.Barrier(len(sheets))
                def write(index):
                    barrier.wait(timeout=10)
                    return self.rpc(function, payload(index))
                assert self.concurrent(write, count=len(sheets)) == [True] * len(sheets)
                assert self.sql(f"select count(*) from public.dataset_sheet_snapshots "
                                f"where dataset_id='{dataset}' and user_id='{owner}' "
                                f"and revision={revision}") == str(len(sheets))
                newer = self.rpc('reserve_restore_snapshot_revision',
                                 {'p_dataset_id': dataset, 'p_user_id': owner})
                assert self.rpc(function, payload(0, newer)) is True
                assert self.rpc(function, payload(1)) is False
                self.rpc(function, {**payload(1, newer), 'p_user_id': foreign}, expected=400)
                assert self.sql(f"select revision from public.dataset_restore_states "
                                f"where dataset_id='{dataset}' and user_id='{owner}'") == str(newer)
        self.checks['parallel_first_sheet_snapshots_v1_v2_128_writes'] = True
        self.checks['snapshot_owner_revision_and_private_rpc_guards_preserved'] = True

    def test_account_erasure_recovery(self):
        # Exercise the real orchestrator against disposable Auth, Storage and DB.
        # The only mocked step is process-local cache eviction; its ordering and
        # failures are covered by unit tests and it carries no remote state here.
        from fastapi import HTTPException
        from app import account_erasure
        from app.config import Settings

        admin, foreign = self.account(admin=True), self.account()
        created = self.http.post(self.base + '/auth/v1/admin/users', headers=self.headers,
            json={'email': f'{uuid4()}@example.invalid', 'password': f'Lab-{uuid4()}!',
                  'email_confirm': True})
        assert created.status_code in (200, 201), ('create erasure account', created.status_code)
        owner = created.json()['id']
        sid = self.synthetic_session(owner)
        request = self.rpc('create_privacy_request', {'p_user_id': owner, 'p_kind': 'erasure',
            'p_message': 'Synthetic end-to-end erasure'})
        rid = request['id']
        owner_path, foreign_path = owner + '/owner.csv', foreign + '/foreign.csv'
        for path, content in ((owner_path, b'owner,data\n1,secret\n'), (foreign_path, b'foreign,data\n1,safe\n')):
            uploaded = self.http.post(self.base + '/storage/v1/object/datasets/' + path,
                headers={**self.headers, 'Content-Type': 'text/csv'}, content=content)
            assert uploaded.status_code in (200, 201), ('synthetic erasure upload', uploaded.status_code)
        owner_dataset, foreign_dataset = str(uuid4()), str(uuid4())
        self.sql(f"insert into public.datasets(id,user_id,name,storage_path) values "
            f"('{owner_dataset}','{owner}','owner.csv','{owner_path}'),"
            f"('{foreign_dataset}','{foreign}','foreign.csv','{foreign_path}');")
        assert self.rpc('verified_session_context', {'p_user_id': owner, 'p_session_id': sid})['session_active']

        settings = Settings(_env_file=None, supabase_url=self.base,
            supabase_service_role_key=self.headers['apikey'], supabase_storage_bucket='datasets')
        # Admission itself invalidates active sessions and closes new writes.
        account_erasure._control(admin, rid, 'prepare', settings)
        assert not self.rpc('verified_session_context', {'p_user_id': owner, 'p_session_id': sid})['session_active']
        denied = self.http.post(self.base + '/rest/v1/rpc/reserve_storage_capacity', headers=self.headers,
            json={'p_user_id': owner, 'p_path': owner + '/late.csv', 'p_bytes': 10, 'p_kind': 'source'})
        assert denied.status_code in (400, 401, 403), ('late write must fail closed', denied.status_code)

        original_control = account_erasure._control
        original_purge = account_erasure._purge_runtime
        faulted = False
        def fail_after_auth(admin_id, request_id, action, current_settings, payload=None):
            nonlocal faulted
            if action == 'complete' and not faulted:
                faulted = True
                raise RuntimeError('Synthetic post-Auth outage')
            return original_control(admin_id, request_id, action, current_settings, payload)
        account_erasure._control = fail_after_auth
        account_erasure._purge_runtime = lambda *_args: None
        try:
            try:
                account_erasure.execute_account_erasure(admin, rid, settings)
                raise AssertionError('Injected post-Auth outage was not raised')
            except HTTPException as exc:
                assert exc.status_code == 502
            assert self.sql(f"select count(*) from auth.users where id='{owner}'") == '0'
            assert self.sql(f"select status from app_private.account_erasure_jobs where request_id='{rid}'") == 'failed'
            account_erasure._control = original_control
            completed = account_erasure.execute_account_erasure(admin, rid, settings)
            assert completed['status'] == 'completed'
        finally:
            account_erasure._control = original_control
            account_erasure._purge_runtime = original_purge

        assert self.sql(f"select status || ':' || coalesce(target_user_id::text,'none') "
                        f"from app_private.account_erasure_jobs where request_id='{rid}'") == 'completed:none'
        digest = hashlib.sha256(owner.encode()).hexdigest()
        assert self.sql(f"select count(*) from app_private.erasure_tombstones "
                        f"where subject_digest='{digest}'") == '1'
        assert self.sql(f"select count(*) from public.admin_audit where target_user_id='{owner}'") == '0'
        assert int(self.sql(f"select count(*) from public.admin_audit where action like 'account_erasure_%' "
                            f"and detail->>'request_id'='{rid}' and target_user_id is null")) >= 2
        assert self.sql(f"select count(*) from public.datasets where user_id='{owner}'") == '0'
        assert self.sql(f"select count(*) from public.datasets where id='{foreign_dataset}'") == '1'
        owner_object = self.http.get(self.base + '/storage/v1/object/datasets/' + owner_path, headers=self.headers)
        foreign_object = self.http.get(self.base + '/storage/v1/object/datasets/' + foreign_path, headers=self.headers)
        assert owner_object.status_code in (400, 404) and owner_object.content != b'owner,data\n1,secret\n'
        assert foreign_object.status_code == 200 and foreign_object.content == b'foreign,data\n1,safe\n'
        receipts = self.rpc('admin_account_erasures', {'p_admin_id': admin})
        assert any(j['request_id'] == rid and j['status'] == 'completed' for j in receipts)
        self.checks['account_erasure_real_auth_storage_db_retry_and_tenant_isolation'] = True
        self.checks['erasure_tombstone_is_pii_free_and_audit_subject_is_scrubbed'] = True

    def test_initial_import_queue(self):
        owner, foreign = self.account(), self.account()
        dataset, identifier = str(uuid4()), 'dq_' + uuid4().hex
        path = owner + '/initial.csv'
        upload = self.http.post(self.base + '/storage/v1/object/datasets/' + path,
                                headers={**self.headers, 'Content-Type': 'text/csv'}, content=b'Value\n1\n')
        assert upload.status_code in (200, 201), upload.text
        self.sql(f"insert into public.datasets(id,user_id,name,storage_path) "
                 f"values('{dataset}','{owner}','initial.csv','{path}');")
        payload = {'dataset_id': dataset, 'source_path': path, 'engine_version': 'queue-lab',
                   'kind': 'standardize', 'options': {'revision': 1, 'sheet': None}}
        args = {'p_action': 'enqueue', 'p_user_id': owner, 'p_job_id': identifier, 'p_payload': payload}
        queued = self.rpc('analysis_queue', args)
        assert queued['status'] == 'queued' and queued['kind'] == 'standardize'
        assert self.rpc('analysis_queue', {**args, 'p_user_id': foreign})['rejected'] == 404
        assert self.rpc('analysis_queue', {'p_action': 'get', 'p_user_id': foreign, 'p_job_id': identifier}) is None
        cancelled = self.rpc('analysis_queue', {'p_action': 'cancel', 'p_user_id': owner, 'p_job_id': identifier})
        assert cancelled['status'] == 'cancelled'
        for role in ('anon', 'authenticated'):
            assert self.sql(f"select has_function_privilege('{role}', "
                            "'public.analysis_queue(text,uuid,text,jsonb,uuid)','execute')") == 'f'
        self.checks['initial_import_queue_admits_new_kind_and_isolates_owners'] = True
        identifier = 'dq_' + uuid4().hex
        payload.update(kind='relationships', engine_version='connections-queue-lab',
                       options={'manifest': {'hojas': [{'nombre': 'Ventas', 'procesar': True}]},
                                'focus': {'sheets': ['Ventas']}, 'relationship': None})
        args.update(p_job_id=identifier, p_payload=payload)
        queued = self.rpc('analysis_queue', args)
        assert queued['status'] == 'queued' and queued['kind'] == 'relationships'
        assert self.rpc('analysis_queue', args)['job_id'] == identifier
        assert self.rpc('analysis_queue', {**args, 'p_user_id': foreign})['rejected'] == 404
        for action in ('get', 'cancel', 'retry'):
            assert self.rpc('analysis_queue', {'p_action': action, 'p_user_id': foreign,
                                               'p_job_id': identifier}) is None
        claimed = self.rpc('analysis_queue', {'p_action': 'claim',
                                              'p_payload': {'engine_version': 'connections-queue-lab'}})
        assert claimed['job_id'] == identifier and claimed['status'] == 'running'
        completed = self.rpc('analysis_queue', {'p_action': 'finish', 'p_user_id': owner,
                             'p_job_id': identifier, 'p_token': claimed['lease_token'],
                             'p_payload': {'status': 'completed', 'result': {'safe_count': 0, 'candidates': []}}})
        assert completed['status'] == 'completed'
        assert self.rpc('analysis_queue', args)['result'] == {'safe_count': 0, 'candidates': []}
        self.checks['business_connections_queue_recovers_result_and_isolates_owners'] = True

    def test_maintenance(self):
        functions = ('retention_guard(text,uuid,uuid)',
                     'retention_journal_operation(text,uuid,uuid,text,text,text,text)',
                     'operational_notification(text,text,text[],text,uuid,bigint,boolean)',
                     'retention_schedule_operation(text,uuid,jsonb)')
        tables = ('retention_guards', 'retention_journal', 'operational_notifications', 'retention_schedule')
        for role in ('anon', 'authenticated'):
            for fn in functions:
                assert self.sql(f"select has_function_privilege('{role}','public.{fn}','execute')") == 'f'
            for table in tables:
                assert self.sql(f"select has_table_privilege('{role}','app_private.{table}','select')") == 'f'
        owner, other = self.account(), self.account()
        claims = self.concurrent(lambda _: self.rpc('retention_guard', {'p_action': 'claim', 'p_user_id': owner}))
        assert len([c for c in claims if c]) == 1
        lease = next(c for c in claims if c)
        assert self.rpc('retention_guard', {'p_action': 'renew', 'p_user_id': other, 'p_lease': lease}) is None
        assert self.rpc('retention_guard', {'p_action': 'renew', 'p_user_id': owner, 'p_lease': lease}) == lease
        self.rpc('retention_guard', {'p_action': 'release', 'p_user_id': owner, 'p_lease': lease})
        args = dict(p_action='begin', p_user_id=owner, p_name='synthetic.csv', p_object_id='original', p_stamp='old')
        jobs = self.concurrent(lambda _: self.rpc('retention_journal_operation', args))
        assert len({j['id'] for j in jobs}) == 1
        job = jobs[0]
        assert self.rpc('retention_journal_operation', dict(p_action='list', p_user_id=other)) == []
        wrong_owner = self.http.post(self.base + '/rest/v1/rpc/retention_journal_operation', headers=self.headers,
            json=dict(p_action='advance', p_user_id=other, p_id=job['id'], p_stage='cancelled'))
        assert wrong_owner.status_code >= 400
        self.rpc('retention_journal_operation', {**args, 'p_name': '../other.csv'}, expected=400)
        self.rpc('retention_journal_operation', dict(p_action='advance', p_user_id=owner, p_id=job['id'], p_stage='cancelled'))
        assert self.rpc('retention_journal_operation', args)['stage'] == 'pending'
        self.checks['retention_journal_private_owner_scoped_idempotent_and_leased'] = True

        destination = hashlib.sha256(b'synthetic-local-destination').hexdigest()
        def notify(action, **kw):
            return self.rpc('operational_notification', dict(p_action=action, p_destination=destination, **kw))
        notify('sync', p_codes=['HTTP_ERRORS'])
        self.concurrent(lambda _: notify('sync', p_codes=['HTTP_ERRORS']))
        claims = self.concurrent(lambda _: notify('claim'))
        assert len([c for c in claims if c]) == 1
        item = next(c for c in claims if c)
        assert item['revision'] == 1
        notify('sync', p_codes=[])
        assert not notify('ack', p_code=item['code'], p_lease=item['lease'], p_revision=1, p_success=True)['acknowledged']
        resolved = notify('claim')
        assert not resolved['active'] and resolved['revision'] == 2
        assert notify('ack', p_code=resolved['code'], p_lease=resolved['lease'], p_revision=2, p_success=False)['acknowledged']
        assert notify('claim') is None
        self.sql(f"update app_private.operational_notifications set next_attempt=now()-interval '1 minute' where destination='{destination}'")
        retry = notify('claim')
        assert retry['revision'] == 2 and retry['lease'] != resolved['lease']
        notify('ack', p_code=retry['code'], p_lease=retry['lease'], p_revision=2, p_success=True)
        assert notify('claim') is None
        self.checks['notifications_coalesce_lease_fence_and_retry_without_duplicate_claims'] = True

        terminal = self.rpc('retention_journal_operation', {**args, 'p_name': 'finished.csv'})
        self.sql(f"update app_private.retention_journal set stage='completed',updated_at=now()-interval '31 days' where id='{terminal['id']}'; "
                 f"update app_private.retention_journal set updated_at=now()-interval '31 days' where id='{job['id']}'")
        self.sql('update app_private.retention_schedule set cursor_user=null,next_scan=now()')
        scans = self.concurrent(lambda _: self.rpc('retention_schedule_operation', {'p_action': 'claim'}))
        assert len([s for s in scans if s]) == 1
        scan = next(s for s in scans if s)
        assert len(scan['users']) <= 5
        assert self.sql(f"select count(*) from app_private.retention_journal where id='{terminal['id']}'") == '0'
        assert self.sql(f"select count(*) from app_private.retention_journal where id='{job['id']}'") == '1'
        report = dict(mode='audit', accounts=1, candidates=1, deleted=0, errors=0)
        assert not self.rpc('retention_schedule_operation', dict(p_action='complete', p_lease=str(uuid4()), p_report=report))['acknowledged']
        self.rpc('retention_schedule_operation', dict(p_action='complete', p_lease=scan['lease'], p_report={**report, 'file': 'private.csv'}), expected=400)
        assert self.rpc('retention_schedule_operation', dict(p_action='complete', p_lease=scan['lease'], p_report=report))['acknowledged']
        status = self.rpc('retention_schedule_operation', {'p_action': 'status'})
        assert set(status) == {'completed_at', 'report'} and status['report'] == report
        self.checks['retention_schedule_global_bounded_and_aggregate_only'] = True

        # Exercise the actual Storage delete response and recovery journal, not mocks.
        from app.config import Settings
        from app.routes.retention import _retention_sync
        uid = self.account()
        for name in ('recent.csv', 'expired.csv'):
            path = uid + '/' + name
            upload = self.http.post(self.base + '/storage/v1/object/datasets/' + path,
                headers={**self.headers, 'Content-Type': 'text/csv'}, content=b'ID,Amount\n1,10\n')
            assert upload.status_code == 200
            self.sql(f"insert into public.datasets(id,user_id,name,storage_path) values('{uuid4()}','{uid}','{name}','{path}')")
        self.sql(f"begin; set local session_replication_role=replica; "
                 f"update storage.objects set created_at=now()-interval '100 days',updated_at=now()-interval '100 days',"
                 f"last_accessed_at=now()-interval '100 days' where name='{uid}/expired.csv'; commit;")
        settings = Settings(_env_file=None, supabase_url=self.base, supabase_service_role_key=self.headers['apikey'], storage_keep_last=1)
        assert _retention_sync(uid, settings, dry_run=True)['candidatos'] == 1
        assert _retention_sync(uid, settings)['eliminados'] == 1
        assert self.sql(f"select count(*) from storage.objects where name='{uid}/expired.csv'") == '0'
        assert self.sql(f"select count(*) from public.datasets where user_id='{uid}' and name='expired.csv' and storage_path is null") == '1'
        assert _retention_sync(uid, settings)['eliminados'] == 0
        self.checks['retention_real_storage_expiry_preserves_history_and_recent_file'] = True

    def test_operational_health(self):
        signature = 'public.operational_health(text,uuid,jsonb)'
        for role in ('anon', 'authenticated'):
            assert self.sql(f"select has_function_privilege('{role}','{signature}','execute')") == 'f'
            assert self.sql(f"select has_table_privilege('{role}','app_private.operational_samples','select')") == 'f'
        instance = str(uuid4())
        data = self.rpc('operational_health', {'p_action': 'heartbeat', 'p_instance_id': instance,
            'p_sample': {'requests': 20, 'errors': 5, 'limited': 1, 'slow': 2}})
        assert data['http']['instances'] == 1 and data['http']['errors'] == 5
        assert set(data) == {'sampled_at', 'http', 'queue', 'storage'}
        assert data['storage']['limit_bytes'] > 0 and data['queue']['max_active'] > 0
        self.rpc('operational_health', {'p_action': 'heartbeat', 'p_instance_id': instance,
            'p_sample': {'requests': 1, 'errors': 2, 'limited': 0, 'slow': 0}}, expected=400)
        self.sql(f"update app_private.operational_samples set updated_at=now()-interval '3 minutes' where instance_id='{instance}';")
        assert self.rpc('operational_health', {})['http']['instances'] == 0
        self.checks['operational_counters_private_bounded_and_staleness_detected'] = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lab = SecurityLab(json.loads(args.status_file.read_text(encoding="utf-8-sig")))
    report = {"commit_sha": os.environ.get("GITHUB_SHA", "local"), "scope": "ephemeral loopback Supabase",
              "production_requests": 0, "customer_files": 0, "checks": lab.checks, "passed": False}
    try:
        lab.run()
        report["passed"] = True
    finally:
        lab.http.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
