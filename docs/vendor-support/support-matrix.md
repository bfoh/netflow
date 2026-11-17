# Vendor Support Matrix

**No real device is supported yet.** Everything below runs against simulated devices.

| Family | Driver | Driver status | Template | Intent features rendered | Template verification |
|---|---|---|---|---|---|
| Aruba AOS-CX | `mock.aruba.aoscx` | Simulated | `aoscx.j2` v0.1.0 | hostname, VLANs, VLAN interface (SVI) addresses + description, static routes | Docs-reviewed, not lab-verified |
| Fortinet FortiOS (FortiGate) | `mock.fortinet.fortios` | Simulated | `fortios.j2` v0.1.0 | hostname, physical interface addresses (`set ip`, `set status`), static routes (egress interface required) | Docs-reviewed, not lab-verified |
| Cisco IOS-XE | `mock.cisco.iosxe` | Simulated | `iosxe.j2` v0.1.0 | hostname, VLANs, interface (physical + SVI) addresses + description, static routes | Docs-reviewed, not lab-verified |

Explicitly **not rendered** yet (generation reports an error instead):
- AOS-CX: addresses on physical (routed) ports — needs per-model/firmware confirmation of
  the routing/L2 default and the exact syntax.
- FortiOS: VLAN definitions (FortiOS models VLANs as sub-interfaces on a parent
  interface; the intent model needs a parent-interface concept first), interface
  descriptions (alias/description field to be confirmed per FortiOS version).

## Device model registry
All catalog entries (`backend/src/undm/inventory/catalog.py`) are `simulated_only`.
Support levels: `simulated_only` → `lab_read_only` → `lab_validated`.

## Validation needed before any real adapter
For each target model + firmware: management access method and default state,
configuration syntax for each rendered feature, how to back up and roll back (e.g.
checkpoints, revisions, archive/replace), how to confirm a change took effect, reboot
and firmware behaviour, rate limits and session limits.
