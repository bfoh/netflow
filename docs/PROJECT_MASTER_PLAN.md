# Project Master Plan

A phase is complete only with working tests and acceptance evidence, not when code exists.

| Phase | Goal | Exit criteria | State |
|---|---|---|---|
| 0 Discovery & architecture | Environment check, requirements, architecture, driver contract, data model, roadmap, conventions, CLAUDE.md | Documents in `docs/`, skeleton builds | **Done** |
| 1 Foundation | FastAPI, React, DB, navigation, project + inventory CRUD, model registry, mock drivers, validation, tests | Directive 28 items 1–7, 15 | **Done** |
| 2 Configuration generation | Intent models, templates, capability validation, rendering, preview, versioning, comparison | Directive 28 items 8–10 + template library, more intent concepts | **Started**: first intent slice, 3 templates, versions, diff. Missing: template library, parameters, secret variables, more concepts |
| 3 Topology | Canvas, placement, interface links, VLAN/IP planning, persistence, validation | Graph model + validation tests + UI | **First version done** (canvas, links, validation). Missing: addressing plans, site hierarchy |
| 4 Simulated deployment | Plans, state machine, approval, mock execution, verification, history, recovery | Directive 28 items 11–14 | **Largely done in simulation**. Missing: persistent job runner, dependency ordering, timeouts/cancellation mid-run, scenario library (timeouts, auth failure, interruption via UI) |
| 5 Lab integrations (read-only) | Identify, retrieve info, backup, capability detection on approved lab devices | Per-model acceptance tests on a named lab device | **Code ready (experimental SSH drivers), not yet run against a real lab device** |
| 6 Initial provisioning | One lab model via console or ZTP | Isolated lab, documented procedure | Not started |
| 7 Firmware | Inventory, offline compatibility; real operations only after lab validation | — | **Repository, compatibility, upgrade orchestration done (simulated)**. Real procedures: not started |
| 8 Enterprise hardening | RBAC, advanced audit, resumable jobs, secrets integration, policies, backup/restore docs | — | Not started (auth pulled forward, see below) |

## Next milestones (proposed order)
1. **M1 — Authentication and roles (pulled forward from Phase 8).** Directive 19 asks
   for security from the beginning; the API currently trusts an attribution header.
   Local accounts with hashed passwords, sessions/tokens, roles: viewer, engineer
   (generate), approver, operator (execute), admin; enforce on every endpoint;
   separate-approver policy on by default.
2. **M2 — Phase 2 completion.** Template library (versioned, parameters, secret
   variables via credential refs), intent for access/trunk ports, DNS, NTP, SNMP,
   syslog, admin access; per-platform feature matrix in the UI.
3. **M3 — Phase 4 hardening.** Persistent job runner (decision D-004), cancellation,
   timeouts, scenario library and UI for failure injection in the simulated lab.
4. **M4 — Phase 3 topology.** Graph model (devices, interfaces, links), React Flow canvas,
   validation; addressing plans (RA-04).
