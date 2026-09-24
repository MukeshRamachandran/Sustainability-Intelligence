"""Pure, database-free sustainability formulas.

This module is the single source of the accepted calculation formulas
(DERIVED_KPI_CALCULATION_CONTRACT.md, schema 1.4). Both release preparation
(app.services.publication / app.services.emission_factors) and the historical
data layer (app.historical.calculator) call these functions, so the two paths
cannot drift apart.

Every function treats ``None`` as *missing*: a missing input makes the result
missing. Missing is never replaced by zero. An explicit zero input is a real
value and stays zero.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

ACTIVITY_EMISSION_PLACES = Decimal("0.000001")


def _all_present(values: Iterable[Decimal | None]) -> list[Decimal] | None:
    items = list(values)
    if any(item is None for item in items):
        return None
    return [item for item in items if item is not None]


def total_of(values: Iterable[Decimal | None]) -> Decimal | None:
    """Sum of every value, or missing when any value is missing."""
    items = _all_present(values)
    return None if items is None else sum(items, Decimal("0"))


def activity_emissions_kgco2e(activity: Decimal | None, factor: Decimal | None) -> Decimal | None:
    """activity × factor (kgCO2e), unrounded."""
    if activity is None or factor is None:
        return None
    return activity * factor


def activity_emissions_tco2e(activity: Decimal | None, factor: Decimal | None) -> Decimal | None:
    """activity × factor / 1000, quantized exactly like frozen submissions."""
    kgco2e = activity_emissions_kgco2e(activity, factor)
    return None if kgco2e is None else (kgco2e / Decimal(1000)).quantize(ACTIVITY_EMISSION_PLACES)


def grid_total_kwh(ht: Decimal | None, commercial: Decimal | None, temporary: Decimal | None) -> Decimal | None:
    return total_of((ht, commercial, temporary))


def renewable_electricity_kwh(on_campus: Decimal | None, procured: Decimal | None) -> Decimal | None:
    """On-campus + procured. Solar water heater (thermal) is deliberately not an input."""
    return total_of((on_campus, procured))


def total_electricity_consumption_kwh(grid: Decimal | None, renewable: Decimal | None) -> Decimal | None:
    return total_of((grid, renewable))


def renewable_share_pct(renewable: Decimal | None, total: Decimal | None) -> Decimal | None:
    """Ratio of sums. Never average monthly percentages; pass summed inputs."""
    if renewable is None or total is None or total <= 0:
        return None
    return renewable * 100 / total


def estimated_avoided_grid_emissions_tco2e(renewable: Decimal | None, grid_factor: Decimal | None) -> Decimal | None:
    if renewable is None or grid_factor is None or not grid_factor.is_finite() or grid_factor <= 0:
        return None
    return renewable * grid_factor / 1000


def scope1_tco2e(
    petrol: Decimal | None, transport_diesel: Decimal | None, dg_diesel: Decimal | None, lpg: Decimal | None
) -> Decimal | None:
    """All four governed components are required; a partial Scope 1 is missing."""
    return total_of((petrol, transport_diesel, dg_diesel, lpg))


def operational_ghg_tco2e(scope1: Decimal | None, scope2: Decimal | None) -> Decimal | None:
    return total_of((scope1, scope2))


def per_capita(value: Decimal | None, population: Decimal | int | None, *, multiplier: int = 1) -> Decimal | None:
    if value is None or population is None:
        return None
    people = Decimal(population)
    if people <= 0:
        return None
    return value * multiplier / people


def operational_ghg_per_capita_kgco2e(operational: Decimal | None, population: Decimal | int | None) -> Decimal | None:
    return per_capita(operational, population, multiplier=1000)


def water_consumed_kl(twad: Decimal | None, borewell: Decimal | None, private: Decimal | None) -> Decimal | None:
    return total_of((twad, borewell, private))


def water_per_capita_l(water_kl: Decimal | None, population: Decimal | int | None) -> Decimal | None:
    return per_capita(water_kl, population, multiplier=1000)


def waste_total_kg(wet: Decimal | None, dry: Decimal | None) -> Decimal | None:
    return total_of((wet, dry))


def waste_per_capita_kg(total_kg: Decimal | None, population: Decimal | int | None) -> Decimal | None:
    return per_capita(total_kg, population)
