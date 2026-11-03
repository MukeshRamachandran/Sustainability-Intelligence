# K-COSMOS Project Map

## Public application

Path:
apps/public-dashboard

## Manager and Admin application

Path:
apps/manager-admin

## Main FastAPI service

Path:
services/main-api

Responsibilities:
- authentication
- authorization
- manager submissions
- admin review
- correction workflow
- approval
- sustainability calculations
- publication
- read-only Aeron environment API (latest/history/status/parameters)

## Aeron environmental ingestion

Path:
services/main-api/app/environment

Responsibilities:
- Aeron REST API v1 polling with a Bearer API key (worker only, every 5 min by default)
- sensor normalization and validation
- environmental persistence (`environment` schema)
- freshness classification

Runs as the `environment-worker` container (same image as the API,
`python -m app.environment.worker`). Guide:
`docs/reports/AERON_INTEGRATION_ARCHITECTURE.md`.

## Report generation

Path:
services/report-generation

## Main PostgreSQL migrations

Path:
services/main-api/alembic

The Aeron `environment` schema is migration `0012_environment_readings`;
`0018_aeron_api_v1` adds the API v1 provenance columns.

## Legacy Supabase reference

Path:
docs/legacy/supabase-reference

This directory is historical/reference material only.
It is not part of the active production runtime.

## Deployment

Path:
deployment

## Cross-application tests

Path:
tests

## Private runtime information

Real environment files, PostgreSQL backups and emergency Docker
disk backups are stored outside this repository.
