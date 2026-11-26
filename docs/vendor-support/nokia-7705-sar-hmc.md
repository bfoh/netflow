# Nokia 7705 SAR-Hmc (the system's LTE modem): staging over the console

Status: **experimental**. UNDM's first access (D-112) is built from the product owner's
console recording and Nokia's public guides; it passed on a factory unit on 2026-11-26 (third
bench run). Loading the modem's configuration file over its console as a plan (D-116)
passed on the same unit on 2026-11-26: 149 lines in about one minute, all accepted, saved and
verified (Q-58).

## What is known, and from where

### The product owner's console recording (2026-11-26)
A 7705 SAR-Hmc on TiMOS 20.5.R1, staged by hand by the team. Identifiers (the unit's name,
which is its serial number from the factory, and the new password) are not recorded here.

1. At power-on the boot loader lists the boot options file and asks:
   `Hit a key within 3 seconds to change boot parameters...`
   The factory boot options were: `primary-image cf3:/TiMOS-SR-20.5.R1`,
   `primary-config cf3:/config.cfg`, `wait 3`, `persist off`, `console-speed 115200` and two
   `auto-discover` lines (`private.nokia.nsp.primary.nms`, `…secondary.nms`).
2. After a key: `Type "sros" and hit ENTER within 25 seconds to begin changing parameters:`
   (a countdown from 30 seconds: the person typed with 25 left, second bench run)
   → `sros`.
3. The boot menu, question by question:

   | The modem asks | The team answers |
   |---|---|
   | `Press ENTER to begin, or 'flash' to enter firmware update...` | Enter |
   | `Software Image URL:` (after "Press ENTER to keep it.") | Enter |
   | `Config File URL:` (after "…or the word 'none' for no Config URL.") | `none` |
   | "…or press ENTER to keep existing fips configuration" | Enter |
   | `Would you like to keep auto-discovery enabled? (yes/no)` | `no` |
   | `Do you want to overwrite cf3:/bof.cfg with the new settings? (yes/no):` | `no` |

4. The unit starts the image and reaches `Login:`. `admin` with the default password is
   accepted (product owner, 2026-11-26). The prompt is `*A:<name>#`.
5. On the command line, in this order:
   - `admin save config.cfg` (no answer shown in the recording)
   - `exec cf3:/config.cfg` → "Executed 141 lines in 0.2 seconds from file cf3:\config.cfg"
   - `configure system security user "admin" password <new>`; a too simple one is refused:
     `MINOR: SYSTEM #1372 The user password does not meet the system requirement - is too simple`
   - `bof primary-config cf3:\config.cfg`, `show bof`
   - `bof persist on`, `show bof` (now without `auto-discover`)
   - `bof save` → "Writing BOF to cf3:/bof.cfg ... OK" / "Completed."
   - `admin save` → "Writing configuration to cf3:\config.cfg" / "Saving configuration ... OK"
     / "Completed."; the prompt loses its `*`.
   - `show system information` → `System Type : 7705 SAR-Hmc`, `System Version : B-20.5.R1`,
     `Changes Since Last Save: No`, `Management IP Addr : 0.0.0.0/0`.

After that the team pastes the modem's configuration into the prompt.

