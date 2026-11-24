# Black Box switch — staging with the team's configuration file

Source: one sample file supplied by the product owner on 2026-11-19 and studied offline.
The file is **not** in this repository and never will be (it holds the admin password,
site addressing and names). Tests use a synthetic file in the same layout.

## How it is done by hand today
The complete configuration file is loaded through the switch's **web interface** (file
upload). LIG1014A: `http://192.0.2.1` → Configuration → upload; the page lets you choose
the running and/or the startup configuration (product owner, 2026-11-19). Firmware
v00.01.00 → v00.01.01 is also done through the web interface. Two models, two formats:
**LIG1014A** files use the switch's CLI syntax; **LE2700A** files are XML exports.

## Bench unit and logins (product owner, 2026-11-24)
The bench unit is a **LIG1014A**. Its factory login is `admin` with an **empty password**;
the team's file sets the approved admin password. In UNDM: the device's own login is the
factory one, and a plan that loads the file names the approved login as "login after
loading", as for the 2930F (D-042). UNDM keeps the approved login for the device once the
load is verified. Cable the PC to **port 1/3**: the file keeps management on that port only.

## LIG1014A file (facts read from the sample)
| Topic | Finding |
|---|---|
| Kind | A **complete** switch configuration in the switch's CLI syntax: `hostname`, `username`, `access management`, `vlan`, `interface GigabitEthernet 1/1` … `1/14`, `interface vlan <id>`, `!` separators, final `end`. No header naming model or firmware. Same syntax family as the LIG1014A CLI guide found earlier (`interface vlan`, `copy … startup-config`). |
| Ports | 14 Gigabit ports (1/1–1/14); unused ports shut down |
| Management after loading | The factory address **192.0.2.1 stays, on VLAN 222, untagged only on port 1/3** ("OOBM"); the site address is on VLAN 168, carried only by the trunk ports |
| Access restrictions | `access management` on: web and telnet only from 192.0.2.0–192.0.2.254 on VLAN 222 and from three site hosts on VLAN 168; SNMP from one host. Telnet itself is switched off (`no ip telnet`); the web interface is switched to HTTPS |
| Admin password | `username admin privilege 15 password encrypted <value>` — the value in the sample is **plain base64**: it decodes to readable text. Anyone with the file can read the admin password |
| Other | Syslog, SNMP traps, NTP, default route, voice-VLAN OUIs, an MST region name that looks like a MAC address (probably of the unit the file was exported from), RingV2 groups |

## LE2700A file (facts read from the sample)
| Topic | Finding |
|---|---|
| Kind | A **complete** configuration as an XML export: `<configuration>` with `<platform>` (product id, version), `<global>` and `<switch>` sections; every value in a `val` attribute, with the allowed syntax in a comment above it |
| Ports | 28 ports; 1–9 and 16 enabled, the rest disabled |
| Management after loading | **One static address only, the site address on VLAN 168**, untagged on port 16, tagged on trunk port 9 (port 10 is a member but disabled). The address the switch had before loading is gone |
| Access | SSH on, HTTPS on (no redirect from HTTP); logins local for console, SSH and web; telnet login method `none` = telnet off (product owner, Q-30) |
| Accounts | **No administrator accounts or passwords** in the file |
| SNMP | v2c on, with the well-known default community names and a read-write group accepted from any address |
| Other | Syslog, NTP, SNMP trap destination, port names, VLANs, ring and Modbus/EtherNet-IP sections |

## What follows for UNDM
- Both files are loaded **as a whole** (replace), never line by line. UNDM's offline check
  says so at import and refuses a merge plan.
- LE2700A: after loading, the switch is only reachable at its site address, on port 16 (or
  tagged on port 9). Any automated check after loading needs the laptop in that subnet on
  that port (Q-29). Its admin login is not in the file, so the stored credential should stay
  valid (to confirm).
- LE2700A: SNMP accepts configuration changes from any address with a default community
  name. This is the team's file, not UNDM's decision, but worth a review by whoever owns the
  template.
- On the bench, after loading, the laptop must be on **port 1/3** with a 192.0.2.x address
  to reach the switch (web/HTTPS). Whether SSH is allowed by the `access management` rules
  ("telnet" may or may not cover SSH) is unknown — this decides whether UNDM can verify
  the switch over SSH after loading (Q-27).
- The base64 "encryption" means these files must be handled like files containing the
  password in clear text (storage, e-mail, sharing). UNDM flags it at import and never
  shows the value.

## Possible ways for UNDM to load the file (to decide after the bench questions)
| Way | What is documented | What is missing |
|---|---|---|
| CLI over SSH + TFTP | LIG1014A CLI guide: SSH on port 22; `copy` between startup-config, running-config and files in flash or on a TFTP server (`tftp://server[:port]/path`); `copy running-config startup-config` | whether SSH is on by default; the exact `copy` syntax with a URL; whether a reload is needed (Q-28) |
| Web interface (as today) | the upload page exists | its requests are not documented; automating them would need a recorded upload from a spare unit |

## Built so far
- Offline recognition at import: kind, ports, where the switch answers after loading, the
  access restrictions, the password warning.
- Black Box LIG1014A and LE2700A in the model catalog with a **simulated** driver, so a plan
  that loads either file can be rehearsed. No real-device driver yet.
- LE2700A XML: files that declare a document type or entities are refused (no XML-based
  attack can reach the backend through an import).

## Bench log
| Date | Unit | Step | Result | Notes |
|---|---|---|---|---|
| 2026-11-24 | — | Second team file (LIG1014A, another system) checked offline | **recognised** | Same format as the first sample. UNDM's import check reported it correctly: complete configuration → replace; 14 ports, 9 shut down; after loading the switch answers only on VLAN 222 (untagged on port 1/3) and on the site VLAN (trunk ports 1/10 and 1/14, native VLAN tagged); VLAN 1 loses its address and is forbidden on every port; `access management` allows web and telnet only (whether that covers SSH is the key bench question, Q-27); telnet off; HTTPS only; one base64 "encrypted" password. The file is not stored in UNDM's repository. |

