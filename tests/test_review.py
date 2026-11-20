from tests.helpers import ProjectTestCase

from irona.circuit_review import CircuitReviewer
from irona.sipi_review import SIPIReviewer


class TestSIPIReview(ProjectTestCase):
    def test_categories_and_score(self):
        r = SIPIReviewer(self.pcb, self.sch, self.netlist).generate_review_report()
        self.assertEqual(len(r["categories"]), 6)
        names = " ".join(c["name"] for c in r["categories"])
        for key in ("IPC-2221", "IPC-2222", "IPC-6012", "Hot Loop"):
            self.assertIn(key, names)
        self.assertGreaterEqual(r["overall_score"], 85.0)

    def test_current_checks_only_with_sim_inputs(self):
        without = SIPIReviewer(self.pcb).evaluate_ipc_2221()["findings"]
        self.assertFalse(any("current density" in f for f in without))
        with_inputs = SIPIReviewer(self.pcb, sim_inputs={"load_currents_A": {"VOUT_3V3": 2.0}}).evaluate_ipc_2221()["findings"]
        self.assertTrue(any("current density" in f for f in with_inputs))


class TestCircuitReview(ProjectTestCase):
    def test_full_analysis_uses_detected_data(self):
        out = self.project_dir / "out"
        r = CircuitReviewer().run_full_analysis(self.sch, self.pcb, out)
        rails = {x["rail"]: x["voltage"] for x in r["power_tree"]["rails"]}
        self.assertEqual(rails.get("VOUT_3V3"), 3.3)
        self.assertIn("U1", [reg["ref"] for reg in r["power_tree"]["regulators"]])
        self.assertIn("jlcpcb", r["dfm_audit"])
        self.assertEqual(r["findings_count"]["total"], len(r["findings"]))
        self.assertTrue((out / "circuit_review.md").exists())
        self.assertTrue((out / "schematic_analysis.json").exists())
