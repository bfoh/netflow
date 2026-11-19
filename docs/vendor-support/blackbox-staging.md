# Black Box switch — staging with the team's configuration file

Source: one sample file supplied by the product owner on 2026-11-19 and studied offline.
The file is **not** in this repository and never will be (it holds the admin password,
site addressing and names). Tests use a synthetic file in the same layout.

## How it is done by hand today
The complete configuration file is loaded through the switch's **web interface** (file
upload). Firmware v00.01.00 → v00.01.01 is also done through the web interface.

## What the file is (facts read from the sample)
| Topic | Finding |
|---|---|
| Kind | A **complete** switch configuration in the switch's CLI syntax: `hostname`, `username`, `access management`, `vlan`, `interface GigabitEthernet 1/1` … `1/14`, `interface vlan <id>`, `!` separators, final `end`. No header naming model or firmware. Same syntax family as the LIG1014A CLI guide found earlier (`interface vlan`, `copy … startup-config`). |
| Ports | 14 Gigabit ports (1/1–1/14); unused ports shut down |
| Management after loading | The factory address **192.0.2.1 stays, on VLAN 222, untagged only on port 1/3** ("OOBM"); the site address is on VLAN 168, carried only by the trunk ports |
| Access restrictions | `access management` on: web and telnet only from 192.0.2.0–192.0.2.254 on VLAN 222 and from three site hosts on VLAN 168; SNMP from one host. Telnet itself is switched off (`no ip telnet`); the web interface is switched to HTTPS |
| Admin password | `username admin privilege 15 password encrypted <value>` — the value in the sample is **plain base64**: it decodes to readable text. Anyone with the file can read the admin password |
| Other | Syslog, SNMP traps, NTP, default route, voice-VLAN OUIs, an MST region name that looks like a MAC address (probably of the unit the file was exported from), RingV2 groups |

## What follows for UNDM
- The file is loaded **as a whole** (replace), never line by line. UNDM's offline check
  says so at import and refuses a merge plan.
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
- Black Box LIG1014A in the model catalog with a **simulated** driver, so a plan that
  loads the file can be rehearsed. No real-device driver yet.
