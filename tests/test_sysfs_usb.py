"""Fixture tests for sysfs.usb_devices().

Fake <sys_root>/bus/usb/devices trees built under tmp_path: well-formed
devices sorted by (bus, port), interface nodes skipped, minimal devices
degrading to None/'USB device'/'unknown', numeric coercion, and graceful
handling of absent/empty directories (universality mandate).
"""

import os

import sysfs


def _write(path, text):
    with open(path, "w") as handle:
        handle.write(text)


def _make_device(base, name, fields):
    """Create <base>/<name>/ with one file per field mapping."""
    devdir = os.path.join(base, name)
    os.makedirs(devdir)
    for fname, value in fields.items():
        _write(os.path.join(devdir, fname), value)
    return devdir


def _usb_base(sys_root):
    base = os.path.join(sys_root, "bus", "usb", "devices")
    os.makedirs(base)
    return base


# ---------------------------------------------------------------------------
# well-formed devices, sorted by (bus, port)
# ---------------------------------------------------------------------------

def test_two_well_formed_devices_sorted(tmp_path):
    sys_root = str(tmp_path)
    base = _usb_base(sys_root)
    # Deliberately create the higher (bus, port) first so sort must reorder.
    _make_device(base, "2-1", {
        "idVendor": "8087", "idProduct": "0024",
        "manufacturer": "Intel Corp.", "product": "Integrated Hub",
        "serial": "HUB123", "busnum": "2", "devnum": "4",
        "speed": "5000", "removable": "fixed",
    })
    _make_device(base, "1-1", {
        "idVendor": "046d", "idProduct": "c52b",
        "manufacturer": "Logitech", "product": "Unifying Receiver",
        "serial": "ABC001", "busnum": "1", "devnum": "3",
        "speed": "12", "removable": "removable",
    })

    devs = sysfs.usb_devices(sys_root=sys_root)
    assert [(d["bus"], d["port"]) for d in devs] == [(1, 3), (2, 4)]

    first = devs[0]
    assert first["name"] == "Unifying Receiver"
    assert first["vendor_id"] == "046d"
    assert first["product_id"] == "c52b"
    assert first["manufacturer"] == "Logitech"
    assert first["product"] == "Unifying Receiver"
    assert first["serial"] == "ABC001"
    assert first["bus"] == 1
    assert first["port"] == 3
    assert first["speed_mbps"] == 12.0
    assert first["removable"] == "removable"

    second = devs[1]
    assert second["name"] == "Integrated Hub"
    assert second["vendor_id"] == "8087"
    assert second["speed_mbps"] == 5000.0
    assert second["removable"] == "fixed"


# ---------------------------------------------------------------------------
# interface nodes (name contains ':') are skipped
# ---------------------------------------------------------------------------

def test_interface_entry_skipped(tmp_path):
    sys_root = str(tmp_path)
    base = _usb_base(sys_root)
    _make_device(base, "1-1", {
        "idVendor": "046d", "idProduct": "c52b",
        "busnum": "1", "devnum": "3",
    })
    # An interface node: real names look like "1-0:1.0".
    _make_device(base, "1-0:1.0", {
        "idVendor": "dead", "idProduct": "beef",
        "busnum": "1", "devnum": "1",
    })

    devs = sysfs.usb_devices(sys_root=sys_root)
    assert len(devs) == 1
    assert devs[0]["vendor_id"] == "046d"


# ---------------------------------------------------------------------------
# minimal device -> everything else None / 'USB device' / 'unknown'
# ---------------------------------------------------------------------------

def test_minimal_device_degrades(tmp_path):
    sys_root = str(tmp_path)
    base = _usb_base(sys_root)
    _make_device(base, "1-1", {
        "idVendor": "1d6b", "idProduct": "0002",
    })

    devs = sysfs.usb_devices(sys_root=sys_root)
    assert len(devs) == 1
    dev = devs[0]
    assert dev["vendor_id"] == "1d6b"
    assert dev["product_id"] == "0002"
    assert dev["name"] == "USB device"
    assert dev["manufacturer"] is None
    assert dev["product"] is None
    assert dev["serial"] is None
    assert dev["bus"] is None
    assert dev["port"] is None
    assert dev["speed_mbps"] is None
    assert dev["removable"] == "unknown"


# ---------------------------------------------------------------------------
# absent bus directory -> []
# ---------------------------------------------------------------------------

def test_absent_bus_dir_is_empty(tmp_path):
    # tmp_path exists but has no bus/usb/devices subtree.
    assert sysfs.usb_devices(sys_root=str(tmp_path)) == []


def test_missing_sys_root_is_empty(tmp_path):
    missing = os.path.join(str(tmp_path), "does_not_exist")
    assert sysfs.usb_devices(sys_root=missing) == []


# ---------------------------------------------------------------------------
# numeric coercion: ints, float, junk speed -> None
# ---------------------------------------------------------------------------

def test_numeric_coercion(tmp_path):
    sys_root = str(tmp_path)
    base = _usb_base(sys_root)
    _make_device(base, "1-1", {
        "idVendor": "046d", "idProduct": "c52b",
        "busnum": "1", "devnum": "7",
        "speed": "480", "removable": "fixed",
    })
    _make_device(base, "1-2", {
        "idVendor": "046d", "idProduct": "c53f",
        "busnum": "1", "devnum": "8",
        "speed": "not-a-number",
    })

    devs = sysfs.usb_devices(sys_root=sys_root)
    by_port = {d["port"]: d for d in devs}

    good = by_port[7]
    assert isinstance(good["bus"], int) and good["bus"] == 1
    assert isinstance(good["port"], int) and good["port"] == 7
    assert isinstance(good["speed_mbps"], float) and good["speed_mbps"] == 480.0

    junk = by_port[8]
    assert junk["speed_mbps"] is None


# ---------------------------------------------------------------------------
# no exceptions on empty device dirs
# ---------------------------------------------------------------------------

def test_empty_device_dir_no_exception(tmp_path):
    sys_root = str(tmp_path)
    base = _usb_base(sys_root)
    # A device directory with no files at all.
    os.makedirs(os.path.join(base, "1-1"))
    # And a completely empty bus root alongside it is also fine.

    devs = sysfs.usb_devices(sys_root=sys_root)
    assert len(devs) == 1
    dev = devs[0]
    assert dev["name"] == "USB device"
    assert dev["vendor_id"] is None
    assert dev["bus"] is None
    assert dev["removable"] == "unknown"
