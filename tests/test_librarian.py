"""
Unit & Integration Tests for KiCad 10 CAD Librarian Tool
"""

import sys
import unittest
import tempfile
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.librarian import Librarian, SExprLibTableManager, SyntheticCADGenerator


class TestLibrarian(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="irona_lib_test_"))
        self.librarian = Librarian(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_synthetic_symbol_generation(self):
        pins = [
            {"num": "1", "name": "VIN", "type": "power_in", "side": "left"},
            {"num": "2", "name": "GND", "type": "power_in", "side": "left"},
            {"num": "3", "name": "VOUT", "type": "power_out", "side": "right"},
        ]
        sym = SyntheticCADGenerator.generate_symbol("TEST_REG", "U", pins, "Test LDO")
        self.assertIn('(symbol "TEST_REG"', sym)
        self.assertIn('(name "VIN"', sym)
        self.assertIn('(name "VOUT"', sym)
        self.assertIn('(property "Reference" "U"', sym)

    def test_synthetic_footprint_generation(self):
        fp = SyntheticCADGenerator.generate_footprint("TEST_IC", "SOIC", 8, pad_pitch=1.27)
        self.assertIn('(footprint "TEST_IC"', fp)
        self.assertIn('(pad "1" smd rect', fp)
        self.assertIn('(pad "8" smd rect', fp)
        self.assertIn('(layer "F.Cu")', fp)

    def test_lib_tables_registration(self):
        res = self.librarian.fetch_or_create_part("TPS54202", category="IC")
        self.assertEqual(res["mpn"], "TPS54202")
        self.assertEqual(res["symbol_lib"], "Irona_Symbols")
        self.assertEqual(res["footprint_lib"], "Irona_Footprints")

        # Verify sym-lib-table exists and contains Irona_Symbols
        sym_table = self.test_dir / "sym-lib-table"
        self.assertTrue(sym_table.exists())
        self.assertIn('Irona_Symbols', sym_table.read_text())

        # Verify fp-lib-table exists and contains Irona_Footprints
        fp_table = self.test_dir / "fp-lib-table"
        self.assertTrue(fp_table.exists())
        self.assertIn('Irona_Footprints', fp_table.read_text())

        # Verify footprint file was created
        mod_file = self.test_dir / "libraries" / "footprints.pretty" / "TPS54202.kicad_mod"
        self.assertTrue(mod_file.exists())


if __name__ == "__main__":
    unittest.main()
