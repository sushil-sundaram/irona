"""
Unit & Integration Tests for Schematic Builder Tool
"""

import sys
import unittest
import tempfile
import shutil
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.schematic_builder import SchematicCircuitBuilder
from kicad_scripts.sexpr_generator import KiCad10SchematicGenerator


class TestSchematicBuilder(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="irona_sch_test_"))
        self.builder = SchematicCircuitBuilder("test_circuit", self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_buck_circuit_generation(self):
        self.builder.build_buck_converter_circuit(vin_v=12.0, vout_v=3.3, iout_a=2.0)
        sch_path = self.builder.export_schematic()
        netlist_path = self.builder.export_netlist()

        # Check schematic file
        self.assertTrue(sch_path.exists())
        content = sch_path.read_text(encoding="utf-8")
        self.assertIn("(kicad_sch", content)
        self.assertIn('(property "Reference" "U1"', content)
        self.assertIn('(property "Reference" "L1"', content)
        self.assertIn('(label "SW_NODE"', content)
        self.assertIn('(label "VOUT_3V3"', content)

        # Check netlist file
        self.assertTrue(netlist_path.exists())
        netlist_data = json.loads(netlist_path.read_text(encoding="utf-8"))
        self.assertIn("components", netlist_data)
        self.assertIn("nets", netlist_data)
        self.assertIn("SW_NODE", netlist_data["nets"])
        self.assertIn("VIN", netlist_data["nets"])
        self.assertIn("GND", netlist_data["nets"])


if __name__ == "__main__":
    unittest.main()
