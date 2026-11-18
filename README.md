# UNDM — Universal Network Deployment Manager

Vendor-neutral network deployment platform: describe what each device should do,
generate vendor configurations, preview and approve changes, and deploy them with
backup, verification and recovery. This first prototype runs entirely against
**simulated devices**; it never contacts real equipment.

> Status: Phase 0 + Phase 1 foundation (see `docs/DEVELOPMENT_STATUS.md`).
> No real-device drivers exist yet. Listing a vendor or model does not mean it is supported.

## What you can do today
Create projects, add network elements (simulated Aruba AOS-CX, Fortinet FortiOS and Cisco
IOS-XE profiles), define vendor-neutral intent (hostname, VLANs, L3 interfaces, static
routes), generate and compare configurations, and run simulated deployments through
validate → preview → approve → preflight → backup → deploy → verify, with rollback or
manual-recovery reporting and a full audit trail.

## Run locally

Requirements: Python 3.12+, Node.js 20.19+ (22 recommended), and PostgreSQL 14+
(recommended). Without PostgreSQL you can use a local SQLite file for development.

### 1. Database (PostgreSQL)
```bash
psql -U postgres -c "CREATE ROLE undm LOGIN PASSWORD 'undm';"
```
```bash
psql -U postgres -c "CREATE DATABASE undm OWNER undm;"
```
These are local development credentials only. To skip PostgreSQL, set
`UNDM_DATABASE_URL=sqlite:///./undm-dev.db` in `backend/.env` (development only).

### 2. Backend (terminal 1)
Linux/macOS:
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/python -m undm.seed
.venv/bin/uvicorn --factory undm.api.app:app_factory --host 127.0.0.1 --port 8000
```
Windows (PowerShell):
```powershell
cd backend
py -3 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
Copy-Item .env.example .env
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m undm.seed
.venv\Scripts\uvicorn --factory undm.api.app:app_factory --host 127.0.0.1 --port 8000
```

### 3. Frontend (terminal 2)
```bash
cd frontend
npm ci
npm run dev
```
Open http://127.0.0.1:5173. API documentation: http://127.0.0.1:5173/api/docs.

Use `npm ci` instead of `npm install` to get exactly the tested versions from
`package-lock.json`. Do **not** run `npm audit fix --force`: it downgrades Vite and
Vitest to older releases with more serious advisories. As of 2026-11-18 `npm audit`
reports one advisory (picomatch ReDoS, GHSA-fc5q-39xc-vjpf) counted once per dependent
package; no fixed picomatch release exists, and it only affects build/test tooling
matching our own file patterns — nothing shipped to the browser. See
`docs/DEVELOPMENT_STATUS.md`.

## Tests
```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check src tests && .venv/bin/mypy src
```
```bash
cd frontend && npm test && npm run typecheck && npm run lint
```
End-to-end (with both servers running; first time run `npx playwright install chromium`):
```bash
cd frontend && npm run test:e2e
```

## Documentation
| Document | Purpose |
|---|---|
| `CLAUDE.md` | Rules and conventions for development sessions |
| `docs/PROJECT_MASTER_PLAN.md` | Phases, milestones, exit criteria |
| `docs/REQUIREMENTS.md` | Functional requirements, acceptance criteria, status |
| `docs/ARCHITECTURE.md` | Subsystems, data flow, data model |
| `docs/DEVICE_DRIVER_SPEC.md` | Driver contract and capability model |
| `docs/DEVELOPMENT_STATUS.md` | What works, what is mocked, what is missing |
| `docs/DECISIONS.md` | Architectural decisions and reasoning |
| `docs/SECURITY_BOUNDARIES.md` | Device access, data handling, secrets |
| `docs/REFERENCE_ANALYSIS.md` | Reference material index, REA record, open questions |
| `docs/reference-analysis/tndm-screenshot-catalog.md` | TNDM screenshot analysis |
| `docs/vendor-support/support-matrix.md` | What each vendor family supports today |
| `docs/testing/test-strategy.md` | Test layers and how to run them |
