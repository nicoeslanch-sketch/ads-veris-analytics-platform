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
import time
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import httpx


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
        for headers in (aal1, aal2, {'apikey': self.anon_key}):
            r = self.http.post(self.base + '/rest/v1/rpc/session_security_context', headers=headers,
                               json={'p_user_id': uid})
            assert r.status_code in (401, 403), ('private MFA lookup', r.status_code)
        self.checks['mfa_context_rpc_not_public'] = True
        admin = self.account(admin=True)
        result = self.sql(f"begin; set local role authenticated; "
                         f"select set_config('request.jwt.claims','{{\"sub\":\"{admin}\",\"aal\":\"aal1\"}}',true); "
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
        visible = self.sql(f"begin; set local role authenticated; "
                           f"select set_config('request.jwt.claims','{{\"sub\":\"{owner}\",\"role\":\"authenticated\"}}',true); "
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
        self.test_account_limits()
        self.test_operational_health()

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
