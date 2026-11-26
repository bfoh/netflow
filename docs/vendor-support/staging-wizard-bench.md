# Bench run: one system through "Stage a system" (wizard)

First real run of the wizard (D-085) on a full system. The units for this run:
- FortiGate 101F, factory default
- Black Box LIG1014A, factory default
- Two Aruba 2930F, at least one preconfigured with a known password that is not the
  approved one

Everything below uses placeholders. Never type real names into this file.

After **each device**, open **Bench log…** (system page, or the wizard's Report step),
read it, and send it. It replaces screenshots: it lists every step and what the devices
printed, with addresses, serials, names and logins masked (D-090).

## Before you start (once)
1. **UNDM v60 installed.** Run `backend\.venv\Scripts\python.exe undm_update_v60.py` in the
   `undm` folder, then restart the backend.
2. **Settings → Safety**:
   - turn **Real-device changes** and **Firmware changes** on;
   - turn **A second person approves firmware plans** off if you stage alone.
3. **Firmware** page: the approved images are there:
   - FortiGate 7.6.5
   - LIG1014A v00.01.01
   - 2930F WC.16.10.0025
4. **Stage a system → A new system**: give it a placeholder name. Then **Real devices on the
   bench**, and **Add it** for each of the four roles. Change an address on the device
   page if this bench differs.
5. **Settings → For all systems** (since v78, once for every system, D-105):
   - **Logins for all systems**: approved; black box factory (user `admin`, tick **No
     password**); aruba factory / 2930F current; FortiGate base; the tunnel key.
   - **Default logins per device**: FortiGate: approved, after loading FortiGate base,
     tunnel key; Black Box: black box factory, after loading approved; 2930F: approved, login
     it has now aruba factory.
   - **HTTPS certificate (Aruba 2930F)**: the team's answers.
6. **Wizard step 1**: **Add it** gives each new device its default login; for devices added
   before, press **Use the default logins**. A device that differs can get another login
   there.
7. **Wizard step 2** (files and firmware):
   - **FortiGate**: tick "New unit", choose 7.6.5, the base file, the site file and the
     tunnel key, and as login after loading **FortiGate base**.
   - **Black Box**: v00.01.01 (with "also the backup slot": both banks, since v81), the team file, and as login after loading **approved**.
   - **FortiGate license** (optional, since v81): choose the file if the project lead sent it; otherwise load it later from the FortiGate's menu (⋯ → Load license…).
   - **2930F**: WC.16.10.0025 (and "also the backup slot" if wanted), the team file, and as
     login after loading **approved**.
8. **Wizard step 3** (Bench check): cable as in the table below; give the PC
   192.168.1.50/24 and 192.0.2.50/24; close PuTTY; allow incoming UDP 69 on the PC.

## Files from the team's templates (since v82, D-111)
Once, in **Settings → For all systems → Configuration templates**, import the team's
current files (one zone's file each; add the same file for a second zone to have it
checked) and the FortiGate base file. Then, for each system:
1. In wizard step 1, check the **Zone** (read from the system name) and press **Save zone**.
2. In step 2, press **Generate the files for zone N**: the four devices get their files and
   they are chosen.
3. If the team's own files for that zone are already on the devices, press **Compare with
   the devices' files**: every line must be identical.
4. To keep the files or hand them on, press **Download the files for zone N**: one zip with
   the team's file names, byte for byte as the team writes them (a byte comparison such as
   `fc /b` shows no difference). Templates imported before v83 were kept with Unix line
   endings: import them once again to have the team's formatting.

## Nokia modem (7705 SAR-Hmc): first access (since v84, D-112, experimental)
For a modem straight from the factory, which refuses the default login. UNDM does what the
team does by hand on the console; it has not yet run on a modem, so read the transcript of
the first run and send it back.
1. In **Stage a system**, step 1, add the Nokia modem and choose **its login**: the approved
   login with user name `admin`. Its password becomes the modem's admin password (the modem
   refuses one it finds too simple).
2. Connect the console cable (115200). Close PuTTY.
3. Step 4, the modem's card: **Open console setup**. Choose the COM port, press
   **Run first access…**, type the device name, press **Run first access**.
4. **Then switch the modem off and on.** About 2.5 minutes later the modem asks for a key
   for 3 seconds; UNDM presses Enter, answers the boot menu (configuration file `none`,
   auto-discovery `no`, boot options file not written), waits for the start (2–3 minutes),
   logs in, sets the password and saves. While it runs, the dialog shows what UNDM sees
   (stage, time, bytes received, last line). The whole run takes up to about 15 minutes.
5. The result says "First access done" with the modem's own name, type and software.
   UNDM logs out at the end (the modem shows its login prompt again).
6. Its configuration is still pasted on the console by hand, then `admin save`.

If it stops:
- "Nothing arrived from the console": the modem was not switched off and on after Run, or
  the COM port or speed is wrong. Nothing was changed.
- "start-up text arrived, but … question …": send the transcript with its technical details
  (Copy sanitized transcript includes them). Nothing was changed.
- "started normally instead of asking to type sros": the key came too late. Nothing was
  changed; run again.
