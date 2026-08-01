from pathlib import Path


SQL = (Path(__file__).parents[2] / "supabase" / "migrations" / "0023_general_consolidation.sql").read_text(encoding="utf-8")


def test_migration_0023_keeps_old_roles_and_adds_general_roles():
    for role in (
        "primary", "supplement_1", "equivalence_1", "historical",
        "matricula", "archivo_b", "oferta", "codebook_d",
    ):
        assert f"'{role}'" in SQL
    assert "drop constraint if exists consolidation_project_sources_role_check" in SQL.lower()
    assert "add constraint consolidation_project_sources_role_check" in SQL.lower()
