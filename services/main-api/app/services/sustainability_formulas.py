"""Pure, database-free sustainability formulas.

This module is the single source of the accepted calculation formulas
(DERIVED_KPI_CALCULATION_CONTRACT.md, schema 1.4). Both release preparation
(app.services.publication / app.services.emission_factors) and the historical
data layer (app.historical.calculator) call these functions, so the two paths
cannot drift apart.

Every function treats ``None`` as *missing*: a missing input makes the result
missing. Missing is never replaced by zero. An explicit zero input is a real
value and stays zero.

Two GHG completeness rules live side by side:

* the strict functions (``scope1_tco2e``, ``grid_total_kwh``,
  ``operational_ghg_tco2e``) need every component and are what official
  release preparation uses;
* the ``*_available_*`` functions (owner-approved available-data methodology)
  sum every component that exists and exclude the missing ones. A missing
  component is excluded, never counted as zero; the caller must label the
  result PARTIAL.
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


def available_total(values: Iterable[Decimal | None]) -> Decimal | None:
    """Sum of the values that exist; missing ones are excluded, never zero.

    Missing only when nothing exists. An explicit zero is a value and counts.
    """
    items = [item for item in values if item is not None]
    return sum(items, Decimal("0")) if items else None


def activity_emissions_kgco2e(activity: Decimal | None, factor: Decimal | None) -> Decimal | None:
    """activity × factor (kgCO2e), unrounded."""
    if activity is None or factor is None:
        return None
    return activity * factor


def activity_emissions_tco2e(activity: Decimal | None, factor: Decimal | None) -> Decimal | None:
    """activity × factor / 1000, quantized exactly like frozen submissions."""
    kgco2e = activity_emissions_kgco2e(activity, factor)
    return None if kgco2e is None else (kgco2e / Decimal(1000)).quantize(ACTIVITY_EMISSION_PLACES)


def dg_diesel_litres(generation_kwh: Decimal | None, sfc_l_per_kwh: Decimal | None) -> Decimal | None:
    """Diesel litres derived from DG generation: kWh x specific fuel consumption (L/kWh), unrounded.

    Missing generation or a missing SFC makes the result missing, never zero.
    """
    if generation_kwh is None or sfc_l_per_kwh is None:
        return None
    return generation_kwh * sfc_l_per_kwh


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


def grid_available_kwh(ht: Decimal | None, commercial: Decimal | None, temporary: Decimal | None) -> Decimal | None:
    """Grid kWh from the meters that reported; a missing meter is not zero."""
    return available_total((ht, commercial, temporary))


def scope1_available_tco2e(
    petrol: Decimal | None, transport_diesel: Decimal | None, dg_diesel: Decimal | None, lpg: Decimal | None
) -> Decimal | None:
    """Scope 1 from the components that exist; missing only when none does."""
    return available_total((petrol, transport_diesel, dg_diesel, lpg))


def operational_ghg_available_tco2e(scope1: Decimal | None, scope2: Decimal | None) -> Decimal | None:
    """Available Scope 1 + available Scope 2; either one alone is enough."""
    return available_total((scope1, scope2))


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


def waste_diverted_from_landfill_kg(dry: Decimal | None) -> Decimal | None:
    """Owner-approved methodology: waste diverted from landfill IS the dry waste generated.

    Missing dry waste is missing (never zero); an explicit zero stays zero. No
    diversion percentage is involved.
    """
    return dry


def waste_per_capita_kg(total_kg: Decimal | None, population: Decimal | int | None) -> Decimal | None:
    return per_capita(total_kg, population)
