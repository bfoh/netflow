# Aruba 2930F — console bootstrap, bench validation

Procedure under test: `undm.provisioning.aos_switch` (console bootstrap). Status:
**experimental; first complete run on hardware 2026-11-19** (one spare 2930F, JL260A,
WC.16.11.0001, new unit). One unit and one software release do not make it accepted:
see the results log.

## Use only
- A **spare** 2930F in **factory-default** state, on a bench that is not connected to any
  live network. Not a switch that belongs to a running system.

## Before you start
- [ ] Console cable from the laptop to the switch's console port; note the COM port
      (Device Manager → Ports). Speed: **9600** (the team's setting; UNDM's default).
- [ ] **Close PuTTY** (and any other terminal program): only one program can use a COM port.
- [ ] `backend\.env` contains `UNDM_ENABLE_REAL_DEVICE_WRITES=true`; backend restarted;
      the header shows "Real-device changes ON".
- [ ] In UNDM the switch exists as a **real lab device** (driver `ssh.aruba.aos_switch`).
- [ ] **New units** ask "Configure the manager credentials :", "Username:", "Password:",
      "Re-enter the new password:" on the console before anything else (seen 2026-11-19).
      Attach the **approved login** (user `manager` + approved password) to the device in
      UNDM before the bootstrap: UNDM sets exactly that login, answering only the username
      and the two password prompts, and uses it from then on. Without it the bootstrap stops
      at that point and sends nothing. If you already set the credentials by hand, use the
      approved password: the bootstrap then logs in with it normally.

## Preconfigured units (BH-DMZ): erase first (D-057)
- [ ] Save the preconfigured login once in the project's **Credentials** (e.g. "preconfigured
      login"); the approved login stays attached to the device.
- [ ] Read the switch's current hostname from its console prompt (the name before `>` or `#`).
- [ ] Run console bootstrap… → tick **This switch is preconfigured … erase its configuration
      first** → choose **Its current login** → type the hostname → type the device name →
      **Erase and bootstrap**. Expected: transcript with the configuration before the erase,
      `erase startup-config`, the confirmation answered "y", the restart, then the new-unit
      credential prompts (or a plain login) and the usual bootstrap; badge "erased … first".
- [ ] Send back the sanitized transcript: the erase confirmation wording and restart time are
      not yet known (Q-37).

## Steps
| # | Step | Expected |
|---|---|---|
| 1 | Device page → **Console bootstrap** | Provisioning Center opens for this switch |
| 2 | Enter VLAN 222, name `OOBM_VLAN`, the OOBM port (2 or 3), address (192.168.1.1/24, or 192.168.1.2/24 for the second switch) → **Save settings** → **Preview commands** | Exactly the commands you type by hand, ending with `write memory` |
| 3 | Choose the COM port and speed → **Run console bootstrap…** → type the device name → **Run bootstrap** | "Bootstrap complete", badges "read back and verified" and "saved (write memory)" |
| 4 | On the switch console (reopen PuTTY): `show running-config` | VLAN 222 with the port untagged and the address |
| 5 | Connect the laptop to the OOBM port (adapter address in 192.168.1.0/24) → device page → **Test connection** | Success, or a message that tells us how a factory-default switch answers SSH |
| 6 | Run the bootstrap **again** | "Already bootstrapped — nothing was changed" |

## Please send back
- **Download sanitized transcript** from the result (also when it fails — a failure
  transcript is the most useful one).
- The COM speed that worked, and anything on the console that looked different from the
  preview.

## What may differ on real hardware (unknown until this test)
Console wake-up behaviour; the banner and "Press any key" text; the default
hostname in the prompt; wording of error messages; whether SSH accepts the empty default
password. The procedure stops at the first unexpected response and saves nothing unless
the configuration read back matches, so a mismatch leaves the switch unsaved: restart it
(or factory-reset it with your usual method) to return to the starting state.