### The first bench run (2026-11-26, UNDM v84)
The console of a factory unit from power-on, as UNDM received it (identifiers not recorded;
the unit's MAC addresses and flash volume UUID are masked):
1. U-Boot ("Model: Nokia SAR-Hmc Board", "Autoboot in 3 seconds"), then Linux starting
   (about 75 seconds of kernel and service messages), then the TiMOS boot ROM
   ("auto-booting..."), then the boot loader with the boot options listed above.
2. The question is printed again each second as it counts down:
   `Hit a key within 3 seconds to change boot parameters...   Hit a key within 2 seconds…
   Hit a key within 1 second…` (three spaces between them in the cleaned transcript).
3. With no key, it loads the image (`Loading image cf3:\TiMOS-SR-20.5.R1\both.tim`).

Timing: by the unit's own clock lines, the boot loader started about 2.5 minutes after the
kernel. UNDM v84 did not answer the question (D-112, fixed in v85).

### The second bench run (2026-11-26, UNDM v85): raw characters
From the run's technical details (control characters written out):
- The 3-second question: `\rHit a key within 3 seconds to change boot parameters...   \b\b\b`.
- After Enter: `\r\r\n`, then the sros question as a one-line input field:
  `\rType "sros" and hit ENTER within 30 seconds to begin changing parameters:` followed by
  six spaces and five backspaces (cursor on the empty field).
- After the first typed letter the whole line is redrawn:
  `\rType "sros" … parameters: s` followed by five spaces and five backspaces.
- The countdown starts at **30 seconds** (the recording's "25" was the count when the
  person typed).
- UNDM v85 took the redraw for a second question and stopped (fixed in v86).

### The third bench run (2026-11-26, UNDM v86): the first access worked
All of it, on the factory unit:
- Enter at the 3-second question, `sros` typed key by key into the redrawn field (Enter
  once it showed; the "29 seconds" redraw ignored), then the boot menu answers.
- The other boot-menu questions echo plainly (`Config File URL: none`, `(yes/no) no`),
  with `\r\r\n` line endings (Q-56).
- Started without its configuration, the unit printed "CRITICAL: CLI #1001 Cannot locate
  the configuration file - Using default configuration values." and "MAJOR: CLI #1008 The
  SNMP daemon is disabled…" before `Login:`, then accepted `admin`/`admin`.
- `environment no more` printed nothing.
- `admin save config.cfg` printed "Writing configuration to cf3:\config.cfg", "Saving
  configuration ... OK", "Completed." (Q-52).
- `exec cf3:/config.cfg` executed 128 lines.
- The new password, `bof primary-config`, `show bof`, `bof persist on`, `bof save` and
  `admin save` all succeeded.
- `show system information` reported 7705 SAR-Hmc, B-20.5.R1, "Changes Since Last Save: No".
- Its `SNMP Engine ID` ends with a MAC address of the unit; UNDM masks it in shared text
  since v87.

### Nokia's public documentation (read 2026-11-26 on documentation.nokia.com)
7705 SAR Basic System Configuration Guide 26.4.R1 (generic to the 7705 SAR family) unless
noted. Quotes are Nokia's words.

| Fact | Source and quote |
|---|---|
| Console: 115200, 8 data bits, no parity, 1 stop bit, no flow control | "Boot options", table: "Baud rate 115 200", "Data bits 8", "Parity None", "Stop bits 1", "Flow control None" |
| Default login | "Boot options": "The default login is admin. The default password is admin." |
| The asterisk in the prompt | "CLI usage": "a "*" appears in the prompt string (*A:NOK-1), indicating that the changes have not been saved. When an admin save command is executed, the "*" disappears." |
| Factory name | "System management": "The default system name is set to the chassis serial number which is read from the backplane EEPROM." |
| Paging | "CLI usage": "[no] more … Default more"; "Press any key to continue (Q to quit)"; "The no form of the command displays the output all at once."; the setting is for "a single CLI session" |
| Message formats | "CLI usage": "Error: Bad command."; System Management Guide: `MINOR: CLI User "testuserA" already exists - use overwrite flag.`; "System management": `MAJOR: CLI #1009 An error occurred while processing a CLI command`, "CRITICAL: CLI #1002 An error occurred while processing the configuration file." |
| Boot menu wording | "Boot options": "Hit a key within 3 seconds to change boot parms..."; "Press ENTER to keep it, or the word 'none' for no Config URL."; "Do you want to overwrite cf3:/bof.cfg with the new settings? (yes/no):" |
| A boot menu password can exist | "Boot options": "editing of the BOF during a boot process is allowed only if the password is entered correctly … If the password is not entered correctly within 30 s, the node reboots" |
| No address from the factory | "Boot options": "Default: no address – there are no IP addresses assigned to CSM Management ports" |
| `exec` | "CLI usage": "executes the contents of a text file as if they were CLI commands entered at the console"; "-syntax performs a syntax check of the file without executing the commands" |
| Lockout | System Management Guide, "Security": default "attempts 3 time 5 lockout 10" |

7705 SAR-Hm and SAR-Hmc Main Configuration Guide 26.3.R1, "Basic system configuration":

| Fact | Quote |
|---|---|
| Factory boot options | "The system ships from the factory with the BOF configured with an empty primary-config, and with auto-discover enabled." |
| A unique factory password on some variants | "For those variants of the 7705 SAR-Hm series node with a unique factory-set password which must be changed at first login, the new password must match the password expected by the NSP NFM-P…" |
| Ending auto-discovery by command | "ADP can be disabled manually by executing the bof no auto-discover command and saving the BOF."; at login: "Do you wish to terminate Auto-Discovery (y/n?)"; "tools# perform auto-boot terminate" |

Why the factory login fails is **not proven**. The guide's "unique factory-set password"
fits; so does the factory configuration file. Nokia documents no procedure called password
recovery for this family; the team's procedure combines documented boot-menu steps.

## What UNDM does (first access, Console setup)
`undm.provisioning.sros_sar`, run from **Console setup** for a device of this model.

- It is a console setup of a factory unit, so it uses the safeguards of that exception
  (D-025): an exact preview, the typed device name, the real-device switch, a factory check,
  a read-back before saving, and an audit record.
- The person presses Run, **then switches the modem off and on**. UNDM waits up to 10
  minutes for the 3-second question (about 2.5 minutes after power-on) and presses **Enter**
  as soon as the sentence arrives, as the team does.
- Questions and the login prompts are found wherever they appear in the output, whatever
  follows them (control characters are dropped and counted); command-line prompts wait for
  the answer to end. The raw characters at each question are kept as technical details.
- A question's line redrawn (same line, after a key or each second of a countdown) is not
  a new question. The same question after a line break means the answer was not taken:
  UNDM stops.
- Typed answers go one key at a time; Enter follows only when the modem shows the answer.
- Before sending a key UNDM reads the boot options the modem lists:
  - no "Nokia 7705 SAR" in the start-up text: no key, nothing changed;
  - no `auto-discover` line: not a factory unit. No key is sent. If it then accepts this
    device's login, the run ends "already done"; otherwise it is refused. Nothing changes.
- It answers only the questions of the table above, in that order. Any other question (a
  boot menu password, for example) ends the run with the modem's own words. The boot menu
  is never told to write the boot options file.
- After the login it sends `environment no more` (Nokia's documented session setting; a
  pager question is answered with a key if it still appears), then the recorded commands in
  the recorded order.
- The admin password is the password of the device's login in UNDM. The login's user name
  must be `admin`. Because the password is typed on a command line, it must be plain ASCII
  without spaces or quotation marks. It is masked in the transcript in both directions (the
  modem echoes the line) and never stored in the audit.
- A line starting `MINOR:`, `MAJOR:`, `CRITICAL:` or `Error:` after a command ends the run.
- `bof save` and `admin save` are sent only after `show bof` reads back as intended
  (the configuration file set, persist on, no auto-discovery), and each must answer with
  its recorded confirmation.
- If the run stops before `bof save`, the boot options file is unchanged: switching the
  modem off and on returns it to its factory start. One difference remains in that case:
  `admin save config.cfg` has already replaced the factory configuration file with the
  default configuration (as in the team's procedure).
- At the end UNDM sends `logout` and checks that the login prompt appears. Nokia documents
  it: "When the logout command is issued from the console, the login prompt is displayed"
  (Basic System Configuration Guide, CLI usage). A missing prompt is reported, not a
  failure; everything is saved by then.

## Its configuration file (D-114)
The team's file for each system is generated from a template:
- by zone and system: `Zone` + 3 digits, the system letter + 3 digits after the site-type
  prefix, 130.zone and 10.(127+zone);
- the admin password is a secret slot, filled from the modem's login only when the file is
  downloaded from Stage a system;
- checked on two systems in two zones: byte for byte.

## Loading its configuration file (D-116)
A plan in Stage a system, step 4, after the first access, over the console port the first
access saved (Edit on the device page changes it):
- making the plan logs in and reads `admin display-config`; nothing is changed;
- the run sends the file's configuration lines one at a time, each after the previous one's
  prompt, and stops at the first line answered with `MINOR:`, `MAJOR:`, `CRITICAL:` or
  `Error:`; comments, blank lines, `echo` lines and `admin save` are not sent;
- the admin password comes from the modem's login (masked in the transcript);
- `admin save` must answer "Completed."; then UNDM logs in again and checks the system name
  and "Changes Since Last Save: No";
- a load that stopped is not saved: switched off and on, the modem starts with its saved
  configuration.

## A console window (D-118)
Device menu → **Open console window**: a terminal on the modem's saved console port at 115200 (PuTTY when installed, else pySerial's terminal). UNDM types nothing into it; close it before UNDM uses the port again.

## Not built yet
- Firmware for this model.

## Open questions
See `docs/REFERENCE_ANALYSIS.md`, Q-49 to Q-53, Q-55, Q-56 and Q-58.
