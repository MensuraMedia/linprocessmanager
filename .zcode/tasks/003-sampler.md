# Task 003 — Phase 2b: sampling pipeline (GLib-free sampler + pure step function)

Phase: 2b (concept §sampling; docs/modules/sampling-pipeline.md)   Branch: task/003-sampler (cut from main)
Dispatcher: ZCode (r048)  Executor: Claude Code, headless, acceptEdits

## Goal

Build `src/modules/manager_sampler.py`: a threaded, **GLib-free** sampler that
turns procfs/sysfs reads into immutable `Snapshot` objects on a fixed cadence,
buffers them in a bounded drop-oldest queue, and exposes a pure step function.
The sampler owns timing and the queue; it never touches GTK. Task 004 installs
the single GLib idle source and does model-layer translation. This task freezes
the record schema (acceptance gate) before 004 is dispatched.

## Read first (binding)

- docs/modules/sampling-pipeline.md — cadence, watchdog, backoff, rate math. THE SPEC.
- docs/modules/procfs-data.md — reader contracts, identity rule, error taxonomy.
- AGENTS.md (loads automatically).

## Scope (touch nothing else)

- NEW  src/modules/manager_sampler.py — Sampler + Snapshot + build_snapshot
- NEW  tests/test_sampler.py — rate math, guards, queue, watchdog, backoff, schema
- EDIT tests/fixtures/proc/ — add jiffy-pair fixtures only if a needed one is absent
- EDIT src/modules/procfs.py — add ONLY iter_pids(proc_root) (PID enumeration; live testing r048 found the gap — the boundary rule forbids the sampler listing /proc itself)
- NEW  tests/test_live_procfs.py — opt-in live tier: pytest.ini registers + skips the "live" marker by default (addopts -m "not live"); tests run against the REAL /proc with own-pid invariants (no psutil dependency); run explicitly with: python3 -m pytest -m live

## Rules (verbatim, rulings baked in)

1. **GLib-free.** No `import gi`, no GLib, no `idle_add`, no GTK anywhere in
   this module. Grep-gated. The idle source is task 004's job.
2. **Bounded queue, owned here:** small (4 slots), `put_nowait` + drop-oldest
   on full. Public `drain_latest()` returns the newest queued Snapshot (or
   None) and empties the queue. No per-snapshot callback pileup.
3. **Pure step function mandated:** `build_snapshot(prev, now, clock, readers)`
   — no I/O, no globals, no clock reads inside; all inputs injected. The thread
   loop is the only stateful shell; rate math lives in the pure function and is
   unit-tested in isolation.
4. **No-data seam is pure Python:** absent/unreadable → `None` value or absent
   key. NO `(-1, has_data=False)` here — that translation is 004's model layer
   only. Rate fields emit `None` on: first sample, Δwall < one period,
   `(pid, starttime)` mismatch (PID recycling), negative counter delta (reset).
5. **Identity everywhere is `(pid, starttime)`, pid never alone** — deltas
   computed only on match; a mismatch re-arms like a first sample.
6. **Activity injected, never read from GTK:** `set_activity_state(active,
   iconified)` is called by the UI; the sampler reads that flag only. Backoff
   (10 s) keys on iconified/withdrawn + inactive. Backoff snapshots carry
   `from_backoff=True`; ring exclusion is resource-graphs' concern, not here.
7. **`request_rollup(pid, starttime)` is thread-safe** — enqueues a one-shot
   smaps_rollup read for the selected process; result rides the next snapshot.
8. **Watchdog:** whole loop under top-level try/except that logs and continues;
   consecutive-failure counter stops the thread cleanly after N. Snapshot `ts`
   lets 004 detect staleness — sampler never fakes liveness.
9. **Schema freeze (acceptance gate):** the record field set (appendix) is
   frozen and C-review signs it BEFORE task 004 dispatch. Adding/renaming a
   field after sign-off is a defect.
10. All existing mandates: offline app code, no subprocess, no pip/venv, never
    create claude-named files/dirs. You cannot run Bash — write code + Report;
    ZCode runs tests and returns failures on this session.

## Acceptance (ZCode verifies)

1. `python3 -m pytest tests/ -q` green; existing tiers still pass.
2. Grep-gate proves zero gi/GLib/GTK references in manager_sampler.py.
3. `build_snapshot` tested pure: synthetic jiffies → expected cpu_pct;
   first-sample None; Δwall-guard; counter-reset → None; recycle mismatch → None.
4. Queue drop-oldest under backpressure and `drain_latest()` newest-wins tested.
5. Watchdog state machine + backoff tagging (`from_backoff`) tested.
6. Record field set matches the frozen appendix exactly (schema assertion test).
7. git diff touches only Scope.

## Report

Markdown: file map; the `build_snapshot` signature + step description; the final
record field table (echo appendix, note any deviation — none expected); queue
and watchdog notes; open questions; anything needing Bash.

## Out of scope

The GLib idle source, `(-1, has_data=False)` translation, model/table wiring
(all task 004); ring buffers and backoff exclusion (resource-graphs); sysfs
sensor additions; settings persistence; per-core vs whole-machine toggle UI.

## Appendix — frozen Snapshot per-process record fields

| Field | Type | Notes |
|---|---|---|
| `pid` | int | identity half 1 |
| `starttime` | int | identity half 2; jiffies since boot |
| `name` (comm) | str | comm, last-`)` parse |
| `user` | str | uid→name cache |
| `state` | str | proc(5) field 3 |
| `ppid` | int | from stat, status cross-check |
| `cpu_pct` | float \| None | precomputed; None = no-data interval |
| `mem_rss` | int \| None | bytes, VmRSS source of truth |
| `mem_vsize` | int \| None | bytes |
| `mem_shared` | int \| None | RssFile+RssShmem, bytes |
| `io_read_rate` | float \| None | bytes/s; None on reset/first/unreadable |
| `io_write_rate` | float \| None | bytes/s; None on reset/first/unreadable |
| `nice` | int | proc(5) field 19 |
| `threads` | int | proc(5) field 20 |
| `unit` | str | cgroup-derived; `—` for kthread/`0::/` |
| `is_kthread` | bool | empty cmdline AND state ≠ Z |
| `is_defunct` | bool | state == Z |
| `from_backoff` | bool | true on 10 s backoff samples |
| `rollup` | dict \| None | present only when request_rollup fulfilled |

(Snapshot envelope: `ts: float`, `procs: {(pid,starttime)→record}`, `system: {...}`, `from_backoff: bool`.)