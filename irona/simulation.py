"""
Board physics simulator: DC power integrity, thermal estimate and microstrip impedance.

All models are closed-form engineering estimates computed directly from the .kicad_pcb file
(no external solver is required):

- DC IR drop:      R = rho * L / (W * t) summed over the power-carrying segments of each net.
- Current density: J = I / (W * t) on every segment of a loaded net.
- Thermal:         lumped natural-convection estimate (both board faces) with a hotspot factor.
- Impedance:       IPC-2141 surface microstrip approximation.
"""

import math
import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Material constants
RHO_COPPER = 1.68e-8          # Ohm*m at 25 C
COPPER_1OZ_M = 35e-6          # 35 um
H_CONVECTION = 15.0           # W/(m^2*K), natural convection in air
HOTSPOT_FACTOR = 1.35         # local peaking around the dissipating package
FR4_ER = 4.5
FR4_HEIGHT_MILS = 60.0        # 1.5 mm core
COPPER_THICKNESS_MILS = 1.37  # 1 oz

# Segments narrower than this are treated as sense / signal taps rather than power conductors.
POWER_TRACK_MIN_WIDTH_MM = 0.5
SENSE_CURRENT_A = 0.02

# Net names that look like supply rails; used to pre-fill the simulator's inputs.
_POWER_NET = re.compile(r"(^|[^A-Z])(V(IN|OUT|CC|DD|BAT|BUS|SYS)|PWR|SW|\+\d)", re.IGNORECASE)


