"""
Unit & Integration Tests for KiCad 10 IPC Router & Layout Engine
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

from tools.ipc_router import IPCRouterEngine
from kicad_scripts.ipc_server_bridge import MockKiCadIPCServer, KiCad10IPCClient


class TestIPCRouter(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="irona_router_test_"))

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_mock_ipc_server_communication(self):
        server = MockKiCadIPCServer(port=4299)
        server.start()
        try:
            client = KiCad10IPCClient(port=4299)
            connected = client.connect(timeout=2.0)
            self.assertTrue(connected)
            self.assertTrue(client.ping())

            res_place = client.place_footprint("U1", 25.0, 20.0)
            self.assertEqual(res_place["placed"], "U1")

            res_drc = client.run_drc()
            self.assertEqual(res_drc["status"], "PASS")
            client.close()
        finally:
            server.stop()

    def test_headless_pcb_routing_and_export(self):
        router = IPCRouterEngine(board_width=60.0, board_height=40.0)
        netlist_data = {
            "project": "test_board",
            "components": [
                {"ref": "U1", "value": "TPS54202", "footprint": "Irona_Footprints:TPS54202"},
                {"ref": "L1", "value": "4.7uH", "footprint": "Irona_Footprints:L_0805"}
            ],
            "nets": {"SW_NODE": [], "VIN": [], "GND": []}
        }
        router.execute_buck_converter_layout(netlist_data)

        pcb_file = self.test_dir / "test_board.kicad_pcb"
        saved_path = router.save(pcb_file)

        self.assertTrue(saved_path.exists())
        content = saved_path.read_text(encoding="utf-8")
        self.assertIn("(kicad_pcb", content)
        self.assertIn('(segment', content)
        self.assertIn('(via', content)
        self.assertIn('(zone', content)
        self.assertIn('(layer "Edge.Cuts")', content)


if __name__ == "__main__":
    unittest.main()
