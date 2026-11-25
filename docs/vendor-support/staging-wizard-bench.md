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
5. **System page → Logins**: add
   - **approved**: the approved user and password;
   - **black box factory**: user `admin`, tick **No password**;
   - **2930F current**: the preconfigured switch's current manager login;
   - **FortiGate base**: the password the base file sets (as before);
   - the tunnel key, if the site file needs it.
6. **Wizard step 1**, set each device's login:
   - FortiGate: approved (its first login sets it);
   - Black Box: black box factory;
   - both 2930F: approved.
7. **Wizard step 2** (files and firmware):
   - **FortiGate**: tick "New unit", choose 7.6.5, the base file, the site file and the
     tunnel key, and as login after loading **FortiGate base**.
   - **Black Box**: v00.01.01, the team file, and as login after loading **approved**.
   - **2930F**: WC.16.10.0025 (and "also the backup slot" if wanted), the team file, and as
     login after loading **approved**.
8. **Wizard step 3**:
   - cable as shown;
   - give the PC 192.168.1.50/24 and 192.0.2.50/24;
   - close PuTTY;
   - allow incoming UDP 69 on the PC.

## Order of the run (wizard step 4)

### 1. Black Box LIG1014A: firmware, then the team file
Expected:
- Firmware: the switch fetches the image (about 5.5 MB) and restarts by itself about 4–5
  minutes after the command. It answers again after about 30 s, with the same MAC address,
  running v00.01.01.
- Team file: "Import Done!", `reload cold`, back after about 30 s. The login is now the
  approved one, the name is as in the file, and **192 of 192** lines are shown. This answers
  Q-44, which asked whether the two `ip http secure-…` lines survive the upgrade.

### 2. 2930F A, then 2930F B
- **Console setup** (link on its card). For the preconfigured unit:
  - tick **erase first**;
  - choose its current login;
  - type its hostname as shown in the console prompt.

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

## If a step stops
- **The plan says "Needs attention"**: check the device on its console. When it is right,
  open the plan and press **Mark as checked…**. Then make a new plan for that device; the
  run board offers "Make a new plan for this device…".
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
