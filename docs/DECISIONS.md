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

### D-025 Console bootstrap is a provisioning workflow outside the deployment lifecycle (2026-11-19)
A factory-default device cannot be previewed against or approved over the network, and
the technician is alone at the bench. Console bootstrap therefore has its own safeguards
instead of the Draft→Approve lifecycle: exact command preview, typed device-name
confirmation, the real-device write switch, a factory-default check (refuses switches
with site configuration or a password unless explicitly overridden), stop at the first
error, save only after read-back matches, idempotent re-runs, audit record, transcript.
The backend opens the PC's COM port itself (pyserial), so no separate agent is needed
while UNDM runs on the technician's PC.

### D-026 Per-device bootstrap settings; temporary staging address (2026-11-19)
Bootstrap settings (VLAN, name, untagged port, address) are stored on each device, not
hard-coded, so the two switch roles keep their own port. The product owner approved
giving one switch 192.168.1.2 during staging so both can be on the bench at once.

### D-027 Secrets mentioned in conversation are never recorded (2026-11-19)
A password was shared in the development conversation. It is not written to code, docs,
fixtures, tests or commits. Operators enter passwords only in UNDM's credential store.
Empty passwords are allowed there because factory-default devices have none.

### D-028 Follow the team's FortiGate upgrade practice (2026-11-19)
The team upgrades FortiGate 101F from 7.2.7 directly to 7.6.5. UNDM will perform that
single step and not invent intermediate versions; the firmware image's
"minimum version to upgrade from" rule stays available if the team wants to enforce a path.

