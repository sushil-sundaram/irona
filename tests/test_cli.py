import contextlib
import io
import json

from tests.helpers import ProjectTestCase

from irona.cli import main


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(list(argv))
    return code, buf.getvalue()


class TestCLI(ProjectTestCase):
    def test_sim_requires_currents(self):
        with self.assertRaises(SystemExit) as cm:
            run("sim", str(self.project_dir))
        self.assertIn("VOUT_3V3", str(cm.exception))

    def test_sim_saves_and_checks(self):
        code, out = run("sim", str(self.project_dir), "--current", "VOUT_3V3=2", "--power", "U1=0.35", "--save", "--check")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], "PASS")
        self.assertTrue((self.project_dir / "irona-sim.json").exists())
        code, out = run("sim", str(self.project_dir))  # reuses the saved inputs
        self.assertIn("VOUT_3V3", json.loads(out)["power_integrity"]["nets"])

    def test_check(self):
        code, out = run("check", str(self.project_dir), "--check")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["drc"]["status"], "PASS")


class TestCLIFailing(ProjectTestCase):
    sample = "test_proj"

    def test_check_exit_code(self):
        code, _ = run("check", str(self.project_dir), "--check")
        self.assertEqual(code, 1)
