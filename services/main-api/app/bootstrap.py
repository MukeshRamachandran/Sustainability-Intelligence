import argparse
import calendar
import getpass
import os
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import create_database_engine, create_session_factory
from app.models.enums import OperationalDomain, RoleCode
from app.models.identity import ManagerDomainAssignment, Role, User, UserRoleAssignment
from app.models.sustainability import ReportingPeriod
from app.security.passwords import hash_password


@dataclass(frozen=True)
class AccountSpec:
    username: str
    display_name: str
    role: RoleCode
    domain: OperationalDomain | None = None
    email: str | None = None


DEVELOPMENT_ACCOUNTS = (
    AccountSpec("demo.admin", "Development Admin", RoleCode.ADMIN),
    AccountSpec(
        "demo.transport",
        "Development Transport Manager",
        RoleCode.MANAGER,
        OperationalDomain.TRANSPORT,
    ),
    AccountSpec("demo.energy", "Development Energy Manager", RoleCode.MANAGER, OperationalDomain.ENERGY),
    AccountSpec("demo.lpg", "Development LPG Manager", RoleCode.MANAGER, OperationalDomain.LPG),
    AccountSpec("demo.water", "Development Water Manager", RoleCode.MANAGER, OperationalDomain.WATER),
    AccountSpec("demo.outreach", "Development Outreach Manager", RoleCode.MANAGER, OperationalDomain.OUTREACH),
    AccountSpec("demo.waste", "Development Waste Manager", RoleCode.MANAGER, OperationalDomain.WASTE),
)


def normalize(value: str) -> str:
    return value.strip().casefold()


def create_account(db: Session, spec: AccountSpec, password: str, *, must_change: bool = True) -> User:
    normalized_username = normalize(spec.username)
    if db.scalar(select(User).where(User.normalized_username == normalized_username)) is not None:
        raise ValueError(f"account already exists: {spec.username}")
    role = db.scalar(select(Role).where(Role.code == spec.role.value))
    if role is None:
        raise RuntimeError("roles have not been seeded; run alembic upgrade head first")
    if (spec.role is RoleCode.MANAGER) != (spec.domain is not None):
        raise ValueError("manager accounts require exactly one domain; admins require none")

    user = User(
        username=spec.username.strip(),
        normalized_username=normalized_username,
        email=spec.email.strip() if spec.email else None,
        normalized_email=normalize(spec.email) if spec.email else None,
        display_name=spec.display_name.strip(),
        password_hash=hash_password(password),
        must_change_password=must_change,
    )
    db.add(user)
    db.flush()
    db.add(UserRoleAssignment(user_id=user.id, role_id=role.id, reason="account bootstrap"))
    db.flush()
    if spec.domain is not None:
        db.add(ManagerDomainAssignment(user_id=user.id, domain=spec.domain, reason="account bootstrap"))
    return user


def bootstrap_development(db: Session, password: str) -> list[str]:
    created: list[str] = []
    for spec in DEVELOPMENT_ACCOUNTS:
        exists = db.scalar(select(User.id).where(User.normalized_username == normalize(spec.username)))
        if exists is None:
            create_account(db, spec, password, must_change=True)
            created.append(spec.username)
    for year in range(2025, 2028):
        for month in range(1, 13):
            existing_period = db.scalar(
                select(ReportingPeriod.id).where(ReportingPeriod.year == year, ReportingPeriod.month == month)
            )
            if existing_period is None:
                db.add(
                    ReportingPeriod(
                        year=year,
                        month=month,
                        period_start=date(year, month, 1),
                        period_end=date(year, month, calendar.monthrange(year, month)[1]),
                        is_open=True,
                    )
                )
    db.commit()
    return created


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap K-COSMOS accounts safely.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("development", help="Create six synthetic development accounts and local periods.")
    admin = subparsers.add_parser("admin", help="Interactively create the first production administrator.")
    admin.add_argument("--username", required=True)
    admin.add_argument("--display-name", required=True)
    admin.add_argument("--email")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    engine = create_database_engine(settings.DATABASE_URL)
    factory = create_session_factory(engine)
    try:
        with factory() as db:
            if args.command == "development":
                if settings.APP_ENV == "production":
                    raise RuntimeError("development account bootstrap is disabled in production")
                password = os.getenv("MICROCOSM_DEV_BOOTSTRAP_PASSWORD")
                if not password or len(password) < settings.PASSWORD_MIN_LENGTH:
                    raise RuntimeError("MICROCOSM_DEV_BOOTSTRAP_PASSWORD must satisfy password policy")
                created = bootstrap_development(db, password)
                print("Created development accounts: " + (", ".join(created) if created else "none (already present)"))
            else:
                password = getpass.getpass("Initial administrator password: ")
                confirmation = getpass.getpass("Confirm password: ")
                if password != confirmation or len(password) < settings.PASSWORD_MIN_LENGTH:
                    raise RuntimeError("passwords differ or do not satisfy policy")
                spec = AccountSpec(args.username, args.display_name, RoleCode.ADMIN, email=args.email)
                create_account(db, spec, password, must_change=True)
                db.commit()
                print(f"Created administrator: {args.username}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
