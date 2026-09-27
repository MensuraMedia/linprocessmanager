# Module doc — branding (`src/ui/branding.py`)

Part of the linprocman modular docs. Siblings: [procfs-data.md](procfs-data.md) ·
[sampling-pipeline.md](sampling-pipeline.md) · [process-table.md](process-table.md) ·
[resource-graphs.md](resource-graphs.md) · [sysfs-data.md](sysfs-data.md) ·
[metric-band-basics.md](metric-band-basics.md) · [graphs-hub.md](graphs-hub.md) ·
[persistence-config.md](persistence-config.md). Overview:
[../process-manager-concept.md](../process-manager-concept.md).

Added r082 (operator): the mark changed to Phosphor **list-checks** and every
icon placement was consolidated behind one module, so a brand switch is an
asset swap plus one regeneration — never a code hunt.

## Purpose

One mark, every placement. `ui/branding.py` is the SINGLE owner of the brand
mark: its files, its pixbufs, and the two runtime apply functions. Nothing
else in `src/` may hardcode a brand raster path (gate-tested).

## The assets (checked in, `resources/images/`)

| File | What it is | Produced by |
|---|---|---|
| `list-checks.svg` | Vector source — Phosphor `list-checks` (regular), copied from the `~/projects/assets/icons` master (assets are copied in, never referenced) | copy, once per brand change |
| `logo.svg` | accent-filled copy of the source (`currentColor` → `#0078D7`) for the sidebar's SVG candidate | s017 |
| `logo.png` | 150×150 accent glyph on transparent (sidebar raster candidate) | s017 |
| `icon-{16,32,48,64,128,512}.png` | blue `#0078D7` rounded tile + white glyph — app icon set | s017 |

`s017_generate_linprocman_brand.sh` (Zai-ZCode register) renders the set: it
rasterizes the SVG via the local GdkPixbuf loader at 512, tints via the alpha
channel, composes the tile, and LANCZOS-downscales. Run it ONLY at brand-change
time — install time never rasterizes (librsvg is optional; install.sh only
copies/rescales the checked-in rasters).

## Interface

```python
from ui import branding

branding.icon_path(size)        # checked-in raster for a size
branding.tray_icon_path()       # icon_path(128)
branding.logo_png_path() / logo_svg_path()
branding.logo_pixbuf(size)      # sidebar mark (PNG first, SVG fallback)
branding.pixbuf_for(path, size) # cached pixbuf or None (never raises)
branding.set_window_icon(win)   # ALT+Tab/taskbar: default icon + win icon
```

`ICON_SIZES`, `TRAY_ICON_SIZE = 128` and `MENU_ICON_NAME = "linprocman"`
(the `.desktop` `Icon=` key, resolving the installed hicolor set) are the
constants.

## Placements — who consumes what

| Placement | When | Consumer | Branding call |
|---|---|---|---|
| Sidebar logo (top-left mark) | runtime | `sidebar.build_logo_area` | `logo_pixbuf(LOGO_IMAGE_SIZE)` |
| Window / ALT+Tab / taskbar (`_NET_WM_ICON`) | runtime | `main._do_activate` | `set_window_icon(window)` |
| Tray / pane icon (XApp → Ayatana → StatusIcon) | runtime | `main._do_activate` → `tray.create(icon_path=…)`, `tray_icon_path()` |
| Program-menu entry | install | `install.sh` copies `icon_path(size)` set → `~/.local/share/icons/hicolor/*/apps/linprocman.png` |

Layering note: `ui/compat/tray.py` accepts `icon_path` as a parameter instead
of importing branding — the compat seam must not depend on app modules
(`main.py`, the app layer, wires the two).

## How to switch to any other logo (the recipe)

1. **Pick the SVG** from the icon master (`~/projects/assets/icons/<weight>/`)
   and copy it to `resources/images/list-checks.svg` (replace; keep the
   mandate: copied in, never referenced).
2. **Regenerate the rasters**: `bash
   ~/projects/Zai-ZCode/s017_generate_linprocman_brand.sh`. It verifies the
   set automatically (sizes, transparent corners, accent/white ink) — if the
   treatment should change (colors, radius, glyph fraction), edit s017, not
   the PNGs.
3. **Test**: `python3 -m pytest tests/test_branding.py -q` — asset checks
   plus the routing gate.
4. **Reinstall** so the menu picks the new set: `./install.sh`
   (copies the hicolor set; `Icon=linprocman` in the .desktop is stable and
   never changes).
5. **Restart the app** (`systemctl --user restart linprocman-app`) and verify:
   sidebar mark, `xprop -name linprocman _NET_WM_ICON`, tray tooltip/icon.

## Rules

- No placement may build a brand path itself — `test_branding.py` greps for
  hardcoded rasters in `main.py` / `tray.py` / `sidebar.py` (routing gate).
- PNG candidates always work; SVG rendering needs the optional librsvg
  pixbuf loader and is a fallback only (r054 lesson).
- `pixbuf_for` never raises — a missing asset degrades to the next
  candidate (sidebar falls through to the text fallback logo).
- The `.desktop` name `linprocman` is permanent infrastructure: themes
  resolve it to the installed hicolor set; rebranding never touches it.
- Everything offline; no pip/venv; Pillow + GdkPixbuf only.

## Tests

`tests/test_branding.py` — asset completeness + treatment pixels, pixbuf
helper behavior (incl. missing-file → None), `set_window_icon` smoke, and
the routing gate over `main.py` / `sidebar.py` / `tray.py`.
