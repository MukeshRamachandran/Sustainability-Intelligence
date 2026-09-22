from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_ready_succeeds_when_dependencies_are_ready(client: TestClient) -> None:
    with patch("app.routers.health.database_is_ready", return_value=True):
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ready", "evidence": "ready"}


def test_ready_fails_safely_when_database_is_unavailable(client: TestClient) -> None:
    with patch("app.routers.health.database_is_ready", return_value=False):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unavailable",
        "evidence": "ready",
    }
    for forbidden in ("postgresql", "password", "traceback", "exception", "evidence_root"):
        assert forbidden not in response.text.lower()


def test_ready_fails_safely_when_evidence_root_is_missing(client: TestClient, tmp_path: Path) -> None:
    client.app.state.settings.EVIDENCE_ROOT = tmp_path / "missing"
    with patch("app.routers.health.database_is_ready", return_value=True):
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["evidence"] == "unavailable"
    assert str(tmp_path) not in response.text
