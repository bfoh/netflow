# Vendor Support Matrix

No driver has been validated on lab equipment yet. "Experimental" means: written from
public documentation and Netmiko's source, tested only against fake connections.

## Drivers
| Family | Driver | Maturity | Read-only (connect, facts, backup) | Config apply | Replace | Rollback | Firmware |
|---|---|---|---|---|---|---|---|
| Aruba AOS-CX | `mock.aruba.aoscx` | simulation | ✔ | ✔ merge | ✔ | ✔ | ✔ (simulated, with rollback) |
| Aruba AOS-CX | `ssh.aruba.aoscx` | **experimental** | ✔ (`show version`, `show system`, `show running-config`) | ✔ merge, save `copy running-config startup-config` | ✘ | ✘ manual | ✘ |
| ArubaOS-Switch (2930F) | `mock.aruba.aos_switch` | simulation | ✔ | ✔ merge | ✘ | ✘ | ✔ (simulated dual image banks, with rollback) |
| ArubaOS-Switch (2930F) | `ssh.aruba.aos_switch` | **experimental** — lab acceptance pending | ✔ (`show system`, `show modules`, `show running-config`) ⁵ | ✔ merge, save `write memory` | ✘ | ✘ manual | ✘ |
| Fortinet FortiOS | `mock.fortinet.fortios` | simulation | ✔ | ✔ merge | ✘ | ✘ | ✔ (simulated, no rollback) |
| Fortinet FortiOS | `ssh.fortinet.fortios` | **experimental** | ✔ (`get system status`, `show`) ¹ | ✔ merge; FortiOS commits on `end` ² | ✘ | ✘ manual | ✘ |
| Cisco IOS-XE | `mock.cisco.iosxe` | simulation | ✔ | ✔ merge | ✔ | ✔ | ✔ (simulated, no rollback) |
| Cisco IOS-XE | `ssh.cisco.iosxe` | **experimental** | ✔ (`show version`, `show running-config`) ³ | ✔ merge, save `write mem` | ✘ | ✘ manual | ✘ |

¹ If console paging (`set output more`) is enabled, Netmiko temporarily sets
`config system console / set output standard` and restores it on disconnect.
Multi-VDOM devices are not supported.
² Relies on the default `cfg-save automatic`; not checked on the device.
³ Requires a privilege-15 login; enable-password prompts are not handled.
⁵ Netmiko `aruba_osswitch`: passes the "Press any key" banner, runs `enable` (the login
password is sent if an enable password is requested), then `terminal width 511` and
`no page` for the session; answers "no" to the save prompt on logout. Needs a manager login.
Checklist: `aruba-2930f-acceptance.md`.

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
All catalog entries are `simulated_only` (the support level rises to `lab_read_only` /
`lab_validated` only after acceptance tests on that model).

## What must be validated per model before a driver leaves "experimental"
Facts parsing against real output; behaviour of each rendered configuration line; how
the device displays applied configuration (for verification); error strings for rejected
lines; save behaviour; session limits and timeouts; and, before any firmware work, the
vendor's documented image transfer, boot-bank, reboot and rollback procedure.
