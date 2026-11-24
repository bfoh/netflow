# Vendor Support Matrix

No driver has been validated on lab equipment yet. "Experimental" means: written from
public documentation and Netmiko's source, tested only against fake connections.

## Drivers
| Family | Driver | Maturity | Read-only (connect, facts, backup) | Config apply | Replace | Rollback | Firmware |
|---|---|---|---|---|---|---|---|
| Aruba AOS-CX | `mock.aruba.aoscx` | simulation | ✔ | ✔ merge | ✔ | ✔ | ✔ (simulated, with rollback) |
| Aruba AOS-CX | `ssh.aruba.aoscx` | **experimental** | ✔ (`show version`, `show system`, `show running-config`) | ✔ merge, save `copy running-config startup-config` | ✘ | ✘ manual | ✘ |
| ArubaOS-Switch (2930F) | `mock.aruba.aos_switch` | simulation | ✔ | ✔ merge | ✘ | ✘ | ✔ (simulated dual image banks, with rollback) |
| ArubaOS-Switch (2930F) | `ssh.aruba.aos_switch` | **experimental**; read-only operations **lab-accepted** on 2930F-48G-4SFP (JL260A) WC.16.10.0025 | ✔ (`show system`, `show modules`, `show running-config`) ⁵ | ✔ merge, save `write memory` | **experimental**: HTTPS certificate created first (team commands); complete file by TFTP into the startup configuration, restart, address followed, serial and hostname checked (`aruba-2930f-staging.md`) | ✘ manual | **experimental, not run on hardware**: TFTP pull into primary flash, restart, verify (`aruba-2930f-firmware.md`); no automatic rollback |
| Fortinet FortiOS | `mock.fortinet.fortios` | simulation | ✔ | ✔ merge | ✘ | ✘ | ✔ (simulated, no rollback) |
| Fortinet FortiOS | `ssh.fortinet.fortios` | **experimental**, not run on hardware | ✔ (`get system status`, `show`) ¹ | ✔ merge: script statement by statement (multi-VDOM, hostname change, secret slots) ² | ✔ full backup restored by TFTP (`execute restore config tftp`), checked by facts | ✘ manual | **experimental**: TFTP (`execute restore image tftp`), unit restarts itself, version verified; revisions after file deployments (`execute backup config flash`, unverified) |
| Cisco IOS-XE | `mock.cisco.iosxe` | simulation | ✔ | ✔ merge | ✔ | ✔ | ✔ (simulated, no rollback) |
| Cisco IOS-XE | `ssh.cisco.iosxe` | **experimental** | ✔ (`show version`, `show running-config`) ³ | ✔ merge, save `write mem` | ✘ | ✘ manual | ✘ |

¹ If console paging (`set output more`) is enabled, Netmiko temporarily sets
`config system console / set output standard` and restores it on disconnect.
Multi-VDOM units: `execute` commands are issued inside `config global` (community guidance).
² Checks `cfg-save` on the device after each load (D-069); manual or revert mode is reported, not saved by UNDM.
³ Requires a privilege-15 login; enable-password prompts are not handled.
⁵ Netmiko `aruba_osswitch`: passes the "Press any key" banner, runs `enable` (the login
password is sent if an enable password is requested), then `terminal width 511` and
`no page` for the session; answers "no" to the save prompt on logout. Needs a manager login.
Checklist: `aruba-2930f-acceptance.md`.

## Console bootstrap (factory-default devices)
| Family | Procedure | Status |
|---|---|---|
| ArubaOS-Switch (2930F) | Serial console: out-of-band management VLAN, one untagged port, address, `write memory` | Simulated-tested; **hardware validation pending** (`aruba-2930f-console-bootstrap.md`) |
| FortiOS (FortiGate 101F) | Forced first-login password change | By hand in the browser (Q-24). Firmware, base restore, site script and revisions: built, experimental (`fortigate-101f-bench.md`) |
| Black Box LIG1014A / LE2700A | Default address | No bootstrap needed for the LIG1014A: its factory address is the one the team's file keeps, and SSH works with the factory login. LIG1014A SSH driver (experimental): connection, facts and backup checked on hardware (D-074 to D-076); loading the team's file by TFTP into the startup configuration + `reload cold` **passed once on hardware** (D-077 to D-079); SSH works after loading. LE2700A: file recognition and a simulated driver only |

## Templates (generation)
| Template | Intent features rendered | Verification |
|---|---|---|
| `aoscx.j2` v0.1.0 | hostname, VLANs, VLAN-interface addresses + description, static routes | docs-reviewed, not lab-verified |
| `fortios.j2` v0.1.0 | hostname, physical interface addresses, static routes (egress interface required) ⁴ | docs-reviewed, not lab-verified |
| `aos_switch.j2` v0.1.0 | hostname, VLANs (name), VLAN addresses (per-VLAN context, `exit`), static routes ⁶ | docs-reviewed, not lab-verified |
| `iosxe.j2` v0.1.0 | hostname, VLANs, interface (physical + SVI) addresses + description, static routes | docs-reviewed, not lab-verified |

⁴ Static routes are written as entries `1..n`; on a real device this overwrites existing
routes with the same IDs. Generation shows a warning.

⁶ `ip route` entries only take effect with IP routing enabled (warning shown).

Not rendered (generation reports an error): ArubaOS-Switch routed ports and VLAN interface descriptions; AOS-CX routed physical ports; FortiOS VLANs
(needs a parent-interface concept) and interface descriptions.

## Device model registry
`aruba-2930f` is `lab_read_only` (connect, facts, backup accepted on 2930F-48G-4SFP,
WC.16.10.0025, 2026-11-19). All other entries are `simulated_only`. The level rises to
`lab_validated` only after configuration changes pass acceptance too.

## What must be validated per model before a driver leaves "experimental"
Facts parsing against real output; behaviour of each rendered configuration line; how
the device displays applied configuration (for verification); error strings for rejected
lines; save behaviour; session limits and timeouts; and, before any firmware work, the
vendor's documented image transfer, boot-bank, reboot and rollback procedure.
