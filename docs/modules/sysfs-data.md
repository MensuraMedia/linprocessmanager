# Module doc — sysfs sensors (`src/modules/sysfs.py`)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [process-table.md](process-table.md) ·
[actions-permissions.md](actions-permissions.md) · [resource-graphs.md](resource-graphs.md) ·
[persistence-config.md](persistence-config.md) · [logs-journal.md](logs-journal.md) ·
[disks-filesystems.md](disks-filesystems.md). Overview: [../process-manager-concept.md](../process-manager-concept.md).

Added by the r039 adversarial feature pass (P2, phase 5): temperature is the
most-requested sensor on laptops; CPU frequency is one file. Exists because
build-principles §4 was amended (additively) to read /proc **and** /sys.

## Purpose

Read-only sensor values for the Resources page summary chips:

| Data | Source | Notes |
|---|---|---|
| temperatures | `/sys/class/hwmon/hwmon*/temp*_input` + `temp*_label` | °C millidegrees; label fallback = hwmon `name`; chips only, no graphs in v1 |
| fan speeds | `/sys/class/hwmon/hwmon*/fan*_input` + `fan*_label` | RPM; same reader shape as temps — near-zero cost (r042) |
| CPU frequency | `/proc/cpuinfo` (`cpu MHz`) or `/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq` | per-core current, min/avg/max shown |
| GPU usage (AMD only, degrade elsewhere) | `/sys/class/drm/card*/device/gpu_busy_percent` | amdgpu first; absent file → chip hidden, no error |

## Rules

- Missing hwmon/cpufreq files are **normal**, not errors — chips hide
  themselves (universality mandate: a VM with no hwmon shows nothing, works
  fine).
- Sampled by the existing sampler thread alongside /proc reads — no extra
  cadence. Pure functions, fixture-tested (hwmon tree fixtures).
