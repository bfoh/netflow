# Reference Analysis

## Reference material index
| ID | Material | Received | Handling | Analysis |
|---|---|---|---|---|
| SC-01…SC-04 | Four TNDM GUI screenshots (one is a photo of a monitor) | 2026-11-17 | Not stored in repo; identifiers redacted | `reference-analysis/tndm-screenshot-catalog.md` |
| BRIEF-01 | Product owner's description of TNDM capabilities (directive section 2) | 2026-11-17 | USER-CONFIRMED statements | Requirements in `REQUIREMENTS.md` |

## REA (Reverse Engineer Anything) analysis record
REA and its analysis engines are installed in the development container as an optional
research aid. They are **not** a dependency of UNDM.

| Authorization condition (directive 6) | Status |
|---|---|
| 1. Analysis expressly authorized | Not given |
| 2. Software licence permits the activity | Not verified |
| 3. Use of Claude Code / AI provider permitted for the material | Not confirmed |
| 4. Files, versions, components in scope | Not defined |
| 5. Credentials, keys, confidential config, customer data excluded | n/a |
| 6. Scope documented | n/a |

**No REA analysis has been performed.** None is needed for current work: the
screenshots and public vendor documentation are sufficient for functional requirements.

Template for future entries:
```
### REA-<n> <question>
Authorized artifact:   <file, version, hash>  Authorization ref: <who/when/where>
Question:              <narrow engineering question>
Evidence obtained:     <summary, no proprietary code>
Confidence:            <high/medium/low>
Relevance:             <public protocol / independent functionality>
Safe conclusions:      <what UNDM may use>
```

## Open questions for the product owner
| ID | Question | Why it matters |
|---|---|---|
| Q-01 | What does TNDM's **Initialize** do for the Aruba and Fortinet models you know: console-based, network-based (factory-default IP / DHCP), or vendor ZTP? What is the minimal configuration it applies? | Shapes the provisioning engine (Phase 6) and the first lab model. |
| Q-02 | What does **Audit** check: running config vs. expected config, security baseline, or something else? What does a report contain? | Drift/compliance design. |
| Q-03 | Do cluster/zone/site numbers and "octets" determine device IP addresses (e.g. 10.\<zone\>.\<site\>.x)? What other values are derived from the structure (VLAN IDs, hostnames)? | Addressing-plan feature (RA-04). |
| Q-04 | What does **MAC Filtering** manage (port security, NAC allow-lists)? | Intent model scope. |
| Q-05 | Which exact models and firmware versions should the first lab phase target (e.g. one Aruba CX model + one FortiGate model)? Is a lab available? | Phase 5 planning; real drivers are built per model/firmware. |
| Q-06 | Multi-user needs: how many engineers, separate approvers required? Single-machine or shared server? | Authentication design (M1), separate-approver default. |
| Q-07 | Should UNDM import existing device configurations as a project starting point (brownfield)? | Intent-from-config parsing is a large feature. |
| Q-10 | Staging: are the four devices configured one at a time (laptop cabled to each), or all cabled together? Where does the laptop plug in? | Answered 2026-11-19: one at a time today; wants all at once. One Aruba may use 192.168.1.2 temporarily. |
| Q-11 | Exact console commands typed today on a factory-default 2930F (sanitized) | Answered 2026-11-19: recorded in `requirements/staging-use-case.md`; implemented as the console bootstrap. |
| Q-12 | Black Box: LIG1014A documented by search (see `vendor-support/staging-procedures-research.md`); manuals cannot be supplied by the product owner. **Open: exact LE2700-series model, and whether its defaults are 192.168.10.1 / admin / admin as its quick-start guide says.** | LE2700A is a different family from the LIG1014A. |
| Q-13 | Configuration files: produced by another team, loaded via each vendor's web interface (answered 2026-11-19). **Still needed: a sample of each file (first lines) and the web-interface function used.** | Decides restore method and verification. |
| Q-14 | Firmware: Aruba target **WC.16.10.0025** (answered 2026-11-19; arrival version not readily known); FortiGate 7.2.7 → 7.6.5 direct; Black Box v00.01.00 → v00.01.01. | UNDM reads the arrival version from the device itself. |
| Q-15 | FortiGate 101F first login: is a password change forced, and what is done about it today? | Answered 2026-11-19: yes, a change is forced; the approved password is set (not recorded here). |
| Q-16 | Are spare factory-default units available for testing on an isolated bench? | Answered 2026-11-19: yes. |
| Q-17 | Console speed for a factory-default 2930F: **9600** (answered 2026-11-19). | Default of the console bootstrap. |
| Q-18 | Can the staging laptop accept inbound TFTP (UDP 69) from the bench network (Windows Firewall / company policy), or is a TFTP server tool already approved? | TFTP is the transfer method documented for Aruba, FortiGate and LIG1014A. Product owner 2026-11-18: start with TFTP; change method if the bench test fails. |
| Q-19 | FortiGate: is the base file restored **before** the firmware upgrade (on 7.2.7, the version it was written on) or after it (on 7.6.5)? | **Answered 2026-11-19: after.** Firmware first, then base, then site (D-034). |
| Q-20 | FortiGate: after the base file is restored, which administrator password is valid — the approved one, or one that is only in the base file? | **Answered 2026-11-19:** the base file has its own, and the team changes it in the file to the approved one. Not recorded here. |
| Q-21 | FortiGate: when the site file is pasted today, are any error messages normal apart from the first `end`? | **Answered 2026-11-19: no.** |
| Q-22 | FortiGate: after the site file, is anything else done by hand (the tunnel's pre-shared key, which is placeholder text in the sample; licence; certificates; the remote-access and inter-site scripts mentioned in the file header)? | **Answered 2026-11-19:** the CEN tunnel's pre-shared key is set to an approved value (now inserted from the credential store, D-036). |
| Q-24 | FortiGate first login: may UNDM perform the forced password change (factory unit, `admin` with no password) itself? | Would be a second exception to the deployment lifecycle (only console bootstrap is allowed today). Until agreed: done by hand in the browser. |
| Q-26 | Black Box: is the sample file (14 Gigabit ports, 192.0.2.1 kept on VLAN 222) for the **LIG1014A**? Do LE2700A systems use files in the same format? | Decides which model the file check and the future driver cover. |
| Q-27 | Black Box: in the web interface, which page loads the file, does it ask "running" or "startup" configuration and "replace" or "merge", and does the switch restart afterwards? Can you still log in by SSH after loading (the file's access rules mention only web and telnet)? | Decides how UNDM loads the file and how it verifies the result. |
| Q-28 | Black Box (spare unit, factory default): does `ssh admin@192.0.2.1` work? If yes, the output of `show version`, `copy ?` and `reload ?` (sanitized). | Gives the exact, verified command syntax for loading a file by TFTP. |
| Q-25 | FortiGate wording to confirm on the bench: the questions before `execute restore image/config tftp`, the reply to a bare `end`, informational replies such as on `edit root`, and the output of `execute backup config flash` / `execute revision list config`. | The procedures answer only documented questions and treat unknown replies cautiously; the bench run will show the real text. |
| Q-23 | Exact Black Box model in the other systems: **LE2700A** (answered 2026-11-18). | Web-managed; needs its own investigation. |
| Q-09 | Is the zone used for 2930F testing a test/verification system or a live network? | Decides whether phase B (first write) may use this unit. |
| Q-08 | Can future screenshots be sanitized (system names, hostnames, zone numbers, user names removed) before sharing? | Directive 5 handling rules. |
