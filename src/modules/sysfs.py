"""Pure /sys (and /proc/cpuinfo) sensor readers for linprocman.

Read-only sensor values for the Resources page summary chips: temperatures,
fan speeds, CPU frequency, and (AMD) GPU busy percent. No UI imports, no
state; stdlib only (``os``/``re``).

Spec: docs/modules/sysfs-data.md (binding).

Universality rule: missing hwmon / cpufreq / drm files are **normal**, not
errors. A VM with no sensors reads empty and works fine, so every reader
degrades to an empty list / ``None`` and never raises. Tests pass a fixture
tree via ``sys_root`` / ``proc_root``.
"""

import os
import re

SYS = "/sys"
PROC = "/proc"

_TEMP_INPUT = re.compile(r"temp(\d+)_input")
_FAN_INPUT = re.compile(r"fan(\d+)_input")
_CPU_DIR = re.compile(r"cpu(\d+)")
_CARD_DIR = re.compile(r"card\d+")


def _read_text(path):
    """Read a small sysfs/procfs file as stripped text, or ``None``."""
    try:
        with open(path, "r") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _to_int(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _listdir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def read_temperatures(sys_root=SYS):
    """Temperatures from ``/sys/class/hwmon/hwmon*/temp*_input`` (millidegrees).

    Label comes from the matching ``temp*_label`` file, falling back to the
    hwmon ``name``. Returns a list of ``{chip, label, celsius}`` (empty when no
    hwmon nodes exist).
    """
    base = os.path.join(sys_root, "class", "hwmon")
    result = []
    for hw in _listdir(base):
        hwdir = os.path.join(base, hw)
        chip = _read_text(os.path.join(hwdir, "name")) or hw
        for fname in _listdir(hwdir):
            match = _TEMP_INPUT.fullmatch(fname)
            if not match:
                continue
            milli = _to_int(_read_text(os.path.join(hwdir, fname)))
            if milli is None:
                continue
            label = _read_text(
                os.path.join(hwdir, "temp%s_label" % match.group(1))
            ) or chip
            result.append({
                "chip": chip,
                "label": label,
                "celsius": milli / 1000.0,
            })
    return result


def read_fans(sys_root=SYS):
    """Fan speeds (RPM) from ``/sys/class/hwmon/hwmon*/fan*_input``.

    Same shape as :func:`read_temperatures`; returns ``{chip, label, rpm}``.
    """
    base = os.path.join(sys_root, "class", "hwmon")
    result = []
    for hw in _listdir(base):
        hwdir = os.path.join(base, hw)
        chip = _read_text(os.path.join(hwdir, "name")) or hw
        for fname in _listdir(hwdir):
            match = _FAN_INPUT.fullmatch(fname)
            if not match:
                continue
            rpm = _to_int(_read_text(os.path.join(hwdir, fname)))
            if rpm is None:
                continue
            label = _read_text(
                os.path.join(hwdir, "fan%s_label" % match.group(1))
            ) or chip
            result.append({
                "chip": chip,
                "label": label,
                "rpm": rpm,
            })
    return result


def read_cpu_freq(proc_root=PROC, sys_root=SYS):
    """Current CPU frequency (MHz), per core plus min/avg/max.

    Prefers ``/proc/cpuinfo`` ``cpu MHz`` lines; falls back to
    ``/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq`` (kHz). Returns
    ``None`` when neither source is available.
    """
    freqs = []
    cpuinfo = _read_text(os.path.join(proc_root, "cpuinfo"))
    if cpuinfo:
        for line in cpuinfo.splitlines():
            if line.lower().startswith("cpu mhz"):
                _, _, value = line.partition(":")
                try:
                    freqs.append(float(value.strip()))
                except ValueError:
                    continue

    if not freqs:
        base = os.path.join(sys_root, "devices", "system", "cpu")
        for entry in _listdir(base):
            if not _CPU_DIR.fullmatch(entry):
                continue
            khz = _to_int(_read_text(
                os.path.join(base, entry, "cpufreq", "scaling_cur_freq")
            ))
            if khz is not None:
                freqs.append(khz / 1000.0)

    if not freqs:
        return None
    return {
        "per_core": freqs,
        "min": min(freqs),
        "max": max(freqs),
        "avg": sum(freqs) / len(freqs),
    }


def read_gpu_busy(sys_root=SYS):
    """AMD GPU busy percent from ``/sys/class/drm/card*/device/gpu_busy_percent``.

    Returns the first card's integer percent, or ``None`` when absent (the chip
    hides itself elsewhere; never an error).
    """
    base = os.path.join(sys_root, "class", "drm")
    for card in _listdir(base):
        if not _CARD_DIR.fullmatch(card):
            continue
        value = _to_int(_read_text(
            os.path.join(base, card, "device", "gpu_busy_percent")
        ))
        if value is not None:
            return value
    return None


def _to_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def usb_devices(sys_root=SYS):
    """Enumerate connected USB devices from <sys_root>/bus/usb/devices.

    Returns a list of dicts, one per DEVICE (entries whose name contains
    ':' are interfaces and are skipped). Dict shape:
      'name':        str -- product string, or 'USB device' when absent
      'vendor_id':   str|None -- idVendor, 4 hex chars
      'product_id':  str|None -- idProduct, 4 hex chars
      'manufacturer':str|None
      'product':     str|None
      'serial':      str|None
      'bus':         int|None -- busnum
      'port':        int|None -- devnum
      'speed_mbps':  float|None -- speed file (e.g. '480', '5000')
      'removable':   str -- 'removable' | 'fixed' | 'unknown' (file value;
                     missing file -> 'unknown')
    Order: sorted by (bus, port) with None-safe keys.
    """
    base = os.path.join(sys_root, "bus", "usb", "devices")
    result = []
    for entry in _listdir(base):
        if ":" in entry:
            continue  # interface node (e.g. "1-0:1.0"), not a device
        devdir = os.path.join(base, entry)
        product = _read_text(os.path.join(devdir, "product"))
        result.append({
            "name": product or "USB device",
            "vendor_id": _read_text(os.path.join(devdir, "idVendor")),
            "product_id": _read_text(os.path.join(devdir, "idProduct")),
            "manufacturer": _read_text(os.path.join(devdir, "manufacturer")),
            "product": product,
            "serial": _read_text(os.path.join(devdir, "serial")),
            "bus": _to_int(_read_text(os.path.join(devdir, "busnum"))),
            "port": _to_int(_read_text(os.path.join(devdir, "devnum"))),
            "speed_mbps": _to_float(_read_text(os.path.join(devdir, "speed"))),
            "removable": _read_text(
                os.path.join(devdir, "removable")
            ) or "unknown",
        })

    def _key(dev):
        bus, port = dev["bus"], dev["port"]
        return (bus is None, bus or 0, port is None, port or 0)

    result.sort(key=_key)
    return result
