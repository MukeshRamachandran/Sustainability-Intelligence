# K-COSMOS delivery source of truth

- Public dashboard: `C:\Users\Ram\Downloads\microcosm-website\microcosm-website`
- Manager/admin portal: `C:\Users\Ram\Downloads\Mukesh_sustainability`
- FastAPI backend: this `microcosm-backend` directory
- Reference only: `C:\Users\Ram\Downloads\Mukesh_sustainability\Microcosm-Dashboard` public-dashboard copy and its `supabase` directory

Legacy/reference files are retained but must not receive delivery changes.

## Checkpoint 2 portal routing map

Authentication and authorization must come from `GET /api/auth/session`; the
portal's existing `localStorage.currentUser` and browser-controlled role switch
are demo behavior and are not part of the production path.

- Unauthenticated: login page
- Transport manager: manager home, transport/DG entry, own history
- Energy manager: manager home, energy/renewable entry, own history
- LPG manager: manager home, LPG entry, own history
- Water manager: manager home, water entry, own history
- MICROCOSM admin: overview, review queue, factors, release preview, audit/history

The existing demo-role buttons, sample autofill, editable calculated totals,
manager-supplied LPG factor, and prefilled water-lab values remain untouched in
the reference UI at Checkpoint 1. They are explicitly excluded from the
production route and must be removed or development-gated during Checkpoint 2.
