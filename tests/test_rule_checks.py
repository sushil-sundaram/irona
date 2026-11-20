from tests.helpers import ProjectTestCase

from irona.drc import DRCEngine
from irona.erc import ERCEngine


class TestCleanBoard(ProjectTestCase):
    def test_drc_passes(self):
        r = DRCEngine(self.pcb).run_drc()
        self.assertEqual(r["status"], "PASS")
        self.assertEqual(r["error_count"], 0)
        self.assertGreater(r["total_tracks"], 0)

    def test_erc_passes(self):
        r = ERCEngine(self.sch, self.netlist).run_erc()
        self.assertEqual(r["status"], "PASS")
        self.assertGreater(r["total_symbols"], 0)


class TestBoardWithViolations(ProjectTestCase):
    sample = "test_proj"

    def test_drc_reports_clearance_violations(self):
        r = DRCEngine(self.pcb).run_drc()
        self.assertEqual(r["status"], "FAIL")
        rules = {v["rule"] for v in r["violations"]}
        self.assertIn("TRACK_TO_TRACK_CLEARANCE", rules)
        for v in r["violations"]:
            self.assertIn("description", v)
