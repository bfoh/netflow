# Requirements

Status values: **Done** (implemented and tested), **Partial**, **Planned** (phase noted),
**Backlog** (not yet scheduled). "Simulated" means it works against simulated devices only.

## FR-PRJ — Projects
| ID | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| FR-PRJ-01 | Create, list, view, update, delete projects | API + UI; duplicate names rejected (409) | Done |
| FR-PRJ-02 | Project holds site, purpose, description | Fields editable in UI | Done |
| FR-PRJ-03 | Projects persist across restarts | Data present after backend restart (PostgreSQL) | Done |
| FR-PRJ-04 | Archive and clone projects | — | Planned (Phase 2) |
| FR-PRJ-05 | Export/import with readable header and schema-version check | See RA-05 | Planned (Phase 2/3) |
| FR-PRJ-06 | Project templates | — | Planned (Phase 2) |
| FR-PRJ-07 | User-defined site hierarchy and device groups | See RA-03 | Planned (Phase 3) |

## FR-INV — Inventory
| ID | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| FR-INV-01 | Structured device record (directive 9 fields) | All fields stored; validated enums | Done (except template assignment) |
| FR-INV-02 | Declared vs observed data kept separate | `observed_facts` only written by retrieval | Done |
| FR-INV-03 | Device model registry | `/api/device-models`; support level shown | Done (code catalog) |
| FR-INV-04 | Environment attribute: simulated / lab / production with visible indicator | Simulated driver ⇔ simulated environment enforced; badge everywhere | Done |
| FR-INV-05 | Searchable inventory with multi-select bulk actions | Search, vendor/category filters, read-only bulk actions | Done |
| FR-INV-06 | Credential references (no secrets in inventory) | `credential_refs` table; env-var provider | Partial (API only, no UI) |
| FR-INV-07 | Supported capabilities shown per device | From driver declaration | Done |

## FR-INT / FR-CFG — Intent and configuration
| ID | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| FR-INT-01 | Typed vendor-neutral intent: hostname, VLANs, L3 interfaces, static routes | Pydantic model; invalid input → 422 | Done |
| FR-INT-02 | Intent validation: duplicate VLANs/interfaces, overlapping subnets, invalid host address, SVI without VLAN, unreachable next hop | Errors block generation; warnings do not | Done |
| FR-INT-03 | Further concepts (access/trunk ports, DNS, NTP, SNMP, logging, AAA, zones, policies, NAT, dynamic routing) | — | Planned (Phase 2+) |
| FR-CFG-01 | Platform capability validation: unsupported intent reported, never silently dropped | Error `feature_not_supported_by_platform` | Done |
| FR-CFG-02 | Render candidate config for aoscx, fortios, iosxe | Golden tests | Done (docs-reviewed, not lab-verified) |
| FR-CFG-03 | Version configurations (immutable, sha256) | Each generation stored | Done |
| FR-CFG-04 | Preview and compare versions (generated vs generated/backup) | Diff endpoint + UI | Done |
| FR-CFG-05 | Template library, versioned, user parameters, secret variables resolved securely | — | Planned (Phase 2) |
| FR-CFG-06 | Per-firmware-version template selection | — | Planned (Phase 5) |

## FR-DEP — Deployment
| ID | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| FR-DEP-01 | Explicit lifecycle state machine (directive 15 states) | Illegal transitions raise; tests cover gates | Done |
| FR-DEP-02 | Dry run: read-only, no approval needed | Device config and checkpoints unchanged | Done |
| FR-DEP-03 | Explicit approval for live deployments; optional separate-approver policy | 403/409 when violated | Done |
| FR-DEP-04 | Preflight: reachability, identity (serial), capabilities for all targets before any change | Identity mismatch blocks | Done |
| FR-DEP-05 | Backup of every target before first change | Backup stored as ConfigVersion | Done |
| FR-DEP-06 | Verification by read-back | Partial apply detected | Done (textual line check) |
| FR-DEP-07 | Automatic rollback where supported; manual recovery reported otherwise | ROLLED_BACK / RECOVERY_REQUIRED | Done |
| FR-DEP-08 | Device locking against concurrent deployments | Second deployment → 409 | Done |
| FR-DEP-09 | Interrupted-process detection on restart | Transient states resolved, locks released | Done |
| FR-DEP-10 | Production deployments disabled by policy | 403 for production devices | Done |
| FR-DEP-11 | Each target bound to exact config version and device | FK + stored ids | Done |
| FR-DEP-12 | Persistent background jobs with progress, cancellation mid-run, timeouts | — | Planned (Phase 4/8) |
| FR-DEP-13 | Dependency ordering and failure containment for multi-device plans | — | Planned (Phase 4) |

## FR-PRV / FR-FW — Provisioning and firmware
| ID | Requirement | Status |
|---|---|---|
| FR-PRV-01 | Provisioning approaches A–D (directive 16) with status tracking | Planned (Phase 6); simulated driver operation only |
| FR-FW-01 | Firmware inventory, integrity, compatibility, controlled upgrade | Planned (Phase 7); simulated driver operations only |

## FR-TOP — Topology
| ID | Requirement | Status |
|---|---|---|
| FR-TOP-01 | Graph-based topology designer with interface links and validation | Planned (Phase 3) |

## FR-SEC / FR-AUD — Security and audit
| ID | Requirement | Acceptance criteria | Status |
|---|---|---|---|
| FR-AUD-01 | Audit every significant action: actor, action, target, time, outcome, sanitized details | Audit entries for create/update/delete/generate/deploy/approve/execute/operations | Done |
| FR-SEC-01 | Secrets redacted from logs and audit | Tests for keys and CLI fragments | Done |
| FR-SEC-02 | User authentication | — | Planned (next milestone) |
| FR-SEC-03 | Role-based permissions (view, generate, approve, execute, firmware, credentials, admin) | — | Planned |
| FR-SEC-04 | Impacting operations only through deployment workflow | Direct call → 403 | Done |

## NFR — Non-functional
| ID | Requirement | Status |
|---|---|---|
| NFR-01 | Runs locally via browser without Docker/admin rights (SQLite fallback for dev) | Done |
| NFR-02 | Typed code: mypy strict (backend), TypeScript strict (frontend) | Done |
| NFR-03 | Automated tests at unit, contract, API, DB-integration, UI and E2E levels | Done (initial) |
| NFR-04 | Responsive, accessible UI (labels, keyboard, contrast) | Partial (labels/roles; no formal audit) |

## Prototype acceptance (directive 28)
| # | Criterion | Evidence |
|---|---|---|
| 1 | Start locally | README commands; verified in dev container |
| 2 | Open dashboard | E2E test |
| 3 | Create project | E2E + API tests |
| 4–5 | Add Aruba switch, Fortinet firewall | E2E |
| 6 | Both in inventory | E2E |
| 7 | Metadata and roles | E2E (role, address); API tests (all fields) |
| 8 | VLAN and management settings | E2E (VLAN 99 + management SVI / interface) |
| 9–10 | Generate, preview, validate via mock drivers | E2E |
| 11–13 | Simulated plan, run, inspect progress | E2E (approve, execute, outcome, targets, events) |
| 14 | Audit record | E2E |
| 15 | Restart without data loss | Verified manually against PostgreSQL; `test_postgres.py` |
