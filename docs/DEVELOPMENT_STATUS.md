# Development Status

_Last updated: 2026-11-19 — ArubaOS-Switch (Aruba 2930F) platform and sanitized diagnostics,
on top of configuration import, real-device SSH drivers (experimental), credentials,
firmware manager and topology designer._

## What works (implemented and tested)
| Area | Details |
|---|---|
| Projects & inventory | CRUD; device edit form; environment (simulated / lab / production) with rules; declared vs observed data; search, filters, bulk read-only actions |
| Credentials | Stored in the OS credential store (Windows Credential Manager on Windows); write-only through the API; attached per device |
| Real devices (experimental) | SSH drivers for ArubaOS-Switch (2930F), AOS-CX, FortiOS, IOS-XE: test connection, facts (best-effort parsing, raw output kept), backup, merge apply + save. Gated by policy switches (see SECURITY_BOUNDARIES) |
| Intent & generation | Hostname, VLANs, L3 interfaces, static routes → AOS-CX / FortiOS / IOS-XE templates; validation; platform support checks |
| Configuration import | Upload a file per device; normalised, versioned, labelled unvalidated; selectable per device in deployment plans |
| Deployments | Lifecycle with directive-15 states; dry runs; approval; preflight with identity check; backup; verification by read-back (platform-aware for SSH drivers); rollback or manual recovery; device locks; crash recovery on restart |
| Firmware | Repository with SHA-256 vs vendor checksum, approval/retire/delete; offline compatibility; upgrade plans with maintenance window and second approver; stage/install/reboot/wait/verify; rollback or manual recovery — **simulated devices only** |
| Topology | Canvas (React Flow), interface links with mode/VLANs, saved layout, auto-arrange, validation (interface reuse, self links, subnet mismatch, VLANs, duplicate IPs, isolated devices) |
| Audit & logging | All significant actions, redacted details and device output |
| Sanitized diagnostics | Shareable report of last retrieved device output with IPs, MACs, serials, names and secrets masked |
| Migrations | Two Alembic revisions; batch mode; tested on SQLite with existing data and on PostgreSQL |

## What is simulated or experimental
- Simulated drivers: all three families, full feature set including firmware.
- SSH drivers: **experimental** — tested only against fake connections with synthetic
  output; no real device has been contacted. Parsers may not match real output.
- No real-device firmware procedure exists; real devices are reported incompatible.
- Templates: docs-reviewed, not lab-verified.

## Not implemented
Authentication and RBAC (attribution header only — keep the backend on localhost);
provisioning workflows (console/ZTP); real-device firmware; vendor signature verification;
replace mode and rollback for real devices; addressing plans and site hierarchy; template
library; intent beyond the first slice; project export/import; persistent job runner
(deployments run inside the HTTP request — long real-device runs block that request).

## Test results (2026-11-19)
| Suite | Result |
|---|---|
| Backend pytest | 165 passed, 2 skipped (PostgreSQL suite skips without DB URL) |
| Backend PostgreSQL integration | 2 passed; `alembic check`: no pending changes |
| SQLite migration of previous-version data | upgrade → downgrade → upgrade OK, data intact |
| ruff / mypy --strict | clean / clean (56 files) |
| Frontend Vitest | 11 passed |
| tsc / oxlint / vite build | clean / clean / success |
| Playwright E2E | 2 tests, 6/6 passed over 3 repeated runs (acceptance flow; import + topology + firmware) |

## Known issues and limitations
- SSH verification is textual (stripped line presence); real platforms may display some
  lines differently than sent, which would show up as verification failure → manual recovery.
- FortiOS template writes static routes as IDs 1..n (warning shown).
- FortiOS SSH sessions may temporarily change the console output mode (see support matrix).
- Simulated device state is in memory and resets on backend restart.
- `npm audit`: picomatch ReDoS advisory in build tooling, no fix released (see README).
- Production build is a single large JS chunk.

## Next milestone
1. **Aruba 2930F lab acceptance, phase A (read-only)** — steps 3 (test connection) and
   4 (retrieve information: all fields parsed, WC.16.10.0025) done on 2026-11-19; steps 5–8 pending — product owner runs
   `docs/vendor-support/aruba-2930f-acceptance.md` and shares the sanitized diagnostics;
   fix parser/verification against the real output and keep it as a fixture; then phase B
   (one supervised VLAN change). Firmware version of the unit still to be confirmed.
2. Authentication and roles (M1).
3. Persistent job runner so long real-device deployments do not block the HTTP request.
