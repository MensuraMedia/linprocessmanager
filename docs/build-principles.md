# linprocman — Build Principles (local build document)

Status: binding (operator mandates, r036, 2026-09-26)
Fundamentals source: MensuraMedia/universal-instruction-set v2026.04
(CC BY-NC 4.0; vendored master at ~/doctrines/universal-instruction-set —
principles are copied here, never loaded from the master at build or runtime).

## 1. Core fundamentals

This project is built on the universal-instruction-set's design principles,
adapted to the application itself — not just to the workflow that produces it:

1. **Copy, not reference** — assets and standards live *inside* the project.
   The icon subset is copied into `resources/icons/`; nothing is loaded from
   another repo, path, or URL at build or runtime.
2. **Portable / self-contained** — the repo works on any Debian/Mint-class
   machine with GTK3. Clone + run; no master library, no network, no
   machine-specific setup.
3. **Immutable foundation** — the starter's architecture and these principles
   are the baseline; later changes add alongside, never restructure away.
4. **Additive customization** — new rules, pages, and modules are added as new
   files; universal files are not edited in place.
5. **Additive tracking** — changelog.md and .zcode/memory supplement git.
6. **Tiered cost** — deterministic work (parsing, deltas, formatting) is
   code, not model/generation work; keep it in pure functions.
7. **Platform-native** — GTK3/PyGObject idioms (TreeModel, GLib main loop,
   cairo draw callbacks); no web-view shims, no emulated widgets.
8. **Language-agnostic core** — procfs/sampler/actions logic is plain Python
   with no UI imports, so it is testable and reusable headlessly.

## 2. Product mandate: modularity & universality

Modularity and universality are **product mandates**, not preferences:

- **Modular** — each capability is an isolated module with a narrow interface:
  `procfs.py` (pure parsing), `manager_sampler.py` (producer), pages
  (consumers), `manager_actions.py` (signals/policy). No page reads /proc
  directly; no module reaches into another's internals. Any module can be
  replaced or tested alone.
- **Universal** — runs on any mainstream Linux with GTK3 (Debian, Mint, Ubuntu
  derivatives; X11 or Wayland). No assumptions about kernel config beyond
  procfs itself; features degrade visibly when the kernel hides data (hidepid,
  restricted `/proc/<pid>/io`) instead of failing. All 7 starter themes work
  without per-theme assets. CPU-count, locale, and theme independent.

## 3. Local-only resources (assets policy)

- Icons and graphic assets come **strictly from the local master library**
  `/home/user/projects/assets/icons` (Phosphor, MIT) and are **copied** into
  `resources/icons/{regular,fill}` (authoritative count on the manifest
  footer — currently 57 + 12 files; the manifest is the single source of
  truth and all docs reconcile to it). No icon is fetched, linked, or loaded
  from any remote source, ever.
- Fonts are the system's own (Ubuntu/Cantarell on Mint) — no web fonts, no
  bundled font downloads.
- Documentation (including mockups) references only files inside this
  repository or the local master library during design; the application
  itself references only files inside this repository.

## 4. Self-reliance: no web-based resources

- **Runtime:** the app never opens a network socket. Every datum comes from
  the local machine: kernel interfaces — `/proc` (stat, status, io,
  smaps_rollup, cgroup, net/dev, meminfo, pressure, diskstats) **and `/sys`**
  (hwmon, cpufreq, drm) — plus the local binaries `journalctl` and (fallback
  only) `dmesg` for the operator-mandated logs feature (amendment r039;
  module contract in docs/modules/logs-journal.md). No telemetry, no update
  checks, no version pings, no remote help links that fetch content.
- **Build/run:** system Python + system packages only
  (`python3-gi`, `python3-cairo`, `python3-pil` via apt on Mint/Debian).
  `pip` and virtualenv are NOT used; the starter's venv-creating `run.sh`
  will be replaced by a direct `python3 src/main.py` launcher (linfilesearch
  pattern). An air-gapped machine can build and run linprocman from the repo
  alone.
- **Verification against this mandate:** an AST-based import allowlist
  (permitted stdlib subset; `urllib`, `http`, `socket`, `requests`, etc.
  absent) **plus** a subprocess-argv allowlist — every `subprocess`/spawn
  call site must invoke a fixed binary from the approved list
  (`journalctl`, `dmesg`) with values only in `=`-form flags. The original
  grep for network imports stays as a fast pre-filter only (it cannot see
  subprocess-hidden binaries or comment false-positives). Changes to either
  allowlist change this document first, by operator decision.

## 5. Security stance (from the doctrine's security rules)

- Unprivileged process; v1 never elevates (no pkexec/sudo paths wired).
- Destructive actions (kill, renice) confirm first, act on `(pid, starttime)`
  identity, and surface exact kernel error text on refusal.
- No secrets in the repo; the app runtime writes nothing outside
  `~/.config/linprocman/`. Two sanctioned exceptions, pre-authorized here:
  the installer (`install.sh`, operator-run, writes ~/.local/bin and
  ~/.local/share/applications) and user-directed log-view export through a
  FileChooser dialog. Nothing else, ever.
- Read-only use of `/proc`; the app sends signals only on explicit operator
  action.

## 5b. UI bounding-box policy (r071)

Recurred twice (r060 band gauges, r071 Basics cards): dynamic text inside a
card grows the card's natural size, so the whole card visibly expands and
contracts as values change. Policy, binding for all UI work:

1. **The bounding box is fixed; only the visual inside it moves.** A card,
   panel, or gauge declares its dimensions (width via pinned text or
   size_request; height via the bar/row height) and never resizes in
   response to its content.
2. **Any label bound to dynamic data** (values, captions, statuses) pins
   `set_width_chars(...)` + `set_ellipsize(END)`. The ellipsis is the
   honest signal of truncation.
3. **Progress bars/bars may change fill fraction only** — never the box.
4. **Reviewers (adversarial pass) must check for unpinned dynamic labels**
   on every UI diff; the recurrence itself is a process defect.

## 6. Compliance checklist (per change)

- [ ] New assets? Sourced from `/home/user/projects/assets/icons` and copied
      into `resources/icons/` + manifest entry.
- [ ] New code? Pure-Python core modules with no UI imports; no network
      imports anywhere.
- [ ] New page/feature? Added alongside existing structure; starter
      architecture untouched.
- [ ] changelog.md entry appended; decisions recorded in
      `.zcode/memory/decisions.md`.
- [ ] Tests run green (`python3 -m pytest tests/ -q`) with the no-network
      grep gate.
