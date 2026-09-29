#!/usr/bin/env bash
# linprocman installer (r072) — run from the git checkout.
# Installs: program-menu entry, hicolor icons (menu + ALT+Tab + tray),
# ~/.local/bin launcher. --uninstall removes all three; your settings
# (~/.config/linprocman) and logs (~/.local/state/linprocman) are preserved.
set -euo pipefail

APP=linprocman
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
DATA_DIR="$HOME/.local/share"
DESKTOP_DIR="$DATA_DIR/applications"
ICON_BASE="$DATA_DIR/icons/hicolor"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/$APP"

case "${1:-install}" in
install)
    # r138: stamp the installed revision — the running instance's version
    # must always be diagnosable (the stale-instance incident).
    REV="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    # -- dependency check (report; the app runs without the optional ones) --
    missing=()
    for pkg in python3-gi gir1.2-gtk-3.0 python3-cairo python3-pil; do
        dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        echo "Missing required packages: ${missing[*]}"
        echo "Install with:  sudo apt install ${missing[*]}"
        exit 1
    fi
    for opt in gir1.2-xapp-1.0 gir1.2-ayatanaappindicator3-1; do
        dpkg -s "$opt" >/dev/null 2>&1 || \
            echo "note: $opt not installed — tray icon falls back (window icon unaffected)"
    done

    # -- launcher -------------------------------------------------------
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/$APP" <<LAUNCH
#!/usr/bin/env bash
# linprocman launcher — installed by install.sh from $REPO_DIR
# revision: $REV (installed $(date '+%Y-%m-%d %H:%M'))
if [ "\${1:-}" = "--version" ]; then
  sed -n 's/^# revision: //p' "\$0" | head -1
  exit 0
fi
export DISPLAY="\${DISPLAY:-:0}"
exec /usr/bin/python3 "$REPO_DIR/src/main.py" "\$@"
LAUNCH
    chmod +x "$BIN_DIR/$APP"

    # -- icons (hicolor size dirs; the 512 also serves as ALT+Tab large) --
    for size in 16 32 48 64 128 512; do
        dir="$ICON_BASE/${size}x${size}/apps"
        mkdir -p "$dir"
        cp "$REPO_DIR/resources/images/icon-${size}.png" "$dir/$APP.png"
    done

    # -- desktop entry (program menu) ------------------------------------
    mkdir -p "$DESKTOP_DIR"
    cat > "$DESKTOP_DIR/$APP.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=LinProcessManager
Comment=Live process manager — table, signals, resources, logs
Exec=$BIN_DIR/$APP
Icon=$APP
Terminal=false
Categories=System;Monitor;Utility;
StartupWMClass=linprocman
Keywords=process;system;monitor;task;kill;
DESKTOP
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

    echo "installed:"
    echo "  revision     $REV"
    echo "  menu entry   $DESKTOP_DIR/$APP.desktop"
    echo "  icons        $ICON_BASE/*/apps/$APP.png (16–512)"
    echo "  launcher     $BIN_DIR/$APP"
    echo "  app source   $REPO_DIR (installer references the checkout in place)"
    echo "tray icon appears if a backend is available (XApp on Mint: yes)"
    echo "run:  $APP   (or from the menu: LinProcessManager)"
    ;;

--uninstall)
    rm -f "$DESKTOP_DIR/$APP.desktop" "$BIN_DIR/$APP"
    for size in 16 32 48 64 128 512; do
        rm -f "$ICON_BASE/${size}x${size}/apps/$APP.png"
    done
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    echo "uninstalled (menu entry, icons, launcher)."
    echo "kept: ~/.config/$APP (settings, netwatch marks/tracking), $STATE_DIR (logs)"
    ;;

*)
    echo "usage: $0 [install|--uninstall]" && exit 1
    ;;
esac
