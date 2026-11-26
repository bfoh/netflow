# Security Boundaries

## Device and network access

Two different actors must be distinguished:
- **The development assistant (Claude)** never connects to real devices or networks. Its
  container cannot reach the product owner's network; real-device code is tested with fake
  connections only.
- **The operator running UNDM on their own machine** decides which devices UNDM reaches.
  On 2026-11-18 the product owner requested real-device capability for testing on a real
  system. UNDM enforces these switches (all off by default). Since D-082 (2026-11-24) the
  three bench switches — real-device changes, firmware changes, second approver for firmware —
  can also be changed in **Settings → Safety**: turning one to its less safe position needs a
  confirmation, every change is audited (`policy.change`, who, before, after), and the values
  are kept in `settings.json` in this copy's data folder. A switch set in `backend/.env` or the
  environment wins and is shown as fixed. The production switches are start-up settings only.
  A damaged `settings.json` counts as empty, i.e. everything off.

| Environment | Read-only (connect, facts, backup, dry runs) | Configuration changes | Firmware |
|---|---|---|---|
| Simulated | always | always (through approved deployments) | simulated upgrades |
| Lab (real) | allowed | only with Real-device changes on (`UNDM_ENABLE_REAL_DEVICE_WRITES` or Settings → Safety), through approved plans | only with the write switch **and** Firmware changes on (`UNDM_ENABLE_REAL_DEVICE_FIRMWARE` or Settings → Safety), approved plan, maintenance window; procedures exist for Aruba 2930F, FortiGate 101F and Black Box LIG1014A (experimental, each run on bench units) |
| Production (real) | only with `UNDM_ALLOW_PRODUCTION_READ_ONLY=true` | only with writes enabled **and** `UNDM_ALLOW_PRODUCTION_DEPLOYMENTS=true` | not implemented |

Console bootstrap (Console setup page) writes to a device over a serial cable. For real
devices it needs Real-device changes on, a typed confirmation of the device
name, and a switch that looks factory default (no password prompt, no site configuration)
unless the operator explicitly overrides that check. It is meant for spare or new units on
an isolated bench. A **preconfigured** switch (e.g. BH-DMZ units delivered with another
manager password) can be erased first, only on explicit request (D-057): UNDM logs in with
the saved "current login", refuses unless the hostname typed by the technician equals the
switch's console prompt, keeps the configuration read before the erase in the transcript,
runs `erase startup-config` answering only a continue/proceed y/n question ("n" to a save
question), and audits the erase with the hostname and the name of the login used.

