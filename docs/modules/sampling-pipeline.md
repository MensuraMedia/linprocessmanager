# Module doc — sampling pipeline (`src/modules/manager_sampler.py`)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[process-table.md](process-table.md) · [actions-permissions.md](actions-permissions.md) ·
[resource-graphs.md](resource-graphs.md) · [persistence-config.md](persistence-config.md).
Overview: [../process-manager-concept.md](../process-manager-concept.md).

## Purpose

Owns timing. Turns procfs reads into immutable `Snapshot` objects on a fixed
cadence and hands them to the GTK main thread — the only bridge between the
kernel-reading world and the UI world. Consumers never read /proc.

## Interface

Provides:
- `Sampler.start()` / `stop()` / `set_interval(seconds)`
- `queue.Queue` of `Snapshot` objects (bounded; UI drains via `GLib.idle_add`)
- `Snapshot` schema: `{"ts": float, "procs": {pid: record}, "system": {cpu, mem, net, psi}}`
  where each `record` carries stat+status fields plus the **previous sample's
  jiffies** so rates are computed at snapshot build time, not in the UI.

Consumes: [procfs-data.md](procfs-data.md) readers only.

## Logic

- **Cadence:** sample every 1 s. The process table applies every 2nd snapshot
  (default 2 s, operator-adjustable 0.5–5 s), graphs and the details pane
  apply every snapshot. One thread, one loop, no per-consumer threads.
- **Backoff:** while the window is hidden, sample every 10 s (keeps history
  alive cheaply); resume instantly on visibility.
- **Pause:** `pause-circle` stops applying snapshots but the thread keeps a
  minimal heartbeat so deltas stay computable on resume — or stops entirely
  after a grace period (decide at implementation; prefer the simple full stop
  and show "—" for one sample on resume).

## Rate math (computed here, not in the UI)

```
cpu%       = Δ(utime + stime) / (CLK_TCK × Δwallclock) × 100   # 100% = one core
cpu%_total = cpu% / ncpu                                       # 100% = whole machine
```

- First sample after start/resume → no delta → "—" (never 0.0: zero is data,
  absence is not).
- Process gone between samples → row drops; its last delta is discarded.
- Disk I/O and network are cumulative counters — rates are byte deltas per
  Δwall, formatted by the table layer.
- Per-core normalization is the default; whole-machine is a settings toggle
  (the two parity references — htop and gnome-system-monitor — disagree).

## Tests

Synthetic-jiffy units: known Δ(utime+stime) over known Δwall → expected %;
first-sample None; vanished-process discard; backoff state machine.
