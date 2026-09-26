# Aeron real API contract — verified

Verified live on 2026-09-25 (03:18–04:04 UTC) against station **Air Quality KCT**. This replaces the earlier "blocked" report: the blocker was the wrong Python path; the project-local interpreter `C:\Projects\AERON-PLAYWRIGHT\AQI-integration--main\.venv\Scripts\python.exe` (Python 3.13.14, Playwright 1.63.0, Chromium 153 headless) works.

Every statement below comes from a real authenticated response. No secret was printed, logged, persisted or committed. The sanitized sample is [`services/main-api/tests/fixtures/aeron/aeron_real_sample_sanitized.json`](services/main-api/tests/fixtures/aeron/aeron_real_sample_sanitized.json).

## Authentication

| Question | Verified result |
| --- | --- |
| Stored `AERON_SESSION_COOKIE` valid? | **No.** The internal route returned HTTP 401 `application/json`. |
| Stored `AERON_LOGIN_URL` usable? | **No.** It is an Auth0 `/u/login?state=…` link whose state has expired, so no form renders. |
| Working login entry | `https://live3.aeronsystems.com/dashboard` redirects to `auth.aeronsystems.com` with a fresh state. The existing `cookie_manager` selectors then work unchanged (username → Continue → password → submit → `**/dashboard**`). |
| Login success | **Yes.** It took about 20 s end to end. A single credential submission per login; no retries. |
| Session material | Cookies for `live3.aeronsystems.com` (Auth0 / `__session__*`). The shortest-lived cookie expires about **1 hour** after login. |
| Browser needed after login? | **No.** The browser is closed immediately. Plain HTTP requests carrying those cookies succeeded 0, 5 and 10 minutes later, and the K-COSMOS worker reused one session across cycles (`login_performed=false`). |
| Public API-key route `GET https://api.aeronsystems.com/v3/devices/{station_id}/latest` | **HTTP 404.** Not a working route; `AERON_API_KEY` / `AERON_BASE_URL` are not used. |

Conclusion: **Playwright is needed only to obtain or refresh the session, not on every poll.**

## Verified reading endpoint

| Item | Value |
| --- | --- |
| Method / route | `GET https://live3.aeronsystems.com/api/stations/{station_id}/readings?mode=latest&region=india` |
| Identifier | `station_id` = Aeron station UUID `b1ce41c2-586a-4a26-9382-9d8bfe757e78` (timezone `Asia/Kolkata`, type XTM-XG930) |
| Auth | `Cookie` header from the Playwright session |
| Response | HTTP 200, `application/json`, 1100 bytes, a non-empty object |
| Unauthenticated / expired | HTTP 401 `application/json` (`{"error": …}`) |

The Aeron dashboard itself also calls these routes (observed, same session):

- `…/readings?mode=latest&coalesce=1&region=india`: same shape and `recordedAt`.
- `…/readings?from=<UTC ISO>&to=<UTC ISO>&limit=300&region=india`: a JSON **array** of the same objects. It returned 244 rows at 1-minute spacing.
- `…/parameters?scope=live&region=india`: parameter metadata (ID, caption, unit).
- `…/health?region=india`: `recordedAt`, `receivedAt`, `health`, `stationStatus`.

Only `mode=latest` is used for ingestion. History backfill is possible but not implemented.

## Payload shape

```json
{
  "recordedAt": "2026-09-24T22:34:00.000Z",
  "health":   {"fuse": 0, "gpsfix": 0, "supply": 0, "battery": 0, "network": 4, "charging": 0, "DeviceTemp": 0, "network_reg": 1},
  "location": {"Altitude": 0, "Latitude": 0, "Longitude": 0},
  "data":     {"<parameter id>": <number>, "...": "35 entries"}
}
```

## Field contract

Captions and units are exactly what Aeron's `/parameters?scope=live` returned; all 35 are neither hidden nor retired. No unit conversion is applied. Every metric in the sample was present and numeric; K-COSMOS stores a missing or non-numeric value as `NULL` with a quality flag. "Can be null" therefore means *K-COSMOS tolerates absence*; a real null has not yet been observed.

