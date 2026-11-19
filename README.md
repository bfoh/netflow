# UNDM — Universal Network Deployment Manager

Vendor-neutral network deployment platform: describe what each device should do,
generate or import vendor configurations, preview and approve changes, and deploy them with
backup, verification and recovery; design topologies; manage firmware images and upgrades.

> Status: see `docs/DEVELOPMENT_STATUS.md`. Everything works against **simulated devices**.
> Real devices can be reached through **experimental** SSH drivers (ArubaOS-Switch such as
> the 2930F, Aruba AOS-CX, FortiOS, Cisco IOS-XE) that have **not been validated on lab equipment**. Real-device configuration
> changes are off by default; real-device firmware upgrades are not implemented.

## What you can do today
- Projects and network elements (simulated, or real lab devices over SSH).
- Vendor-neutral intent (hostname, VLANs, L3 interfaces, static routes) → generated
  configuration for ArubaOS-Switch (e.g. 2930F), AOS-CX, FortiOS, IOS-XE; or
  **import a configuration file**.
- Compare versions and backups; deploy through validate → preview → approve → preflight
  (reachability + identity) → backup → deploy → verify, with rollback or manual recovery.
- **Topology designer**: devices and interface-to-interface links with validation.
- **Firmware manager**: image repository with SHA-256 checks, approval, offline
  compatibility, upgrade plans with maintenance windows (simulated devices only).
- Credentials kept in the OS credential store; full audit trail.

## Run locally

Requirements: Python 3.12+, Node.js 20.19+ (22 recommended), and PostgreSQL 14+
(recommended). Without PostgreSQL you can use a local SQLite file for development.

### 1. Database (PostgreSQL)
```bash
psql -U postgres -c "CREATE ROLE undm LOGIN PASSWORD 'undm';"
```
```bash
psql -U postgres -c "CREATE DATABASE undm OWNER undm;"
```
These are local development credentials only. To skip PostgreSQL, set
`UNDM_DATABASE_URL=sqlite:///./undm-dev.db` in `backend/.env` (development only).

