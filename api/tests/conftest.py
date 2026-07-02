import os
import time
from pathlib import Path

# Configurar el entorno ANTES de importar la app (Settings se cachea).
TEST_SECRET = "secreto-de-prueba-suficientemente-largo-32b"
os.environ["SUPABASE_JWT_SECRET"] = TEST_SECRET
os.environ["DEV_AUTH_BYPASS"] = "false"

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def auth_headers() -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": "user-test-123",
            "email": "test@adsveris.cl",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def sample_csv() -> tuple[str, bytes]:
    path = DATA_DIR / "ventas_ejemplo.csv"
    return path.name, path.read_bytes()
