# TNDM Screenshot Catalog

Reference analysis of user-visible TNDM behaviour, used to derive **functional
requirements** for UNDM. Screenshots describe what a user sees; they are not
evidence of TNDM's internal algorithms, protocols, file formats or database
design, and UNDM does not reproduce TNDM's visual assets.

**Handling rules** (see `docs/SECURITY_BOUNDARIES.md`):
- Screenshot image files are **not stored in this repository**.
- System names, device hostnames, user-profile names, zone/cluster numbers and
  folder names visible in the screenshots are replaced with placeholders such
  as `<system-name>` and `<zone-switch-01>`.
- The 2026-11-17 batch contained real-looking system and device identifiers.
  Future references should be sanitized before sharing (see open question Q-08
  in `docs/REFERENCE_ANALYSIS.md`).

Evidence classes: **OBSERVED** (visible), **USER-CONFIRMED** (stated by the
product owner), **DOCUMENTED** (public/vendor documentation), **INFERRED**
(reasonable but unverified), **UNKNOWN**.

---

## SC-01 — Main window, no database open

| Field | Content |
|---|---|
| Date reviewed | 2026-11-17 |
| Screen | Application main window immediately after start |
| Visible controls | Menu bar: File, Setup, Configurations, Device Management, Script, Help. Setup, Configurations, Device Management and Script are disabled (OBSERVED). Toolbar: open folder, save, save-as (disk with arrow), check mark, outlined gear, filled gear, sliders, hierarchy/tree, "LOG" document, capture/record frame. A padlock with a masked-password field at the far right (OBSERVED). Title bar shows the product name and a 9.x version string (OBSERVED). |
| Observed workflow | Nothing can be configured or managed until a database is opened (OBSERVED: disabled menus). |
| Functional interpretation | The whole tool is scoped to one open "database" = one network system (INFERRED). Check mark likely validates the open database (INFERRED). The two gears probably generate/apply configuration, perhaps "selected" vs "all" (INFERRED, low confidence). Sliders = preferences (INFERRED). Tree icon = structure/topology view (INFERRED). LOG = operation log viewer (INFERRED). Padlock = credential or session lock (INFERRED). The capture icon turns red once a database is open (OBSERVED in SC-03); purpose UNKNOWN (possibly script/macro recording, given the Script menu). |
| Uncertainties | Exact meaning of both gear icons, the capture icon and the padlock: UNKNOWN. |
| Relevant UNDM features | Projects (one project ≈ one TNDM database); Configuration Studio validate/generate; Logs & Audit; Settings. |
| UNDM design response | UNDM opens to a dashboard rather than an empty window, and every module is reachable from the left navigation; modules without data show empty states instead of disabled menus. Icon-only toolbars are replaced with labelled actions (accessibility). |
| Priority | Informational (done: navigation, dashboard). |

## SC-02 — Open dialog for a "Transport Network Database"

| Field | Content |
|---|---|
| Date reviewed | 2026-11-17 |
| Screen | File → Open dialog |
| Visible controls | Standard file chooser; file type filter "Transport Network Database" (`.tndbz` extension) (OBSERVED). A side panel previews metadata of the selected file **before opening**: System name, System type (a platform release identifier), Modification date, "Saved by TNCT/TNDM" with a version number (OBSERVED). |
| Observed workflow | User browses to a database file, sees its system name/type/version, opens it (OBSERVED). |
| Functional interpretation | A network design is a portable, self-describing file (OBSERVED). The "Saved by TNCT/TNDM" field suggests the same file is produced or edited by more than one tool, e.g. a design tool and a deployment tool (INFERRED). Version metadata likely gates compatibility (INFERRED). |
| Uncertainties | File format, compression, signing: UNKNOWN and intentionally not investigated. |
| Relevant UNDM features | Project export/import (requirement FR-PRJ-05). |
| UNDM design response | UNDM projects live in PostgreSQL, but **export bundles** will carry a readable header (project name, purpose, schema version, exporting UNDM version, export time, content hash) so a user can inspect a bundle before importing, and import will refuse incompatible schema versions with a clear message. UNDM uses its own open format (JSON-based); no compatibility with `.tndbz` is attempted. |
| Priority | Medium — Phase 2/3 (export/import). |

## SC-03 — Database open: structure tree and system settings

