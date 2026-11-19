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
| Passwords | The copies supplied end with `password manager` and `password operator` without values; the file the team loads **sets the approved manager password** (product owner, Q-31), so the login changes during the load |
| SNMP | One community string (counted, never shown) |
| Comments in the files | "https certificate shall be created before this configuration is loaded"; the LTE file is marked as a draft with hardening "not validated" |
| Inconsistency | The LTE switch file defines **VLAN 1004 twice** (names "SMAG" and "ERGR"); the second definition renames the first. In the BH-DMZ file ERGR is VLAN 1010 |

## Sequence for one 2930F
| # | Step | Mechanism | Status |
|---|---|---|---|
| 1 | Factory default → (new units: manager credentials set to the approved login) → 192.168.1.1 (or 192.168.1.2 temporarily) on VLAN 222, OOBM port | console bootstrap | built; bench run pending (`aruba-2930f-console-bootstrap.md`) |
| 2 | Firmware → WC.16.10.0025 | firmware job, TFTP | built (experimental); bench run pending (`aruba-2930f-firmware.md`) |
| 3 | HTTPS certificate on the switch (the file's own caution) | first part of the load job (step 4), with the project's certificate subject | **built (experimental)**; by hand if no subject is set |
| 4 | Load the complete file into the startup configuration, restart, reconnect at the address the file sets **with the login after loading** (approved password), check the serial number and the hostname, compare the running configuration | configuration job, replace mode, TFTP (`copy tftp startup-config <pc> <file> unix`) | **built (experimental)**, bench run pending (below) |

### Step 3 — HTTPS certificate, as the team does it today (Q-32)
```
crypto pki identity-profile <profile-name> subject
<subject values, one per line, in the order the switch asks: common name, organisational
 unit, organisation, location, …, country code; Enter for the ones left empty>
crypto pki enroll-self-signed certificate-name <certificate-name>
web-management ssl
save
```
The questions the switch asks (screenshot from a running unit, 2026-11-19), in this order,
in the configuration context (`(config)#`):

| Question as shown | Field |
|---|---|
| `Enter Common Name(CN) :` | common name |
| `Enter Org Unit(OU) :` | organisational unit |
| `Enter Org Name(O) :` | organisation |
| `Enter Locality(L) :` | locality |
| `Enter State(ST) :` | state (left empty by the team) |
| `Enter Country(C) :` | two-letter country code |

`crypto pki enroll-self-signed certificate-name <name>` prints nothing on a new switch and
returns to the prompt; on a switch that already has it, it prints
`Certificate "<name>" already exists.` Then the team enters `web-management ssl` and saves.

**In UNDM (D-044):** set the subject once per project (Project settings → HTTPS certificate).
Before loading a file that makes the web interface HTTPS-only, the load job runs
`configure`, the identity-profile command (answering exactly these six questions with the
project's values), the enroll command (silence or "already exists" both count as done),
`web-management ssl`, `end` and `write memory`. Any other question or an error stops the job
before the file is sent. The values live only in the UNDM database, not in this repository.

Order matters: the file switches the TFTP client off, so firmware (step 2) must come first.
Both switch roles end at 192.168.1.1: after step 4 only one of them may be connected to the
bench network at a time — UNDM checks the serial number after the restart and refuses a
different switch answering at that address.

## Bench checklist — step 4 (spare 2930F only)
Before: steps 1–3 done; `UNDM_ENABLE_REAL_DEVICE_WRITES=true`; inbound UDP 69 allowed on the
laptop; laptop on 192.168.1.x on the switch's OOBM port; the other switch disconnected; in the
project's **Credentials**: the **approved login** (manager + approved password). On new units
it is already the device's login from the bootstrap; on a unit that still had the factory
login (manager, no password), choose the approved login under **Login after loading**.

| # | Step | Expected |
|---|---|---|
| 1 | Device page → Retrieve information | model and serial read; this serial is checked again after the restart |
| 2 | Configurations → import the team's file | "Complete ArubaOS-Switch configuration (JL260A, 52 ports …)"; the notes above |
| 3 | Project settings → HTTPS certificate: enter the subject once. Deployments → new plan → choose the file (mode switches to Replace) → (only if the device still has the factory login: **Login after loading** = approved login) → Validate → Approve → Execute | events start with "HTTPS certificate 'certificate' created (self-signed); web management set to SSL and saved" (or "already existed") | "fetched the file (… bytes) into its startup configuration and is restarting" (plus "it will answer at 192.168.1.1" if the switch was on .2), "device reachable again (…, same serial number)", "back after loading: hostname …; N of M lines of the file appear in the running configuration" |
| 4 | Device page | management address now the one the file set, credential now the approved one (audit: "device.address_changed", "device.credential_changed") |
| 5 | Browser: `https://192.168.1.1` | the web interface opens over HTTPS (the certificate from step 3 survived the load) |

If something goes wrong: "did not request the file" — firewall/addresses, or a question UNDM
did not recognise (its text is in the events); "a different device answers" — another unit
uses that address; "Authentication failed" after the restart — see Q-31. Please send back
the job's event list (names and addresses replaced).