### D-029 TFTP first, served by UNDM itself (2026-11-18)
The product owner chose TFTP as the first file-transfer method ("if we test and it fails,
then we look at another method"). UNDM carries its own TFTP server instead of depending on
a separate tool: read-only, serves only files published for the running job, each file
only to the one device address it is meant for, started when a real-device job needs it
and stopped when the job ends. It is tested against an independent client (tftpy).

### D-030 Firmware on real devices has its own switch (2026-11-18)
`UNDM_ENABLE_REAL_DEVICE_FIRMWARE` is required in addition to the write switch; dry runs
stay allowed. The second-approver rule for firmware stays on by default and can be turned
off explicitly (`UNDM_FIRMWARE_REQUIRE_SEPARATE_APPROVER=false`) for one technician staging
new units on an isolated bench. The maintenance window stays mandatory.

### D-031 Interactive device dialogues: answer only what is known, prove success (2026-11-18)
Commands that ask questions are run by a dialogue routine with an explicit list of
(question, answer) pairs. An unrecognised question is never answered: the step ends and
the device's text is shown in the job events. A step is reported successful only on
independent evidence: for the 2930F image copy, UNDM's own TFTP record must show the whole
file was fetched by that switch **and** `show flash` must show the expected version; a
restart counts as started only after the confirmation was actually sent.

### D-032 A supplied file is applied the way its kind requires (2026-11-18)
Drivers can describe a supplied configuration file offline (`inspect_config_file`): a full
backup is restored as a whole (replace), a CLI script is a list of changes (merge).
Deployment creation refuses a mismatch, a file with structural problems, and a kind the
driver cannot apply yet. Reason: sending a 12,000-line FortiGate backup line by line, or
"restoring" a script, would leave a device in an undefined state. The report counts
secrets but never contains them.

### D-033 FortiGate staging follows the team's two-file method (2026-11-18)
Base file (full backup, common to all sites) first, then the site script, with a named
revision saved after each — as the team does by hand. The site script will be run one
statement at a time and stop at the first unexpected reply, which is stricter than pasting
(pasting continues after errors). Details and open questions:
`docs/vendor-support/fortigate-101f-staging.md`.

_Note: entries above dated 2026-11-19 were written on 2026-11-18._

### D-034 FortiGate order and credentials (2026-11-19)
Answers from the product owner: the base file is restored **after** the firmware upgrade
(7.2.7 → 7.6.5, then base); the base file is edited by the team to carry the approved admin
password, so one stored credential is valid throughout; when the site file is pasted, the
only error is the one for the first `end`; afterwards the CEN tunnel's pre-shared key is set
to an approved value. UNDM follows this order with three approved jobs (firmware, base
restore, site script) and saves a revision named after each file. The first login (forced
password change) stays a manual browser step for now: automating it would need a second
exception to the deployment lifecycle (CLAUDE.md allows only console bootstrap), which needs
the product owner's agreement.

### D-035 How a FortiGate CLI script is run (2026-11-19)
One statement at a time over SSH, reading the reply to each. A reply that looks like an
error stops the run at that line (lines before it stay applied; the rest are not sent); a
bare `end` before the first block may fail without stopping; any other message is recorded
as a warning and the run continues; a question stops the run (never answered). This is
stricter than pasting, which carries on after errors. Verification: every statement
accepted, the hostname the file sets is in place, and a read-back count (FortiOS hides
default values, so a line-by-line comparison would be wrong).

### D-036 Secret values in supplied files come from the credential store (2026-11-19)
A file's clear-text secret settings (for example a tunnel `psksecret` placeholder) are
listed as slots. A plan may map each slot to a credential reference; only the reference is
stored. The value is read at execution and inserted into the copy sent to the device; it is
masked in every message and never stored, logged or returned. Values containing `"`, `\`
or `?` (CLI help) are refused for now. The simulated FortiGate checks the mapping the same
way but only ever holds `ENC <simulated>`.

### D-037 Generic driver hooks instead of vendor branches (2026-11-19)
New, vendor-neutral contract points: `needs_file_server(kind, mode)` (TFTP session for any
job that needs it), an apply result flagged `restarting` (the orchestrator waits for the
device), `verify_configuration` (driver-specific verification, e.g. facts after a full
restore), `create_checkpoint` with capability `supports_configuration_checkpoint` (named
restore point after verification; a failure is a warning), and `prepare_for_device` (secret
insertion). The manual-recovery message now keeps the cause of the failure.

### D-038 The backend checks its database at startup (2026-11-19)
After an update the database may be behind the code (seen on 2026-11-19: a missing column
showed only as "Request failed (500)"). The backend now compares the database revision with
its migrations at startup, reports it in `/api/health`, the UI shows a banner with the exact
command, and database errors say so instead of a generic 500.

### D-039 Black Box files: recognised and simulated first (2026-11-19)
The product owner supplied a Black Box configuration file (loaded today as a file in the
web interface). It is a complete configuration in the switch's CLI syntax, so it is applied
as a whole (replace) — never line by line. UNDM recognises it at import and reports where
the switch answers after loading, its access restrictions, and that the admin password's
"encrypted" value in the sample is only base64 (readable by anyone with the file). The
LIG1014A is in the catalog with a simulated driver only. A real procedure waits for the
answers to Q-26…Q-28: the CLI `copy` syntax with a TFTP URL is not confirmed, and the web
upload is undocumented, so neither is built on guesswork.

### D-040 LE2700A files: XML, recognised and simulated (2026-11-19)
The product owner confirmed the CLI-syntax file is for the LIG1014A and supplied the LE2700A
format: an XML export of the whole configuration. UNDM recognises it at import (complete
file → replace; the single management address after loading and the ports that carry it;
access settings; no accounts in the file; SNMP exposure) and adds the LE2700A to the catalog
with the simulated driver. XML is parsed with the standard library after refusing any
document type or entity declaration, so no new dependency is needed and entity-based attacks
are excluded. The LIG1014A web upload lets the user pick running and/or startup
configuration; the real loading procedure for either model still waits for the switch's
own command output (Q-28) or the web upload details (Q-27, Q-29).

### D-041 2930F complete files loaded by TFTP into the startup configuration (2026-11-19)
The team's 2930F files are complete configurations written by the switch itself. UNDM loads
one as a whole: `copy tftp startup-config <pc> <file> unix` (syntax from the manual of a
sibling model; unverified on the 2930F), then the switch restarts — by itself, or after
`boot system flash primary`, where a "save current configuration" question is always
answered "n" so the old running configuration never overwrites the new file. A file for
another product number is refused. If the file sets an address in the same subnet as the
one UNDM used (e.g. temporary 192.168.1.2 → 192.168.1.1), UNDM reconnects there and, once
the switch is verified, updates the device's address (audited). Verification: hostname as
in the file, plus a count of the file's lines in the running configuration (missing ones
listed as warnings). New general rule: after **any** restart (firmware, FortiGate restore,
2930F load) the serial number is compared with the one read at preflight; a different unit
answering at the address fails the job instead of being verified by mistake.

### D-042 A loaded file may change the login (2026-11-19)
The team's 2930F file sets the approved manager password, while the switch is reached
before loading with the factory login (manager, no password). A configuration plan may
therefore name, per device, a **login after loading** (a credential reference, stored as a
reference only). After the apply, UNDM logs in with it — after the restart, or by logging
in again for a change without restart, as proof that the new login works — and, once the
device is verified, makes it the device's credential (audited `device.credential_changed`).
Without it, the job stops after the restart with "Authentication failed", which the file
check now points out. Generic, not vendor-specific.

### D-043 New 2930F units: first-login credentials set by the console bootstrap (2026-11-19)
A new 2930F shows "Configure the manager credentials :" and "Username:" on the console and
requires a password and its confirmation before anything else (product owner's screenshot).
The console bootstrap — still the single lifecycle exception of D-025, with its preview,
typed confirmation and write switch — now recognises that exact text and sets the device's
attached login: the username, then the password for exactly two password prompts. With no
login attached, or an empty password, it stops before sending anything. A request for the
username again (password refused) or a third password prompt stops it with the switch's
text. The password is never written to the transcript, the result or the audit, which
records only that first-login credentials were set and with which credential. Afterwards the
device's login is the approved one, so later jobs use it from the start.

### D-044 2930F HTTPS certificate created inside the load job (2026-11-19)
The team's 2930F files make the web interface HTTPS-only and say a certificate must exist
before loading. From the team's commands and screenshots of a running unit, the load job
now starts with: `configure`; `crypto pki identity-profile <profile> subject`, answering
exactly the six questions shown (`Enter Common Name(CN) :` … `Enter Country(C) :`) with the
project's certificate subject; `crypto pki enroll-self-signed certificate-name <name>`
(silent, or "already exists" — both accepted, so re-runs are safe); `web-management ssl`;
`end`; `write memory`. Unknown questions or errors stop the job before the file is sent. The
subject is a project setting (organisation details, kept only in the UNDM database; values
that cannot be typed safely into a CLI are refused). It runs only for files that make the
web interface HTTPS-only. This is a generic driver hook (`prepare_before_apply`); a job,
not a new exception to the deployment lifecycle.

### D-045 New 2930F prompts answered exactly (2026-11-19)
A second screenshot of a new unit showed the full sequence after the HPE banner:
"Configure the manager credentials :", "Username:", "Password:", "Re-enter the new
password:". The console bootstrap now answers exactly that sequence; a different password
question, the right questions in another order, or the username asked again stops it with
nothing answered. A unit whose credentials were already set by hand (with the approved
password) is logged into normally and still passes the factory-default check, which looks
at site configuration, not at the password.

### D-046 Console left half-way through a login: start again (2026-11-19, first bench run)
On the first bench run the console was still at "Re-enter the new password:" from a manual
try; the bootstrap's wake-up Enter answered it with an empty password and the switch ended
the session ("Password cannot be empty. / Operation aborted. / Session Terminated, unable to
login."). Nothing was set. The bootstrap now recognises "Session Terminated, unable to
login." and starts the login again (at most twice), so a console left in any login state is
handled. A serial console does not redraw a pending prompt, so it cannot be seen before a
key is pressed; an empty answer is the least harmful key.

### D-047 Console reader: escape codes across reads, line codes as line breaks (2026-11-19)
Second bench run: a serial read ended between ESC and `[24;18H`, so the code stayed in the
text and "Password:" did not start a line. The console reader now holds back the start of
an escape sequence cut off at the end of a read and joins it with the next read, and turns
"next line" (ESC E) and "insert line" (ESC[nL) into line breaks, mirroring Netmiko's
handling of Aruba/ProCurve consoles; other codes are removed. "Password:" is also matched at
the end of the output, independent of line starts.

### D-048 Approved older firmware: an explicit plan option (2026-11-19)
New 2930F units ship with WC.16.11.0001 while the project's approved release is the older
WC.16.10.0025 (product owner). Downgrades stay refused by default; a firmware plan may set
"install the approved version even on devices that run a newer one". The preview marks each
such device as a DOWNGRADE (warning), the deployment page shows a badge, and the plan's audit
records the setting, so the approver sees it before approving. The procedure itself is the
same as an upgrade; if a switch refuses the older image, the job stops with its answer.

### D-049 Times are UTC everywhere, and shown as UTC (2026-11-19)
The network's time is UTC+0 (product owner). The database returns every timestamp with
its zone (`UtcDateTime`; SQLite stores none, which made the API send zone-less times that
browsers read as local time). The interface shows times as `YYYY-MM-DD HH:MM:SS UTC`,
whatever the PC's time zone, and the maintenance window is entered in UTC. Device logs,
UNDM events and the audit log can be compared directly.

### D-050 Approved release in both image slots: secondary written after the primary is verified (2026-11-23)
Team standard (product owner): the approved release in the primary **and** secondary flash.
A firmware plan may set "also write the approved version into the secondary flash". Drivers
declare it as a capability (`supports_firmware_secondary_image`); the 2930F procedure uses
the same command as for primary with the other slot (`copy tftp flash <pc> <file> secondary`)
and requires `show flash` to report the target there. Order: the secondary is written only
after the device has restarted and runs the target from primary, so a new image that does
not boot never leaves both slots without the previous release. A device already on the
target gets only its secondary written (no restart). A newer secondary is overwritten only
when the plan allows the approved older version (D-048). A failed or unconfirmed secondary
ends in "manual check" with the running version stated; the working primary is not rolled
back. Because the team's files switch the TFTP client off, both slots are written before
the file load. The second transfer of the same file is told apart from the first, so an
earlier fetch never counts as the secondary's.

### D-051 Stop button; runs continue on the server (2026-11-23)
Bench: after a file load the switch answered on another port than the laptop's, so UNDM
kept waiting for it; the browser reported the long request as failed while the run went
on. Now: (1) the page starts a run in the background (`execute?background=true`) and
follows its events; the run no longer depends on one open browser request (the API keeps
the synchronous form for scripts and tests). (2) **Stop** (`POST /deployments/{id}/stop`,
audited) asks the run to stop at its next safe point: between steps and devices, while
waiting for a device to come back, or while waiting for a device's answer in an SSH
dialogue. A command the device is already carrying out is not undone and no rollback is
started after a stop. Outcome: FAILED "no device was changed" if no device was touched,
otherwise RECOVERY_REQUIRED with the touched devices named for a manual check; devices
not yet reached are SKIPPED. A plan shown as running without a run in this process (e.g.
after a restart) is resolved at once, like the startup recovery. (3) While waiting after a
restart, an event names the address, and a 2930F file load says where the switch answers
after the restart, with VLAN and port ("untagged on port 3"), so the PC can be moved there.

### D-052 2930F load: evidence before restarting; never save over the fetched file (2026-11-23)
Bench: the switch fetched the whole file and restarted, but came back with its previous
configuration (cause open, Q-36). UNDM gaps found and closed: (1) if the switch returns to
its prompt after the load, UNDM restarted it without checking that the file had reached
the startup configuration; it now requires the file's `hostname` in `show config` (the
startup configuration, per the vendor's CLI documentation; not yet seen on the bench)
and otherwise stops without restarting, showing the switch's output. (2) The load dialogue
answered "y" to every y/n question; a "save current configuration" question is now
answered "n" first (as `boot system flash primary` already did), because "y" would write
the old running configuration over the fetched file. (3) What the switch printed during
the load, and what UNDM answered, is recorded as an event; on a failed configuration step
the device output is recorded as for firmware. (4) A failed post-load check says that the
switch is not running the file and where to look (console during the start, `show logging`).

### D-053 An HTTPS-only 2930F file needs the certificate first: a hard requirement (2026-11-23)
Product owner: through the web page, loading the team's file fails if the HTTPS
certificate commands were not run first. On the bench, three UNDM loads without a
certificate subject (certificate step skipped, only a warning) came back with the
switch's previous configuration. A file report can now name project settings the file
requires (`required_settings`, generic; core code checks the project, not the vendor);
the 2930F inspector requires the certificate subject for HTTPS-only files. Plans for such
a file are refused until the subject is set (Project settings → HTTPS certificate), and
the check is repeated when the run starts. Earlier warning-only behaviour (D-044) is
replaced for these files.

### D-054 2930F load: a silent session after the transfer means "restarting" (2026-11-23)
Bench, first load with the certificate: the switch took the file and restarted by itself,
but the SSH session neither closed nor printed anything. UNDM treated silence after the
transfer as "still writing" and would have waited for the whole transfer timeout (40
minutes). Now silence is expected only while the transfer is in progress; once it is
complete, silence for `question_timeout` with no unanswered question ends the wait and the
load is reported as restarting. "Unanswered" means text printed after UNDM's last answer
(a switch does not echo the "y" it was given). The wait for the switch and the checks after
it (serial number, hostname from the file, the file's lines) prove the result.

### D-055 Restarts are announced and visible; the configuration after a change is kept (2026-11-23)
First fully automatic 2930F file load on the bench (succeeded). Product owner: people must
see that the device is restarting and be patient, and be able to look at the configuration
after a deployment. (1) Drivers may give a `restart_notice` for an apply that restarts the
device; it is an event before the apply ("loading the file: … expect 1-2 minutes …").
(2) The plan page shows the latest step with its age and, while a device restarts, a
"please wait" banner with a timer and "do not power it off or unplug it". (3) The 2930F
load ends its wait as soon as the switch prints "Rebooting switch" (verified wording,
below) instead of after a quiet period. (4) After verification (passed or failed) the
running configuration read back from the device is stored as a version ("after
deployment …", `deployment_targets.after_version_id`, migration 33f472692b47); the plan
page offers "View configuration after deployment" and "Compare with what was sent".
(5) Verification warnings are grouped (one line per distinct text with a count).
Wording seen on the bench (2930F, WC.16.10.0025) for `copy tftp startup-config`:
"Device may be rebooted, do you want to continue [y/n]?", "TFTP download in progress.",
"Rebooting switch..."; the SSH session then stays open and silent.

### D-056 From a configuration to a deployment: "Deploy this version…", not a second plan form (2026-11-23)
Product owner asked for a way from the Configuration Studio to deployment. Chosen: a
contextual action on the version being viewed ("Deploy this version…", generated or
imported versions; disabled with the reason for a file that cannot be applied) that opens
the Deployment Center's plan form with the device and that version already chosen.
Rejected: a deployment tab inside the studio, which would duplicate the plan form and its
checks (file kind and apply mode, required project settings, secrets, login after
loading, approval). Nothing reaches a device until the plan is validated, approved and
executed. Links go both ways: the studio links to the device page and to the Deployment
Center for the device; a plan's targets link "configuration sent", "backup before" and
"after deployment" to the studio (`/configurations?device=…&version=…`).

### D-057 Console bootstrap may erase a preconfigured switch first, on explicit request (2026-11-23)
Product owner: BH-DMZ 2930F units arrive preconfigured (hostname, site configuration and a
manager password that is not the approved one; the same preconfigured login on all units).
The bootstrap failed at `enable` ("Unable to verify password"). Decision (product owner,
asked with alternatives): UNDM erases such a switch instead of the technician doing a
manual reset. This widens D-025 for one explicit case and is written into CLAUDE.md.
Safeguards in addition to D-025's: an opt-in "erase its configuration first" option; the
switch's current login comes from a saved credential (never shown or logged); UNDM logs in
with it and refuses, erasing nothing, unless the hostname the technician typed equals the
name in the switch's prompt; a switch that already looks factory default is not erased;
the configuration read before the erase stays in the transcript; `erase startup-config`
(vendor CLI documentation; confirmation wording **not yet seen on the bench**) is answered
only for a y/n question asking to continue/proceed ("n" to a save question), any other
question stops the run unanswered; UNDM waits up to 7 minutes for the restart, then sets
the switch up as new with the device's (approved) login and bootstraps it as usual,
including the factory-default check and read-back. Audit: erase_existing, erased hostname,
name of the current login. The enable-level failure message now points to this option.
Amendment (2026-11-23, first bench run): after the erase the switch restarted but its
console stayed silent until a key was pressed (it senses the speed again), so the run
waited its full limit. UNDM now waits 20 s, then presses Enter every 10 s until the start
of a login appears (up to 7 minutes), and hands that prompt to the normal login. If the
switch never answers, the result says that it was erased and to bootstrap it again
without erasing.

### D-058 The bootstrap gives a switch without a manager password the approved one (2026-11-23)
Bench (BH-DMZ unit after the erase, WC.16.10.0025): the unit asked for no manager
credentials and was left without a password, so SSH with the approved login failed.
The product owner set it on the console; the screenshot gave the exact dialogue:
`configure`, `password manager`, "New password for manager:", "Re-enter the new password
for manager:" (typed characters echoed as `*`), five notices that DHCP image/config
download, TR-69 ACS URL, the switch's own TFTP server and autorun are disabled once a
password is set, then `write memory` (accepted in configuration mode). The bootstrap now
does this itself when the switch asked for no password at login or enable, and the
device's attached login is user `manager` with a password: it answers exactly those two
questions in order ("Re-enter …" is checked first because it also ends like the first),
saves, and confirms by a `password manager` line in the configuration. The password never
enters the transcript. Other user names are not handled (the command sets the manager
account); the result then says "no manager password" with what to do. Re-runs do not set
it again (the switch then asks for the password).

### D-059 A device that restarts without closing the session is noticed by its SSH port (2026-11-23)
Lesson from the 2930F bench (D-054) applied to the FortiGate procedures, which wait
patiently after a transfer while the unit checks and writes the file (seconds to minutes),
without relying on FortiOS wording not yet seen on the bench: once the transfer is
complete and the session has been quiet for `question_timeout`, UNDM checks the unit's SSH
port every 10 s; if it stops answering, the step ends as "is restarting (its SSH port
stopped answering)" and the usual wait for the unit, identity check and verification
follow. A unit that stays silent with its port open is still reported as "neither
restarted nor returned to its prompt". The base restore also announces the restart
(`restart_notice`).

### D-060 A login that reaches no prompt is explained with what the device showed (2026-11-23)
Bench, first FortiGate 101F contact: Test connection ended with Netmiko's "ReadTimeout:
Pattern not detected: 'to accept|[#$]'" — the login was accepted but no command prompt
followed (on a new FortiGate most likely the forced admin password change; to be
confirmed). The SSH drivers now record what the device prints while the session is
prepared (in memory only; Netmiko scrubs the password, UNDM redacts again; the recording
stops once the prompt is reached) and report "Logged in, but the device did not show its
command prompt; it showed: …" with platform advice (`prompt_hint`; FortiOS: set the
approved admin password once by hand, then retry).

### D-061 Vendor checksums: SHA-256 or SHA-512, added at upload or later; MD5 refused (2026-11-24)
Bench: a FortiOS image uploaded without a checksum stayed "not verified" and could not be
approved; Fortinet publishes MD5 and SHA-512 for FortiGate images, not SHA-256 (Fortinet
community: "How to verify downloaded firmware checksum"). The repository now accepts a
vendor checksum of 64 hex characters (SHA-256) or 128 (SHA-512); both hashes are computed
during the upload. An uploaded image can be verified later ("Add vendor checksum…",
`POST /api/firmware/images/{id}/checksum`): the stored file is hashed and compared; a
mismatch is refused and its audit record kept. MD5 is refused with an explanation: it
cannot show that a file is genuine. New column `firmware_images.vendor_sha512`
(migration d75f9b5c5360).

### D-062 Approving an image without the vendor's checksum needs a written reason (2026-11-24)
Bench: the FortiOS 7.6.5 image for the 101F was uploaded without a checksum, and the
product owner could not obtain Fortinet's SHA-512 (the checksums are behind the support
portal). Product owner decision: allow approval without the checksum. Rule: an image whose
checksum was not matched can be approved only with a written reason (at least 10
characters, e.g. where the file came from); `POST /api/firmware/images/{id}/approve` with
`{"unverified_reason": "..."}`. The reason and the approver are stored with the image
(`firmware_images.unverified_reason`, migration 6cd026e18a31) and recorded in the audit
log (`integrity_verified: false`, `unverified_reason`). Wherever the image is used it stays
marked: the repository shows "not verified · approved with reason" (reason in the tooltip),
the planner labels it "NOT VERIFIED" and shows the reason, the compatibility check returns
a warning instead of an error, and every firmware plan with it carries a warning event
naming the approver and the reason (audit `image_verified: false`). The vendor's checksum
can still be added later, which makes the image verified. Without a reason the approval is
refused as before. Everything else about firmware plans (maintenance window, second
approver, firmware safety switch) is unchanged.

### D-063 A fetch still running is never mistaken for the end of the step, and is cancelled when UNDM ends it (2026-11-24)
Bench, first FortiOS firmware run (101F v7.2.6 → 7.6.5, image approved under D-062): after
"y" the unit printed "Please wait...", "Connect to tftp server <PC> ..." and a line of '#'
progress marks. The FortiOS prompt pattern (any line ending in '#') took that line for the
prompt; five seconds later the step failed as "Transfer incomplete (5581824 of 101271832
bytes)" while the unit was still fetching. Worse, the TFTP server did not stop a transfer
that was under way when the job ended (it only refused new requests), so the unit could
have finished the fetch and installed the image after UNDM had reported "rolled back".
Changes:
- FortiOS prompt: the line must hold something besides '#' (a line of progress marks is
  not a prompt).
- `_dialogue(prompt_ok=...)`: while the device's fetch of the offered file is under way,
  no prompt is accepted; it is checked again with the next output or while quiet.
- TFTP server: a transfer under way is cancelled (TFTP error "Transfer cancelled by the
  server", record "cancelled by UNDM: ...") at the next block once its file is withdrawn
  or the server stops; a block already sent is still acknowledged, so a fetch that has
  just ended stays complete.
- FortiOS procedures withdraw the file as soon as the exchange ends, before deciding the
  result, so a step reported as failed cannot complete later. `FileServer.withdraw`.
Confirmed the same day: the unit finished that fetch after UNDM had closed its SSH
session, installed 7.6.5 and restarted, so the plan's "rolled back" record is wrong.
Regression tests: the fake FortiGate now fetches in the background and prints the bench's
lines and '#' marks; the old code fails that test with the bench's result. Still unknown
(Q-39): what the unit prints when the fetch ends, and what it does when the TFTP server
cancels a fetch or the SSH session closes during one.

### D-064 After a clean file check, a returning FortiGate prompt means "wait for the restart" (2026-11-24)
Bench, first base restore (101F v7.6.5): after "y" the unit printed "Please wait...",
"Connect to TFTP server <PC> ...", "Get file from TFTP server OK.", "File check OK." and
then its prompt (twice). UNDM concluded "did not accept it: it returned to its prompt
without restarting" three seconds later and stopped. FortiOS prints the prompt before it
restarts. Rule now: when the whole file was fetched, "y" was answered and the unit's
answer has no error-looking line, a returning prompt starts a wait of up to 180 s
(`restart_grace`) for the restart, i.e. the unit closing the session or its SSH port
stopping answering (checked every 10 s). A restart then continues as before (wait for the
unit, identity, verification of hostname/VDOM/version). An error-looking line ends the
step at once as "did not accept it"; no restart within the grace is reported as "fetched
and checked ... but did not restart within 180 s" with the unit's text. Applies to image
and configuration fetches alike. Regression test: the fake FortiGate prints the bench's
wording and its prompt before restarting; the old code fails it with the bench's result.

### D-065 After a restart, a login problem gets a clear instruction and time for a person (2026-11-24)
Bench (product owner): the FortiGate base file sets its own admin password; logging in
with it after the restore, the unit demands a new one ("Your password does not conform to
the password policy", rules: 12 characters, one upper case, lower case, number and special
character) and the team sets the approved password again. While waiting for a device after
its restart, UNDM now tells a login that is accepted without reaching the prompt, or
refused, apart from an unreachable device (`login_accepted` / `login_refused` from the SSH
drivers). On the first such answer it emits one warning with what to do and allows a
further full wait (30 × 20 s) for a person. With a login after loading in the plan, UNDM
keeps using it (accepted logins do not fail, so the unit is not provoked into a lockout)
until it is refused, then tries the device's previous login once; if that works the device
keeps it (no `device.credential_changed`). Failing that, the step ends with "the device
answers after its restart, but no login reached its prompt".

### D-066 A demanded password change is answered with the device's approved login (FortiOS) (2026-11-24)
The product owner supplied the FortiGate's SSH CLI text of the demanded change: "You are
forced to change your password. Old password:", "Verifying password...", the policy
("Your password doesn't conform to the password policy enforced on this device. ... New
password must conform to the following policy: minimum-length=12 upper-case-letter=1
lower-case-letter=1 number=1 non-alphanumeric=1"), "New Password:", "Confirm Password:",
"Verifying password...", "Welcome!" and the prompt. During the wait after a restart, when
the plan names a login after loading (the base file's password) and the device has its own
login (the approved one), the FortiOS driver logs in with Netmiko's own steps
(`auto_connect=False`: connect, then the dialogue, then Netmiko's session preparation) and
answers exactly these questions, each at most once: old = the login after loading, new and
confirm = the device's own login. Anything else ends the login with the unit's text
(passwords removed) and the D-065 instruction; a question asked again (new password not
accepted) is never answered twice. Success needs independent evidence: UNDM logs in again
with the approved login before it continues (identity, verification). The device keeps its
approved login; the change is audited as `device.password_set` (no password values). Only
the drivers that know the questions act on the offer (`answers_password_change`); others
leave the change to a person (D-065).

### D-067 Text read during the login dialogue is handed back to Netmiko (2026-11-24)
Bench, second base restore with v39 (101F v7.6.5): the restart after "File check OK." and
the prompt was recognised (D-064 confirmed on hardware); after the restart the unit
demanded the password change over SSH and accepted UNDM's answers (the base file's password
was refused afterwards). Over SSH it showed "... New Password:", "Confirm Password:",
"Verifying password..." and then its prompt, without the "Welcome!" seen in the CLI capture.
But every login on that path then ended in a Netmiko ReadTimeout, also the plain login with
the approved password, and the plan seemed stuck: Netmiko's FortinetSSH prepares the session
without pressing Enter first (`_try_session_preparation(force_data=False)`), and waits for
the prompt the unit printed by itself, which UNDM's dialogue had already read. Fix: the
dialogue hands what it read since its last answer back to Netmiko (`_read_buffer`, the
buffer Netmiko itself uses for unread text). The fake connection now behaves like
Netmiko here (prompt must still be readable), and three tests fail with the old code as on
the bench. Also: if a password change succeeded but the prompt is still missed, the driver
switches to the new login anyway (`password_changed` on the failure), and every further
attempt in the wait shows an event ("still waiting for a working login (attempt N of M)").

### D-068 FortiOS "new entry '…' added" is counted, not listed as a warning (2026-11-24)
Bench, first site script on a 101F v7.6.5 (1784 statements, every one accepted): 192
messages were listed as warnings, 191 of them FortiOS's normal answer to `edit` of an
entry that does not exist yet ("new entry '<name>' added"). They hid the one expected
warning (the bare `end` before the first block). A reply that is exactly that line, after
an `edit`, is now counted ("N new entries created") instead of listed. Anything else is
listed as before; error-looking replies still stop the script.

### D-069 The FortiOS save mode is checked, not assumed (2026-11-24)
Bench (Q-40): on the multi-VDOM unit `get system global | grep cfg-` fails at the top
("command parse error before 'global'") and inside `config global` shows
"cfg-save             : automatic". The FortiOS save step now reads it there after every
load: automatic → "saved automatically (cfg-save automatic, checked)" with a note event;
manual or revert → the step fails with what to do (save on the unit before it restarts;
UNDM has no save command for these modes yet); unreadable → success that says it was
assumed, never "checked". The orchestrator now shows the save step's notes as events.

### D-070 A FortiOS site file over an existing site configuration is cautioned before approval (2026-11-24)
Bench: a corrected site file run over the earlier site configuration stopped at line 918,
"Cannot change 'extintf' while the VIP entry is used. Command fail. Return code -23", after
879 of 1784 statements. FortiOS protects objects in use, so a site script cannot simply be
run again over itself. Drivers may now add a caution to a merge preview
(`merge_rerun_note(already, checked)`); FortiOS does when at least two thirds of at least 20
checked lines are already on the unit (first site run on the bench: about a quarter;
second: about nine tenths): restore the base file first, then load the file. The refusal
"Cannot change … while … is used" now carries the same advice. Other platforms add no
caution, since a mostly unchanged merge is a normal update there. Re-running from a clean
base is done with UNDM alone: the base plan (replace), then the site plan.
