"""Guided staging (D-117): devices that a person stages by hand in the device's own portal,
following UNDM's steps. UNDM never logs in to such a device and never changes it: it checks,
read-only, that the portal answers, hands out the exact files (with their SHA-256), and
records who did each step, when, and what the person noted.

The first procedure is the Nokia Flexi Multiradio 10 BBU (FSMF) through its web portal
(WebEM), as the team does it today (product owner, 2026-11-26; D-113). The steps are the
team's: load the software, then the site configuration file. Where in the portal each is
done is not written here: no Nokia document is available to UNDM, and the first run done
with the team records it in the steps' notes (Q-54) before anything is automated.

Pure data: no database, no web framework.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuidedStep:
    key: str
    title: str
    detail: str
    # "check": UNDM checks, read-only; "software": the approved package chosen for it;
    # "file": the configuration file chosen for it; "manual": what the person saw.
    kind: str
    note_label: str = ""
    # A "file" step's file generated from this template role is handed out in the template's
    # own format (line endings), as the team writes the file (D-083).
    template_role: str = ""


FLEXI_BBU: tuple[GuidedStep, ...] = (
    GuidedStep(
        "portal", "Its portal answers",
        "UNDM checks, read-only, that the BBU answers on port 443 at its address on the LMP "
        "port. The PC needs an address in the same network on the adapter the LMP cable is "
        "on (the team uses 192.168.255.126/24).", "check"),
    GuidedStep(
        "software", "Software package loaded and in use",
        "In the portal, load the software package below and take it into use; the BBU "
        "restarts. Note where you did it and the version the portal shows afterwards.",
        "software", "Where in the portal, and the version it shows now"),
    GuidedStep(
        "scf", "Site configuration file (SCF) loaded and in use",
        "In the portal, load the SCF below and take it into use; the BBU restarts. Note where "
        "you did it and what the portal reported.",
        "file", "Where in the portal, and what it reported", template_role="bbu_scf"),
    GuidedStep(
        "state", "Its state checked",
        "Once the BBU is back, note the state the portal shows (its operational state and any "
        "alarms).", "manual", "What the portal shows"),
)

PROCEDURES: dict[str, tuple[str, tuple[GuidedStep, ...]]] = {
    "flexi_bbu": ("Flexi BBU through its portal (WebEM), by hand", FLEXI_BBU),
}
