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
| Q-10 | Staging: are the four devices configured one at a time (laptop cabled to each), or all cabled together? Where does the laptop plug in? | Both Aruba switches use 192.168.1.1, so they cannot share one network segment at the same address. Decides the staging-run design. |
| Q-11 | Exact console commands typed today on a factory-default 2930F (sanitized) | Becomes the console bootstrap. |
| Q-12 | Black Box switch exact model and firmware version | No driver exists; needs the vendor manual. |
| Q-13 | What are the per-system configuration files (source tool, format per device), and which web-interface function applies them? | Decides restore method and verification. |
| Q-14 | Firmware versions currently installed vs target, per device; file types | Firmware procedures and upgrade-path rules. |
| Q-15 | FortiGate 101F first login: is a password change forced, and what is done about it today? | Factory-default login handling. |
| Q-16 | Are spare factory-default units available for testing on an isolated bench? | Safe place to validate writes (replaces testing on a zone switch). |
| Q-09 | Is the zone used for 2930F testing a test/verification system or a live network? | Decides whether phase B (first write) may use this unit. |
| Q-08 | Can future screenshots be sanitized (system names, hostnames, zone numbers, user names removed) before sharing? | Directive 5 handling rules. |
