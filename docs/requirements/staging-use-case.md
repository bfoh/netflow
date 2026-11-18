# Primary use case: staging a four-device system from factory default

Source: product owner, 2026-11-19 (USER-CONFIRMED). This is the problem UNDM must solve
first; generic design/intent features are secondary to it.

## Today's process
Every system has four network elements:

| Device | Factory-default access (as stated by the product owner) |
|---|---|
| 1 × Fortinet FortiGate 101F | 192.168.1.99 on the management port; user `admin`, no password |
| 1 × Black Box switch (model to be confirmed) | 192.0.2.1; user `admin`, no password |
| 2 × Aruba 2930F | no usable management IP; user `manager`, no password |

For the two Aruba switches a technician connects to the **console port** and configures
management address 192.168.1.1 reachable on **port 2** (one switch) or **port 3** (the
other). After that, firmware and configuration are pushed to each device separately
through its **web interface**.

## Goal
- Push configuration (and firmware) to **all four devices from one place** (one tool, one
  sitting) instead of four web portals plus a console session.
- Still handle the Aruba switches, which have no default management IP.

## Consequences for UNDM
1. The core workflow is a **staging run**: factory-default device → identified → reachable
   → correct firmware → full configuration from a supplied file → verified → report.
2. Configurations are **supplied files** (per system), not generated from intent.
   Full-configuration restore matters more than merge-mode deployment.
3. A **console (serial/USB) bootstrap** for ArubaOS-Switch is required (provisioning
   approach B in the directive). UNDM runs on the technician's PC, so the backend can use
   the PC's COM ports directly (pyserial is already installed with Netmiko; Netmiko has
   no ArubaOS-Switch serial device type, so UNDM needs its own small console driver).
4. Real **firmware procedures** are needed for exactly three platforms: 2930F
   (ArubaOS-Switch), FortiGate 101F (FortiOS), and the Black Box model.
5. Factory-default login behaviour must be handled per platform (empty passwords; FortiOS
   first-login password change — to be verified on a factory-default unit).

## Facts still to be verified (not yet DOCUMENTED or tested)
- ArubaOS-Switch factory default: whether VLAN 1 requests an address by DHCP (the saved
  configuration of the tested unit shows `ip address dhcp-bootp` on VLAN 1), and whether
  SSH is enabled without a password. If both hold, a DHCP-based bootstrap could replace
  the console step.
- Vendor-documented file-transfer methods for configuration and firmware on each of the
  three platforms and the exact firmware versions in use.
- What the supplied configuration files are (saved startup configurations or command
  scripts) and how the web interfaces apply them today.

Open questions for the product owner are tracked in `docs/REFERENCE_ANALYSIS.md` (Q-10 on).
