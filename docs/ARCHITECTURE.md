# Architecture

UNDM is a **modular monolith**: one backend process with strictly layered,
independently testable packages, plus a browser frontend. This keeps local
installation simple (directive 7: runs on an engineer's workstation) while the
module boundaries allow later extraction of workers or a provisioning agent.

## Layers and dependency direction

```
 Browser (React SPA)
        │  HTTP/JSON (OpenAPI at /api/docs)
 ┌──────▼─────────────────────────────────────────────────────────┐
 │ api/        FastAPI routers, request/response schemas, deps     │
 ├────────────────────────────────────────────────────────────────┤
 │ services/   use cases + transaction boundaries + audit          │
 ├───────────────┬───────────────┬──────────────┬─────────────────┤
 │ orchestration │ configgen     │ inventory    │ security        │
 │ (deployment   │ (intent →     │ (model       │ (redaction,     │
 │  state mach.) │  config, diff)│  catalog)    │  credential refs)│
 ├───────────────┴───────┬───────┴──────────────┴─────────────────┤
 │ drivers/  contract, registry, mock/ (simulated lab)             │
 ├───────────────────────▼────────────────────────────────────────┤
 │ domain/   enums, intent model, validation, lifecycle, impact    │
 └────────────────────────────────────────────────────────────────┘
 db/  SQLAlchemy models + sessions (used by api/services only)
```

Rules: `domain`, `configgen`, `orchestration` and `drivers` never import `api`,
`db` or FastAPI. Vendor-specific code exists only in `drivers/` and
`configgen/templates/`.

## Mapping to directive section 8

| Directive subsystem | Package | Status |
|---|---|---|
| 8.1 Presentation | `frontend/` | Implemented (Phase 1 modules) |
| 8.2 Application API | `undm.api` | Implemented; **authentication not yet** |
| 8.3 Network intent engine | `undm.domain.intent`, `undm.domain.validation` | First slice |
| 8.4 Configuration generation | `undm.configgen` | First slice, 3 platform templates |
| 8.5 Driver & capability framework | `undm.drivers` (`mock/`, `ssh/`) | Implemented; SSH drivers experimental |
| 8.6 Provisioning engine | — | Planned (Phase 6); mock `provision_factory_default_device` exists |
| 8.7 Deployment orchestrator | `undm.orchestration`, `undm.services.deployments` | Implemented (simulation) |
| 8.8 Firmware lifecycle | `undm.services.firmware`, `undm.orchestration.firmware`, `undm.domain.firmware` | Implemented for simulated devices |
| 8.9 Inventory & topology | `undm.inventory`, `undm.domain.topology`, `api.routers.topology` | Inventory and first topology version done |
| 8.10 Security & audit | `undm.security`, `undm.services.audit`, `undm.services.policy` | Audit, redaction, OS-keyring credentials, real-device policy; auth/RBAC planned |
| 8.11 Testing & simulation | `undm.drivers.mock`, `backend/tests` | Implemented |

## The five states the architecture keeps apart (directive 3)

| Concept | Where it lives |
|---|---|
| Desired design | `Device.intent` (vendor-neutral `DeviceIntent`) |
| Current device state | `Device.observed_facts`, backups (`ConfigVersion kind=backup`) |
| Configuration needed | `ConfigVersion kind=generated` (+ diff computed at preview/preflight) |
| Deployment operation | `DeploymentRecord`, `DeploymentTargetRecord`, `DeploymentEventRecord` |
| Verified state | Target state `verified`/`no_change`, `Device.deployment_status=in_sync` |

## Configuration pipeline (directive 13)

```
DeviceIntent ──validate_intent──► platform support check ──► Jinja2 renderer
  (Pydantic,      (duplicates,       (template declares        (StrictUndefined,
   typed)          overlaps, ...)     supported features)       per-platform)
                                             │
                     GenerationResult(text, issues, template_version, verification)
                                             │
                          ConfigVersion (sha256, immutable) ──► deployment plan
```
Unsupported intent produces an error, never silently dropped output.

## Deployment lifecycle (directive 4.4 / 15)

```
DRAFT → VALIDATING → AWAITING_APPROVAL → READY → PREFLIGHT → BACKING_UP → DEPLOYING → VERIFYING → SUCCEEDED
              │            (dry run: VALIDATING → READY, PREFLIGHT → SUCCEEDED)
              └→ FAILED (nothing changed)            DEPLOYING/VERIFYING ─failure→ RECOVERING → ROLLED_BACK
                                                                                            └→ RECOVERY_REQUIRED
CANCELLED from DRAFT / AWAITING_APPROVAL / READY
```
- Validation + preview are read-only; preflight checks reachability, **device identity**
  (serial number vs inventory) and capabilities for *all* targets before any change.
- Backup of every target precedes the first change.
- Success is decided by reading configuration back (verification), never by
  "command sent".
- Each step is committed as it happens; on startup, deployments found in a transient
  state are resolved (`RECOVERY_REQUIRED` if devices may have changed) and device
  locks are released (`recover_interrupted_deployments`).
- Device locks (`Device.locked_by_deployment_id`, claimed atomically for all targets)
  prevent concurrent conflicting deployments.
- Execution is currently synchronous inside the request (adequate for simulation).
  A persistent job runner is a planned change (see DECISIONS D-004).

## Data model (current)

| Table | Purpose |
|---|---|
| `projects` | Network project (name unique) |
| `credential_refs` | Pointer (provider + locator) to a secret held outside UNDM |
| `devices` | Inventory: declared attributes, environment, driver, intent (JSON), observed facts (JSON), status, lock |
| `config_versions` | Immutable generated configs and backups, sha256, template version, verification status |
| `deployments` | Deployment header: state, dry-run, apply mode, creator, approver |
| `deployment_targets` | Device + exact config version + backup version + per-device state, diff, message |
| `deployment_events` | Ordered event log per deployment |
| `audit_events` | Who/what/target/when/outcome + redacted details |
| `firmware_images` | Repository entries: version, platform, sha256, vendor checksum, compatibility, status |
| `topology_links` | Interface-to-interface links with mode and VLANs |
| `topology_positions` | Canvas layout only |

`deployments.kind` is `configuration` or `firmware`; firmware deployments also store the
image and the maintenance window, and their targets store from/to versions.

Planned (directive 21): users, roles, sites, vendors/models as tables, interfaces,
links, VLAN/IP allocation, templates, firmware images and compatibility, approvals as
a separate table.

## Frontend

React 19 + TypeScript + Vite, Mantine (components), TanStack Query (server state),
React Router. Modules: Dashboard, Projects, Network Elements, Topology*, Configuration
Studio, Provisioning*, Firmware*, Deployment Center, Logs & Audit, Settings
(*placeholder pages that state they are not implemented). The dev server proxies
`/api` to the backend, so the browser talks to one origin.

## Repository structure vs the suggested layout (directive 22)

| Suggested | Actual | Why |
|---|---|---|
| `backend/app/...` | `backend/src/undm/...` | `src` layout prevents accidental imports from the working directory and makes the package installable; `undm` is a unique import name. |
| `backend/models`, `schemas` | `db/models.py`, `api/schemas.py` | Keeps persistence models and API schemas next to the layer that owns them. |
| `backend/deployment`, `configurations` | `orchestration/`, `configgen/` | Names describe the responsibility. |
| `templates/fortinet|aruba|cisco` (top level) | `backend/src/undm/configgen/templates/` | Built-in templates are versioned code shipped with the package and covered by golden tests. User-defined template libraries will be stored in the database (Phase 2). |
| `lab/mocks`, `fixtures`, `scenarios` | `backend/src/undm/drivers/mock/`, `backend/tests/` | The simulated lab is used by the running app (demo mode), so it is part of the package. Scenario files will be added when scenarios become data-driven. |
| `docs/architecture`, `requirements`, ... | `docs/*.md` + `reference-analysis/`, `vendor-support/`, `testing/` | Section 25 names top-level files; sub-folders are created only when they hold content. |
