#!/usr/bin/env python3
"""
Installs the Irona plugins into KiCad's user scripting folder:

    <data>/kicad/<version>/scripting/plugins/irona_*/

where <data> is ~/.var/app/org.kicad.KiCad/data (Flatpak) or ~/.local/share (native), for every
KiCad version already present. Each plugin gets an irona_config.json pointing back at this
repository, so the shared `irona` core is imported from here (edit once, all plugins update).

Also removes the old single "Irona Hardware Engineering Studio" plugin and its PCM entries.

    python3 install_kicad_plugins.py                  # install / update the plugins
    python3 install_kicad_plugins.py --assistant-deps # also pip-install `anthropic` into KiCad's Python
    python3 install_kicad_plugins.py --register-mcp   # also add the Irona MCP server to Claude Code,
                                                      # Claude Desktop and Antigravity
    python3 install_kicad_plugins.py --uninstall      # remove everything Irona installed
    python3 install_kicad_plugins.py --dry-run        # show what would change
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PLUGINS = ["irona_simulator", "irona_rule_check", "irona_design_review", "irona_docs", "irona_assistant"]
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


# --------------------------------------------------------------------------- Assistant dependencies
FLATPAK_ID = "org.kicad.KiCad"


def install_assistant_deps(dry: bool) -> bool:
    """pip-installs `anthropic` into the Python that KiCad's plugins run in (user site-packages)."""
    flatpak_installed = shutil.which("flatpak") and subprocess.run(
        ["flatpak", "info", FLATPAK_ID], capture_output=True).returncode == 0
    if flatpak_installed:
        cmd = ["flatpak", "run", "--command=python3", FLATPAK_ID, "-m", "pip", "install", "--user", "--upgrade", "anthropic"]
    else:  # native KiCad uses the system Python
        cmd = [sys.executable, "-m", "pip", "install", "--user", "--upgrade", "anthropic"]
    print("Installing the Assistant's dependency (anthropic) for KiCad:\n  " + " ".join(cmd))
    if dry:
        return True
    return subprocess.run(cmd).returncode == 0


# --------------------------------------------------------------------------- MCP registration
MCP_NAME = "irona"


def mcp_entry(project_arg=None) -> dict:
    args = ["-m", "irona", "mcp"] + (["--project", project_arg] if project_arg else [])
    return {"command": shutil.which("python3") or sys.executable, "args": args, "env": {"PYTHONPATH": str(REPO)}}


def mcp_config_files():
    """(label, path, entry) for clients configured through a JSON file."""
    home = Path.home()
    return [
        # Antigravity substitutes the open workspace folder, so the server starts on that project.
        ("Antigravity", home / ".gemini" / "antigravity" / "mcp_config.json", mcp_entry("${workspace.path}")),
        ("Claude Desktop", home / ".config" / "Claude" / "claude_desktop_config.json", mcp_entry()),
    ]


def _edit_json(path: Path, mutate, dry: bool) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        print(f"  skip    {path} (not valid JSON)")
        return
    before = json.dumps(data, sort_keys=True)
    mutate(data)
    if json.dumps(data, sort_keys=True) == before:
        return
    print(f"  update  {path}")
    if not dry:
        if path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def register_mcp(dry: bool, remove: bool = False) -> None:
    print(("Removing" if remove else "Registering") + " the Irona MCP server:")
    for label, path, entry in mcp_config_files():
        if not path.parent.exists():
            continue  # client not installed

        def mutate(data, entry=entry):
            servers = data.setdefault("mcpServers", {})
            if remove:
                servers.pop(MCP_NAME, None)
            else:
                servers[MCP_NAME] = entry
        print(f"  {label}")
        _edit_json(path, mutate, dry)
    claude = shutil.which("claude")
    if claude:
        print("  Claude Code (user scope)")
        cmds = [[claude, "mcp", "remove", "--scope", "user", MCP_NAME]]
        if not remove:
            e = mcp_entry()
            cmds.append([claude, "mcp", "add", "--scope", "user", MCP_NAME, "-e", f"PYTHONPATH={REPO}", "--",
                         e["command"], *e["args"]])
        for cmd in cmds:
            print("    " + " ".join(cmd))
            if not dry:
                subprocess.run(cmd, capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--assistant-deps", action="store_true",
                    help="pip-install the anthropic package into KiCad's Python for the Assistant plugin")
    ap.add_argument("--register-mcp", action="store_true",
                    help="add the Irona MCP server to Claude Code, Claude Desktop and Antigravity")
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
        if args.register_mcp:
            register_mcp(dry, remove=True)
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

    ok = True
    if args.assistant_deps:
        ok = install_assistant_deps(dry)
        if not ok:
            print("Installing anthropic failed; the other plugins are installed. See the pip output above.")
    if args.register_mcp:
        register_mcp(dry)
        print("Restart Claude Desktop / Antigravity to pick up the server.")

    print("\nRestart the PCB editor (or Tools > External Plugins > Refresh Plugins).")
    print("The Irona buttons appear on the toolbar and under Tools > External Plugins.")
    if not args.assistant_deps:
        print("The Assistant also needs the anthropic package in KiCad's Python: re-run with --assistant-deps.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
