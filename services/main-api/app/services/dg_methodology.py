"""DG generator activity methodology (0015_dg_kwh_methodology).

Two legitimate DG activity pathways feed the same DG emission:

* legacy - source-reported diesel litres x governed DIESEL factor;
* from the governed SFC's effective date - source-reported generation (kWh)
  x governed SFC -> derived diesel litres x governed DIESEL factor.

The effective date and the SFC value live in
``sustainability.calculation_parameters``; nothing here names a month or a
number. A period never counts both pathways: when a usable kWh source exists
it is authoritative and any litre value for that period is not used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sustainability import CalculationParameter
from app.services import sustainability_formulas as formulas

DG_SFC = "DG_SFC"
DG_GENERATION_METRIC = "dg_generation_kwh"
DG_LITRES_METRIC = "dg_diesel_litres"
DG_EMISSIONS = "dg_diesel_emissions"
DG_FACTOR = "DIESEL"
DOMAIN_KEY = "transport"  # DG entry lives in the Transport domain
GENERATION_UNIT = "kWh"
LITRES_UNIT = "L"
SOURCE_REPORTED_LITRES = "SOURCE_REPORTED_LITRES"
DERIVED_FROM_KWH = "DERIVED_FROM_KWH"


def parameter_for(db: Session, code: str, on: date) -> CalculationParameter | None:
    """The governed parameter in force on ``on`` (latest effective date not after it)."""
    return db.scalar(
        select(CalculationParameter)
        .where(CalculationParameter.code == code, CalculationParameter.effective_from <= on)
        .order_by(CalculationParameter.effective_from.desc())
        .limit(1)
    )


def manager_source_metric(db: Session, period_start: date) -> str:
    """The DG activity a Manager enters for a period: kWh once the SFC is in force, else litres."""
    return DG_GENERATION_METRIC if parameter_for(db, DG_SFC, period_start) is not None else DG_LITRES_METRIC


def superseded_manager_metric(db: Session, period_start: date) -> str:
    """The DG activity a Manager must NOT enter for a period."""
    source = manager_source_metric(db, period_start)
    return DG_LITRES_METRIC if source == DG_GENERATION_METRIC else DG_GENERATION_METRIC


@dataclass(frozen=True)
class DgDerivation:
    generation_kwh: Decimal
    parameter: CalculationParameter
    litres: Decimal

    def as_json(self) -> dict[str, Any]:
        """Frozen provenance: source kWh, the SFC applied and the derived litres."""
        return {
            "activity_origin": DERIVED_FROM_KWH,
            "source_metric_code": DG_GENERATION_METRIC,
            "source_value": format(self.generation_kwh.normalize(), "f"),
            "source_unit": GENERATION_UNIT,
            "parameter_code": self.parameter.code,
            "parameter_value": format(self.parameter.parameter_value.normalize(), "f"),
            "parameter_unit": self.parameter.unit,
            "parameter_effective_from": self.parameter.effective_from.isoformat(),
            "parameter_source": self.parameter.source_reference,
            "derived_metric_code": DG_LITRES_METRIC,
            "derived_value": format(self.litres.normalize(), "f"),
            "derived_unit": LITRES_UNIT,
        }


def derive_litres(db: Session, generation_kwh: Decimal | None, period_start: date) -> DgDerivation | None:
    """Derived diesel litres for a kWh source, or ``None`` when it cannot be derived.

    ``None`` when the kWh value is missing (missing is never zero) or when no
    governed SFC is in force for the period (a pre-methodology period is never
    pushed through the kWh pathway).
    """
    parameter = parameter_for(db, DG_SFC, period_start)
    litres = formulas.dg_diesel_litres(generation_kwh, parameter.parameter_value if parameter else None)
    if generation_kwh is None or parameter is None or litres is None:
        return None
    return DgDerivation(generation_kwh, parameter, litres)
