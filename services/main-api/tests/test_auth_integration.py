from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.bootstrap import AccountSpec, create_account
from app.core.config import Settings
from app.main import create_app
from app.models.enums import OperationalDomain, RoleCode
from app.models.identity import SessionRecord, User
from app.security.tokens import token_hash
from tests.integration_support import unique_username

TEST_PASSWORD = "Checkpoint1-Local!"


def _client(engine: Engine) -> TestClient:
    settings = Settings(
        APP_ENV="test",
        DATABASE_URL=str(engine.url),
        EVIDENCE_ROOT=".local/test-evidence",
        LOGIN_MAX_FAILURES=3,
        LOGIN_LOCK_MINUTES=15,
    )
    return TestClient(create_app(settings, engine))


def _account(
    engine: Engine,
    role: RoleCode,
    domain: OperationalDomain | None = None,
    *,
    active: bool = True,
    must_change: bool = True,
) -> str:
    username = unique_username(role.value)
    with Session(engine) as db:
        user = create_account(
            db,
            AccountSpec(username, "Integration Test", role, domain),
            TEST_PASSWORD,
            must_change=must_change,
        )
        user.is_active = active
        db.commit()
    return username


def test_password_hash_login_session_and_logout(postgres_engine: Engine) -> None:
    username = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    with Session(postgres_engine) as db:
        user = db.scalar(select(User).where(User.normalized_username == username))
        assert user is not None
        assert user.password_hash != TEST_PASSWORD
        assert user.password_hash.startswith("$argon2id$")

    with _client(postgres_engine) as client:
        response = client.post("/api/auth/login", json={"username": username, "password": TEST_PASSWORD})
        assert response.status_code == 200
        assert TEST_PASSWORD not in response.text
        assert "password_hash" not in response.text.lower()
        raw_token = client.cookies.get("microcosm_session")
        csrf = response.headers["x-csrf-token"]
        assert raw_token and csrf
        with Session(postgres_engine) as db:
            record = db.scalar(select(SessionRecord).where(SessionRecord.session_token_hash == token_hash(raw_token)))
            assert record is not None
            assert record.session_token_hash != raw_token
        assert client.get("/api/auth/session").json()["user"]["manager_domain"] == "transport"
        assert client.post("/api/auth/logout").status_code == 403
        assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
        assert client.get("/api/auth/session").status_code == 401


def test_wrong_disabled_and_locked_accounts_fail_generically(postgres_engine: Engine) -> None:
    username = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.LPG)
    disabled = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.WATER, active=False)
    with _client(postgres_engine) as client:
        wrong = client.post("/api/auth/login", json={"username": username, "password": "wrong"})
        assert wrong.status_code == 401
        assert wrong.json()["error"]["message"] == "Invalid username or password."
        denied = client.post("/api/auth/login", json={"username": disabled, "password": TEST_PASSWORD})
        assert denied.status_code == 401
        assert denied.json()["error"]["message"] == "Invalid username or password."
        client.post("/api/auth/login", json={"username": username, "password": "wrong"})
        client.post("/api/auth/login", json={"username": username, "password": "wrong"})
    with Session(postgres_engine) as db:
        locked = db.scalar(select(User).where(User.normalized_username == username))
        assert locked is not None and locked.locked_until is not None
        assert locked.locked_until > datetime.now(UTC)


def test_role_and_domain_authorization(postgres_engine: Engine) -> None:
    manager = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.ENERGY, must_change=False)
    admin = _account(postgres_engine, RoleCode.ADMIN, must_change=False)
    with _client(postgres_engine) as anonymous:
        assert anonymous.get("/api/access/admin").status_code == 401
    with _client(postgres_engine) as manager_client:
        assert (
            manager_client.post("/api/auth/login", json={"username": manager, "password": TEST_PASSWORD}).status_code
            == 200
        )
        assert manager_client.get("/api/access/manager/energy").status_code == 200
        assert manager_client.get("/api/access/manager/transport").status_code == 403
        assert manager_client.get("/api/access/admin").status_code == 403
    with _client(postgres_engine) as admin_client:
        assert (
            admin_client.post("/api/auth/login", json={"username": admin, "password": TEST_PASSWORD}).status_code == 200
        )
        assert admin_client.get("/api/access/admin").status_code == 200
        assert admin_client.get("/api/access/manager/energy").status_code == 403


def test_change_password_requires_csrf(postgres_engine: Engine) -> None:
    username = _account(postgres_engine, RoleCode.ADMIN)
    new_password = f"Replacement-{uuid4().hex}!"
    with _client(postgres_engine) as client:
        login = client.post("/api/auth/login", json={"username": username, "password": TEST_PASSWORD})
        csrf = login.headers["x-csrf-token"]
        payload = {"current_password": TEST_PASSWORD, "new_password": new_password}
        assert client.post("/api/auth/change-password", json=payload).status_code == 403
        assert (
            client.post(
                "/api/auth/change-password",
                json={"current_password": "wrong", "new_password": new_password},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/auth/change-password",
                json={"current_password": TEST_PASSWORD, "new_password": TEST_PASSWORD},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/auth/change-password",
                json={"current_password": TEST_PASSWORD, "new_password": "too-short"},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 422
        )
        assert client.post("/api/auth/change-password", json=payload, headers={"X-CSRF-Token": csrf}).status_code == 200


def test_must_change_password_blocks_privileged_apis_until_changed(postgres_engine: Engine) -> None:
    username = _account(postgres_engine, RoleCode.MANAGER, OperationalDomain.TRANSPORT)
    new_password = f"Replacement-{uuid4().hex}!"
    with _client(postgres_engine) as client:
        login = client.post("/api/auth/login", json={"username": username, "password": TEST_PASSWORD})
        csrf = login.headers["x-csrf-token"]
        assert login.json()["user"]["must_change_password"] is True
        assert client.get("/api/access/manager/transport").status_code == 403
        assert client.get("/api/auth/session").status_code == 200
        assert (
            client.post(
                "/api/auth/change-password",
                json={"current_password": TEST_PASSWORD, "new_password": new_password},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 200
        )
        assert client.get("/api/access/manager/transport").status_code == 200


def test_password_change_revokes_other_sessions_but_preserves_current(postgres_engine: Engine) -> None:
    username = _account(
        postgres_engine,
        RoleCode.MANAGER,
        OperationalDomain.WATER,
        must_change=False,
    )
    new_password = f"Replacement-{uuid4().hex}!"
    with _client(postgres_engine) as current_client, _client(postgres_engine) as other_client:
        current_login = current_client.post(
            "/api/auth/login", json={"username": username, "password": TEST_PASSWORD}
        )
        other_login = other_client.post(
            "/api/auth/login", json={"username": username, "password": TEST_PASSWORD}
        )
        assert current_login.status_code == 200 and other_login.status_code == 200
        assert (
            current_client.post(
                "/api/auth/change-password",
                json={"current_password": TEST_PASSWORD, "new_password": new_password},
                headers={"X-CSRF-Token": current_login.headers["x-csrf-token"]},
            ).status_code
            == 200
        )
        assert current_client.get("/api/auth/session").status_code == 200
        assert other_client.get("/api/auth/session").status_code == 401
