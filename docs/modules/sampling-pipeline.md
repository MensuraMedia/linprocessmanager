# Module doc — sampling pipeline (`src/modules/manager_sampler.py`)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[process-table.md](process-table.md) · [actions-permissions.md](actions-permissions.md) ·
[resource-graphs.md](resource-graphs.md) · [persistence-config.md](persistence-config.md) ·
[logs-journal.md](logs-journal.md) · [disks-filesystems.md](disks-filesystems.md) ·
[sysfs-data.md](sysfs-data.md). Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

Owns timing. Turns procfs+sysfs reads into immutable `Snapshot` objects on a
fixed cadence and hands them to the GTK main thread — the only bridge
between the kernel-reading world and the UI world. Consumers never read the
kernel.

## Interface

Provides:
- `Sampler.start()` / `stop()` / `set_interval(seconds)`
- `Snapshot` schema: `{"ts": float, "procs": {pid: record}, "system": {cpu, mem, net, psi, disks, sensors}}`
  — records carry **precomputed** `cpu_pct` (chosen normalization), byte
  rates for io, and raw identity fields. Rates are computed here, at build
  time, from the previous snapshot held in the sampler; consumers render,
  they never differentiate.
- Queue: bounded small (e.g. 4 slots), `put_nowait` + **drop-oldest** on
  full; the UI drains via **one persistent GLib idle source** (no per-
  snapshot `idle_add` pileup).

Consumes: [procfs-data.md](procfs-data.md) and [sysfs-data.md](sysfs-data.md)
readers only.

## Logic

- **Cadence (settled r039):** the sampler period **is** the configured
  refresh interval (0.5–5 s, default 2 s). Every snapshot is applied by the
  graphs and the details pane; the table applies every snapshot too — there
  is no second decimation stage. Rings are sized for ~5 min of *current*
  history at the chosen period (300/period samples). Changing the interval
  clears rate baselines for one sample.
- **Watchdog (adversarial fix):** the whole loop runs under a top-level
  try/except that logs and continues; a consecutive-failure counter stops
  the thread cleanly after N failures. The UI checks snapshot age every few
  seconds and raises a "sampling stalled" banner — stale data is never
  silently presented as live.
- **Backoff:** while the window is inactive, sample every 10 s to keep
  identities/deltas warm — backoff keys on **iconified/withdrawn +
  `is_active` state, not occlusion** (Wayland does not expose occlusion;
  documented limitation: an occluded-but-visible Wayland window samples at
  full cadence — X11 behaves fully). Backoff samples are **excluded from
  chart rings** (timestamped rings; a gap renders as a gap).
- **Pause:** full stop (the simple option); on resume, one sample of "—"
  for rate fields while deltas re-arm. Honest absence, never 0.0.

## Rate math (computed here, not in the UI)

```
cpu%       = Δ(utime + stime) / (CLK_TCK × Δwall) × 100   # 100% = one core
cpu%_total = cpu% / ncpu                                   # 100% = whole machine
```

- **Δwall guard:** if Δwall < one sampler period (clock weirdness, double
  tick), skip the sample's rate fields — never divide by ~0.
- **PID-recycling guard on deltas (r042 fix):** per-process rate deltas are
  computed only when `starttime` matches the previous snapshot — a recycled
  PID yields a mismatch and the record emits no-data for that interval
  (re-arms like a first sample). The actions guard and the rate guard now
  share one identity rule: **(pid, starttime) everywhere, pid never alone.**
- **Counter-reset rule (net, disk io):** a negative delta means the counter
  reset (interface down/up, 32-bit wrap) → emit no-data for that interval,
  not 0 and not garbage.
- Per-core normalization is the default; whole-machine is a settings toggle.

## Tests

Synthetic-jiffy units (known deltas → expected %), first-sample None,
Δwall-guard, counter-reset → no-data, queue drop-oldest under backpressure,
watchdog state machine, backoff exclusion from rings.
