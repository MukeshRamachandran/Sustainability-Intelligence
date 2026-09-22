from fastapi.testclient import TestClient


def test_application_starts(client: TestClient) -> None:
    assert client.app.title == "K-COSMOS Backend API"


def test_live_is_minimal_and_has_request_id(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]
    text = response.text.lower()
    for forbidden in ("database_url", "password", "secret", "cookie", "traceback", "evidence_root"):
        assert forbidden not in text


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "unsafe\nvalue"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] != "unsafe\nvalue"