## Results log
| Date | Unit | Result | Notes |
|---|---|---|---|
| 2026-11-19 | spare 2930F, new unit | stopped, nothing changed | The console had been left at "Re-enter the new password:" from a manual try. UNDM's wake-up Enter answered it with an empty password; the switch replied "Password cannot be empty. / Operation aborted. / Session Terminated, unable to login." Fixed the same day: the bootstrap now starts the login again after that message (D-046). |
| 2026-11-19 | same unit, run 2 | stopped at the first new-password prompt, nothing answered | The unit identified itself (JL260A 2930F-48G-4SFP, WC.16.11.0001). After the echoed username the console placed "Password:" with cursor control codes, so without them the text read "managerPassword:" and UNDM, expecting the prompt on a new line, did not recognise it. Fixed: "Password:" is recognised at the end of the output; an unexpected question is now quoted in the message. |
| 2026-11-19 | same unit, run 2 (transcript end) | root cause found | The transcript showed `manager`, a new line, then `ESC[24;18H` and `Password:`: the serial read had ended between ESC and `[24;18H`, so the code was not removed and the prompt did not start the line. Fixed in the console reader: an escape code cut by a read is joined with the next read; next-line and insert-line codes become line breaks (as Netmiko does for this switch family). |
| 2026-11-19 | same unit, run 3 | **bootstrap complete**: read back and verified, saved | The console was again left at a pending new-password question from the previous run; the wake-up Enter answered it, the switch replied "Session Terminated, unable to login." and UNDM started the login again (D-046, now seen working on hardware). Then: banner, "Configure the manager credentials :", username, "Password:", "Re-enter the new password:" answered with the attached login, "You have never previously logged in.", prompt `Aruba-2930F-48G-4SFP#`. The factory-default check passed (only VLAN 1), the VLAN commands were accepted without messages, the read-back matched (VLAN 1 now lists `no untagged <port>`), `write memory` returned to the prompt without text. Network reachability not yet checked (laptop not yet on the OOBM port). Still to do on this unit: steps 5 and 6. |
| 2026-11-19 | same unit, step 5 | **passed** | Laptop on the OOBM port with an address in the same /24: ping answered; **Test connection** succeeded over SSH ("SSH session established (ArubaOS-Switch)") with the login set at first login. So this unit, after the bootstrap, accepts SSH without further commands. Step 6 (re-run) still to do. |
| 2026-11-23 | BH-DMZ unit (preconfigured, WC.16.10.0025), erase-first run 1 | stopped before the erase, nothing changed | This time the console asked Username/Password at login (earlier: operator prompt without login); the preconfigured login worked and reached the manager prompt with a login banner. The typed hostname did not match the prompt exactly, so UNDM stopped as designed. The comparison now ignores upper/lower case and the field explains what to type. |
| 2026-11-23 | same BH-DMZ unit, erase-first run 2 | **erased**; bootstrap then waited for the console | Hostname confirmed; `erase startup-config` confirmed; the switch restarted (heard on the bench). Its console stayed silent until a key was pressed, and UNDM was not pressing any, so the run waited its 7-minute limit. Fixed: Enter every 10 s after the erase. Erase wording and restart time still to be read from a transcript (Q-37). |
| 2026-11-23 | same BH-DMZ unit, audit log | erased; bootstrapped; **no manager password** | Boot output after the erase ended with "Waiting for Speed Sense.  Press <Enter> twice to continue." (now recognised: UNDM presses Enter twice). The erased unit (WC.16.10.0025) did **not** ask "Configure the manager credentials" (the new unit on WC.16.11.0001 did), so the bootstrap left it without a manager password and SSH with the approved login failed. The bootstrap now flags this ("no manager password") with what to do. |
| 2026-11-23 | same BH-DMZ unit, console by hand | manager password set | `configure`, `password manager`, "New password for manager:", "Re-enter the new password for manager:" (echo `*`), five notices (DHCP image/config download, TR-69, TFTP server, autorun disabled once a password is set), `write memory` in configuration mode. UNDM's bootstrap now performs exactly this for switches without a password (D-058). |
| 2026-11-23 | same BH-DMZ unit, made preconfigured again, erase-first run with v32 | **everything worked** (product owner) | One run: login with the current login, hostname confirmed, erase, restart with "Speed Sense" answered, approved manager password set by UNDM (D-058), VLAN 222 on port 2, read back and saved; Test connection with the approved login succeeded. The erase confirmation wording was not sent back (Q-37). |
| 2026-11-19 | same unit, Retrieve information | **passed** | All facts filled from the real output on WC.16.11.0001: hostname, model 2930F-48G-4SFP, product JL260A, software WC.16.11.0001, ROM WC.16.01.0010, serial number (not recorded here). The 2930F facts parser is now listed as checked on WC.16.10.0025 and WC.16.11.0001. |