| Raw ID | Source caption | Type | Sanitized example | Source unit | Can be null? | K-COSMOS field | Existing UI |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `63d0da020016a` | CO | float | 0.130831 | mg/m3 | tolerated | `co_mg_m3` | CO tile |
| `63d0da885f1a0` | NO2 | float | 87.967484 | ug/m3 | tolerated | `no2_ug_m3` | NO₂ tile |
| `63d0daa4740ba` | SO2 | float | 1.671602 | ug/m3 | tolerated | `so2_ug_m3` | SO₂ tile |
| `63d0daf2bcb74` | O3 | float | 14.11762 | ug/m3 | tolerated | `o3_ug_m3` | O₃ card |
| `63d0db066e993` | NO | float | 0.000789 | ug/m3 | tolerated | `no_ug_m3` | NO tile |
| `63d0db8f77ecb` | PM 2.5 | float | 4.693056 | ug/m3 | tolerated | `pm25_ug_m3` | PM2.5 card + chart |
| `63d0dbb867a7c` | PM 10 | float | 9.93737 | ug/m3 | tolerated | `pm10_ug_m3` | PM10 card + chart |
| `63d0dbfe0a111` | Ambient Temperature | float | 27.113262 | degC | tolerated | `temperature_c` | Temperature card + chart |
| `63d0dc28f109d` | Relative Humidity | float | 69.387342 | Per (percent) | tolerated | `relative_humidity_percent` | Humidity card + chart |
| `63d0dc5164112` | RAIN | int/float | 0 | mm | tolerated | `rain_mm` | Rainfall card + chart |
| `63d0dd3721886` | Wind Speed | float | 1.044231 | kmph | tolerated | `wind_speed_kmph` | Wind card + chart |
| `63d0dd4ff30c9` | Wind Direction | float | 22.948194 | Deg | tolerated | `wind_direction_deg` | Wind direction card |
| `63d0ddf115956` | Noise Average | float | 45.288128 | db | tolerated | `noise_average_db` | Noise average |
| `63d0de104027f` | Min value of Noise level | float | 45.28212 | db | tolerated | `noise_min_db` | Noise minimum |
| `63d0de34a0b72` | Max value of Noise level | float | 45.306344 | db | tolerated | `noise_max_db` | Noise maximum |
| `63d0de7568a3b` | UV | float | 0.109317 | index | tolerated | `uv_index` | UV card |
| `63d0ea1253e8f` | CO2 | float | 383.406878 | ppm | tolerated | `co2_ppm` | CO₂ card |
| `63d0ea927306d` | CO_WE | float | 375.793326 | mv | tolerated | `co_we_mv` | stored, not shown |
| `63d0eb32b7070` | CO_AUX | float | 314.110443 | mV | tolerated | `co_aux_mv` | stored, not shown |
| `63d0eb591ee3a` | NO2_WE | float | 0.336311 | mV | tolerated | `no2_we_mv` | stored, not shown |
| `63d0eb7f49e34` | NO2_AUX | float | 242.685318 | mV | tolerated | `no2_aux_mv` | stored, not shown |
| `63d0eba20cd96` | SO2_WE | float | 241.793286 | mV | tolerated | `so2_we_mv` | stored, not shown |
| `63d0ebc89f18d` | SO2_AUX | float | 234.342885 | mV | tolerated | `so2_aux_mv` | stored, not shown |
| `63d0ebfa17c49` | O3_WE | float | 353.526063 | mV | tolerated | `o3_we_mv` | stored, not shown |
| `63d0ec7aa5a61` | O3_AUX | float | 339.811142 | mV | tolerated | `o3_aux_mv` | stored, not shown |
| `63d0ec9873bc3` | NO_WE | float | 282.154628 | mV | tolerated | `no_we_mv` | stored, not shown |
| `63d0ecc9829f2` | NO_AUX | float | 278.498042 | mV | tolerated | `no_aux_mv` | stored, not shown |
| `63d0ee3fcd99a` | Baromteric Pressure *(sic)* | int | 150 | mBa | tolerated | `barometric_pressure_mba` | Pressure card ("verify calibration" note) |
| `63d0eeb2aaeef` | Molecular Volume | float | 166.372899 | ltr | tolerated | `molecular_volume_ltr` | stored, not shown |
| `641d7b36d4413` | CO_ppm *(unit says ppb)* | float | 0.777293 | ppb | tolerated | `co_ppb` | stored, not shown |
| `6421673518c4f` | NO2_ppb | float | 318.162494 | ppb | tolerated | `no2_ppb` | stored, not shown |
| `64216914170b7` | SO2_ppb | float | 4.340745 | ppb | tolerated | `so2_ppb` | stored, not shown |
| `64216a7500e46` | O3_ppb | float | 48.90828 | ppb | tolerated | `o3_ppb` | stored, not shown |
| `64216b8187e5e` | NO_ppb | float | 0.004572 | ppb | tolerated | `no_ppb` | stored, not shown |
| `6422ae0f8147e` | Air Quality Index | int | 107 | Unit (index) | tolerated | `air_quality_index` | AQI card + chart |
| `health.network` | — | int | 4 | 0–4 bars | tolerated | `network` | "Signal 4/4" badge |
| `health.battery` | — | int | 0 | not stated | tolerated | `battery` | production UI health row |
| `health.charging` | — | int | 0 | flag | tolerated | `charging` | production UI health row |
| `health.DeviceTemp` | — | int | 0 | not stated | tolerated | `device_temp` | production UI health row |
| `recordedAt` | — | string | `2026-09-24T22:34:00.000Z` | UTC instant | **required** | `observed_at` | status bar + chart x-axis |

