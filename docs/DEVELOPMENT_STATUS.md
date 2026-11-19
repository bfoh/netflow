# Development Status

_Last updated: 2026-11-19 — FortiGate 101F staging procedures (firmware, base restore,
site script with the tunnel key from the credential store, revisions; experimental, bench
run pending); startup database check; on top of the TFTP server, 2930F firmware, console
bootstrap, the 2930F platform, configuration import, SSH drivers, credentials, firmware
manager, topology._

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
| FortiGate 101F staging | Firmware by TFTP; base file restored by TFTP (replace mode, checked by hostname/VDOM/version, wrong-model backups refused); site script statement by statement (multi-VDOM, hostname change, error-looking reply stops the run); tunnel key inserted from the credential store, never stored or shown; revision named after each file. **Tested against a fake FortiGate only; not yet run on hardware** |
| Database check | Startup comparison of the database with the migrations; banner with the exact command; clear database errors |
| 2930F complete files | Team files recognised at import (address after loading, authorized managers, HTTPS-only and certificate caution, TFTP client switched off, bare password lines, duplicate VLANs, secrets counted); loaded by TFTP into the startup configuration with restart, address followed, serial and hostname checked, device address updated. **Fake switch only; not yet run on hardware** |
| Identity after restarts | Serial number re-checked after every restart (firmware, restore, load); a different unit at the address fails the job |
| Login after loading | A plan can name the credential valid once a file is applied (the 2930F files set the approved password); used after the restart and kept for the device once verified (audited) |
| Black Box files | LIG1014A (CLI text) and LE2700A (XML) configuration files recognised at import (complete file → replace; where the switch answers after loading; access settings; base64 "encrypted" password and SNMP exposure flagged; hostile XML refused); both models in the catalog with a **simulated** driver only |
| Supplied-file recognition | FortiOS files are classified offline at import (full backup vs CLI script), with structure check, what the file will change about access, and a count of secrets (never the values). A file cannot be applied in a way that does not fit its kind |
| Live progress | The deployment page refreshes every 2 s while a job runs and shows the device's last output when a step fails |
| Topology | Canvas (React Flow), interface links with mode/VLANs, saved layout, auto-arrange, validation (interface reuse, self links, subnet mismatch, VLANs, duplicate IPs, isolated devices) |
| Audit & logging | All significant actions, redacted details and device output |
| Console bootstrap (provisioning) | ArubaOS-Switch over a serial console from the PC running UNDM: new units' mandatory first-login credentials set to the device's attached login (D-043); per-device settings (VLAN, port, address), command preview, factory-default check, stop on first error, read-back before `write memory`, idempotent re-run, transcript (raw + sanitized). **Tested against a simulated console only; not yet run on hardware** |
| Sanitized diagnostics | Shareable report of last retrieved device output with IPs, MACs, serials, names and secrets masked |
| Migrations | Three Alembic revisions; batch mode; tested on SQLite with existing data and on PostgreSQL |

## What is simulated or experimental
- Simulated drivers: all three families, full feature set including firmware.
- SSH drivers: **experimental** — tested only against fake connections with synthetic
  output; no real device has been contacted. Parsers may not match real output.
- Real-device firmware: Aruba 2930F and FortiGate procedures exist, experimental; every
  other real model is reported incompatible. The devices' exact wording is unverified (Q-25).
- Templates: docs-reviewed, not lab-verified.

## Not implemented
Authentication and RBAC (attribution header only — keep the backend on localhost);
provisioning for FortiGate and Black Box, zero-touch provisioning; the staging run
across all four devices; full-configuration push to the 2930F; FortiGate first login (by
hand, Q-24); Black Box drivers; vendor signature verification;
replace mode and rollback for real devices; addressing plans and site hierarchy; template
library; intent beyond the first slice; project export/import; persistent job runner
(deployments run inside the HTTP request — long real-device runs block that request).

## Test results (2026-11-19)
| Suite | Result |
|---|---|
| Backend pytest | 316 passed, 2 skipped (PostgreSQL suite skips without DB URL) |
| Backend PostgreSQL integration | 2 passed; `alembic check`: no pending changes; new migration down/up OK |
| SQLite migration of previous-version data | upgrade → downgrade → upgrade OK, data intact |
| ruff / mypy --strict | clean / clean (73 files) |
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
owner: the 2930F screen after `crypto pki enroll-self-signed` (Q-34), the password prompts on a
new unit (Q-35), and Black Box command output from a spare unit (Q-28). Bench runs owed: 2930F
console bootstrap and firmware; FortiGate 101F staging.

## Next milestone
1. **Bench runs** (product owner): 2930F console bootstrap and firmware
   (`vendor-support/aruba-2930f-*.md`); FortiGate 101F firmware, base, site, revisions
   (`vendor-support/fortigate-101f-bench.md`). Correct wording and waiting times against what
   the units really print (Q-25); keep the output as fixtures.
2. **2930F complete-file load**: built (experimental), with the login after loading; bench
   run with `vendor-support/aruba-2930f-staging.md`. Certificate step inside UNDM after Q-34.
3. Black Box LIG1014A and LE2700A: real load procedure once the switch's own command output
   (Q-28) or the web upload details (Q-27, Q-29) are available; file recognition and a
   simulated driver exist for both.
4. The one-screen staging run across the four devices.
5. FortiGate first login inside UNDM, if agreed (Q-24).
6. Authentication and roles; persistent job runner.
