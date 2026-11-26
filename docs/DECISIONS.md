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

### D-071 Staging plan: base file, then site file, as one plan (2026-11-24)
Product owner request after D-070: one plan that always restores the base file before the
site file, so a site file can never land on an earlier site configuration. Built from the
existing plans rather than a new kind of run, so every safeguard applies unchanged
(validation, preview, preflight with identity check, backup, verification, revisions,
login after loading, password change, secrets, policy switches, device locks, Stop):
- `POST /api/projects/{id}/staging-plans` {device, base version, site version, login after
  loading for the base, secret credentials for the site} creates two linked plans
  (`deployments.staging_id`, `staging_step`; migration 8f9754b6c029): step 1 replace with
  the base file, previewed now; step 2 merge with the site file, whose preview is deferred
  to its run ("preview deferred: it is made at the run, after step 1 has restored the base
  file"): before the base restore the comparison would be meaningless. The site file is
  checked for merge before anything is created; if step 1 fails its preview, step 2 is
  cancelled with the reason.
- One approval (`/approve`) covers every step awaiting it; `/execute` (background by
  default) runs the steps that have not succeeded, in order; a step that does not succeed
  ends the plan and the later steps are cancelled with "not run: step N ended <state>".
  The steps share one Stop signal (`/stop`), so a stop also keeps later steps from running.
- A later step run on its own (its own page) is refused until the steps before it have
  succeeded.
- UI: Deployment Center → "New staging plan (base file, then site file)"; a staging page
  with both steps, Approve both steps, Execute, Stop; each step's page links back to it.

### D-072 FortiOS replies: control codes, a repeated statement and the VDOM note are not warnings (2026-11-24)
Bench, corrected site file on a clean base (v41, 1784 statements, every one accepted): of
six warnings, three were empty (terminal control codes only), one was the statement itself
(it holds a double space, so the echo removal missed it) and one was "current vf=root:0",
FortiOS's note on entering a VDOM. Replies now drop control codes and any line that only
repeats the statement (spacing ignored), and "current vf=<name>" is not listed. Everything
else is listed as before; error-looking replies still stop the script.

### D-073 First login on a new unit is an approved plan (2026-11-24)
Product owner: the first login of a new FortiGate (admin with an empty password, then a
demanded new password) must not be done by hand. Setting a password changes the device, so
it goes through the deployment lifecycle (no new exception to the CLAUDE.md rule): a plan
of kind `first_login` for one device (`POST /api/projects/{id}/first-login`; Deployment
Center → "First login on a new unit"; or "New unit: start with the first login" in the
staging plan, which then runs first login → base → site).
- Validation: the driver must declare `FIRST_LOGIN_SETUP` (FortiOS) and the device must
  have its own login, whose password is the one set.
- Preview (read-only): log in as that user with an empty password through Netmiko's normal
  path, which sends nothing at FortiOS's login (D-067); the unit's text is recorded and
  nothing is answered. The empty password refused (not a new unit) or reaching the prompt
  without a demand fails the plan; nothing is changed.
- Run after approval: preflight repeats the probe; the backup step records that a new
  unit shows no configuration before its first login; deploy logs in with the empty
  password and answers only the known questions (D-066: old = empty, new and confirm =
  the device's login); verification logs in afresh with the device's login and reads its
  facts. Audited as `device.password_set`. A change that does not complete ends as
  recovery required with the unit's text.
- The SSH wording of a factory unit's first login is not yet seen (Q-41): the questions
  answered are those captured after the base restore. Different wording stops the step
  with the unit's text, and nothing is guessed.

### D-074 Black Box LIG1014A over SSH: read-only driver from the switch's own output (2026-11-24)
Bench, factory-default LIG1014A v00.01.00 (Q-28 answered): SSH as `admin` with the empty
password lands at a bare `#` prompt, with no password demand; `show version` gives
`MAC Address`, an empty `Serial Number`, `System Name`, active and alternate images, and
`Board Type`, `Port Count`, `Software Version`; `show running-config` starts with
"Building configuration..." and ends with `end`; `copy ?` lists `tftp://server/path-and-
filename` (also `flash:`, `ftp://`), `running-config` and `startup-config` as sources, with
file names of letters, digits, `.`, `-`, `_`, at most 63, not starting with `-`;
`reload ?` lists `cold` and `defaults` (factory settings without restarting).
Driver `ssh.blackbox.lig1014a` (experimental), capabilities SSH and backup only:
- Netmiko type `generic` (sends nothing at login), so no paging or terminal command whose
  syntax is unconfirmed is ever sent; every command is read by UNDM up to the prompt (a
  bare `#` would end Netmiko's default read at the first `#` of the output).
- Facts from `show version`; the unit reports no serial number, so its base MAC address
  is its identity (`serial_number` carries it, `extra.identity` says so) and is what UNDM
  compares after a restart.
- Backup = `show running-config` without the banner; a read that does not end with `end`
  (for example stopped at a page break) is refused, never stored.
- Loading the team's file is not offered (plans are refused at validation) until the bench
  confirms: the destination of `copy` with a TFTP source, what `reload cold` asks, and
  whether SSH is allowed by the file's `access management` (Q-42, Q-27).

### D-075 Older SSH methods for the LIG1014A only; paramiko 3.5 (2026-11-24)
Bench: UNDM's Test connection to the LIG1014A failed with "Incompatible ssh peer (no
acceptable host key)" while PuTTY logged in from the same PC: the key exchange was agreed,
but the switch offers no host key type that paramiko 5.1 still has (5.x removed the SHA-1
key exchanges and the `ssh-rsa` and `ssh-dss` host keys; 4.0 keeps `ssh-rsa` but not DSA;
3.5.1 keeps both). The probe could not read the switch's offer (it closed new connections
then, probably while its few SSH sessions were taken), so the version that covers both
possibilities is used: `paramiko>=3.5.1,<4` (Netmiko 4.8's own minimum is 3.5.1).
Scope: every SSH driver passes `disabled_algorithms` for the SHA-1 key exchanges and the
`ssh-rsa`/`ssh-dss` host keys, which is what paramiko 5 gave them (the 2930F was validated
that way), except the LIG1014A driver (`legacy_ssh_algorithms = True`) and FortiOS, where
Netmiko's FortinetSSH keeps choosing the key exchanges itself as on the bench 101F. Even
for the LIG1014A the older methods are only used if the switch offers nothing newer.

### D-076 LIG1014A: long output continues at the switch's own page prompt (2026-11-24)
Bench with paramiko 3.5.1 (D-075): Test connection works; Retrieve information and Back up
stopped at the switch's page prompt "-- more --, next page: Space, continue: g, quit: ^C"
(Q-42 (2) answered: output is paged). The driver reads each command itself; at exactly that
prompt it presses `g`, the switch's own option for the rest without further pauses, and
removes the prompt and the characters a terminal uses to erase it (CR + spaces + CR,
backspaces, ANSI sequences), so a backup keeps each line's indentation. Nothing else is
answered; more than three pauses for one command, or silence without the prompt, ends the
read with the switch's text, and a backup that does not end with `end` is never stored. No
paging command (whose syntax is unconfirmed) is sent. The old reader fails the new test
with the bench's message.

### D-077 LIG1014A: the team's file is loaded by TFTP into the startup configuration, then `reload cold` (2026-11-24)
Bench, factory unit (Q-42 (1) and (3) answered): `copy tftp://<pc>/<file> ?` lists
`<url_file>`, `running-config` and `startup-config` as destinations; `reload cold` asks
nothing, prints "% Cold reload in progress, please stand by." (the prompt still follows) and
the session closes; error replies start with `%` ("% Invalid word detected at '^' marker.",
"% Incomplete command."). Procedure (replace mode, complete file only):
1. the file is offered on UNDM's TFTP server to this switch only, under a name the switch
   accepts (`undm-<hash>.txt`), and the switch runs `copy tftp://<pc>/<name>
   startup-config`; no prompt counts while the fetch is under way, and the file is withdrawn
   as soon as the exchange ends (D-063);
2. the whole file must have been fetched, and a `%` line in the answer stops the step: the
   switch is not restarted;
3. `reload cold`: the reload line (not the prompt after it) or the closed session is the
   restart; a switch that does not restart is reported (the file then takes effect at its
   next restart);
4. the usual wait, login after loading (the approved password the file sets), identity by
   MAC address, then verification: the name must be the file's hostname; how many of the
   file's lines `show running-config` shows is reported, with up to ten missing lines as
   warnings (the switch may show some lines differently: to be learnt from the first run).
Saving is not needed: the file was loaded as the startup configuration. Merge mode is not
offered. Not yet run on hardware; whether the file's `access management` still lets SSH in
afterwards (Q-27) decides whether step 4 can log in.

### D-078 LIG1014A load: "Import Done!" is the evidence; its '%' progress lines are not errors (2026-11-24)
First load on hardware: the switch fetched the team's file and answered "% Loading /<file>
from TFTP server <pc>", "% Saving 5997 bytes to flash:startup-config", "Import Done!
Configuration will become active after reboot!". UNDM (D-077) took the first `%` line for a
refusal and stopped before `reload cold`, so the file was in the startup configuration but
the switch still ran its factory configuration. Now the switch's own confirmation is the
evidence: "Import Done!" must appear; the "% Loading … from TFTP server" and "% Saving <n>
bytes to …" lines are progress; any other `%` line is a refusal. The saved byte count is
compared with what UNDM sent (reported, not a failure, as the switch may store the file in
its own form), and the switch's lines are kept as events. The fake switch prints the
bench wording; the old code fails that test with the bench's message.

### D-079 LIG1014A: first complete load passed on hardware; VLAN lists compared as sets (2026-11-24)
With v50 the team's file was loaded end to end on the factory LIG1014A: "Import Done!",
`reload cold`, the switch answered again after 29 s (first attempt), same MAC address,
login with the approved password (kept for the device), name as in the file, 191 of 192
lines shown. Q-27 answered: the file's `access management` ("web telnet" from VLAN 222
192.0.2.0–254) still lets SSH in from the PC on port 1/3. The one line "not shown",
`vlan 168,222,1001,1006`, is listed in the switch's own form; `vlan` list lines are now
compared as sets of VLANs (ranges understood), so a VLAN that is really missing is still
reported.

### D-080 LIG1014A firmware: `firmware upgrade tftp://<pc>/<file>`, then the switch's own restart (2026-11-24)
From the switch's help (Q-42 (4) answered): `firmware ?` lists `swap` ("Swap between Active
and Alternate firmware image", no arguments) and `upgrade`, whose argument is a URL
`<protocol>://[<user>[:<password>]@]<host>[:<port>][/<path>]/<file_name>` with the same
file-name rules as `copy`. What the upgrade prints, whether it asks anything, which slot it
writes and whether it restarts by itself are not known yet, so the driver learns them
safely: the image is offered by TFTP to this switch only (under its own name if the switch
accepts it, else `undm-<hash>.dat`); nothing is answered; no prompt counts while the image
is fetched; the whole image must arrive; a `%` line other than progress is a refusal; the
restart must come from the switch (session closed, or SSH port down; after a clean return
to the prompt UNDM waits up to 180 s for it). Then the firmware orchestrator's usual wait,
identity (MAC address) and check that the active image runs the new version. If the switch
returns to its prompt and does not restart, the step fails with its text and both image
slots: UNDM sends no `firmware swap` and no `reload`, because which image they would start
is not known. Firmware page: platform "Black Box LIG1014A" (`blackbox_lig1014a`). Not yet
run on hardware.

### D-081 LIG1014A firmware upgrade passed on hardware; device text shown for firmware steps (2026-11-24)
With v52 the bench unit was upgraded v00.01.00 → v00.01.01: the switch fetched the 5.5 MB
image, wrote it and restarted by itself about 4½ minutes after the command (its SSH port
stopped answering), answered again after 26 s (same MAC address) and runs v00.01.01. No
`firmware swap` or `reload` was needed. The pre-upgrade backup comparison reported two lines
of the team's file no longer shown afterwards: `ip http secure-server` and `ip http
secure-redirect` (Q-44). Staging order for this switch: firmware first, then the team's
file. The firmware orchestrator now also shows what a driver reports the device printed
during a step (as configuration loads already did).

### D-082 Safety switches can be changed in Settings → Safety (2026-11-24)
Product owner decision (Plan A, A1b): colleagues must be able to switch real-device changes
on and off without editing `backend\.env`. `services/safety_settings.py` keeps three switches
in `settings.json` in the data folder: `enable_real_device_writes`,
`enable_real_device_firmware`, `firmware_require_separate_approver`. Defaults are unchanged
(off, off, second approver on; rule 1). `GET /api/policy` reports the switches in force and
which are `locked`; `PUT /api/policy` changes them, records one `policy.change` audit event
per switch that really changed (actor, before, after), logs a warning, and answers 409 for a
switch fixed by the start-up settings (an `UNDM_*` variable or `.env` line wins, as before).
Production switches are not accepted (422): UNDM changes production devices only when its
start-up settings say so. The settings in force are read for every request and when a queued
plan builds its service, so turning a switch off stops an approved plan that has not started.
A damaged file counts as empty (everything off). The UI asks for a confirmation ("the devices
are spare units on an isolated bench") before a switch moves to its less safe position, not
for the safe direction. Refusal texts now name Settings → Safety instead of variable names,
and the second-approver refusal says how to proceed.

### D-083 Plain words and a work-ordered navigation (2026-11-24)
Plan A, A1a + A2: one glossary in the UI (`frontend/src/services/labels.ts`): a *device*, a
*system* (internally a project), a *plan* run in steps (internally a deployment), a *login*
(internally a credential reference), *file* (configuration). States, drivers, platforms,
fact keys, capabilities and audit actions are shown in words; internal ids stay visible only
under "Technical details". Navigation: Home, Systems, Devices, Files, Firmware, Console
setup, Plans, Advanced (Topology, Audit log), Settings; page titles match. Texts that were
wrong are corrected: the Firmware page lists the three real upgrade procedures (2930F,
FortiGate 101F, LIG1014A — experimental, each run on bench units); the Console setup page
says a FortiGate gets its password from a First login plan and a LIG1014A needs no console
setup; the Home page lost "Firmware Manager is planned for Phase 7" and shows what is
waiting for the user; the "port 8000" error text is gone. API paths and stored values are
unchanged.

### D-084 Feedback and confirmations: errors stay visible, one confirmation dialog (2026-11-24)
Plan A, A1c. An error from an action inside a dialog is shown in that dialog (it stays
open), not only in a passing message. Other errors stay on screen until closed and offer
"Copy details" to pass the text to a colleague. One confirmation dialog (`useConfirm`)
replaces `window.confirm` and the missing confirmations: cancel a plan, retire or delete a
firmware image, delete a login, delete a system (its name must be typed). Deleting a system
now also removes its logins' passwords from the credential store (before, they were left in
Windows Credential Manager); the audit event counts them (`stored_logins_removed`) without
any value. Layout: every table scrolls sideways inside its card, fields wider than 320 px
shrink on narrow screens, one top-level heading per page, status badges carry an icon as
well as a colour, the plan form's mode switch and the topology link mode have labels, and
configuration versions can be chosen with the keyboard. Checked at 390 px and 1280 px: no
page scrolls sideways.

### D-085 "Stage a system" wizard on a generalised staging engine (2026-11-24)
Plan A, A3 (product owner decision: guided staging wizard). Engine: a staging plan is now any
sequence of 1–8 steps for one device — `first_login`, `firmware`, `configuration` — made by
`POST /api/projects/{id}/device-staging` (`DeploymentService.create_device_staging`). Every
step is checked offline before any is made (inputs present, file fits its mode, the mode
taken from the file's kind unless given, secrets and login-after valid, image approved and
compatible, safety switches); a first login may only be the first step. Steps after the
first are previewed at their run, because earlier steps change the device; this now applies
to firmware steps too (the running version is read at the step's preflight; on a new
FortiGate it cannot be read before the first login). Approving a staging plan with a
firmware step needs a maintenance window (`POST /api/staging-plans/{id}/approve` takes
`window_start`/`window_end`); the second-approver switch applies as for any firmware plan.
`GET /api/projects/{id}/staging-plans` lists a system's plans with their device and step
states. The base+site endpoint (D-071) is unchanged. The console setup of the 2930F stays
its own action (CLAUDE.md exception, D-025/D-057); the wizard asks for it before the
switch's plan can be made. No new device-changing path.

Wizard (`/stage`, `/stage/{system}`): 1 system and its four devices by role (FortiGate 101F,
Black Box LIG1014A, two 2930F; found by name, then bench address, then order; missing ones
added with the bench defaults of `staging-run-design.md`, real or simulated); 2 files and
firmware per device (import a file in place, what UNDM found in it, tunnel-key values from
logins, login after loading; first login offered only where the driver supports it); 3
bench check (cabling, PC addresses, safety switches, console setup status, Test connection);
4 run board (one card per device: make the plan, approve, run, stop, follow; expected step
durations); 5 report (per device: firmware and identity read last, each step's result, start,
duration, approver, warnings; print or save as HTML). Choices are kept in the browser only;
the plans made are the record. The simulated FortiGate now also restores a base file, so the
whole run can be practised on simulated devices (no statement about real units). Messages
moved to the top centre so they never cover a page's buttons (bottom right hid
the wizard's Next, top right the plan's Run). Catalog notes for the
FortiGate 101F and 2930F brought up to date with the bench results.

### D-086 Page-by-page fixes (2026-11-24)
Plan A, A4, from the audit of every page: a device can be deleted from its page (its name
typed to confirm; the device itself is untouched); Add device checks the address (IPv4,
IPv6 or host name; no port or prefix length) and suggests the bench address for the model;
the firmware planner says why "Create upgrade plan" is not available yet and shows drivers
and platforms in words; the configuration plan form has column headings, always starts
from a real file choice (the one UNDM would take) so the file's needs are always shown, and
takes the apply mode from the chosen file's kind (shown, not silently changed; files of
both kinds in one plan are refused with a reason); audit details are shown as named values
(raw JSON one click away); the topology has a legend and an "Add link…" dialog that works
without dragging; a plan's page shows its latest 40 events with the earlier ones one click
away, warnings marked, and the staging note no longer assumes base and site files.

### D-087 Export and import of a system (`.undm`) (2026-11-24)
Plan A, A5 (product owner decision: each colleague runs their own copy and shares prepared
systems by export/import). `GET /api/projects/{id}/export[?include_firmware=true]` gives
one zip: `manifest.json` (format `undm-system-package`, version 1, who and when) and the
files it lists with their SHA-256: the system's settings, its devices as entered (no
retrieved facts, no plans or history), the names of its logins (never a user name,
password or key), its imported and generated configuration files, its topology and, on
request, the approved firmware images that fit its models. Backups are not exported (they
hold a device's running configuration). The team's files are exported as written and can
hold passwords (Black Box base64): the package is confidential, and the Export dialog says
so. `POST /api/systems/import` checks everything before creating anything: zip and format
version, every listed file against its checksum, plain file names inside the package (no
paths), sizes, driver ids known to this copy, links and files pointing at listed devices,
a free system name (another one can be given). Logins are created by name without a
password (the dialog lists them: store them on the Logins tab); firmware images arrive
"uploaded", their vendor checksum re-checked, never approved. Both are audited
(`system.export`, `system.import`). Not yet: mapping a package's login to an existing login
of another system (logins belong to their system).

### D-088 Plans that need attention stop waiting once checked; deleting from lists (2026-11-24)
Product owner, on the Home page: eight "Needs attention" 2930F loads from the bench sessions
of 2026-11-23 (before the fifth run succeeded) were listed as waiting, forever: the state is
terminal and UNDM had no way to record that the device was checked. Now a plan that needs
attention keeps its outcome but no longer *waits* when (a) a later, real (not dry-run),
successful plan covered all of its devices, which changed and verified them again, or (b)
a person records a check with a note (`POST /api/deployments/{id}/checked`: a `checked`
event "device checked by <who>: <note>" and audit `deployment.checked`). Plan lists and the
plan page carry `needs_attention` and `attention_cleared` (`checked` or `superseded:<id>`).
Home lists only plans still waiting, and its all-time "Did not finish" count became "Needs
attention" (still waiting). No database change.

Deleting (product owner: "make it possible to also delete on this page and other similar
pages"): devices from the Devices list (row menu, or several at once with the word
"delete" typed), systems from the Systems list (name typed), and plans from the Plans list,
a system's Plans tab and the plan page (`DELETE /api/deployments/{id}`). A running plan
cannot be deleted. Deleting a step of a staging plan deletes the whole staging plan, so the
step order can never be bypassed. Every deletion is audited with what the plan was; the
devices themselves are never touched. The device-kind badge is no longer cut short in
narrow columns.

### D-089 One message vocabulary; the safety switches shown only where they matter (2026-11-24)
Product owner, on the header pills "REAL-DEVICE CHANGES ON / FIRMWARE CHANGES ON" (solid red):
review every banner and present them better. The inventory found 50 banners in 25 files in 8
colours with no consistent meaning (red for a normal bench state as well as for errors, long
explanations as permanent banners, the same safety text on five pages, empty lists as grey
banners). Now there are four kinds of message, each with one colour and icon, drawn only by
`components/Notice.tsx`:
- Problem (red): something is wrong or blocks you; the fix is the action.
- Caution (amber): a risk to weigh at the point of action.
- Status (blue while running, grey when settled, teal when it worked).
- Help is not a box: `Hint` (small dimmed text, "More" for the rest); empty lists use
  `EmptyState`.
A Vitest guard fails if any other file draws a banner. Product owner decision: the safety
switches left the header; `SafetyHint` shows their state in one quiet line only where it
matters (next to Approve/Run of plans and staging plans for real devices, the console setup
Run, the firmware planner, the wizard's bench check, a real device's page), with a link to
Settings → Safety; nothing for simulated devices. The plan page shows one outcome message (a
plan that needs attention carries "Mark as checked…" as its action); the Run dialog names the
real devices that will change.

### D-090 Bench log: one masked text per system instead of screenshots (2026-11-25)
For the first full bench run through the wizard (a new system: FortiGate 101F and LIG1014A
factory default, 2930F preconfigured), results come back as one text.
`GET /api/projects/{id}/bench-log?hours=48` (0 = everything; `services/bench_log.py`) lists:
- the UNDM version and the safety switches in force
- each device as last read: model, driver and maturity, status, the facts read
- each console setup: outcome, verified, saved, message, findings
- each plan, oldest first: kind, mode, staging step, state, approver, targets with
  versions and messages, and every event with its time, stage and status

It masks with the diagnostics sanitizer (IPs, MACs, serials, labelled names) and with
values that belong to the system:
- its name and site
- device names
- hostnames read from the devices or written in the plans' files
- serials, MACs and login names
- names typed for an erase
- people's names
- double-quoted names in event text (FortiOS objects)

A factory hostname equal to the model is kept, so the log still names the models. The
sanitizer no longer takes a bracket for a serial number after "serial number". The dialog
("Bench log…" on the system page and the wizard's Report step) shows the text before
Copy/Download, with "read it through before sharing". The export is audited
(`system.bench_log`, no content). Wizard texts:
- each role says which login it starts with (Black Box new unit: admin with no password,
  the approved login after loading);
- a 2930F's console setup hint mentions "erase first";
- the bench check reminds a lone stager to turn off the second approver for firmware.

Bench checklist: `vendor-support/staging-wizard-bench.md`.

### D-091 All four on one bench switch; two devices never on one address (2026-11-25)
The product owner asked whether all four devices can be staged at once and how the laptop
connects. Yes: one small switch, connected to nothing else, one cable per device (FortiGate
MGMT, Black Box port 1/3, 2930F A port 2 and B port 3 after their console setups), the PC
on 192.168.1.50/24 and 192.0.2.50/24. Both 2930F team files set 192.168.1.1, so B (on the
temporary 192.168.1.2) runs only after A is staged and unplugged.
- The wizard's Bench check shows a cabling table (cable, address now, address after its file,
  from `roles.ts`) and names the device that must go first when two end at one address
  (`addressTakenBy`). The run board shows the same caution on the waiting device's card.
- New driver hook `check_before_apply(config, mode)`: a check that changes nothing, run in
  the plan's preflight after the diff; a failed result fails the target in preflight, so the
  plan ends "failed, no device was changed". Generic in the orchestrator; the ArubaOS-Switch
  driver uses it for a complete file that moves the switch to a new address: if a TCP
  connection to that address on the SSH port succeeds, another device answers there and the
  load is refused before the certificate step or the file. Before, the file was loaded, the
  serial check found the other switch after the restart, and the plan ended Needs attention.
- The probe is UNDM's own check (no vendor command); a device that answers neither SSH nor
  TCP at that address is not detected, and the serial check after the restart stays.

### D-092 The wizard requires a login after loading where the file sets a new password (2026-11-25)
First full wizard run: both 2930F and the FortiGate (first login → firmware → base → site)
staged. The Black Box loaded its team file ("Import Done!", restart), then refused the
login for 10 minutes. The plan had no login after loading (no "from now on logging in with
the credential chosen for after loading" event), so UNDM kept the factory login while the
file had set the approved password. The wizard showed the field as optional with "Same login
as now", which is right for the 2930F (their console setup already gave them the approved
login) and wrong for a factory Black Box. Roles now say when a real device needs it
(`roles.ts` `loginAfter`: Black Box team file, FortiGate base file); `planSteps` lists it as
missing until chosen, so "Make the plan" stays disabled, and step 2 shows the field as
required with the reason. Simulated devices and the 2930F are unchanged.

### D-093 First full wizard run: results, and two bench log fixes (2026-11-25)
Results (bench log of the run):
- FortiGate 101F, factory default on v7.2.8: first login (Q-41 answered: "You are forced to
  change your password. Please input a new password. New Password:"), firmware 7.6.5 (image
  fetched, restart, back in about 2.5 minutes), base restore (the forced password change after
  the restore answered as in D-065), site script (1784 statements accepted, revision saved):
  one staging plan, every step succeeded.
- 2930F A (preconfigured): the first console setup erased it, then reached no command prompt
  on the console; the second was refused because the typed hostname no longer matched (the
  switch was already erased, nothing done); the third set it up. Already on WC.16.10.0025
  (primary and secondary), so its firmware step was skipped; its file loaded and verified.
- 2930F B (new, on WC.16.11.0001): approved downgrade to WC.16.10.0025 in both slots, then its
  file; it came back at the shared address with A unplugged, as D-091 asks.
- Black Box: firmware v00.01.00 → v00.01.01 succeeded; the file step ended Needs attention for
  want of a login after loading (D-092).

Bench log fixes:
- A FortiGate revision is named after its file (without the extension), and that name was
  shown in clear. The log now masks file names with and without their extension, and any name
  in "revision '…'".
- A failed console setup now keeps the last 1500 characters of its masked console transcript
  in its audit entry (passwords are never in the transcript), and the bench log prints them,
  so the next "Could not reach a command prompt" shows the switch's own words.

### D-094 Devices take their real hostname (2026-11-25)
Product owner: the wizard's placeholder names (`<system>-sw-a`) should give way to the real
ones, taken from the configuration file chosen for the device. When a non-dry-run plan is
made with a supplied (imported) file, the device is renamed to the hostname the file sets
(the driver's file report; FortiOS: `set hostname` in `config system global`), before any
connection. After the file is loaded and verified, the hostname the device reports is
compared again and wins if it differs. A hostname that is the model's factory name is not a
name; a name another device of the system has is not taken (`device.rename_skipped`). Audit:
`device.renamed` (from, to, source). The wizard finds its devices by the role it gave them at
creation (`device.role`), then by name and address as before, so renamed devices, and two
2930F at one address, keep their cards.

### D-095 Erase: UNDM reads the switch's name, the person confirms it (amends D-057) (2026-11-25)
D-057 made the person type the preconfigured switch's hostname. On the bench nobody knows it
without a terminal program, which UNDM is meant to replace. New read-only console action
(`POST /api/devices/{id}/provisioning/console-identify`): logs in with the switch's current
login, returns the hostname of its prompt and whether it holds configuration, sends no
configuration command, and does not answer a new switch's "configure the manager
credentials" dialogue (`ArubaOSSwitchConsole.read_only`). The page shows "The switch on this
console is X" with a checkbox "Yes, erase X"; the run sends that name, and `erase_existing`
still refuses if the switch on the console has another name at that moment. A switch found
at factory default or new is reported as such ("run the setup without erase"). D-057's other
safeguards are unchanged: explicit request, current login, device name typed for the run,
write switch, audit.

### D-096 A device is moved to a spare address, unsaved, to free its own (EXPERIMENTAL) (2026-11-25)
Both 2930F of a system end at one management address (D-091); unplugging the first by hand
worked but is a step to forget. The product owner asked for something that undoes itself
(a port that returns after 30 minutes). No timed command is verified for ArubaOS-Switch, so
none is used. Instead: new plan kind `free_address` (lifecycle: preview with the exact
commands, approval, backup, run, evidence) and driver capability `TEMPORARY_ADDRESS`,
implemented for ArubaOS-Switch only. The switch gets a spare address in its running
configuration (`vlan <id>` / `ip address <spare> <mask>`, the team's own console commands),
UNDM reaches it there and checks its serial number, removes the old address if the switch
kept both (`no ip address`; Q-45 asks which a real unit does), reads back, and checks that
the old address has gone quiet. `write memory` is never sent: the saved configuration still
matches the team's file, and the switch returns to its own address at its next power-on,
which shipping from the bench guarantees. No port is switched off.
- The wizard adds the step to the second switch's plan before its file step, when the device
  in the way can be moved (`planSteps`, `addressTakenBy`, spare address 192.168.1.3).
- Nothing answering at the first switch's address means nothing to move (off or unplugged):
  the step succeeds without a change, so the old manual way still works.
- The device keeps its own address on record; `observed_facts.extra.temporary_address` makes
  UNDM reach it at the spare one. It is cleared when a later plan finds the device back at its
  own address, or by "It was restarted" on the device page (no device contacted).
- A failed step ends Needs attention and says that a restart returns the switch to its saved
  configuration. The v61 check before sending a file stays as the last guard.
- The two addresses of a plan are kept in the target's from/to fields (no schema change).

### D-097 Backups as files on request; the report says when a system is complete (2026-11-25)
Backups stay in the database (`ConfigVersion` kind `backup`: before each change, and read back
after a load) and are shown on the device's Configurations tab. The product owner asked where
they are and chose download buttons over an automatic folder (a folder of device
configurations would need protecting). `GET /api/projects/{id}/backups.zip`: one folder per
device, one text file per backup named by UTC time, before/after and plan, a README that says
they are confidential; audited with counts only. "Backups…" on the system page; a download
icon on every row of a device's versions.

The first full system finished on the bench the same day (Black Box file loaded after its
login was corrected; Q-44 partly answered). The product owner asked how the process ends: the
Report step now says "All N devices are staged" with what is left to do (save the report,
download the backups, safety switches off, power off and label), or which devices are still
open. A system is complete when every device's latest staging plan has succeeded; UNDM
records no separate "completed" state.

### D-098 "Open SSH window": UNDM starts the PC's SSH program; it sends nothing itself (2026-11-25)
The product owner asked for Open → SSH / Web page on a device, as the reference tool offers.
A browser cannot start a terminal, and a terminal inside UNDM would let commands reach a device
outside plans and approvals. So `POST /api/devices/{id}/open-ssh` starts Windows' own SSH client
(OpenSSH, `ssh.exe`) in a new console window on the PC running UNDM, with `-p <port>
<user>@<address>` (the user from the device's login; the temporary address if one is set). The
password is never passed: the person types it. Arguments are a list (no shell) and checked
against strict patterns; simulated devices and requests not from this PC are refused; audit
`device.session_opened`. Bench units are reset and re-used at the same addresses, so, like
UNDM's own sessions, the window neither keeps nor checks host keys. What is typed in that window
is the person's own work, outside UNDM's plans and audit, as with PuTTY; the device-changing rule
(changes only through the lifecycle) concerns what UNDM sends. "Open web page" is a link to
`https://<address>`.

### D-099 One device menu, the system tree, watching devices, the device log, restart as a plan (2026-11-25)
Studied for workflow only from three screenshots of the reference tool (nothing copied; its
product-specific items such as zones, clusters, MAC filtering and audit scripts not taken over):
- **Device menu** (`DeviceMenu.tsx`) everywhere a device is listed, by "⋯" next to its name or
  right-click on its row: Open SSH window, Open web page, Copy address; Check information (reads
  the device and shows firmware, image slots, serial/MAC, hostname, with Copy); Test connection;
  Wait until it answers (checks every 10 s for up to 10 minutes, then tells); Back up now;
  Configurations and compare; Device log; Restart…; Console setup (2930F); Make a plan…; Delete.
  Items appear only where they apply (real or simulated, capabilities).
- **Restart** is a plan kind `restart` (preview with the command it sends, approval, backup,
  restart, wait until it answers with the same serial number, facts). New capability `RESTART`
  for drivers with a restart already run on hardware: ArubaOS-Switch `boot system flash primary`
  (the firmware procedure's restart; answers "n" to saving) and LIG1014A `reload cold` (the
  file procedure's restart). FortiGate: none verified yet (Q-47), so no Restart item. A device
  at a temporary address (D-096) is waited for at its own address and the note is cleared.
- **System tree** on the system page: the system, then Firewalls / Routers / Switches / Other,
  each device with its icon, reachability dot, tick box (shared with the table) and menu.
- **Watch devices** (per system, remembered in the browser): every 15 s,
  `GET /api/projects/{id}/reachability` tries a TCP connection to each device's management port
  (no login, nothing sent) and the tree and table show a dot.
- **Device log**: the device page's Activity tab becomes Log, from `GET /api/devices/{id}/log`:
  its audit entries and its plans' events, newest first, filtered (All, Plans, Console, Tests
  and reads), and copied masked (names, addresses, serials).

### D-100 A FortiGate license file is loaded through an approved plan (EXPERIMENTAL) (2026-11-25)
The project lead supplies a license file (already verified by the team); today it is uploaded on
the FortiGate's web page after staging. Fortinet documents a CLI way for hardware units
(FortiOS 7.2 "manual licensing for FortiGates in air-gap environments"):
`execute restore manual-license {ftp | tftp} <file> <server>`, with the warning that it
"will overwrite the current license and reboot the system". UNDM uses it with its own TFTP
server, like the image and base restores: plan kind `license` (preview with the command,
approval, backup, fetch, answer only that question with "y", wait until the unit answers with
the same serial number, read its facts), capability `LICENSE_FILE` (FortiOS driver; simulated
FortiGate for practice). Not yet run on 7.6.5 (Q-46): marked experimental in the dialog; after
it, the person checks the license status on the unit's web page (System → FortiGuard).
The file is stored for its device (`ConfigVersion` kind `license`, base64), never listed or
shown, kept out of system exports and backup zips; only its name, size and hash are audited.
UNDM does not check its content (the team does). Device menu: "Load license…" uploads the file
and makes the plan; the Report step reminds that a FortiGate's license is loaded from its menu.

### D-101 The erase dialog shows the login the switch gets after the erase (2026-11-25)
Bench: a 2930F preconfigured with the factory login (no password) was erased with that login
as "Its current login" (right), but the device's own login was the same factory login, so the
run was refused at the end ("attach the approved login"). The two logins mean different things:
the current login is used only to log in and erase; the device's own login is set on the switch
after the erase and must be the approved one. The erase section now shows "After the erase it is
set up with this device's login: X" with a link to change it, and refuses up front (button
disabled, reason shown) when the device has no login, its login has no password, or it is the
login being erased. `CredentialRefOut.empty_password` tells whether a stored login has no
password (never the value). The backend refusal says where to change it and that nothing was
erased.

