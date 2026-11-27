# Vendor procedures for staging — research record

Collected 2026-11-19 by web search (the documents themselves could not be opened from
the development environment, so every item is a search-result extract and must be
re-checked against the full document or on the bench before it is relied on).

Evidence: **DOC** = vendor documentation; **COMM** = community post / third-party page;
**USER** = stated by the product owner; **UNKNOWN** = not found.

## Aruba 2930F (ArubaOS-Switch, target firmware WC.16.10.0025 — USER)
| Topic | Finding | Evidence |
|---|---|---|
| Factory-default addressing | "In the factory default configuration, the switch automatically obtains its IP network settings from a DHCP or BootP server" | DOC (2930F quick setup guide) |
| Console speed | 9600 used by the team | USER |
| Firmware to flash | `copy tftp flash <tftp-ip> <file.swi> primary` | COMM (2930F upgrade write-ups); syntax `flash <primary\|secondary>` DOC for sibling models |
| Activate firmware | `boot system flash primary` (reboots) | COMM |
| Check image | `verify signature flash primary` before rebooting | COMM |
| Configuration from file | `copy tftp {startup-config \| running-config} <ip-address> <remote-file> [pc \| unix]`; a replaced startup-config takes effect after reboot | DOC (ArubaOS-Switch manual page for a sibling model) + COMM |
| Configuration to file | `copy startup-config tftp <ip-address> <remote-filename>` | COMM (HPE forum) |
| SCP/SFTP | Requires secure copy to be enabled on the switch ("Secure Copy Enabled: Yes/No" in SSH status). Paths and enabling command not confirmed by search; the accepted unit's configuration contains `ip ssh filetransfer` | COMM + observed |
| SSH at factory default / empty password | — | UNKNOWN (bench test) |

## Fortinet FortiGate 101F (7.2.7 → 7.6.5 directly — USER)
| Topic | Finding | Evidence |
|---|---|---|
| Default access | 192.168.1.99 on the management port, `admin`, no password; password change forced at first login | USER |
| Configuration restore | `execute restore config tftp <filename> <tftp server> [password]` | DOC (FortiGate 7.6.5 CLI reference) |
| Firmware | `execute restore image tftp <filename> <tftp address>` | DOC (FortiGate 7.6.5 CLI reference) |
| SCP restore | Not confirmed for FortiGate (only found for FortiManager) | UNKNOWN |
| First-login dialogue text | — | UNKNOWN (bench test) |

## Black Box LIG1014A (firmware v00.01.00 → v00.01.01 — USER)
| Topic | Finding | Evidence |
|---|---|---|
| Defaults | IP 192.0.2.1; `admin`, no password | DOC (quick start guide, user manual) + USER |
| Console | 115,200 bps, 8 data bits, no parity, 1 stop bit, no flow control | DOC (CLI guide, quick start) |
| CLI access | Console, Telnet (port 23), SSH (port 22). Whether SSH is enabled by default: not stated | DOC / UNKNOWN |
| Set IP by CLI | `enable`, `configure terminal`, `interface vlan 1`, `ip address …`, `exit` | DOC (user manual) |
| Save configuration | `copy running-config startup-config` | DOC (CLI guide) |
| Load/save configuration files | `copy { startup-config \| running-config \| <Filename> }` … with a file "in flash or on a TFTP server"; TFTP URL form `tftp://server[:port]/path-to-file` (exact full syntax of copy with a URL not confirmed) | DOC (CLI guide) |
| Firmware | `firmware { swap \| upgrade }` — upgrade, and swap between active and alternate image; web: Maintenance → Software → Upload ("do not restart until it reboots on its own") | DOC (CLI guide, user manual) |
| Factory reset | `reload defaults` / `reload defaults keep-ip` | DOC (CLI guide) |

## Black Box LE2700A (LE2700 series) — different product family from the LIG1014A
| Topic | Finding | Evidence |
|---|---|---|
| Defaults | Static IP **192.168.10.1**; `admin` / `admin` (differs from the LIG1014A defaults) | DOC (LE2700A quick start guide) — to confirm with the product owner |
| Console | RS-232 on RJ-45, 115200 bps, 8, N, 1 | DOC (quick start guide) |
| Firmware | Web page "Firmware Update" (user manual 5.1.11) | DOC |
| Configuration | Web page "Backup/Restore Configurations" (user manual 5.1.10) | DOC |
| Telnet | Can be enabled in the remote-control security settings | DOC |
| SSH, TFTP, CLI command set | — | UNKNOWN |