File transfer: while a real-device job needs it (firmware; FortiGate full-backup restore), UNDM listens on UDP 69 (TFTP). TFTP
has no authentication or encryption, so the server is deliberately narrow: read-only, only
files published for that job, each only to the address of the device it is for, and it is
stopped when the job ends. Use it on the isolated bench network only. Settings:
`UNDM_TFTP_HOST` (default all adapters; set the bench adapter's address to restrict it) and
`UNDM_TFTP_PORT`.

A FortiGate full backup or a complete 2930F file is written to a private temporary file only
for the moment of the transfer, under a neutral name, and deleted straight after.

When a loaded file moves a device to another address, UNDM follows it only after the serial
number matches the one read before the change, and records the address change in the audit.

Secret values for supplied files (e.g. a tunnel pre-shared key) are kept only in the
credential store. A plan stores the credential reference; the value is read at execution,
inserted into the copy sent to the device, and masked in every message (D-036).

Supplied configuration files (for example FortiGate backups and site scripts) contain
passwords, keys and addressing. In the Black Box sample the admin password marked
"encrypted" is only base64-encoded, i.e. readable by anyone with the file: handle such files
as containing the password in clear text. They are stored in UNDM's database on the PC running UNDM;
protect that PC and the database file accordingly. File reports and audit entries never
contain secret values.

Rules are re-checked when a deployment executes, not only when it is planned. A device's
environment cannot be `simulated` with a real driver or vice versa.

Strong recommendation for the current phase: real devices only on an **isolated lab network**,
never operational systems (including equipment managed by other vendor tools), until each
driver has passed acceptance tests for the exact model and firmware.

- No scanning, discovery broadcasts, DHCP/TFTP/ZTP services or provisioning traffic on
  any network other than an isolated lab, and only after approval.
- Firmware is never downloaded from unverified sources and never installed on real
  equipment during development.
- UNDM sets a device password only in four cases: the console bootstrap of a
  factory-default unit (D-043); when a device demands a new password at login after a
  planned load (D-066); the approved first-login plan of a new unit (D-073); and the first
  access of a factory Nokia 7705 SAR-Hmc over its console (D-112), where the password is
  typed on a command line and masked wherever the console is recorded. It always
  sets the device's own stored (approved) login, and only answers questions recorded from
  the bench. Audited as `device.password_set`; values never logged or shown.
- Older SSH methods (SHA-1 key exchanges, `ssh-rsa`/`ssh-dss` host keys) are switched off
  for every device except the Black Box LIG1014A, whose SSH server needs them, and are used
  there only if it offers nothing newer (D-075).
- UNDM approves a firmware image only when its checksum matches the vendor's published
  SHA-256 or SHA-512, or when the approver writes a reason for approving it without one
  (D-062). Such an image stays marked "not verified" in the repository, the planner and
  every firmware plan, and the reason is audited.
- Telnet is not offered (plaintext). Interactive terminal access is not planned until
  a security review.

### Approved lab devices
| Date | Device | Firmware | Status | Allowed operations |
|---|---|---|---|---|
| 2026-11-19 | Aruba 2930F-48G-4SFP (ArubaOS-Switch), named by the product owner | WC.16.10.0025 | lab/spare status to be confirmed by the product owner | Phase A read-only (`docs/vendor-support/aruba-2930f-acceptance.md`); writes only in phase B after phase A is accepted |
| 2026-11-19 | Aruba JL260A 2930F-48G-4SFP, spare **new** unit on an isolated bench (product owner) | WC.16.11.0001 as shipped | spare, factory default, not part of any running system | Console bootstrap; firmware to the approved WC.16.10.0025 (approved downgrade); complete-file load. Serial number not recorded here |

No Nokia device is listed yet: the 7705 SAR-Hmc first access (D-112) has run only on the
simulated console. Record the bench unit here before its first run (model, software release;
no serial number).

Real-device output shared with the developer must go through **Sanitized diagnostics**
(or equivalent manual masking) and be reviewed by the product owner first.

## Credentials and secrets
- No real credentials in source code, fixtures, commits, screenshots, logs or test data.
  Development uses synthetic values only. The local PostgreSQL role `undm`/`undm` in the
  README is a development-only credential for a database on localhost.
- Inventory stores `CredentialRef` (provider + locator) only. Providers:
  `keyring` (default) — the OS credential store (Windows Credential Manager, macOS Keychain,
  Linux Secret Service); secrets are written through `PUT /api/credential-refs/{id}/secret`
  and can never be read back through the API. `env` — read-only, from
  `UNDM_CRED_<LOCATOR>_USERNAME/PASSWORD`. A vault provider is planned (Phase 8).
- Passwords mentioned in conversations with the developer are never written to the
  repository. Factory-default (empty) passwords can be stored for devices that have none.
- SSH error messages and device output are redacted before they reach logs or the audit trail.
- Logs are JSON and pass through redaction (`undm.security.redaction`): keys such as
  password/secret/token/key/community/psk are masked, and CLI fragments such as
  `password 0 …`, `secret 5 …`, `set password ENC …`, `snmp-server community …` are
  masked in free text. Audit details are redacted before storage.
- Configuration texts (generated and backups) are stored in the database because they
  are needed for diff and rollback. They may contain secrets once intent supports AAA;
  before that happens, secret fields will be stored as references and rendered only at
  deployment time (FR-CFG-05).

## Application access
- **Authentication and RBAC are not implemented yet.** The API attributes actions via
  the `X-UNDM-Actor` header, which anyone can set. Run the backend bound to
  `127.0.0.1` only; do not expose it on a network. Milestone M1 adds authentication.
- CORS allows only the local dev origins.
- Input validation: Pydantic models with `extra=forbid` for intent; enums for categories,
  protocols, environments; hostnames, VLAN IDs, addresses and prefixes typed.
- Templates are package code rendered with `StrictUndefined`; users cannot submit
  templates yet. When user templates arrive they must run in a sandboxed Jinja2
  environment with no access to Python objects beyond the intent data.

## Reference materials and REA
- TNDM screenshots and other reference material are not committed (`.gitignore` blocks
  `reference-material/` and `*.tndbz`). Analysis records use placeholders for system
  names, hostnames, numbers and user names.
- REA (Reverse Engineer Anything) must not be used on TNDM binaries, databases, process
  memory or traffic unless the six authorization conditions of directive section 6 are
  documented in `docs/REFERENCE_ANALYSIS.md`. Current status: **not authorized**.
- Reference material is not sent to services other than this development assistant.

## System packages (`.undm`, D-087)
A package never contains a password, user name or key: logins travel by name only and arrive
empty. It does contain the system's configuration files as written, which can hold passwords
or keys (e.g. base64 "encrypted" passwords in Black Box files, FortiGate files with secrets):
treat a package as confidential, like those files; never commit one or attach it to a ticket.
Import checks every file against the manifest's SHA-256 and refuses unsafe names before
anything is created; firmware arrives unapproved.

