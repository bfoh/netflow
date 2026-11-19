# Aruba 2930F — firmware over SSH + TFTP, bench validation

Procedure under test: `ArubaOSSwitchSsh.stage_firmware / reboot` with UNDM's built-in TFTP
server. Status: **experimental — one successful run on hardware** (2026-11-19, spare JL260A,
approved downgrade; see the results log). Before that only against a fake switch that downloads
from the real TFTP server.

Commands UNDM sends (from public write-ups of the ArubaOS-Switch CLI, see
`staging-procedures-research.md`; the switch's exact questions are not verified):

| Step | Command | UNDM answers |
|---|---|---|
| Read versions | `show system`, `show flash` | — |
| Copy image | `copy tftp flash <this PC> <file> primary` | `y` to a `[y/n]` / `(y/n)` question only |
| Check | `show flash` — primary must show the target version | — |
| Restart | `boot system flash primary` | `n` to a "save configuration" question, then `y` |
| After restart | reconnect, `show system` — running version must equal the target | — |

Any other question is **not answered**: the job stops and shows the switch's text.

## Use only
- A **spare** 2930F on an isolated bench, reachable by SSH from the laptop (for a
  factory-default unit: run the console bootstrap first).
- A switch you can reach by **console cable** during the test, in case it does not come back.

## Before you start
- [ ] Image `WC_16_10_0025.swi` downloaded from the HPE/Aruba support portal, with its
      published SHA-256.
- [ ] `backend\.env` contains both `UNDM_ENABLE_REAL_DEVICE_WRITES=true` and
      `UNDM_ENABLE_REAL_DEVICE_FIRMWARE=true`; backend restarted.
- [ ] Working alone? add `UNDM_FIRMWARE_REQUIRE_SEPARATE_APPROVER=false` (otherwise a second
      person must approve the plan).
- [ ] Windows Firewall allows **inbound UDP 69** to Python on the bench network (Windows asks
      the first time; choose the network the bench adapter is on). No other TFTP program
      (Tftpd64, SolarWinds…) is running.
- [ ] The laptop's bench adapter and the switch are in the same subnet; `ping` works.
- [ ] Note the switch's current `show flash` and `show version` output (for the record).

## Steps
| # | Step | Expected |
|---|---|---|
| 1 | Firmware → upload the image: vendor Aruba, platform `aos_switch`, version `WC.16.10.0025`, compatible models `2930F` (or the exact model string shown under Observed facts), vendor SHA-256 | "integrity verified" |
| 2 | Approve the image | status approved |
| 3 | Upgrade planning → select the switch → **dry run** (new units ship with WC.16.11.0001, newer than the approved WC.16.10.0025: tick **Install the approved version even on devices that run a newer one**) | plan shows `from <current> → WC.16.10.0025` (marked DOWNGRADE if older); nothing changed |
| 4 | Create the real plan → approve with a maintenance window | state ready |
| 5 | Execute | page shows "In progress"; events appear step by step |
| 6 | Watch the events | `stage: … bytes transferred`, `reboot: restart … started`, `device reachable again`, `running WC.16.10.0025`, state **succeeded** |
| 7 | On the switch: `show flash`, `show version` | primary = running = WC.16.10.0025 |

## If something goes wrong
- **"did not request the image"** — the switch never contacted this PC: firewall (UDP 69),
  wrong adapter/subnet, or the switch asked a question UNDM did not recognise (its text is
  in the events). Nothing was changed.
- **"Transfer incomplete"** — do not restart the switch; check `show flash` on the console.
- **Job ends "Upgrade did not complete"** with the original version still running — the
  image may already be in the primary flash; the target's message says so.
- **Switch does not come back** — console cable; `show flash`; the secondary image is
  untouched by this procedure (`boot system flash secondary`).

## Please send back
- The event list of the job (copy from the deployment page) and, if a step failed, the
  "device output" event. Replace serial numbers and names as usual.
- How long the transfer, the flash write and the restart took (to tune the waiting times:
  currently 30 checks × 20 s after the restart).

## Results log
| Date | Unit | From → to | Result | Notes |
|---|---|---|---|---|
| 2026-11-19 | spare 2930F-48G-4SFP (JL260A), new unit, after the console bootstrap | WC.16.11.0001 → WC.16.10.0025 (approved downgrade, allowed by the plan) | **succeeded**, target verified | Dry run first (preflight: reachable, identity ok, running WC.16.11.0001; nothing changed). Real plan approved with a 2-hour window, executed: backup, TFTP transfer, restart, same serial after the restart, running WC.16.10.0025. Event wording and durations still to be copied in from the job's event list. |
