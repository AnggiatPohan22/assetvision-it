
# AssetVision IT — Codex Engineering Guide

## Mission
Build a local-first IT asset inventory, recognition,
location tracking, and audit system.

Initial scale: fewer than 500 physical assets.

Development hardware:
- Windows with Ubuntu WSL2
- 16 GB system RAM
- NVIDIA RTX 3050 4 GB
- No mandatory GPU inference
- Zero recurring infrastructure cost target

## Technology
- Next.js App Router + TypeScript
- FastAPI + Python
- PostgreSQL + PostGIS
- SQLAlchemy 2.x + Alembic
- Docker Engine + Docker Compose
- Pytest + frontend automated tests

## Architecture
- Modular monolith
- REST API under /api/v1
- PostgreSQL is the source of truth
- Backend owns all business authorization
- Keep AI, OCR, and storage behind interfaces
- No mandatory Ollama or paid cloud services

## Domain rules
1. DeviceModel and AssetUnit are separate entities.
2. Asset IDs are immutable.
3. Serial numbers may be missing or damaged.
4. Location alone never proves physical identity.
5. Survey observations do not directly overwrite
   approved asset master data.
6. Asset movements require an auditable history.
7. Unknown devices must be supported.
8. AI output is evidence, not final authority.
9. Important changes must be auditable.
10. Never silently overwrite concurrent changes.

## Sprint 0 scope
Implement:
- Monorepo foundation
- PostgreSQL/PostGIS
- FastAPI skeleton
- Next.js skeleton
- Database migrations
- Basic authentication
- Role-based authorization
- Health checks
- Smoke and authentication tests

Do NOT implement:
- AI recognition
- OCR
- Asset movement workflows
- Camera capture
- Cloud infrastructure
- Redis or microservices

## Authentication
- Password hashing with Argon2id
- Short-lived signed access tokens
- HTTP-only cookies for browser sessions
- Backend RBAC: ADMIN, OFFICER, VIEWER
- No public registration
- No hardcoded credentials
- No JWT secrets in Git

## Coding requirements
- Use typed Python and TypeScript
- Keep modules small and testable
- Use Alembic for schema changes
- Validate input with Pydantic
- Enforce authorization server-side
- Do not expose database ports publicly
- Never commit real asset data or photos
- Document all environment variables

## Testing
- Run backend unit and API tests
- Run frontend lint and type checks
- Verify database migrations
- Verify login and unauthorized access
- Report actual results, not assumptions

## Codex behavior
- Work on one bounded task at a time
- Review existing files before editing
- Explain architectural changes
- Do not invent successful test results
- Do not delete user data
- Do not change domain invariants
- End each task with changed files,
  executed commands, and test results
