from copy import deepcopy

from app.services.publication import _schema_1_4_indicators, derived_payload_blockers


def _payload(*, solar: int = 500, procured: int = 60, factor: float = 0.8) -> dict[str, object]:
    return {
        "schema_version": "1.4",
        "energy": {
            "metrics": {
                "grid_total_kwh": {"value": 350},
                "renewable_on_campus_kwh": {"value": 40},
                "renewable_procured_kwh": {"value": procured},
                "solar_water_heater_kwh": {"value": solar},
                "renewable_total_kwh": {"value": 40 + procured + solar},
            },
            "calculations": [{
                "calculation_code": "grid_electricity_emissions",
                "status": "available",
                "factor_code": "GRID_ELECTRICITY",
                "factor_value": factor,
                "factor_unit": "kgCO2e/kWh",
                "factor_set_version": "synthetic-second-month",
                "formula_version": "activity_x_factor_kgco2e_v1",
            }],
        },
        "water": {"metrics": {"water_consumed_kl": {"value": 700}}},
        "population": {"status": "available", "value": 7000},
    }


def _indicators(payload: dict[str, object]) -> dict[str, object]:
    result = _schema_1_4_indicators(payload)
    payload["indicators"] = result
    return result


def _value(indicators: dict[str, object], code: str) -> object:
    entry = indicators[code]
    assert isinstance(entry, dict)
    return entry["value"]


def test_synthetic_second_month_and_solar_thermal_exclusion() -> None:
    baseline = _payload(solar=0)
    derived = _indicators(baseline)
    assert _value(derived, "renewable_electricity_kwh") == 100
    assert _value(derived, "total_electricity_consumption_kwh") == 450
    assert _value(derived, "renewable_share_pct") == 22.222222222222
    assert _value(derived, "estimated_avoided_grid_emissions_tco2e") == 0.08
    assert _value(derived, "water_per_capita_l") == 100
    assert derived_payload_blockers(baseline) == []

    changed = _payload(solar=1_000_000)
    assert _indicators(changed) == derived

    # Legacy keys stay present but point at their governed replacements.
    legacy_avoided = derived["avoided_emissions_tco2e"]
    legacy_share = derived["renewable_share_percent"]
    assert isinstance(legacy_avoided, dict) and isinstance(legacy_share, dict)
    assert legacy_avoided["reason"] == "superseded_by_estimated_avoided_grid_emissions_tco2e"
    assert legacy_share["reason"] == "superseded_by_renewable_share_pct"


def test_procured_renewable_and_grid_factor_provenance_change_results() -> None:
    baseline = _indicators(_payload(procured=60, factor=0.8))
    more_procured = _indicators(_payload(procured=160, factor=0.8))
    assert _value(more_procured, "renewable_electricity_kwh") == 200
    assert _value(more_procured, "total_electricity_consumption_kwh") == 550
    assert _value(more_procured, "renewable_share_pct") != _value(baseline, "renewable_share_pct")
    assert _value(more_procured, "estimated_avoided_grid_emissions_tco2e") == 0.16
    different_factor = _indicators(_payload(procured=60, factor=0.5))
    assert _value(different_factor, "estimated_avoided_grid_emissions_tco2e") == 0.05
    avoided = different_factor["estimated_avoided_grid_emissions_tco2e"]
    assert isinstance(avoided, dict)
    assert avoided["provenance"]["factor_set_version"] == "synthetic-second-month"


def test_missing_sources_block_but_explicit_zero_is_preserved() -> None:
    missing = _payload()
    assert isinstance(missing["energy"], dict)
    assert isinstance(missing["energy"]["metrics"], dict)
    missing["energy"]["metrics"]["renewable_procured_kwh"]["value"] = None
    _indicators(missing)
    assert derived_payload_blockers(missing)

    zero = _payload(procured=0)
    assert isinstance(zero["energy"], dict)
    assert isinstance(zero["energy"]["metrics"], dict)
    zero["energy"]["metrics"]["renewable_on_campus_kwh"]["value"] = 0
    zero_derived = _indicators(zero)
    assert _value(zero_derived, "renewable_electricity_kwh") == 0
    assert _value(zero_derived, "estimated_avoided_grid_emissions_tco2e") == 0
    assert derived_payload_blockers(zero) == []

    no_denominator = deepcopy(zero)
    no_denominator["energy"]["metrics"]["grid_total_kwh"]["value"] = 0
    _indicators(no_denominator)
    assert any("renewable_share_pct" in row["reason"] for row in derived_payload_blockers(no_denominator))
