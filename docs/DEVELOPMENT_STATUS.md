# Development Status

_Last updated: 2026-11-27 — v95, after staging: a system is reached on the bench or in the
network through its BFW, with network addresses read from each device's file and its real
devices marked production there (D-125); a console window for every real device (D-126); the
modem read over SSH in the network (D-127); ping and traceroute from this PC, the BFW and
capable devices (D-128). Before: 2026-11-26 — v94, UI/UX pass 2: one design system checked for WCAG 2.2 AA
(D-119), navigation in three groups with one place for every address (D-120), Stage a system
with Check and run, Start all ready, staging alone and safety switches in place (D-121),
device/system/plan pages with one main action (D-122), one word for each thing and a setup
checklist on Home (D-123), the modem's default login (D-124). Before: 2026-11-24 — Plan A
(UI/UX) started: plain words, a work-ordered navigation and a Home page (D-083); safety
switches changeable in Settings → Safety, audited (D-082)._

## What works (implemented and tested)
| Area | Details |
|---|---|
| Projects & inventory | CRUD; device edit form; environment (simulated / lab / production) with rules; declared vs observed data; search, filters, bulk read-only actions |
| Credentials | Stored in the OS credential store (Windows Credential Manager on Windows); write-only through the API; attached per device |
| Real devices (experimental) | SSH drivers for ArubaOS-Switch (2930F), AOS-CX, FortiOS, IOS-XE: test connection, facts (best-effort parsing, raw output kept), backup, merge apply + save. Gated by policy switches (see SECURITY_BOUNDARIES) |
| Intent & generation | Hostname, VLANs, L3 interfaces, static routes → AOS-CX / FortiOS / IOS-XE templates; validation; platform support checks |
| Configuration import | Upload a file per device; normalised, versioned, labelled unvalidated; selectable per device in deployment plans |
| First login | New unit's first login as an approved plan (kind `first_login`): read-only check of the empty password, then the device's login set when the unit demands a new password, verified by a fresh login (D-073). Fake FortiGate only; factory SSH wording not yet seen (Q-41) |
| Stage a system (wizard) | `/stage`: system and its four devices by role, files and firmware per device, bench check, one plan per device (any of first login, firmware, files; checked before anything is made; later steps checked at their run), approve with a window when firmware is in it, run, stop, report to print or save. Tested with fake devices (API) and simulated devices (browser); **not yet run on hardware through the wizard** (D-085) |
| Staging plan | Base file (replace), then site file (merge) for one device as one plan (optionally after the first login): one approval, one Execute, step 2 previewed at its run and run only after step 1 succeeded, shared Stop (D-071). API and fake FortiGate tests; **not yet run on hardware** |
| Deployments | Lifecycle with directive-15 states; dry runs; approval; preflight with identity check; backup; verification by read-back (platform-aware for SSH drivers); rollback or manual recovery; device locks; crash recovery on restart |
| Firmware | Repository with SHA-256 or SHA-512 vs vendor checksum (addable after upload); approval only when verified or with a written, audited reason (D-062); retire/delete; offline compatibility; upgrade plans with maintenance window and second approver; stage/install/reboot/wait/verify; rollback or manual recovery. Simulated devices, plus **one experimental real procedure: Aruba 2930F** (switch pulls the image from UNDM by TFTP into primary flash, restarts, version verified) behind `UNDM_ENABLE_REAL_DEVICE_FIRMWARE`. Experimental: **one successful run on hardware** (2026-11-19, spare JL260A, approved downgrade WC.16.11.0001 → WC.16.10.0025, verified) |
| File transfer | Built-in TFTP server: read-only, per-job, per-device allowlist, transfer records; a transfer under way is cancelled when its file is withdrawn or the job ends (D-063); tested with an independent client |
| FortiGate 101F staging | Firmware by TFTP; base file restored by TFTP (replace mode, checked by hostname/VDOM/version, wrong-model backups refused); site script statement by statement (multi-VDOM, hostname change, error-looking reply stops the run); tunnel key inserted from the credential store, never stored or shown; revision named after each file. Bench 2026-11-24: connection and facts passed on a 101F; the first firmware run was reported failed through a UNDM fault (progress marks taken for the prompt) while the unit went on to install 7.6.5 (fixed D-063; the corrected procedure is not yet run on hardware); the first base restore was taken by the unit but reported failed by UNDM after "File check OK." and the prompt (fixed D-064); the forced admin password change after the base restore is answered with the approved login (D-066; answers accepted on hardware, login afterwards fixed in D-067) or left to a person (D-065). **Base restore and site script passed end to end on hardware with v40 (2026-11-24)**, revisions listed on the unit; save mode checked: automatic (D-069); a site file cannot be re-run over itself, the base plan comes first (D-070); the corrected firmware procedure not yet run on hardware. **Otherwise tested against a fake FortiGate only** |
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
| Black Box files | LIG1014A (CLI text) and LE2700A (XML) configuration files recognised at import (complete file → replace; where the switch answers after loading; access settings; base64 "encrypted" password and SNMP exposure flagged; hostile XML refused); both models in the catalog with a **simulated** driver; LIG1014A also with an **experimental read-only SSH driver** (connection, facts with the MAC address as identity, backup; D-074 to D-076), **read-only checks passed on hardware 2026-11-24** (factory unit, v00.01.00); loading the team's file (TFTP into the startup configuration, `reload cold`, MAC/hostname/lines verified) **passed once on hardware 2026-11-24** (D-077 to D-079); firmware upgrade (`firmware upgrade tftp://…`, the switch's own restart, active version checked) **passed once on hardware** v00.01.00 → v00.01.01 (D-080, D-081) |
| Supplied-file recognition | FortiOS files are classified offline at import (full backup vs CLI script), with structure check, what the file will change about access, and a count of secrets (never the values). A file cannot be applied in a way that does not fit its kind |
| Live progress | The deployment page refreshes every 2 s while a job runs and shows the device's last output when a step fails |
| Topology | Canvas (React Flow), interface links with mode/VLANs, saved layout, auto-arrange, validation (interface reuse, self links, subnet mismatch, VLANs, duplicate IPs, isolated devices) |
| Audit & logging | All significant actions, redacted details and device output; actions shown in words (raw action name kept below) |
| Safety switches in Settings | Real-device changes, Firmware changes and the second approver for firmware can be changed in Settings → Safety: confirmation before the less safe position, one audit event per change, kept in `settings.json` in the data folder, `.env`/environment values win and are shown as fixed, production switches start-up only, in force at once (an approved plan not yet started is stopped by turning a switch off) (D-082) |
| Feedback and confirmations | Errors shown inside the dialog that caused them; other errors stay until closed, with Copy details; one confirmation dialog for cancel plan, retire/delete image, delete login, delete system (typed name); deleting a system removes its stored passwords; tables scroll inside their cards; no sideways page scroll at 390 px (D-084) |
| Names, erase, two switches (v68) | Devices are named after the hostname in the file chosen for them, confirmed after loading (D-094). Erasing a preconfigured 2930F: UNDM reads its name from the console, the person ticks it; no typing (D-095). **Experimental, not yet run on hardware:** the second 2930F's plan moves the first to a spare address, unsaved, instead of unplugging it (D-096, Q-45) |
| Two logins (v74) | Console setup takes the login the switch has now and the approved one; falls back on the current login when the approved one is refused (also after an erase that kept the password) and then requires 'Login after loading' for its file (D-102) |
| Address refused (v75) | Console setup recognises the 2930F's "overlapping network" refusal (VLAN 1 holding a DHCP address in the bench network), quotes it and says to unplug, power-cycle and rerun (D-103) |
| Console port (v76) | Console setup fills the port and address from the switch's wizard role, and refuses a port the switch's configuration does not list before changing anything (D-104) |
| Bench check FortiGate (v77) | A factory FortiGate that refuses the approved login before it ever connected shows "Expected now" (its plan's first login sets the password), not a red failure; test results carry `login_refused` |
| For all systems (v78) | Logins (tunnel key included), default logins per device and the 2930F certificate answers set once in Settings → For all systems; the wizard and console setup start from them; a system can still use its own (D-105, migration 2abfdc4c7344) |
| Make room (v78) | The 2930F's "overlapping network" refusal is recognised over SSH; a refused move fails cleanly; the spare address is 192.0.2.3 in the other bench network (D-106, experimental) |
| Make room (v79) | Switches off the first 2930F's management port, unsaved, and checks its address goes quiet; replaces the spare address, which a staged switch cannot use (authorized managers); 'invalid port' recognised; a step that leaves the switch as it was ends Failed (D-107, experimental) |
| Finish staging (v80) | Report step checklist (staged, switches back on their address, license, report, backups, safety switches off, powered off) and Finish staging, checked by the server and recorded; Staged badge on Systems, system page and Home; reopen by hand or by a new plan (D-108). Make room worked on hardware (D-107) |
| Finish checklist (v81) | A switch with its port off is confirmed by the person (no test: the other switch has its address); safety switches fixed in backend\.env are named with their lines (D-108) |
| License in the wizard (v81) | FortiGate license file optional in wizard step 2, loaded as the plan's last step; otherwise later from the device menu (D-109, experimental) |
| Black Box both banks (v81) | 'Also the backup slot' on the LIG1014A runs the upgrade a second time and checks both banks; ticked by default for switches with two banks (D-110, experimental) |
| Templates by zone (v82) | Team files imported once as templates (verified against a second zone); the system's zone in wizard step 1; Generate makes the four devices' files and chooses them; Compare checks them against the files on the devices line by line (D-111) |
| Files byte for byte (v83) | A template keeps the team file's line endings and final line break; Download the files for zone N (zip) in the wizard and per template in Settings gives the team's files byte for byte; stored device files stay normalised (D-111) |
| Nokia modem first access (v84) | 7705 SAR-Hmc added as a system's fifth device, staged over its console only. Console setup runs its first access from the team's recording: boot menu (no configuration file, no auto-discovery), factory login, admin password from the device's login (masked), boot options and configuration saved after read-back. **Experimental: simulated console only, not yet run on a modem.** Its configuration load and the Flexi BBU (guided by hand first, D-113) are not built (D-112) |
| Modem question answered (v85) | First bench run: the modem's 3-second question was printed but UNDM never answered (it waited for the output to end with it). Questions are now found anywhere and answered at once with Enter; control characters dropped and counted; 10-minute wait; truthful messages; live progress and technical details (D-112). **Steps after the question still not run on a modem** |
| Modem boot menu field (v86) | Second bench run: Enter at the 3-second question worked; UNDM then took the sros field's redraw (on every key) for a new question. Redraws on the same line are now ignored, a re-ask after a line break stops the run, answers are typed key by key and Enter waits until the modem shows them (D-112). **Boot menu after the sros question, login and commands still not run on a modem** |
| Modem first access on hardware (v87) | Third bench run: the whole first access worked on a factory 7705 SAR-Hmc (admin password set, boot options and configuration saved, verified). v87 logs out at the end (Nokia's documented `logout`), requires `admin save config.cfg` to confirm, masks SNMP engine IDs in shared text, and keeps the password marker readable (D-112). Next: the modem's configuration load (needs two zones' files) |
| Modem file and BBU SCF by zone and system (v88) | A system's number (B007) next to its zone; the team's PCI table imported once (.xlsx/CSV, Compact Sector columns); modem and SCF templates with the system rules, the cells' PCIs from the table, the modem's password as a slot filled from its login; a system's files in one zip; import check with accepted differences (D-114). Proven locally on two real systems: modem byte for byte, SCF identical except the decided lines. The BBU is not a wizard device yet (guided staging next) |
| Template import reads the file (v89) | Zone and system from the file name (zone also without leading zeros, `MRBTS-<n>`, eNodeB's `eNB1` ignored), else from its text; the source shown; a name and text that disagree pointed out. A team file's own `${…}` (FortiOS report variables) is kept; only UNDM's markers are refused (D-114 amendments) |
| Logins for all systems from the systems (v89) | Settings → For all systems → Logins made in the systems: a preview with suggested names (devices' model + user name), editable; one step moves them, merging logins with the same user name and password; devices, plans and the wizard's choices follow (D-115) |
| Modem configuration load over the console (v90) | The modem's file (from its template) loaded by a plan over the console port its first access saved: line by line, stop at the first refused line unsaved, `admin save`, then log in again and check the system name (D-116). Experimental: passed once on a real modem, 2026-11-26 (149 lines, about one minute, saved and verified; Q-58). Finish staging needs the modem's plan; a modem first accessed before v90 gets its port from that first access (v91) |
| Console window for every real device (v92, v95) | Device menu, Troubleshoot tab and In the network tab → Open console window…: COM port and speed (the model's documented speed with its source: 2930F 9600, FortiGate 9600, LIG1014A 115200, modem 115200), saved on the device; PuTTY when installed, else pySerial's terminal; refused while UNDM uses the port; audited (D-118, D-126). Only the modem's window has been opened on hardware |
| In the network (v95) | System page → In the network: the BFW, each device's network address chosen from its file (line shown, one suggested when the file leaves no doubt) or typed, the file's management limits against this PC, Move to the network / back to the bench (real devices production / lab, audited), the start-up line for UNDM's own logins, route hints to copy, Check all from this PC or the BFW. Plans, console setup and guided steps refused in the network; one resolver for every connection, guarded by a source test (D-125). File readers checked locally on the team's files; **not yet run in a real network** |
| Modem over SSH (v95) | `ssh.nokia.sar`: facts and backup over SSH in the network, nothing changed (D-127). Fake channel only; **not yet run on hardware** |
| Ping and traceroute (v95) | Device page → Troubleshoot: from this PC (Windows ping/tracert, refused elsewhere), from the BFW or the device where its driver documents a command (FortiOS, 2930F, modem ping only); hops named by device, shared addresses as candidates; raw output kept; audited (D-128). Synthetic output only; **not yet run on hardware** |
| Flexi BBU in the wizard, guided (v93) | Role Nokia Flexi BBU (FSMF): no login, no plan; UNDM checks its portal answers (port 443), hands out the approved package and the generated SCF (byte for byte) with their SHA-256, and records each step done by hand in the portal (who, when, notes, file hashes); Finish staging and the report count it (D-117). Not yet used on a BBU |
| Erase dialog (v73) | Shows the login the switch gets after the erase and blocks early when it has no password or is the login being erased (D-101) |
| FortiGate license (v72) | "Load license…" in a FortiGate's menu: the team's file is kept for the device (never shown or exported) and loaded through an approved plan with `execute restore manual-license tftp` (Fortinet-documented; **experimental, not yet run on hardware**, Q-46, D-100) |
| Working with devices (v71) | Device menu everywhere (⋯ and right-click): Open SSH window (PC's own SSH program, password typed by the person, D-098), web page, check information, test, wait until it answers, back up, log, restart (approved plan; 2930F and LIG1014A), console setup. System tree with tick boxes, watch devices (reachability dots), device log (D-099) |
| Backups and completion (v70) | A system's backups as one zip (folder per device; confidential), download per backup row; the Report step says when all devices are staged and what to do last (D-097). **First full system staged on hardware 2026-11-25** through the wizard: FortiGate 101F, LIG1014A, two 2930F |
| Bench cabling | Wizard Bench check: cabling table per device (all four on one isolated switch); a 2930F whose file moves it to an address another device has waits until that one is unplugged (card caution); the 2930F file step stops in preflight, nothing changed, when another device answers at that address (D-091) Test connection answers in the device's row (a real device without a login says "Choose its login first" with a link to step 1; a refused test shows its reason there, no pop-up) (v63). A console setup whose switch does not answer yet says to plug its port into the bench switch and press Test (v64). An SSH timeout says "No answer from <address> on port 22 (SSH)" with the bench causes (cable, PC address, Wi-Fi on the same network); the library text stays in the diagnostics. The console setup state reads "Console setup done", not "Reachable" (v65). First full wizard run (2026-11-25): both 2930F and the FortiGate staged; the Black Box loaded its file but its plan had no login after loading, so the wizard now requires one for a real Black Box and FortiGate (D-092, v66). |
| Bench log | One masked text per system (devices, console setups, plans with every event) to send instead of screenshots; read before sharing; audited (D-090). Checklist for the first full wizard run: `vendor-support/staging-wizard-bench.md` Masks file names with and without extension and revision names; failed console setups show their last console lines (D-093). |
| Messages | Four kinds only (problem, caution, status, help) from one component; explanations as quiet hints; empty states; safety switch state shown next to actions on real devices instead of the header; guarded by a test (D-089) A real device without a login says so in plain words, with where to choose one (v62). |
| Needs attention, deleting | A plan that needs attention stops waiting once a later real plan succeeded on its devices or a person records a check (note, audited); Home shows only those still waiting. Delete devices (row or several), systems and plans (a staging step takes its whole staging plan; never while running); audited (D-088) |
| System packages | Export a system to one `.undm` file (settings, devices, login names, files, topology, optionally approved firmware; no passwords; checksummed manifest) and import it on another copy: checked completely before anything is created; logins arrive empty, images unapproved (D-087) |
| Plain words and navigation | One glossary (D-123, `services/labels.ts`); sidebar **Work** (Home, Stage a system, Systems) · **Setup** (Firmware, Settings) · **Advanced** (Devices, Plans, Console tool, Topology, Audit log); addresses `/systems`, `/plans`, `/plans/new`, `/plans/staging/:id`, `/console`, old ones redirect; breadcrumbs; Page not found; Settings tabs Logins · Templates · Certificate · Safety · Your name and appearance · About (D-120); Home with **Set up once** and **Continue staging** (D-123) |
| Design system and accessibility (v94) | Theme tokens for light and dark (contrast proven by a test), headings by level, toned tags, status with icon and words, dialogs that start on Cancel and give focus back, page titles, focus to the title on navigation, skip link; axe (WCAG 2.0–2.2 A/AA) on every page and the Start all dialog in light and dark; no sideways scroll at 1366 and 390 px; a conventions test keeps hand-picked colours, sizes, unnamed tables, written-out addresses and old words at 0 (D-119, D-123) |
| Stage a system, pass 2 (v94) | Zone and system saved by themselves; Add all missing devices; one login picker; the only fitting approved image chosen once; Test all; console setup inside the wizard; **Check and run** (check, then one Approve and run); **Start all ready** (switch B after A); **I am staging alone** (second-approver rule off for one approval, on again at once, audited; Finish checklist checks it); safety switches turned on in place with the Settings dialog (D-121). Simulated devices and tests only: **not yet used on the bench** |
| Pages, pass 2 (v94) | Device page: Test connection, Edit, the device menu (now with Edit and Delete), one Read information, login changed in place; Edit device with Advanced settings; system page with Stage this system, Add device and More; Plans list with filters and New plan; plan page badges and More; Firmware upload from the device model (`?model=`); Audit log in words with names and links, every backend action labelled (test against the backend source); Topology keyboard edit, dashed problem links (D-122) |
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

## Test results (2026-11-27, v95)
| Suite | Result |
|---|---|
| Backend pytest | 688 passed, 2 skipped (PostgreSQL suite skips without DB URL); no test starts ping or tracert, and a source test guards every read of a device address |
| Backend PostgreSQL integration | 2 passed |
| ruff / mypy --strict | clean / clean (107 files) |
| Frontend Vitest | 148 passed (network tab and address chooser, console window, troubleshoot hop table, conventions at 0, audit words vs backend) |
| tsc / oxlint / vite build | clean / clean / success |
| Playwright | 14 passed: 11 workflows (1280 px, a practice system moved to the network and back, Check all from the BFW, a simulated ping and traceroute), axe on every page light and dark including the In the network and Troubleshoot tabs (1366 px), no sideways scroll at 1366 and 390 px |

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
owner: the LIG1014A load procedure (Q-42) and SSH after loading (Q-27). Bench runs: 2930F console
bootstrap, SSH check, firmware (approved downgrade WC.16.11.0001 → WC.16.10.0025) and the
secondary flash done once on a new unit (2026-11-19/23); file load: **succeeded fully automatically**
(5th run, 2026-11-23; D-053, D-054, D-055); owed: file load, bootstrap re-run;
FortiGate 101F staging.

## Next milestone
**v95 on the bench**: the checklist's "What is new in v95: after staging, in the network"
(`vendor-support/staging-wizard-bench.md`); its outputs answer Q-59 to Q-64. Then **the
topology from the product owner's wiring picture, with the packet path of a traceroute**
drawn through it (the hops are already recorded by device, D-128).

**v94 on the bench** (2026-11-27): the reworked screens on real devices, with the checklist's
"What is new in v94" (`vendor-support/staging-wizard-bench.md`): Test all, Check and run,
console setup inside the wizard, staging alone, Start all ready. Earlier plan below.

**Plan A — UI/UX for colleagues** (product owner, 2026-11-24; plan B, the portable Windows
app, is deferred). Done: A0 baseline screenshots, A1a words, A1b safety switches, A2
navigation, A1c feedback and confirmations (D-084), A3 the **Stage a system** wizard on a
generalised staging engine (D-085; bench run through the wizard still to do), A4
page-by-page fixes (D-086), A5 export/import of a system (D-087). Next: a bench run through the
wizard on a new system (2026-11-25, checklist `vendor-support/staging-wizard-bench.md`, bench log D-090); then Plan B (portable Windows app) when the product owner asks for it. Bench items below stay open.

1. **Bench runs** (product owner): 2930F console bootstrap and firmware
   (`vendor-support/aruba-2930f-*.md`); FortiGate 101F firmware, base, site, revisions
   (`vendor-support/fortigate-101f-bench.md`). Correct wording and waiting times against what
   the units really print (Q-25); keep the output as fixtures.
2. **2930F complete-file load**: built (experimental), with the certificate step and the login
   after loading; bench run with `vendor-support/aruba-2930f-staging.md`.
3. Black Box LIG1014A and LE2700A: real load procedure once the switch's own command output
   (Q-28) or the web upload details (Q-27, Q-29) are available; file recognition and a
   simulated driver exist for both.
4. The one-screen staging run across the four devices (first part: the FortiGate staging plan, base then site, D-071).
5. FortiGate first login inside UNDM, if agreed (Q-24).
6. Authentication and roles; persistent job runner.
