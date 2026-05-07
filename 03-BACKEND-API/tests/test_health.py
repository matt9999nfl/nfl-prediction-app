"""Tests for GET /health."""


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_shape(client):
    resp = client.get("/health")
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "commit" in data


def test_health_no_auth_required(client):
    """Health must be public — no X-API-Key needed."""
    resp = client.get("/health")
    assert resp.status_code == 200
