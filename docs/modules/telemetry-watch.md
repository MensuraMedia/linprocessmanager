# Module doc — Telemetry Watch (`src/modules/manager_telemetry.py` + Processes-page surface)

Part of the linprocman modular docs. Siblings: [sampling-pipeline.md](sampling-pipeline.md) ·
[process-table.md](process-table.md) · [process-preview.md](process-preview.md) ·
[logs-journal.md](logs-journal.md) · [actions-permissions.md](actions-permissions.md) ·
[procfs-data.md](procfs-data.md). Overview: [../process-manager-concept.md](../process-manager-concept.md).

Status: concept for operator review (r055). New feature — **Telemetry Watch**:
detect anomalous traffic to/from applications that are **not currently in
use**, and surface any process or function that gathers information about
the local system and ships it to an external system.

## 1. The mandate, translated into detectable signals

"Telemetry" on a Linux desktop is not one mechanism — it is a handful of
recognizable behaviors. Telemetry Watch looks for each signal with
/proc-level evidence, scores the combination, and presents a verdict with
its reasons. **It never accuses on a single weak signal** and it never
names a process "spyware" — it reports *what was observed* and how well it
matches known telemetry shapes.

| Signal | Evidence source (offline, /proc + local only) |
|---|---|
| Idle-but-talking | process with **zero user input windows** (no focus, no open user-facing fd on the session) yet steady egress | input state from the session tracker (r055 probe below); egress from net attribution (process-preview §4) |
| Telemetry-shaped cadence | egress in **periodic bursts** (fixed intervals: 30 s/5 min/15 min/1 h) or at **session milestones** (login, unlock, boot+5 min) | burst detector over the per-process net ring (30-min window, Fisher-style interval regularity) |
| Remote endpoint persistence | same remote **IP:port repeatedly** across bursts | conntrack-free: per-socket remotes from `/proc/net/tcp` inode match (existing attribution tables) |
| Hostile DNS shape | resolves many distinct hosts, short TTL-style churn | not readable without packet capture → **out of scope, stated** |
| Config/resource snooping | **weak snapshot heuristic only**: unusually many concurrent open fds outside its working set | fd-count snapshot (r055 review: file-sweep detection is ~impossible at 2 s cadence — opens/closes complete between samples; io counters carry no paths. Stated in-UI as weak) |
| Known telemetry fingerprints | executable path, cmdline, cgroup unit matches a **local signature list** (flatpak runtimes that phone home, distro reporters, vendor agents) | local YAML ruleset shipped in-repo + user-extensible in ~/.config/linprocman/telemetry-rules.yaml |
| Masking behaviors | comm ≠ exe basename **with corroboration** (r055 review: comm is 15-char truncated and routinely differs benignly — Electron, interpreters; argv rewrite is normal for shells/postgres) — weight applies only with a second matching signal | stat/exe/cgroup cross-checks (readers already collect all three) |
| Network egress while flagged idle | any egress ≥ threshold while user-idle > N minutes | idle source = session tracker; egress = attribution |

## 2. Scoring — transparent, not magic

Each process gets a **Watch Score 0–100** = sum of weighted confirmed
signals, displayed only when ≥ 20:

```
idle-but-talking            +25
periodic-burst cadence      +20
persistent remote endpoint  +15
fingerprint match           +30 (rule lists its own weight)
snooping file sweep         +20
masking behavior (corroborated) +12
egress-during-idle          +15
```

Verdicts — named for what is actually measured (adversarial r055: cadence
shape cannot confirm *telemetry* vs sync/backup/update, so the axis says
"unattended egress", and the word telemetry is reserved for fingerprint
rule matches): **Quiet** (<20) · **Chatty** (20–49) · **Unattended-egress
Suspicious** (50–79) · **Telemetry-fingerprinted** (80+, rules only). The
status line and preview pane show the *contributing signals by name* —
the operator can always audit why. False positives are expected (backup
agents, update checkers are periodic talkers; Mint's own mintupdate/
mintreport/timeshift ship with the same shape — they arrive pre-seeded in
the shipped allow-list); the UI's job is exposure + one-click
Allow-listing, not judgment.

**Allow/deny lists** persist in settings.json (`telemetry.allowed[]`,
`telemetry.denied[]` by unit/exe-glob). A denied process's rows tint; an
allowed process never scores.

## 3. Surfaces

- **Processes page:** new scope chip **Telemetry** (`crosshair` icon)
  = processes with score ≥ 20, sorted by score. Watch Score column
  (optional, chooser group Diagnostics) with verdict tint.
- **Preview pane section "Telemetry Watch":** verdict + contributing
  signals + top remote endpoints (from attribution) + Allow / Deny buttons.
- **Status strip:** a `shield-warning` chip appears when any process
  crosses Suspicious while idle ("1 suspicious talker — review").
- **Logs cross-link (Phase 7):** "View journal for unit" pre-filtered to
  the process's unit — telemetry bursts usually leave journald traces.

## 4. Architecture (mandates preserved)

- New **logic-only** module `manager_telemetry.py`: consumes Snapshots +
  attribution data (never reads /proc itself — boundary law); pure
  scoring functions `score_process(history, rules) -> (score, signals)`;
  fixture-tested (synthetic burst series, idle matrices, rule matches).
- **Session/idle input is injected** (same pattern as activity state):
  `set_idle_info(seconds_idle, focused_pids)` — X11 via
  `XScreenSaverAllocInfo` (X11-only; Wayland: `idle-inhibit` unaware →
  idle signals degrade to "unknown", feature narrows to cadence+fingerprint
  signals, stated in the UI).
- **No packet capture, no eBPF, no root, no network** — everything is
  /proc-derived or user-configured. The feature *observes*; it does not
  block (blocking is an operator action via existing Kill/Stop paths).
- **Phasing:** Phase 5 (after io-rate/net columns land — needs attribution
  data), one executor task: scoring engine + chip + column; preview
  section + allow/deny UI in the same task; logs cross-link at Phase 7.

## 5. Honest limits (stated in the UI, not just here)

- Per-process egress under the attribution design is **proportional, not
  kernel-accounted** — burst *timing* is high-confidence only when the
  process is the sole talker in the window (concurrent talkers smear
  each other); byte counts are estimates. Sub-cadence beacons and
  short-lived sockets (open-send-close between samples) are invisible to
  /proc/net snapshots — stated in-UI.
- Other users' processes under Yama are score-limited (fewer observable
  signals); the UI shows which signals were invisible.
- DNS content, encrypted payload inspection, and host-level firewall
  questions are out of scope by design (offline mandate; no packet capture).
- A process can always evade heuristics; the signature list + exposure
  model is the defense in depth, not a guarantee.

## 6. Tests

Pure scoring units (each signal's trigger + weights), burst-regularity
detector (synthetic series: exact-period, jittered, random), idle-matrix
cases, rule-file parsing + user-rule override, allow/deny persistence,
degradation (no idle source → narrow mode), schema additions through the
sign-off gate.
