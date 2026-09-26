# K-COSMOS Transfer Checklist

## Transfer to the new machine

Transfer:
- K-COSMOS-FINAL
- K-COSMOS-PRIVATE securely
- emergency Docker VHDX backup separately if needed

## Do not transfer as source dependencies

These are recreated:
- node_modules
- Python virtual environments
- caches
- Docker images
- Docker containers
- Docker build cache

## Install on new machine

- Git
- Python
- Node.js
- Docker Desktop
- development editor/tools

## Recreate

1. Python virtual environments
2. Node dependencies
3. Docker images
4. Docker containers
5. PostgreSQL volume

## Database

- Run current migrations on clean PostgreSQL
- Recover existing database data if required
- Immediately create a PostgreSQL pg_dump after recovery

## Final integration

- Main FastAPI
- PostgreSQL
- Manager/Admin portal
- Public dashboard
- Aeron API
- Nginx
- Docker Compose
- Backup automation

## Verification

Do not delete the original project folders until the transferred
system passes complete end-to-end testing.
