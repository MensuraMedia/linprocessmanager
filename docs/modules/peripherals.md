# Module doc — Peripherals (`src/pages/page_peripherals.py`)

Part of the linprocman modular docs. Siblings:
[sysfs-data.md](sysfs-data.md) (the sensor readers this page consumes) ·
[disks-filesystems.md](disks-filesystems.md) · [disks-capacity.md](disks-capacity.md) ·
[procfs-data.md](procfs-data.md). Overview:
[../process-manager-concept.md](../process-manager-concept.md).

Shipped r092 (operator): a Peripherals sidebar entry (between Disks and
Logs) whose page lists ALL detected connected devices — any and all USB
devices included — with info cards, sensor info-bars, and a Refresh button
so newly plugged hardware appears without a restart.

## Purpose

One page answering "what is plugged into this machine, and what are its
sensors reading?" — read-only, /sys-only, offline.

## Data sources (all existing or appended to `modules/sysfs.py`)

| Data | Source | Notes |
|---|---|---|
| USB devices | `sysfs.usb_devices()` → `/sys/bus/usb/devices/*` | device nodes only (interface nodes, name containing `:`, are skipped); product/manufacturer/serial strings, `idVendor:idProduct`, `busnum`/`devnum`, `speed`, `removable` |
| Temperatures | `sysfs.read_temperatures()` | hwmon `temp*_input` + labels |
| Fans | `sysfs.read_fans()` | hwmon `fan*_input` RPM |
| CPU frequency | `sysfs.read_cpu_freq()` | min/max/avg MHz (+ per-core list) |
| GPU busy | `sysfs.read_gpu_busy()` | first amdgpu card's integer percent or None |

`usb_devices` was executor-built to a frozen contract
(`.zcode/tasks/012-peripherals-usb.md`): device dicts with `name, vendor_id,
product_id, manufacturer, product, serial, bus, port, speed_mbps,
removable`; missing attributes are `None` and the page renders `—` (r039
taxonomy); absent bus → `[]` (universality mandate — nothing to list is a
normal machine).

## Page structure

1. **Refresh button** (toolbar row) — re-runs `refresh()`: clears the
   tracked-children device and sensor sections and rebuilds them from a
   fresh `/sys` scan. Rebuilt subtrees reveal per-widget (`show_all` is
   gate-banned; the basics tracked-children pattern is used — no
   `get_children`, no raw `add`).
2. **Connected devices** — a FlowBox grid of fixed-size cards (360×118,
   bounding-box policy §5b): product name + removable badge, manufacturer,
   `USB ID` as `vendor:product`, location `bus N · port M · S Mbps`.
   Empty state: "No USB devices detected — connect one and press Refresh."
3. **Sensors** — fixed 220×84 chips: temperature (°C + accent mini-bar,
   fill = °C/100), fan RPM, CPU frequency span, GPU busy % with bar.
   Mini-bars use the SINGLE accent color (r088 consistency rule).
   No sensors → "No sensors found — normal on VMs."

## Rules

- Boundary law: the page calls sysfs readers only; readers stay UI-free.
- No new sampling cadence: Peripherals scans on build + manual Refresh
  (sensor CONTINUITY lives on the Graphs pages; this page is a live
  snapshot view, not a history surface).
- Every toolkit call through the compat seams; `FlowBox.insert` for flow
  children (FlowBox has no pack_start).
- Hot-plug without Refresh is out of scope for v1 — udev/Gio.UnixMountMonitor
  integration is a documented v2 follow-up (disks-filesystems.md owns mount
  events; device-level hotplug would reuse the same monitor).

## Tests

`tests/test_sysfs_usb.py` (7, executor-written): well-formed devices sorted
by (bus, port), interface nodes skipped, minimal device degradation to
None/'unknown', absent bus → [], numeric coercion incl. junk speed → None,
empty/permission-less dirs raise nothing. Page build + refresh round-trip is
covered by the UI tier (build window, navigate, assert cards exist).
