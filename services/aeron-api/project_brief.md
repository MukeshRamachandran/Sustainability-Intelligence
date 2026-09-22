# Project Brief: Aeron Environment Dashboard

## Overview
We are maintaining the **Aeron Environment Dashboard**, a custom dashboard that syncs environmental data from the Aeron Live3 platform. 

## The Issue & Our Investigation
The local dashboard was displaying no data. The user correctly suspected a domain mismatch between the old `aeron.live` API and the new `live3.aeronsystems.com` dashboard. 

Here is what we did to investigate and fix:
1. **Domain Correction:** We updated the `.env` file to use `https://api.aeronsystems.com/v3` instead of the old `https://api.aeron.live/v3` endpoint. 
2. **Added Resiliency:** We updated `backend/services/aeron_sync_service.py` to add a retry-with-backoff mechanism (up to 3 retries). Previously, the sync job would fail silently. Now it handles transient network failures gracefully and logs errors properly to the `AeronSyncLog` table.
3. **Triggered Sync:** We re-ran the sync endpoint (`/api/sync/aeron`).

## Conclusion: Real Outage
While the domain `aeron.live` was indeed incorrect (returning a Cloudflare 525 SSL error), updating the domain to `api.aeronsystems.com` revealed that **there is still a genuine outage on Aeron's side**. 

When querying the new correct domain, Cloudflare returns a **502 Bad Gateway** error. This confirms that Aeron's origin API servers are currently down or unreachable, even on the correct domain. 

## Deliverables Completed
- [x] **Corrected `.env` values:** Updated to `api.aeronsystems.com/v3`.
- [x] **Corrected `.env.example`:** Reflected the new required template structure.
- [x] **Corrected sync client code:** Added retry-with-backoff logic to `aeron_sync_service.py` to handle origin outages.
- [x] **Confirmed Root Cause:** The root cause is a combination of both—a wrong domain, followed by a real outage on the correct domain.

We must wait for Aeron to resolve their 502 Bad Gateway API server outage before the local DB will populate.