### D-102 Console setup asks for both logins; a switch that keeps its password after the erase (2026-11-25)
Bench, second system: a 2930F preconfigured with a factory login was erased (`erase
startup-config`, confirmed, restarted), but its manager password survived: after the restart
the console asked "Username:" and refused the approved login ("Authentication failed. Please
verify that the username and password are correct." three times, then "Session Terminated").
A second run without erase showed operator level without a password and `enable` refusing the
approved password ("Unable to verify password"). On the first system's unit the erase had
cleared the passwords, so units differ (probably by how the credentials were stored).
Product owner: the console setup should take both logins. It now does, for every run:
- "Login it has now" (factory or preconfigured; empty for a new switch) and "Approved login
  (its login after the setup)", the device's own login, chosen right in the dialog.
- UNDM logs in with the approved login; when the switch refuses it, at the login or at
  `enable`, UNDM tries the login it has now, once (`ArubaOSSwitchConsole.fallback`), also
  after an erase. The transcript notes the switch.
- When the setup succeeds on the login it had, that login becomes the device's login in UNDM
  (audit `device.credential_changed`, reason "the switch kept its previous password") and the
  device is marked so that a complete-file plan requires "Login after loading" (the team's
  file sets the approved password); the wizard lists it as missing and the backend refuses a
  plan without it. The mark is cleared once a load reaches the switch with the approved login.
- No new command: changing an existing manager password on the console is not done, because
  its dialogue is not yet seen on hardware.
The simulator models the surviving password (`keep_passwords_on_erase`) with the bench wording.

### D-103 Console setup: the address is refused because VLAN 1 holds one by DHCP (2026-11-25)
Bench: a 2930F's console setup ended "Commands were accepted but the configuration read back
does not show the expected VLAN, port and address". The transcript shows the switch refused
`ip address` in the OOBM VLAN with "An interface with the same IP address or subnet or an
overlapping network … already exists", although its configuration had no other static
address. VLAN 1 asks for an address by DHCP on a factory switch; one of its ports was cabled
to the bench network, where a DHCP server gave it an address in the same network. Which
device served DHCP is not known (not checked).
- The switch's wording is now recognised as a rejection (observed text, not invented), so
  the setup stops at that command and quotes the switch.
- The message says what it means and what to do: unplug every network cable, switch the
  switch off and on (nothing was saved; this discards the leftover VLAN and the DHCP
  address), run the setup again, and plug its management port in only afterwards.
- UNDM does not remove VLAN 1's DHCP setting itself: that would add a command to the
  console bootstrap that the team's procedure does not have (D-025).

### D-104 Console setup: the port comes from the switch's role and is checked first (2026-11-25)
Bench: a new 2930F's console setup stopped at `untagged 83` ("Module not present for port or
invalid port: 83"); the free-text port field held 83 on a 48-port switch (ports 1-52).
- The console setup page starts, for a device added by Stage a system and with no saved
  settings, from its role's bench cabling: port 2 (switch A) or 3 (switch B) and the role's
  address (B: 192.168.1.2/24). A different port shows a caution; the field stays editable.
- Before any change, UNDM checks the port against the switch's own running configuration
  (the ports its VLANs list; factory: VLAN 1 `untagged 1-52`). A port it does not list is
  refused with the list, and nothing is sent. No model port table is assumed.
- Quotes of a rejected command no longer include the switch's prompt.- Amends D-103 after a second refusal on another switch (port 3, 192.168.1.2): the switch's
  refusal quotes only the address being set, so D-103's "VLAN 1 by DHCP" was a guess. On that
  refusal UNDM now reads the switch's `show ip` (read-only) and quotes the lines that hold
  an address in that network; the DHCP advice is given only when that line says DHCP.

### D-105 Logins, default logins and certificate answers for all systems (2026-11-26)
Product owner: every system of this project uses the same logins (the tunnel key included)
and the same 2930F certificate answers; entering them per system, then choosing them device
by device, is repetitive.
- **Logins for all systems**: `CredentialRef` without a system (`project_id` NULL,
  migration 2abfdc4c7344). Settings → For all systems lists, adds, sets and deletes them
  (`GET/POST /api/credential-refs`). A system's login list returns its own logins, then the
  shared ones (`shared: true`), so every picker offers them; the system page shows them
  read-only. A device, plan, secret or console setup may use its own system's logins or a
  shared one (`app_settings.usable_by`), never another system's. Shared names are unique
  among shared logins. Deleting a system keeps them; deleting one unassigns it everywhere.
- **Default logins per device** (`app_settings` table, `GET/PUT /api/settings/defaults`):
  FortiGate login / login after loading / tunnel key; Black Box login / login after
  loading; 2930F login / login it has now. Only shared logins can be defaults. Stage a
  system's **Add it** sets the device's login; **Use the default logins** fills devices with
  none; step 2 fills the login after loading and the site file's secret once (a cleared
  choice stays cleared); the console setup's "Login it has now" starts at the 2930F default.
  Simulated devices are left alone. Every choice stays editable per device.
