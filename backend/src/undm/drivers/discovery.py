"""What management services a device offers (D-130). Read-only.

Without a login, UNDM opens a TCP connection to each documented management port and reads
only what the server presents by itself:
- SSH (22) and NETCONF over SSH (830, RFC 6242): the identification line an SSH server
  sends first (RFC 4253 §4.2). UNDM sends nothing on these ports.
- HTTPS (443): the certificate the server presents in the TLS handshake. No HTTP request is
  sent.

With a login and only on request, :func:`netconf_hello` logs in once to the NETCONF
subsystem and reads the server's ``<hello>``: the capabilities and the YANG modules it
announces. It sends no ``<rpc>`` and closes. A refused login is not retried, so an account
cannot be locked by UNDM.

Nothing here knows a vendor: drivers say which ports to look at.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import socket
import ssl
import xml.etree.ElementTree as ET  # noqa: N817 - the usual short name
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

SSH_BANNER_LIMIT = 1024  # RFC 4253: lines before the identification line are allowed
HELLO_LIMIT = 1 << 20  # a server <hello> larger than 1 MiB is not read
EOM = b"]]>]]>"  # NETCONF 1.0 end of message: hello messages always use it (RFC 6242 §4.1)
NETCONF_NS = "urn:ietf:params:xml:ns:netconf:base:1.0"


@dataclass(frozen=True)
class Service:
    port: int
    kind: str  # "ssh" | "https" | "netconf"
    name: str
    reference: str


SSH = Service(22, "ssh", "SSH", "RFC 4253")
HTTPS = Service(443, "https", "HTTPS (web portal)", "RFC 8446")
NETCONF = Service(830, "netconf", "NETCONF over SSH", "RFC 6242")
MANAGEMENT_SERVICES: tuple[Service, ...] = (SSH, HTTPS, NETCONF)


@dataclass
class PortAnswer:
    port: int
    kind: str
    name: str
    reference: str
    open: bool
    banner: str | None = None
    certificate: dict[str, str] | None = None
    note: str = ""


@dataclass
class NetconfHello:
    session_id: str | None
    capabilities: list[str] = field(default_factory=list)
    modules: list[dict[str, str]] = field(default_factory=list)
    base_versions: list[str] = field(default_factory=list)
    host_key: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DiscoveryError(Exception):
    """A step of the NETCONF reading failed; the message says which, without secrets."""


# Patched by the tests: nothing in the test suite opens a real connection.
connect: Callable[..., socket.socket] = socket.create_connection


def _printable(raw: bytes | str, limit: int = 200) -> str:
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    return "".join(c for c in text if c.isprintable())[:limit].strip()


def read_ssh_banner(sock: socket.socket) -> tuple[str | None, str]:
    """The server's identification line, read without sending anything."""
    data = b""
    while len(data) < SSH_BANNER_LIMIT:
        complete = data.split(b"\n")[:-1]  # lines that have ended
        found = next((line for line in complete if line.startswith(b"SSH-")), None)
        if found is not None:
            return _printable(found.rstrip(b"\r")), ""
        try:
            chunk = sock.recv(256)
        except OSError:
            break
        if not chunk:
            break
        data += chunk
    found = next((line for line in data.split(b"\n") if line.startswith(b"SSH-")), None)
    if found is not None:
        return _printable(found.rstrip(b"\r")), ""
    first = data.split(b"\n", 1)[0]
    if not data:
        return None, "It accepted the connection but sent nothing within the time limit."
    return None, f"It sent no SSH identification line; it began with: {_printable(first, 80)!r}"


def _certificate(der: bytes) -> dict[str, str]:
    from cryptography import x509

    cert = x509.load_der_x509_certificate(der)
    return {
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "not_after": cert.not_valid_after_utc.isoformat(),
        "sha256": hashlib.sha256(der).hexdigest(),
    }


