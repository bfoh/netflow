# Security Boundaries

## Device and network access
| Environment | Allowed now | Conditions |
|---|---|---|
| Simulated | Everything | In-memory simulated lab only |
| Lab | **Nothing yet** | Phase 5 begins with read-only access to specific lab devices named and approved in writing by the product owner, on an isolated lab network. Each approval is recorded here (device, model, firmware, address range, allowed operations, date). |
| Production | **Nothing** | Out of scope for all current phases. Enforced in code: deployments to `production` devices are refused (`UNDM_ALLOW_PRODUCTION_DEPLOYMENTS=false`). |

- No scanning, discovery broadcasts, DHCP/TFTP/ZTP services or provisioning traffic on
  any network other than an isolated lab, and only after approval.
- Firmware is never downloaded from unverified sources and never installed on real
  equipment during development.
- Telnet is not offered (plaintext). Interactive terminal access is not planned until
  a security review.

### Approved lab devices
None.

## Credentials and secrets
- No real credentials in source code, fixtures, commits, screenshots, logs or test data.
  Development uses synthetic values only. The local PostgreSQL role `undm`/`undm` in the
  README is a development-only credential for a database on localhost.
- Inventory stores `CredentialRef` (provider + locator) only. The current provider reads
  `UNDM_CRED_<LOCATOR>_USERNAME/PASSWORD` from the backend's environment at use time.
  A keyring/vault provider is planned (Phase 8).
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
