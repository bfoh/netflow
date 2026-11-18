# Device Driver Specification

Source of truth: `backend/src/undm/drivers/base.py`. Contract tests:
`backend/tests/test_driver_contract.py` (every registered driver must pass).

## Principles
- One driver per **platform family + transport**, developed and validated one model and
  firmware family at a time. No assumption that a vendor's products share commands.
- Drivers **declare capabilities**. Core code checks capabilities; it never branches on
  vendor names.
- Operations a driver does not implement return
  `OperationResult(status=UNSUPPORTED)`; they must not raise.
- Drivers never log or return credentials. Credentials arrive as `Credentials`
  (resolved from a `CredentialRef` at use time) and are not stored on the instance's repr.
- A driver must not report success for an operation it cannot confirm. Where a device
  gives no confirmation, return `FAILED` with diagnostics, and let verification decide.

## Types

| Type | Meaning |
|---|---|
| `DriverInfo` | `driver_id`, `vendor`, `platform` (template key), `os_family`, `description`, `simulated`, `capabilities`, `maturity` (simulation / experimental / lab_validated), `transport`, `notes` |
| `FirmwareImageRef` | `version`, `filename`, `sha256`, `size_bytes`, `local_path` of an approved repository image |
| `DeviceTarget` | `device_id`, `management_address`, `port` |
| `OperationResult` | `operation`, `status` (`success`/`unsupported`/`failed`), `message`, `data`, `diagnostics` |
| `DeviceFacts` | `hostname`, `vendor`, `model`, `os_version`, `serial_number`, `extra` |
| `ConfigurationBackup` | `device_id`, `text`, `reference` (driver handle usable for rollback) |
| `ApplyMode` | `merge` (add/modify) or `replace` (running = supplied text) |

## Operations

| Directive name | Driver method | Impact | Required capability | Status |
|---|---|---|---|---|
| connect / disconnect | `connect()`, `disconnect()` | read-only | — | Implemented |
| get_device_facts | `get_device_facts()` | read-only | — | Implemented |
| get_supported_capabilities | `capabilities()` (class) | — | — | Implemented |
| get_running_configuration | `get_running_configuration()` | read-only | — | Implemented |
| get_startup_configuration | — | read-only | — | Planned |
| backup_configuration | `backup_configuration()` | read-only* | `supports_configuration_backup` | Implemented |
| validate_candidate_configuration | — | read-only | `supports_candidate_configuration` | Planned |
| generate_configuration | `undm.configgen.engine.generate` (not a driver method) | — | — | Implemented (core) |
| calculate_configuration_diff | `undm.configgen.diff` (core) | — | — | Implemented (core, textual) |
| apply_configuration | `apply_configuration(config, mode)` | impacting | `supports_configuration_apply` (+ `_replace` for replace mode) | Implemented |
| save_configuration | `save_configuration()` | impacting | — | Implemented |
| verify_configuration | orchestrator reads back running config | read-only | — | Implemented (core) |
| rollback_configuration | `rollback_configuration(backup)` | impacting | `supports_configuration_rollback` | Implemented |
| reboot_device | `reboot()` | impacting | `supports_reboot` | Implemented (mock) |
| get_firmware_information | `get_firmware_information()` | read-only | — | Implemented (mock) |
| validate_firmware_image | — | read-only | — | Planned (Phase 7) |
| stage_firmware / install_firmware | `stage_firmware(image: FirmwareImageRef)`, `install_firmware()` | impacting | `supports_firmware_upgrade` | Mock only |
| verify_firmware | — | read-only | — | Planned (Phase 7) |
| rollback_firmware | `rollback_firmware()` | impacting | `supports_firmware_rollback` | Mock only |
| provision_factory_default_device | `provision_factory_default_device(bootstrap)` | impacting | `supports_zero_touch_provisioning` | Mock only |
| discover_device | — | read-only | — | Planned (Phase 5) |

\* A backup may write a checkpoint on the device (e.g. a stored checkpoint). Dry runs
therefore skip the backup stage.

Impact classes come from `undm.domain.operations.IMPACT`; the API refuses impacting
operations outside a deployment.

## Capabilities
`supports_ssh`, `supports_rest_api`, `supports_netconf`, `supports_gnmi`,
`supports_serial_console`, `supports_configuration_backup`, `supports_configuration_apply`,
`supports_configuration_replace`, `supports_candidate_configuration`,
`supports_configuration_rollback`, `supports_zero_touch_provisioning`,
`supports_firmware_upgrade`, `supports_firmware_rollback`, `supports_reboot`.

## Verification hooks
`expected_lines(config)` and `present_lines(running)` define how the orchestrator decides
"already applied" and "verified". Defaults compare lines exactly (minus trailing spaces).
The SSH drivers compare stripped lines and ignore lines a platform does not display
(`no shutdown`, `set status up`, `end`, `next`, `exit`, `!`), and drop file headers and
comments before sending.

## Real-device drivers (experimental)
`drivers/ssh/`: one Netmiko-based `SshCliDriver` plus `ArubaAOSCXSsh`, `FortiOSSsh`,
`CiscoIOSXESsh`. See `docs/vendor-support/support-matrix.md` for commands and caveats.
They require a credential, map authentication/timeout errors to clear messages, treat
device error output (`% Invalid input`, `Command fail`, ...) as failure ("may be partially
applied"), and redact device output before it is logged. Tests use fake connections
(`tests/fake_netmiko.py`) with synthetic output.

## Simulated drivers (current)

| Driver | Platform | Capability profile (simulation only) |
|---|---|---|
| `mock.aruba.aoscx` | `aoscx` | ssh, rest_api, backup, apply, replace, rollback, firmware upgrade + rollback, ztp, reboot |
| `mock.fortinet.fortios` | `fortios` | ssh, rest_api, backup, apply, firmware upgrade, ztp, reboot — **no rollback**, to exercise manual-recovery paths |
| `mock.cisco.iosxe` | `iosxe` | ssh, netconf, serial, backup, apply, replace, rollback, firmware upgrade, reboot |

These profiles are chosen to exercise orchestration paths. They are **not** statements
about the real products.

The simulated lab (`drivers/mock/lab.py`) supports failure injection per device:
`reachable=False`, `fail_on={operation,...}`, and `ignored_lines` (lines silently not
applied, to exercise verification failure).

## Adding a real driver (acceptance checklist)
1. Name the exact models and firmware versions it targets; record sources in
   `docs/vendor-support/support-matrix.md` (DOCUMENTED evidence only).
2. Declare only capabilities verified against vendor documentation **and** lab tests.
3. Implement read-only operations first (Phase 5); impacting ones only after the
   read-only acceptance tests pass on an approved lab device.
4. Pass `test_driver_contract.py` using recorded/mock transports (no live devices in CI).
5. Add transport-level tests for timeouts, auth failure, unexpected prompts, partial output.
6. Document non-reversible operations and recovery procedures.
7. Mark the device model's `SupportLevel` accordingly (`lab_read_only`, `lab_validated`).
