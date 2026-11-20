"""Rule Check dialog: DRC on the board and ERC on its schematic."""

from irona.drc import DRCEngine
from irona.erc import ERCEngine
from irona.kicad_ui import IronaDialog, ResultList


class Dialog(IronaDialog):
    title = "Rule Check"

    def build_body(self, panel, sizer):
        wx = self.wx
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.clearance = wx.SpinCtrlDouble(panel, min=0.05, max=5, initial=0.2, inc=0.05, size=(90, -1))
        self.clearance.SetDigits(2)
        self.drill = wx.SpinCtrlDouble(panel, min=0.1, max=5, initial=0.3, inc=0.05, size=(90, -1))
        self.drill.SetDigits(2)
        self.labelled(row, "Clearance mm", self.clearance)
        self.labelled(row, "Min drill mm", self.drill)
        row.AddStretchSpacer()
        row.Add(self.button("Run", self.on_run, primary=True))
        sizer.Add(row, 0, wx.EXPAND | wx.BOTTOM, 12)

        self.results = ResultList(self, [("Severity", 80), ("Check", 60), ("Rule", 200), ("Detail", 420)])
        sizer.Add(self.results.ctrl, 1, wx.EXPAND)

    def on_run(self):
        if not self.require_project():
            return
        pr = self.project
        clearance, drill = self.clearance.GetValue(), self.drill.GetValue()

        def work():
            drc = DRCEngine(pr.pcb, min_clearance_mm=clearance, min_drill_mm=drill).run_drc()
            erc = ERCEngine(pr.sch, pr.netlist).run_erc() if pr.sch else None
            return drc, erc

        self.run_async(work, self.show_results, "Checking…")

    def show_results(self, result):
        drc, erc = result
        rl = self.results
        rl.clear()
        for v in drc["violations"]:
            loc = v.get("location")
            where = f"  @ ({loc[0]:.2f}, {loc[1]:.2f}) mm" if isinstance(loc, (list, tuple)) and len(loc) == 2 else ""
            rl.add(str(v.get("severity", "error")).lower(), "DRC", v.get("rule", ""), v.get("description", "") + where)
        if erc:
            for v in erc.get("violations", []) + erc.get("warnings", []):
                if isinstance(v, dict):
                    rl.add(str(v.get("severity", "warning")).lower(), "ERC", v.get("rule", ""), v.get("description", ""))
                else:
                    rl.add("warning", "ERC", "", str(v))
        rl.fit_last_column()

        parts = [f"DRC {drc['error_count']} errors"]
        parts.append(f"ERC {erc['error_count']} errors, {erc['warning_count']} warnings" if erc else "ERC skipped (no schematic)")
        failed = drc["error_count"] or (erc and erc["error_count"])
        if not rl.rows:
            rl.add("pass", "DRC/ERC", "", "No violations.")
        self.set_status("  ·  ".join(parts), "fail" if failed else "pass")
