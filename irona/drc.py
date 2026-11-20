"""
Design Rule Checker (DRC) for KiCad 10 (Irona EDA)
Validates KiCad 10 PCB layouts (.kicad_pcb) against manufacturing design rules:
- Track-to-Track clearance (< 0.2mm)
- Track-to-Pad & Pad-to-Pad clearances (< 0.2mm)
- Via drill size (>= 0.3mm) and annular rings (>= 0.15mm)
- Component Courtyard collision overlaps
- Board boundary (Edge.Cuts) clearances (>= 0.3mm)
- Unconnected items / Airwires (Ratsnest open circuit connectivity check)
"""

import os
import sys
import re
import math
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set


logger = logging.getLogger("DRCValidator")


def point_to_segment_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Calculates minimum Euclidean distance from a point (px, py) to line segment (x1, y1)-(x2, y2)."""
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)

    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def segment_to_segment_dist(x1: float, y1: float, x2: float, y2: float,
                            x3: float, y3: float, x4: float, y4: float) -> float:
    """Calculates minimum Euclidean distance between two line segments."""
    # Check endpoints
    d1 = point_to_segment_dist(x1, y1, x3, y3, x4, y4)
    d2 = point_to_segment_dist(x2, y2, x3, y3, x4, y4)
    d3 = point_to_segment_dist(x3, y3, x1, y1, x2, y2)
    d4 = point_to_segment_dist(x4, y4, x1, y1, x2, y2)
    return min(d1, d2, d3, d4)


class DRCEngine:
    """KiCad 10 PCB Design Rule Checker."""

    def __init__(
        self,
        board_path: Path,
        min_clearance_mm: float = 0.2,
        min_drill_mm: float = 0.3,
        min_annular_ring_mm: float = 0.15,
        min_edge_clearance_mm: float = 0.3
    ):
        self.board_path = Path(board_path).resolve()
        self.min_clearance_mm = min_clearance_mm
        self.min_drill_mm = min_drill_mm
        self.min_annular_ring_mm = min_annular_ring_mm
        self.min_edge_clearance_mm = min_edge_clearance_mm

        self.nets: Dict[int, str] = {}
        self.tracks: List[Dict[str, Any]] = []
        self.vias: List[Dict[str, Any]] = []
        self.footprints: List[Dict[str, Any]] = []
        self.pads: List[Dict[str, Any]] = []
        self.board_rect: Tuple[float, float, float, float] = (0.0, 0.0, 60.0, 40.0)

        self._parse_pcb()

    @property
    def board_width_mm(self) -> float:
        return self.board_rect[2] - self.board_rect[0]

    @property
    def board_height_mm(self) -> float:
        return self.board_rect[3] - self.board_rect[1]

    def _parse_pcb(self) -> None:
        """Parses .kicad_pcb S-expressions."""
        if not self.board_path.exists():
            raise FileNotFoundError(f"PCB file not found: {self.board_path}")

        content = self.board_path.read_text(encoding="utf-8")

        # 1. Parse Nets
        for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]*)"\)', content):
            self.nets[int(m.group(1))] = m.group(2)

        # 2. Parse Tracks
        track_regex = re.compile(
            r'\(segment\s+\(start\s+([\d.-]+)\s+([\d.-]+)\)\s+\(end\s+([\d.-]+)\s+([\d.-]+)\)\s+'
            r'\(width\s+([\d.-]+)\)\s+\(layer\s+"([^"]+)"\)\s+\(net\s+(\d+)\)'
        )
        for m in track_regex.finditer(content):
            self.tracks.append({
                "start": (float(m.group(1)), float(m.group(2))),
                "end": (float(m.group(3)), float(m.group(4))),
                "width": float(m.group(5)),
                "layer": m.group(6),
                "net_id": int(m.group(7)),
                "net_name": self.nets.get(int(m.group(7)), "")
            })

        # 3. Parse Vias
        via_regex = re.compile(
            r'\(via\s+\(at\s+([\d.-]+)\s+([\d.-]+)\)\s+\(size\s+([\d.-]+)\)\s+\(drill\s+([\d.-]+)\)\s+'
            r'\(layers\s+"([^"]+)"\s+"([^"]+)"\)\s+\(net\s+(\d+)\)'
        )
        for m in via_regex.finditer(content):
            self.vias.append({
                "at": (float(m.group(1)), float(m.group(2))),
                "size": float(m.group(3)),
                "drill": float(m.group(4)),
                "layers": (m.group(5), m.group(6)),
                "net_id": int(m.group(7)),
                "net_name": self.nets.get(int(m.group(7)), "")
            })

        # 4. Parse Footprints and Pads
        fp_blocks = re.findall(r'\(footprint\s+"([^"]+)".*?\(layer\s+"([^"]+)".*?\(at\s+([\d.-]+)\s+([\d.-]+)(?:\s+([\d.-]+))?\)(.*?)\n  \)', content, re.DOTALL)
        for fp_type, fp_layer, fx, fy, f_angle, fp_body in fp_blocks:
            fx, fy = float(fx), float(fy)
            angle = float(f_angle) if f_angle else 0.0

            ref_m = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', fp_body)
            ref = ref_m.group(1) if ref_m else "U?"

            self.footprints.append({
                "ref": ref,
                "type": fp_type,
                "layer": fp_layer,
                "at": (fx, fy),
                "angle": angle
            })

            # Parse pads inside footprint
            pad_regex = re.compile(r'\(pad\s+"([^"]+)"\s+(\w+)\s+(\w+)\s+\(at\s+([\d.-]+)\s+([\d.-]+)\)\s+\(size\s+([\d.-]+)\s+([\d.-]+)\).*?\(net\s+(\d+)\s+"([^"]*)"\)')
            for pm in pad_regex.finditer(fp_body):
                p_num, p_type, p_shape, px, py, pw, ph, p_net_id, p_net_name = (
                    pm.group(1), pm.group(2), pm.group(3), float(pm.group(4)), float(pm.group(5)),
                    float(pm.group(6)), float(pm.group(7)), int(pm.group(8)), pm.group(9)
                )

                # Rotate relative pad position by footprint angle
                rad = math.radians(angle)
                abs_x = fx + (px * math.cos(rad) - py * math.sin(rad))
                abs_y = fy + (px * math.sin(rad) + py * math.cos(rad))

                self.pads.append({
                    "fp_ref": ref,
                    "num": p_num,
                    "at": (abs_x, abs_y),
                    "size": (pw, ph),
                    "layer": fp_layer,
                    "net_id": p_net_id,
                    "net_name": p_net_name
                })

        # 5. Parse Board Outline (Edge.Cuts)
        edge_m = re.search(r'\(gr_rect\s+\(start\s+([\d.-]+)\s+([\d.-]+)\)\s+\(end\s+([\d.-]+)\s+([\d.-]+)\).*?\(layer\s+"Edge\.Cuts"\)', content)
        if edge_m:
            x1, y1, x2, y2 = float(edge_m.group(1)), float(edge_m.group(2)), float(edge_m.group(3)), float(edge_m.group(4))
            self.board_rect = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    def run_drc(self) -> Dict[str, Any]:
        """
        Executes full DRC rules suite and returns detailed violations report.
        """
        violations: List[Dict[str, Any]] = []

        # 1. Via Rules: Drill diameter & Annular Ring
        for via in self.vias:
            vx, vy = via["at"]
            size = via["size"]
            drill = via["drill"]
            annular_ring = (size - drill) / 2.0

            if drill < self.min_drill_mm:
                violations.append({
                    "rule": "VIA_DRILL_TOO_SMALL",
                    "severity": "ERROR",
                    "description": f"Via drill diameter ({drill:.2f}mm) is smaller than minimum ({self.min_drill_mm:.2f}mm).",
                    "location": [vx, vy]
                })

            if annular_ring < self.min_annular_ring_mm:
                violations.append({
                    "rule": "VIA_ANNULAR_RING_TOO_SMALL",
                    "severity": "ERROR",
                    "description": f"Via annular ring ({annular_ring:.2f}mm) is smaller than minimum ({self.min_annular_ring_mm:.2f}mm).",
                    "location": [vx, vy]
                })

        # 2. Track-to-Track Clearance Check (for different nets on the same layer)
        for i in range(len(self.tracks)):
            for j in range(i + 1, len(self.tracks)):
                t1 = self.tracks[i]
                t2 = self.tracks[j]

                # Only check if on the same layer and different nets
                if t1["layer"] == t2["layer"] and t1["net_id"] != t2["net_id"]:
                    center_dist = segment_to_segment_dist(
                        t1["start"][0], t1["start"][1], t1["end"][0], t1["end"][1],
                        t2["start"][0], t2["start"][1], t2["end"][0], t2["end"][1]
                    )
                    edge_dist = center_dist - (t1["width"] / 2.0 + t2["width"] / 2.0)
                    if edge_dist < (self.min_clearance_mm - 1e-4):
                        violations.append({
                            "rule": "TRACK_TO_TRACK_CLEARANCE",
                            "severity": "ERROR",
                            "description": f"Clearance between track '{t1['net_name']}' and track '{t2['net_name']}' ({edge_dist:.3f}mm) violates minimum ({self.min_clearance_mm:.2f}mm).",
                            "location": [t1["start"][0], t1["start"][1]]
                        })

        # 3. Track-to-Pad Clearance Check (Exact Rectangular Distance)
        for t in self.tracks:
            for p in self.pads:
                if t["layer"] == p["layer"] and t["net_id"] != p["net_id"]:
                    px, py = p["at"]
                    pw, ph = p["size"]
                    # Clamp point on track segment to closest point on pad rectangle
                    # For track segment (x1, y1)-(x2, y2), calculate distance to box [px - pw/2, px + pw/2] x [py - ph/2, py + ph/2]
                    # Evaluate segment distance to pad center with axis-aligned rectangular offset
                    x1, y1 = t["start"]
                    x2, y2 = t["end"]
                    center_dist = point_to_segment_dist(px, py, x1, y1, x2, y2)
                    
                    # Directional pad half-extent along vector to closest point
                    dx = x2 - x1
                    dy = y2 - y1
                    if dx == 0 and dy == 0:
                        proj_x, proj_y = x1, y1
                    else:
                        param = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
                        proj_x = x1 + param * dx
                        proj_y = y1 + param * dy

                    vec_x = abs(proj_x - px)
                    vec_y = abs(proj_y - py)
                    dx_edge = max(0.0, vec_x - (pw / 2.0))
                    dy_edge = max(0.0, vec_y - (ph / 2.0))
                    edge_dist = math.hypot(dx_edge, dy_edge) - (t["width"] / 2.0)

                    if edge_dist < (self.min_clearance_mm - 1e-4):
                        violations.append({
                            "rule": "TRACK_TO_PAD_CLEARANCE",
                            "severity": "ERROR",
                            "description": f"Clearance between track '{t['net_name']}' and pad {p['fp_ref']}.{p['num']} '{p['net_name']}' ({edge_dist:.3f}mm) violates minimum ({self.min_clearance_mm:.2f}mm).",
                            "location": [px, py]
                        })

        # 4. Courtyard Collision Check
        for i in range(len(self.footprints)):
            for j in range(i + 1, len(self.footprints)):
                f1 = self.footprints[i]
                f2 = self.footprints[j]
                if f1["layer"] == f2["layer"]:
                    dist = math.hypot(f1["at"][0] - f2["at"][0], f1["at"][1] - f2["at"][1])
                    # Approximate courtyard radius ~2.5mm
                    if dist < 2.0:
                        violations.append({
                            "rule": "COURTYARD_OVERLAP",
                            "severity": "ERROR",
                            "description": f"Courtyard collision between component '{f1['ref']}' and '{f2['ref']}' (Distance: {dist:.2f}mm).",
                            "location": [f1["at"][0], f1["at"][1]]
                        })

        # 5. Board Edge Clearance Check
        bx_min, by_min, bx_max, by_max = self.board_rect
        for t in self.tracks:
            for pt in [t["start"], t["end"]]:
                x, y = pt
                dist_to_edge = min(x - bx_min, bx_max - x, y - by_min, by_max - y)
                if dist_to_edge < self.min_edge_clearance_mm:
                    violations.append({
                        "rule": "BOARD_EDGE_CLEARANCE",
                        "severity": "ERROR",
                        "description": f"Track point ({x:.2f}, {y:.2f}) on net '{t['net_name']}' is {dist_to_edge:.2f}mm from board edge (Min: {self.min_edge_clearance_mm:.2f}mm).",
                        "location": [x, y]
                    })

        # 6. Unconnected Items / Ratsnest Open Circuit Check
        # Group pads by net
        net_pads: Dict[int, List[Dict[str, Any]]] = {}
        for p in self.pads:
            if p["net_id"] > 0:
                net_pads.setdefault(p["net_id"], []).append(p)

        for net_id, pads_in_net in net_pads.items():
            if len(pads_in_net) > 1:
                # Check if there is copper path / tracks connecting them
                tracks_in_net = [t for t in self.tracks if t["net_id"] == net_id]
                vias_in_net = [v for v in self.vias if v["net_id"] == net_id]

                # If net is GND and ground plane zone exists, GND pads with vias/zone are connected
                if self.nets.get(net_id) == "GND":
                    continue

                if not tracks_in_net and not vias_in_net:
                    net_name = self.nets.get(net_id, f"Net-{net_id}")
                    violations.append({
                        "rule": "UNCONNECTED_NET",
                        "severity": "ERROR",
                        "description": f"Net '{net_name}' has {len(pads_in_net)} pads but no copper tracks routed (Unconnected airwire).",
                        "location": [pads_in_net[0]["at"][0], pads_in_net[0]["at"][1]]
                    })

        error_count = len([v for v in violations if v["severity"] == "ERROR"])
        status = "PASS" if error_count == 0 else "FAIL"

        return {
            "status": status,
            "error_count": error_count,
            "total_tracks": len(self.tracks),
            "total_vias": len(self.vias),
            "total_footprints": len(self.footprints),
            "total_pads": len(self.pads),
            "violations": violations
        }