## Consequences
1. **TFTP is the one transfer method documented for the Aruba, the FortiGate and the
   LIG1014A.** A staging run therefore needs a TFTP server on the bench laptop that serves
   exactly the run's firmware and configuration files, only on the bench adapter, only
   while the run is active. Open question for the product owner: whether the laptop's
   firewall allows inbound TFTP (UDP 69) from the bench network.
2. The LE2700A is documented as web-managed; automating it may need its web interface or
   Telnet. It needs its own investigation and exact model.
3. A factory-default 2930F asks for an address by DHCP, so a DHCP-based bootstrap could
   later replace the console step. It needs a DHCP service on the isolated bench only.

## Sources
- Black Box CLI guide (LIG1014A/LIE1014A and LIG1080A families): https://bbpimassetsp-aza7efghcfa8c2dh.a03.azurefd.net/resources/lig1080a_cli-guide-rev1_22232.pdf , https://manualzz.com/doc/41821334/industrial-managed-gigabit-ethernet-switch-cli-guide
- Black Box LIG1014A user manual: https://www.manualslib.com/manual/1271771/Black-Box-Lig1014a.html
- Black Box LIG1014A/LIE1014A quick start: https://manualzz.com/doc/79043534/black-box-lie1014a-quick-start-manual
- Black Box LE2700A quick start: https://bbpimassetsp-aza7efghcfa8c2dh.a03.azurefd.net/resources/le2700a_qsg_rev1_21165.pdf ; user manual: https://www.manualslib.com/manual/976500/Black-Box-Le2700a.html
- Aruba 2930F: https://arubanetworking.hpe.com/techdocs/AOS-S/16.11/MCG/WC/content/home.htm ; https://network-faq.blogspot.com/2023/12/aruba-2930f-switch-firmware-upgrade.html ; https://manualslib.com/manual/1536241/Aruba-2530.html?page=277 ; https://airheads.hpe.com/discussion/copy-startup-config-tftp-on-2530-switch
- FortiGate 7.6.5 CLI reference: https://docs.fortinet.com/document/fortigate/7.6.5/cli-reference/150608926

## Ping, traceroute and console speeds after staging (v95, D-126, D-128)

Found by web search on 2026-11-27. The vendor pages themselves could not be opened from the
development environment (their hosts are not reachable from it), so what is recorded here
is what the search results quote from them; every command stays experimental until the
bench shows its output (Q-59, Q-60).

| Platform | What | Source (as quoted by the search results) |
|---|---|---|
| FortiOS (FortiGate) | `execute ping <dest>`; options with `execute ping-options` before the ping (left at their defaults by UNDM) | Fortinet, FortiGate cookbook "Running ping and traceroute" (docs.fortinet.com/document/fortigate/6.2.0/cookbook/982816/running-ping-and-traceroute); FortiOS CLI reference "execute ping-options" (docs.fortinet.com/document/fortigate/7.2.13/cli-reference/221756471/execute-ping-options) |
| FortiOS (FortiGate) | `execute traceroute <dest>` | Fortinet, FortiOS CLI reference "execute traceroute" (docs.fortinet.com/document/fortigate/8.0.0/cli-reference/868095304/execute-traceroute); admin guide example output: a header with "32 hops max", numbered hops with three times in ms |
| FortiOS (FortiGate) | console 9600 baud default (`config system console`: 9600, 19200, 38400, 57600, 115200) | Fortinet, FortiOS 6.0 CLI reference "system console" (docs.fortinet.com/document/fortigate/6.0.6/cli-reference/363838/system-console) |
| ArubaOS-Switch (2930F) | `ping <ip> repetitions <1-10000>` (example "ping 10.10.10.10 repetitions 3"); `traceroute <ip>` with `maxttl` | HPE/Aruba, 2930F/2930M Management and Configuration Guide (16.05 to 16.11), troubleshooting chapter ("Number of ping packets", "A low maxttl causes traceroute to halt…") |
| Nokia 7705 SAR | `ping {ip-address \| dns-name} … [count requests] … [router router-instance]`, router Base by default | Nokia, 7705 SAR Basic Command Reference (infocenter.nokia.com, root commands) |
| Nokia 7705 SAR | traceroute | **Not confirmed**: the results describe what it does, not its syntax. Not offered by UNDM. |
| Black Box LIG1014A | console 115200 bps, 8 data bits, 1 stop bit, no parity, no flow control | Black Box, LIG1014A/LIG1082A/LIG1080A quick start guide |
| Black Box LIG1014A | ping, traceroute | **Not found**. Not offered by UNDM. |
| Windows (bench PC) | `ping -n <count> -w <timeout ms>`, `tracert -d -h <max hops> -w <timeout ms>` | Microsoft, Windows Commands reference "ping" and "tracert" (learn.microsoft.com) |
