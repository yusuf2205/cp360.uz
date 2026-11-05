import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["AI_MODE"] = "off"
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-1234"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app, bootstrap  # noqa: E402


class _Loopback:
    """Real servers always give the app a peer IP; Starlette's TestClient reports the string 'testclient' instead."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope["client"] = ("127.0.0.1", 50000)
        await self.inner(scope, receive, send)


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bootstrap()
    with TestClient(_Loopback(app)) as c:
        yield c


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture()
def admin(client):
    return login(client, "admin@example.com", "admin12345")


@pytest.fixture()
def make_user(client, admin):
    def _make(email, role, department=None):
        r = client.post("/api/users", json={"email": email, "name": email.split("@")[0] + " Тестов", "password": "password-12345", "role": role, "department": department}, headers=admin)
        assert r.status_code == 201, r.text
        return login(client, email, "password-12345")

    return _make
