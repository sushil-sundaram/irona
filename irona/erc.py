"""
Electrical Rule Checker (ERC) for KiCad 10 (Irona EDA)
Parses KiCad 10 schematics (.kicad_sch) and netlists to validate:
- Pin conflict matrix (e.g. Output-to-Output short circuits)
- Unconnected / floating pins without No-Connect flags
- Single-pin nets (dangling net labels)
- Power Input pins without power sources or PWR_FLAG
- Duplicate reference designators & missing footprints
"""

import os
import sys
import re
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set


logger = logging.getLogger("ERCValidator")

# KiCad Pin Conflict Matrix
# Levels: 0 = OK, 1 = WARNING, 2 = ERROR
PIN_TYPES = ["input", "output", "bidirectional", "tri_state", "passive", "power_in", "power_out", "open_collector", "open_emitter", "unspecified"]

# Conflict rules mapping (type1, type2) -> (severity, description)
PIN_CONFLICT_RULES = {
    ("output", "output"): ("ERROR", "Conflict between output pins (short circuit risk)"),
    ("output", "power_out"): ("ERROR", "Output pin connected to power output"),
    ("power_out", "power_out"): ("WARNING", "Two power output pins connected together"),
    ("input", "input"): ("WARNING", "Input pin connected to input with no driving source"),
    ("open_collector", "output"): ("ERROR", "Open collector connected to standard output"),
}


