"""Locates the files that make up a KiCad project and where Irona writes its output."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

OUTPUT_DIRNAME = "irona-out"
SIM_INPUTS_FILENAME = "irona-sim.json"


class Project:
    """A KiCad project directory: schematic, board, optional netlist JSON and Irona output folder."""

    def __init__(self, project_dir: Path):
        self.dir = Path(project_dir).resolve()
        if not self.dir.is_dir():
            raise FileNotFoundError(f"Project directory not found: {self.dir}")
        self.name = self.dir.name
        self.sch = self._find(".kicad_sch")
        self.pcb = self._find(".kicad_pcb")
        self.netlist = self._find("_netlist.json")

    @classmethod
    def from_board(cls, board_file: Path) -> "Project":
        return cls(Path(board_file).resolve().parent)

    def _find(self, suffix: str) -> Optional[Path]:
        """Prefers <dirname><suffix>, otherwise the first match in the folder."""
        preferred = self.dir / f"{self.name}{suffix}"
        if preferred.exists():
            return preferred
        matches = sorted(self.dir.glob(f"*{suffix}"))
        return matches[0] if matches else None

    @property
    def output_dir(self) -> Path:
        out = self.dir / OUTPUT_DIRNAME
        out.mkdir(parents=True, exist_ok=True)
        return out

    # Simulator inputs (net currents / component dissipation) are saved per project so the
    # report and docs can reuse what the user last entered in the Simulator plugin.
    def load_sim_inputs(self) -> Optional[Dict[str, Any]]:
        f = self.dir / SIM_INPUTS_FILENAME
        if not f.exists():
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save_sim_inputs(self, inputs: Dict[str, Any]) -> Path:
        f = self.dir / SIM_INPUTS_FILENAME
        f.write_text(json.dumps(inputs, indent=2), encoding="utf-8")
        return f
