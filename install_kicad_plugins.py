#!/usr/bin/env python3
"""
Installs the Irona plugins into KiCad's user scripting folder:

    <data>/kicad/<version>/scripting/plugins/irona_*/

where <data> is ~/.var/app/org.kicad.KiCad/data (Flatpak) or ~/.local/share (native), for every
KiCad version already present. Each plugin gets an irona_config.json pointing back at this
repository, so the shared `irona` core is imported from here (edit once, all plugins update).

Also removes the old single "Irona Hardware Engineering Studio" plugin and its PCM entries.

    python3 install_kicad_plugins.py              # install / update
    python3 install_kicad_plugins.py --uninstall  # remove everything Irona installed
    python3 install_kicad_plugins.py --dry-run    # show what would change
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PLUGINS = ["irona_simulator", "irona_rule_check", "irona_design_review", "irona_docs"]
LEGACY_DIRS = ["irona_kicad_plugin", "org_kicad_irona_copilot"]
LEGACY_PCM_IDS = {"org.kicad.irona_copilot", "irona.kicad.plugin"}
VERSIONS = ["10.0", "9.0"]


def kicad_roots():
    """(data_root, config_root) pairs for Flatpak and native KiCad."""
    home = Path.home()
    flatpak = home / ".var" / "app" / "org.kicad.KiCad"
    return [
        (flatpak / "data" / "kicad", flatpak / "config" / "kicad"),
        (home / ".local" / "share" / "kicad", home / ".config" / "kicad"),
    ]


def plugin_dirs():
    for data_root, _ in kicad_roots():
        for ver in VERSIONS:
            if (data_root / ver).is_dir():
                yield data_root / ver / "scripting" / "plugins"


def legacy_paths():
    """Every place the old installer may have copied the AI co-pilot plugin."""
    home = Path.home()
    for data_root, config_root in kicad_roots():
        for ver in VERSIONS + ["8.0"]:
            for base in (data_root / ver / "scripting" / "plugins", config_root / ver / "scripting" / "plugins",
                         data_root / ver / "3rdparty" / "plugins"):
                for name in LEGACY_DIRS:
                    yield base / name
    for base in (home / ".kicad_plugins", home / ".kicad" / "scripting" / "plugins"):
        yield base / "irona_kicad_plugin"


def remove(path: Path, dry: bool) -> None:
    if path.is_symlink() or path.exists():
        print(f"  remove  {path}")
        if not dry:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()


def clean_pcm_registry(dry: bool) -> None:
    for _, config_root in kicad_roots():
        for ver in VERSIONS:
            f = config_root / ver / "installed_packages.json"
            if not f.exists():
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            pkgs = data.get("packages", [])
            keep = [p for p in pkgs if p.get("package", {}).get("identifier") not in LEGACY_PCM_IDS]
            if len(keep) != len(pkgs):
                print(f"  unregister legacy package in {f}")
                if not dry:
                    shutil.copy2(f, f.with_suffix(".json.bak"))
                    data["packages"] = keep
                    f.write_text(json.dumps(data, indent=4), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run

    targets = list(plugin_dirs())
    if not targets and not args.uninstall:
        print("No KiCad 9/10 user folder found. Start KiCad once, then re-run.")
        return 1

    print("Removing the legacy AI co-pilot plugin (if present):")
    for p in legacy_paths():
        remove(p, dry)
    clean_pcm_registry(dry)

    for d in targets:
        for name in PLUGINS:
            remove(d / name, dry)
    if args.uninstall:
        print("Uninstalled.")
        return 0

    for d in targets:
        print(f"Installing into {d}")
        for name in PLUGINS:
            dest = d / name
            print(f"  add     {dest}")
            if dry:
                continue
            d.mkdir(parents=True, exist_ok=True)
            shutil.copytree(REPO / "plugins" / name, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            (dest / "irona_config.json").write_text(json.dumps({"irona_root": str(REPO)}, indent=2), encoding="utf-8")

    print("\nRestart the PCB editor (or Tools > External Plugins > Refresh Plugins).")
    print("The four Irona buttons appear on the toolbar and under Tools > External Plugins.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
