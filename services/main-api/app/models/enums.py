from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM


class RoleCode(StrEnum):
    MANAGER = "manager"
    ADMIN = "microcosm_admin"


class OperationalDomain(StrEnum):
    TRANSPORT = "transport"
    ENERGY = "energy"
    LPG = "lpg"
    WATER = "water"
    OUTREACH = "outreach"
    WASTE = "waste"


class AccountingClassification(StrEnum):
    SCOPE1 = "scope1_inventory"
    SCOPE2 = "scope2_inventory"
    AVOIDED = "avoided_impact"
    ACTIVITY = "activity_only"
    RENEWABLE = "renewable_reporting"
    WATER = "water_reporting"


class PublicationClass(StrEnum):
    PUBLIC_AGGREGATE = "public_aggregate"
    ADMIN_ONLY = "admin_only"
    INTERNAL_VERIFICATION = "internal_verification"


class SubmissionStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    CORRECTION_REQUESTED = "correction_requested"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class ReviewActionType(StrEnum):
    SUBMIT = "submit"
    BEGIN_REVIEW = "begin_review"
    REQUEST_CORRECTION = "request_correction"
    APPROVE = "approve"
    SUPERSEDE = "supersede"


class FactorSetStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class FactorCode(StrEnum):
    PETROL = "PETROL"
    DIESEL = "DIESEL"
    GRID_ELECTRICITY = "GRID_ELECTRICITY"
    # Legacy litre factor (kgCO2e/L). Kept only so retired factor sets and
    # frozen litre-era calculations stay readable; new sets cannot use it.
    LPG = "LPG"
    # Governed LPG factor on a weight basis (kgCO2e/kg), 0013_lpg_kg_governance_v2.
    LPG_KG = "LPG_KG"


LEGACY_FACTOR_CODES = frozenset({FactorCode.LPG})


class ReleaseStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


def _values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


OPERATIONAL_DOMAIN_DB = ENUM(
    OperationalDomain,
    name="operational_domain",
    schema="sustainability",
    values_callable=_values,
    create_type=False,
)
ACCOUNTING_CLASSIFICATION_DB = ENUM(
    AccountingClassification,
    name="accounting_classification",
    schema="sustainability",
    values_callable=_values,
    create_type=False,
)
PUBLICATION_CLASS_DB = ENUM(
    PublicationClass,
    name="publication_class",
    schema="sustainability",
    values_callable=_values,
    create_type=False,
)
SUBMISSION_STATUS_DB = ENUM(
    SubmissionStatus,
    name="submission_status",
    schema="sustainability",
    values_callable=_values,
    create_type=False,
)
REVIEW_ACTION_TYPE_DB = ENUM(
    ReviewActionType,
    name="review_action_type",
    schema="sustainability",
    values_callable=_values,
    create_type=False,
)
FACTOR_SET_STATUS_DB = ENUM(
    FactorSetStatus,
    name="factor_set_status",
    schema="sustainability",
    values_callable=_values,
    create_type=False,
)
RELEASE_STATUS_DB = ENUM(
    ReleaseStatus,
    name="release_status",
    schema="publication",
    values_callable=_values,
    create_type=False,
)
