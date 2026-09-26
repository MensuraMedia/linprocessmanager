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
14. **Frequency analysis + sidebar shell (r040).** Right-click row context
    menu on logs (copy/flag/filter/focus/frequency/export; Menu key parity;
    resolved pattern shown in the menu label). Frequency = own module
    (manager_frequency.py): heuristic template normalization (digits/hex/
    IP/path → placeholders), binned histogram, incident bands threshold
    max(3, median×4), related-events strip, incident table, PNG/CSV export;
    warning/err seeds self-tune to incident mode. Sidebar: ONE left-aligned
    icon column at x=12; submenu indents to parent TEXT level (x=43), never
    the icon; width study mockup H — 150px truncates (fail), 170px
    recommended, 190px headroom; one constant in starter config_layout if
    adopted. Mockup G lesson: absolutely-positioned overlays inside
    overflow:hidden windows clip silently — and the SECOND changelog
    append-mistake happened (replaced r039 entry with r040); rule: always
    append-only with old_string = the LAST line, new_string = last line +
    new line.
15. **zcode-executor collaboration (r041, proposed).** T2 delegation
    inverted: ZCode plans/verifies, Claude Code (claude -p headless,
    v2.1.282 verified installed) executes on task branches via
    .zcode/tasks/NNN-*.md contracts. Executor never merges, never edits
    binding docs, never creates CLAUDE.md/.claude (no-claude-path rule is
    a contract constraint AND a verification sweep). Verification chain:
    scope diff → pytest → AST/argv gates → pixel verification. Pilot =
    task 001 (Phase 1 data core) — NOT started; operator approval gate.
    Lessons: changelog append-mistake happened a THIRD time (r040→r041);
    the decisions.md rule from #14 now also applies mechanically — never
    use a previous entry as old_string unless new_string starts with it.
16. **Executor collaboration LIVE (r042).** First real dispatches ran:
    AGENTS.md loads natively in Claude Code ($0.01 probe). Review dispatch
    ($0.89) found 3 P1s ZCode's own three-agent pass missed — independent
    vendor review has real value (doctrine P3 argument confirmed). Task 001
    ($6.08, 23.6 min, acceptEdits, no Bash) delivered in-scope, 49/49
    tests, zero deviations; executor cannot `rm` files (acceptEdits has no
    Bash) — ZCode handles deletions in staging/verification. Verification
    chain worked end-to-end incl. live X11 window pixel proof
    (app-live-phase1.png). cgroup display: strip .scope/.service suffixes.
    Session ids are strict UUIDs (a friendly-name --session-id silently
    fails with empty stdout).
17. **GTK4 port strategy (r043).** docs/gtk4-port.md: port stays post-v1,
   but NINE portability seams are adoptable now under GTK3 and enforced by
   a banned-API pytest gate (Application lifecycle, Gio.Menu+popover
   adapter, event controllers + SimpleAction accels — NOT
   ShortcutController (GTK4-only) and NOT bare GestureClick (renamed from
   GestureMultiPress), layout.py box_add/set_child adapters, ChartArea,
   windows-not-dialogs, icon helper, CSS discipline incl.
   add_provider_for_display path). TreeView family: works on 4.14,
   deprecated since 4.10 — ColumnView is the standing post-port item.
   Collaborator review earned its cost again ($0.35, six real corrections).
