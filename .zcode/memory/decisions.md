# Decisions

Record architectural decisions with rationale. Newest at the bottom.

## r036 — 2026-09-26 — concept-stage decisions

1. **/proc direct, no psutil at runtime.** Starter stays zero-dep beyond
   PyGObject/pycairo/Pillow. psutil 5.9.8 is installed but dev-time only — it
   does not expose PSI and its `cpu_percent(interval=…)` blocks. Verified on
   this machine.
2. **Sampler thread → queue → `GLib.idle_add`.** Same streaming pattern as
   linfilesearch's engine. Table applies every 2nd snapshot (default 2 s),
   graphs/details every snapshot (1 s). Backs off when window hidden.
3. **CPU % from jiffy deltas** (`Δ(utime+stime) / (CLK_TCK × Δwall) × 100`),
   per-core-normalized default (100% = one core), whole-machine toggle.
   First sample shows "—". CLK_TCK verified 100.
4. **Diff-in-place model updates keyed by PID dict → TreeIter** (never full
   rebuild — preserves selection/sort/expansion); sort blocked around the
   batch. Typed columns; formatting in cell data funcs.
5. **(pid, starttime) guard before every signal** — closes the PID-recycle
   race. Selection identity is the pair, not the row.
6. **smaps_rollup only for the selected process** — walking smaps for all
   PIDs every tick is the classic freeze mistake; forbidden.
7. **No elevation ever in v1.** EPERM surfaces exact errno text in the
   status line. pkexec path deliberately not wired.
8. **Kernel threads hidden by default**, grouped under kthreadd in tree
   view; zombies shown as `name (defunct)` with an explaining details pane.
9. **Mockup verification lesson (same as linfilesearch r034):** a
   small-model QA pass on a full-page screenshot reported 'broken process
   icons' on mockup B; upscaled crop probes showed clean glyphs everywhere.
   Verify flag reports against crops before acting on them.