- **Certificate answers for all systems** (`GET/PUT /api/settings/certificate`): used when a
  system has none of its own; a system can still override them (System settings tab).
- Existing systems keep their own logins and answers (product owner's choice); export lists
  shared logins by name and import matches them with this PC's shared logins of that name.
- Audited: `credential_ref.create` (with `shared`), `settings.defaults` (login names only),
  `settings.certificate` (whether set). No password ever leaves the credential store.

### D-106 "Make room" uses a spare address in the other bench network (2026-11-26)
Bench: B's "Make room" step on switch A ended "The switch took the command but does not
answer at 192.168.1.3". The SSH driver did not recognise the 2930F's refusal wording ("An
interface with the same IP address or subnet or an overlapping network … already exists",
seen on the console on 2026-11-25, D-103), so it took a refusal for acceptance. The step
recorded no device output, so the refusal is inferred, not seen; A was left at 192.168.1.1.
- The wording is now a rejection in the ArubaOS-Switch SSH driver. A move refused before any
  change ends **Failed: nothing was changed**, not Needs attention.
- The spare address is **192.0.2.3** (same mask as A's own), in the PC's other bench
  network, so it is not a second address in A's network. Unverified: whether the 2930F takes
  an address of another network next to its own; a refusal stops the step with nothing
  changed. Q-45 updated.

### D-107 "Make room" switches off the first switch's management port, unsaved (2026-11-26)
Bench (bench log, 08:08): with the spare address 192.0.2.3 (D-106), switch A accepted the
address, but SSH to it from the PC (source 192.0.2.50) went unanswered. A's team file allows
management only from 192.168.1.0/24 (`ip authorized-managers`,
`vendor-support/aruba-2930f-staging.md`), and the switch refuses a second address in that
network. So no spare address can work on a staged 2930F. D-096 and D-106's spare address
is withdrawn.
- **Product owner's choice:** UNDM switches off A's management port, unsaved, with
  `interface <port> disable` at configuration level. This is the vendor's ArubaOS-Switch
  CLI as quoted from the Management and Configuration Guide; it has not been run on this
  bench yet, so the step stays experimental. Never `write memory`.
- **Which port:** the one untagged port of the VLAN holding A's address, from A's running
  configuration. Several ports are refused; UNDM cannot tell which one the PC uses.
- **Evidence:** the session ends with the port (expected), then A's address must stop
  answering within 30 s (D-031). If it keeps answering, or the switch rejects the command
  ("invalid port" now recognised, as seen on the console on 2026-11-25), the step ends
  Failed with "nothing was changed on it".
- **After:** the device note `management_port_off` (port, since) replaces
  `temporary_address`. The run board and the device page say "Port 2 off until its next
  power-on". The note clears itself when A answers again, or by hand.
- **Recovery:** switch A off and on. Nothing was saved on it, and its file and password
  stay.
- The timed variant asked for on 2026-11-25 (port back after ~30 minutes) still has no
  verified command; A stays off the network until it is switched off and on.
- **Bench, 2026-11-26 08:27 (first run):** worked. The session stayed open and silent after
  the command, so UNDM waited out its read timeout (2 minutes) before checking; since v80 that
  read waits 10 s. B's file then loaded at 192.168.1.1.

### D-108 A real finish to staging a system (2026-11-26)
Product owner, after the first system staged end to end through the wizard (Make room
included): "I still do not see the whole process being finished or completed". The Report
step said "All 4 devices are staged" in prose; the stepper stayed open and nothing recorded
the end.
- **Finish checklist** on the Report step. Ticked by UNDM:
  - every device's latest staging plan succeeded;
  - no switch left with its port off (D-107), with a Test button after switching it off and
    on;
  - safety switches off, with **Turn them off** (the audited policy change).

  Ticked by the person (kept per system in the browser):
  - the FortiGate license loaded or not needed;
  - report saved (Print / Save as HTML tick it);
  - backups downloaded (the download ticks it);
  - devices powered off and labelled.
- **Finish staging** is enabled when all are ticked. The server checks again: the named
  devices' latest staging plans succeeded and none has its port off. It records
  `Project.staged_at` / `staged_by` (migration 1e637569cbdd) and audits `system.staged`.
- **Shown everywhere:** the stepper shows every step done ("finished <date>"); the report
  says when and by whom; the Systems list, the system page and Home show **Staged <date>**.
- **Reopen** by hand (`system.reopened`), or automatically when a new staging plan is made
  on the system, so a finished system never hides newer work.
- **Amended, bench 2026-11-26 (v81):**
  - A switch whose port Make room switched off is not tested: switched on again it answers
    at the address the other switch now has, so a test could reach the wrong switch. The
    person states it was switched off and on (**It was switched off and on**, audited
    `device.management_port_on`); a later plan or read that reaches it also clears it.
  - Safety switches fixed in `backend\.env` are named with their exact lines, in the
    checklist and in Settings → Safety: deleting them once hands the switches to Settings.

### D-109 The FortiGate license is an optional last step of its staging plan (2026-11-26)
Product owner: the license could not be found in the app (it was only in the FortiGate's menu,
⋯ → Load license…, D-100), and loading it must be optional because the file is often not
there when the firewall is staged.
- **Wizard step 2:** the FortiGate card has **License file (optional)**. Choosing a file
  stores it for the device (never shown, as D-100) and adds a `license` step as the last step
  of its staging plan, previewed at its run like the other later steps. Without a file the
  plan has no such step, and nothing is missing.
- **Later, also after staging:** the device menu's **Load license…** (an approved plan of its
  own), unchanged.
