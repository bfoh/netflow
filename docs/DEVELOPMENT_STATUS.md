# Development Status

_Last updated: 2026-11-17 — end of first assignment (Phase 0 + Phase 1 foundation)._

## Environment inspected (Task 1)
Linux container (Ubuntu 24.04, x86_64), Python 3.13, Node.js 22, npm 10, PostgreSQL 16
(local), Docker CLI present but unused, uv available, Chromium + Playwright 1.63
preinstalled. The product owner's workstation is unknown (TNDM screenshots suggest
Windows), so the README gives Windows commands and a SQLite fallback that needs no
administrator rights.

## What works (implemented and tested)
| Area | Details |
|---|---|
| Backend app | FastAPI, OpenAPI at `/api/docs`, structured JSON logging with redaction, settings via `UNDM_*` env vars |
| Persistence | SQLAlchemy 2 models, Alembic initial migration, PostgreSQL verified; data survives restart |
| Projects | CRUD (API + UI) |
| Inventory | Device CRUD with directive-9 fields, environment attribute + rule enforcement, declared vs observed data, capabilities, search/filter, multi-select bulk read-only actions |
| Device model registry | 6 catalog entries (Aruba CX, FortiGate, Cisco Catalyst/ISR), all `simulated_only` |
| Driver framework | Contract, capability model, registry, structured UNSUPPORTED results; 3 simulated drivers with distinct capability profiles; simulated lab with failure injection |
| Intent + config generation | Typed intent (hostname, VLANs, L3 interfaces, static routes), semantic validation, platform feature checks, templates for aoscx/fortios/iosxe, immutable versions with sha256, version diff |
| Read-only device operations | Reachability, retrieve facts (stored as observed), backup, firmware info — via API and UI |
| Deployments | Full lifecycle with directive-15 states, dry run, approval (optional separate approver), preflight with identity check, backup, merge/replace apply, read-back verification, rollback or manual-recovery reporting, device locks, per-step persistence, startup recovery of interrupted deployments, production-deployment policy |
| Audit | All significant actions with actor, target, outcome, redacted details; UI with filter |
| Frontend | Dashboard, Projects, Network Elements, device detail (overview / intent editor / configurations / activity), Configuration Studio, Deployment Center (plan, approve, execute, stepper, diffs, event timeline), Logs & Audit, Settings (identity, drivers, models, system); Topology/Provisioning/Firmware placeholders that say they are not implemented |
| Demo data | `python -m undm.seed`: "Demo Branch Site" with a simulated Aruba switch and FortiGate (synthetic addresses) |

## What is mocked
- **All devices.** The only drivers are simulations (`mock.*`). The simulated lab is in
  memory: simulated device state (running config, checkpoints) resets when the backend
  restarts, while UNDM's own data (projects, versions, deployments, audit) persists.
- Capability profiles of the mock drivers are chosen to exercise code paths, not to
  describe real products.
- Templates follow public documentation conventions but are **not lab-verified**.

## Not implemented
Authentication and RBAC (attribution header only — run on localhost); topology designer;
site hierarchy and addressing plans; template library and user parameters; intent
concepts beyond the first slice; provisioning workflows; firmware management; project
export/import, archive, clone, templates; credential-reference UI; persistent job runner,
mid-run cancellation, timeouts; real drivers of any kind; drift detection.

## Test results (2026-11-17)
| Suite | Result |
|---|---|
| Backend pytest (unit, contract, orchestration, API, redaction, seed) | 91 passed, 2 skipped (PostgreSQL suite skips without DB URL) |
| Backend PostgreSQL integration (`UNDM_TEST_DATABASE_URL` set) | 2 passed; `alembic check`: no pending changes |
| ruff / mypy --strict | clean / clean (44 files) |
| Frontend Vitest | 7 passed |
| tsc / oxlint / vite build | clean / clean / success |
| Playwright E2E (directive 28 flow, real browser, simulated devices) | 1 passed |

## Known issues and limitations
- Verification is textual (line presence / equality); real platforms need normalization.
- Merge mode in the simulator appends lines; it does not model hierarchical config.
- Deployment execution is synchronous in the HTTP request (fine for simulation only).
- Production build is a single 600 kB JS chunk (code splitting not done yet).
- No formal accessibility audit yet.
- `npm audit` (2026-11-18): 1 advisory, picomatch <= 4.0.7 ReDoS (GHSA-fc5q-39xc-vjpf),
  reported as 8 "high" entries because vite, vitest, tinyglobby, fdir, postcss-mixins,
  postcss-preset-mantine and @vitejs/plugin-react depend on it. No patched release
  exists. Exposure: dev/build/test tooling only, patterns come from project config.
  Action: upgrade when picomatch publishes a fix; never use `npm audit fix --force`
  (it downgrades to Vite 6 / Vitest 3 with critical advisories).

## Next milestone
**M1 — Authentication and role-based access** (see `PROJECT_MASTER_PLAN.md`), then M2
(Phase 2 completion: template library, more intent concepts). Answers to the open
questions in `REFERENCE_ANALYSIS.md` (especially Q-01, Q-03, Q-05, Q-06) will shape M1,
M2 and Phase 5 planning.
