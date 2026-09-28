# Task 012a — USB device enumeration reader (`sysfs.usb_devices`)

You are the executor for this task in the linprocman project
(/home/user/projects/linprocman). ZCode has frozen the interface and will
integrate it into the Peripherals page. Work precisely; read before writing.

## Hard constraints

- Touch EXACTLY two files:
  - `src/modules/sysfs.py` — APPEND one public function `usb_devices`
    (plus any private helpers it needs, styled like the existing ones).
    Change NOTHING else in the file.
  - `tests/test_sysfs_usb.py` — NEW test file.
- Do NOT run git commands. Do NOT create CLAUDE.md or .claude/ paths.
- Standard library only; NO gi imports (sysfs.py is a core module: UI-free,
  headlessly testable — boundary law).
- Missing files/dirs are NORMAL, never errors (universality mandate):
  a machine section absent from the tree yields missing/None fields, an
  absent bus yields an empty list.

## Context to read first

- `src/modules/sysfs.py` — existing reader style: `_read_text`, `_to_int`,
  `_listdir`, injectable roots, per-entry try/except.
- `tests/test_sysfs.py` — fixture style (tmp_path sysfs trees).

## Frozen interface

```python
def usb_devices(sys_root=SYS):
    """Enumerate connected USB devices from <sys_root>/bus/usb/devices.

    Returns a list of dicts, one per DEVICE (entries whose name contains
    ':' are interfaces and are skipped). Dict shape:
      'name':        str — product string, or 'USB device' when absent
      'vendor_id':   str|None — idVendor, 4 hex chars
      'product_id':  str|None — idProduct, 4 hex chars
      'manufacturer':str|None
      'product':     str|None
      'serial':      str|None
      'bus':         int|None — busnum
      'port':        int|None — devnum
      'speed_mbps':  float|None — speed file (e.g. '480', '5000')
      'removable':   str — 'removable' | 'fixed' | 'unknown' (file value;
                     missing file -> 'unknown')
    Order: sorted by (bus, port) with None-safe keys.
    """
```

## Tests to deliver (`tests/test_sysfs_usb.py`, pytest, tmp_path fixtures)

Build a fake sysfs tree and cover at minimum:

- Two well-formed devices (all fields present) → parsed exactly, sorted by
  (bus, port).
- An interface entry (`1-0:1.0` style, name containing ':') is skipped.
- A minimal device (only idVendor/idProduct) → the rest None /
  'USB device' / 'unknown'.
- Absent bus directory → [].
- Numeric coercion: busnum/devnum ints, speed float, junk speed → None.
- No exceptions on permission-less/empty dirs (empty dirs in the tree).

Do not run anything; ZCode executes the suite. When done, print a short
summary (files written, test count, interpretation calls).
