"""What management services a device offers (D-130). Read-only: without a login nothing is
sent on SSH or NETCONF and no HTTP request on HTTPS; the NETCONF <hello> is read with one
login and no request. Servers here run on this PC's loopback; no device is contacted, and
every answer is SYNTHETIC."""

import contextlib
import datetime as dt
import socket
import ssl
import threading

import keyring
import paramiko
import pytest
from api_helpers import make_client
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from memory_keyring import MemoryKeyring

from undm.drivers import discovery
from undm.drivers.base import Credentials, DeviceTarget
from undm.drivers.nokia.flexi import NokiaFlexiGuided

HELLO = (b'<?xml version="1.0" encoding="UTF-8"?>\n'
         b'<hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"><capabilities>'
         b"<capability>urn:ietf:params:netconf:base:1.0</capability>"
         b"<capability>urn:ietf:params:netconf:base:1.1</capability>"
         b"<capability>urn:example:abc:sw?module=abc-software&amp;revision=2026-01-01"
         b"</capability>"
         b"<capability>urn:ietf:params:netconf:capability:yang-library:1.0?revision=2016-06-21"
         b"&amp;module-set-id=1</capability>"
         b"</capabilities><session-id>42</session-id></hello>]]>]]>")


class FakeSocket:
    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.sent = b""
        self.closed = False

    def settimeout(self, t):
        pass

    def recv(self, n):
        if not self.chunks:
            raise TimeoutError("timed out")
        return self.chunks.pop(0)

    def send(self, data):
        self.sent += data
        return len(data)

    sendall = send

    def close(self):
        self.closed = True


def test_ports_are_read_without_sending_anything(monkeypatch):
    sockets = {22: FakeSocket([b"Welcome\r\n", b"SSH-2.0-AbcSSH_1.0\r\n"]),
               830: FakeSocket([b"SSH-2.0-AbcNetconf\r\n"])}
    seen: list[int] = []

    def fake_connect(address, timeout):
        seen.append(address[1])
        if address[1] == 443:
            return FakeSocket()
        if address[1] in sockets:
            return sockets[address[1]]
        raise ConnectionRefusedError

    monkeypatch.setattr(discovery, "connect", fake_connect)
    monkeypatch.setattr(discovery, "read_tls_certificate",
                        lambda sock, host: ({"subject": "CN=abc-bbu.example"}, ""))
    answers = {a.port: a for a in discovery.probe("198.51.100.9")}
    assert seen == [22, 443, 830]
    assert answers[22].banner == "SSH-2.0-AbcSSH_1.0" and answers[22].open
    assert answers[830].banner == "SSH-2.0-AbcNetconf"
    assert answers[443].certificate == {"subject": "CN=abc-bbu.example"}
    assert all(s.sent == b"" and s.closed for s in sockets.values())  # nothing was sent


def test_closed_ports_and_silent_ports(monkeypatch):
    def fake_connect(address, timeout):
        if address[1] == 22:
            return FakeSocket()  # accepts, says nothing
        raise ConnectionRefusedError

    monkeypatch.setattr(discovery, "connect", fake_connect)
    answers = {a.port: a for a in discovery.probe("198.51.100.9")}
    assert answers[22].open and answers[22].banner is None
    assert "sent nothing" in answers[22].note
    assert not answers[443].open and not answers[830].open
    assert "No connection" in answers[830].note


def test_a_banner_that_is_not_ssh_is_shown_not_trusted():
    banner, note = discovery.read_ssh_banner(FakeSocket([b"HTTP/1.1 400 Bad\r\n\r\n"]))
    assert banner is None and "HTTP/1.1 400" in note


def _self_signed(cn: str) -> tuple[bytes, bytes]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = dt.datetime.now(dt.UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30)).sign(key, hashes.SHA256()))
    return (cert.public_bytes(serialization.Encoding.PEM),
            key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()))


