# K-COSMOS

## Kumaraguru Climate Observatory and Sustainability Monitoring System

K-COSMOS is a sustainability intelligence and environmental monitoring platform.

## Applications

### Public Dashboard
`apps/public-dashboard`

Public sustainability, GHG, energy, water, waste, green cover,
community outreach and environmental monitoring dashboard.

### Manager/Admin Portal
`apps/manager-admin`

Authenticated institutional workflow for manager submissions,
administrative review, correction, approval and publication.

## Backend Services

### Main API
`services/main-api`

FastAPI service responsible for authentication, authorization,
sustainability submissions, review, calculations and publication.

### Aeron Environmental API
`services/aeron-api`

FastAPI service responsible for Aeron environmental synchronization,
normalization, storage and latest/history/status APIs.

### Report Generation
`services/report-generation`

Report generation engine and templates.

## Database

PostgreSQL.

Primary schemas:

- identity
- sustainability
- publication
- audit
- environmental

Main database migrations are maintained under:

`services/main-api/alembic`

Aeron environmental schema currently exists under:

`services/aeron-api/database`

## Deployment

Deployment configuration belongs under:

`deployment/`

Final Docker Compose and Nginx integration are completed during
the deployment/integration phase.

## Security

Real secrets must never be committed to this repository.

Use `.env.example` files as configuration templates.

## Documentation

Operational, deployment, backup, database and architecture
documentation is under `docs/`.
