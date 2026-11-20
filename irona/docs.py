"""
Documentation and manufacturing outputs for a KiCad project.

Real fabrication files (Gerbers, drill, positions, schematic PDF) are produced with kicad-cli.
If kicad-cli is not available those outputs are skipped and reported as such; nothing is faked.
The BOM / placement CSVs, the PDF design report and an index page are always produced.
"""

import csv
import html
import logging
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from irona import theme
from irona.project import Project
from irona.report_pdf import DesignReportPDF, group_bom

logger = logging.getLogger(__name__)

FLATPAK_KICAD = ["flatpak", "run", "--command=kicad-cli", "org.kicad.KiCad"]


def find_kicad_cli() -> Optional[List[str]]:
    """Command prefix for kicad-cli: on PATH (incl. inside KiCad's flatpak) or via the host flatpak."""
    exe = shutil.which("kicad-cli")
    if exe:
        return [exe]
    if shutil.which("flatpak"):
        try:
            probe = subprocess.run(FLATPAK_KICAD + ["version"], capture_output=True, text=True, timeout=60)
            if probe.returncode == 0:
                return list(FLATPAK_KICAD)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def read_board_footprints(pcb_path: Path) -> List[Dict[str, Any]]:
    """Reference, value, footprint, position, rotation and side of every footprint on the board."""
    content = Path(pcb_path).read_text(encoding="utf-8")
    out = []
    # Split on top-level footprint blocks; each chunk runs until the next footprint.
    for chunk in re.split(r'\n\s*\(footprint\s+', content)[1:]:
        name = re.match(r'"([^"]+)"', chunk)
        layer = re.search(r'\(layer\s+"([^"]+)"\)', chunk)
        at = re.search(r'\(at\s+([\d.-]+)\s+([\d.-]+)(?:\s+([\d.-]+))?\)', chunk)
        ref = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', chunk) or re.search(r'\(fp_text\s+reference\s+"?([^"\s)]+)', chunk)
        val = re.search(r'\(property\s+"Value"\s+"([^"]*)"', chunk) or re.search(r'\(fp_text\s+value\s+"?([^"\s)]+)', chunk)
        if not (name and at and ref):
            continue
        out.append({
            "ref": ref.group(1),
            "value": val.group(1) if val else "",
            "footprint": name.group(1),
            "x": float(at.group(1)),
            "y": float(at.group(2)),
            "rotation": float(at.group(3) or 0.0),
            "side": "bottom" if layer and layer.group(1).startswith("B.") else "top",
        })
    return out