def read_tls_certificate(sock: socket.socket, host: str) -> tuple[dict[str, str] | None, str]:
    """The certificate the server presents, without checking it (it is only read) and
    without sending an HTTP request."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
            version = tls.version() or ""
    except (ssl.SSLError, OSError) as e:
        return None, f"The TLS handshake did not complete: {_printable(str(e), 160)}"
    if not der:
        return None, "The TLS handshake completed without a certificate."
    try:
        cert = _certificate(der)
    except ValueError as e:
        return None, f"Its certificate could not be read: {_printable(str(e), 160)}"
    return {**cert, "tls": version}, ""


def probe(host: str, services: Iterable[Service] = MANAGEMENT_SERVICES,
          timeout: float = 3.0) -> list[PortAnswer]:
    answers: list[PortAnswer] = []
    for s in services:
        answer = PortAnswer(s.port, s.kind, s.name, s.reference, open=False)
        try:
            sock = connect((host, s.port), timeout=timeout)
        except OSError:
            answer.note = "No connection (closed, filtered or nothing listening)."
            answers.append(answer)
            continue
        answer.open = True
        try:
            sock.settimeout(timeout)
            if s.kind in ("ssh", "netconf"):
                answer.banner, answer.note = read_ssh_banner(sock)
            elif s.kind == "https":
                answer.certificate, answer.note = read_tls_certificate(sock, host)
        finally:
            with contextlib.suppress(OSError):
                sock.close()
        answers.append(answer)
    return answers


def parse_hello(raw: bytes) -> NetconfHello:
    """The server's <hello> (NETCONF 1.0 framing): its capabilities, the YANG modules they
    name (``?module=…&revision=…``, RFC 6020 §5.6.4) and its session id."""
    text = raw.split(EOM, 1)[0].decode("utf-8", "replace").strip()
    # From a device: expat (2.4.1+) refuses entity expansion attacks and ElementTree never
    # fetches external resources; a DOCTYPE is refused outright.
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise DiscoveryError("Its <hello> carries a DOCTYPE: not read.")
    try:
        root = ET.fromstring(text)  # noqa: S314 - see above
    except ET.ParseError as e:
        raise DiscoveryError(f"Its <hello> is not well-formed XML: {e}") from e
    if root.tag not in (f"{{{NETCONF_NS}}}hello", "hello"):
        raise DiscoveryError(f"It answered with <{root.tag}>, not a NETCONF <hello>.")
    caps = [(c.text or "").strip() for c in root.iter()
            if c.tag in (f"{{{NETCONF_NS}}}capability", "capability") and (c.text or "").strip()]
    session = next((c.text for c in root.iter()
                    if c.tag in (f"{{{NETCONF_NS}}}session-id", "session-id")), None)
    modules: list[dict[str, str]] = []
    versions: list[str] = []
    for cap in caps:
        if cap.startswith("urn:ietf:params:netconf:base:"):
            versions.append(cap.rsplit(":", 1)[-1])
        query = parse_qs(urlsplit(cap).query)
        if "module" in query:
            modules.append({"name": query["module"][0], "namespace": cap.split("?", 1)[0],
                            "revision": query.get("revision", [""])[0]})
    note = ""
    if any(c.startswith("urn:ietf:params:netconf:capability:yang-library:") for c in caps):
        note = ("It announces the YANG library: its full module list is read with a request, "
                "which this reading does not send.")
    return NetconfHello(session.strip() if session else None, caps,
                        sorted(modules, key=lambda m: m["name"]), versions, note=note)


def netconf_hello(host: str, port: int, username: str, password: str,
                  timeout: float = 15.0) -> NetconfHello:
    """One login to the NETCONF subsystem; the server's <hello> read; nothing sent; closed."""
    import paramiko

    try:
        sock = connect((host, port), timeout=timeout)
    except OSError as e:
        raise DiscoveryError(f"No connection to {host}:{port}: {_printable(str(e), 120)}") from e
    transport = paramiko.Transport(sock)
    try:
        try:
            transport.start_client(timeout=timeout)
        except paramiko.SSHException as e:
            raise DiscoveryError(f"No SSH session: {_printable(str(e), 160)}") from e
        key = transport.get_remote_server_key()
        host_key = (f"{key.get_name()} SHA256:"
                    + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("="))
        try:
            transport.auth_password(username, password, fallback=False)
        except paramiko.BadAuthenticationType as e:
            raise DiscoveryError(
                "It does not take a password login here; it allows: "
                f"{', '.join(e.allowed_types) or 'nothing listed'}. Nothing else was tried."
            ) from e
        except paramiko.AuthenticationException as e:
            raise DiscoveryError("The login was refused. UNDM tried once and stops there, so "
                                 "the account is not locked by retries.") from e
        except paramiko.SSHException as e:
            raise DiscoveryError(f"The login did not complete: {_printable(str(e), 160)}") from e
        try:
            channel = transport.open_session(timeout=timeout)
            channel.settimeout(timeout)
            channel.invoke_subsystem("netconf")
        except (paramiko.SSHException, OSError) as e:
            raise DiscoveryError("The login worked, but it refused the NETCONF subsystem: "
                                 f"{_printable(str(e), 160)}") from e
        data = b""
        try:
            while EOM not in data and len(data) < HELLO_LIMIT:
                chunk = channel.recv(65536)
                if not chunk:
                    break
                data += chunk
        except (TimeoutError, OSError) as e:
            if not data:
                raise DiscoveryError("The NETCONF subsystem sent no <hello> within "
                                     f"{timeout:.0f} s.") from e
        finally:
            channel.close()
        if EOM not in data:
            raise DiscoveryError("Its <hello> did not end with the NETCONF 1.0 end mark.")
        hello = parse_hello(data)
        hello.host_key = host_key
        return hello
    finally:
        transport.close()
