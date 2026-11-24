# FortiGate 101F — staging procedure, bench validation

Procedures under test: `undm.drivers.fortinet.fortios_ssh` (firmware and base restore over
TFTP, site script statement by statement, tunnel key from the credential store, revisions).
Status: **experimental — tested only against a fake FortiGate** whose wording is synthetic
but which really fetches files from UNDM's TFTP server. This checklist is the first run on
hardware. Order agreed 2026-11-19: firmware → base file → site file (D-034).

## Use only
- A **spare, factory-default** FortiGate 101F on an isolated bench, connected to the laptop
  through its **mgmt** port. Not a unit that belongs to a running system.
- Console cable available, in case the unit does not come back after a restart.

## Before you start
- [ ] Laptop address on the bench adapter in 192.168.1.0/24 (for example 192.168.1.10/24).
      The site file only allows admin logins from that network (and two others).
- [ ] **First login (by hand for now):** browser → `https://192.168.1.99`, user `admin`, empty
      password, set the approved password when forced to. (UNDM does not do this step yet.)
- [ ] The **base file carries the approved admin password** (your team edits it; otherwise
      UNDM cannot log in after the restore and stops with "Authentication failed").
- [ ] Image `FGT_101F-v7.6.5…out` downloaded from the Fortinet support site, with its
      **SHA-512** (the 'Checksum' link next to the download; UNDM accepts SHA-256 or SHA-512, D-061).
- [ ] `backend\.env`: `UNDM_ENABLE_REAL_DEVICE_WRITES=true`,
      `UNDM_ENABLE_REAL_DEVICE_FIRMWARE=true` (and, if alone,
      `UNDM_FIRMWARE_REQUIRE_SEPARATE_APPROVER=false`); database upgraded
      (`.venv\Scripts\python.exe -m alembic upgrade head`); backend restarted.
- [ ] Windows Firewall allows **inbound UDP 69** to Python on the bench network; no other
      TFTP program running.
- [ ] In UNDM, project → **Credentials**: `fw-admin` = admin + approved password;
      `cen-psk` = any user name + the approved tunnel key. Values are typed only there.
- [ ] Device: model FortiGate-101F, **Real lab device (SSH)**, address 192.168.1.99,
      credential `fw-admin`.

## Since the 2930F bench runs (UNDM v33)
- Runs continue on the server; **Stop** ends one at its next safe point. A yellow banner with
  a timer shows while the unit restarts; "Copy events as text" copies the event list.
- If the FortiGate restarts after a firmware or base-file transfer **without closing the SSH
  session** (as a 2930F did), UNDM notices that its SSH port stopped answering and goes on
  to wait for it (D-059), instead of waiting up to 30 minutes.
- After a configuration plan, **View configuration after deployment** / **Compare with what
  was sent** show what the unit runs.

## Steps
| # | Step | Expected |
|---|---|---|
| 1 | Device page → **Test connection**, **Retrieve information** | model FortiGate-101F, version v7.2.6 (bench unit) |
| 2 | Firmware → upload the 7.6.5 image: platform **FortiOS**, version `7.6.5`, compatible model `FortiGate-101F`, Fortinet's SHA-512 → **Approve**. Without the SHA-512: **Approve without checksum…** with a reason (where the file came from) | verified and approved; or "not verified · approved with reason" |
| 3 | Before planning: check Fortinet's upgrade path for 101F 7.2.6 → 7.6.5 (Q-38); if intermediate versions are required, upload and run those first. Upgrade planning → device → **dry run** | `v7.2.6 -> 7.6.5`, nothing changed; a warning if the image was approved without a checksum |
| 4 | Real firmware plan → approve with a window → **Execute** | events: "fetched the image (… bytes), accepted it and closed the session to restart", "device reachable again", "running v7.6.5" |
| 5 | Device → Configurations → import the **base** file and the **site** file | base: "Full FortiOS configuration backup … → replace"; site: "FortiOS CLI script … multi-VDOM", one secret setting (psksecret) |
| 6 | Deployments → new plan → device → choose the **base** file (mode switches to Replace) → **Login after loading: the base file's password** (a credential on the project's Credentials tab) → Validate → Approve → Execute | "fetched the configuration file …, accepted it and closed the session to restart", "device reachable again", "back after the restore: hostname …, VDOMs multiple, running v7.6.5", "revision 'base-vNN' saved" |
| 7 | New plan → choose the **site** file (Merge) → **Value for psksecret**: `cen-psk` → Validate → Approve → Execute | "N statements sent, every one accepted", a warning for the first `end` (expected), "every statement was accepted; hostname <site hostname>", "revision '<site file name>' saved" |
| 8 | FortiGate GUI → Configuration → Revisions | both revisions listed, as when done by hand |