- "asked … where UNDM expected": the modem asked something UNDM has no answer for (a boot
  menu password, for example). Send the transcript.
- "asked again …" or "did not show it, so UNDM did not press Enter": the modem did not take
  a typed answer. Send the transcript with its technical details.
- After any stop in the boot menu the modem waits there: switch it off and on before the
  next run (press Run first).
- "refused the new admin password": choose a login with a longer, less simple password;
  switch the modem off and on, then run again.

## Nokia modem: its configuration file (since v90, D-116; passed on hardware 2026-11-26)
After the first access, with the console cable still on the same COM port:
1. Step 1: set the zone and system (B007) of the system; step 2: **Generate the files**
   gives the modem its configuration file (its password comes from the modem's login).
2. Step 4, the modem's card: **Make the plan** (it logs in over the console and reads the
   configuration; nothing changes), **Approve all steps**, **Run**. The lines go one at a
   time; about 1–2 minutes.
3. Success: "N line(s) accepted", "saved ('admin save': Completed.)", then "logged in again
   with its login; system name …; nothing unsaved". The card shows **Staged**.
4. If it stops: the event names the file line and the modem's words; nothing was saved.
   Switch the modem off and on (it starts with its saved configuration), then send the
   plan's events (Bench log) and make a new plan once the line is understood.
- "No login prompt from the modem on COMx": the cable is on another port (Edit on the device
  page), or the modem is still starting (about 3 minutes after power-on).
- "COMx is in use by another console session": close Console setup or wait for the other
  plan, then try again.
- A modem that already had its first access is left alone ("already done" or "refused").

## The modem's file and the BBU's SCF (since v88, D-114)
Once, in **Settings → For all systems**:
1. **Configuration templates → LTE modem → Import…**: one system's modem file. Add another
   system's and zone's file as the check; it should say "byte for byte".
2. **Flexi BBU site configuration file (SCF) → Import…**: one system's SCF, with another
   system's as the check. A line written by hand (a site label) is shown: press **Keep it
   anyway** if it differs on purpose.
3. **PCI table → Import the table…**: the team's PCI workbook.

For each system:
1. In wizard step 1, check the **System** (read from the name, e.g. B007) next to the zone.
   The PCIs of its cells are shown, and **Save**.
2. Choose the modem's login (step 1).
3. In step 2, press **Download the files for zone N · B…**. The zip holds every team file
   for the system, with the modem's file (its password from the modem's login) and the
   BBU's SCF (its name stamped with the time).

## Cabling (all four at once)
One small switch, connected to nothing else, one cable per device (two would make a loop):

| Device | Cable to the small switch | Address now | After its file |
|---|---|---|---|
| PC | wired port | 192.168.1.50/24 and 192.0.2.50/24 on the same adapter | same |
| FortiGate 101F | MGMT port | 192.168.1.99 | same (the base file keeps it) |
| Black Box LIG1014A | port 1/3 (the file keeps management on that port only) | 192.0.2.1 | same |
| 2930F A | port 2, plugged in after its console setup | 192.168.1.1 | same |
| 2930F B | port 3, plugged in after its console setup | 192.168.1.2 (temporary) | **192.168.1.1** |

The USB console cable goes from the PC to a 2930F's console port for its console setup; one
cable is enough, moved from A to B. Plug a 2930F's port into the small switch only after its
console setup: a preconfigured unit may still use an address another device has.

**Both 2930F end at 192.168.1.1.** Once B's file loads, A and B would share the address. B's
plan has a step "Make room". Since v79 (D-107, experimental) it switches off A's management
port (port 2) in A's running configuration only, nothing saved, and checks that 192.168.1.1
goes quiet. A answers again after its next power-on. **Switch A off and on before it
leaves the bench.** Stage A first, then run B's plan; no cable to unplug.

The spare addresses of v68–v78 could not work (2026-11-26):
- the 2930F refuses a second address in its own network;
- its team file accepts management only from 192.168.1.0/24 (`ip authorized-managers`).

If the step stops, it says whether A was left as it was. Otherwise switch A off and on.
Either way, unplug A from the small switch as before and make a new plan for B: the step
finds nothing at 192.168.1.1 and moves nothing. A device UNDM cannot take off its address
(or a step that is absent) still means: unplug A before B's plan; the v61 check stops B's
file step otherwise.

## Order of the run (wizard step 4)

### 1. Black Box LIG1014A: firmware, then the team file
Expected:
- Firmware: the switch fetches the image (about 5.5 MB) and restarts by itself about 4–5
  minutes after the command. It answers again after about 30 s, with the same MAC address,
  running v00.01.01.
- Team file: "Import Done!", `reload cold`, back after about 30 s. The login is now the
  approved one, the name is as in the file, and **192 of 192** lines are shown. This answers
  Q-44, which asked whether the two `ip http secure-…` lines survive the upgrade.

