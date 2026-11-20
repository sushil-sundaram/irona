import json
import zipfile
from unittest import mock

from tests.helpers import ProjectTestCase

from irona import docs
from irona.docs import DocumentationGenerator, read_board_footprints
from irona.report_pdf import DesignReportPDF, PureVectorPDF, group_bom


class TestPDFEngine(ProjectTestCase):
    def test_builds_valid_pdf(self):
        pdf = PureVectorPDF()
        pdf.add_section_header("Title", "subtitle")
        pdf.add_table(["A", "Status"], [["x" * 300, "FAIL"], ["y", "PASS"]])
        data = pdf.build()
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertTrue(data.endswith(b"%%EOF\n"))

    def test_fail_badge_is_red(self):
        pdf = PureVectorPDF()
        pdf.add_badge(0, 0, "FAIL", "FAIL")
        self.assertIn("0.80 0.15 0.15 rg", " ".join(pdf.pages[-1]))

    def test_group_bom(self):
        rows = group_bom([("R2", "10k", "lib:R_0805"), ("R1", "10k", "lib:R_0805"), ("C1", "1u", "lib:C")])
        self.assertIn(["R1, R2", "10k", "R_0805", "2"], rows)


class TestReport(ProjectTestCase):
    def test_report_reflects_results(self):
        out = DesignReportPDF(self.project_dir).generate_pdf()
        content = out.read_bytes()
        self.assertTrue(content.startswith(b"%PDF-1.4"))
        self.assertIn(b"No load currents configured", content)
        self.assertNotIn(b"IPC-6012 CLASS 3", content)  # no more boilerplate claims

    def test_report_includes_simulation_when_configured(self):
        (self.project_dir / "irona-sim.json").write_text(json.dumps({"load_currents_A": {"VOUT_3V3": 2.0}}))
        content = DesignReportPDF(self.project_dir).generate_pdf().read_bytes()
        self.assertIn(b"VOUT_3V3", content)
        self.assertNotIn(b"No load currents configured", content)


class TestDocs(ProjectTestCase):
    def test_reads_footprints(self):
        fps = read_board_footprints(self.pcb)
        self.assertIn("U1", [f["ref"] for f in fps])
        self.assertTrue(all(f["footprint"] for f in fps))

    def test_without_kicad_cli_nothing_is_faked(self):
        with mock.patch.object(docs, "find_kicad_cli", return_value=None):
            out = DocumentationGenerator(self.project_dir).build_all()
        self.assertEqual(out["gerbers"], [])
        self.assertIsNone(out["fab_package"])
        self.assertIsNone(out["schematic_pdf"])
        self.assertTrue(out["report"].exists())
        self.assertTrue(out["bom"].exists())
        self.assertTrue(out["positions"].exists())
        self.assertTrue(any("kicad-cli not found" in s for s in out["skipped"]))
        html = out["index"].read_text()
        self.assertIn("#282a36", html)  # Dracula background
        self.assertIn("not generated", html)

    def test_fab_package_contains_given_gerbers(self):
        gen = DocumentationGenerator(self.project_dir)
        g = gen.output_dir / "gerbers"
        g.mkdir()
        (g / "board-F_Cu.gbr").write_text("G04*")
        z = gen.create_fab_package([g / "board-F_Cu.gbr"])
        names = zipfile.ZipFile(z).namelist()
        self.assertIn("gerbers/board-F_Cu.gbr", names)
        self.assertTrue(any(n.startswith("assembly/") and n.endswith("_bom.csv") for n in names))