- **Finish checklist:** ticked by UNDM when the plan's license step succeeded; otherwise
  "loaded, or later", ticked by the person, with where to load it later.
- Still experimental: the license load has not run on a FortiGate yet (Q-46).

### D-110 Black Box LIG1014A: both image banks get the approved version (2026-11-26)
Product owner: as on the 2930F, both image banks of the LIG1014A must hold the approved
release. Bench (web page "Software Image Selection", 2026-11-26): after UNDM's upgrade the
active image is v00.01.01 and the alternate keeps v00.01.00. So `firmware upgrade` writes the
bank that is not running and starts from it (as also seen on 2026-11-24).
- **"Also write it into the backup slot":** for the LIG1014A this runs the same `firmware
  upgrade` a second time. It fills the other bank, and the switch restarts from it. UNDM
  waits for it, then requires both banks (`show version`: Active and Alternate Image) to
  show the version, or the step fails.
- No `firmware swap` or `reload` is used.
- Experimental until run on hardware. A switch already at the version (this bench's unit)
  gets only the second upgrade.
- The wizard ticks the option by default when an image is chosen for a switch that has a
  second bank (2930F, LIG1014A); it can be unticked.

### D-111 Generating a system's files from the team's templates by zone (2026-11-26)
Product owner: UNDM should generate the files of all four devices of a system; the FortiGate
base file stays the same for every zone. The product owner supplied the current files of
two zones.
- **The team's numbering convention.** Five rules turn every file of one zone into the
  other zone's file exactly (all four files, every line):
  1. the zone tag `z` + 3 digits;
  2. `10.(127+zone).x.x`;
  3. `10.zone.x.x`;
  4. `10.0.zone.x`;
  5. `130.zone.x.x`.

  Everything else is copied unchanged. Zones run from 1 to 128 (127+zone ≤ 255). These are
  the team's convention as shown by its files, not vendor facts; a new file version is
  checked again on import.
- **Templates stay outside the code.** They are kept in UNDM's database on the PC
  (`config_templates`, migration bc4f1515c70a), imported in Settings → For all systems →
  Configuration templates, one per role:
  - FortiGate base (used as it is);
  - FortiGate site script;
  - BH-DMZ 2930F;
  - LTE 2930F;
  - Tetra Black Box.

  The team's files are never committed; tests use fictional zones.
- **Import.** The reference zone comes from the file name, or is given. UNDM counts the
  replacements per rule and lists lines that still hold the zone's number in another form,
  for a person to check. With the same file for a second zone, the template is kept only
  if it gives that file exactly (`verified_zone`). A newer version becomes current; older
  ones are kept.
- **A system's zone.** `Project.zone`, set in Stage a system step 1 and prefilled from a
  `zNNN` in the system name.
- **Generate** (wizard step 2): renders each role's template for the zone and stores it on
  its device as an imported file named as the team names it. Every existing check applies:
  recognition, the secret slot, the HTTPS-certificate requirement, naming from the hostname.
  The wizard's choices are filled.
- **Compare with the devices' files** (read-only): each rendered file against the best
  matching file a person imported on that device, line by line, with the first differences.
- Generated files reach devices only through approved plans, as before.
- Audited: `template.import`, `template.delete`, `config.generate` (versions, zone, hashes;
  never content).
- **Local check (2026-11-26, not committed):** the four files of the first zone supplied,
  imported with the second zone's files as proof, all verified. Generating for the second
  zone through the API gave its files identical line for line.
- **Byte for byte (v83, product owner decision 2026-11-26).** The product owner compared
  UNDM's files for a third zone with the team's own: all four were identical line for line, and the
  Black Box file byte for byte. Three of the team's files are written with Windows line
  endings (CRLF) and no line break after the last line. UNDM had written LF with a final
  line break. Decision: generated files must match byte for byte.
  - A template keeps the imported file's formatting (`line_ending` lf|crlf, the one most
    lines use; `final_newline`), detected from the file as supplied, before UNDM normalises
    it (migration e1c8964a4d52; existing templates default to LF with a final line break,
    so re-import them once).
  - `configgen.zone.as_file` writes a normalised text in that formatting; only line endings
    change. Downloads use it: `GET /api/templates/{role}/file?zone=N` and
    `GET /api/templates/files.zip?zone=N` (every current template, the team's file names;
    audited `template.files_export`, names only). The wizard's step 2 has **Download the
    files for zone N**; Settings has a download per template for a chosen zone.
  - Files stored on devices for plans stay normalised, as every imported file is: the
    drivers send them line by line, so the devices get the same lines either way.
    **Compare** stays line by line and says that line endings are not compared.
  - An import with a second zone's file also reports whether the download is that file byte
    for byte (`verified_bytes`).
  - Local check (not committed): the first zone's files imported with the second zone's as
    proof (all four byte for byte); the third zone's zip compared with `cmp` against the
    product owner's files for that zone: all four identical byte for byte.

