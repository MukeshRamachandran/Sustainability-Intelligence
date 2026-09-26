# Authentication

FastAPI owns authentication. The browser sends cookies to `/api/auth/...` on `https://sustainability.kct.ac.in`. It does not connect to PostgreSQL.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/login` | Password check, session cookie, CSRF cookie |
| GET | `/api/auth/session` | Current user, role, and domain. Anonymous callers get 401. |
| POST | `/api/auth/logout` | Revoke the server-side session. Requires CSRF. |
| POST | `/api/auth/change-password` | Replace the password and clear `must_change_password`. Requires CSRF. |

Passwords are hashed with Argon2id (`app/security/passwords.py`). Only the hash is stored. Login responses, user-admin responses, and logs must not contain the password, the hash, the session token, or the CSRF secret.

## Cookies

Production settings in `services/main-api/.env`:

- `SESSION_COOKIE_SECURE=true` (HttpOnly is set by the session code)
- `SESSION_COOKIE_SAMESITE=lax`
- idle timeout `SESSION_IDLE_MINUTES` (default 60)
- absolute timeout `SESSION_ABSOLUTE_HOURS` (default 8)

The session row is checked on each authenticated request. Logout and password reset revoke it. A copied cookie from a revoked session does not stay valid.

State-changing authenticated requests send the `X-CSRF-Token` header copied from the readable CSRF cookie. The session cookie itself is HttpOnly, so page script cannot read it.

## Roles and domains

Roles: `microcosm_admin` (administrator) and `manager`.

Manager domains: `transport`, `energy`, `lpg`, `water`, `outreach`, `waste`.

Every manager route checks the signed-in user, the manager role, and the assigned domain. A waste manager who changes a URL to a transport resource is rejected by the API. Hiding a button is not the control.

Login pages share `auth-client.js`, `role-auth.js`, and `role-login.js`. After `POST /api/auth/login` the page reads `GET /api/auth/session`, logs out when the role or domain does not match that page, and sends `must_change_password` users to `change-password.html`. The password field is cleared with `getElementById`, not `event.currentTarget`.

## Creating a manager

`POST /api/admin/users` requires an administrator session and a CSRF token.

```json
{
  "username": "waste@kct.ac.in",
  "display_name": "Waste Manager",
  "email": "waste@kct.ac.in",
  "role": "manager",
  "domain": "waste",
  "temporary_password": "set-a-long-temporary-password"
}
```

`manager_domain` is still accepted for the existing admin form. `role` must be `manager`. The temporary password is not returned.

Failed logins increment a counter and lock the account after `LOGIN_MAX_FAILURES` (default 5) for `LOGIN_LOCK_MINUTES` (default 15).

## Local development

Opening the manager pages from `http://127.0.0.1:3000` makes `auth-client.js` call port 8000 on that same host. That path is development-only. `sustainability.kct.ac.in` always uses a relative `/api/...` URL. Development CORS origins belong in a development `.env` only. Production rejects loopback origins and wildcard origins.
