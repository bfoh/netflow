"""Where UNDM connects is decided in one place (D-125).

Every connection takes its address from ``services.reach.reach_of`` through
``services.devices.build_driver``. A new read of a device's bench or network address
elsewhere would connect around it (for example to the bench address of a system that is in
the network), so any such read must be listed here with its reason."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "undm"

# (file, text on the line) -> why it may read the address directly.
ALLOWED = {
    ("services/reach.py", "device.management_address"): "the resolver itself",
    ("services/reach.py", "device.network_address"): "the resolver and its setter",
    ("services/reach.py", "Device.network_address"): "duplicate check in the system",
    ("services/reach.py", "gateway.network_address"): "the BFW needs one to move",
    ("services/reach.py", "d.management_address for d in device.project.devices"):
        "the bench networks, to leave bench addresses out of a file's suggestion",
    ("services/troubleshoot.py", "(d.management_address, \"bench address\")"):
        "every address of the system, to name traceroute hops (no connection)",
    ("services/troubleshoot.py", "(d.network_address, \"network address\")"):
        "every address of the system, to name traceroute hops (no connection)",
    ("services/troubleshoot.py", "gateway.network_address"):
        "a simulated trace passes the BFW (no connection)",
    ("services/devices.py", "device.management_address, device.network_address"):
        "masking shared text (no connection)",
    ("services/deployments.py", "from_version=device.management_address"):
        "plans record the bench address they run at (plans are bench only)",
    ("services/deployments.py", "to_version=device.management_address"):
        "a restart comes back at its bench address (plans are bench only)",
    ("services/deployments.py", '"address": device.management_address'):
        "audit of a verified load on the bench",
    ("services/deployments.py", "reached != device.management_address"):
        "a verified load moved the bench address (plans are bench only)",
    ("services/deployments.py", '"from": device.management_address'):
        "audit of the bench address change",
    ("services/deployments.py", "device.management_address = reached"):
        "the bench address a verified load gave the device",
    ("services/provisioning.py", "device.management_address"):
        "console setup sets the bench address (bench only)",
}

_READ = re.compile(r"(?<![.\w])(\w+)\.(management_address|network_address)\b")


def _hits() -> list[tuple[str, int, str]]:
    out = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        for n, line in enumerate(path.read_text().splitlines(), 1):
            for m in _READ.finditer(line):
                owner = m.group(1)
                if owner in {"target", "network", "net"} or rel.startswith("drivers/"):
                    continue  # a driver's own target, or ipaddress' network_address
                out.append((rel, n, line.strip()))
    return out


def test_device_addresses_are_read_only_where_listed():
    unlisted = [f"{rel}:{n}: {line}" for rel, n, line in _hits()
                if not any(rel == f and text in line for (f, text) in ALLOWED)]
    assert not unlisted, ("Read the address through services.reach.reach_of (or list it "
                          "here with a reason):\n" + "\n".join(unlisted))


def test_every_listed_read_still_exists():
    hits = _hits()
    stale = [k for k in ALLOWED if not any(rel == k[0] and k[1] in line
                                           for rel, _, line in hits)]
    assert not stale, f"Remove these entries, the code is gone: {stale}"


def test_device_targets_are_made_only_in_build_driver():
    made = [f"{p.relative_to(SRC)}:{n}" for p in SRC.rglob("*.py")
            for n, line in enumerate(p.read_text().splitlines(), 1)
            if "DeviceTarget(" in line and "class DeviceTarget" not in line]
    assert made == ["services/devices.py:" + made[0].split(":")[1]] and len(made) == 1, made
