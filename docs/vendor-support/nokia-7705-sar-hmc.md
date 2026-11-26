# Nokia 7705 SAR-Hmc (the system's LTE modem): staging over the console

Status: **experimental**. UNDM's first access (D-112) is built from the product owner's
console recording and Nokia's public guides. It has run only on UNDM's simulated console,
never on a modem. Loading the modem's configuration is not built yet.

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
  the answer to end. The raw characters at the question are kept as technical details.
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
- UNDM does not log out at the end: the console stays logged in as admin (Q-51).

## Not built yet
- Loading the modem's configuration (today: pasted on the console by hand, then
  `admin save`). Planned as a normal plan (preview, approve, run) that types the file over
  the console and stops at the first refused line; needs the team's files for two zones.
- The modem's file by zone (D-111), once two zones' files prove the rules.
- Reading facts, backups and firmware for this model.

## Open questions
See `docs/REFERENCE_ANALYSIS.md`, Q-49 to Q-53.
