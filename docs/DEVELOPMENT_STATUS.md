# Development Status

_Last updated: 2026-11-23 — first fully automatic 2930F file load on the bench; restart banner and
configuration after deployment; Stop for running deployments, runs continue on the server;
firmware plans can also write the secondary flash; first 2930F console
bootstrap and firmware downgrade on hardware (2026-11-19); FortiGate 101F staging procedures (firmware, base restore,
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
| Firmware | Repository with SHA-256 or SHA-512 vs vendor checksum (addable after upload); approval only when verified or with a written, audited reason (D-062); retire/delete; offline compatibility; upgrade plans with maintenance window and second approver; stage/install/reboot/wait/verify; rollback or manual recovery. Simulated devices, plus **one experimental real procedure: Aruba 2930F** (switch pulls the image from UNDM by TFTP into primary flash, restarts, version verified) behind `UNDM_ENABLE_REAL_DEVICE_FIRMWARE`. Experimental: **one successful run on hardware** (2026-11-19, spare JL260A, approved downgrade WC.16.11.0001 → WC.16.10.0025, verified) |
| File transfer | Built-in TFTP server: read-only, per-job, per-device allowlist, transfer records; a transfer under way is cancelled when its file is withdrawn or the job ends (D-063); tested with an independent client |
| FortiGate 101F staging | Firmware by TFTP; base file restored by TFTP (replace mode, checked by hostname/VDOM/version, wrong-model backups refused); site script statement by statement (multi-VDOM, hostname change, error-looking reply stops the run); tunnel key inserted from the credential store, never stored or shown; revision named after each file. Bench 2026-11-24: connection and facts passed on a 101F; the first firmware run was reported failed through a UNDM fault (progress marks taken for the prompt) while the unit went on to install 7.6.5 (fixed D-063; the corrected procedure is not yet run on hardware); the first base restore was stopped by UNDM after "File check OK." and the prompt (fixed D-064). **Otherwise tested against a fake FortiGate only** |
| Database check | Startup comparison of the database with the migrations; banner with the exact command; clear database errors |
| 2930F complete files | Team files recognised at import (address after loading, authorized managers, HTTPS-only and certificate caution, TFTP client switched off, bare password lines, duplicate VLANs, secrets counted); loaded by TFTP into the startup configuration with restart, address followed, serial and hostname checked, device address updated. **Fake switch only; not yet run on hardware** |
| Identity after restarts | Serial number re-checked after every restart (firmware, restore, load); a different unit at the address fails the job |
| 2930F HTTPS certificate | Created inside the load job before an HTTPS-only file, with the team's commands and the project's certificate subject (Project settings); already-existing certificate accepted. **Fake switch only** |
| Approved older firmware | Firmware plans can explicitly install the approved image on devices that run a newer one (new 2930F units ship with WC.16.11.0001); refused by default, flagged in preview, badge and audit |
| Erase preconfigured switches | Console bootstrap option for preconfigured units (BH-DMZ): log in with the saved current login, confirm the typed hostname, erase, wait for the restart, set up and bootstrap as new; audited; **worked on hardware** (BH-DMZ unit, 2026-11-23, one run from erase to saved bootstrap with the approved password set by UNDM; D-057, D-058) |
| Studio to deployment | "Deploy this version…" in the Configuration Studio opens a plan with the device and version chosen; links between plans and versions both ways (D-056) |
| Restarts and results visible | An event announces an apply that restarts the device; the plan page shows the latest step with its age and a "please wait" banner with a timer while a device restarts; the configuration read back after a change is kept per target (view / compare with what was sent); grouped verification warnings (D-055) |
| Stop and background runs | Runs continue on the server (the page follows the events); **Stop** ends a run at its next safe point with an honest outcome (failed if nothing changed, otherwise manual check naming the devices); restart waits name the address, and a 2930F load names the port to connect to (D-051) |
| Secondary image slot | Firmware plans can also write the approved image into the secondary flash (team standard), only after the primary runs it; devices already on the version get only the secondary; capability-based; 2930F procedure run once on hardware (2026-11-23, spare unit: both slots WC.16.10.0025, confirmed by `show flash`) (D-050) |
| Login after loading | A plan can name the credential valid once a file is applied (the 2930F files set the approved password); used after the restart and kept for the device once verified (audited) |
| Black Box files | LIG1014A (CLI text) and LE2700A (XML) configuration files recognised at import (complete file → replace; where the switch answers after loading; access settings; base64 "encrypted" password and SNMP exposure flagged; hostile XML refused); both models in the catalog with a **simulated** driver only |
| Supplied-file recognition | FortiOS files are classified offline at import (full backup vs CLI script), with structure check, what the file will change about access, and a count of secrets (never the values). A file cannot be applied in a way that does not fit its kind |
| Live progress | The deployment page refreshes every 2 s while a job runs and shows the device's last output when a step fails |
| Topology | Canvas (React Flow), interface links with mode/VLANs, saved layout, auto-arrange, validation (interface reuse, self links, subnet mismatch, VLANs, duplicate IPs, isolated devices) |
| Audit & logging | All significant actions, redacted details and device output |
| Console bootstrap (provisioning) | ArubaOS-Switch over a serial console from the PC running UNDM: new units' mandatory first-login credentials set to the device's attached login (D-043); per-device settings (VLAN, port, address), command preview, factory-default check, stop on first error, read-back before `write memory`, idempotent re-run, transcript (raw + sanitized). Experimental: **one complete run on hardware** (spare 2930F JL260A, WC.16.11.0001, new unit, 2026-11-19: credentials set, VLAN/address verified and saved); re-run and network check on that unit pending |
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

## Test results (2026-11-24)
| Suite | Result |
|---|---|
| Backend pytest | 392 passed, 2 skipped (PostgreSQL suite skips without DB URL) |
| Backend PostgreSQL integration | 2 passed; `alembic check`: no pending changes; new migration down/up OK |
| SQLite migration of previous-version data | upgrade → downgrade → upgrade OK, data intact |
| ruff / mypy --strict | clean / clean (74 files) |
| Frontend Vitest | 26 passed |
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
owner: Black Box command output from a spare unit (Q-28). Bench runs: 2930F console
bootstrap, SSH check, firmware (approved downgrade WC.16.11.0001 → WC.16.10.0025) and the
secondary flash done once on a new unit (2026-11-19/23); file load: **succeeded fully automatically**
(5th run, 2026-11-23; D-053, D-054, D-055); owed: file load, bootstrap re-run;
FortiGate 101F staging.

## Next milestone
1. **Bench runs** (product owner): 2930F console bootstrap and firmware
   (`vendor-support/aruba-2930f-*.md`); FortiGate 101F firmware, base, site, revisions
   (`vendor-support/fortigate-101f-bench.md`). Correct wording and waiting times against what
   the units really print (Q-25); keep the output as fixtures.
2. **2930F complete-file load**: built (experimental), with the certificate step and the login
   after loading; bench run with `vendor-support/aruba-2930f-staging.md`.
3. Black Box LIG1014A and LE2700A: real load procedure once the switch's own command output
   (Q-28) or the web upload details (Q-27, Q-29) are available; file recognition and a
   simulated driver exist for both.
4. The one-screen staging run across the four devices.
5. FortiGate first login inside UNDM, if agreed (Q-24).
6. Authentication and roles; persistent job runner.
