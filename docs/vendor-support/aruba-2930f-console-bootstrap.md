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
