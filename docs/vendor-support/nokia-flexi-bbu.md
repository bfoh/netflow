# Nokia Flexi Multiradio 10 BBU (FSMF): staging through WebEM

Status: **nothing built yet**. This page records what the product owner said, what a web
search found, and the decision on how UNDM will help (D-113).

## What the product owner said (2026-11-26)
- The BBU is the main node of the system's LTE radio access network: a Flexi Multiradio 10
  system module, **FSMF**.
- Staging: load the firmware, then the site configuration file (SCF).
- The laptop connects to the port called **LMP**, default address **192.168.255.129**, and
  the work is done in the web portal (WebEM) in a browser.
- The team has no Nokia tool or manual for scripted BTS operations.

## What a web search found (2026-11-26): all unverified
None of this is from Nokia's own public pages. The sources are copies of Nokia manuals on
document-sharing sites and forum or blog posts, read as search-engine extracts: the pages
themselves could not be opened from the development environment, so wording and context
are unchecked. Treat every line as a lead to confirm from the team's own Nokia documents or
on the bench. Nothing here may be built on as a fact (CLAUDE.md rule 2).

| Topic | Lead | Source kind |
|---|---|---|
| The portal | WebEM (Web Element Manager) at `https://192.168.255.129`, port 443; a secondary core at `.119`. Recommended browser: Chrome | copy of "WebEM User Guide" |
| Which tool per release | "Starting from release LTE 19/SRAN 17A Web Element Manager … became the official Element Manager"; BTS Site Manager (an installed Java program) for older releases | copy of "WebEM User Guide" |
| Laptop address | A fixed address in 192.168.255.0/24. Sources disagree: `.126` (LTE training material, a forum) or `.130` (WCDMA commissioning material). No DHCP on the LMP was found | training copies, forum |
| Firmware | Software → Software Update; the package is a ZIP; "Activate software after update" takes it into use, otherwise it is listed as planned; the unit restarts; the previous version becomes "passive"; the browser session is lost during the update | copies of "WebEM User Guide" and a quick reference |
| SCF | An XML file. Configuration → Configuration Management → Commissioning Wizard: Load SCF, Validate Plan, Activate Plan; activation overwrites the configuration and the unit resets | copies of "Commissioning SBTS by WebEM" and "WebEM User Guide" |
| Order | Software first, and it must match the SCF | blog |
| End state | "On Air" / "IntegratedToRan" | training copy |
| Automation | "The interface between WebEM is binary, it is not intended to be used by 3rd parties. For automatization purposes, WebEM Remote Tool (former BTS CLI) should be used." No syntax of that tool is public | copy of "WebEM User Guide" |
| Not found | Any REST, WebSocket or NETCONF description; the tool's commands; the FSMF's start-up time; a typical update duration; the SCF's root element from a Nokia document |  |

Default account names appear in those copies. They are not recorded here, and passwords
found there are never recorded anywhere.

## Decision (D-113): guided by hand first
UNDM will not drive the portal: no documented interface is available to the team, and
nothing may be invented. The first version instead:
- keeps the system's firmware package and SCF, with their SHA-256;
- makes the SCF by zone, if two zones' SCFs prove the zone rules hold for it (D-111);
- checks, read-only, that the LMP address answers on port 443;
- opens the portal in the browser and shows the steps one by one;
- records who did each step and when, and shows it in the staging report.

Automation can follow if the team obtains Nokia's WebEM Remote Tool with its manual, or
decides on browser automation after bench screenshots of every screen (experimental).

## Needed from the product owner before building
See `docs/REFERENCE_ANALYSIS.md`, Q-54.
