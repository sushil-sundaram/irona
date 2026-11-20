"""Docs dialog: generate the report, schematic PDF, Gerbers/drill, BOM, placement and fab package."""

from pathlib import Path

from irona.docs import DocumentationGenerator
from irona.kicad_ui import IronaDialog, ResultList, open_path


class Dialog(IronaDialog):
    title = "Docs"
    size = (820, 520)

    def build_body(self, panel, sizer):
        wx = self.wx
        row = wx.BoxSizer(wx.HORIZONTAL)
        out = (self.project.output_dir / "docs") if self.project else None
        self.out_label = wx.StaticText(panel, label=f"Output: {out}" if out else "")
        row.Add(self.out_label, 1, wx.ALIGN_CENTER_VERTICAL)
        self.folder_btn = self.button("Open folder", self.on_open_folder)
        self.folder_btn.Enable(bool(out and out.exists()))
        row.Add(self.folder_btn, 0, wx.RIGHT, 8)
        row.Add(self.button("Generate", self.on_generate, primary=True))
        sizer.Add(row, 0, wx.EXPAND | wx.BOTTOM, 12)

        self.results = ResultList(self, [("Status", 80), ("Output", 200), ("File", 480)])
        self.results.ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_activate)
        sizer.Add(self.results.ctrl, 1, wx.EXPAND)
        self.paths = []
        self.gen = None

    def on_generate(self):
        if not self.require_project():
            return
        self.gen = DocumentationGenerator(self.project.dir)
        self.run_async(self.gen.build_all, self.show_results, "Generating (Gerbers can take a few seconds)…")

    def show_results(self, out):
        rl = self.results
        rl.clear()
        self.paths = []
        labels = [("index", "Index page"), ("report", "Design report"), ("schematic_pdf", "Schematic PDF"),
                  ("fab_package", "Fab package"), ("bom", "BOM"), ("positions", "Positions")]
        for key, label in labels:
            p = out.get(key)
            rl.add("ok" if p else "warning", label, str(p) if p else "not generated")
            self.paths.append(p)
        if out.get("gerbers"):
            rl.add("ok", "Gerbers + drill", f"{len(out['gerbers'])} files in {Path(out['gerbers'][0]).parent}")
            self.paths.append(Path(out["gerbers"][0]).parent)
        for s in out.get("skipped", []):
            rl.add("warning", "Skipped", s)
            self.paths.append(None)
        rl.fit_last_column()
        self.folder_btn.Enable()
        n_skipped = len(out.get("skipped", []))
        self.set_status("Done. Double-click a row to open it." + (f"  {n_skipped} item(s) skipped." if n_skipped else ""),
                        "warning" if n_skipped else "pass")

    def on_activate(self, evt):
        i = evt.GetIndex()
        if 0 <= i < len(self.paths) and self.paths[i]:
            open_path(self.paths[i])

    def on_open_folder(self):
        if self.project:
            open_path(self.project.output_dir / "docs")
