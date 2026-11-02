"""Aeron parameter IDs for station "Air Quality KCT".

``PARAMETER_MAP`` is the owner-supplied mapping: name, unit and category per
Aeron parameter ID. All 35 IDs and their units match what
``GET /api/v1/parameters?station=...`` returned live on 2026-11-02, except
the AQI unit, which the source reports as ``Unit``. No unit conversion is
performed anywhere: each stored value is in the unit listed here.

``READING_COLUMNS`` binds each ID to its existing ``environment.readings``
column, so stored history and the Weather UI contract are unchanged.
"""

from dataclasses import dataclass
from typing import Final

PARAMETER_MAP: Final[dict[str, dict[str, str]]] = {
    # Air quality
    "63d0da020016a": {"name": "CO", "unit": "mg/m3", "category": "air_quality"},
    "63d0da885f1a0": {"name": "NO2", "unit": "ug/m3", "category": "air_quality"},
    "63d0daa4740ba": {"name": "SO2", "unit": "ug/m3", "category": "air_quality"},
    "63d0daf2bcb74": {"name": "O3", "unit": "ug/m3", "category": "air_quality"},
    "63d0db066e993": {"name": "NO", "unit": "ug/m3", "category": "air_quality"},
    "63d0db8f77ecb": {"name": "PM2.5", "unit": "ug/m3", "category": "air_quality"},
    "63d0dbb867a7c": {"name": "PM10", "unit": "ug/m3", "category": "air_quality"},
    "63d0ea1253e8f": {"name": "CO2", "unit": "ppm", "category": "air_quality"},
    "6422ae0f8147e": {"name": "AQI", "unit": "index", "category": "air_quality"},
    # Weather
    "63d0dbfe0a111": {"name": "Ambient Temperature", "unit": "degC", "category": "weather"},
    "63d0dc28f109d": {"name": "Relative Humidity", "unit": "Per", "category": "weather"},
    "63d0dc5164112": {"name": "Rainfall", "unit": "mm", "category": "weather"},
    "63d0dd3721886": {"name": "Wind Speed", "unit": "kmph", "category": "weather"},
    "63d0dd4ff30c9": {"name": "Wind Direction", "unit": "Deg", "category": "weather"},
    "63d0de7568a3b": {"name": "UV Index", "unit": "index", "category": "weather"},
    "63d0ee3fcd99a": {"name": "Barometric Pressure", "unit": "mBa", "category": "weather"},
    "63d0eeb2aaeef": {"name": "Molecular Volume", "unit": "ltr", "category": "weather"},
    # Noise
    "63d0ddf115956": {"name": "Noise Average", "unit": "db", "category": "noise"},
    "63d0de104027f": {"name": "Noise Minimum", "unit": "db", "category": "noise"},
    "63d0de34a0b72": {"name": "Noise Maximum", "unit": "db", "category": "noise"},
    # Electrochemical sensor diagnostics
    "63d0ea927306d": {"name": "CO_WE", "unit": "mv", "category": "diagnostics"},
    "63d0eb32b7070": {"name": "CO_AUX", "unit": "mV", "category": "diagnostics"},
    "63d0eb591ee3a": {"name": "NO2_WE", "unit": "mV", "category": "diagnostics"},
    "63d0eb7f49e34": {"name": "NO2_AUX", "unit": "mV", "category": "diagnostics"},
    "63d0eba20cd96": {"name": "SO2_WE", "unit": "mV", "category": "diagnostics"},
    "63d0ebc89f18d": {"name": "SO2_AUX", "unit": "mV", "category": "diagnostics"},
    "63d0ebfa17c49": {"name": "O3_WE", "unit": "mV", "category": "diagnostics"},
    "63d0ec7aa5a61": {"name": "O3_AUX", "unit": "mV", "category": "diagnostics"},
    "63d0ec9873bc3": {"name": "NO_WE", "unit": "mV", "category": "diagnostics"},
    "63d0ecc9829f2": {"name": "NO_AUX", "unit": "mV", "category": "diagnostics"},
    # Additional pollutant measurements
    "641d7b36d4413": {"name": "CO_ppm", "unit": "ppb", "category": "pollutant_ppb"},
    "6421673518c4f": {"name": "NO2_ppb", "unit": "ppb", "category": "pollutant_ppb"},
    "64216914170b7": {"name": "SO2_ppb", "unit": "ppb", "category": "pollutant_ppb"},
    "64216a7500e46": {"name": "O3_ppb", "unit": "ppb", "category": "pollutant_ppb"},
    "64216b8187e5e": {"name": "NO_ppb", "unit": "ppb", "category": "pollutant_ppb"},
}