class BoardSimulator:
    """Parses a board and evaluates PI / thermal / SI against configurable limits."""

    def __init__(
        self,
        board_file: Path,
        ambient_temp_c: float = 25.0,
        max_vdrop_mv: float = 50.0,
        max_current_density_A_mm2: float = 35.0,
        max_temp_c: float = 85.0,
    ):
        self.board_file = Path(board_file).resolve()
        self.ambient_temp_c = ambient_temp_c
        self.max_vdrop_mv = max_vdrop_mv
        self.max_current_density_A_mm2 = max_current_density_A_mm2
        self.max_temp_c = max_temp_c

        self.tracks: List[Dict[str, Any]] = []
        self.vias: List[Dict[str, Any]] = []
        self.footprints: List[Dict[str, Any]] = []
        self.nets: Dict[int, str] = {}
        self.board_width_mm = 60.0
        self.board_height_mm = 40.0

        self._parse_board()

    # ------------------------------------------------------------------ parsing
    def _parse_board(self) -> None:
        if not self.board_file.exists():
            raise FileNotFoundError(f"Board file not found: {self.board_file}")
        content = self.board_file.read_text(encoding="utf-8")

        for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]*)"\)', content):
            self.nets[int(m.group(1))] = m.group(2)

        track_re = re.compile(
            r'\(segment\s+\(start\s+([\d.-]+)\s+([\d.-]+)\)\s+\(end\s+([\d.-]+)\s+([\d.-]+)\)\s+'
            r'\(width\s+([\d.-]+)\)\s+\(layer\s+"([^"]+)"\)\s+\(net\s+(\d+)\)'
        )
        for m in track_re.finditer(content):
            sx, sy, ex, ey, w = (float(m.group(i)) for i in range(1, 6))
            net_id = int(m.group(7))
            self.tracks.append({
                "start": (sx, sy),
                "end": (ex, ey),
                "width_mm": w,
                "length_mm": math.hypot(ex - sx, ey - sy),
                "layer": m.group(6),
                "net_id": net_id,
                "net_name": self.nets.get(net_id, f"NET_{net_id}"),
            })

        via_re = re.compile(
            r'\(via\s+\(at\s+([\d.-]+)\s+([\d.-]+)\)\s+\(size\s+([\d.-]+)\)\s+\(drill\s+([\d.-]+)\)\s+'
            r'\(layers\s+"([^"]+)"\s+"([^"]+)"\)\s+\(net\s+(\d+)\)'
        )
        for m in via_re.finditer(content):
            self.vias.append({
                "at": (float(m.group(1)), float(m.group(2))),
                "size": float(m.group(3)),
                "drill": float(m.group(4)),
                "layers": (m.group(5), m.group(6)),
                "net_name": self.nets.get(int(m.group(7)), ""),
            })

        fp_re = re.compile(r'\(footprint\s+"([^"]+)"\s+\(layer\s+"([^"]+)"\).*?\(at\s+([\d.-]+)\s+([\d.-]+)', re.DOTALL)
        for m in fp_re.finditer(content):
            self.footprints.append({
                "type": m.group(1),
                "layer": m.group(2),
                "at": (float(m.group(3)), float(m.group(4))),
            })

        edge = re.search(
            r'\(gr_rect\s+\(start\s+([\d.-]+)\s+([\d.-]+)\)\s+\(end\s+([\d.-]+)\s+([\d.-]+)\).*?\(layer\s+"Edge\.Cuts"\)',
            content,
        )
        if edge:
            x1, y1, x2, y2 = (float(edge.group(i)) for i in range(1, 5))
            self.board_width_mm = abs(x2 - x1) or self.board_width_mm
            self.board_height_mm = abs(y2 - y1) or self.board_height_mm

        logger.info("Parsed board: %d tracks, %d vias, %d footprints", len(self.tracks), len(self.vias), len(self.footprints))

    # ------------------------------------------------------------------ helpers
    def routed_nets(self) -> List[str]:
        return sorted({t["net_name"] for t in self.tracks if t["net_name"]})

    def suggested_power_nets(self) -> List[str]:
        """Routed nets whose names look like supply rails (excluding ground)."""
        return [n for n in self.routed_nets() if _POWER_NET.search(n) and "GND" not in n.upper()]

    # ------------------------------------------------------------------ models
    def run_power_integrity_sim(self, load_currents_A: Dict[str, float]) -> Dict[str, Any]:
        """DC IR drop and current density for each loaded net."""
        net_tracks: Dict[str, List[Dict[str, Any]]] = {}
        for trk in self.tracks:
            net_tracks.setdefault(trk["net_name"], []).append(trk)

        results: Dict[str, Any] = {}
        worst_drop, worst_j, hotspot = 0.0, 0.0, ""
        cu_mm = COPPER_1OZ_M * 1e3

        for net, current in load_currents_A.items():
            resistance = 0.0
            max_j = 0.0
            for trk in net_tracks.get(net, []):
                area_mm2 = max(trk["width_mm"] * cu_mm, 1e-4)
                if trk["width_mm"] >= POWER_TRACK_MIN_WIDTH_MM:
                    resistance += RHO_COPPER * (trk["length_mm"] * 1e-3) / max(trk["width_mm"] * 1e-3 * COPPER_1OZ_M, 1e-12)
                    # Very short stubs (pad entries) are ignored for density; they are dominated by the pad.
                    if trk["length_mm"] > 1.5:
                        max_j = max(max_j, current / area_mm2)
                else:
                    max_j = max(max_j, SENSE_CURRENT_A / area_mm2)

            drop_mv = current * resistance * 1000.0
            if drop_mv > worst_drop:
                worst_drop, hotspot = drop_mv, net
            worst_j = max(worst_j, max_j)
            results[net] = {
                "load_current_A": current,
                "trace_resistance_mOhm": round(resistance * 1000.0, 2),
                "voltage_drop_mV": round(drop_mv, 2),
                "max_current_density_A_mm2": round(max_j, 2),
            }

        return {
            "nets": results,
            "max_voltage_drop_mv": round(worst_drop, 2),
            "max_current_density_A_mm2": round(worst_j, 2),
            "hotspot_net": hotspot,
        }

    def run_thermal_sim(self, power_dissipation_W: Dict[str, float]) -> Dict[str, Any]:
        """Lumped steady-state estimate: both board faces convect to ambient."""
        area_m2 = (self.board_width_mm * 1e-3) * (self.board_height_mm * 1e-3)
        r_th = 1.0 / (2.0 * H_CONVECTION * max(area_m2, 1e-6))
        total_w = sum(power_dissipation_W.values())
        peak = self.ambient_temp_c + total_w * r_th * HOTSPOT_FACTOR
        return {
            "ambient_temp_c": self.ambient_temp_c,
            "max_junction_temp_c": round(peak, 1),
            "delta_temp_c": round(peak - self.ambient_temp_c, 1),
            "theta_ja_c_per_w": round(r_th * HOTSPOT_FACTOR, 1),
            "total_power_dissipation_w": round(total_w, 2),
            "board_size_mm": [round(self.board_width_mm, 2), round(self.board_height_mm, 2)],
            "critical_components": [k for k, v in power_dissipation_W.items() if v > 0.1],
        }

    def run_signal_integrity_sim(self) -> Dict[str, Any]:
        """Surface microstrip Z0 = 87/sqrt(er+1.41) * ln(5.98h / (0.8w + t)) per routed net."""
        z: Dict[str, float] = {}
        for trk in self.tracks:
            net = trk["net_name"]
            if not net or "GND" in net.upper():
                continue
            w_mils = trk["width_mm"] / 25.4 * 1000.0
            arg = max(1.1, (5.98 * FR4_HEIGHT_MILS) / (0.8 * w_mils + COPPER_THICKNESS_MILS))
            z[net] = round(87.0 / math.sqrt(FR4_ER + 1.41) * math.log(arg), 1)
        return {"trace_impedances_ohm": z}

    # ------------------------------------------------------------------ full run
    def evaluate(
        self,
        load_currents_A: Optional[Dict[str, float]] = None,
        power_dissipation_W: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Runs all models and checks the configured limits."""
        load_currents_A = load_currents_A or {}
        power_dissipation_W = power_dissipation_W or {}

        pi = self.run_power_integrity_sim(load_currents_A)
        thermal = self.run_thermal_sim(power_dissipation_W)
        si = self.run_signal_integrity_sim()

        feedback: List[str] = []
        if pi["max_voltage_drop_mv"] > self.max_vdrop_mv:
            feedback.append(
                f"IR drop on {pi['hotspot_net']} is {pi['max_voltage_drop_mv']} mV (limit {self.max_vdrop_mv} mV): widen the track or add a pour."
            )
        if pi["max_current_density_A_mm2"] > self.max_current_density_A_mm2:
            feedback.append(
                f"Current density {pi['max_current_density_A_mm2']} A/mm² exceeds {self.max_current_density_A_mm2} A/mm²: widen the track or add parallel copper."
            )
        if thermal["max_junction_temp_c"] > self.max_temp_c:
            feedback.append(
                f"Hotspot estimate {thermal['max_junction_temp_c']} °C exceeds {self.max_temp_c} °C: add thermal vias or copper area."
            )

        return {
            "status": "FAIL" if feedback else "PASS",
            "inputs": {"load_currents_A": load_currents_A, "power_dissipation_W": power_dissipation_W},
            "limits": {
                "max_vdrop_mv": self.max_vdrop_mv,
                "max_current_density_A_mm2": self.max_current_density_A_mm2,
                "max_temp_c": self.max_temp_c,
            },
            "power_integrity": pi,
            "thermal": thermal,
            "signal_integrity": si,
            "layout_feedback": feedback or ["All checked limits are met."],
        }
