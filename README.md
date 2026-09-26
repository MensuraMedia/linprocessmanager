# linprocman

A native Linux process manager for Debian-based desktops (Mint first):
live process table and tree, signals and renice, resource history, PSI,
and a searchable, organizable systemd-journal log viewer with pattern
frequency analysis. GTK3 + Python, fully offline.

**Status:** in development (Phase 2 of 8 — data core and sampler shipped;
live table landing; logs and frequency analysis designed). Docs are the
contract: what's described there is what gets built and tested.

## Principles (binding — docs/build-principles.md)

- **Fully offline.** Every datum from the local kernel (`/proc`, `/sys`)
  and local binaries (`journalctl`). No network, ever — enforced by test
  gates (AST import allowlist + subprocess argv allowlist).
- **Local assets only.** Icons are Phosphor (MIT), copied from the local
  master library into `resources/icons/` (manifest is the contract).
- **Modular and universal.** Core modules import no UI; runs on any
  Debian-based build (floors: docs/debian-compatibility.md); degrades
  visibly, never crashes, on hardened kernels (hidepid, Yama, dmesg_restrict).
- **Unprivileged.** No elevation paths, v1 and beyond.

## Quick start

```bash
./run.sh                 # == python3 src/main.py  (system python, no pip/venv)
```

System packages needed: `python3-gi gir1.2-gtk-3.0 python3-cairo python3-pil`.

## Development

```bash
python3 -m pytest tests/ -q        # unit + gate suite
python3 -m pytest -m live -q       # opt-in live-kernel tier
DISPLAY=:0 python3 tests/live_gui_walk.py   # live navigation walk + screenshots
```

Workflow, gates, task contracts, and the ZCode⇄Claude collaboration:
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Documentation map

| Doc | What it holds |
|---|---|
| [docs/process-manager-concept.md](docs/process-manager-concept.md) | overview + module index + phased roadmap |
| [docs/build-principles.md](docs/build-principles.md) | binding mandates + compliance checklist |
| [docs/modules/](docs/modules/) | 10 module specs — the engineering contracts |
| [docs/mockups/](docs/mockups/index.html) | 8 UI mockups + rendered PNGs |
| [docs/executor-collaboration.md](docs/executor-collaboration.md) | ZCode⇄Claude Code build collaboration |
| [docs/gtk4-port.md](docs/gtk4-port.md) | GTK3→GTK4 port strategy |
| [docs/upgrade-architecture.md](docs/upgrade-architecture.md) | compat layer + upgrade runbooks |
| [docs/debian-compatibility.md](docs/debian-compatibility.md) | distro matrix, floors, packaging |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | day-to-day development guide |
| [.zcode/tasks/QUEUE.md](.zcode/tasks/QUEUE.md) | orchestration queue + task states |

## License

Code and documentation: CC BY-NC 4.0 (see LICENSE). Icons: Phosphor, MIT —
see `resources/icons/manifest.txt`. Built on the
gtk-python-dashboard-starter (vendored; starter terms in
docs/starter-README.md).
