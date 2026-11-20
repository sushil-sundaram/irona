"""Irona Docs — KiCad action plugin."""

import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _irona_root() -> Path:
    """The folder containing the `irona` package: set by the installer, $IRONA_ROOT, or the repo layout."""
    cfg = _HERE / "irona_config.json"
    candidates = []
    if cfg.exists():
        candidates.append(json.loads(cfg.read_text(encoding="utf-8")).get("irona_root", ""))
    candidates += [os.environ.get("IRONA_ROOT", ""), str(_HERE.parent.parent)]
    for c in candidates:
        if c and (Path(c) / "irona" / "__init__.py").exists():
            return Path(c)
    raise ImportError("Irona core not found; re-run install_kicad_plugins.py")


_ROOT = str(_irona_root())
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from irona.kicad_ui import register_plugin, show_dialog  # noqa: E402


def _open(board, board_path):
    from .dialog import Dialog
    show_dialog(Dialog, board, board_path)


NAME = "Irona Docs"
DESCRIPTION = "Design report PDF, schematic PDF, Gerbers, drill, BOM, placement and a fab package."
plugin = register_plugin(NAME, DESCRIPTION, _HERE / "icon.png", _open)
