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
18. **Upgrade architecture (r044).** src/ui/compat/ one-file-per-seam
    module is the standing structure (import law + flip point gtk_env.py
    flipping BOTH Gtk and Gdk; raw gi.repository import banned outside
    it — bare import silently loads a default version). Deprecation
    honesty: PyGObject does NOT warn for GTK C-level deprecations
    (TreeView-on-GTK4 silent); PyGIDeprecationWarning-as-error catches
    binding-level only; G_ENABLE_DIAGNOSTIC covers deprecated properties
    best and needs an our-names allowlist (theme noise false-reds). One
    Gtk version per process — non-active compat path tests cover
    branch/non-GTK logic only. pygobject ≥3.42 for GTK4 (noble: 3.48).
19. **Debian-family compatibility (r045).** Support current+previous LTS
    bases; floors Python 3.10 / GTK3 3.24 / GTK4 4.6 (jammy-only floor) /
    PyGObject 3.42; feature probes (HAS_* flags in compat/gtk_env) for
    ≥4.10 conveniences. Yama ptrace_scope=1 = stock Ubuntu/Mint: other
    users' smaps_rollup/environ unreadable — lock-path degrade, same as
    hidepid. Snap rejection is mandate-based NOT technical (its
    system-observe/process-control interfaces would work); flatpak is
    technically impossible (own PID namespace). .deb (Phase 8):
    dh_python3, no maintainer-script cache calls (dpkg triggers own it),
    #!/usr/bin/python3 shebang. Distro matrix mostly knowledge-verified —
    only noble machine-tested; keep floors boring so the gap stays boring.
20. **Direct collaboration + Phase 2a (r046).** Claude now co-drafts
    contracts in consult sessions before dispatch (first: task 003; it
    found the None-vs-sentinel seam bug across 003/004 — schema-freeze
    gate instituted). Task 002 merged: compat/ nine adapters, Application
    lifecycle, three gate tiers, raw-gi-import ban repo-wide. Lessons:
    resume via --session-id fails while a session is held open ('already
    in use') — fallback = fresh session with prior conclusions embedded;
    EVERY dispatch needs its own --permission-mode acceptEdits (missing
    it = silent write-denials, executor reports honestly); dead-code
    deletion stays ZCode's (git rm -f for executor-touched files).
21. **Phase 2b + schema gate live-fire (r048).** Component testing =
   live cross-check vs psutil (dev-only) + suite + gates. Task 003 merged.
   The schema-freeze gate worked exactly as designed: C-review rejected
   the record set (mem_swap missing, read-then-dropped) before 004 could
   build on the broken seam; fix was reviewer-specified and mechanical →
   ZCode applied as sign-off remediation (precedent: reviewer-specified
   mechanical fixes may be applied by ZCode, recorded as such). Gate
   tuning precedent: banned-API sweep scoped to UI trees (raw-import ban
   proves modules GTK-free; plain set.add is legitimate there).
22. **Phase 2c + documentary close (r052).** Live table shipped and
    pixel-verified (real rows on :0). Two verification-caught bugs fixed by
    ZCode per r048 precedent: dual-layout import shim (app vs test path —
    executor cannot run the app, so startup crashes are ZCode's catch),
    clamp semantics (invalid→default, near-miss→clamp — the test encoded
    finer rules than the doc; doc refined). Documentary set complete:
    README/LICENSE/DEVELOPMENT; corpus review keeps docs honest vs code
    (tuple-keyed procs, missing sensors key, unwired sysfs — all fixed).
    Phase-2 close (005) = independent review + operator gate + backup.
23. **Contrast fix + standing adversarial role (r054).** Static CSS must
    load through the theme applicator (combined single load — load_from_data
    REPLACES). ThemeManager deletion lesson refined: 'dead code' must be
    checked for SIDE EFFECTS not just importers. GTK3 treeview facts: rows
    need treeview bg (row nodes inherit), headers are real button nodes
    (style 'treeview header button'), per-row hover is not available by
    default (whole-widget :hover flashes — omit). librsvg pixbuf loader is
    OPTIONAL on Debian family — SVG assets need a png fallback chain.
    170px sidebar adopted (css + config constant). Pulse mark is the logo.
24. **Threshold coloring + runtime-only bug class (r057).** Value colors =
    capacity zones (<60 green, 60–84 amber, ≥85 red) via one shared
    _cap_zone for ALL stats; delta arrows stay r056 (red ▲ up, green ▼
    down) on plain values. Class-scope trap: a staticmethod cannot see
    class attrs by bare name (ProcessPage._cap_zone → NameError at first
    live snapshot; tests never called it) — and an orphaned @staticmethod
    from a sloppy edit surfaced only at runtime. Runtime journal
    (journalctl --user -u linprocman-app) is now part of verification.
    Window-ID pixel proof without raising: xwd -id <win> + in-repo XWD
    parser (PIL lacks XWD; no convert/netpbm on this box) — immune to
    GNOME focus-stealing-prevention which now blocks wmctrl raises.
25. **Continuous cycle (r058).** Phase-2 closed (8/8 close-review fixes);
    Phase 3 actions merged and LIVE-verified (real process killed via the
    library path, EPERM errno surfaced, guard refuses reused PID).
    Backlog discipline: .zcode/tasks/BACKLOG.md (OPT/INNOV/DEBT) absorbs
    optimizations + innovations so mainline stays phase-ordered; backlog
    items ride executors when scope-adjacent (D6 entry-dialog seam logged
    by executor itself). PROCESS DEVIATION logged: 006 ran on main (branch
    cut skipped) — verification chain unchanged, discipline restored.
    Standing: per-phase tests + s009 backups at every phase close;
    GUI walk needs no-raise window capture (xwd parser) per r057.