## If something goes wrong
- **"did not request the … from UNDM's TFTP server"** — firewall (UDP 69), adapter/subnet,
  or the unit asked a question UNDM did not recognise (its text is in the events). Nothing
  was changed.
- **"did not accept it: it returned to its prompt"** — the unit refused the file (for example
  a licence or image check message, shown in the events).
- **"neither restarted nor returned to its prompt"** — check the unit on the console.
- **"If it asks for a new password, set the device's approved password on the unit by hand
  now"** — UNDM could not answer the unit's questions itself (unexpected wording, or no login
  after loading in the plan). Log in with the base file's password in a browser or SSH, set
  the approved password; UNDM continues by itself.
- **"lines of this file are already on the FortiGate"** (preview) or **"Cannot change … while
  … is used"** — a site configuration is on the unit already. Run the base plan again, then
  the site plan.
- **"fetched and checked … but did not restart within 180 s"** — the unit took the file
  without complaint but did not restart; check on the unit whether it applied it.
- **"Transfer incomplete … UNDM has withdrawn the file"** — the fetch was cut off by UNDM (or
  the unit stopped acknowledging); the unit cannot finish it later. Check its output in the
  events and that it still runs the old version.
- **"Authentication failed" after the base restore** — the base file's admin password is not
  the stored one. Log in on the console with the base file's password and set the approved one.
- **Site file stops at a line** — the event names the line and the unit's answer; lines
  before it were applied, the rest were not sent. Tell us the message: if it is harmless it
  will be added to the known messages.
- **Revision warning** — the change is applied; save the revision in the GUI. Send us the
  output of `execute revision list config` so the check can be corrected.

## Please send back
The event list of each job (copy from the deployment page; replace hostnames, serials and
addresses as usual), especially any "device output" event, and the time each step took.