### D-112 Nokia 7705 SAR-Hmc: first access over the console (2026-11-26)
Product owner: every system also has a Nokia modem (7705 SAR-Hmc) and a Nokia Flexi BBU.
The modem is staged over its console cable only. A factory unit refuses the default login;
the team "breaks" it with a boot-menu procedure, recorded on the console and supplied.
- **Evidence.** The recording (TiMOS 20.5.R1) and Nokia's public guides, quoted in
  `docs/vendor-support/nokia-7705-sar-hmc.md`. Every question UNDM answers and every command
  it sends is in the recording, except `environment no more` and the pager text, which Nokia
  documents. The default login `admin`/`admin` is Nokia's documented default and is what
  the team types after the boot-menu steps (product owner).
- **Where it runs.** Console setup. It is a console bootstrap of a factory-default device,
  so it falls under the existing exception to the deployment lifecycle (D-025) and keeps its
  safeguards: preview, typed device name, the real-device switch, a factory check, read-back
  before saving, audit. No new exception was added.
- **Procedure** (`provisioning/sros_sar.py`): the person presses Run and switches the modem
  off and on. UNDM reads the boot options the modem lists, sends a key only to a factory
  unit (one with `auto-discover` lines), answers the recorded boot-menu questions in the
  recorded order (configuration file `none`, auto-discovery `no`, boot options file not
  written), logs in with the factory login, then: `admin save config.cfg`,
  `exec cf3:/config.cfg`, the admin password, `bof primary-config`, `bof persist on`,
  `show bof` read back, `bof save`, `admin save`, `show system information`.
