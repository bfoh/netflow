# Development Status

_Last updated: 2026-11-18 — built-in TFTP server and the first real-device firmware
procedure (Aruba 2930F, experimental, bench run pending); FortiGate two-file method studied
and both file kinds recognised offline; on top of console bootstrap, the 2930F platform,
sanitized diagnostics, configuration import, SSH drivers, credentials, firmware manager,
topology. (Earlier entries dated 2026-11-19 were written on 2026-11-18.)_

## What works (implemented and tested)
| Area | Details |
|---|---|
| Projects & inventory | CRUD; device edit form; environment (simulated / lab / production) with rules; declared vs observed data; search, filters, bulk read-only actions |
| Credentials | Stored in the OS credential store (Windows Credential Manager on Windows); write-only through the API; attached per device |
| Real devices (experimental) | SSH drivers for ArubaOS-Switch (2930F), AOS-CX, FortiOS, IOS-XE: test connection, facts (best-effort parsing, raw output kept), backup, merge apply + save. Gated by policy switches (see SECURITY_BOUNDARIES) |
| Intent & generation | Hostname, VLANs, L3 interfaces, static routes → AOS-CX / FortiOS / IOS-XE templates; validation; platform support checks |
| Configuration import | Upload a file per device; normalised, versioned, labelled unvalidated; selectable per device in deployment plans |
| Deployments | Lifecycle with directive-15 states; dry runs; approval; preflight with identity check; backup; verification by read-back (platform-aware for SSH drivers); rollback or manual recovery; device locks; crash recovery on restart |
| Firmware | Repository with SHA-256 vs vendor checksum, approval/retire/delete; offline compatibility; upgrade plans with maintenance window and second approver; stage/install/reboot/wait/verify; rollback or manual recovery. Simulated devices, plus **one experimental real procedure: Aruba 2930F** (switch pulls the image from UNDM by TFTP into primary flash, restarts, version verified) behind `UNDM_ENABLE_REAL_DEVICE_FIRMWARE`. **Tested against a fake switch only; not yet run on hardware** |
| File transfer | Built-in TFTP server: read-only, per-job, per-device allowlist, transfer records; tested with an independent client |
| Supplied-file recognition | FortiOS files are classified offline at import (full backup vs CLI script), with structure check, what the file will change about access, and a count of secrets (never the values). A file cannot be applied in a way that does not fit its kind |
| Live progress | The deployment page refreshes every 2 s while a job runs and shows the device's last output when a step fails |
| Topology | Canvas (React Flow), interface links with mode/VLANs, saved layout, auto-arrange, validation (interface reuse, self links, subnet mismatch, VLANs, duplicate IPs, isolated devices) |
| Audit & logging | All significant actions, redacted details and device output |
| Console bootstrap (provisioning) | ArubaOS-Switch over a serial console from the PC running UNDM: per-device settings (VLAN, port, address), command preview, factory-default check, stop on first error, read-back before `write memory`, idempotent re-run, transcript (raw + sanitized). **Tested against a simulated console only; not yet run on hardware** |
| Sanitized diagnostics | Shareable report of last retrieved device output with IPs, MACs, serials, names and secrets masked |
| Migrations | Three Alembic revisions; batch mode; tested on SQLite with existing data and on PostgreSQL |

## What is simulated or experimental
- Simulated drivers: all three families, full feature set including firmware.
- SSH drivers: **experimental** — tested only against fake connections with synthetic
  output; no real device has been contacted. Parsers may not match real output.
- Real-device firmware: only the Aruba 2930F procedure exists, experimental; every other
  real model is reported incompatible. The switch's exact questions are unverified.
- Templates: docs-reviewed, not lab-verified.

## Not implemented
Authentication and RBAC (attribution header only — keep the backend on localhost);
provisioning for FortiGate and Black Box, zero-touch provisioning; the staging run
across all four devices; full-configuration push to real devices; FortiGate first login,
base restore, site-script runner, revisions and firmware; Black Box drivers; vendor signature verification;
replace mode and rollback for real devices; addressing plans and site hierarchy; template
library; intent beyond the first slice; project export/import; persistent job runner
(deployments run inside the HTTP request — long real-device runs block that request).

## Test results (2026-11-18)
| Suite | Result |
|---|---|
| Backend pytest | 249 passed, 2 skipped (PostgreSQL suite skips without DB URL) |
| Backend PostgreSQL integration | 2 passed; `alembic check`: no pending changes |
| SQLite migration of previous-version data | upgrade → downgrade → upgrade OK, data intact |
| ruff / mypy --strict | clean / clean (67 files) |
| Frontend Vitest | 14 passed |
| tsc / oxlint / vite build | clean / clean / success |
| Playwright E2E | 3 passed (acceptance flow; import + topology + firmware; console bootstrap on the simulated console) |

## Known issues and limitations
- Merge-mode previews list intended lines only (fixed 2026-11-19; previously the whole
  running configuration appeared as removed on devices with existing configuration).
- SSH verification is textual (stripped line presence); real platforms may display some
  lines differently than sent, which would show up as verification failure → manual recovery.
- FortiOS template writes static routes as IDs 1..n (warning shown).
- FortiOS SSH sessions may temporarily change the console output mode (see support matrix).
- Simulated device state is in memory and resets on backend restart.
- `npm audit`: picomatch ReDoS advisory in build tooling, no fix released (see README).
- Production build is a single large JS chunk.

## Primary use case (restated by the product owner 2026-11-19)
Staging four factory-default devices per system (FortiGate 101F, Black Box switch,
2 × Aruba 2930F) from one place: `docs/requirements/staging-use-case.md`, design and
build order in `docs/requirements/staging-run-design.md`. Still needed from the product
owner: sample configuration files, Aruba firmware versions, Black Box manuals and the
answers to Q-19…Q-22 (FortiGate order, credentials, expected messages) in
`REFERENCE_ANALYSIS.md`. Bench runs still owed: console bootstrap and firmware on a spare 2930F.

## Next milestone
1. **Bench runs on a spare 2930F** (product owner): console bootstrap
   (`vendor-support/aruba-2930f-console-bootstrap.md`), then firmware over TFTP
   (`vendor-support/aruba-2930f-firmware.md`). Fix the dialogue wording and waiting times
   against what the switch really prints; keep the output as fixtures.
2. **2930F full-configuration push** over TFTP, with the address/password change that the
   final configuration brings.
3. **FortiGate 101F**, once Q-19…Q-22 are answered: first-login password change, base
   restore, firmware, site-script runner (statement by statement), named revisions.
4. Black Box LIG1014A, then LE2700A (web-managed; investigate).
5. The one-screen staging run across the four devices.
6. Authentication and roles; persistent job runner (long jobs still run inside the HTTP
   request; the page now shows live progress while it waits).
