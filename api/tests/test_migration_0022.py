from pathlib import Path


SQL = (Path(__file__).parents[2] / "supabase" / "migrations" / "0022_consolidation_domain.sql").read_text(encoding="utf-8")


def test_migration_0022_is_additive_and_has_rls():
    lowered = SQL.lower()
    assert "drop table" not in lowered
    assert "truncate" not in lowered
    assert "create table if not exists public.consolidation_projects" in lowered
    assert lowered.count("enable row level security") == 5
    assert "to service_role" in lowered


def test_migration_0022_has_ownership_foreign_keys_and_idempotency():
    assert SQL.count("references auth.users(id)") >= 5
    assert "unique(user_id, idempotency_key)" in SQL
    assert "unique(run_id, kind)" in SQL
    assert "unique(storage_path)" in SQL
