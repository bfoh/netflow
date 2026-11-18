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

### D-013 Credentials live in the OS credential store (2026-11-18)
`keyring` gives Windows Credential Manager / macOS Keychain / Secret Service without extra
infrastructure, matching the "runs on an engineer's workstation" goal. The database keeps
only a reference. Secrets are write-only through the API. When no OS store exists (e.g. a
headless Linux container) the API says so and the `env` provider remains available.

### D-014 First real drivers: SSH CLI via Netmiko, marked experimental (2026-11-18)
Netmiko 4.8 provides `aruba_aoscx`, `fortinet` and `cisco_xe` device types, so one generic
SSH driver plus small platform classes cover all three initial families. Session behaviour
was checked in Netmiko's source: AOS-CX `no page` and IOS-XE `terminal length 0` are
session-only; FortiOS may temporarily change `config system console / set output` and
restores it on disconnect (documented to the user). Netmiko does not implement saving for
FortiOS; the driver reports reliance on FortiOS' default automatic save instead of claiming
a save. Capabilities declared: SSH, backup, merge apply. Not declared: replace, rollback,
firmware — the orchestrator therefore ends failures in manual recovery. Fact parsers are
best-effort and tested only with synthetic output until lab validation.

### D-015 Real-device safety switches (2026-11-18)
See `undm.services.policy` and SECURITY_BOUNDARIES. Read-only access to lab devices is on;
writes, production read-only and production deployments each need an explicit setting,
re-checked at execution time. The header shows whether real-device changes are enabled.

### D-016 Platform-aware verification hooks (2026-11-18)
Real devices print configuration with their own indentation and hide defaults (`no shutdown`).
Drivers expose `expected_lines()` / `present_lines()`; the orchestrator compares those.
Simulated drivers keep exact (indentation-sensitive) comparison.

### D-017 Imported configurations are deployed as-is (2026-11-18)
User-supplied files are normalised (BOM, CRLF) and stored as immutable `imported`
versions with `verification=user_supplied_not_validated`; they are not checked against
intent. The UI labels them and recommends comparing with the latest backup first.

### D-018 Firmware workflow (2026-11-18)
Images must have a vendor SHA-256 that matches before approval; approved, non-retired
images only; offline compatibility by platform + model list + minimum-version rule;
downgrades refused. Plans require a maintenance window (≤ 24 h) and an approver who is not
the creator, regardless of the general separate-approver setting. Devices are upgraded one
at a time, stopping at the first failure. Real drivers declare no firmware capability:
per-model procedures need vendor documentation and lab validation first. Vendor signature
verification is not implemented.

### D-019 Topology: graph is the truth, positions are layout (2026-11-18)
Links connect named interfaces of two devices and carry mode (routed/access/trunk) and
VLANs. Positions are stored separately and not audited. Validation: interface used twice,
self links, subnet mismatch on routed links, access-link VLAN count, VLANs missing from
device intent, duplicate IPs across the project, isolated devices. React Flow 13 (MIT).

### D-020 Alembic batch mode (2026-11-18)
Migrations run in batch mode so they work on SQLite (the documented workstation fallback,
which cannot ALTER columns) as well as PostgreSQL. Upgrade/downgrade was tested on a SQLite
database containing data from the previous version.

### D-021 Aruba 2930F is a separate platform: ArubaOS-Switch (2026-11-19)
The 2930F runs ArubaOS-Switch (ProCurve lineage), not AOS-CX: different CLI, config format
(per-VLAN contexts closed with `exit`, quoted names, masks written out) and firmware naming
(`WC.16.x`). Added platform `aos_switch` with its own template, simulated driver and
experimental SSH driver (Netmiko `aruba_osswitch`, behaviour checked in Netmiko's source).
The device edit form warns when a driver's OS does not match the device's OS.

### D-022 Sanitized diagnostics for sharing real output (2026-11-19)
Real outputs are needed to validate drivers, but may identify sites and equipment. The
diagnostics export masks IPs, MACs (incl. HP format), serials, names/contacts/locations and
secrets with stable placeholders, from data UNDM already stored (no device contact).
Pattern-based, so the user reviews it before sharing.

### D-023 Real output becomes fixtures with fictional identifiers (2026-11-19)
Sanitized real output is stored under `backend/tests/fixtures/<model>_<firmware>/` with the
exact layout and whitespace kept, and masked identifiers replaced by fictional values, so
parsers are tested against what devices really print. Drivers state the model/firmware
combinations their parser was checked on (`parser_validated_on`), shown in the facts.

### D-024 Merge previews show intended lines, not a full diff (2026-11-19)
Found while preparing the first real dry run: a full unified diff of the running config
against a few intended lines showed nearly the whole real configuration as "removed",
although merge mode removes nothing. Merge previews now list each intended line as "+"
(will be added) or unchanged (already present), using the driver's verification hooks.
Replace mode keeps the full diff. The intent editor defaults the hostname to the observed
hostname and warns before a rename.
