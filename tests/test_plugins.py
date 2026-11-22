import importlib
import json
import sys
from pathlib import Path
from unittest import mock

from tests.helpers import REPO, ProjectTestCase

import install_kicad_plugins as installer

PLUGIN_DIR = REPO / "plugins"


class TestPluginPackages(ProjectTestCase):
    def test_every_plugin_is_complete(self):
        self.assertEqual(sorted(p.name for p in PLUGIN_DIR.iterdir() if p.is_dir() and not p.name.startswith("__")),
                         sorted(installer.PLUGINS))
        for name in installer.PLUGINS:
            d = PLUGIN_DIR / name
            for f in ("__init__.py", "dialog.py", "icon.png", "metadata.json"):
                self.assertTrue((d / f).exists(), f"{name}/{f}")
            meta = json.loads((d / "metadata.json").read_text())
            self.assertTrue(meta["identifier"].startswith("org.irona."))

    def test_imports_without_kicad(self):
        """Outside KiCad there is no pcbnew: importing must work and register nothing."""
        sys.path.insert(0, str(PLUGIN_DIR))
        try:
            for name in installer.PLUGINS:
                mod = importlib.import_module(name)
                self.assertIsNone(mod.plugin)
                self.assertTrue(mod.NAME.startswith("Irona "))
        finally:
            sys.path.remove(str(PLUGIN_DIR))

    def test_no_ai_pipeline_left(self):
        own = [p for p in REPO.joinpath("irona").rglob("*.py") if "happy" not in p.parts]  # skip vendored kicad-happy
        for path in own + list(PLUGIN_DIR.rglob("*.py")):
            text = path.read_text(encoding="utf-8").lower()
            for word in ("langgraph", "gemini", "ollama", "orchestrator"):
                self.assertNotIn(word, text, f"{word} in {path}")


class TestInstaller(ProjectTestCase):
    def test_install_and_legacy_cleanup(self):
        home = self.project_dir / "home"
        data = home / ".var/app/org.kicad.KiCad/data/kicad/10.0"
        cfg = home / ".var/app/org.kicad.KiCad/config/kicad/10.0"
        legacy = [data / "scripting/plugins/irona_kicad_plugin", data / "3rdparty/plugins/org_kicad_irona_copilot",
                  cfg / "scripting/plugins/irona_kicad_plugin"]
        for p in legacy:
            p.mkdir(parents=True)
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "installed_packages.json").write_text(json.dumps({"packages": [
            {"package": {"identifier": "org.kicad.irona_copilot"}}, {"package": {"identifier": "other.plugin"}}]}))

        with mock.patch.object(Path, "home", return_value=home), mock.patch.object(sys, "argv", ["install"]):
            self.assertEqual(installer.main(), 0)

        for p in legacy:
            self.assertFalse(p.exists(), p)
        ids = [p["package"]["identifier"] for p in json.loads((cfg / "installed_packages.json").read_text())["packages"]]
        self.assertEqual(ids, ["other.plugin"])
        for name in installer.PLUGINS:
            dest = data / "scripting/plugins" / name
            self.assertTrue((dest / "__init__.py").exists())
            self.assertEqual(json.loads((dest / "irona_config.json").read_text())["irona_root"], str(REPO))

        with mock.patch.object(Path, "home", return_value=home), mock.patch.object(sys, "argv", ["install", "--uninstall"]):
            self.assertEqual(installer.main(), 0)
        self.assertFalse(any((data / "scripting/plugins" / n).exists() for n in installer.PLUGINS))


class TestMCPRegistration(ProjectTestCase):
    def test_register_and_remove(self):
        home = self.project_dir / "home"
        ag = home / ".gemini/antigravity/mcp_config.json"
        desktop = home / ".config/Claude/claude_desktop_config.json"
        ag.parent.mkdir(parents=True)
        ag.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
        desktop.parent.mkdir(parents=True)  # installed, no config yet

        real_which = installer.shutil.which
        no_claude = lambda name: None if name == "claude" else real_which(name)  # noqa: E731
        with mock.patch.object(Path, "home", return_value=home), mock.patch.object(installer.shutil, "which", no_claude):
            installer.register_mcp(dry=False)
            servers = json.loads(ag.read_text())["mcpServers"]
            self.assertEqual(set(servers), {"other", "irona"})
            self.assertEqual(servers["irona"]["args"], ["-m", "irona", "mcp", "--project", "${workspace.path}"])
            self.assertEqual(servers["irona"]["env"]["PYTHONPATH"], str(REPO))
            self.assertTrue(ag.with_suffix(".json.bak").exists())
            self.assertIn("irona", json.loads(desktop.read_text())["mcpServers"])

            installer.register_mcp(dry=False, remove=True)
            self.assertEqual(set(json.loads(ag.read_text())["mcpServers"]), {"other"})
