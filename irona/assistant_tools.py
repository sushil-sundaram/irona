"""
Design tools shared by the in-KiCad Assistant (Claude API) and the MCP server (Claude Code,
Claude Desktop, Antigravity). Each tool reads the project on disk and returns JSON-able data.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from irona.design_context import DesignContext
from irona.project import Project


class ToolError(Exception):
    """A problem the model can act on (bad reference, missing file…), returned as an error result."""


class Workspace:
    """Caches one DesignContext per project and reloads it when the board or schematic changes."""

    def __init__(self, default_project: Optional[Path] = None, search_root: Optional[Path] = None):
        self.default_project = Path(default_project).resolve() if default_project else None
        self.search_root = Path(search_root).resolve() if search_root else self.default_project
        self._cache: Dict[Path, tuple] = {}

    def project(self, path: Optional[str] = None) -> Project:
        target = Path(path).expanduser().resolve() if path else self.default_project
        if target is None:
            raise ToolError("No project given. Pass `project` (a KiCad project folder); find_projects can list them.")
        if target.is_file():
            target = target.parent
        try:
            pr = Project(target)
        except FileNotFoundError as e:
            raise ToolError(str(e)) from None
        if not (pr.pcb or pr.sch):
            raise ToolError(f"No .kicad_pcb or .kicad_sch in {pr.dir}")
        return pr

    def context(self, path: Optional[str] = None) -> DesignContext:
        pr = self.project(path)
        stamp = tuple(f.stat().st_mtime_ns for f in (pr.sch, pr.pcb) if f)
        hit = self._cache.get(pr.dir)
        if hit and hit[0] == stamp:
            return hit[1]
        ctx = DesignContext(pr)
        self._cache[pr.dir] = (stamp, ctx)
        return ctx


# --------------------------------------------------------------------------- tool bodies
def _overview(ws: Workspace, args: Dict[str, Any]):
    return ws.context(args.get("project")).overview()


def _list_components(ws: Workspace, args: Dict[str, Any]):
    ctx = ws.context(args.get("project"))
    q = (args.get("filter") or "").strip().lower()
    rows = [ctx.component_row(r) for r in ctx.refs()]
    if q:
        rows = [r for r in rows if any(q in str(v).lower() for v in r.values())]
    return {"count": len(rows), "components": rows}


def _get_component(ws: Workspace, args: Dict[str, Any]):
    ctx = ws.context(args.get("project"))
    out = []
    for ref in args["refs"]:
        d = ctx.component_detail(ref)
        if d is None:
            raise ToolError(f"No component {ref!r}. Known references: {', '.join(ctx.refs())}")
        out.append(d)
    return {"components": out}


def _get_net(ws: Workspace, args: Dict[str, Any]):
    ctx = ws.context(args.get("project"))
    d = ctx.net_detail(args["net"])
    if d is None:
        raise ToolError(f"No net {args['net']!r}. Nets: {', '.join(sorted(ctx.nets))}")
    return d


def _rule_check(ws: Workspace, args: Dict[str, Any]):
    from irona.drc import DRCEngine
    from irona.erc import ERCEngine
    pr = ws.project(args.get("project"))
    drc = DRCEngine(pr.pcb).run_drc() if pr.pcb else None
    erc = ERCEngine(pr.sch, pr.netlist).run_erc() if pr.sch else None
    return {
        "drc": drc and {"error_count": drc["error_count"], "violations": drc["violations"]},
        "erc": erc and {"error_count": erc["error_count"], "warning_count": erc["warning_count"],
                        "violations": erc.get("violations", []), "warnings": erc.get("warnings", [])},
    }


def _design_review(ws: Workspace, args: Dict[str, Any]):
    from irona.circuit_review import CircuitReviewer
    from irona.sipi_review import SIPIReviewer
    pr = ws.project(args.get("project"))
    out: Dict[str, Any] = {}
    if pr.pcb:
        r = SIPIReviewer(pr.pcb, pr.sch, pr.netlist, pr.load_sim_inputs()).generate_review_report()
        out["sipi"] = {k: r.get(k) for k in ("overall_score", "letter_grade", "critical_findings", "warning_findings")}
    if pr.sch and pr.pcb:
        c = CircuitReviewer().run_full_analysis(pr.sch, pr.pcb, pr.output_dir / "circuit-review")
        out["circuit"] = {k: c.get(k) for k in ("overall_score", "grade", "power_tree", "subcircuits", "findings",
                                                "emc_score", "emc_summary", "emc_error", "dfm_score", "dfm_audit")
                          if k in c}
    return out


def _simulate(ws: Workspace, args: Dict[str, Any]):
    from irona.simulation import BoardSimulator
    pr = ws.project(args.get("project"))
    if not pr.pcb:
        raise ToolError("The simulator needs a .kicad_pcb")
    saved = pr.load_sim_inputs() or {}
    currents = args.get("load_currents_A") or saved.get("load_currents_A")
    power = args.get("power_dissipation_W") or saved.get("power_dissipation_W") or {}
    sim = BoardSimulator(pr.pcb, ambient_temp_c=args.get("ambient_temp_c", saved.get("ambient_temp_c", 25.0)))
    if not currents:
        raise ToolError("No load currents. Pass load_currents_A, e.g. {\"VOUT\": 2.0}. "
                        f"Routed supply nets: {', '.join(sim.suggested_power_nets()) or ', '.join(sim.routed_nets())}")
    return sim.evaluate(currents, power)


def _find_projects(ws: Workspace, args: Dict[str, Any]):
    root = Path(args.get("root") or ws.search_root or Path.home()).expanduser().resolve()
    found = set()
    for pattern in ("*.kicad_pro", "*.kicad_pcb", "*.kicad_sch"):
        for f in root.rglob(pattern):
            rel = f.relative_to(root).parts[:-1]
            if not any(part.startswith(".") or part.endswith("-backups") for part in rel):
                found.add(str(f.parent))
        if len(found) >= 200:
            break
    return {"root": str(root), "projects": sorted(found)[:200]}


# --------------------------------------------------------------------------- registry
_PROJECT_PROP = {"project": {"type": "string",
                             "description": "Path to the KiCad project folder (or a file in it). "
                                            "Optional when the server was started for one project."}}


def _schema(props: Dict[str, Any], required: List[str] = ()) -> Dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_design_overview",
        "description": "Project summary: every component (reference, value, footprint, MPN, manufacturer, "
                       "datasheet URL), the list of nets, and which parts lack an MPN or datasheet. Call this "
                       "first when you need to know what is in the design.",
        "input_schema": _schema(dict(_PROJECT_PROP)),
        "run": _overview,
    },
    {
        "name": "list_components",
        "description": "Components whose reference, value, footprint, MPN, manufacturer or description contains "
                       "`filter` (case-insensitive), e.g. 'U' for ICs, '0805', 'TPS'. Empty filter lists all.",
        "input_schema": _schema({**_PROJECT_PROP, "filter": {"type": "string"}}),
        "run": _list_components,
    },
    {
        "name": "get_component",
        "description": "Full detail for one or more parts: all fields, and every pin with its name, electrical type, "
                       "net and the other pins on that net. Call this before judging whether a part is connected "
                       "the way its datasheet requires.",
        "input_schema": _schema({**_PROJECT_PROP,
                                 "refs": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                                          "description": "Reference designators, e.g. [\"U1\", \"L1\"]"}},
                                ["refs"]),
        "run": _get_component,
    },
    {
        "name": "get_net",
        "description": "Every pin on a net, with the part value and MPN at each pin.",
        "input_schema": _schema({**_PROJECT_PROP, "net": {"type": "string"}}, ["net"]),
        "run": _get_net,
    },
    {
        "name": "run_rule_check",
        "description": "Irona's design-rule check of the board and electrical-rule check of the schematic.",
        "input_schema": _schema(dict(_PROJECT_PROP)),
        "run": _rule_check,
    },
    {
        "name": "run_design_review",
        "description": "Irona's SI/PI + IPC review and circuit review (power tree, regulators, EMC, DFM). "
                       "Takes several seconds.",
        "input_schema": _schema(dict(_PROJECT_PROP)),
        "run": _design_review,
    },
    {
        "name": "run_simulation",
        "description": "Closed-form DC IR drop, current density, thermal hotspot and microstrip impedance estimates. "
                       "Uses the inputs saved by the Simulator plugin unless new ones are given.",
        "input_schema": _schema({**_PROJECT_PROP,
                                 "load_currents_A": {"type": "object", "additionalProperties": {"type": "number"},
                                                     "description": "Net name -> load current in amps"},
                                 "power_dissipation_W": {"type": "object", "additionalProperties": {"type": "number"},
                                                         "description": "Reference -> dissipated power in watts"},
                                 "ambient_temp_c": {"type": "number"}}),
        "run": _simulate,
    },
    {
        "name": "find_projects",
        "description": "Lists KiCad project folders under `root` (folders holding a .kicad_pro, .kicad_pcb or .kicad_sch).",
        "input_schema": _schema({"root": {"type": "string", "description": "Folder to search (default: the workspace, else home)"}}),
        "run": _find_projects,
    },
]

_BY_NAME = {t["name"]: t for t in TOOLS}

_JSON_TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "array": list, "object": dict}


def validate(schema: Dict[str, Any], args: Any) -> Optional[str]:
    """Checks tool input against the (flat) schemas above. Returns an error message or None."""
    if not isinstance(args, dict):
        return "input must be an object"
    for key in schema.get("required", []):
        if key not in args:
            return f"missing required field {key!r}"
    props = schema.get("properties", {})
    for key, val in args.items():
        spec = props.get(key)
        if spec is None:
            return f"unknown field {key!r}"
        typ = _JSON_TYPES.get(spec.get("type"))
        if typ and (not isinstance(val, typ) or (spec.get("type") == "number" and isinstance(val, bool))):
            return f"{key!r} must be {spec['type']}"
        if spec.get("type") == "array" and "items" in spec:
            item_t = _JSON_TYPES.get(spec["items"].get("type"))
            if item_t and not all(isinstance(v, item_t) for v in val):
                return f"items of {key!r} must be {spec['items']['type']}"
        if spec.get("type") == "object" and "additionalProperties" in spec and isinstance(spec["additionalProperties"], dict):
            item_t = _JSON_TYPES.get(spec["additionalProperties"].get("type"))
            if item_t and not all(isinstance(v, item_t) and not isinstance(v, bool) for v in val.values()):
                return f"values of {key!r} must be {spec['additionalProperties']['type']}"
    return None


def call(ws: Workspace, name: str, args: Any, include_project_arg: bool = True) -> Any:
    """Runs a tool. Raises ToolError for problems the caller should report back to the model."""
    tool = _BY_NAME.get(name)
    if tool is None:
        raise ToolError(f"Unknown tool {name!r}")
    schema = tool["input_schema"] if include_project_arg else without_project(tool["input_schema"])
    err = validate(schema, args)
    if err:
        raise ToolError(f"Invalid input for {name}: {err}")
    return tool["run"](ws, args)


def without_project(schema: Dict[str, Any]) -> Dict[str, Any]:
    """The in-KiCad Assistant is bound to the open board, so it hides the `project` argument."""
    s = json.loads(json.dumps(schema))
    s["properties"].pop("project", None)
    return s


def to_json(result: Any) -> str:
    return json.dumps(result, indent=1, default=str)
