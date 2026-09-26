# Integration checks

These paths are the production contract. They are verified on the VPS after Nginx and Cloudflare are in place, not by a laptop-only unit test.

Public dashboard:

```text
https://sustainability.kct.ac.in/
    -> Nginx :443
    -> 127.0.0.1:3001
    -> browser fetch /api/public/dashboard
    -> Nginx /api/
    -> FastAPI :8000
    -> PostgreSQL
```

Manager and admin portal:

```text
https://sustainability.kct.ac.in/admin/admin-login.html
    -> Nginx :443
    -> 127.0.0.1:3002
    -> POST /api/auth/login
    -> FastAPI session cookie
    -> PostgreSQL
```

Run the public checks with:

```bash
deployment/scripts/health-check.sh
```

Unauthenticated `GET /api/auth/session` must return 401. A 500 means the API or database is failing, not that the visitor is logged out.

Sign-in with a real account, wrong-portal rejection, and password change stay manual. Do not put that password in the repository or in this script.
