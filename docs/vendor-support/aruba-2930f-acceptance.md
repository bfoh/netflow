# Aruba 2930F (ArubaOS-Switch) — lab acceptance checklist

Driver under test: `ssh.aruba.aos_switch` (experimental). Goal of phase A: prove that UNDM
can **read** a 2930F correctly. Configuration changes come in phase B, only after the
driver has been corrected against your real output.

## Before you start
- [ ] Use a **spare or lab 2930F** that carries no live traffic, on a management network
      your UNDM PC can reach. Not operational equipment.
- [ ] Note the exact firmware version (e.g. `WC.16.xx.xxxx`) and tell the developer.
- [ ] SSH is enabled on the switch and you have a **manager-level** account.
- [ ] Take your own backup of the switch configuration with your usual method.
- [ ] `backend\.env` does **not** contain `UNDM_ENABLE_REAL_DEVICE_WRITES=true`
      (header shows "Real-device changes off").

## Phase A — read-only (nothing is changed on the switch)
| # | Step in UNDM | Expected result | Record |
|---|---|---|---|
| 1 | Project → Credentials → Add credential (switch username/password) | "Password set: yes" | — |
| 2 | Add device → model **Aruba 2930F** → **Real lab device (SSH)** → address + credential | Device in `lab` environment, driver `ssh.aruba.aos_switch` | — |
| 3 | Device → **Test connection** | "SSH session established (ArubaOS-Switch)" | message if it fails |
| 4 | **Retrieve information** | hostname, os_version `WC.16…`, serial, model filled | do they match the switch's `show system`? |
| 5 | **Back up** → Configurations tab, open the backup | Text equals the switch's `show running-config` | identical? which lines differ? |
| 6 | **Sanitized diagnostics** → read through → Copy/Download | Placeholders instead of IPs, MACs, serials, names | send the text to the developer |
| 7 | Intent: add VLAN `3999` named `undm-test` (an unused VLAN) → Generate | Text shows `vlan 3999` / `name "undm-test"` / `exit` | — |
| 8 | Deployments → plan with this device, **Dry run** on → Run dry run | Succeeds; preview shows only the VLAN lines; `show vlans` on the switch unchanged | result |

**Phase A passes when** steps 3–5 succeed, the facts match the switch, and the backup matches
the running configuration. The driver is then corrected with your (sanitized) output, kept as
a test fixture, and the 2930F model is promoted to `lab_read_only` for that firmware version.

## Phase B — first supervised change (only after phase A is accepted)
1. Set `UNDM_ENABLE_REAL_DEVICE_WRITES=true` in `backend\.env`, restart the backend.
2. Deploy the VLAN 3999 plan (not a dry run): approve → execute.
3. Expected: backup → lines sent → `write memory` → read back → **verified**.
4. Check on the switch: `show vlans` lists 3999 "undm-test"; `show running-config` contains it.
5. Remove the test VLAN yourself (`no vlan 3999`, then `write memory`): UNDM's merge mode
   adds and changes lines but never deletes.
6. Turn writes off again until the next planned test.

## Known limitations for this switch
- Static routes are rendered as `ip route …`; they only take effect with IP routing enabled
  (generation shows a warning). Management default gateways are not modelled yet.
- No routed physical ports and no VLAN descriptions in the template.
- No automatic rollback (manual recovery from the stored backup); no firmware upgrades.

## Results log
| Date | Step | Result | Notes |
|---|---|---|---|
| 2026-11-19 | 3 Test connection | **Pass** | SSH session established with `ssh.aruba.aos_switch`: login with stored credential, banner handling and `enable` worked. |
| 2026-11-19 | 4 Retrieve information | **Pass** — hostname, firmware and serial confirmed against the switch's `show system` by the product owner | Model 2930F-48G-4SFP, firmware WC.16.10.0025. Hostname and serial parsed (not recorded here). |
| 2026-11-19 | 6 Sanitized diagnostics | **Received** | Real `show system` / `show modules` layout confirmed the parser. Found and fixed: serial placeholder re-masking (`<serial-1>` vs `<serial-2>`); model now split into model + product number (JL260A); ROM version captured. Output kept as fixture `backend/tests/fixtures/aruba_2930f_wc_16_10_0025/` (identifiers replaced with fictional values). |
| 2026-11-19 | 5 Backup vs `show running-config` | **Pass** | Compared with live output: identical content. Only differences: the `Running configuration:` header/blank lines, and 80-column wrapping in the terminal copy (UNDM's session uses `terminal width 511`, so its copy is unwrapped). (A first attempt had compared against a stored reference file.) |
| 2026-11-19 | **Phase A criteria (steps 3–5)** | **Met** | 2930F catalog entry promoted to `lab_read_only` for 2930F-48G-4SFP (JL260A) WC.16.10.0025. Driver stays `experimental` overall until writes are validated (phase B). |
| — | 7–8 Generate + dry run | pending | Fixed before this step: merge-mode preview now lists only the intended lines (+ = will be added), never the existing configuration as removed; intent hostname defaults to the switch's reported hostname and warns before a rename. |

## Observations from the reference-file comparison (2026-11-19)
Comparing the live backup with a stored reference configuration file showed (without
identifiers): different ordering of global lines; `no lacp` under every interface in the
file but not in the live output; `ip ssh` in the file but not live; 2- vs 3-space
indentation; and possibly real differences (logging and SNTP lines). Implications:
- Textual diff is too noisy for audits; a normalized comparison is needed (feature idea:
  configuration audit — reference file vs live backup, order/indentation-insensitive).
- Lines such as `no lacp` / `ip ssh` may not be displayed by the switch; if so, verification
  after a merge deployment would report them missing. To be confirmed on a lab unit before
  adding them to the platform's "not displayed" list.
- The unit is part of a TETRA/DIMETRA zone system. Phase B (writes) requires a spare/lab
  unit or written approval from the system owner.
