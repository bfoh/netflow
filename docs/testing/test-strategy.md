# Test Strategy

| Layer | Tool | Location | What it proves |
|---|---|---|---|
| Domain unit | pytest | `backend/tests/test_lifecycle.py`, `test_intent_and_configgen.py` | State-machine gates, intent validation, golden template output |
| Driver contract | pytest | `test_driver_contract.py` | Every registered driver: complete info, structured UNSUPPORTED for missing capabilities, clean failure when disconnected |
| Orchestration scenarios | pytest + simulated lab | `test_orchestrator.py` | Success, dry run, approval, identity mismatch, backup failure, apply failure + rollback, no-rollback manual recovery, partial apply detected by verification, idempotence, replace mode, unreachable device |
| API integration | pytest + FastAPI TestClient (in-memory SQLite) | `test_api.py` | CRUD, validation, policies, full deployment flow, locking, crash recovery, audit, redaction |
| SSH drivers | pytest + fake Netmiko connections (synthetic output) | `test_ssh_drivers.py` | Parameters, error mapping, fact parsing, comment stripping, merge apply, partial-apply reporting, policy gates end-to-end |
| Credentials | pytest + in-memory keyring | `test_credentials.py` | Secrets stored outside the DB, never returned, deleted with the reference; clear error without an OS store |
| Firmware | pytest | `test_firmware_orchestrator.py`, `test_firmware_api.py` | Checksum rules, approval, compatibility, window, second approver, downgrade/upgrade-path refusal, rollback, device not returning after reboot |
| Topology | pytest | `test_topology.py` | Validation rules and API |
| Database integration | pytest + PostgreSQL | `test_postgres.py` (needs `UNDM_TEST_DATABASE_URL`) | Alembic migrations apply and match models; full flow on PostgreSQL |
| Security helpers | pytest | `test_redaction.py` | Secrets masked in dicts, CLI text, log records |
| Frontend unit | Vitest + Testing Library | `frontend/tests/` | Navigation modules, dashboard aggregation, inventory indicators, API client errors/headers |
| End-to-end | Playwright | `frontend/e2e/acceptance.spec.ts`, `features.spec.ts` | Directive 28 flow; config import, topology link drawing, firmware upload → approve → plan → second-person approval → simulated upgrade |
| Static checks | ruff, mypy --strict, tsc, oxlint | — | Style, types |

Simulated failure injection: `SimulatedDevice(reachable=False, fail_on={...}, ignored_lines={...})`.

Planned: scenario library with authentication failure, timeouts and mid-deployment
interruption driven from the UI; transport-level tests with recorded sessions for real
drivers; accessibility checks (axe) in E2E.
