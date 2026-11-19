# Aruba 2930F — console bootstrap, bench validation

Procedure under test: `undm.provisioning.aos_switch` (console bootstrap). Status:
**tested only against a simulated console**. This checklist is its first run on hardware.

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
- [ ] **New units** ask "Configure the manager credentials :" / "Username:" on the console
      and require a password and its confirmation before anything else (seen 2026-11-19).
      Attach the **approved login** (user `manager` + approved password) to the device in
      UNDM before the bootstrap: UNDM sets exactly that login, answering only the username
      and the two password prompts, and uses it from then on. Without it the bootstrap stops
      at that point and sends nothing.

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
