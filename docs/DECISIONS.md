# Decisions

Format: context → decision → consequences. Newest last.

### D-001 Modular monolith with src-layout package `undm` (2026-11-17)
Single deployable backend with strict internal layers is simplest to run on an
engineer's workstation and keeps boundaries testable. `src/` layout avoids import
mistakes. Later extraction (workers, site provisioning agent) goes along existing
package boundaries.

### D-002 PostgreSQL primary; SQLite for tests and development fallback (2026-11-17)
PostgreSQL is the supported store (directive 7). The ORM models avoid
PostgreSQL-only types so in-memory SQLite gives fast tests and a no-admin fallback on
workstations. A dedicated test suite (`test_postgres.py`) runs the migrations and the
full flow on PostgreSQL and checks that migrations match the models. SQLite is not
supported for shared use.

### D-003 Deployment state names follow directive 15, plus RECOVERING (2026-11-17)
States: DRAFT, VALIDATING, AWAITING_APPROVAL, READY, PREFLIGHT, BACKING_UP, DEPLOYING,
VERIFYING, RECOVERING, SUCCEEDED, FAILED, ROLLED_BACK, RECOVERY_REQUIRED, CANCELLED.
RECOVERING is added so that a crash during rollback is distinguishable. FAILED is used
only when no device was changed.

### D-004 Execution runs in-request for now; job runner decision deferred (2026-11-17)
Simulated deployments finish in milliseconds. Every lifecycle step is committed as it
happens and interrupted runs are resolved at startup, so a crash cannot leave a
deployment looking untouched. Before real devices (Phase 5) a persistent runner is
required. Evaluation criteria: no extra infrastructure on a workstation, retries only
for idempotent steps, visibility, cancellation. Leading candidate: a PostgreSQL-backed
queue (e.g. a jobs table with `SELECT … FOR UPDATE SKIP LOCKED`, or the Procrastinate
library), which avoids adding Redis/RabbitMQ. Celery/RQ/Dramatiq rejected for now
because they add a broker.

### D-005 Frontend: Mantine + TanStack Query + React Router (2026-11-17)
Mantine provides accessible inputs, tables, modals, steppers and theming without a CSS
framework build step. TanStack Query handles server state and invalidation. Topology
library (likely React Flow) to be chosen in Phase 3; not installed yet.

### D-006 Built-in templates are package code with a verification status (2026-11-17)
Templates are versioned with the code and covered by golden tests. Each declares the
intent features it supports and a `verification` status
(`docs_reviewed_not_lab_verified` for all current ones). User template libraries will
live in the database (Phase 2).

### D-007 Verification is textual for now (2026-11-17)
Merge mode: every intended line must be present in the read-back running config.
Replace mode: normalized running config must equal the intended config. This is
adequate for the simulation; real platforms will need platform-aware parsing (config
normalization, defaults, ordering) and structured verification (e.g. via APIs).

### D-008 Actor header is attribution, not authentication (2026-11-17)
`X-UNDM-Actor` records who acted in the audit trail during Phase 1. The backend must
only listen on localhost until authentication (milestone M1) exists.

### D-009 No global "enable impacting actions" switch (2026-11-17)
TNDM shows such a checkbox (SC-03). UNDM classifies every operation as read-only or
impacting; read-only operations run directly, impacting ones only via a deployment plan
with preview, approval, backup and verification. This is stricter and auditable.

### D-010 Device locks are a column claimed atomically (2026-11-17)
`devices.locked_by_deployment_id` is set with one conditional UPDATE for all targets;
if fewer rows than targets are claimed the transaction is rolled back. Works on
PostgreSQL and SQLite; survives process restarts (released by startup recovery).

### D-011 Device environment attribute with policy (2026-11-17)
Every device is `simulated`, `lab` or `production`. Simulated drivers may only be used
with simulated devices and vice versa, so a simulation can never be mistaken for
equipment. Deployments to production devices are disabled by default
(`UNDM_ALLOW_PRODUCTION_DEPLOYMENTS=false`).

### D-012 Preflight checks device identity (2026-11-17)
If an inventory record has an observed serial number, preflight refuses a device that
reports a different one (protects against wrong IP / replaced hardware).