### 2. 2930F A, then unplug A, then 2930F B
Run A's plan to the end. When A shows **Staged**, unplug A from the small switch, then run B's
plan (its file moves B to A's address). The Black Box and the FortiGate can run alongside.
- **Console setup** (link on its card). For the preconfigured unit:
  - tick **erase first**;
  - choose its current login;
  - press **Read its name from the console** (it changes nothing), then tick "Yes, erase
    <name>". No name to type and no PuTTY (D-095).

  Expected: the erase, then a restart (about 1–2 minutes), "Press Enter twice", then the
  bootstrap. The log records the switch's own words for the erase confirmation (Q-37).
- **Plan: firmware → team file.** Expected:
  - Firmware: the switch pulls the image, restarts, runs WC.16.10.0025.
  - File: certificate, load, restart. Back with the approved login on the file's
    address.

### 3. FortiGate 101F: first login → firmware → base → site (one staging plan)
- **Making the plan** reads the factory unit's first-login text and records it in the log.
  This is Q-41, never seen on hardware. If UNDM does not know a question, the step stops
  and the log shows the text: send it.
- **Firmware** (corrected procedure, D-063): "Please wait...", "Connect to tftp server…",
  `#` marks, then the restart. The log records the unit's last words before the restart
  (Q-39).
- **Base**: "Get file from TFTP server OK.", "File check OK.", restart, then the forced
  password change, answered by UNDM (as on 2026-11-24).
- **Site**: statement by statement; "Command fail … -61" on the first `end` is expected.
  Revisions are saved after each file.

## End of the run (wizard step 5, since v80, D-108)
The Report step has a checklist. UNDM ticks what it can see: every device staged, every
switch back at its own address, and the safety switches off (**Turn them off**). Switch
A, whose port Make room switched off: switch it off and on, unplugged from the bench switch
(B now uses 192.168.1.1), then press **It was switched off and on**. If the safety item says
"Fixed on in backend\.env", delete the lines `UNDM_ENABLE_REAL_DEVICE_WRITES` and
`UNDM_ENABLE_REAL_DEVICE_FIRMWARE` from `backend\.env` once and restart the backend. You tick the rest: license loaded or not needed, report saved, backups
downloaded, devices powered off and labelled. Then press **Finish staging**: the system
shows **Staged <date>** everywhere. A new plan on one of its devices reopens it.

## If a step stops
- **The plan says "Needs attention"**: check the device on its console. When it is right,
  open the plan and press **Mark as checked…**. Then make a new plan for that device; the
  run board offers "Make a new plan for this device…".
- **"The device refused the login"** when making or running a plan: the unit has another
  password than the login chosen for it in UNDM, usually because its file was loaded before.
  Choose the login the file sets as "Its login" (step 1) and make the plan again.
- **The device answers after its file but refuses the login** (2026-11-25, Black Box): the
  plan had no login after loading, so UNDM kept the factory login while the file had set the
  approved password. Since v66 the wizard requires it for a real Black Box and FortiGate. To
  recover: set the device's "Its login" to the login the file set (Test should connect), set
  "Login after loading" to it as well, and make a new plan; the firmware step is skipped
  (already running) and the file is loaded and checked again.
- **Console setup: "The switch rejected 'ip address …': … overlapping network … already
  exists"** (2026-11-25): VLAN 1 got an address by DHCP because a port of the switch was
  cabled to the bench network during the setup. Unplug every network cable from the switch,
  switch it off and on (nothing was saved), run the console setup again, and plug its
  management port in only after it.
- **Console setup: "This switch has no port …"** (2026-11-25): the port in "Management
  settings" is wrong. Since v76 it starts at the role's port (A: 2, B: 3); correct it and run
  again. Nothing was changed.
- **A new 2930F runs a newer release than the approved one** (seen: WC.16.11.0001): tick
  the approved downgrade option in its firmware step.
- **Any other stop**: send the bench log. Do not retry more than once before sending it.

## What this run answers
| Question | Answered by |
|---|---|
| Q-37 | The 2930F erase confirmation wording |
| Q-39 | The end of a FortiGate image fetch |
| Q-41 | The FortiGate first-login text |
| Q-44 | The Black Box `ip http` lines after the upgrade |

It is also the first hardware run of:
- the first login as a plan;
- the generic staging plan (four steps, one approval);
- the wizard as a whole.

## Nokia Flexi BBU: guided steps (since v93, D-117)
Done by hand in its portal; UNDM checks, hands out the files and records:
1. **Before.**
   - Upload the software package once on the Firmware page (platform "Nokia Flexi BBU
     (SBTS)") with its SHA-256 from `certutil -hashfile <file> SHA256`, then approve it.
   - Import the SCF template and the PCI table (Settings → For all systems).
2. **Step 1.** Add the BBU (no login). **Step 2.** Generate (it gets its SCF) and choose the
   software package.
3. **Cabling.** The LMP cable goes to the PC (or the small switch). Add 192.168.255.126/24 to
   that adapter. Step 3 Test checks port 443.
4. **Step 4, the BBU's card.**
   - **Open its portal**, then **Check now**.
   - For the software and the SCF: use UNDM's download, do it in the portal, write where and
     what it showed, then **Done**.
   - Last, note the state the portal shows.
5. **Undo** clears a step and those after it, if one was recorded by mistake.
