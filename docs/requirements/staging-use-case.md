# Primary use case: staging a four-device system from factory default

Source: product owner, 2026-11-19 (USER-CONFIRMED). This is the problem UNDM must solve
first; generic design/intent features are secondary to it.

## Today's process
Every system has four network elements:

| Device | Factory-default access (as stated by the product owner) |
|---|---|
| 1 × Fortinet FortiGate 101F | 192.168.1.99 on the management port; user `admin`, no password |
| 1 × Black Box switch: LIG1014A in some systems, LE2700A in others (confirmed 2026-11-18) | 192.0.2.1; user `admin`, no password |
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

## Black Box LIG1014A — what is known (2026-11-19)
DOCUMENTED (vendor quick-start guide and datasheet, found by web search; the documents
themselves could not be opened from the development environment):
- Factory default IP 192.0.2.1; login `admin` with a blank password.
- The quick-start guide shows a Telnet connection to the default IP and the user manual has
  a "CLI Initialization and Configuration" section.
- Datasheet feature list: Web, HTTPS, Telnet, SSH, SNMP v1/v2c, TFTP/FTP, Syslog, RADIUS,
  VLAN, RMON, DHCP.

Further details found by search on 2026-11-19 (CLI modes, save/copy commands, firmware
command, console settings) are in `docs/vendor-support/staging-procedures-research.md`.
Still unknown: whether SSH is enabled at factory default and the exact syntax for copying
files with a TFTP URL. The LE2700 series is a different family with different defaults.

## Answers from the product owner (2026-11-19, USER-CONFIRMED)
- **Cabling today:** the laptop is connected to each device directly, one at a time.
  Wanted: reach all four from the laptop at once.
- **Address clash:** both Aruba switches normally get 192.168.1.1. During staging one of
  them may use **192.168.1.2** and be changed back to 192.168.1.1 afterwards.
- **Aruba console commands used today** (role: DMZ switch — OOBM on port 2; role: LTE
  switch — OOBM on port 3):
  `configure` / `vlan 222` / `name "OOBM_VLAN"` / `untagged <2|3>` /
  `ip address 192.168.1.1 255.255.255.0` / `exit`, then save.
- **Configuration files** are produced by another team and loaded through each vendor's
  web interface. Formats not yet seen. A generator inside UNDM may come later.
- **Firmware:** FortiGate arrives on 7.2.7 and is upgraded **directly** to 7.6.5 (the
  team's established practice). Black Box arrives on v00.01.00 and is upgraded to
  v00.01.01. Aruba from/to versions not yet stated (the unit read on 2026-11-19 runs
  WC.16.10.0025).
- **FortiGate first login** forces a password change; the team sets the organisation's
  approved password. (The password itself is deliberately not recorded anywhere in this
  repository; it is entered into UNDM's credential store by the operator.)
- **Spare factory-default units** on a bench not connected to live networks: available.
- **Aruba firmware target:** WC.16.10.0025. **Console speed:** 9600.

## FortiGate configuration: two files (stated by the product owner 2026-11-18)
1. A **base file** common to all sites, uploaded through the FortiGate GUI; afterwards a
   revision named after the file is saved.
2. A **site file**, pasted into the CLI console of the GUI; afterwards a revision named
   after that file is saved.

Samples of both were supplied and studied; the findings and the planned UNDM sequence are in
`docs/vendor-support/fortigate-101f-staging.md`. The files are not stored in this repository.
