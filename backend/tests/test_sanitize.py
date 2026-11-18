from fake_netmiko import AOS_SWITCH_SHOW_MODULES, AOS_SWITCH_SHOW_SYSTEM, IOSXE_SHOW_VERSION

from undm.security.sanitize import new_mapper, sanitize


def test_masks_ips_macs_serials_names_but_keeps_versions():
    text = AOS_SWITCH_SHOW_SYSTEM + "\n mgmt 10.255.0.21/24 gw 10.255.0.1 peer 0011.2233.4455\n"
    out = sanitize(text, [("hostname", "lab-2930f")])
    for secret in ("lab-2930f", "001122-334455", "CN00TEST01", "10.255.0.21", "0011.2233.4455"):
        assert secret not in out, secret
    assert "WC.16.10.0012" in out and "WC.17.02.0006" in out  # versions untouched
    assert "<ip-1>" in out and "<mac-1>" in out and "<serial-1>" in out


def test_same_value_gets_same_placeholder_across_texts():
    m = new_mapper()
    a = sanitize(AOS_SWITCH_SHOW_SYSTEM, (), m)
    b = sanitize(AOS_SWITCH_SHOW_MODULES, (), m)
    assert "<serial-1>" in a and "<serial-1>" in b and "CN00TEST01" not in a + b


def test_cisco_board_id_and_secrets():
    out = sanitize(IOSXE_SHOW_VERSION + "enable secret 5 $1$abcd$xyz\n")
    assert "FDO0000TEST" not in out and "$1$abcd" not in out
    assert "17.09.04a" in out


def test_empty_labels_do_not_swallow_next_line():
    text = "  System Contact     :\n  System Location    : Building 7, Room 2\n"
    out = sanitize(text)
    assert "System Contact     :\n  System Location    : <name-1>" in out
    assert "Building 7" not in out


def test_known_serial_and_label_share_one_placeholder():
    m = new_mapper()
    a = sanitize("serial_number: SG00FAKE01", [("serial", "SG00FAKE01")], m)
    b = sanitize("  ROM Version : WC.16.01.0010   Serial Number : SG00FAKE01  \n",
                 [("serial", "SG00FAKE01")], m)
    assert "<serial-1>" in a and "<serial-1>" in b and "<serial-2>" not in b