`health.fuse`, `gpsfix`, `supply`, `network_reg` and `location` are real but unused; they are retained in `raw_payload`. The existing UI shows 19 metrics plus the network signal. It shows **no metric the source lacks**, and the source has **no metric the UI requires but K-COSMOS lacks**. The fields stored but not shown are the 10 electrochemical mV channels, the 5 ppb gas channels and molecular volume.

### Data-quality observations (source-side, not K-COSMOS defects)

- Barometric pressure is a constant `150` "mBa" across all 244 readings on 2026-09-25. That is not a plausible atmospheric value (~1010 mbar), so it points to a sensor or calibration fault. The UI already carries a "Verify sensor calibration" note.
- AQI stayed at `107` for 4 hours, which suggests a rolling or daily index rather than an instantaneous one.
- Health `battery`, `supply` and `DeviceTemp` are `0`, and `location` is `0/0/0`.
- **The station stopped reporting at 2026-09-24 22:34 UTC (04:04 IST).** Aeron's own dashboard showed "4 hrs ago", and station `lastDataAt` is `22:38:56Z`. Every live poll through 04:04 UTC returned that same reading.

## Timestamp contract

| Question | Verified answer |
| --- | --- |
| Raw field | `recordedAt` |
| Formats | `latest`: `2026-09-24T22:34:00.000Z`; history: `2026-09-24 18:30:00+00`. Both are ISO 8601 with an explicit UTC designator. |
| Unix seconds / milliseconds? | No |
| Semantics | **True UTC measurement instant**, not IST mislabelled as `Z` |
| **+330 correction** | **NOT REQUIRED.** The legacy normalizer that added it was **wrong**. |

Evidence:

1. Aeron's `/health` reports `receivedAt 22:34:14Z`, 14 s after `recordedAt 22:34:00Z`. With +330, the measurement would fall 5 h 30 m *after* Aeron received it.
2. Aeron's own dashboard, rendered at 03:25:05Z, labelled the reading **"4 hrs ago"** (actual age 4 h 51 m). With +330 it would be 45 minutes in the *future*.
3. The dashboard requests "today" as `from=2026-09-24T18:30:00.000Z` / `to=2026-09-25T18:29:59.999Z`. That is exactly the IST calendar day expressed in true UTC.
4. Aeron's HTTP `Date` header matched the local clock to the second.

Worked example:

```
raw source      2026-09-24T22:34:00.000Z
parsed          2026-09-24 22:34:00+00:00  (aware)
UTC instant     2026-09-24 22:34:00Z       (stored as observed_at, unchanged)
Asia/Kolkata    2026-09-25 04:04:00+05:30  (display only)
```

K-COSMOS stores `observed_at` (Aeron measurement time, UTC) and `ingested_at` (K-COSMOS storage time, UTC) separately. Naive timestamps are rejected rather than guessed.

## Two-reading verification

| Check | Result |
| --- | --- |
| Measurement timestamp advances | **Yes in history:** 244 distinct, strictly ascending timestamps at 1-minute spacing (18:30Z → 22:34Z). **Not yet observed via `latest`**, because the station has not reported since 22:34Z. |
| Station ID stable | Yes; the same UUID appears in every response and route. |
| Live values, not a static fixture | Yes. Across 244 rows, temperature took 244 distinct values (26.86–27.60 °C) and PM2.5 took 244 (4.10–34.31 µg/m³). |
| Session reuse | Yes; cookies worked for 10+ minutes with the browser closed. |

## Error behaviour (verified or tested)

| Case | Behaviour |
| --- | --- |
| Expired or invalid session | HTTP 401 → the worker logs in once and retries once. A second rejection records `SESSION_EXPIRED`, with no loop. |
| Login failure | `AUTH_FAILED`. Further logins are paused (5 min doubling to 1 h, `AUTH_BACKOFF`) to prevent lockout. |
| Timeout / network | `TIMEOUT` / `NETWORK_ERROR`; nothing is stored. |
| Non-JSON, `{}`, `[]`, `null` | `MALFORMED_RESPONSE`; nothing is stored. |
| JSON without sensor data / bad `recordedAt` | `INVALID_READING`; nothing is stored. |
| Same `recordedAt` again | `DUPLICATE`; no new row. |

Run records store only these fixed codes, never upstream text.
