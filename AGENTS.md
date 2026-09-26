# linprocman — project instructions

Workspace scope. Global standards load first from ~/.zcode/AGENTS.md; this file
only adds what is specific to this project. Additive changes only — never modify
universal standards here.

- Description: native Linux GTK3 process manager built on mikesdatawork/gtk-python-dashboard-starter; lists/sorts/filters processes, signals, renice, resource graphs
- Bootstrapped: 2026-09-26 by s003_workspace_bootstrap_a.sh
- Ledger: ~/projects/Zai-ZCode/s-register.md

## Stack
- Python 3.12 (system python3, PyGObject via system packages; starter deps only: PyGObject, pycairo, Pillow — no psutil at runtime)
- GTK 3 (PyGObject, gi); run with `python3 src/main.py` (starter not yet vendored — see roadmap in docs/process-manager-concept.md)
- Data source: /proc read directly (stat, status, io, smaps_rollup, cgroup, pressure)
- Icons: Phosphor (MIT) — master library ~/projects/assets/icons; project subset resources/icons/{regular,fill} (57+12, manifest.txt maps use)
- Docs: docs/process-manager-concept.md (overview + module index), docs/build-principles.md (binding mandates), docs/modules/ (10 modular docs: procfs-data, sampling-pipeline, process-table, actions-permissions, resource-graphs, persistence-config, disks-filesystems, logs-journal, log-frequency, sysfs-data), docs/mockups/ (8 UI mockups + index + PNGs)
- Tests: pytest (tests/) — /proc parser fixtures, CPU-rate math, tree builder; run `python3 -m pytest tests/ -q` from repo root (once created)

## Project rules
- Fundamentals: universal-instruction-set v2026.04 (MensuraMedia; vendored at ~/doctrines/universal-instruction-set) — principles codified in docs/build-principles.md; modularity and universality are product mandates.
- Assets: icons and graphics strictly from /home/user/projects/assets/icons (Phosphor, MIT), copied into resources/icons/ + manifest entry. Never fetched or referenced from remote sources.
- Self-reliance: no web-based resources at build or runtime — no network imports under src/ (grep-gated in tests), system packages only, direct python3 launcher (no pip/venv).
- Core modules (procfs, sampler, actions) stay UI-import-free and headlessly testable.

## Change tracking
- changelog.md at repo root — append-only; every completed change gets an entry

## Memory
- .zcode/memory/decisions.md — architectural decisions with rationale
- .zcode/memory/pending.md — unfinished work carried between sessions
