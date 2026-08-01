from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.consolidation.repository import MEMORY_REPOSITORY


def _settings(enabled: bool) -> Settings:
    return Settings(
        consolidation_enabled=enabled,
        consolidation_admin_only=True,
        dev_auth_bypass=True,
        supabase_url="",
        supabase_service_role_key="",
        supabase_jwt_secret="",
    )


def setup_function():
    MEMORY_REPOSITORY.projects.clear()
    MEMORY_REPOSITORY.runs.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_feature_flag_off_rejects_domain():
    app.dependency_overrides[get_settings] = lambda: _settings(False)
    response = TestClient(app).post("/consolidation/projects", json={"name": "Prueba"})
    assert response.status_code == 404


def test_admin_local_can_create_and_read_project_when_flag_on():
    app.dependency_overrides[get_settings] = lambda: _settings(True)
    client = TestClient(app)
    created = client.post("/consolidation/projects", json={"name": "Prueba"})
    assert created.status_code == 200
    project = created.json()
    assert project["status"] == "draft"
    assert project["config"]["template"] == "general"
    assert project["config"]["target_columns"] == []
    read = client.get(f"/consolidation/projects/{project['id']}")
    assert read.status_code == 200


def test_demre_template_keeps_92_column_contract():
    app.dependency_overrides[get_settings] = lambda: _settings(True)
    response = TestClient(app).post(
        "/consolidation/projects",
        json={"name": "Admisión", "template": "demre_2026"},
    )
    assert response.status_code == 200
    assert len(response.json()["config"]["target_columns"]) == 92


def test_status_explains_backend_flag_instead_of_failing_on_create():
    app.dependency_overrides[get_settings] = lambda: _settings(False)
    response = TestClient(app).get("/consolidation/status")
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["reason"] == "backend_disabled"


def test_foreign_project_is_not_revealed():
    app.dependency_overrides[get_settings] = lambda: _settings(True)
    foreign = MEMORY_REPOSITORY.create_project("other-user", {"name": "Otro", "config": {}, "config_hash": "a" * 64, "engine_version": "x"})
    response = TestClient(app).get(f"/consolidation/projects/{foreign['id']}")
    assert response.status_code == 404


def test_general_run_requires_primary_assignment():
    app.dependency_overrides[get_settings] = lambda: _settings(True)
    client = TestClient(app)
    project = client.post("/consolidation/projects", json={"name": "Prueba"}).json()
    response = client.post(f"/consolidation/projects/{project['id']}/runs")
    assert response.status_code == 422
    assert "principal" in response.json()["detail"]


def test_memory_run_enqueue_is_idempotent():
    project = MEMORY_REPOSITORY.create_project("dev-user", {"name": "P", "config": {}, "config_hash": "a" * 64, "engine_version": "x"})
    first = MEMORY_REPOSITORY.enqueue_run(project, "b" * 64)
    second = MEMORY_REPOSITORY.enqueue_run(project, "b" * 64)
    assert first["id"] == second["id"]
