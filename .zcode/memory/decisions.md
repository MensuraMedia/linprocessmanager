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
10. **Binding operator mandates (r036, mid-turn):** (a) fundamentals from
    MensuraMedia/universal-instruction-set v2026.04 — modularity and
    universality are PRODUCT mandates, codified in docs/build-principles.md;
    (b) assets strictly from ~/projects/assets/icons, copied in, never
    referenced remotely; (c) fully self-reliant app — no web-based resources
    at build or runtime (grep gate on network imports; system packages only;
    direct python3 launcher, no pip/venv); (d) build documentation must state
    all of this — done in docs/build-principles.md.
11. **Modular docs (r037):** grouped logic lives in its own document under
    docs/modules/ (one per planned src module: procfs-data,
    sampling-pipeline, process-table, actions-permissions, resource-graphs,
    persistence-config), each with Purpose / Interface / Logic / Tests.
    The concept doc is overview + index only. Boundaries are load-bearing:
    only procfs.py reads the kernel; only manager_actions.py mutates; UI
    pages consume snapshots and never reach sideways. New grouped logic gets
    a new module doc, not a longer overview.
12. **Adversarial review applied (r039).** Three agents (correctness,
    security/ops, feature-gap). Notable accepted findings: diff keys must be
    TreeRowReferences with an explicit move op (re-parenting); sampler
    period = table interval (no second decimation); rings hold (ts,value);
    renice rule corrected (own=only increase, others=always EPERM); PID
    guard re-reads stat at click time; hidepid EACCES is a locked row, not
    an exit; sampler needs a watchdog + drop-oldest queue; fork-bomb row
    budget; per-process network columns rejected (needs eBPF/root).
13. **System logs (r039, operator-mandated).** journalctl subprocess only
    (no python3-systemd): argv-list, `=`-form flags only, never shell=True;
    bounded fetch + cursor paging; follow via io_add_watch + child reaping;
    permission probe-and-degrade (lock + remedy text, never elevate).
    Organize = Saved Views (named filter sets in settings.json, submenu
    children) + cursor-anchored Flags. Sidebar submenu: Journal / Kernel /
    Auth / Applications / Saved Views / Flags. build-principles §4 amended
    additively for /sys + local binaries; no-network gate upgraded to AST
    import allowlist + subprocess argv allowlist. Logs = roadmap Phase 7
    (large). Mockups E + F verified.
