"""
Schematic Builder Tool for KiCad 10 (Irona EDA)
Instantiates components, handles pin-to-wire connections, places net labels,
junctions, and exports both KiCad 10 .kicad_sch files and netlists for layout.
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
import logging
import argparse
from typing import Dict, Any, List, Optional, Tuple

from kicad_scripts.sexpr_generator import KiCad10SchematicGenerator, generate_uuid

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SchematicBuilder")


class SchematicCircuitBuilder:
    """High-level builder to assemble circuits into KiCad 10 schematics."""

    def __init__(self, project_name: str, output_dir: Path):
        self.project_name = project_name
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sch_gen = KiCad10SchematicGenerator(title=f"{project_name} Schematic", company="Irona AI")
        self.components: List[Dict[str, Any]] = []
        self.nets: Dict[str, List[Dict[str, Any]]] = {}  # net_name -> list of pin connections

    def add_component(
        self,
        ref: str,
        value: str,
        lib_id: str,
        footprint: str,
        x: float,
        y: float,
        angle: int = 0,
        pins: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Adds a component to the schematic."""
        pins_list = pins or []
        sym_uuid = self.sch_gen.add_symbol(
            lib_id=lib_id,
            ref=ref,
            value=value,
            footprint=footprint,
            x=x,
            y=y,
            angle=angle,
            pins=pins_list
        )
        self.components.append({
            "uuid": sym_uuid,
            "ref": ref,
            "value": value,
            "lib_id": lib_id,
            "footprint": footprint,
            "x": x,
            "y": y,
            "angle": angle,
            "pins": pins_list
        })
        logger.info(f"Added component {ref} ({value}) at ({x}, {y})")
        return sym_uuid

    def connect_net(self, net_name: str, ref: str, pin_num: str) -> None:
        """Registers a logical connection between a component pin and a net."""
        if net_name not in self.nets:
            self.nets[net_name] = []
        self.nets[net_name].append({"ref": ref, "pin": pin_num})
        logger.debug(f"Connected {ref}.{pin_num} -> Net '{net_name}'")

    def build_buck_converter_circuit(self, vin_v: float = 12.0, vout_v: float = 3.3, iout_a: float = 2.0) -> None:
        """
        Builds a standard synchronous buck converter circuit (e.g. TPS54202 architecture).
        Includes: Input Filter, IC, Bootstrap, Inductor, Feedback Divider, Output Filter.
        """
        logger.info(f"Building Buck Converter Circuit ({vin_v}V -> {vout_v}V @ {iout_a}A)...")

        # 1. Input Connector J1
        self.add_component(
            ref="J1",
            value="Power_In",
            lib_id="Irona_Symbols:Power_In",
            footprint="Irona_Footprints:Power_In",
            x=38.1,
            y=63.5,
            pins=[{"num": "1", "name": "VIN"}, {"num": "2", "name": "GND"}]
        )
        self.connect_net("VIN", "J1", "1")
        self.connect_net("GND", "J1", "2")

        # 2. Input Decoupling Capacitors C1 (10uF), C2 (100nF)
        self.add_component("C1", "10uF/25V", "Irona_Symbols:C_0805", "Irona_Footprints:C_0805", 58.42, 63.5,
                           pins=[{"num": "1", "name": "1"}, {"num": "2", "name": "2"}])
        self.connect_net("VIN", "C1", "1")
        self.connect_net("GND", "C1", "2")

        self.add_component("C2", "100nF/50V", "Irona_Symbols:C_0805", "Irona_Footprints:C_0805", 71.12, 63.5,
                           pins=[{"num": "1", "name": "1"}, {"num": "2", "name": "2"}])
        self.connect_net("VIN", "C2", "1")
        self.connect_net("GND", "C2", "2")

        # 3. Main Buck IC U1 (TPS54202 / SOT23-6)
        u1_pins = [
            {"num": "1", "name": "GND", "side": "left"},
            {"num": "2", "name": "SW", "side": "right"},
            {"num": "3", "name": "VIN", "side": "left"},
            {"num": "4", "name": "FB", "side": "right"},
            {"num": "5", "name": "EN", "side": "left"},
            {"num": "6", "name": "BOOT", "side": "right"},
        ]
        self.add_component("U1", "TPS54202", "Irona_Symbols:TPS54202", "Irona_Footprints:TPS54202", 99.06, 63.5, pins=u1_pins)
        self.connect_net("GND", "U1", "1")
        self.connect_net("SW_NODE", "U1", "2")
        self.connect_net("VIN", "U1", "3")
        self.connect_net("FB", "U1", "4")
        self.connect_net("VIN", "U1", "5")  # EN tied to VIN for always-on
        self.connect_net("BOOT", "U1", "6")

        # 4. Bootstrap Cap C_BOOT (100nF) between BOOT (pin 6) and SW (pin 2)
        self.add_component("C_BOOT", "100nF", "Irona_Symbols:C_0805", "Irona_Footprints:C_0805", 114.3, 50.8,
                           pins=[{"num": "1", "name": "1"}, {"num": "2", "name": "2"}])
        self.connect_net("BOOT", "C_BOOT", "1")
        self.connect_net("SW_NODE", "C_BOOT", "2")

        # 5. Power Inductor L1 (4.7uH)
        self.add_component("L1", "4.7uH", "Irona_Symbols:L_0805", "Irona_Footprints:L_0805", 132.08, 63.5,
                           pins=[{"num": "1", "name": "1"}, {"num": "2", "name": "2"}])
        self.connect_net("SW_NODE", "L1", "1")
        self.connect_net("VOUT_3V3", "L1", "2")

        # 6. Feedback Divider R1 (e.g. 40.2k), R2 (e.g. 10.0k for 0.596V Vref -> 3.3V)
        self.add_component("R1", "40.2k", "Irona_Symbols:R_0805", "Irona_Footprints:R_0805", 152.4, 63.5,
                           pins=[{"num": "1", "name": "1"}, {"num": "2", "name": "2"}])
        self.connect_net("VOUT_3V3", "R1", "1")
        self.connect_net("FB", "R1", "2")

        self.add_component("R2", "10.0k", "Irona_Symbols:R_0805", "Irona_Footprints:R_0805", 152.4, 76.2,
                           pins=[{"num": "1", "name": "1"}, {"num": "2", "name": "2"}])
        self.connect_net("FB", "R2", "1")
        self.connect_net("GND", "R2", "2")

        # 7. Output Filter Capacitors C3 (22uF), C4 (22uF)
        self.add_component("C3", "22uF/10V", "Irona_Symbols:C_0805", "Irona_Footprints:C_0805", 170.18, 63.5,
                           pins=[{"num": "1", "name": "1"}, {"num": "2", "name": "2"}])
        self.connect_net("VOUT_3V3", "C3", "1")
        self.connect_net("GND", "C3", "2")

        self.add_component("C4", "22uF/10V", "Irona_Symbols:C_0805", "Irona_Footprints:C_0805", 182.88, 63.5,
                           pins=[{"num": "1", "name": "1"}, {"num": "2", "name": "2"}])
        self.connect_net("VOUT_3V3", "C4", "1")
        self.connect_net("GND", "C4", "2")

        # 8. Output Connector J2
        self.add_component(
            ref="J2",
            value="Power_Out",
            lib_id="Irona_Symbols:Power_Out",
            footprint="Irona_Footprints:Power_Out",
            x=203.2,
            y=63.5,
            pins=[{"num": "1", "name": "VOUT"}, {"num": "2", "name": "GND"}]
        )
        self.connect_net("VOUT_3V3", "J2", "1")
        self.connect_net("GND", "J2", "2")

        # Add Wires, Net Labels, and Power Symbols
        self._add_schematic_wiring()

    def _add_schematic_wiring(self) -> None:
        """Injects visual wires and net labels for standard power nodes."""
        self.sch_gen.add_label("VIN", 48.0, 58.0)
        self.sch_gen.add_label("SW_NODE", 118.0, 60.0)
        self.sch_gen.add_label("VOUT_3V3", 145.0, 58.0)
        self.sch_gen.add_label("FB", 148.0, 70.0)
        self.sch_gen.add_label("GND", 58.0, 78.0)

        # Wire segments linking blocks
        self.sch_gen.add_wire(38.1, 60.0, 58.42, 60.0)
        self.sch_gen.add_wire(58.42, 60.0, 99.06, 60.0)
        self.sch_gen.add_wire(99.06, 63.5, 132.08, 63.5)
        self.sch_gen.add_wire(132.08, 63.5, 170.18, 63.5)
        self.sch_gen.add_wire(170.18, 63.5, 203.2, 63.5)
        self.sch_gen.add_junction(58.42, 60.0)
        self.sch_gen.add_junction(132.08, 63.5)
        self.sch_gen.add_junction(170.18, 63.5)

    def export_schematic(self, filename: Optional[str] = None) -> Path:
        """Writes the .kicad_sch file."""
        fname = filename or f"{self.project_name}.kicad_sch"
        sch_file = self.output_dir / fname
        content = self.sch_gen.serialize()
        sch_file.write_text(content, encoding="utf-8")
        logger.info(f"Exported KiCad 10 Schematic: {sch_file.name}")
        return sch_file

    def export_netlist(self, filename: Optional[str] = None) -> Path:
        """Exports a JSON and IPC-compatible netlist dictionary."""
        fname = filename or f"{self.project_name}_netlist.json"
        netlist_file = self.output_dir / fname

        netlist_payload = {
            "project": self.project_name,
            "components": self.components,
            "nets": self.nets
        }

        netlist_file.write_text(json.dumps(netlist_payload, indent=2), encoding="utf-8")
        logger.info(f"Exported Netlist: {netlist_file.name}")
        return netlist_file


def main():
    parser = argparse.ArgumentParser(description="Irona KiCad 10 Schematic Builder")
    parser.add_argument("--project-name", "-n", default="irona_buck", help="Project name")
    parser.add_argument("--output-dir", "-o", default="./projects/irona_buck", help="Output directory")
    parser.add_argument("--vin", type=float, default=12.0, help="Input Voltage")
    parser.add_argument("--vout", type=float, default=3.3, help="Output Voltage")
    parser.add_argument("--iout", type=float, default=2.0, help="Output Current (Amps)")
    args = parser.parse_args()

    builder = SchematicCircuitBuilder(args.project_name, Path(args.output_dir))
    builder.build_buck_converter_circuit(vin_v=args.vin, vout_v=args.vout, iout_a=args.iout)
    sch_path = builder.export_schematic()
    netlist_path = builder.export_netlist()
    print(f"Generated schematic: {sch_path}")
    print(f"Generated netlist: {netlist_path}")


if __name__ == "__main__":
    main()
