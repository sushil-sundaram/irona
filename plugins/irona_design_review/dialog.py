"""Design Review dialog: SI/PI + IPC review and the kicad-happy circuit / EMC / DFM review."""

from irona.circuit_review import CircuitReviewer
from irona.kicad_ui import IronaDialog, ResultList, open_path
from irona.sipi_review import SIPIReviewer

_PREFIX_SEVERITY = (("❌", "error"), ("⚠️", "warning"), ("✅", "pass"))
FILTERS = ["Errors and warnings", "Everything", "Errors only"]


class Dialog(IronaDialog):
    title = "Design Review"
    size = (900, 600)

    def build_body(self, panel, sizer):
        wx = self.wx
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.filter = wx.Choice(panel, choices=FILTERS)
        self.filter.SetSelection(0)
        self.filter.Bind(wx.EVT_CHOICE, lambda _e: self.render())
        self.labelled(row, "Show", self.filter)
        row.AddStretchSpacer()
        self.report_btn = self.button("Open report", self.on_open_report)
        self.report_btn.Disable()
        row.Add(self.report_btn, 0, wx.RIGHT, 8)
        row.Add(self.button("Run", self.on_run, primary=True))
        sizer.Add(row, 0, wx.EXPAND | wx.BOTTOM, 12)

        self.results = ResultList(self, [("Severity", 80), ("Area", 90), ("Topic", 220), ("Finding", 420)])
        sizer.Add(self.results.ctrl, 1, wx.EXPAND)
        self.items = []
        self.summary = ""
        self.report_path = None

    def on_run(self):
        if not self.require_project():
            return
        pr = self.project

        def work():
            sipi = SIPIReviewer(pr.pcb, pr.sch, pr.netlist, pr.load_sim_inputs()).generate_review_report()
            circuit = CircuitReviewer().run_full_analysis(pr.sch, pr.pcb, pr.output_dir / "circuit-review") if pr.sch else None
            return sipi, circuit

        self.run_async(work, self.collect, "Reviewing…")

    def collect(self, result):
        sipi, circuit = result
        items = []
        for cat in sipi["categories"]:
            for f in cat["findings"]:
                sev = next((s for p, s in _PREFIX_SEVERITY if f.startswith(p)), "info")
                text = f
                for p, _ in _PREFIX_SEVERITY:
                    text = text.replace(p, "", 1) if text.startswith(p) else text
                items.append((sev, "SI/PI", cat["name"], text.strip()))
        parts = [f"SI/PI {sipi['overall_score']}% ({sipi['letter_grade']})"]

        if circuit:
            for f in circuit["findings"]:
                items.append((f["severity"], "Circuit", f"{f['rule_id']} · {f['category']}", f["summary"]))
            for fab, label in (("jlcpcb", "JLCPCB"), ("pcbway", "PCBWay")):
                for c in circuit["dfm_audit"][fab]["checks"]:
                    items.append(("pass" if c["pass"] else "error", "DFM", f"{label} · {c['name']}", f"{c['actual']} (rule {c['limit']})"))
            emc = circuit["emc_score"]
            parts.append(f"Circuit {circuit['overall_score']} ({circuit['grade']})")
            parts.append(f"EMC {emc}/100" if emc is not None else "EMC unavailable")
            parts.append(f"DFM {circuit['dfm_score']:.0f}%")
            self.report_path = circuit.get("report_path")
            self.report_btn.Enable(bool(self.report_path))
        else:
            parts.append("circuit review skipped (no schematic)")

        order = {"error": 0, "fail": 0, "warning": 1, "info": 2, "pass": 3}
        self.items = sorted(items, key=lambda i: order.get(i[0], 2))
        errors = sum(1 for i in items if i[0] in ("error", "fail"))
        warnings = sum(1 for i in items if i[0] == "warning")
        self.summary = "  ·  ".join(parts) + f"  ·  {errors} errors, {warnings} warnings"
        self.render()
        self.set_status(self.summary, "error" if errors else ("warning" if warnings else "pass"))

    def render(self):
        mode = FILTERS[self.filter.GetSelection()]
        keep = {"Everything": None, "Errors only": {"error", "fail"}, "Errors and warnings": {"error", "fail", "warning"}}[mode]
        self.results.clear()
        for sev, area, topic, text in self.items:
            if keep is None or sev in keep:
                self.results.add(sev, area, topic, text)
        if self.items and not self.results.rows:
            self.results.add("pass", "", "", "Nothing to show for this filter.")
        self.results.fit_last_column()

    def on_open_report(self):
        if self.report_path:
            open_path(self.report_path)
