"""Simulator dialog: enter load currents / part dissipation, run, read the results."""

import re

from irona import theme
from irona.kicad_ui import IronaDialog, ResultList, colour
from irona.simulation import BoardSimulator

# Parts that usually dissipate meaningful power; offered as rows to fill in.
_HOT_PART = re.compile(r"^(U|Q|L|D|VR|IC)\d", re.IGNORECASE)


class Dialog(IronaDialog):
    title = "Simulator"
    size = (860, 640)

    def build_body(self, panel, sizer):
        wx = self.wx
        import wx.grid as gridlib

        self.sim = BoardSimulator(self.project.pcb) if self.project and self.project.pcb else None
        saved = (self.project.load_sim_inputs() if self.project else None) or {}

        tables = wx.BoxSizer(wx.HORIZONTAL)
        currents = saved.get("load_currents_A") or {n: "" for n in (self.sim.suggested_power_nets() if self.sim else [])}
        power = saved.get("power_dissipation_W") or {r: "" for r in self._hot_parts()}
        self.current_grid = self._grid(gridlib, "Net", "Current (A)", currents, rows=8)
        self.power_grid = self._grid(gridlib, "Part", "Power (W)", power, rows=8)
        tables.Add(self._titled("Load currents", self.current_grid), 1, wx.EXPAND | wx.RIGHT, 12)
        tables.Add(self._titled("Dissipation", self.power_grid), 1, wx.EXPAND)
        sizer.Add(tables, 0, wx.EXPAND | wx.BOTTOM, 12)

        row = wx.BoxSizer(wx.HORIZONTAL)
        limits = saved.get("limits", {})
        self.ambient = self._num(saved.get("ambient_temp_c", 25.0))
        self.max_drop = self._num(limits.get("max_vdrop_mv", 50.0))
        self.max_temp = self._num(limits.get("max_temp_c", 85.0))
        self.labelled(row, "Ambient °C", self.ambient)
        self.labelled(row, "Max drop mV", self.max_drop)
        self.labelled(row, "Max temp °C", self.max_temp)
        row.AddStretchSpacer()
        row.Add(self.button("Run", self.on_run, primary=True))
        sizer.Add(row, 0, wx.EXPAND | wx.BOTTOM, 12)

        self.results = ResultList(self, [("Status", 70), ("Item", 160), ("Value", 260), ("Note", 300)])
        sizer.Add(self.results.ctrl, 1, wx.EXPAND)

        if not self.sim:
            self.set_status("Save the board, then reopen the Simulator.", "error")
        elif not currents:
            self.set_status("No routed supply nets detected: type net names in the left table.")

    # ---- widgets
    def _hot_parts(self):
        from irona.docs import read_board_footprints
        if not (self.project and self.project.pcb):
            return []
        return sorted({fp["ref"] for fp in read_board_footprints(self.project.pcb) if _HOT_PART.match(fp["ref"])})

    def _grid(self, gridlib, key_label, value_label, values, rows):
        g = gridlib.Grid(self.panel)
        g.CreateGrid(max(rows, len(values) + 2), 2)
        g.SetColLabelValue(0, key_label)
        g.SetColLabelValue(1, value_label)
        g.SetRowLabelSize(0)
        g.SetColSize(0, 200)
        g.SetColSize(1, 110)
        g.SetDefaultCellBackgroundColour(colour(theme.SURFACE))
        g.SetDefaultCellTextColour(colour(theme.FOREGROUND))
        g.SetLabelBackgroundColour(colour(theme.BACKGROUND))
        g.SetLabelTextColour(colour(theme.COMMENT))
        g.SetGridLineColour(colour(theme.CURRENT_LINE))
        g.SetMinSize((-1, 190))

        def stretch(evt):
            g.SetColSize(0, max(80, g.GetClientSize().width - g.GetColSize(1) - 2))
            evt.Skip()

        g.Bind(self.wx.EVT_SIZE, stretch)
        for i, (k, v) in enumerate(values.items()):
            g.SetCellValue(i, 0, str(k))
            g.SetCellValue(i, 1, "" if v == "" else f"{v:g}")
        return g

    def _titled(self, label, ctrl):
        wx = self.wx
        s = wx.BoxSizer(wx.VERTICAL)
        t = wx.StaticText(self.panel, label=label)
        t.SetForegroundColour(colour(theme.PURPLE))
        t._irona_keep_fg = True
        s.Add(t, 0, wx.BOTTOM, 4)
        s.Add(ctrl, 1, wx.EXPAND)
        return s

    def _num(self, value):
        wx = self.wx
        c = wx.SpinCtrlDouble(self.panel, min=-1000, max=100000, initial=float(value), inc=1, size=(90, -1))
        c.SetDigits(1)
        return c

    @staticmethod
    def _read(grid):
        out = {}
        for r in range(grid.GetNumberRows()):
            key, val = grid.GetCellValue(r, 0).strip(), grid.GetCellValue(r, 1).strip()
            if key and val:
                out[key] = float(val)
        return out

    # ---- actions
    def on_run(self):
        if not self.require_project():
            return
        self.current_grid.SaveEditControlValue()
        self.power_grid.SaveEditControlValue()
        try:
            currents, power = self._read(self.current_grid), self._read(self.power_grid)
        except ValueError:
            self.set_status("Currents and powers must be numbers.", "error")
            return
        if not currents:
            self.set_status("Enter at least one net current.", "warning")
            return
        limits = {"max_vdrop_mv": self.max_drop.GetValue(), "max_temp_c": self.max_temp.GetValue()}
        ambient = self.ambient.GetValue()
        self.project.save_sim_inputs({"load_currents_A": currents, "power_dissipation_W": power,
                                      "ambient_temp_c": ambient, "limits": limits})

        def work():
            sim = BoardSimulator(self.project.pcb, ambient_temp_c=ambient, **limits)
            return sim.evaluate(currents, power)

        self.run_async(work, self.show_results, "Simulating…")

    def show_results(self, r):
        rl = self.results
        rl.clear()
        lim = r["limits"]
        for net, v in r["power_integrity"]["nets"].items():
            ok = v["voltage_drop_mV"] <= lim["max_vdrop_mv"] and v["max_current_density_A_mm2"] <= lim["max_current_density_A_mm2"]
            rl.add("pass" if ok else "fail", net,
                   f"{v['voltage_drop_mV']} mV · {v['max_current_density_A_mm2']} A/mm²",
                   f"{v['load_current_A']:g} A through {v['trace_resistance_mOhm']} mΩ")
        t = r["thermal"]
        rl.add("pass" if t["max_junction_temp_c"] <= lim["max_temp_c"] else "fail", "Hotspot estimate",
               f"{t['max_junction_temp_c']} °C (+{t['delta_temp_c']} °C)",
               f"{t['total_power_dissipation_w']} W over {t['board_size_mm'][0]}×{t['board_size_mm'][1]} mm")
        for net, z in sorted(r["signal_integrity"]["trace_impedances_ohm"].items()):
            rl.add("info", f"Z0 {net}", f"{z} Ω", "surface microstrip, 1.5 mm FR-4")
        rl.fit_last_column()
        msg = "  ".join(r["layout_feedback"])
        self.set_status(msg, "pass" if r["status"] == "PASS" else "fail")
