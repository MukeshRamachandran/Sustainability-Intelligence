# Aeron REST API v1 contract (verified)

This is the source contract the K-COSMOS environment worker is built on. How the worker uses it, and how to run it, is in [AERON_INTEGRATION_ARCHITECTURE.md](AERON_INTEGRATION_ARCHITECTURE.md).

Verified live on 2026-11-02 at 11:02 UTC, one request per endpoint. The key was not printed or stored. The sanitized responses (device IMEI redacted, no headers or credentials) are in [`services/main-api/tests/fixtures/aeron/aeron_v1_sample_sanitized.json`](../../services/main-api/tests/fixtures/aeron/aeron_v1_sample_sanitized.json).

## Access

| Item | Value |
| --- | --- |
| Base URL | `https://live3.aeronsystems.com/api/v1` |
| Authentication | `Authorization: Bearer <API key>` |
| Key location | `AERON_API_KEY` in `services/main-api/.env` on the server only |
| Rate limits | 60 requests/minute, 10,000/day (`X-Ratelimit-Limit-Minute`, `X-Ratelimit-Limit-Day`) |
| Other headers | `X-Ratelimit-Remaining-Minute`, `X-Ratelimit-Remaining-Day`, `X-Ratelimit-Reset` (epoch seconds), `X-Ratelimit-Bucket: cheap` |
| Push / webhook | None documented or observed. K-COSMOS polls. |

## Station

| Field | Value |
| --- | --- |
| `id` | `b1ce41c2-586a-4a26-9382-9d8bfe757e78` |
| `name` | Air Quality KCT |
| `type` | XTM-XG930 |
| `location` | Kumaraguru College Of Technology KCT |
| `timezone` | `Asia/Kolkata` |
| `reportingIntervalMs` | 60000 |
| `region` | india |

## Endpoints

| Request | Used by K-COSMOS | Response (200, JSON) |
| --- | --- | --- |
| `GET /stations` | No (verification only) | `{"stations": [{id, name, type, location, latitude, longitude, timezone, status, lastDataAt, expiryDate, region, organizationId, reportingIntervalMs, …}]}` |
| `GET /parameters?station={id}` | Once at worker start, to log drift | `{"parameters": [{code, unit, description}]}`, 35 entries |
| `GET /timeseries?station={id}` | Every poll | `{"station": "<id>", "resolution": "latest", "reading": {"timestamp": "…Z", "epoch_ms": <int>, "values": {"<parameter code>": <number>, …}}}` |

Example `timeseries` response (shortened):

```json
{
  "station": "b1ce41c2-586a-4a26-9382-9d8bfe757e78",
  "resolution": "latest",
  "reading": {
    "timestamp": "2026-11-02T10:58:01.000Z",
    "epoch_ms": 1793617081000,
    "values": {
      "63d0db8f77ecb": 4.69,
      "63d0dbfe0a111": 27.11,
      "6422ae0f8147e": 107
    }
  }
}
```

History parameters for `/timeseries` are not verified and are not used.

## Error responses and worker codes

| Response | Worker `error_code` | Retried by the client? | Next poll |
| --- | --- | --- | --- |
| 401 | `AUTH_FAILED` | No | 5 min, doubling to 1 h |
| 403 | `FORBIDDEN` | No | 5 min, doubling to 1 h |
| 404 | `NOT_FOUND` | No | 5 min, doubling to 1 h |
| 429 | `RATE_LIMITED` | No | `Retry-After` / `X-Ratelimit-Reset`, capped at 1 h |
| 5xx | `HTTP_ERROR` | Yes, up to `AERON_MAX_ATTEMPTS` | Normal interval |
| Other non-200, redirects | `HTTP_ERROR` | No | Normal interval |
| Timeout | `TIMEOUT` | Yes | Normal interval |
| Connection failure | `NETWORK_ERROR` | Yes | Normal interval |
| Body not a JSON object | `MALFORMED_RESPONSE` | No | Normal interval |
| No usable timestamp or values | `INVALID_READING` | No | Normal interval |
| `station` differs from `AERON_STATION_ID` | `STATION_MISMATCH` | No | 5 min, doubling to 1 h |

Nothing is stored when a cycle fails. Run records keep the fixed code only, never response text.

## Timestamp contract

| Question | Answer |
| --- | --- |
| Field | `reading.timestamp`, ISO 8601 with `Z` |
| Meaning | True UTC measurement time |
| `epoch_ms` | Same instant in milliseconds. A mismatch adds the `epoch_ms_mismatch` flag. |
| +330 minute correction | **Not applied.** The timestamp is already UTC. |
| Timestamps without a zone | Rejected, not guessed |

```text
raw            2026-11-02T10:58:01.000Z
stored         observed_at = 2026-11-02 10:58:01+00
shown (IST)    2026-11-02 16:28:01
```

K-COSMOS stores `observed_at` (sensor time), `fetched_at` (response received) and `ingested_at` (row stored) separately, all UTC. Display converts to `Asia/Kolkata`.

## Parameters

