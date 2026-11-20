import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SAMPLES = REPO / "projects"
SOURCE_SUFFIXES = (".kicad_pcb", ".kicad_sch", "_netlist.json", "-lib-table")


class ProjectTestCase(unittest.TestCase):
    """Copies a sample project's source files into a temp dir (tests never write into the repo)."""

    sample = "buck_12v_3v3"

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="irona_test_")
        src = SAMPLES / self.sample
        self.project_dir = Path(self._tmp) / self.sample
        self.project_dir.mkdir()
        for f in src.iterdir():
            if f.is_file() and f.name.endswith(SOURCE_SUFFIXES):
                shutil.copy2(f, self.project_dir / f.name)
        self.pcb = next(self.project_dir.glob("*.kicad_pcb"))
        self.sch = next(self.project_dir.glob("*.kicad_sch"))
        nl = list(self.project_dir.glob("*_netlist.json"))
        self.netlist = nl[0] if nl else None

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
