"""Test fixtures: a throwaway SQLite database seeded from the repo's source files."""
import os
import sys
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_tmp, 'test.db')}")
os.environ.setdefault("AUTH_SECRET", "test-secret")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def client():
    import seed_db
    from fastapi.testclient import TestClient
    from main import app

    sys.argv = ["seed_db.py", "--reset"]
    seed_db.main()
    with TestClient(app) as c:
        yield c


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin@northeastern.edu", "econpassword123")


@pytest.fixture(scope="session")
def admin2(client):
    return _login(client, "scheduler2@northeastern.edu", "scheduler123")


@pytest.fixture(scope="session")
def faculty(client):
    return _login(client, "m.stone@northeastern.edu", "faculty123")