All 35 codes and units from `GET /parameters` match `PARAMETER_MAP` in `services/main-api/app/environment/parameters.py`. The only difference is AQI, whose source unit is `Unit`; K-COSMOS records it as `index`. Values are stored in source units with no conversion. A missing or non-numeric value is stored as `NULL` with a quality flag, never as 0.

| Code | Source name | Source unit | K-COSMOS column | Shown on Weather page |
| --- | --- | --- | --- | --- |
| `63d0da020016a` | CO | mg/m3 | `co_mg_m3` | CO tile |
| `63d0da885f1a0` | NO2 | ug/m3 | `no2_ug_m3` | NO₂ tile |
| `63d0daa4740ba` | SO2 | ug/m3 | `so2_ug_m3` | SO₂ tile |
| `63d0daf2bcb74` | O3 | ug/m3 | `o3_ug_m3` | O₃ card |
| `63d0db066e993` | NO | ug/m3 | `no_ug_m3` | NO tile |
| `63d0db8f77ecb` | PM 2.5 | ug/m3 | `pm25_ug_m3` | PM2.5 card and chart |
| `63d0dbb867a7c` | PM 10 | ug/m3 | `pm10_ug_m3` | PM10 card and chart |
| `63d0dbfe0a111` | Ambient Temperature | degC | `temperature_c` | Temperature card and chart |
| `63d0dc28f109d` | Relative Humidity | Per | `relative_humidity_percent` | Humidity card and chart (shown as %) |
| `63d0dc5164112` | RAIN | mm | `rain_mm` | Rainfall card and chart |
| `63d0dd3721886` | Wind Speed | kmph | `wind_speed_kmph` | Wind card and chart |
| `63d0dd4ff30c9` | Wind Direction | Deg | `wind_direction_deg` | Wind direction card |
| `63d0ddf115956` | Noise Average | db | `noise_average_db` | Noise average |
| `63d0de104027f` | Min value of Noise level | db | `noise_min_db` | Noise minimum |
| `63d0de34a0b72` | Max value of Noise level | db | `noise_max_db` | Noise maximum |
| `63d0de7568a3b` | UV | index | `uv_index` | UV card |
| `63d0ea1253e8f` | CO2 | ppm | `co2_ppm` | CO₂ card |
| `63d0ea927306d` | CO_WE | mv | `co_we_mv` | stored only |
| `63d0eb32b7070` | CO_AUX | mV | `co_aux_mv` | stored only |
| `63d0eb591ee3a` | NO2_WE | mV | `no2_we_mv` | stored only |
| `63d0eb7f49e34` | NO2_AUX | mV | `no2_aux_mv` | stored only |
| `63d0eba20cd96` | SO2_WE | mV | `so2_we_mv` | stored only |
| `63d0ebc89f18d` | SO2_AUX | mV | `so2_aux_mv` | stored only |
| `63d0ebfa17c49` | O3_WE | mV | `o3_we_mv` | stored only |
| `63d0ec7aa5a61` | O3_AUX | mV | `o3_aux_mv` | stored only |
| `63d0ec9873bc3` | NO_WE | mV | `no_we_mv` | stored only |
| `63d0ecc9829f2` | NO_AUX | mV | `no_aux_mv` | stored only |
| `63d0ee3fcd99a` | Baromteric Pressure *(sic)* | mBa | `barometric_pressure_mba` | Pressure card (hPa), "!" marker while the value is outside 870–1085 hPa |
| `63d0eeb2aaeef` | Molecular Volume | ltr | `molecular_volume_ltr` | stored only |
| `641d7b36d4413` | CO_ppm *(unit says ppb)* | ppb | `co_ppb` | stored only |
| `6421673518c4f` | NO2_ppb | ppb | `no2_ppb` | stored only |
| `64216914170b7` | SO2_ppb | ppb | `so2_ppb` | stored only |
| `64216a7500e46` | O3_ppb | ppb | `o3_ppb` | stored only |
| `64216b8187e5e` | NO_ppb | ppb | `no_ppb` | stored only |
| `6422ae0f8147e` | Air Quality Index | Unit | `air_quality_index` | AQI card and chart, no health category |

An unknown code in `values` is kept in `unmapped_values` with the flag `unknown_parameter:<code>`. A code from the map that is missing gets `missing:<column>`.

## Source data-quality notes

These are source-side and are not corrected by K-COSMOS. They are served by `GET /api/environment/parameters` as `note`. They are not shown on the public page.

| Parameter | Note |
| --- | --- |
| Barometric pressure | A constant 150 "mBa". Not a plausible atmospheric value (~1010 mbar). Calibration unconfirmed. |
| CO_ppm | Name says ppm, unit says ppb. Kept as sent until Aeron confirms. |
| Air Quality Index | Calculation standard (US EPA, Indian NAQI, …) not confirmed, so no health category is assigned. |
| Relative Humidity | Unit "Per" not confirmed as percent. |

Other observations:

- Although the station reports every 60 s, the `latest` reading changes only about every 7 minutes and arrives 1.6–7.6 minutes after the sensor time (measured 2026-11-03). K-COSMOS therefore polls every 5 minutes.
- API v1 has no device-health block (network, battery, charging, device temperature).
