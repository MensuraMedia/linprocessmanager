# Module doc — performance thresholds & first-run baseline (`src/modules/manager_baseline.py`)

Part of the linprocman modular docs. Siblings: [sampling-pipeline.md](sampling-pipeline.md) ·
[process-table.md](process-table.md) · [resource-graphs.md](resource-graphs.md) ·
[graphs-hub.md](graphs-hub.md) · [metric-band-basics.md](metric-band-basics.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

Status: implemented r071 (operator mandate: threshold color-alerting derived
from the actual machine, not fixed percentages; first-run baseline).

## 1. Why baselines

Fixed thresholds (60/85) treat a 4-core 8 GB laptop and a 16-core 128 GB
workstation identically — wrong on both. The app measures the machine at
first run, derives per-metric thresholds from formulae over those specs,
and stores them. Every zone color (green/amber/red) then comes from the
baseline, and Settings offers "Recalibrate".

## 2. First-run baseline capture

Captured once (stored in settings.json under `baseline`), re-runnable from
Settings ▸ Recalibrate:

| Measured | Source | Duration |
|---|---|---|
| ncpu, per-core max freq | `/proc/cpuinfo`, `/sys/.../cpufreq` | instant |
| MemTotal, SwapTotal | `/proc/meminfo` | instant |
| **Idle CPU noise floor** | 12 samples of total CPU% at 500 ms while the user is not interacting | ~6 s, first run only |
| Disk devices + types | `/proc/diskstats` + `/sys/block/*/queue/rotary` | instant |
| Kernel + virtualization hints | `uname`, `/proc/xen\|hypervisor` presence | instant |

The idle noise floor is the calibration anchor: a machine that idles at
8% (desktop services) has a different "nominal" than one idling at 1%.

## 3. Threshold formulae (pure functions, fixture-tested)

All thresholds live in `Thresholds` (a plain dict-like), derived by
`derive(specs, idle_samples)`:

```
cpu_yellow = clamp(idle_p90 + 12, 20, 45)      # nominal headroom over noise
cpu_red    = clamp(idle_p90 * 4 + 20, 55, 85)

mem_yellow = 55 + ram_gb            # +1%/GB over 8 GB, capped
mem_red    = mem_yellow + 25        # …capped 95
    ram_gb <= 4  -> mem_yellow = 50, mem_red = 80   (small-RAM: alert early)
    ram_gb >= 32 -> mem_yellow = 75, mem_red = 90   (large-RAM: % is cheap)

swap_red   = 20 if ram_gb >= 16 else 10          # swapping at all is a smell
                                        # on big-RAM boxes; expected on small
disk_red   = 85 (HDD) / 60 (SSD/NVMe)    # SSDs hurt at high util (latency);
                                         # HDDs are expected to sit high
net_alert  = 80% of the auto-scale ceiling
load_red   = ncpu * 1.5                  # 1-min load vs cores
```

Zones for display: `< yellow` nominal (green) · `≥ yellow` amber ·
`≥ red` critical (red). The r056/r057 display rules are unchanged — only
the *numbers* become machine-derived.

## 4. Runtime shape

- `manager_baseline.capture()` — pure-ish: reads via procfs/sysfs readers +
  one short CPU sampling loop (sampler-thread friendly, no GTK).
- `manager_baseline.derive(specs, idle_samples) -> Thresholds` — pure,
  fixture-tested.
- `Thresholds.get(metric, level)` — the single provider the pages'
  `_cap_zone`-style helpers consult; falls back to the fixed defaults when
  no baseline exists yet (first 6 seconds of first run).
- Stored in settings.json (`baseline: {specs, thresholds, captured_at,
  schema: 1}`) — persistence-config.md schema gains the key; validation
  clamps hostile values.

## 5. Recalibration & honesty

- Settings ▸ "Recalibrate baseline" re-runs capture (asks the user to
  leave the machine idle ~6 s).
- The Basics/Band zone captions state the thresholds in effect
  ("nominal < 27% · amber ≥ 27% · critical ≥ 52%") — the operator can
  always see what the machine claimed.
- Idle calibration is skipped (defaults used) when user input occurred
  during the sampling window — a noisy baseline is worse than defaults.

## 6. Tests

derive() fixture table (8 GB/16 GB/32 GB/128 GB × idle floors 1–15),
clamp edges, Thresholds.get fallback, persistence round-trip + hostile
clamping, capture smoke (live marker).