READING_COLUMNS: Final[dict[str, str]] = {
    "63d0da020016a": "co_mg_m3",
    "63d0da885f1a0": "no2_ug_m3",
    "63d0daa4740ba": "so2_ug_m3",
    "63d0daf2bcb74": "o3_ug_m3",
    "63d0db066e993": "no_ug_m3",
    "63d0db8f77ecb": "pm25_ug_m3",
    "63d0dbb867a7c": "pm10_ug_m3",
    "63d0ea1253e8f": "co2_ppm",
    "6422ae0f8147e": "air_quality_index",
    "63d0dbfe0a111": "temperature_c",
    "63d0dc28f109d": "relative_humidity_percent",
    "63d0dc5164112": "rain_mm",
    "63d0dd3721886": "wind_speed_kmph",
    "63d0dd4ff30c9": "wind_direction_deg",
    "63d0de7568a3b": "uv_index",
    "63d0ee3fcd99a": "barometric_pressure_mba",
    "63d0eeb2aaeef": "molecular_volume_ltr",
    "63d0ddf115956": "noise_average_db",
    "63d0de104027f": "noise_min_db",
    "63d0de34a0b72": "noise_max_db",
    "63d0ea927306d": "co_we_mv",
    "63d0eb32b7070": "co_aux_mv",
    "63d0eb591ee3a": "no2_we_mv",
    "63d0eb7f49e34": "no2_aux_mv",
    "63d0eba20cd96": "so2_we_mv",
    "63d0ebc89f18d": "so2_aux_mv",
    "63d0ebfa17c49": "o3_we_mv",
    "63d0ec7aa5a61": "o3_aux_mv",
    "63d0ec9873bc3": "no_we_mv",
    "63d0ecc9829f2": "no_aux_mv",
    "641d7b36d4413": "co_ppb",
    "6421673518c4f": "no2_ppb",
    "64216914170b7": "so2_ppb",
    "64216a7500e46": "o3_ppb",
    "64216b8187e5e": "no_ppb",
}

# Metadata awaiting confirmation from Aeron. Values are stored and served
# exactly as received; these notes travel with the metadata instead.
VERIFICATION_NOTES: Final[dict[str, str]] = {
    "63d0ee3fcd99a": "Reported as a constant 150 mBa; not plausible atmospheric pressure. Calibration unconfirmed.",
    "641d7b36d4413": "Source name says ppm but unit says ppb. Source metadata kept until Aeron confirms.",
    "6422ae0f8147e": "AQI calculation standard unconfirmed; no health category is assigned.",
    "63d0dc28f109d": "Source unit 'Per' is unconfirmed as percent.",
}


@dataclass(frozen=True)
class AeronParameter:
    field: str
    name: str
    unit: str
    category: str
    note: str | None = None


AERON_PARAMETERS: Final[dict[str, AeronParameter]] = {
    parameter_id: AeronParameter(
        field=READING_COLUMNS[parameter_id],
        name=meta["name"],
        unit=meta["unit"],
        category=meta["category"],
        note=VERIFICATION_NOTES.get(parameter_id),
    )
    for parameter_id, meta in PARAMETER_MAP.items()
}

METRIC_FIELDS: Final[tuple[str, ...]] = tuple(parameter.field for parameter in AERON_PARAMETERS.values())
