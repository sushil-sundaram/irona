from tests.helpers import ProjectTestCase

from irona.simulation import BoardSimulator

CURRENTS = {"VIN": 0.61, "SW_NODE": 2.0, "VOUT_3V3": 2.0}
POWER = {"U1": 0.35, "L1": 0.15}


class TestSimulation(ProjectTestCase):
    def test_parses_board(self):
        sim = BoardSimulator(self.pcb)
        self.assertGreater(len(sim.tracks), 0)
        self.assertEqual((sim.board_width_mm, sim.board_height_mm), (60.0, 40.0))
        self.assertIn("VOUT_3V3", sim.suggested_power_nets())
        self.assertNotIn("GND", sim.suggested_power_nets())

    def test_evaluate_within_limits(self):
        r = BoardSimulator(self.pcb).evaluate(CURRENTS, POWER)
        self.assertEqual(r["status"], "PASS")
        pi = r["power_integrity"]
        self.assertAlmostEqual(pi["nets"]["VOUT_3V3"]["voltage_drop_mV"], 14.13, places=1)
        self.assertEqual(pi["hotspot_net"], "VOUT_3V3")
        self.assertAlmostEqual(r["thermal"]["total_power_dissipation_w"], 0.5)
        self.assertIn("VIN", r["signal_integrity"]["trace_impedances_ohm"])

    def test_limits_trip(self):
        r = BoardSimulator(self.pcb, max_vdrop_mv=1.0, max_temp_c=26.0).evaluate(CURRENTS, POWER)
        self.assertEqual(r["status"], "FAIL")
        self.assertEqual(len(r["layout_feedback"]), 2)

    def test_no_inputs_means_no_load(self):
        r = BoardSimulator(self.pcb).evaluate()
        self.assertEqual(r["power_integrity"]["nets"], {})
        self.assertEqual(r["thermal"]["delta_temp_c"], 0.0)
