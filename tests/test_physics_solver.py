"""
Unit & Integration Tests for Physics Solver Tool
"""

import sys
import unittest
import tempfile
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.physics_solver import PhysicsSolverEngine
from tools.ipc_router import IPCRouterEngine


class TestPhysicsSolver(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="irona_physics_test_"))
        self.pcb_file = self.test_dir / "physics_test.kicad_pcb"

        # Generate a test board
        router = IPCRouterEngine(board_width=60.0, board_height=40.0)
        netlist_data = {"project": "physics_test", "components": [], "nets": {}}
        router.execute_buck_converter_layout(netlist_data)
        router.save(self.pcb_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_physics_evaluation(self):
        solver = PhysicsSolverEngine(self.pcb_file)
        results = solver.evaluate_board(iout_a=2.0)

        self.assertIn("status", results)
        self.assertEqual(results["status"], "PASS")

        # Power Integrity metrics
        pi = results["power_integrity"]
        self.assertIn("max_voltage_drop_mv", pi)
        self.assertIn("max_current_density_A_mm2", pi)
        self.assertLess(pi["max_voltage_drop_mv"], 50.0)
        self.assertLess(pi["max_current_density_A_mm2"], 35.0)

        # Thermal metrics
        th = results["thermal"]
        self.assertIn("max_junction_temp_c", th)
        self.assertLess(th["max_junction_temp_c"], 85.0)

        # Signal Integrity metrics
        si = results["signal_integrity"]
        self.assertIn("trace_impedances_ohm", si)


if __name__ == "__main__":
    unittest.main()
