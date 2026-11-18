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
| 1 Reach | **Console bootstrap** (built; simulated-tested) → SSH | default address, first-login password change (to build) | default address (to build; manual needed) |
| 2 Identify | read model, serial, firmware (built, accepted on a 2930F) | to validate on a spare | to build |
| 3 Firmware | to build (vendor procedure, per model) | to build; 7.2.7 → 7.6.5 directly as practised | to build; v00.01.00 → v00.01.01 |
| 4 Configuration | full file push (to build); today only "add lines" exists | restore from file (to build) | to build |
| 5 Verify + report | read back, compare with the file, one report per system | same | same |

Firmware always precedes configuration: configuration files are tied to a firmware
release. After the final configuration loads, addresses and passwords change, so the
last verification uses the console or the final management address.

## What exists today
Console bootstrap for ArubaOS-Switch with per-device settings, preview, factory-default
check, read-back verification and transcript; SSH read access for the 2930F (accepted on
real hardware); configuration file import and versioning; firmware repository and
upgrade orchestration (simulated only); credentials in the OS store; audit.

## Build order
1. Bench-validate the console bootstrap on a spare 2930F
   (`docs/vendor-support/aruba-2930f-console-bootstrap.md`).
2. 2930F: full-configuration push and firmware install, using the vendor-documented
   file transfer for WC.16.x, validated on the spare.
3. FortiGate 101F: first-login handling, firmware, configuration restore.
4. Black Box (LIG1014A, LE2700 series): after the manuals are available.
5. The staging run itself: one screen, four devices, one report.

## Transfer method
Vendor documentation found so far (see `vendor-support/staging-procedures-research.md`)
gives TFTP for firmware and configuration on the 2930F, the FortiGate and the LIG1014A.
Plan: a TFTP server inside UNDM, bound to the bench adapter, serving only the files of the
active run, read-only, stopped when the run ends. Depends on Q-18 (laptop firewall).

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
