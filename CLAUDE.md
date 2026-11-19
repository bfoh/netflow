# CLAUDE.md — Universal Network Deployment Manager (UNDM)

Read this file, then `docs/DEVELOPMENT_STATUS.md`, before starting work in a new session.
Do not rely on conversational memory for project state.

## Mission
A vendor-neutral platform for designing, configuring, provisioning, deploying and
maintaining network equipment (switches, routers, firewalls) across enterprise,
industrial and lab networks. Inspired by the *capabilities* of Motorola TNDM but
independent of it: no DIMETRA assumptions, no TNDM code, no TNDM assets.

## Non-negotiable rules
1. **No real devices from the development environment.** Claude never connects to, scans
   or changes real devices or networks. UNDM itself can reach real devices through the
   experimental SSH drivers, controlled by the safety switches in `undm.services.policy`
   (all off by default; firmware has its own switch). Never weaken those defaults; record named lab devices in
   `docs/SECURITY_BOUNDARIES.md`.
2. **No invented vendor facts.** Do not invent CLI commands, API endpoints, device
   capabilities or test results. Mark anything unverified as such (templates carry a
   `verification` status). Record unknowns in `docs/REFERENCE_ANALYSIS.md`.
3. **Mock ≠ support.** Simulated drivers prove the workflow, not hardware compatibility.
   Never describe a simulated driver as supporting a product.
4. **No secrets anywhere** in code, fixtures, commits, logs or screenshots. Credentials are
   referenced (`CredentialRef`), resolved at use time, and redacted from logs/audit.
5. **No reverse engineering of TNDM** (REA or otherwise) unless authorization is documented
   per directive section 6 in `docs/REFERENCE_ANALYSIS.md`. Current status: NOT authorized.
6. **Reference screenshots** are analysed for workflow only, never committed, and
   identifiers are replaced with placeholders.
7. Do not claim a feature works unless it is implemented **and** tested.

## Architecture rules
- Layers: `api` (HTTP) → `services` (use cases, transactions) → `orchestration` /
  `configgen` / `drivers` / `domain`. Domain, configgen, orchestration and drivers must
  not import `api`, `db` or FastAPI.
- Vendor specifics live only in `drivers/<vendor>` and `configgen/templates`. Core code
  branches on **capabilities**, never on vendor names.
- Every device-changing action goes through the deployment lifecycle
  (`domain/lifecycle.py`); no API endpoint may change a device directly. One exception:
  console bootstrap of factory-default devices (`services/provisioning.py`), which has
  its own safeguards (preview, typed confirmation, write switch, factory-default check,
  read-back before save, audit) — see DECISIONS D-025. Do not add other exceptions.
- Unsupported operations return `OperationResult.unsupported(...)`; they do not raise.
- Device dialogues answer only listed questions (`SshCliDriver._dialogue`); an unknown
  question ends the step with the device's text. Success needs independent evidence (D-031).
- A supplied configuration file is applied only in the way its kind requires
  (`inspect_config_file`, D-032). Real customer files are never committed; tests use
  synthetic files.
- Declared (user-entered) device data and observed (retrieved) data stay separate.

## Repository layout
```
backend/            FastAPI app, package `undm` (src layout)
  src/undm/api/       routers, schemas, dependencies
  src/undm/services/  use cases (devices, deployments, firmware, audit, policy)
  src/undm/orchestration/  deployment + firmware orchestrators (pure logic)
  src/undm/configgen/ intent -> config rendering, Jinja2 templates, diff
  src/undm/drivers/   driver contract, registry, mock/ simulated lab + drivers, ssh/ real (experimental),
                      fortinet/ FortiOS file recognition + SSH procedures (experimental),
                      blackbox/ Black Box file recognition
  src/undm/provisioning/  serial console sessions, console bootstrap procedures, simulated console
  src/undm/transfer/  built-in TFTP server (read-only, per job, per device) and its hub
  src/undm/domain/    enums, intent model, validation, lifecycle, operation impact
  src/undm/inventory/ device model catalog, driver/environment rules
  src/undm/db/        SQLAlchemy models, sessions
  src/undm/security/  redaction, credential references
  migrations/         Alembic
  tests/              pytest (unit, contract, API, PostgreSQL integration)
frontend/           React + TypeScript + Vite + Mantine
  src/pages, src/features, src/components, src/hooks, src/services, src/types
  tests/ (Vitest), e2e/ (Playwright)
docs/               requirements, architecture, decisions, status, security, references
```

## Commands
Backend (from `backend/`):
- install: `python -m venv .venv && .venv/bin/pip install -e ".[dev]"` (or `uv pip install -e ".[dev]"`)
- migrate: `.venv/bin/alembic upgrade head`   seed demo: `.venv/bin/python -m undm.seed`
- run: `.venv/bin/uvicorn --factory undm.api.app:app_factory --host 127.0.0.1 --port 8000`
- checks: `.venv/bin/pytest`, `.venv/bin/ruff check src tests`, `.venv/bin/mypy src`
- PostgreSQL tests: `UNDM_TEST_DATABASE_URL=postgresql+psycopg://undm:undm@localhost:5432/undm_test .venv/bin/pytest tests/test_postgres.py`
- new migration: `.venv/bin/alembic revision --autogenerate -m "..."`, then review it.

Frontend (from `frontend/`):
- `npm install`, `npm run dev` (proxies /api to 127.0.0.1:8000)
- checks: `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`
- e2e (both servers running): `npm run test:e2e`

## Conventions
- Python 3.12+, strict mypy, ruff; Pydantic models for API and intent; dataclasses for
  driver/orchestrator values. TypeScript strict; API types mirrored in `src/types/api.ts`.
- Tests first or alongside; every new driver must pass `tests/test_driver_contract.py`.
- Small commits; update `docs/DEVELOPMENT_STATUS.md` and `docs/DECISIONS.md` with changes.
- Use RFC 5737 / RFC 1918 addresses and fictional names in fixtures and examples.

## Primary use case
Staging four factory-default devices per system (FortiGate 101F, a Black Box switch,
two Aruba 2930F) from one laptop: `docs/requirements/staging-use-case.md` and
`docs/requirements/staging-run-design.md`; FortiGate two-file method in
`docs/vendor-support/fortigate-101f-staging.md`. Prioritise work that serves it.

## Current focus
See `docs/DEVELOPMENT_STATUS.md` ("Next milestone"). Real-device drivers are experimental
until acceptance-tested on named lab models; keep that label until then.