| Field | Content |
|---|---|
| Date reviewed | 2026-11-17 |
| Screen | Main window with a database loaded |
| Visible controls | **Left:** "Selected devices: N" counter and "Unselect All" button; a checkbox tree: `<system-name>` → Cluster `<n>` → MSO `<n>` → Zone `<n>` → groups *Zone Switches*, *Zone Routers*, *RF Sites*, *Console Sites*, *Firewalls*, each containing devices (e.g. `<zone-switch-01>`, `<zone-router-01>`, `<zone-firewall-01>`, `<site-1>`) with device-type icons (OBSERVED). **Bottom-left:** an action drop-down ("Backup Configuration" selected) with a **Perform** button, and an **"Enable impacting actions"** checkbox (OBSERVED; checkbox visible in SC-04). **Right:** tabs System Settings / Cluster Settings / MSO Settings / Zone Settings; sub-tabs Structure / Inter MSO Links / Properties; tables of clusters (name, number, octet, number of zones, manual cluster octet), MSOs (name, number, located in cluster, zones list, zones type) and zones (located in cluster/MSO, zone number, zone octet, zone type, contact, location) (OBSERVED). |
| Observed workflow | Select one or many devices with checkboxes anywhere in the hierarchy → choose an action → Perform. Disruptive actions are only available after ticking "Enable impacting actions" (OBSERVED control; gating behaviour INFERRED). |
| Functional interpretation | (1) Devices are organised in a fixed, multi-level hierarchy with functional device groups (OBSERVED). (2) Hierarchy levels carry numbers and "octets" that very likely feed IP address derivation, i.e. addressing is computed from the structure (INFERRED, high confidence — USER-CONFIRMATION requested, Q-03). (3) Bulk operations on arbitrary selections are central to the workflow (OBSERVED). (4) A deliberate safety interlock separates read-only from impacting operations (OBSERVED control). |
| Uncertainties | Whether "Enable impacting actions" persists, times out or requires a role: UNKNOWN. How octets map to addresses: UNKNOWN. |
| Relevant UNDM features | Inventory (multi-select + bulk actions: **implemented**); operation impact classification (**implemented** in `undm.domain.operations`); site hierarchy and addressing plans (planned). |
| UNDM design response | (a) UNDM keeps the select-then-perform pattern (implemented in Network Elements). (b) The DIMETRA-specific levels (Cluster/MSO/Zone, RF/Console sites) are **not** hard-coded; UNDM will offer a user-defined hierarchy (e.g. Region → Site → Area) and user-defined device groups. (c) Structure-driven addressing becomes a generic **addressing plan** feature: pools and per-site/per-role allocation rules defined by the user (planned, Phase 3). (d) Instead of a global "enable impacting actions" checkbox, every operation carries an impact class; read-only operations run directly, impacting ones only through a deployment plan with preview, explicit approval and recovery — a stronger and auditable gate (implemented). |
| Priority | High — bulk actions and impact gating done; hierarchy and addressing plans Phase 3. |

## SC-04 — Device context menu (photograph of the screen)

| Field | Content |
|---|---|
| Date reviewed | 2026-11-17 |
| Screen | Right-click menu on a zone switch in the structure tree |
| Visible controls | **Open ▸** (Telnet, SSH); **Show Device Log** (disabled); **Continuous Ping in Background**; **Other Ping Options ▸**; **Initialize ▸**; **Set Password**; **Reboot**; **Check Information**; **Wait Until Available**; **Audit**; **Firmware ▸**; **MAC Filtering ▸**; **Configuration ▸**; **Retrieve ▸** (OBSERVED). |
| Observed workflow | Per-device operations are launched from the tree's context menu (OBSERVED). |
| Functional interpretation | Open: interactive terminal session (OBSERVED labels). Ping options / Wait Until Available: reachability monitoring, e.g. after reboot or firmware install (INFERRED). Initialize: first-time provisioning of an unconfigured device — matches the product owner's description of provisioning unconfigured elements (USER-CONFIRMED capability; mapping to this menu item INFERRED). Set Password: credential rotation on the device (INFERRED). Check Information: read model/serial/version (INFERRED). Audit: compare device state against expected configuration or policy (INFERRED, low confidence — Q-02). Firmware: upgrade sub-workflows (INFERRED). MAC Filtering: port-security / MAC allow-listing management (INFERRED — Q-04). Configuration / Retrieve: push and pull configuration (INFERRED). |
| Uncertainties | Behaviour behind each sub-menu: UNKNOWN. Whether impacting items are hidden/disabled without the SC-03 checkbox: UNKNOWN. |
| Relevant UNDM features | Device row actions (implemented: details, reachability, retrieve information, backup, generate, deploy); facts retrieval and identity check (implemented); provisioning (Phase 6); firmware (Phase 7); drift/compliance "audit" (future); terminal access (not planned — security review needed first). |
| UNDM design response | UNDM's device action menu separates **Read-only** from **Changes the device** sections. "Check Information" ≙ *Retrieve device information* (implemented, stores observed facts separately from declared data). "Wait Until Available" becomes part of orchestrated workflows (post-reboot verification) rather than a manual action. "Set Password" will be a credential-rotation workflow with approval (Phase 8). Interactive Telnet is not offered; Telnet is plaintext and is excluded by the security boundaries. |
| Priority | High for read-only items (done); provisioning/firmware per roadmap. |

---

## Requirements derived from this batch

| ID | Requirement | Source | Status |
|---|---|---|---|
| RA-01 | Multi-select devices across the inventory and run one action on the selection | SC-03 | Implemented |
| RA-02 | Explicit separation of read-only and impacting operations | SC-03, SC-04 | Implemented (impact class + deployment gate) |
| RA-03 | Hierarchical, user-defined site structure with functional device groups | SC-03 | Planned (Phase 3) |
| RA-04 | Addressing derived from structure via user-defined plans | SC-03 | Planned (Phase 3); needs Q-03 |
| RA-05 | Self-describing project export with pre-import metadata preview | SC-02 | Planned (Phase 2/3) |
| RA-06 | Retrieve and display device identity information | SC-04 | Implemented |
| RA-07 | Reachability wait/monitoring integrated into reboot/firmware workflows | SC-04 | Planned (Phase 7) |
| RA-08 | Port security / MAC allow-list intent | SC-04 | Backlog; needs Q-04 |
| RA-09 | Device "audit" (state vs intent comparison) | SC-04 | Backlog (drift detection); needs Q-02 |
