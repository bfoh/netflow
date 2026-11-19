# FortiGate 101F — staging with the team's two configuration files

Source: two sample files supplied by the product owner on 2026-11-18 and studied offline.
The files themselves are **not** in this repository and never will be (they contain
passwords, keys and site addressing). Tests use synthetic files in the same layout.

## How it is done by hand today
1. **Base file** (common to all sites, e.g. `base-vNN.conf`): uploaded in the FortiGate GUI
   (configuration restore). Afterwards a configuration revision is saved, named after the
   file without its extension (`base-vNN`).
2. **Site file** (one per site, e.g. `<site>-<role>-vNN.N.cfg`): opened in a text
   editor and pasted into the CLI console of the GUI. Afterwards a revision is saved, named
   after that file.

## What the files are (facts read from the samples)
| | Base file | Site file |
|---|---|---|
| Kind | **Full configuration backup**: first line `#config-version=FG101F-7.2.7-FW-build1577-…:opmode=0:vdom=1:…` | **CLI script**: only `config / edit / set / unset / next / end` and `#` comments |
| Size | about 12,800 lines | about 1,800 lines (about 1,780 statements) |
| Written for | FortiOS **7.2.7**, platform code FG101F | header comment: load on new software **7.6.5**; "tuned for 7.6.5" |
| VDOMs | switches the unit to **multi-VDOM** mode (`config global`, `config vdom / edit root`) | uses `config global … end` then `config vdom / edit root … next / end`, so it needs multi-VDOM mode to exist already |
| Management access afterwards | `mgmt` port keeps the factory address 192.168.1.99 with ping/https/ssh; every other port down; one administrator `admin` | does not touch the `mgmt` port; limits `admin` to trusted networks, one of which is the bench network 192.168.1.0/24; enables SCP for admins |
| Things that matter to automation | replaces everything incl. the admin password; unit restarts | starts with a bare `end` whose error is to be ignored (stated in the file); **changes the hostname** (prompt changes mid-run); comment lines inside blocks; irregular indentation; one line of 477 characters |
| Secrets inside | encrypted passwords and private keys (certificates) | one pre-shared key setting in clear text — in the sample it holds **placeholder text, not a real key**, so the real key is evidently set separately (Q-22); SNMP community |
| Says about order | — | "The base configuration shall be restored … prior to the deployment of this script" |

UNDM's offline check (`drivers/fortinet/config_files.py`) reports both sample files as
well-formed (every block closed) and classifies them as above.

## What follows for UNDM
- The two files need **two different mechanisms**. A full backup is restored as a whole;
  a script is sent statement by statement. Mixing them up is refused (D-032).
- **Base restore**: FortiOS documentation gives `execute restore config tftp <file>
  <server>` (argument list differs between releases) and says the unit restarts
  afterwards. Vendor guidance found: restoring a backup is supported on the **same model
  and firmware version** it was written on. The base file is a 7.2.7 file, which is what a
  new unit runs — so the natural order is base restore **before** the firmware upgrade.
  To be confirmed (Q-19).
- **Site script**: sent over SSH one statement at a time, reading the reply to each:
  `#` lines skipped; the leading `end` allowed to fail; any other error, or any question
  from the firewall, **stops the run** at that line with the firewall's text (pasting by
  hand carries on after an error and can apply later lines in the wrong block). The prompt
  is matched in a way that survives the hostname change and the `(global)` / `(root)` /
  block contexts.
- **Revisions**: after each file, save a revision named after the file. FortiOS help
  lists `execute backup config flash <comment>` for this; to verify on 7.2.7 and 7.6.5.
- **Credentials**: factory default (`admin`, empty) → the password set at the forced first
  login → whatever the base file sets. UNDM needs to know which stored credential is valid
  after each step (Q-20). No password is ever written into UNDM's files.
- **Confidentiality**: imported files are kept in UNDM's database on the staging PC. The
  file report never shows secret values; audit entries carry only name, size and hash.

## Sequence for one FortiGate (order confirmed 2026-11-19, D-034)
| # | Step | Mechanism | Status |
|---|---|---|---|
| 1 | Factory-default unit at 192.168.1.99: forced password change to the approved one | browser, by hand | manual for now (Q-24) |
| 2 | Read model, serial, firmware | SSH | built (experimental) |
| 3 | Upgrade 7.2.7 → 7.6.5 directly (D-028); wait; verify the version | firmware job, TFTP | **built (experimental)** |
| 4 | Restore the base file (it carries the approved admin password); wait; reconnect; check hostname, multi-VDOM, version; refuse a backup from another model | configuration job, replace mode, TFTP | **built (experimental)** |
| 5 | Save revision `<base file name>` | after verification | **built**, command unverified |
| 6 | Site script statement by statement, CEN tunnel key from the credential store; stop at the first error-looking reply | configuration job, merge mode | **built (experimental)** |
| 7 | Save revision `<site file name>` | after verification | **built**, command unverified |

Bench checklist: `fortigate-101f-bench.md`.

## Built so far
- Offline recognition of both file kinds at import; a full backup can only be restored, a
  script only sent statement by statement; a script with unclosed blocks is refused.
- Steps 2–7 above as experimental procedures, tested end to end against a fake FortiGate
  (synthetic wording, real TFTP transfers). Not yet run on a FortiGate.
- The simulated FortiGate can rehearse the site-file plan, including the key mapping
  (it only ever holds `ENC <simulated>`).

## Sources (public documentation; extracts via search, not verified on a unit)
- Fortinet administration guide, "Configuration backups":
  <https://docs.fortinet.com/document/fortigate/7.0.19/administration-guide/702257>
- FortiOS 7.2 new features (restore command arguments from 7.2.4):
  <https://docs.fortinet.com/document/fortigate/7.2.0/new-features/787595>
- FortiOS CLI reference, `execute restore`:
  <https://docs.fortinet.com/document/fortigate/7.2.13/cli-reference/150608926/execute-restore>
- FortiOS 5.2 help, backing up with the CLI (`execute backup config flash <comment>`):
  <https://help.fortinet.com/fos50hlp/52/FortiOS%205.2%20Help/basic_setup.025.78.html>
- Fortinet community, restoring a configuration file written by a lower version:
  <https://community.fortinet.com/t5/FortiGate/Technical-Tip-Restoring-a-configuration-file-with-a-lower/ta-p/335933>
