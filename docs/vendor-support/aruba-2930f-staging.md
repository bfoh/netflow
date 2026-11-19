# Aruba 2930F — staging with the team's configuration files

Source: two sample files supplied by the product owner on 2026-11-19 (one per switch role:
LTE switch and BH-DMZ switch), studied offline. The files are **not** in this repository
(they hold site names, addresses and an SNMP community). Tests use a synthetic file in the
same layout.

## What the files are (facts read from the samples)
| Topic | Finding |
|---|---|
| Kind | **Complete** switch configurations as written by the switch: first line `; JL260A Configuration Editor; Created on release #WC.16.08.0026`, then the team's change history in `;` comments, then the configuration. Windows line endings |
| Model | JL260A (2930F-48G-4SFP), 52 ports, most of them disabled and parked in a dummy VLAN |
| Written by | release WC.16.08.0026; the switches are upgraded to WC.16.10.0025 before staging |
| Management after loading | **192.168.1.1/24 on VLAN 222 (OOBM)**, untagged on port 3 (LTE switch) or port 2 (BH-DMZ switch); the site address on VLAN 168 on trunk ports |
| Access | `ip authorized-managers`: 192.168.1.0/24 with full manager rights, plus site management hosts (web/SSH) and one SNMP host. Telnet off; web interface HTTPS-only (`web-management ssl`, `no web-management`); SSH on with weak ciphers/MACs removed; SSH file transfer (SCP/SFTP) on |
| TFTP | `no tftp client`, `no tftp server`: once the file is active, the switch cannot fetch files by TFTP any more |
| Passwords | The files end with `password manager` and `password operator` **without values** |
| SNMP | One community string (counted, never shown) |
| Comments in the files | "https certificate shall be created before this configuration is loaded"; the LTE file is marked as a draft with hardening "not validated" |
| Inconsistency | The LTE switch file defines **VLAN 1004 twice** (names "SMAG" and "ERGR"); the second definition renames the first. In the BH-DMZ file ERGR is VLAN 1010 |

## Sequence for one 2930F
| # | Step | Mechanism | Status |
|---|---|---|---|
| 1 | Factory default → 192.168.1.1 (or 192.168.1.2 temporarily) on VLAN 222, OOBM port | console bootstrap | built; bench run pending (`aruba-2930f-console-bootstrap.md`) |
| 2 | Firmware → WC.16.10.0025 | firmware job, TFTP | built (experimental); bench run pending (`aruba-2930f-firmware.md`) |
| 3 | HTTPS certificate on the switch (the file's own caution) | by hand for now | how the team does it: Q-32 |
| 4 | Load the complete file into the startup configuration, restart, reconnect at the address the file sets, check the serial number, check the hostname, compare the running configuration | configuration job, replace mode, TFTP (`copy tftp startup-config <pc> <file> unix`) | **built (experimental)**, bench run pending (below) |
| 5 | Check the login after loading (bare `password` lines) | — | Q-31 |

Order matters: the file switches the TFTP client off, so firmware (step 2) must come first.
Both switch roles end at 192.168.1.1: after step 4 only one of them may be connected to the
bench network at a time — UNDM checks the serial number after the restart and refuses a
different switch answering at that address.

## Bench checklist — step 4 (spare 2930F only)
Before: steps 1–3 done; `UNDM_ENABLE_REAL_DEVICE_WRITES=true`; inbound UDP 69 allowed on the
laptop; laptop on 192.168.1.x on the switch's OOBM port; the other switch disconnected.

| # | Step | Expected |
|---|---|---|
| 1 | Device page → Retrieve information | model and serial read; this serial is checked again after the restart |
| 2 | Configurations → import the team's file | "Complete ArubaOS-Switch configuration (JL260A, 52 ports …)"; the notes above |
| 3 | Deployments → new plan → choose the file (mode switches to Replace) → Validate → Approve → Execute | "fetched the file (… bytes) into its startup configuration and is restarting" (plus "it will answer at 192.168.1.1" if the switch was on .2), "device reachable again (…, same serial number)", "back after loading: hostname …; N of M lines of the file appear in the running configuration" |
| 4 | Device page | management address now the one the file set (audit: "device.address_changed") |

If something goes wrong: "did not request the file" — firewall/addresses, or a question UNDM
did not recognise (its text is in the events); "a different device answers" — another unit
uses that address; "Authentication failed" after the restart — see Q-31. Please send back
the job's event list (names and addresses replaced).
