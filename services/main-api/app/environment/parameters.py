"""Aeron parameter IDs verified against the live source on 2026-09-25.

Captions and source units are exactly what Aeron's own
``GET /api/stations/{station_id}/parameters?scope=live&region=india`` returned
for station "Air Quality KCT" (35 parameters, none hidden or retired). The
normalizer performs no unit conversion: each stored value is in its source unit.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AeronParameter:
    field: str
    caption: str
    source_unit: str


AERON_PARAMETERS: dict[str, AeronParameter] = {
    "63d0da020016a": AeronParameter("co_mg_m3", "CO", "mg/m3"),
    "63d0da885f1a0": AeronParameter("no2_ug_m3", "NO2", "ug/m3"),
    "63d0daa4740ba": AeronParameter("so2_ug_m3", "SO2", "ug/m3"),
    "63d0daf2bcb74": AeronParameter("o3_ug_m3", "O3", "ug/m3"),
    "63d0db066e993": AeronParameter("no_ug_m3", "NO", "ug/m3"),
    "63d0db8f77ecb": AeronParameter("pm25_ug_m3", "PM 2.5", "ug/m3"),
    "63d0dbb867a7c": AeronParameter("pm10_ug_m3", "PM 10", "ug/m3"),
    "63d0dbfe0a111": AeronParameter("temperature_c", "Ambient Temperature", "degC"),
    "63d0dc28f109d": AeronParameter("relative_humidity_percent", "Relative Humidity", "Per"),
    "63d0dc5164112": AeronParameter("rain_mm", "RAIN", "mm"),
    "63d0dd3721886": AeronParameter("wind_speed_kmph", "Wind Speed", "kmph"),
    "63d0dd4ff30c9": AeronParameter("wind_direction_deg", "Wind Direction", "Deg"),
    "63d0ddf115956": AeronParameter("noise_average_db", "Noise Average", "db"),
    "63d0de104027f": AeronParameter("noise_min_db", "Min value of Noise level", "db"),
    "63d0de34a0b72": AeronParameter("noise_max_db", "Max value of Noise level", "db"),
    "63d0de7568a3b": AeronParameter("uv_index", "UV", "index"),
    "63d0ea1253e8f": AeronParameter("co2_ppm", "CO2", "ppm"),
    "63d0ea927306d": AeronParameter("co_we_mv", "CO_WE", "mv"),
    "63d0eb32b7070": AeronParameter("co_aux_mv", "CO_AUX", "mV"),
    "63d0eb591ee3a": AeronParameter("no2_we_mv", "NO2_WE", "mV"),
    "63d0eb7f49e34": AeronParameter("no2_aux_mv", "NO2_AUX", "mV"),
    "63d0eba20cd96": AeronParameter("so2_we_mv", "SO2_WE", "mV"),
    "63d0ebc89f18d": AeronParameter("so2_aux_mv", "SO2_AUX", "mV"),
    "63d0ebfa17c49": AeronParameter("o3_we_mv", "O3_WE", "mV"),
    "63d0ec7aa5a61": AeronParameter("o3_aux_mv", "O3_AUX", "mV"),
    "63d0ec9873bc3": AeronParameter("no_we_mv", "NO_WE", "mV"),
    "63d0ecc9829f2": AeronParameter("no_aux_mv", "NO_AUX", "mV"),
    # Source caption is misspelled "Baromteric"; kept verbatim.
    "63d0ee3fcd99a": AeronParameter("barometric_pressure_mba", "Baromteric Pressure", "mBa"),
    "63d0eeb2aaeef": AeronParameter("molecular_volume_ltr", "Molecular Volume", "ltr"),
    # Source caption says CO_ppm while its unit is ppb; the unit is authoritative.
    "641d7b36d4413": AeronParameter("co_ppb", "CO_ppm", "ppb"),
    "6421673518c4f": AeronParameter("no2_ppb", "NO2_ppb", "ppb"),
    "64216914170b7": AeronParameter("so2_ppb", "SO2_ppb", "ppb"),
    "64216a7500e46": AeronParameter("o3_ppb", "O3_ppb", "ppb"),
    "64216b8187e5e": AeronParameter("no_ppb", "NO_ppb", "ppb"),
    "6422ae0f8147e": AeronParameter("air_quality_index", "Air Quality Index", "Unit"),
}

METRIC_FIELDS: tuple[str, ...] = tuple(parameter.field for parameter in AERON_PARAMETERS.values())

# Device-health keys the source sends under ``health`` that K-COSMOS persists.
HEALTH_FIELDS: dict[str, str] = {
    "network": "network",
    "battery": "battery",
    "charging": "charging",
    "DeviceTemp": "device_temp",
}
