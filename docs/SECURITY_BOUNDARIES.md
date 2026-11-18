# Security Boundaries

## Device and network access

Two different actors must be distinguished:
- **The development assistant (Claude)** never connects to real devices or networks. Its
  container cannot reach the product owner's network; real-device code is tested with fake
  connections only.
- **The operator running UNDM on their own machine** decides which devices UNDM reaches.
  On 2026-11-18 the product owner requested real-device capability for testing on a real
  system. UNDM enforces these switches (all off by default, set in `backend/.env`):

| Environment | Read-only (connect, facts, backup, dry runs) | Configuration changes | Firmware |
|---|---|---|---|
| Simulated | always | always (through approved deployments) | simulated upgrades |
| Lab (real) | allowed | only with `UNDM_ENABLE_REAL_DEVICE_WRITES=true`, through approved deployments | **not implemented** (drivers declare no firmware capability) |
| Production (real) | only with `UNDM_ALLOW_PRODUCTION_READ_ONLY=true` | only with writes enabled **and** `UNDM_ALLOW_PRODUCTION_DEPLOYMENTS=true` | not implemented |

Rules are re-checked when a deployment executes, not only when it is planned. A device's
environment cannot be `simulated` with a real driver or vice versa.

Strong recommendation for the current phase: real devices only on an **isolated lab network**,
never operational systems (including equipment managed by other vendor tools), until each
driver has passed acceptance tests for the exact model and firmware.

- No scanning, discovery broadcasts, DHCP/TFTP/ZTP services or provisioning traffic on
  any network other than an isolated lab, and only after approval.
- Firmware is never downloaded from unverified sources and never installed on real
  equipment during development.
- Telnet is not offered (plaintext). Interactive terminal access is not planned until
  a security review.

### Approved lab devices
| Date | Device | Firmware | Status | Allowed operations |
|---|---|---|---|---|
| 2026-11-19 | Aruba 2930F (ArubaOS-Switch), named by the product owner | to be confirmed | lab/spare status to be confirmed by the product owner | Phase A read-only (`docs/vendor-support/aruba-2930f-acceptance.md`); writes only in phase B after phase A is accepted |

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
