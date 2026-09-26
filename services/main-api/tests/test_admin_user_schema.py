import pytest
from pydantic import ValidationError

from app.models.enums import OperationalDomain
from app.schemas.admin_users import CreateManagerRequest


def test_create_manager_accepts_documented_domain_alias() -> None:
    payload = CreateManagerRequest.model_validate(
        {
            "username": "waste@kct.ac.in",
            "display_name": "Waste Manager",
            "email": "waste@kct.ac.in",
            "role": "manager",
            "domain": "waste",
            "temporary_password": "Temporary-Manager-1!",
        }
    )
    assert payload.manager_domain is OperationalDomain.WASTE
    assert payload.role == "manager"
    assert payload.email == "waste@kct.ac.in"
    dumped = payload.model_dump()
    assert "temporary_password" in dumped
    assert "password_hash" not in dumped


def test_create_manager_still_accepts_manager_domain_field() -> None:
    payload = CreateManagerRequest.model_validate(
        {
            "username": "transport.manager",
            "display_name": "Transport Manager",
            "manager_domain": "transport",
            "temporary_password": "Temporary-Manager-1!",
        }
    )
    assert payload.manager_domain is OperationalDomain.TRANSPORT
    assert payload.email is None


def test_create_manager_rejects_non_manager_role() -> None:
    with pytest.raises(ValidationError):
        CreateManagerRequest.model_validate(
            {
                "username": "waste@kct.ac.in",
                "display_name": "Waste Manager",
                "role": "admin",
                "domain": "waste",
                "temporary_password": "Temporary-Manager-1!",
            }
        )
