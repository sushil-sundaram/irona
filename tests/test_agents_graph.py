"""
Unit & Integration Tests for LangGraph Multi-Agent Engine
"""

import sys
import unittest
import tempfile
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.state import IronaAgentState
from agents.graph import IronaDesignGraph


class TestMultiAgentGraph(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="irona_graph_test_"))

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_end_to_end_graph_execution(self):
        initial_state: IronaAgentState = {
            "project_name": "test_graph_buck",
            "project_dir": str(self.test_dir),
            "spec_prompt": "12V to 3.3V 2A Buck Regulator",
            "requirements": {
                "circuit_type": "Synchronous_Buck_Converter",
                "vin_nominal_v": 12.0,
                "vout_target_v": 3.3,
                "iout_max_a": 2.0,
                "switching_freq_khz": 500.0,
                "ambient_temp_c": 25.0,
                "max_allowed_temp_c": 85.0
            },
            "bom": [],
            "libraries_registered": False,
            "schematic_path": None,
            "netlist_path": None,
            "pcb_path": None,
            "spatial_layout_plan": {},
            "physics_results": None,
            "physics_passed": False,
            "iteration_count": 0,
            "max_iterations": 3,
            "messages": [],
            "errors": [],
            "status": "INITIALIZED"
        }

        graph = IronaDesignGraph()
        final_state = graph.run(initial_state)

        # Assert all stages completed
        self.assertEqual(final_state["status"], "COMPLETED")
        self.assertTrue(final_state["libraries_registered"])
        self.assertIsNotNone(final_state["schematic_path"])
        self.assertIsNotNone(final_state["pcb_path"])
        self.assertTrue(Path(final_state["schematic_path"]).exists())
        self.assertTrue(Path(final_state["pcb_path"]).exists())
        self.assertTrue(final_state["physics_passed"])


if __name__ == "__main__":
    unittest.main()