class DocumentationGenerator:
    """Builds the documentation folder (irona-out/docs) for one project."""

    def __init__(self, project_dir: Path, output_dir: Optional[Path] = None):
        self.project = Project(project_dir)
        self.output_dir = Path(output_dir) if output_dir else self.project.output_dir / "docs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.skipped: List[str] = []
        self._cli: Optional[List[str]] = None
        self._cli_checked = False

    # ------------------------------------------------------------------ kicad-cli
    @property
    def kicad_cli(self) -> Optional[List[str]]:
        if not self._cli_checked:
            self._cli, self._cli_checked = find_kicad_cli(), True
        return self._cli

    def _run_cli(self, args: List[str], what: str) -> bool:
        if not self.kicad_cli:
            self.skipped.append(f"{what}: kicad-cli not found")
            return False
        proc = subprocess.run(self.kicad_cli + args, capture_output=True, text=True)
        if proc.returncode != 0:
            self.skipped.append(f"{what}: kicad-cli failed ({proc.stderr.strip().splitlines()[-1:] or proc.returncode})")
            return False
        return True

    def export_gerbers(self) -> List[Path]:
        if not self.project.pcb:
            self.skipped.append("Gerbers: no .kicad_pcb in project")
            return []
        out = self.output_dir / "gerbers"
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        ok = self._run_cli(["pcb", "export", "gerbers", "-o", f"{out}/", str(self.project.pcb)], "Gerbers")
        ok = self._run_cli(["pcb", "export", "drill", "-o", f"{out}/", str(self.project.pcb)], "Drill") and ok
        return sorted(p for p in out.iterdir() if p.is_file()) if ok or any(out.iterdir()) else []

    def export_schematic_pdf(self) -> Optional[Path]:
        if not self.project.sch:
            self.skipped.append("Schematic PDF: no .kicad_sch in project")
            return None
        out = self.output_dir / f"{self.project.name}_schematic.pdf"
        return out if self._run_cli(["sch", "export", "pdf", "-o", str(out), str(self.project.sch)], "Schematic PDF") else None

    # ------------------------------------------------------------------ always-available outputs
    def write_bom_csv(self) -> Optional[Path]:
        if not self.project.pcb:
            return None
        fps = read_board_footprints(self.project.pcb)
        out = self.output_dir / f"{self.project.name}_bom.csv"
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["References", "Value", "Footprint", "Qty"])
            w.writerows(group_bom([(fp["ref"], fp["value"], fp["footprint"]) for fp in fps]))
        return out

    def write_positions_csv(self) -> Optional[Path]:
        if not self.project.pcb:
            return None
        out = self.output_dir / f"{self.project.name}_positions.csv"
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Ref", "Val", "Package", "PosX", "PosY", "Rot", "Side"])
            for fp in sorted(read_board_footprints(self.project.pcb), key=lambda r: r["ref"]):
                w.writerow([fp["ref"], fp["value"], fp["footprint"].split(":")[-1], f"{fp['x']:.4f}", f"{-fp['y']:.4f}", f"{fp['rotation']:.1f}", fp["side"]])
        return out

    def write_report_pdf(self) -> Path:
        return DesignReportPDF(self.project.dir, self.output_dir / f"{self.project.name}_report.pdf").generate_pdf()

    def create_fab_package(self, gerbers: Optional[List[Path]] = None) -> Optional[Path]:
        """Zip of Gerbers + drill, BOM and positions. Returns None if there are no Gerbers to ship."""
        gerbers = gerbers if gerbers is not None else self.export_gerbers()
        if not gerbers:
            self.skipped.append("Fab package: no Gerbers were produced")
            return None
        bom, pos = self.write_bom_csv(), self.write_positions_csv()
        out = self.output_dir / f"{self.project.name}_fab.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for g in gerbers:
                zf.write(g, arcname=f"gerbers/{g.name}")
            for extra in (bom, pos):
                if extra:
                    zf.write(extra, arcname=f"assembly/{extra.name}")
        return out

    # ------------------------------------------------------------------ everything
    def build_all(self) -> Dict[str, Any]:
        self.skipped = []
        gerbers = self.export_gerbers()
        outputs: Dict[str, Any] = {
            "report": self.write_report_pdf(),
            "schematic_pdf": self.export_schematic_pdf(),
            "bom": self.write_bom_csv(),
            "positions": self.write_positions_csv(),
            "gerbers": gerbers,
            "fab_package": self.create_fab_package(gerbers),
        }
        outputs["index"] = self.write_index_html(outputs)
        outputs["skipped"] = list(self.skipped)
        return outputs

    def write_index_html(self, outputs: Dict[str, Any]) -> Path:
        """A single, dependency-free Dracula page linking every generated file."""
        def link(p: Optional[Path], label: str) -> str:
            if not p:
                return f'<li class="missing">{html.escape(label)} <span>not generated</span></li>'
            rel = Path(p).relative_to(self.output_dir).as_posix()
            return f'<li><a href="{html.escape(rel)}">{html.escape(label)}</a> <span>{html.escape(rel)}</span></li>'

        items = [
            link(outputs.get("report"), "Design report (PDF)"),
            link(outputs.get("schematic_pdf"), "Schematic (PDF)"),
            link(outputs.get("fab_package"), "Fabrication package (ZIP)"),
            link(outputs.get("bom"), "Bill of materials (CSV)"),
            link(outputs.get("positions"), "Placement / positions (CSV)"),
        ]
        gerbers = "".join(link(g, g.name) for g in outputs.get("gerbers") or [])
        skipped = "".join(f"<li>{html.escape(s)}</li>" for s in self.skipped)
        bom_rows = ""
        if self.project.pcb:
            for refs, value, fp, qty in group_bom([(f["ref"], f["value"], f["footprint"]) for f in read_board_footprints(self.project.pcb)]):
                bom_rows += f"<tr><td>{html.escape(refs)}</td><td>{html.escape(value)}</td><td>{html.escape(fp)}</td><td>{qty}</td></tr>"

        page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(self.project.name)} docs</title>
<style>
:root {{ --bg:{theme.BACKGROUND}; --surface:{theme.SURFACE}; --line:{theme.CURRENT_LINE}; --fg:{theme.FOREGROUND};
  --muted:{theme.COMMENT}; --accent:{theme.PURPLE}; --link:{theme.CYAN}; --warn:{theme.ORANGE}; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,sans-serif; }}
main {{ max-width:860px; margin:0 auto; padding:32px 16px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:15px; color:var(--accent); margin:28px 0 8px; font-weight:600; }}
p.meta {{ color:var(--muted); margin:0; }}
ul {{ list-style:none; padding:0; margin:0; }}
li {{ padding:8px 0; border-bottom:1px solid var(--line); display:flex; gap:12px; justify-content:space-between; flex-wrap:wrap; }}
li span {{ color:var(--muted); font-size:13px; }} li.missing {{ color:var(--muted); }}
a {{ color:var(--link); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
.skipped li {{ color:var(--warn); }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th,td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); }} th {{ color:var(--muted); font-weight:500; }}
.scroll {{ overflow-x:auto; }}
</style></head><body><main>
<h1>{html.escape(self.project.name)}</h1>
<p class="meta">Generated {time.strftime('%Y-%m-%d %H:%M')}</p>
<h2>Outputs</h2><ul>{''.join(items)}</ul>
{f'<h2>Gerbers &amp; drill</h2><ul>{gerbers}</ul>' if gerbers else ''}
{f'<h2>Skipped</h2><ul class="skipped">{skipped}</ul>' if skipped else ''}
<h2>Bill of materials</h2>
<div class="scroll"><table><thead><tr><th>References</th><th>Value</th><th>Footprint</th><th>Qty</th></tr></thead><tbody>{bom_rows}</tbody></table></div>
</main></body></html>
"""
        out = self.output_dir / "index.html"
        out.write_text(page, encoding="utf-8")
        return out
