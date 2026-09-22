from fastapi import APIRouter

from app.models.enums import OperationalDomain
from app.schemas.auth import MessageResponse
from app.security.dependencies import AdminUser, ManagerUser, enforce_manager_domain

router = APIRouter(prefix="/api/access", tags=["access"])


@router.get("/manager/{domain}", response_model=MessageResponse)
def manager_access(domain: OperationalDomain, current: ManagerUser) -> MessageResponse:
    enforce_manager_domain(current, domain)
    return MessageResponse(message="Access granted.")


@router.get("/admin", response_model=MessageResponse)
def admin_access(_current: AdminUser) -> MessageResponse:
    return MessageResponse(message="Access granted.")