def test_the_portal_certificate_is_read_in_the_handshake_only(tmp_path):
    cert_pem, key_pem = _self_signed("abc-bbu.example")
    (tmp_path / "c.pem").write_bytes(cert_pem)
    (tmp_path / "k.pem").write_bytes(key_pem)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tmp_path / "c.pem", tmp_path / "k.pem")
    server = socket.create_server(("127.0.0.1", 0))
    received: list[bytes] = []

    def serve():
        conn, _ = server.accept()
        try:
            with context.wrap_socket(conn, server_side=True) as tls:
                tls.settimeout(2)
                with contextlib.suppress(TimeoutError, ssl.SSLError, OSError):
                    received.append(tls.recv(1024))
        except (ssl.SSLError, OSError):
            pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    sock = socket.create_connection(server.getsockname(), timeout=3)
    cert, note = discovery.read_tls_certificate(sock, "127.0.0.1")
    t.join(5)
    server.close()
    assert note == "" and cert is not None
    assert cert["subject"] == "CN=abc-bbu.example" and cert["issuer"] == "CN=abc-bbu.example"
    assert len(cert["sha256"]) == 64
    assert received in ([], [b""])  # no HTTP request reached the server


def test_parse_hello_lists_capabilities_and_modules():
    hello = discovery.parse_hello(HELLO)
    assert hello.session_id == "42" and hello.base_versions == ["1.0", "1.1"]
    assert hello.modules == [{"name": "abc-software", "namespace": "urn:example:abc:sw",
                              "revision": "2026-01-01"}]
    assert "YANG library" in hello.note


def test_parse_hello_refuses_doctype_and_other_messages():
    with pytest.raises(discovery.DiscoveryError, match="DOCTYPE"):
        discovery.parse_hello(b'<!DOCTYPE x [<!ENTITY a "b">]><hello/>]]>]]>')
    with pytest.raises(discovery.DiscoveryError, match="not a NETCONF"):
        discovery.parse_hello(b"<rpc-reply/>]]>]]>")


class NetconfServer(paramiko.ServerInterface):
    def __init__(self, password):
        self.password = password
        self.attempts = 0
        self.subsystems: list[str] = []

    def get_allowed_auths(self, username):
        return "password"

    def check_auth_password(self, username, password):
        self.attempts += 1
        return (paramiko.AUTH_SUCCESSFUL if password == self.password
                else paramiko.AUTH_FAILED)

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED

    def check_channel_subsystem_request(self, channel, name):
        self.subsystems.append(name)
        return name == "netconf"


HOST_KEY = paramiko.RSAKey.generate(2048)


def run_server(handler, hello=HELLO):
    server = socket.create_server(("127.0.0.1", 0))
    received: list[bytes] = []

    def serve():
        conn, _ = server.accept()
        t = paramiko.Transport(conn)
        t.add_server_key(HOST_KEY)
        try:
            t.start_server(server=handler)
            chan = t.accept(5)
            if chan is not None:
                chan.sendall(hello)
                chan.settimeout(1)
                with contextlib.suppress(TimeoutError, OSError):
                    received.append(chan.recv(4096))
        except (paramiko.SSHException, EOFError, OSError):
            pass
        finally:
            t.close()
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return server.getsockname()[1], received, thread


def test_netconf_hello_is_read_with_one_login_and_no_request():
    handler = NetconfServer("Example-Only-7")
    port, received, thread = run_server(handler)
    hello = discovery.netconf_hello("127.0.0.1", port, "admin", "Example-Only-7", timeout=5)
    thread.join(5)
    assert hello.session_id == "42" and "abc-software" in [m["name"] for m in hello.modules]
    assert hello.host_key.startswith("ssh-rsa SHA256:")
    assert handler.attempts == 1 and handler.subsystems == ["netconf"]
    assert received in ([], [b""])  # UNDM sent nothing on the NETCONF channel


def test_a_refused_login_is_tried_once():
    handler = NetconfServer("Example-Only-7")
    port, _, thread = run_server(handler)
    with pytest.raises(discovery.DiscoveryError, match="tried once"):
        discovery.netconf_hello("127.0.0.1", port, "admin", "wrong-Example", timeout=5)
    thread.join(5)
    assert handler.attempts == 1


def test_the_real_driver_reads_its_ports(monkeypatch):
    monkeypatch.setattr(discovery, "connect",
                        lambda address, timeout: (_ for _ in ()).throw(ConnectionRefusedError()))
    d = NokiaFlexiGuided(DeviceTarget("b", "192.168.255.1"))
    r = d.discover_services()
    assert r.ok and [p["open"] for p in r.data["ports"]] == [False, False, False]
    assert r.data["simulated"] is False
    hello = d.netconf_hello(Credentials("admin", "Example-Only-7"))
    assert not hello.ok and "No connection" in hello.message