### 2. Backend (terminal 1)
Linux/macOS:
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/python -m undm.seed
.venv/bin/uvicorn --factory undm.api.app:app_factory --host 127.0.0.1 --port 8000
```
Windows (PowerShell):
```powershell
cd backend
py -3 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
Copy-Item .env.example .env
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m undm.seed
.venv\Scripts\uvicorn --factory undm.api.app:app_factory --host 127.0.0.1 --port 8000
```

### 3. Frontend (terminal 2)
```bash
cd frontend
npm ci
npm run dev
```
Open http://127.0.0.1:5173. API documentation: http://127.0.0.1:5173/api/docs.

Use `npm ci` instead of `npm install` to get exactly the tested versions from
`package-lock.json`. Do **not** run `npm audit fix --force`: it downgrades Vite and
Vitest to older releases with more serious advisories. As of 2026-11-18 `npm audit`
reports one advisory (picomatch ReDoS, GHSA-fc5q-39xc-vjpf) counted once per dependent
package; no fixed picomatch release exists, and it only affects build/test tooling
matching our own file patterns — nothing shipped to the browser. See
`docs/DEVELOPMENT_STATUS.md`.

## Updating an existing installation
After extracting a new version over your folder, run once:
```powershell
cd backend
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\alembic upgrade head
cd ..\frontend
npm ci
```
Then start the backend and frontend as usual. `alembic upgrade head` keeps your data and does
nothing when the database is already current; if the app shows **Database upgrade needed**,
this is the step that was missed.

## Using real lab devices (experimental)
Use **isolated lab equipment only**. Read `docs/SECURITY_BOUNDARIES.md` first.
For the Aruba 2930F follow `docs/vendor-support/aruba-2930f-acceptance.md`.
1. Project → **Credentials** → *Add credential*: enter the device username and password.
   They are stored in Windows Credential Manager (macOS Keychain / Linux Secret Service),
   not in the UNDM database.
2. Project → **Add device** → choose the model → **Real lab device (SSH)**, enter the
   management address and pick the credential. The device is created in the `lab` environment.
3. On the device page: **Test connection**, **Retrieve information**, **Back up**. These only read.
   **Sanitized diagnostics** produces a shareable report with identifying details masked.
   (FortiGate note: if console paging is on, the SSH library temporarily sets
   `config system console / set output standard` for the session and restores it afterwards.)
4. Deployment **dry runs** are allowed. To let approved deployments change lab devices, add
   `UNDM_ENABLE_REAL_DEVICE_WRITES=true` to `backend\.env` and restart the backend.
   The header then shows **Real-device changes ON**.
5. Production devices are blocked entirely unless `UNDM_ALLOW_PRODUCTION_READ_ONLY` /
   `UNDM_ALLOW_PRODUCTION_DEPLOYMENTS` are set — do not do this during testing.

What the SSH drivers do not do yet: automatic rollback (failures end in "manual recovery
required" with the stored backup), and firmware or full-file restore on anything except the
Aruba 2930F and the FortiGate (below; both experimental).

## Firmware on a real Aruba 2930F (experimental)
The switch pulls the image from this PC over TFTP, UNDM checks `show flash`, restarts the
switch into the new image and verifies the running version. Not yet run on hardware: do the
first run on a spare switch with `docs/vendor-support/aruba-2930f-firmware.md`.
Add to `backend\.env` and restart the backend:
```
UNDM_ENABLE_REAL_DEVICE_WRITES=true
UNDM_ENABLE_REAL_DEVICE_FIRMWARE=true
# only if one person stages alone on an isolated bench:
UNDM_FIRMWARE_REQUIRE_SEPARATE_APPROVER=false
```
Windows must allow inbound UDP 69 (TFTP) to Python on the bench network, and no other
TFTP program may be running. The TFTP server only runs during a job that needs it.

## FortiGate 101F staging (experimental)
Your team's order, each step an approved job: firmware 7.2.7 → 7.6.5 (Firmware page), then
the **base** file (restored by TFTP; the unit restarts), then the **site** file (sent
statement by statement), with a revision named after each file. Import both files on the
device (Configurations → Import configuration file); UNDM tells you what each is. In a new
deployment plan, choosing the base file switches to Replace and the site file to Merge; for
the site file choose the credential that holds the approved tunnel key under **Value for
psksecret**. The first login (forced password change) is still done in the browser. Not yet
run on a FortiGate: do the first run on a spare unit with
`docs/vendor-support/fortigate-101f-bench.md`.

## Aruba 2930F complete configuration files (experimental)
Import the team's file on the switch (Configurations tab): UNDM shows the address it will
have after loading, who may manage it, and points to check. A plan with that file runs in
Replace mode: the switch fetches the file by TFTP into its startup configuration and
restarts; UNDM follows an address change, checks the serial number and the hostname. The
team's files set the approved password: choose it under **Login after loading** in the plan
(a credential with user `manager` and the approved password). Do the
firmware upgrade first (the file switches the switch's TFTP client off). First run on a spare
switch: `docs/vendor-support/aruba-2930f-staging.md`.

## Black Box configuration files
Add the switch with model **LIG1014A** or **LE2700A** (simulated for now) and import the
team's file (CLI text for the LIG1014A, XML for the LE2700A) on its Configurations tab: UNDM shows where the switch answers after loading, its access rules,
and a warning about the base64 password. Loading it onto a real switch is not built yet —
see `docs/vendor-support/blackbox-staging.md`.

## Console bootstrap (Aruba 2930F and other ArubaOS-Switch models)
New units ask to set the manager credentials on first login: attach the approved login to the
device first and the bootstrap sets it. For a factory-default switch with no management address: **Provisioning** → choose the
switch → enter the management VLAN, port and address → **Preview commands** → choose the
console cable's COM port → **Run console bootstrap**. Simulated devices use the
`SIMULATED` console port, so you can try the workflow without hardware. Real switches
need `UNDM_ENABLE_REAL_DEVICE_WRITES=true`; PuTTY must be closed while UNDM uses the COM
port. First real run: follow `docs/vendor-support/aruba-2930f-console-bootstrap.md`
on a spare switch.

## Tests
```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check src tests && .venv/bin/mypy src
```
```bash
cd frontend && npm test && npm run typecheck && npm run lint
```
End-to-end (with both servers running; first time run `npx playwright install chromium`):
```bash
cd frontend && npm run test:e2e
```

## Documentation
| Document | Purpose |
|---|---|
| `CLAUDE.md` | Rules and conventions for development sessions |
| `docs/PROJECT_MASTER_PLAN.md` | Phases, milestones, exit criteria |
| `docs/REQUIREMENTS.md` | Functional requirements, acceptance criteria, status |
| `docs/ARCHITECTURE.md` | Subsystems, data flow, data model |
| `docs/DEVICE_DRIVER_SPEC.md` | Driver contract and capability model |
| `docs/DEVELOPMENT_STATUS.md` | What works, what is mocked, what is missing |
| `docs/DECISIONS.md` | Architectural decisions and reasoning |
| `docs/SECURITY_BOUNDARIES.md` | Device access, data handling, secrets |
| `docs/REFERENCE_ANALYSIS.md` | Reference material index, REA record, open questions |
| `docs/reference-analysis/tndm-screenshot-catalog.md` | TNDM screenshot analysis |
| `docs/vendor-support/support-matrix.md` | What each vendor family supports today |
| `docs/testing/test-strategy.md` | Test layers and how to run them |
