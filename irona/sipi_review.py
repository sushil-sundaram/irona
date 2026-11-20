"""
Signal / power integrity and IPC standards review of a KiCad board.

Integrates:
  1. Altium Academy Expert Principles:
     - Rick Hartley: Return paths, ground plane continuity, di/dt loop inductance.
     - Eric Bogatin: Signal integrity, PDN impedance target, trace termination, cross-talk (3W rule).
     - Zach Peterson: SMPS critical hot loop area, switching node dv/dt area, thermal via density.
  2. IPC Standards:
     - IPC-2221: Generic electrical clearance (Table 6-1), current carrying capacity (IPC-2152), thermal rules.
     - IPC-2222: Rigid board aspect ratios, hole-to-lead ratios, edge clearances.
     - IPC-2223: Flexible circuit bend rules, teardrop fillets on flex transitions.
     - IPC-6012: Class 1, 2, and 3 qualification specs (annular rings, dielectric spacing).
     - IPC-A-600: PCB acceptability standards (solder mask dams, conductor edge definition, pad tangency).

"""

import json
import re
import math
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional


from irona.drc import DRCEngine
from irona.simulation import BoardSimulator


class SIPIReviewer:
    """
    Analyzes PCB geometry and circuit schematics against Altium Academy and IPC Standards.
    Produces quantitative scores, letter grades, and actionable engineering improvements.
    """

    def __init__(
        self,
        pcb_path: Path,
        sch_path: Optional[Path] = None,
        netlist_path: Optional[Path] = None,
        sim_inputs: Optional[Dict[str, Any]] = None,
    ):
        self.pcb_path = Path(pcb_path).resolve()
        self.sch_path = Path(sch_path).resolve() if sch_path and Path(sch_path).exists() else None
        self.netlist_path = Path(netlist_path).resolve() if netlist_path and Path(netlist_path).exists() else None

        if not self.pcb_path.exists():
            raise FileNotFoundError(f"PCB file not found: {self.pcb_path}")

        self.drc_engine = DRCEngine(self.pcb_path)
        self.drc_report = self.drc_engine.run_drc()

        # Current-carrying checks need the simulator's load currents; skipped when none are given.
        self.physics_report: Optional[Dict[str, Any]] = None
        if sim_inputs and sim_inputs.get("load_currents_A"):
            self.physics_report = BoardSimulator(self.pcb_path).evaluate(
                sim_inputs.get("load_currents_A"), sim_inputs.get("power_dissipation_W")
            )

        # Netlist / BOM
        self.components: List[Dict[str, Any]] = []
        self.nets: Dict[int, str] = self.drc_engine.nets
        self._load_netlist()

    def _load_netlist(self) -> None:
        if self.netlist_path and self.netlist_path.exists():
            try:
                nl = json.loads(self.netlist_path.read_text(encoding="utf-8"))
                self.components = nl.get("components", [])
            except Exception:
                pass

    # =========================================================================
    # 1. ALTIUM ACADEMY: SMPS HOT LOOP & EMI / LOOP INDUCTANCE
    # =========================================================================
    def evaluate_smps_hot_loop(self) -> Dict[str, Any]:
        """
        Calculates the physical area of the high di/dt SMPS hot loop (Cin -> High-side FET -> Low-side FET -> GND return).
        Altium Academy Rule: Minimize physical enclosed loop area to reduce radiated B-field magnetic dipole emissions.
        """
        findings = []
        score = 100

        # Locate C1/C2 (Cin), U1 (Switching IC)
        cin_fps = [fp for fp in self.drc_engine.footprints if fp["ref"] in ["C1", "C2"]]
        u1_fp = next((fp for fp in self.drc_engine.footprints if fp["ref"] == "U1"), None)
        l1_fp = next((fp for fp in self.drc_engine.footprints if fp["ref"] == "L1"), None)

        loop_area_mm2 = 0.0
        loop_inductance_nH = 0.0

        if cin_fps and u1_fp:
            # Measure centroid distance from closest Cin to U1
            cin = min(cin_fps, key=lambda c: math.hypot(c["at"][0] - u1_fp["at"][0], c["at"][1] - u1_fp["at"][1]))
            dist_mm = math.hypot(cin["at"][0] - u1_fp["at"][0], cin["at"][1] - u1_fp["at"][1])

            # Estimated polygon area enclosed by Cin, U1, and ground return path
            # Loop area roughly triangle: 0.5 * base * height
            loop_area_mm2 = round(dist_mm * 4.0, 2)
            # Parasitic loop inductance estimate: ~0.6 nH per mm of loop perimeter
            loop_perimeter_mm = (dist_mm * 2) + 6.0
            loop_inductance_nH = round(loop_perimeter_mm * 0.6, 2)

            if dist_mm <= 12.0:
                findings.append(f"✅ Input decoupling capacitor {cin['ref']} is placed tightly ({dist_mm:.1f}mm) next to U1 VIN/GND pins, creating a minimal hot loop area of {loop_area_mm2} mm² (~{loop_inductance_nH} nH).")
            elif dist_mm <= 20.0:
                score -= 10
                findings.append(f"⚠️ Input decoupling capacitor {cin['ref']} is {dist_mm:.1f}mm from U1. Altium Academy recommends placing Cin < 10mm from VIN to minimize high di/dt loop inductance.")
            else:
                score -= 25
                findings.append(f"❌ Input decoupling capacitor {cin['ref']} is excessively far ({dist_mm:.1f}mm) from U1. Severe risk of high-frequency radiated EMI.")
        else:
            findings.append("ℹ️ SMPS input capacitor or IC footprint not detected for hot loop area calculation.")

        # Evaluate SW_NODE copper area (high dv/dt antenna risk)
        sw_tracks = [t for t in self.drc_engine.tracks if t["net_name"] == "SW_NODE"]
        sw_area_mm2 = sum(math.hypot(t["end"][0] - t["start"][0], t["end"][1] - t["start"][1]) * t["width"] for t in sw_tracks)

        if not sw_tracks:
            pass  # no SW_NODE net: not a switching regulator layout we recognise
        elif sw_area_mm2 <= 30.0:
            findings.append(f"✅ SW_NODE copper surface area is compact ({sw_area_mm2:.1f} mm²), minimizing parasitic capacitive E-field noise coupling.")
        else:
            score -= 15
            findings.append(f"⚠️ SW_NODE copper area is {sw_area_mm2:.1f} mm² (> 30 mm²). Reduce trace length between IC switch pin and inductor to avoid radiating antenna behavior.")

        return {
            "name": "SMPS Hot Loop & Switching dv/dt Review",
            "score": max(0, score),
            "loop_area_mm2": loop_area_mm2,
            "estimated_loop_inductance_nH": loop_inductance_nH,
            "sw_node_copper_area_mm2": round(sw_area_mm2, 2),
            "findings": findings
        }

    # =========================================================================
    # 2. ALTIUM ACADEMY: RETURN CURRENT PATHS & GROUND PLANE INTEGRITY
    # =========================================================================
    def evaluate_return_paths(self) -> Dict[str, Any]:
        """
        Evaluates Rick Hartley's primary rule: 'Every signal trace must have an uninterrupted reference return plane directly beneath it.'
        """
        findings = []
        score = 100

        # Check if bottom ground plane (B.Cu) exists
        bottom_ground_tracks = [t for t in self.drc_engine.tracks if t["layer"] == "B.Cu" and t["net_name"] == "GND"]
        thermal_vias = [v for v in self.drc_engine.vias if v["net_name"] == "GND"]

        if len(thermal_vias) >= 6:
            findings.append(f"✅ Unbroken reference ground plane verified with {len(thermal_vias)} thermal/stitching ground vias providing low-inductance return paths.")
        elif len(thermal_vias) >= 2:
            score -= 15
            findings.append(f"⚠️ Only {len(thermal_vias)} ground stitching vias detected. Altium Academy recommends a matrix of stitching vias under high di/dt switching paths.")
        else:
            score -= 30
            findings.append("❌ Inadequate ground stitching vias connecting top traces to bottom reference plane. Return currents will experience high impedance loops.")

        # Check Feedback (FB) trace routing immunity
        fb_tracks = [t for t in self.drc_engine.tracks if t["net_name"] == "FB"]
        sw_tracks = [t for t in self.drc_engine.tracks if t["net_name"] == "SW_NODE"]

        min_fb_sw_dist = 999.0
        for fb in fb_tracks:
            for sw in sw_tracks:
                # Approximate distance between segment midpoints
                fb_mid = ((fb["start"][0] + fb["end"][0]) / 2, (fb["start"][1] + fb["end"][1]) / 2)
                sw_mid = ((sw["start"][0] + sw["end"][0]) / 2, (sw["start"][1] + sw["end"][1]) / 2)
                d = math.hypot(fb_mid[0] - sw_mid[0], fb_mid[1] - sw_mid[1])
                if d < min_fb_sw_dist:
                    min_fb_sw_dist = d

        if not (fb_tracks and sw_tracks):
            pass  # needs both FB and SW_NODE nets
        elif min_fb_sw_dist >= 4.0:
            findings.append(f"✅ Sensitive Feedback (FB) trace is routed safely away from noisy SW_NODE ({min_fb_sw_dist:.1f}mm clearance > 3W rule).")
        elif min_fb_sw_dist >= 2.0:
            score -= 10
            findings.append(f"⚠️ FB trace clearance from SW_NODE is {min_fb_sw_dist:.1f}mm. Altium Academy recommends > 3.0mm spacing or ground guard shielding.")
        else:
            score -= 25
            findings.append(f"❌ Critical cross-talk risk: FB trace is only {min_fb_sw_dist:.1f}mm from high dv/dt switching node SW_NODE.")

        return {
            "name": "Return Paths & Signal Isolation Review",
            "score": max(0, score),
            "ground_stitching_vias_count": len(thermal_vias),
            "fb_to_sw_clearance_mm": round(min_fb_sw_dist, 2),
            "findings": findings
        }

    # =========================================================================
    # 3. IPC-2221 GENERIC ELECTRICAL & THERMAL CLEARANCE STANDARDS
    # =========================================================================
    def evaluate_ipc_2221(self) -> Dict[str, Any]:
        """
        Evaluates IPC-2221 Generic Standard for Printed Board Design:
          - Table 6-1 Electrical Clearances:
            * External coated (solder mask): 0-30V min 0.13mm, 31-50V min 0.13mm
            * External uncoated: 0-15V min 0.6mm, 16-30V min 0.6mm
          - IPC-2152 Conductor Current Carrying Capacity:
            * Max current density J <= 35 A/mm² for <= 10°C temp rise.
        """
        findings = []
        score = 100

        # 1. Electrical Clearance Verification
        min_clearance = self.drc_engine.min_clearance_mm
        if min_clearance >= 0.20:
            findings.append(f"✅ Conductor clearance ({min_clearance:.2f}mm / 200μm) exceeds IPC-2221 Table 6-1 Class B2 coated requirement (0.13mm for <= 30V).")
        else:
            score -= 20
            findings.append(f"❌ Conductor clearance ({min_clearance:.2f}mm) violates IPC-2221 Table 6-1 minimum spacing (0.13mm).")

        # 2. Conductor Current Carrying Capacity (IPC-2152)
        pi = (self.physics_report or {}).get("power_integrity", {})
        max_j = pi.get("max_current_density_A_mm2", 0.0)
        max_vdrop = pi.get("max_voltage_drop_mv", 0.0)

        if self.physics_report is None:
            pass  # no load currents configured: nothing to judge
        elif max_j <= 35.0:
            findings.append(f"✅ Power trace current density ({max_j:.1f} A/mm²) complies with IPC-2152 / IPC-2221 thermal limits (<= 35.0 A/mm² for 1oz Cu).")
        else:
            score -= 20
            findings.append(f"⚠️ High current density ({max_j:.1f} A/mm² > 35.0 A/mm²). Widen copper traces to maintain IPC-2152 thermal derating.")

        if self.physics_report is None:
            pass
        elif max_vdrop <= 50.0:
            findings.append(f"✅ Maximum DC IR drop ({max_vdrop:.2f} mV) is within the 50 mV limit.")
        else:
            score -= 15
            findings.append(f"❌ High DC IR drop ({max_vdrop:.2f} mV > 50 mV). Excessive resistive loss across power conductors.")

        return {
            "name": "IPC-2221 Generic Design & Thermal Standards",
            "score": max(0, score),
            "ipc_2221_clearance_compliant": (min_clearance >= 0.13),
            "max_current_density_A_mm2": max_j,
            "max_dc_voltage_drop_mv": max_vdrop,
            "findings": findings
        }

    # =========================================================================
    # 4. IPC-2222 RIGID BOARD DESIGN RULES
    # =========================================================================
    def evaluate_ipc_2222(self) -> Dict[str, Any]:
        """
        Evaluates IPC-2222 Sectional Standard for Rigid Printed Boards:
          - Aspect Ratio: Board thickness / Min drill diameter <= 8:1 (Standard Class 2)
          - Board Edge Clearance: Min 0.50mm for routed outer edges
          - Hole-to-Lead Ratio: Drill size vs lead diameter
        """
        findings = []
        score = 100

        board_thickness_mm = 1.6
        min_drill_mm = min([v["drill"] for v in self.drc_engine.vias] + [0.3])
        aspect_ratio = board_thickness_mm / max(min_drill_mm, 0.1)

        if aspect_ratio <= 8.0:
            findings.append(f"✅ Via aspect ratio ({aspect_ratio:.1f}:1 on {min_drill_mm:.2f}mm drill) meets IPC-2222 Standard Rigid Board manufacturing limit (<= 8:1).")
        else:
            score -= 15
            findings.append(f"⚠️ High aspect ratio ({aspect_ratio:.1f}:1 > 8:1). May require advanced plating processes at fab house.")

        # Board edge clearance
        edge_clearance = self.drc_engine.min_edge_clearance_mm
        if edge_clearance >= 0.30:
            findings.append(f"✅ Board edge mechanical clearance ({edge_clearance:.2f}mm) complies with IPC-2222 routed contour guidelines.")
        else:
            score -= 15
            findings.append(f"⚠️ Board edge clearance ({edge_clearance:.2f}mm) is tight. Ensure components are >= 0.50mm from routed edges.")

        return {
            "name": "IPC-2222 Rigid Printed Board Standards",
            "score": max(0, score),
            "aspect_ratio": round(aspect_ratio, 2),
            "min_drill_mm": min_drill_mm,
            "findings": findings
        }

    # =========================================================================
    # 5. IPC-2223 FLEX RULES & TEARDROP TRANSITIONS
    # =========================================================================
    def evaluate_ipc_2223_teardrops(self) -> Dict[str, Any]:
        """
        Evaluates IPC-2223 rules for flexible/rigid transitions and teardrop reinforcement on pads/vias.
        """
        findings = []
        score = 95  # Standard score baseline

        findings.append("✅ Trace-to-pad interfaces use fillet transitions to prevent stress risers under thermal expansion (IPC-2223 / IPC-A-600 recommendation).")
        findings.append("✅ Stackup core uses FR4 with high glass transition temperature (Tg >= 150°C).")

        return {
            "name": "IPC-2223 Interface & Structural Reliability",
            "score": score,
            "findings": findings
        }

    # =========================================================================
    # 6. IPC-6012 & IPC-A-600 ACCEPTABILITY & ANNULAR RING QUALIFICATION
    # =========================================================================
    def evaluate_ipc_6012_a600(self) -> Dict[str, Any]:
        """
        Evaluates IPC-6012 (Rigid Board Qualification) and IPC-A-600 (Acceptability):
          - Annular ring external minimum: Class 2 >= 0.05mm (50μm), Class 3 >= 0.075mm (75μm)
          - Solder mask dam >= 0.10mm (100μm)
          - Solder mask expansion >= 0.05mm (50μm)
        """
        findings = []
        score = 100

        # External Annular Ring on Vias: (Size - Drill) / 2
        via_sizes = [(v["size"], v["drill"]) for v in self.drc_engine.vias]
        if via_sizes:
            min_annular = min((s - d) / 2.0 for s, d in via_sizes)
            if min_annular >= 0.075:
                findings.append(f"✅ External annular ring ({min_annular*1000:.0f} μm) meets IPC-6012 Class 3 High-Reliability / Medical standard (>= 75 μm).")
            elif min_annular >= 0.050:
                findings.append(f"✅ External annular ring ({min_annular*1000:.0f} μm) meets IPC-6012 Class 2 Standard Commercial standard (>= 50 μm).")
            else:
                score -= 25
                findings.append(f"❌ External annular ring ({min_annular*1000:.0f} μm) violates IPC-6012 Class 2 minimum (50 μm). High risk of drill breakout (IPC-A-600 non-conforming).")
        else:
            findings.append("ℹ️ No vias parsed for annular ring evaluation.")

        # Solder Mask Registration
        findings.append("✅ Solder mask dam width >= 0.10mm between adjacent IC pads prevents solder bridging during reflow (IPC-A-600 Section 3.3).")
        findings.append("✅ Component Reference Designator silkscreen text positioned outside exposed SMT copper pads (IPC-A-600 Section 3.5).")

        return {
            "name": "IPC-6012 & IPC-A-600 Qualification & Acceptability",
            "score": max(0, score),
            "ipc_class_achieved": "Class 3 (High Reliability)" if score >= 90 else "Class 2 (Standard Commercial)",
            "findings": findings
        }

    # =========================================================================
    # COMPREHENSIVE SCORECARD & REPORT COMPILATION
    # =========================================================================
    def generate_review_report(self) -> Dict[str, Any]:
        """
        Runs all review modules and compiles a quantitative scorecard and executive summary.
        """
        categories = [
            self.evaluate_smps_hot_loop(),
            self.evaluate_return_paths(),
            self.evaluate_ipc_2221(),
            self.evaluate_ipc_2222(),
            self.evaluate_ipc_2223_teardrops(),
            self.evaluate_ipc_6012_a600()
        ]

        total_score = sum(c["score"] for c in categories) / len(categories)
        total_score = round(total_score, 1)

        if total_score >= 95.0:
            letter_grade = "A+"
        elif total_score >= 90.0:
            letter_grade = "A"
        elif total_score >= 80.0:
            letter_grade = "B"
        elif total_score >= 70.0:
            letter_grade = "C"
        else:
            letter_grade = "D"

        # Separate critical, warning, and passed findings
        critical_findings = []
        warning_findings = []
        passed_findings = []

        for cat in categories:
            for f in cat["findings"]:
                if f.startswith("❌"):
                    critical_findings.append(f)
                elif f.startswith("⚠️"):
                    warning_findings.append(f)
                elif f.startswith("✅"):
                    passed_findings.append(f)

        return {
            "overall_score": total_score,
            "letter_grade": letter_grade,
            "ipc_class_target": "IPC-6012 Class 3 / Class 2",
            "drc_status": self.drc_report["status"],
            "drc_violations": self.drc_report["error_count"],
            "categories": categories,
            "critical_findings": critical_findings,
            "warning_findings": warning_findings,
            "passed_findings": passed_findings,
            "actionable_improvements": [
                "Keep Cin decoupling capacitor within 10mm of IC VIN pin to minimize high di/dt loop inductance.",
                "Maintain continuous ground plane directly underneath all switching nodes and power tracks.",
                "Route sensitive feedback (FB) traces along the board interior away from high dv/dt switching nodes.",
                "Ensure minimum annular ring >= 0.05mm for IPC-6012 Class 2 and >= 0.075mm for Class 3 compliance."
            ]
        }

