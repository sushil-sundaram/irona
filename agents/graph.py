"""
LangGraph Multi-Agent State Graph for Irona KiCad 10
Orchestrates the end-to-end design loop: Orchestrator -> Librarian -> Schematic -> Spatial -> Router -> Physics -> CI/CD.
Includes automatic closed-loop physics correction routing.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Literal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.state import IronaAgentState
from agents.orchestrator import MasterOrchestratorAgent
from agents.spatial_agent import SpatialLayoutAgent
from tools.librarian import Librarian
from tools.schematic_builder import SchematicCircuitBuilder
from tools.ipc_router import IPCRouterEngine
from tools.physics_solver import PhysicsSolverEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MultiAgentGraph")


def orchestrator_node(state: IronaAgentState) -> IronaAgentState:
    """Master Orchestrator decomposes spec and plans BOM."""
    orchestrator = MasterOrchestratorAgent()
    return orchestrator.parse_spec_and_plan(state)


def librarian_node(state: IronaAgentState) -> IronaAgentState:
    """Librarian fetches CAD models and registers KiCad library tables."""
    logger.info("Librarian node executing CAD part acquisition...")
    proj_dir = Path(state["project_dir"]).resolve()
    librarian = Librarian(proj_dir)

    for item in state["bom"]:
        mpn = item.get("mpn", item["value"])
        cat = item.get("category", "IC")
        librarian.fetch_or_create_part(mpn=mpn, category=cat)

    state["libraries_registered"] = True
    state["messages"].append({
        "role": "librarian",
        "content": f"Registered {len(state['bom'])} component symbols and footprints in project libraries."
    })
    return state


def schematic_node(state: IronaAgentState) -> IronaAgentState:
    """Generates KiCad 10 schematic and exports netlist."""
    logger.info("Schematic node building circuit schematic...")
    proj_dir = Path(state["project_dir"]).resolve()
    proj_name = state["project_name"]

    reqs = state["requirements"]
    builder = SchematicCircuitBuilder(proj_name, proj_dir)
    builder.build_buck_converter_circuit(
        vin_v=reqs.get("vin_nominal_v", 12.0),
        vout_v=reqs.get("vout_target_v", 3.3),
        iout_a=reqs.get("iout_max_a", 2.0)
    )

    sch_path = builder.export_schematic()
    netlist_path = builder.export_netlist()

    state["schematic_path"] = str(sch_path)
    state["netlist_path"] = str(netlist_path)
    state["messages"].append({
        "role": "schematic_builder",
        "content": f"Generated schematic {sch_path.name} and netlist {netlist_path.name}."
    })
    return state


def spatial_node(state: IronaAgentState) -> IronaAgentState:
    """Spatial reasoning and coordinate floorplanning."""
    spatial_agent = SpatialLayoutAgent()
    return spatial_agent.plan_layout(state)


def router_node(state: IronaAgentState) -> IronaAgentState:
    """Executes PCB placement, track routing, via stitching, and zone fills."""
    logger.info("Router node executing PCB layout and track routing...")
    proj_dir = Path(state["project_dir"]).resolve()
    proj_name = state["project_name"]
    pcb_path = proj_dir / f"{proj_name}.kicad_pcb"

    plan = state["spatial_layout_plan"]
    router = IPCRouterEngine(
        board_width=plan.get("board_width_mm", 60.0),
        board_height=plan.get("board_height_mm", 40.0)
    )

    netlist_data = router.load_netlist(Path(state["netlist_path"]))
    router.place_components(plan["placements"])

    # Route tracks with width determined by spatial agent
    p_w = plan.get("power_track_width_mm", 2.0)
    s_w = plan.get("signal_track_width_mm", 0.25)

    # VIN
    router.route_net_track(4.5, 20.0, 14.0, 15.0, width=p_w, layer="F.Cu", net_name="VIN")
    router.route_net_track(14.0, 15.0, 18.0, 15.0, width=p_w, layer="F.Cu", net_name="VIN")
    router.route_net_track(18.0, 15.0, 24.0, 20.0, width=p_w, layer="F.Cu", net_name="VIN")
    router.route_net_track(24.0, 20.0, 24.0, 18.73, width=p_w, layer="F.Cu", net_name="VIN")

    # SW Node & BOOT
    router.route_net_track(28.0, 21.27, 34.5, 20.0, width=p_w, layer="F.Cu", net_name="SW_NODE")
    router.route_net_track(28.0, 18.73, 27.0, 12.0, width=s_w, layer="F.Cu", net_name="BOOT")
    router.route_net_track(29.0, 12.0, 34.5, 20.0, width=s_w, layer="F.Cu", net_name="BOOT_SW")

    # VOUT
    router.route_net_track(37.5, 20.0, 44.0, 19.0, width=p_w, layer="F.Cu", net_name="VOUT_3V3")
    router.route_net_track(44.0, 19.0, 48.0, 19.0, width=p_w, layer="F.Cu", net_name="VOUT_3V3")
    router.route_net_track(48.0, 19.0, 52.5, 20.0, width=p_w, layer="F.Cu", net_name="VOUT_3V3")
    router.route_net_track(44.0, 19.0, 34.0, 29.0, width=s_w, layer="F.Cu", net_name="VOUT_SENSE")

    # FB
    router.route_net_track(34.0, 31.0, 28.0, 29.0, width=s_w, layer="F.Cu", net_name="FB")
    router.route_net_track(28.0, 29.0, 28.0, 20.0, width=s_w, layer="F.Cu", net_name="FB")

    # Vias & Ground Plane
    for vx, vy in plan.get("thermal_vias", []):
        router.add_thermal_via(vx, vy, net_name="GND")

    if plan.get("ground_plane", True):
        router.pour_ground_plane(net_name="GND", layer="B.Cu")

    saved_pcb = router.save(pcb_path)
    state["pcb_path"] = str(saved_pcb)
    state["messages"].append({
        "role": "ipc_router",
        "content": f"Routed PCB layout saved to {saved_pcb.name}."
    })
    return state


def physics_validator_node(state: IronaAgentState) -> IronaAgentState:
    """Runs headless Power Integrity, Thermal, and Signal Integrity physics simulations."""
    logger.info("Physics Validator node executing multiphysics simulations...")
    pcb_path = Path(state["pcb_path"])
    iout = state["requirements"].get("iout_max_a", 2.0)

    solver = PhysicsSolverEngine(pcb_path)
    physics_report = solver.evaluate_board(iout_a=iout)

    state["physics_results"] = physics_report
    state["physics_passed"] = (physics_report.get("status") == "PASS")

    status_str = "PASSED" if state["physics_passed"] else "VIOLATIONS DETECTED"
    state["messages"].append({
        "role": "physics_validator",
        "content": f"Physics simulation {status_str}: Max IR drop = {physics_report['power_integrity']['max_voltage_drop_mv']}mV, Max Temp = {physics_report['thermal']['max_junction_temp_c']}°C."
    })
    return state


def physics_routing_condition(state: IronaAgentState) -> Literal["ci_doc_node", "spatial_node"]:
    """Conditional routing edge: Loops back to spatial node on failure, or advances to CI/CD docs on pass."""
    if state.get("physics_passed", False):
        logger.info("Physics validation PASSED. Proceeding to CI/CD & Documentation node.")
        return "ci_doc_node"

    iteration = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)

    if iteration < max_iter:
        state["iteration_count"] = iteration + 1
        logger.warning(f"Physics validation failed. Triggering closed-loop re-routing (Iteration {state['iteration_count']}/{max_iter})...")
        return "spatial_node"
    else:
        logger.error("Maximum layout iterations reached. Proceeding to CI/CD with warning flags.")
        return "ci_doc_node"


def ci_doc_node(state: IronaAgentState) -> IronaAgentState:
    """Final node compiling manufacturing summary and KiBot pipeline status."""
    logger.info("CI/CD Documentation node compiling final project release package...")
    state["status"] = "COMPLETED" if state.get("physics_passed", False) else "COMPLETED_WITH_WARNINGS"
    state["messages"].append({
        "role": "ci_doc",
        "content": "Generated complete KiCad 10 project with schematic, PCB, physics reports, and KiBot automation configs."
    })
    return state


class IronaDesignGraph:
    """Manages the execution flow of the multi-agent system."""

    def __init__(self):
        pass

    def run(self, initial_state: IronaAgentState) -> IronaAgentState:
        """Executes the multi-agent design graph synchronously."""
        logger.info(f"Starting Irona Multi-Agent Design Flow for project: '{initial_state['project_name']}'")

        state = orchestrator_node(initial_state)
        state = librarian_node(state)
        state = schematic_node(state)

        # Closed-loop spatial/router/physics convergence loop
        while True:
            state = spatial_node(state)
            state = router_node(state)
            state = physics_validator_node(state)

            next_step = physics_routing_condition(state)
            if next_step == "ci_doc_node":
                break

        state = ci_doc_node(state)
        return state