- **Answering only what is known (D-031).** Any other question ends the run with the modem's
  words; a line starting `MINOR:`, `MAJOR:`, `CRITICAL:` or `Error:` ends it; `bof save`,
  `admin save` and `exec` must show their recorded confirmations.
- **The password** is the device's login in UNDM (user name `admin`). It is typed on a
  command line the modem echoes, so the console session masks listed secrets in both
  directions (`ConsoleSession.secrets`); it never reaches the transcript, a message or the
  audit. A password with spaces, quotation marks or non-ASCII characters is refused before
  anything is sent.
- **A unit that is not from the factory** (no `auto-discover` in its boot options) is left
  alone: no key is sent. If it accepts the device's login the run ends "already done".
  Resetting a staged modem is not offered; it would replace its configuration and needs
  its own decision, as D-057 was for the 2930F.
- **Model and drivers.** Catalog entry `nokia-7705-sar-hmc` (router); `mock.nokia.sar`
  (simulated) and `console.nokia.sar` (experimental, console only: every operation of the
  driver contract is unsupported for now). A device reached over its console only needs no
  management address; network tests say so.
- **Wizard.** A fifth role, staged over its console only: no plan yet. It counts as staged
  after its first access, in the report and in Finish staging (`finish_system`).
- **Not built:** loading the modem's configuration (next: a plan over the console), its
  file by zone, facts, backup, firmware. Open questions Q-49 to Q-53.