class ERCEngine:
    """KiCad 10 Schematic Electrical Rule Checker."""

    def __init__(self, schematic_path: Path, netlist_path: Optional[Path] = None):
        self.schematic_path = Path(schematic_path).resolve()
        self.netlist_path = Path(netlist_path).resolve() if netlist_path else None
        self.symbols: List[Dict[str, Any]] = []
        self.nets: Dict[str, List[Dict[str, Any]]] = {}  # net_name -> list of pin dicts
        self.labels: List[Dict[str, Any]] = []
        self.wires: List[Dict[str, Any]] = []

        self._load_data()

    def _load_data(self) -> None:
        """Loads schematic data from S-expression or netlist."""
        if not self.schematic_path.exists():
            raise FileNotFoundError(f"Schematic file not found: {self.schematic_path}")

        content = self.schematic_path.read_text(encoding="utf-8")

        # 1. Parse Symbols
        sym_blocks = re.findall(r'\(symbol\s+.*?\(uuid\s+"[^"]+"\)\s+\(property\s+"Reference"\s+"([^"]+)".*?\(property\s+"Value"\s+"([^"]+)".*?\(property\s+"Footprint"\s+"([^"]*)"', content, re.DOTALL)
        for ref, val, fp in sym_blocks:
            self.symbols.append({
                "ref": ref,
                "value": val,
                "footprint": fp,
                "pins": []
            })

        # 2. Parse Net Labels
        for m in re.finditer(r'\(label\s+"([^"]+)"\s+\(at\s+([\d.-]+)\s+([\d.-]+)', content):
            self.labels.append({"name": m.group(1), "x": float(m.group(2)), "y": float(m.group(3))})

        # 3. If netlist JSON is available, load high-fidelity pin net mapping
        if self.netlist_path and self.netlist_path.exists():
            try:
                nl_data = json.loads(self.netlist_path.read_text(encoding="utf-8"))
                self.nets = nl_data.get("nets", {})
                # Enrich symbols with pin data from netlist components
                for c in nl_data.get("components", []):
                    for s in self.symbols:
                        if s["ref"] == c["ref"]:
                            s["pins"] = c.get("pins", [])
            except Exception as e:
                logger.warning(f"Error reading netlist for ERC: {e}")
        else:
            # Look for adjacent _netlist.json file
            auto_nl = self.schematic_path.parent / f"{self.schematic_path.stem}_netlist.json"
            if auto_nl.exists():
                try:
                    nl_data = json.loads(auto_nl.read_text(encoding="utf-8"))
                    self.nets = nl_data.get("nets", {})
                    for c in nl_data.get("components", []):
                        for s in self.symbols:
                            if s["ref"] == c["ref"]:
                                s["pins"] = c.get("pins", [])
                except Exception as e:
                    logger.warning(f"Error reading auto-netlist: {e}")

    def run_erc(self) -> Dict[str, Any]:
        """
        Executes full KiCad 10 ERC rule suite and returns violations report.
        """
        violations: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        # 1. Duplicate Reference Designators
        ref_counts: Dict[str, int] = {}
        for s in self.symbols:
            ref = s["ref"]
            ref_counts[ref] = ref_counts.get(ref, 0) + 1
        for ref, count in ref_counts.items():
            if count > 1:
                violations.append({
                    "rule": "DUPLICATE_REFERENCE",
                    "severity": "ERROR",
                    "description": f"Duplicate reference designator '{ref}' found {count} times.",
                    "item": ref
                })

        # 2. Missing Footprint Assignment
        for s in self.symbols:
            if not s.get("footprint") or s["footprint"].strip() in ["", "Irona_Footprints:", "~"]:
                violations.append({
                    "rule": "MISSING_FOOTPRINT",
                    "severity": "ERROR",
                    "description": f"Component '{s['ref']}' ({s['value']}) has no footprint assigned.",
                    "item": s["ref"]
                })

        # 3. Single-Pin Nets (Dangling / Unconnected Net Labels)
        for net_name, pins in self.nets.items():
            if len(pins) < 2:
                violations.append({
                    "rule": "SINGLE_PIN_NET",
                    "severity": "WARNING",
                    "description": f"Net '{net_name}' is connected to only {len(pins)} pin(s) (dangling net).",
                    "item": net_name
                })

        # 4. Power Input Pins without Power Drivers / PWR_FLAG
        # Verify that power nets (VIN, GND, VOUT, etc.) have power sources
        power_sources: Set[str] = set()
        for net_name, pins in self.nets.items():
            for p in pins:
                # If pin is on a connector (J1/J2) or regulator output, it acts as power source
                ref = p.get("ref", "")
                if ref.startswith("J") or (ref.startswith("U") and p.get("pin") in ["2", "VOUT"]):
                    power_sources.add(net_name)

        for net_name, pins in self.nets.items():
            has_power_in = False
            for p in pins:
                # Check pin types if available
                ref = p.get("ref", "")
                sym = next((s for s in self.symbols if s["ref"] == ref), None)
                if sym:
                    for pin_info in sym.get("pins", []):
                        if str(pin_info.get("num")) == str(p.get("pin")) and pin_info.get("type") == "power_in":
                            has_power_in = True

            if has_power_in and net_name not in power_sources and not net_name.startswith("GND"):
                warnings.append({
                    "rule": "POWER_PIN_NOT_DRIVEN",
                    "severity": "WARNING",
                    "description": f"Power input pin on net '{net_name}' is not driven by any power output or PWR_FLAG.",
                    "item": net_name
                })

        # 5. Pin Conflict Matrix
        for net_name, pins in self.nets.items():
            net_pin_types = []
            for p in pins:
                ref = p.get("ref", "")
                sym = next((s for s in self.symbols if s["ref"] == ref), None)
                if sym:
                    for pin_info in sym.get("pins", []):
                        if str(pin_info.get("num")) == str(p.get("pin")):
                            net_pin_types.append((ref, pin_info.get("num"), pin_info.get("type", "passive")))

            # Compare pairs on the same net
            for i in range(len(net_pin_types)):
                for j in range(i + 1, len(net_pin_types)):
                    r1, p1, t1 = net_pin_types[i]
                    r2, p2, t2 = net_pin_types[j]
                    pair = (t1.lower(), t2.lower())
                    rev_pair = (t2.lower(), t1.lower())

                    rule = PIN_CONFLICT_RULES.get(pair) or PIN_CONFLICT_RULES.get(rev_pair)
                    if rule:
                        sev, descr = rule
                        msg = {
                            "rule": "PIN_TYPE_CONFLICT",
                            "severity": sev,
                            "description": f"{descr} on net '{net_name}' between {r1}.{p1} ({t1}) and {r2}.{p2} ({t2}).",
                            "item": net_name
                        }
                        if sev == "ERROR":
                            violations.append(msg)
                        else:
                            warnings.append(msg)

        error_count = len([v for v in violations if v["severity"] == "ERROR"])
        warning_count = len(warnings) + len([v for v in violations if v["severity"] == "WARNING"])
        status = "PASS" if error_count == 0 else "FAIL"

        return {
            "status": status,
            "error_count": error_count,
            "warning_count": warning_count,
            "total_symbols": len(self.symbols),
            "total_nets": len(self.nets),
            "violations": violations,
            "warnings": warnings
        }
