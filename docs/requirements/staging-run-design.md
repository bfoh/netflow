# Staging run — design

Goal: take the four factory-default devices of one system to the right firmware and
configuration from one laptop in one sitting. See `staging-use-case.md` for the problem.

## Bench setup (proposed)
```
                 ┌──────────── unmanaged bench switch ────────────┐
 laptop ─────────┤                                                 │
 (192.168.1.50/24│  FortiGate mgmt port        192.168.1.99        │
  + 192.0.2.50/24│  Black Box                  192.0.2.1           │
  on one adapter)│  Aruba A, OOBM port (2)     192.168.1.1         │
                 │  Aruba B, OOBM port (3)     192.168.1.2 (temp.) │
                 └─────────────────────────────────────────────────┘
 laptop USB ──── console cable(s) ──── Aruba A / Aruba B console port
```
- The bench switch must be isolated: no connection to any other network.
- The laptop's wired adapter carries two addresses (one per default subnet). UNDM does
  not change the PC's network settings; it reports when a device is unreachable.
- Aruba B uses a temporary address so both switches can be on the bench together. Its
  final configuration (or a last staging step) returns it to its normal address.

## Sequence
| Step | Aruba ×2 | FortiGate | Black Box |
|---|---|---|---|
| 1 Reach | **Console bootstrap** (built; simulated-tested) → SSH | default address; first-login password change by hand in the browser (Q-24) | default address (to build; manual needed) |
| 2 Identify | read model, serial, firmware (built, accepted on a 2930F) | to validate on a spare | to build |
| 3 Firmware | **built (experimental)**: switch pulls the image by TFTP, restarts, version verified; bench run pending | **built (experimental)**: 7.2.7 → 7.6.5 directly by TFTP; bench run pending | to build; v00.01.00 → v00.01.01 |
| 4 Configuration | full file push (to build); today only "add lines" exists | **built (experimental)**: base restored by TFTP after the firmware, then the site script statement by statement with the tunnel key from the credential store, a revision after each | complete file, loaded as a whole: recognised at import, simulated; real procedure after Q-26…Q-28 (`vendor-support/blackbox-staging.md`) |
| 5 Verify + report | read back, compare with the file, one report per system | same | same |

Firmware normally precedes configuration: configuration files are tied to a firmware
release. FortiGate is the exception to check: its base file was written on 7.2.7 and its
site script for 7.6.5, so the likely order is base → firmware → site script (Q-19;
`vendor-support/fortigate-101f-staging.md`). After the final configuration loads, addresses and passwords change, so the
last verification uses the console or the final management address.

## What exists today
Console bootstrap for ArubaOS-Switch with per-device settings, preview, factory-default
check, read-back verification and transcript; SSH read access for the 2930F (accepted on
real hardware); configuration file import and versioning; firmware repository and
upgrade orchestration (simulated only); credentials in the OS store; audit.

## Build order
1. Bench-validate the console bootstrap on a spare 2930F
   (`docs/vendor-support/aruba-2930f-console-bootstrap.md`).
2. 2930F: firmware install over TFTP — **built, bench run pending**
   (`docs/vendor-support/aruba-2930f-firmware.md`); then full-configuration push the same way.
3. FortiGate 101F: firmware, base restore, site script, key, revisions — **built, bench run
   pending** (`docs/vendor-support/fortigate-101f-bench.md`); first login by hand (Q-24).
4. Black Box LIG1014A: file recognised (built); load procedure after Q-26…Q-28; then LE2700A.
5. The staging run itself: one screen, four devices, one report.

## Transfer method
Vendor documentation found so far (see `vendor-support/staging-procedures-research.md`)
gives TFTP for firmware and configuration on the 2930F, the FortiGate and the LIG1014A.
Built: a TFTP server inside UNDM, serving only the files of the active job, each only to
its device, read-only, stopped when the job ends (D-029). Needs inbound UDP 69 on the
laptop (Q-18). If the bench test fails, another method is chosen.

## Open points
- Sample configuration files for each device (first lines are enough) to decide how
  they must be loaded and how to verify them.
- Aruba firmware target is WC.16.10.0025; the arrival version is read from each switch.
- Black Box: exact LE2700-series model and its real defaults (its quick-start guide says
  192.168.10.1, admin/admin — different from the LIG1014A).
- FortiGate: Fortinet publishes upgrade paths between releases. The team upgrades
  7.2.7 → 7.6.5 in one step today; UNDM will follow that practice and will not add
  intermediate versions on its own. Worth confirming once against Fortinet's upgrade
  path tool, since an unsupported jump can alter configuration during the upgrade.
- Whether a factory-default 2930F accepts SSH with the empty default password (decides
  how UNDM logs in after the console bootstrap).