- **Status:** experimental. Run only on the simulated console; the first bench run decides
  the rest.
- **First bench run (2026-11-26, v84): the question was never answered.** UNDM received the
  whole start of a factory unit (U-Boot, Linux, the TiMOS boot ROM, the boot loader), the
  boot options and the 3-second question, printed again each second as it counts down. It
  pressed no key; the unit started normally and UNDM gave up after its 4-minute limit with
  "start-up text did not appear". Nothing was changed. Causes, all UNDM's:
  - questions were matched only at the very end of the output, after a pause. A control
    character after the sentence (backspaces to redraw the countdown, say) or a steady
    trickle of bytes kept that from ever happening. Reproduced with the real session
    settings; the cleaned transcript cannot show which one the unit does;
  - the unit reaches the question about 2.5 minutes after power-on (its own clock lines),
    which left under 90 seconds to switch it off and on;
  - the message said nothing had appeared although text had.
- **Fix (v85):**
  - questions with a time limit, and the login prompts, are found anywhere in the output and
    answered at once (`ConsoleSession.wait_for`); command-line prompts still wait for the
    answer to end;
  - control characters other than line feed and tab are dropped from the text and counted;
    a matched prompt never waits past its deadline;
  - the key is **Enter**, as the team presses (product owner, 2026-11-26; closes Q-49);
  - UNDM waits up to 10 minutes for the question;
  - messages tell "nothing arrived" from "text arrived but no question" and from "not
    recognised";
  - the raw characters at the question (control characters written out) and the counts of
    dropped ones are returned as technical details, masked, added to the sanitized
    transcript and the audit: the next bench run shows exactly how the unit writes it
    (Q-55);
  - while it runs, Console setup shows the stage, the time, the bytes received and the last
    line (`GET /api/devices/{id}/provisioning/console-progress`, in memory, read-only);
  - shared text also masks UUIDs (the unit's flash volume UUID appears in its start).
- The steps after the question (boot menu, login, commands) have still not run on a modem.
- **Second bench run (2026-11-26, v85).** Enter at the 3-second question worked and the
  modem opened its boot menu. UNDM then stopped at "Type "sros" and hit ENTER within 30
  seconds…", reporting it as a second, unexpected question. Nothing was written.

  The technical details showed the raw characters:
  - the 3-second question: `\r` + sentence + three spaces + three backspaces;
  - the sros question: a one-line field. It is `\r` + question + a space + what has been
    typed + five spaces + five backspaces, **redrawn whole on every key** (and, by its
    countdown text, each second). UNDM saw the redraw after its first letter as a new
    question.

  The countdown starts at 30 seconds; the recording's "25" was the count when the person
  typed. Line endings are `\r\r\n`.
- **Fix (v86):**
  - a question already answered that appears again **on the same line** is a redraw and is
    ignored. After a line break it is the question asked again: UNDM stops and answers
    nothing twice;
  - typed answers go one key at a time (0.15 s apart, as a person types);
  - Enter is pressed only once the modem shows the answer, in its redrawn field or as a
    plain echo. Otherwise UNDM stops without Enter;
  - each boot-menu step may take 40 s (longer than the 30-second countdown);
  - the raw characters at every boot-menu question are kept as technical details (Q-56).
- **Third bench run (2026-11-26, v86): the first access worked on hardware**, from the
  3-second question to "Changes Since Last Save: No". The other boot-menu questions echo
  plainly (Q-56); `admin save config.cfg` confirms with "OK" and "Completed." (Q-52).
- **v87:**
  - UNDM ends with `logout` and checks that the login prompt appears. Nokia documents this:
    "When the logout command is issued from the console, the login prompt is displayed"
    (Q-51). The console is no longer left logged in as admin;
  - `admin save config.cfg` must confirm;
  - shared text masks SNMP engine IDs (their tail is a MAC address of the unit; one was left
    unmasked in this run's shared transcript);
  - the transcript marks a typed password as "(password: not shown)". The sharing filter had
    garbled "(password sent)" into "(password ***REDACTED***".

### D-113 Nokia Flexi BBU (FSMF): guided by hand first (2026-11-26)
Product owner: the BBU is an FSMF staged in the browser through WebEM on the LMP port
(192.168.255.129): firmware first, then the SCF. The team has no Nokia tool for scripted
operations.
- A web search found no public description of an interface to WebEM. A copy of Nokia's
  WebEM User Guide says its interface is binary and not for third parties, and names a
  "WebEM Remote Tool" for automation whose commands are not public. Everything found is
  unverified (`docs/vendor-support/nokia-flexi-bbu.md`).
- **Decision:** UNDM does not drive the portal. The first version keeps the firmware package
  and SCF with the system, makes the SCF by zone if two zones' files prove the rules, checks
  read-only that the LMP answers, opens the portal, shows the steps and records who did
  what. Automation waits for Nokia's tool with its manual, or for a later decision on
  browser automation after bench screenshots.
- Not built yet; needs the answers to Q-54.

### D-114 The modem's file and the Flexi BBU's SCF from templates, by zone and system (2026-11-26)
The product owner supplied, for two systems in two zones, the LTE modem's configuration
file and the Flexi BBU's site configuration file (SCF, RAML XML), plus the team's PCI table
(a workbook). Their decisions, the same day:
- the cells' PCIs come from the PCI table's **Compact Sector** columns (cell 1, cell 2),
  never from the supplied file;
- latitude, longitude, altitude and the cells' root sequence index stay as in the template;
- the SCF's `descriptiveName` follows the pattern `<site type>-<system>-Z<zone> …`, even
  though one supplied file has a free-text label there;
- the modem's admin password is not kept in a template; a handed-out file takes it from the
  modem's login;
- a generated SCF's name ends with the time it was made;
- B systems (two cells) only, for now.

**Rules** (`configgen/zone.py`), applied only to the roles `modem` and `bbu_scf`, beyond
D-111's five:
1. `Z`/`Zone` + the zone in 3 digits;
2. `tac` = the zone;
3. `MRBTS-<n>`, and the system letter + 3 digits, alone or after a site-type prefix, with or
   without a dash. Never inside a number or before a hex digit, so certificate and serial
   values are left alone;
4. `phyCellId` of `LNCEL-<k>` = the table's PCI for cell k;
5. the modem's `password "…"` becomes a secret slot.

The modem file's name keeps its zone tag without leading zeros (`…z<zone>.txt`), as the
team names it.

**Proof (local, not committed).** The first system's files, made into templates and
rendered for the second system and zone:
- the modem file came out byte for byte identical;
- the SCF came out identical except three lines, each from a decision above: the two
  `phyCellId` values (now from the table) and `descriptiveName` (now the pattern).

**System.** `Project.system_id` (e.g. B007), prefilled from the system name and set in
wizard step 1 with the zone (migration 96bf3e258ce6). Templates record their reference
and checked systems.

**PCI table.** Settings → For all systems → PCI table:
- imported from .xlsx (read with the standard library; no new dependency) or CSV;
- kept in `app_settings`; audited without its rows;
- PCIs must be 0–503 (3GPP TS 36.211).

**Downloads:**
- `POST /api/projects/{id}/files.zip` gives a system's files for its zone and system. The
  modem's file gets the password of the modem device's login and is left out, with the
  reason, when there is none.
- Settings downloads never include the modem's file.
- What was left out travels in `X-UNDM-Skipped`.
- Generated files stored on the modem device keep the password slot, for the console load
  still to be built.

**Import check.** A second file that differs is shown line by line. The person may keep
the template anyway: "Keep it anyway", `accept_differences`, recorded as
`counts.accepted_differences`, audited with line numbers only.


**Amendment (2026-11-26, v89): reading a team file's zone and system.** Bench: the import
dialog left the zone empty for the modem file `LTEModem…z<zone>.txt` (written without
leading zeros), and the system empty for an SCF whose name holds both `MRBTS-<n>` and the
eNodeB's `eNB1`.
- File names: the zone is `z`/`Zone` + 1 to 3 digits (`zone_from_name`). A file's text
  keeps the strict three digits (`zone_from_text`): there a short `z1` could be anything.
- System in a name: the letter + 3 digits or `MRBTS-<n>`, either case; a shorter `B7` only
  when the name has neither, and never after `eN` (eNodeB).
- The dialog reads the name first and the file's text when the name says nothing. It says
  where each value came from, keeps what the person typed, and points out a name and text
  that name different zones or systems.

**Amendment (2026-11-26, v89): a team file's own `${…}`.** The team's FortiGate base file
was refused because it contains `${hostname}`, `${vdom}` and the like: FortiOS's own report
layout variables. Only UNDM's own markers (`${zone}`, `${sys}`, `${pci_1}`, …) are refused
now. Any other `${…}` is the file's text: rendering touches only UNDM's markers, so it
reaches the device unchanged. Checked locally on the team's base file: imported, and
downloaded byte for byte.

### D-115 The systems' own logins become logins for all systems (2026-11-26)
**Request (product owner):** bring all logins of the existing systems into Settings → For
all systems, so every system can use them, under clearer names. D-105 had left existing
systems' logins where they were.

**Decision.** Settings → For all systems shows **Logins made in the systems** while any
system has logins of its own. **Bring them here…** first shows what will happen, then does it
in one step (audited, `credential_ref.share_all`):
- A login keeps its id, its password in the Credential Manager, and the devices and plans
  that use it. Only its owner (and its name) changes.
- Logins with the same user name and password are one login. The oldest is kept, or the
  login for all systems that already has them. The others' devices and plans (login after
  loading, file secrets) move to it, and they are removed with their stored password. The
  wizard's choices kept in the browser follow.
- Passwords are compared in memory only. A login without a stored password is never merged.
- Suggested names, editable before confirming:
  - the manufacturer and model of the devices that use the login (two at most, else "All
    devices"), then its user name: "Aruba 2930F – manager";
  - "(no password)" for a login without a password;
  - "tunnel key" for a FortiGate site file's pre-shared key;
  - two suggestions that would clash get the old name in brackets;
  - a login nothing uses keeps its name.
- Names are unique among the logins for all systems (case ignored).
- Refused while a plan is running, so no run loses its login in the middle.
- A system can still add a login of its own for a device that differs (D-105).