## Results log
| Date | Unit | Step | Result | Notes |
|---|---|---|---|---|
| 2026-11-23 | spare 101F | Test connection | login accepted, no prompt | Netmiko "Pattern not detected: 'to accept\|[#$]'". Probably the forced admin password change at the first login (to be confirmed by what the unit shows). UNDM now reports the unit's text (D-060). |
| 2026-11-24 | spare 101F | First login (by hand, browser) | done | GUI after `admin` with an empty password: page "Change Password" with "You are required to change the default password.", fields Old Password / New Password / Confirm Password, buttons OK / Logout; after OK the login page returns. Confirms the forced change behind the SSH "no prompt" result. The SSH wording of the same step is not yet seen (needed before UNDM can do it). |
| 2026-11-24 | same unit | Test connection, Retrieve information | **passed** | SSH with the approved admin login; facts read correctly: hostname and model FortiGate-101F, FortiOS **v7.2.6** (as shipped; the checklist expected v7.2.7), serial number (not recorded here), VDOM mode disabled. The FortiOS facts parser is now listed as checked on FortiGate-101F v7.2.6. |
| 2026-11-24 | same unit | Firmware image upload | not verified | Uploaded without a checksum; Fortinet publishes MD5 and SHA-512, which UNDM did not accept. Fixed: SHA-512 accepted, checksum can be added after upload (D-061). |
| 2026-11-24 | same unit | Firmware image approval | decision | Fortinet's SHA-512 could not be obtained; product owner decided to allow approval with a written reason (D-062). |
| 2026-11-24 | same unit | Firmware 7.2.6 → 7.6.5 (real plan) | **failed, UNDM fault** | After "y": "Please wait...", "Connect to tftp server <PC> ...", then '#' progress marks. UNDM took the '#' line for the prompt and failed after 5 s: "Transfer incomplete (5581824 of 101271832 bytes)"; recovery found v7.2.6. The TFTP server did not stop the fetch that was under way, and **the unit finished it, installed 7.6.5 and restarted** (product owner, same day), although UNDM had closed the SSH session that started the fetch and recorded the plan as rolled back. That plan's record is therefore wrong about the outcome. Fixed (D-063): a fetch under way is now cancelled when UNDM ends the step. |
| 2026-11-24 | same unit (v7.6.5) | Base file restore | **failed, UNDM fault** | After "y": "Please wait...", "Connect to TFTP server <PC> ...", "Get file from TFTP server OK.", "File check OK.", then the prompt (twice). UNDM took the prompt for a refusal after 3 s; plan ended in recovery required. **The unit did take the base file** (product owner). Fixed (D-064): UNDM now waits up to 180 s for the restart. |
| 2026-11-24 | same unit, base file loaded | Login with the base file's password | forced change | Browser: "Change Password", "Your password does not conform to the password policy, please input a new password.", rules 1 upper, 1 lower, 1 special, 1 number, minimum length 12; fields Old / New / Confirm password. SSH CLI: "You are forced to change your password. Old password:", the policy (minimum-length=12 upper-case-letter=1 lower-case-letter=1 number=1 non-alphanumeric=1), "New Password:", "Confirm Password:", "Verifying password...", "Welcome!". The team sets the approved password again. UNDM now does this itself when the plan names the base file's password as login after loading (D-066); otherwise it waits for a person (D-065). |
| 2026-11-24 | same unit | Base file restore again (v39) | **failed, UNDM fault** | Restart after "File check OK." and the prompt recognised: "accepted it and returned to its prompt, then restarted (its SSH port stopped answering)" (D-064 works on hardware). After the restart UNDM answered the demanded password change over SSH and the unit took the approved password (SSH text: "... New Password:", "Confirm Password:", "Verifying password...", prompt; no "Welcome!"). Then each login timed out in Netmiko because UNDM had already read the prompt; the plan seemed stuck. Fixed (D-067). |
| 2026-11-24 | same unit | Base file restore (v40) | **passed** | Fetched (387193 bytes), "returned to its prompt, then restarted"; back after about 2 min; the unit demanded the password change on the base file's login and UNDM answered it with the approved login, then logged in again with it; same serial number; verified: hostname, VDOMs multiple, v7.6.5; revision saved on the unit. Device keeps the approved login. First complete FortiGate configuration load by UNDM on hardware. |
| 2026-11-24 | same unit | Site script (Merge, tunnel key from the credential store) | **passed** | 1784 statements sent, every one accepted; the expected warning at the first bare `end` ("Unknown action 0 / Command fail. Return code -1"); 191 "new entry '<name>' added" notices (now counted, D-068); verified: hostname as set by the file, 1363 of 1498 lines shown by `show` (defaults hidden); revision named after the file saved. Note: the hostname set by the file did not match the system number in the file's name; product owner to check the file. |
| 2026-11-24 | same unit | Revisions in the GUI | **passed** | Both revisions listed under 7.6.5 build 3651 (base, then site), user admin. The toolbar showed "Save Changes" with a warning sign: whether the unit saves changes automatically (cfg-save) is not yet known (Q-40). |
| 2026-11-24 | same unit | Save mode (Q-40) | automatic | `get system global \| grep cfg-` fails at the top of a multi-VDOM unit ("command parse error before 'global'"); inside `config global`: "cfg-save : automatic". UNDM now checks it after every load (D-069). |
| 2026-11-24 | same unit | Corrected site file over the earlier site configuration | **refused at line 918** | "Cannot change 'extintf' while the VIP entry is used. Command fail. Return code -23" after 879 of 1784 statements; preview had shown only +136 lines. Not a UNDM fault: FortiOS protects objects in use. Procedure: base plan again, then the site plan. UNDM now cautions before approval (D-070). |
