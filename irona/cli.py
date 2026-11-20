"""
Command line entry point (also used by CI):

    python -m irona sim    PROJECT [--current NET=AMPS ...] [--power REF=WATTS ...] [--check]
    python -m irona check  PROJECT [--check]          # DRC + ERC
    python -m irona review PROJECT                    # SI/PI + circuit review
    python -m irona docs   PROJECT                    # report, schematic PDF, Gerbers, BOM, fab zip
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

from irona.project import Project


def _pairs(items: List[str], flag: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for item in items or []:
        name, sep, value = item.rpartition("=")
        if not sep or not name:
            raise SystemExit(f"{flag} expects NAME=VALUE, got {item!r}")
        out[name] = float(value)
    return out


def cmd_sim(args) -> int:
    from irona.simulation import BoardSimulator

    pr = Project(args.project)
    if not pr.pcb:
        raise SystemExit(f"No .kicad_pcb in {pr.dir}")
    saved = pr.load_sim_inputs() or {}
    currents = _pairs(args.current, "--current") or saved.get("load_currents_A", {})
    power = _pairs(args.power, "--power") or saved.get("power_dissipation_W", {})
    sim = BoardSimulator(pr.pcb, ambient_temp_c=args.ambient)
    if not currents:
        hint = ", ".join(sim.suggested_power_nets()) or ", ".join(sim.routed_nets())
        raise SystemExit(f"No load currents given. Pass --current NET=AMPS (nets: {hint})")
    if args.save:
        pr.save_sim_inputs({"load_currents_A": currents, "power_dissipation_W": power})
    result = sim.evaluate(currents, power)
    print(json.dumps(result, indent=2))
    return 1 if args.check and result["status"] != "PASS" else 0


def cmd_check(args) -> int:
    from irona.drc import DRCEngine
    from irona.erc import ERCEngine

    pr = Project(args.project)
    result = {
        "drc": DRCEngine(pr.pcb).run_drc() if pr.pcb else None,
        "erc": ERCEngine(pr.sch, pr.netlist).run_erc() if pr.sch else None,
    }
    print(json.dumps(result, indent=2))
    failed = any(r and r.get("error_count", 0) for r in result.values())
    return 1 if args.check and failed else 0


def cmd_review(args) -> int:
    from irona.sipi_review import SIPIReviewer
    from irona.circuit_review import CircuitReviewer

    pr = Project(args.project)
    result = {
        "sipi": SIPIReviewer(pr.pcb, pr.sch, pr.netlist, pr.load_sim_inputs()).generate_review_report() if pr.pcb else None,
        "circuit": CircuitReviewer().run_full_analysis(pr.sch, pr.pcb, pr.output_dir / "circuit-review") if pr.sch and pr.pcb else None,
    }
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_docs(args) -> int:
    from irona.docs import DocumentationGenerator

    out = DocumentationGenerator(args.project, Path(args.out) if args.out else None).build_all()
    print(json.dumps(out, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="irona", description="Simulation, checks, review and documentation for KiCad projects.")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sim", help="DC IR drop, current density, thermal and impedance estimates")
    p.add_argument("project", type=Path)
    p.add_argument("--current", action="append", metavar="NET=AMPS", help="load current on a net (repeatable)")
    p.add_argument("--power", action="append", metavar="REF=WATTS", help="power dissipated by a part (repeatable)")
    p.add_argument("--ambient", type=float, default=25.0, help="ambient temperature, °C")
    p.add_argument("--save", action="store_true", help="remember these inputs for the report / plugins")
    p.add_argument("--check", action="store_true", help="exit 1 if any limit is exceeded")
    p.set_defaults(func=cmd_sim)

    p = sub.add_parser("check", help="DRC + ERC")
    p.add_argument("project", type=Path)
    p.add_argument("--check", action="store_true", help="exit 1 on any error")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("review", help="SI/PI + circuit review")
    p.add_argument("project", type=Path)
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("docs", help="report, schematic PDF, Gerbers, BOM and fab package")
    p.add_argument("project", type=Path)
    p.add_argument("--out", help="output folder (default PROJECT/irona-out/docs)")
    p.set_defaults(func=cmd_docs)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
