# API tests

The FastAPI suite lives with the service:

```bash
cd services/main-api
python -m pytest
```

It covers authentication, CSRF, sessions, admin authorization, manager domain isolation, user creation, password reset, health, validation, and database constraints. PostgreSQL integration tests use `TEST_DATABASE_URL` and are skipped when that variable is unset.

`tests/test_admin_user_schema.py` checks that `POST /api/admin/users` accepts the production payload (`domain`, `role`, `email`) and the existing `manager_domain` field.
