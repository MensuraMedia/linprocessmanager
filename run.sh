#!/bin/bash
# run.sh — linprocman direct launcher.
#
# System python3 only: no venv, no pip, no package installs (build-principles
# §4). Dependencies are system packages (python3-gi, python3-cairo,
# python3-pil) via apt. An air-gapped machine builds and runs from the repo
# alone. `bash run.sh` is exactly `python3 src/main.py`.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

exec python3 src/main.py "$@"