# -- the service and API ---------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    c, _ = make_client(data_dir=str(tmp_path))
    with c:
        yield c
    keyring.set_keyring(previous)


def bbu(c, *, real=False, environment=None):
    pid = c.post("/api/projects", json={"name": "Practice B009"}).json()["id"]
    body = {"name": "abc-bbu", "manufacturer": "Nokia", "category": "other",
            "driver_id": "guided.nokia.flexi" if real else "mock.nokia.flexi",
            "management_address": "192.168.255.1"}
    if real:
        body["environment"] = environment or "lab"
    did = c.post(f"/api/projects/{pid}/devices", json=body).json()["id"]
    ref = c.post(f"/api/projects/{pid}/credential-refs", json={"name": "bbu-login"}).json()
    c.put(f"/api/credential-refs/{ref['id']}/secret",
          json={"username": "admin", "password": "Example-Only-7"})
    return pid, did, ref["id"]


def test_simulated_reading_is_kept_and_audited(client):
    pid, did, ref = bbu(client)
    assert client.get(f"/api/devices/{did}/services").json() == {}
    r = client.post(f"/api/devices/{did}/services/netconf-hello",
                    json={"credential_ref_id": ref})
    assert r.status_code == 409 and "first" in r.json()["error"]
    out = client.post(f"/api/devices/{did}/services/discover").json()
    assert out["simulated"] and [p["port"] for p in out["ports"] if p["open"]] == [443, 830]
    hello = client.post(f"/api/devices/{did}/services/netconf-hello",
                        json={"credential_ref_id": ref}).json()
    assert hello["ok"] and hello["login"] == "bbu-login" and hello["simulated"]
    kept = client.get(f"/api/devices/{did}/services").json()
    assert set(kept) == {"services", "netconf_hello"}
    actions = [e["action"] for e in client.get("/api/audit").json()]
    assert "device.discover_services" in actions and "device.netconf_hello" in actions
    assert "Example-Only-7" not in str(client.get("/api/audit").json())


def test_a_login_of_another_system_is_refused(client):
    pid, did, _ = bbu(client)
    other = client.post("/api/projects", json={"name": "Practice B010"}).json()["id"]
    ref = client.post(f"/api/projects/{other}/credential-refs", json={"name": "x"}).json()
    client.post(f"/api/devices/{did}/services/discover")
    r = client.post(f"/api/devices/{did}/services/netconf-hello",
                    json={"credential_ref_id": ref["id"]})
    assert r.status_code == 409 and "another system" in r.json()["error"]


def test_the_operations_endpoint_sends_it_to_its_own_place(client):
    _, did, _ = bbu(client)
    r = client.post(f"/api/devices/{did}/operations/discover_services")
    assert r.status_code == 409 and "Find its management services" in r.json()["error"]


def test_a_model_without_it_says_so(client):
    pid = client.post("/api/projects", json={"name": "Practice B011"}).json()["id"]
    sw = client.post(f"/api/projects/{pid}/devices", json={
        "name": "abc-sw", "manufacturer": "Aruba", "category": "switch",
        "driver_id": "mock.aruba.aos_switch", "management_address": "192.0.2.1"}).json()["id"]
    r = client.post(f"/api/devices/{sw}/services/discover")
    assert r.status_code == 409 and "no management services" in r.json()["error"]


def test_the_real_bbu_is_read_on_the_bench(client, monkeypatch):
    monkeypatch.setattr(discovery, "connect",
                        lambda address, timeout: (_ for _ in ()).throw(ConnectionRefusedError()))
    _, did, _ = bbu(client, real=True)
    out = client.post(f"/api/devices/{did}/services/discover").json()
    assert out["simulated"] is False and not any(p["open"] for p in out["ports"])


def test_a_production_bbu_needs_the_start_up_setting(client):
    _, did, _ = bbu(client, real=True, environment="production")
    r = client.post(f"/api/devices/{did}/services/discover")
    assert r.status_code == 403 and "UNDM_ALLOW_PRODUCTION_READ_ONLY" in r.json()["error"]
