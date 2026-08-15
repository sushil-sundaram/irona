"""
Irona KiCad 10 Multi-Agent AI Co-Pilot CLI
Main entry point for autonomous end-to-end hardware design.
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, Any

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.state import IronaAgentState
from agents.graph import IronaDesignGraph

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IronaCLI")


def print_banner():
    banner = r"""
================================================================================
  ___ ____   ___  _   _    _      _  ___ ____    _    ____    _  ___  
 |_ _|  _ \ / _ \| \ | |  / \    | |/ /_ / ___|  / \  |  _ \  / |/ _ \ 
  | || |_) | | | |  \| | / _ \   | ' / | | |     / _ \ | | | | | | | | |
  | ||  _ <| |_| | |\  |/ ___ \  | . \ | | |___ / ___ \| |_| | | | |_| |
 |___|_| \_\\___/|_| \_/_/   \_\ |_|\_\|_|\____/_/   \_\____/  |_|\___/ 
                                                                         
      Autonomous Multi-Agent Hardware Design & Physics Co-Pilot
================================================================================
"""
    print(banner)


def run_design_pipeline(prompt: str, project_name: str, output_dir: Path, vin: float = 12.0, vout: float = 3.3, iout: float = 2.0) -> Dict[str, Any]:
    """Runs the complete multi-agent pipeline."""
    target_dir = Path(output_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # Initialize agent state
    initial_state: IronaAgentState = {
        "project_name": project_name,
        "project_dir": str(target_dir),
        "spec_prompt": prompt,
        "requirements": {
            "circuit_type": "Synchronous_Buck_Converter",
            "vin_nominal_v": vin,
            "vout_target_v": vout,
            "iout_max_a": iout,
            "switching_freq_khz": 500.0,
            "ambient_temp_c": 25.0,
            "max_allowed_temp_c": 85.0
        },
        "bom": [],
        "libraries_registered": False,
        "schematic_path": None,
        "netlist_path": None,
        "pcb_path": None,
        "spatial_layout_plan": {},
        "physics_results": None,
        "physics_passed": False,
        "iteration_count": 0,
        "max_iterations": 3,
        "messages": [],
        "errors": [],
        "status": "INITIALIZED"
    }

    graph = IronaDesignGraph()
    final_state = graph.run(initial_state)
    return final_state


def display_results_summary(state: IronaAgentState):
    """Displays structured summary of generated hardware project."""
    print("\n" + "=" * 80)
    print(f"🚀 DESIGN SUMMARY: {state['project_name']} (Status: {state['status']})")
    print("=" * 80)

    print("\n📋 Electrical Specifications:")
    reqs = state["requirements"]
    print(f"  - Topology:            {reqs.get('circuit_type')}")
    print(f"  - Input Voltage:       {reqs.get('vin_nominal_v')} V")
    print(f"  - Output Voltage:      {reqs.get('vout_target_v')} V")
    print(f"  - Max Output Current:  {reqs.get('iout_max_a')} A")
    print(f"  - Switching Frequency: {reqs.get('switching_freq_khz')} kHz")

    print("\n📦 Bill of Materials (BOM):")
    print(f"  {'Ref':<8} {'MPN':<20} {'Value':<16} {'Package':<12} {'Category'}")
    print("  " + "-" * 70)
    for comp in state["bom"]:
        print(f"  {comp['ref']:<8} {comp['mpn']:<20} {comp['value']:<16} {comp['package']:<12} {comp['category']}")

    print("\n📁 Generated KiCad 10 Artifacts:")
    print(f"  - Schematic:      {state['schematic_path']}")
    print(f"  - Netlist:        {state['netlist_path']}")
    print(f"  - PCB Layout:     {state['pcb_path']}")
    print(f"  - Symbol Lib:     {state['project_dir']}/libraries/symbols/irona.kicad_sym")
    print(f"  - Footprint Lib:  {state['project_dir']}/libraries/footprints.pretty")

    print("\n⚡ Physics Validation Results:")
    if state.get("physics_results"):
        pi = state["physics_results"]["power_integrity"]
        th = state["physics_results"]["thermal"]
        si = state["physics_results"]["signal_integrity"]

        print(f"  - Status:                {'✅ PASS' if state['physics_passed'] else '❌ FAIL'}")
        print(f"  - Max DC IR Drop:        {pi['max_voltage_drop_mv']} mV (Limit: 50.0 mV)")
        print(f"  - Max Current Density:   {pi['max_current_density_A_mm2']} A/mm² (Limit: 35.0 A/mm²)")
        print(f"  - Max Junction Temp:     {th['max_junction_temp_c']} °C (Ambient: {th['ambient_temp_c']} °C, Delta: +{th['delta_temp_c']} °C)")
        print(f"  - Trace Impedances (Z0): {si['trace_impedances_ohm']}")

    print("\n🛠️ Next Steps:")
    print(f"  1. Open in KiCad 10:      kicad {state['project_dir']}/{state['project_name']}.kicad_pro")
    print(f"  2. Run Headless Physics:  python tools/physics_solver.py --board {state['pcb_path']} --check")
    print(f"  3. Run KiBot CI/CD:       kibot -c config/kibot.yaml -e {state['schematic_path']} -b {state['pcb_path']}")
    print("=" * 80 + "\n")


def main():
    print_banner()
    parser = argparse.ArgumentParser(description="Irona KiCad 10 Multi-Agent AI Co-Pilot")
    parser.add_argument(
        "--prompt", "-p",
        default="Design a 12V to 3.3V 2A Synchronous Step-Down Buck Converter with TPS54202",
        help="Hardware design requirement specification prompt"
    )
    parser.add_argument("--name", "-n", default="irona_buck_converter", help="Project name")
    parser.add_argument("--output", "-o", default="./projects/irona_buck_converter", help="Output project directory")
    parser.add_argument("--vin", type=float, default=12.0, help="Nominal input voltage (V)")
    parser.add_argument("--vout", type=float, default=3.3, help="Target output voltage (V)")
    parser.add_argument("--iout", type=float, default=2.0, help="Max load current (A)")
    args = parser.parse_args()

    final_state = run_design_pipeline(
        prompt=args.prompt,
        project_name=args.name,
        output_dir=Path(args.output),
        vin=args.vin,
        vout=args.vout,
        iout=args.iout
    )

    display_results_summary(final_state)


if __name__ == "__main__":
    main()
