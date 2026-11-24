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
| Q-26 | Black Box: is the sample file (14 Gigabit ports, 192.0.2.1 kept on VLAN 222) for the **LIG1014A**? Do LE2700A systems use files in the same format? | **Answered 2026-11-19:** yes, LIG1014A. The LE2700A uses a different format (XML export; sample supplied, now recognised). |
| Q-27 | Black Box: in the web interface, which page loads the file, does it ask "running" or "startup" configuration and "replace" or "merge", and does the switch restart afterwards? Can you still log in by SSH after loading? | **Partly answered 2026-11-19 (LIG1014A):** `http://192.0.2.1` → Configuration → upload; the page lets you choose running and/or startup configuration. Still open: replace/merge choice, restart, SSH after loading; and the same for the LE2700A. |
| Q-28 | Black Box (spare unit, factory default): does `ssh admin@192.0.2.1` work? If yes, the output of `show version`, `copy ?` and `reload ?` (sanitized). | **Partly answered 2026-11-19:** SSH works; the outputs will follow when a unit is available. |
| Q-29 | LE2700A: factory-default address and login (its quick-start guide says 192.168.10.1, admin/admin), and how its file is loaded (web page, running/startup, restart)? After loading, the switch keeps only the site address on its management VLAN: how is it reached on the bench today? | **Answered 2026-11-19:** the quick-start defaults are correct (192.168.10.1, admin/admin). |
| Q-30 | LE2700A: what does login method `none` for telnet mean on this switch — telnet off, or telnet without a password? The file's own syntax comment lists none/local/RADIUS/TACACS+ without saying. | **Answered 2026-11-19:** telnet is switched off. |
| Q-31 | 2930F (both roles, BH-DMZ and LTE switch: both files end the same way): the files end with `password manager` / `password operator` without values. After uploading the file through the web page and the restart, which login works — manager with no password, the approved password set earlier, or a password set by hand afterwards? | **Answered 2026-11-19:** the file the team loads sets the new approved password, so the login changes during the load (manager/no password before, approved password after). UNDM now takes a "login after loading" credential per plan (D-042). |
| Q-32 | 2930F (both roles; both files carry the comment "https certificate shall be created before this configuration is loaded"): how is the certificate created before uploading — which web page or CLI command — or is the step skipped? | **Answered 2026-11-19:** before loading, the team runs `crypto pki identity-profile <profile> subject` (then types the subject values the switch asks for, one per line), `crypto pki enroll-self-signed certificate-name <name>`, `web-management ssl`, `save`. Recorded in `vendor-support/aruba-2930f-staging.md`; the organisation's values are not stored in the repository. |
| Q-34 | 2930F certificate step: on a spare switch, the exact screen text of each question asked after `crypto pki identity-profile … subject` and after `crypto pki enroll-self-signed …` (organisation values replaced by placeholders). | **Answered 2026-11-19:** the six subject questions are recorded; the enroll command prints nothing on a new switch, or `Certificate "<name>" already exists.`; then `web-management ssl` and save. Built as the first part of the load job (D-044). |
| Q-35 | 2930F new units: after "Configure the manager credentials :" and "Username:", the exact wording of the password prompt and its confirmation, and any password rules the switch states. | **Answered 2026-11-19 (screenshot of a new unit):** `Username:`, `Password:`, `Re-enter the new password:` — UNDM now answers exactly these, in this order. |
| Q-33 | 2930F LTE switch file: VLAN 1004 is defined twice ("SMAG", then "ERGR"); in the BH-DMZ file ERGR is VLAN 1010. Intended, or a slip in the template? | **Answered 2026-11-19:** the files come from a colleague and are loaded as they are. UNDM keeps reporting the duplicate at import so it can be passed on to the file's author. |
| Q-36 | 2930F file load by TFTP (`copy tftp startup-config <pc> <file> unix`): on the bench (2026-11-23) the switch fetched the whole file and restarted, but came back with its **previous** configuration (twice). What does the switch print on the console during the load and the start, and what does `show logging` report afterwards? How does the team load the files today: the web page (Q-31), or a CLI command? | **Answered 2026-11-23:** with the certificate created first, the TFTP load worked (hostname, OOBM VLAN on port 3, HTTPS-only web, TFTP client off, as in the file). Cause of the earlier failures: no certificate. Through the web page too, the file is not taken unless the HTTPS certificate commands were run first; all three UNDM loads ran without a certificate subject (step skipped). UNDM now requires the subject (D-053). To be confirmed by a load with the certificate. Also: the team loads the files through the switch's **web page** (UNDM's TFTP CLI method is not the team's method and is unproven on the 2930F). A third run ended the same way. Still open: the switch's output of the load (v22 records it), its log after the restart, and a cross-check: the same file loaded through the web page on the spare unit. UNDM now checks the startup configuration before restarting a switch that returns to its prompt, answers "n" to any save question during the load, and records the switch's output of the load as an event (D-052). |
| Q-37 | 2930F BH-DMZ units (preconfigured): exact wording of the `erase startup-config` confirmation, the restart time, and whether the erased unit then asks "Configure the manager credentials" (as new units on WC.16.11.0001 do) or has no manager password. | **Partly answered 2026-11-23:** after the restart the console waits for "Press <Enter> twice" (Speed Sense); the erased unit on WC.16.10.0025 does **not** ask for manager credentials and has no manager password afterwards. The prompts for setting the manager password were supplied the same day (D-058). Still open: the exact erase confirmation wording. |
| Q-38 | FortiGate 101F upgrade v7.2.6 → v7.6.5: does Fortinet's upgrade path require intermediate versions (for example a 7.4 release) for this model? UNDM does not know Fortinet's upgrade paths and installs only the chosen image. | **Partly answered 2026-11-24:** on a factory-default 101F the unit accepted 7.6.5 directly from v7.2.6, installed it and came back (product owner). Fortinet's recommended path for units with a configuration to convert is still not checked. |
| Q-39 | FortiGate 101F firmware by TFTP: after the '#' progress marks, what does the unit print when the fetch ends (and before it restarts)? What does it do when the TFTP server cancels a fetch under way, or when the SSH session closes during one: does it stop or carry on and install? | **Partly answered 2026-11-24:** the fetch starts with "Please wait...", "Connect to tftp server <PC> ..." and '#' marks. When the SSH session that started it closes (UNDM's recovery reconnected about 7 s in, at 5.5 of 101 MB), the unit **carries on**: it finished the fetch, installed the image and restarted. Base restore (v7.6.5): "Connect to TFTP server <PC> ...", "Get file from TFTP server OK.", "File check OK.", then the prompt before the restart (D-064). Still open: the text at the end of an image fetch, how long after the prompt the restart starts, and what the unit does when the TFTP server cancels a fetch (v37 does this). See D-063. |
| Q-40 | FortiGate 101F after the base file: is the configuration save mode automatic? UNDM assumes the default `cfg-save automatic` and does not check it (support matrix note 2). After the site script the GUI's Revisions toolbar showed "Save Changes" with a warning sign. If the base file sets manual or revert, the site configuration would not survive a restart (manual) or would be undone after a timeout (revert). | **Answered 2026-11-24:** `cfg-save : automatic` after the base file (read inside `config global`; at the top of a multi-VDOM unit the command is refused). UNDM now checks it after every load (D-069). What the GUI's "Save Changes" button refers to is still unknown; it is not unsaved configuration. |
| Q-25 | FortiGate wording to confirm on the bench: the questions before `execute restore image/config tftp`, the reply to a bare `end`, informational replies such as on `edit root`, and the output of `execute backup config flash` / `execute revision list config`. | The procedures answer only documented questions and treat unknown replies cautiously; the bench run will show the real text. |
| Q-23 | Exact Black Box model in the other systems: **LE2700A** (answered 2026-11-18). | Web-managed; needs its own investigation. |
| Q-09 | Is the zone used for 2930F testing a test/verification system or a live network? | Decides whether phase B (first write) may use this unit. |
| Q-08 | Can future screenshots be sanitized (system names, hostnames, zone numbers, user names removed) before sharing? | Directive 5 handling rules. |
