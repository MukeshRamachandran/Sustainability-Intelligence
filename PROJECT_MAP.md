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

## Aeron environmental service

Path:
services/aeron-api

Responsibilities:
- Aeron upstream API communication
- sensor normalization
- environmental persistence
- latest/history/status APIs
- protected synchronization

## Report generation

Path:
services/report-generation

## Main PostgreSQL migrations

Path:
services/main-api/alembic

## Aeron database schema

Path:
services/aeron-api/database

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
