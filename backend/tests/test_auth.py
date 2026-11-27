import base64

import pytest

from app import config


def _basic(user, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


@pytest.fixture
def protected(monkeypatch):
    monkeypatch.setattr(config, "DEMO_USER", "judge")
    monkeypatch.setattr(config, "DEMO_PASSWORD", "s3cret")


def test_open_when_no_password(client):
    assert client.get("/api/teams").status_code == 200


def test_requires_login_when_password_set(client, protected):
    r = client.get("/api/teams")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Basic")
    assert client.get("/api/teams", headers=_basic("judge", "wrong")).status_code == 401
    assert client.get("/api/teams", headers=_basic("other", "s3cret")).status_code == 401
    ok = client.get("/api/teams", headers=_basic("judge", "s3cret"))
    assert ok.status_code == 200
    assert "noindex" in ok.headers["x-robots-tag"]


def test_health_stays_open_for_the_host(client, protected):
    assert client.get("/api/health").status_code == 200


def test_malformed_header_is_rejected(client, protected):
    assert client.get("/api/teams", headers={"Authorization": "Basic !!!"}).status_code == 401
