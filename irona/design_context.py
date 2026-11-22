"""
A structured view of a KiCad design for answering questions about it: every component with its
fields (value, MPN, manufacturer, datasheet…), every pin with its net, and every net with its pins.

Connectivity comes from the board (pad nets are what gets fabricated), pin names and types from
the schematic's symbol library, and part fields from the schematic (falling back to the board's
footprint properties). Used by the Assistant plugin and the MCP server.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from irona import sexpr
from irona.project import Project

# Field names people use for the orderable part number, most specific first.
MPN_FIELDS = ("MPN", "Manufacturer_Part_Number", "Manufacturer Part Number", "Mfr. Part #", "PartNumber",
              "Part Number", "MFR_PN", "MPN1")
MANUFACTURER_FIELDS = ("Manufacturer", "MFR", "Mfr", "Manufacturer_Name", "Manufacturer 1")
DISTRIBUTOR_FIELDS = ("LCSC", "LCSC Part", "JLCPCB", "DigiKey", "Digi-Key_PN", "Digi-Key Part Number", "Mouser",
                      "Mouser Part Number", "Farnell", "Newark", "Octopart")
_STANDARD_FIELDS = {"Reference", "Value", "Footprint", "Datasheet", "Description", "ki_description",
                    "ki_keywords", "ki_fp_filters", "Sheetname", "Sheetfile"}


def _clean(v: Optional[str]) -> str:
    v = (v or "").strip()
    return "" if v in ("~", "-") else v


def _first(fields: Dict[str, str], names) -> str:
    lower = {k.lower(): v for k, v in fields.items()}
    for n in names:
        v = _clean(lower.get(n.lower()))
        if v:
            return v
    return ""


class DesignContext:
    """Loads a project once and answers lookups about its parts and nets."""

    def __init__(self, project: Project):
        self.project = project
        self.components: Dict[str, Dict[str, Any]] = {}
        self.nets: Dict[str, List[Dict[str, str]]] = {}
        self.sources: List[str] = []
        self._lib_pins: Dict[str, Dict[str, Dict[str, str]]] = {}
        self._loaded_libs: set = set()
        if project.sch:
            self._read_schematic(project.sch, seen=set())
            self.sources.append(project.sch.name)
        if project.pcb:
            self._read_board(project.pcb)
            self.sources.append(project.pcb.name)
        elif project.netlist:
            self._read_netlist_json(project.netlist)
            self.sources.append(project.netlist.name)
        self._finish()

    @classmethod
    def load(cls, project_dir) -> "DesignContext":
        return cls(Project(Path(project_dir)))

    # ------------------------------------------------------------------ schematic
    def _read_schematic(self, path: Path, seen: set) -> None:
        path = Path(path).resolve()
        if path in seen or not path.exists():
            return
        seen.add(path)
        root = sexpr.parse(path.read_text(encoding="utf-8"))

        libs = sexpr.child(root, "lib_symbols")
        if libs is not None:
            self._add_lib_symbols(libs, prefix="")

        for sym in sexpr.children(root, "symbol"):
            lib_id = sexpr.value(sexpr.child(sym, "lib_id"), default="")
            props = sexpr.properties(sym)
            ref = props.get("Reference", "")
            inst = sexpr.child(sym, "instances")
            if inst is not None:  # hierarchical designs keep the real reference here
                for proj in sexpr.children(inst, "project"):
                    for p in sexpr.children(proj, "path"):
                        ref = sexpr.value(sexpr.child(p, "reference"), default=ref) or ref
            if not ref or ref.startswith("#"):  # power flags / symbols
                continue
            comp = self.components.setdefault(ref, self._blank(ref))
            comp["lib_id"] = lib_id
            comp["value"] = props.get("Value", comp["value"])
            comp["footprint"] = _clean(props.get("Footprint")) or comp["footprint"]
            comp["fields"].update({k: v for k, v in props.items() if k not in ("Reference",) and _clean(v)})
            comp["dnp"] = comp["dnp"] or sexpr.value(sexpr.child(sym, "dnp"), default="no") == "yes"
            comp["in_bom"] = sexpr.value(sexpr.child(sym, "in_bom"), default="yes") != "no"
            if lib_id not in self._lib_pins:
                self._load_project_library(lib_id.partition(":")[0])
            for name, pin in self._lib_pins.get(lib_id, {}).items():
                comp["pins"].setdefault(name, {"pad": name, "name": pin["name"], "type": pin["type"], "net": ""})

        for sheet in sexpr.children(root, "sheet"):
            sheet_file = sexpr.properties(sheet).get("Sheetfile") or sexpr.properties(sheet).get("Sheet file")
            if sheet_file:
                self._read_schematic(path.parent / sheet_file, seen)

    def _add_lib_symbols(self, lib_node, prefix: str) -> None:
        """Pin number -> name/type for every symbol in a lib_symbols block or a .kicad_sym file."""
        for sym in sexpr.children(lib_node, "symbol"):
            pins: Dict[str, Dict[str, str]] = {}
            for unit in [sym] + list(sexpr.children(sym, "symbol")):
                for pin in sexpr.children(unit, "pin"):
                    num = sexpr.value(sexpr.child(pin, "number"))
                    if num is not None:
                        pins[num] = {"name": sexpr.value(sexpr.child(pin, "name"), default=""),
                                     "type": sexpr.value(pin, 1, "")}
            self._lib_pins[prefix + sym[1]] = pins

    def _load_project_library(self, nickname: str) -> None:
        """Symbols not embedded in the schematic: look them up in the project's own sym-lib-table."""
        if not nickname or nickname in self._loaded_libs:
            return
        self._loaded_libs.add(nickname)
        table = self.project.dir / "sym-lib-table"
        if not table.exists():
            return
        try:
            for lib in sexpr.children(sexpr.parse(table.read_text(encoding="utf-8")), "lib"):
                if sexpr.value(sexpr.child(lib, "name")) != nickname:
                    continue
                uri = sexpr.value(sexpr.child(lib, "uri"), default="")
                f = Path(uri.replace("${KIPRJMOD}", str(self.project.dir)))
                if f.exists():
                    self._add_lib_symbols(sexpr.parse(f.read_text(encoding="utf-8")), prefix=nickname + ":")
        except (OSError, ValueError):
            pass

    # ------------------------------------------------------------------ board
    def _read_board(self, path: Path) -> None:
        root = sexpr.parse(Path(path).read_text(encoding="utf-8"))
        for fp in sexpr.children(root, "footprint"):
            props = sexpr.properties(fp)
            ref = props.get("Reference")
            if not ref:  # KiCad 6 style
                ref = next((t[2] for t in sexpr.children(fp, "fp_text") if len(t) > 2 and t[1] == "reference"), "")
            if not ref or ref.startswith("#"):
                continue
            comp = self.components.setdefault(ref, self._blank(ref))
            comp["on_board"] = True
            comp["footprint"] = comp["footprint"] or fp[1]
            comp["value"] = comp["value"] or props.get("Value", "")
            layer = sexpr.value(sexpr.child(fp, "layer"), default="F.Cu")
            comp["side"] = "bottom" if layer.startswith("B.") else "top"
            for k, v in props.items():
                if k not in ("Reference", "Value", "Footprint") and _clean(v):
                    comp["fields"].setdefault(k, v)
            for pad in sexpr.children(fp, "pad"):
                num = pad[1] if len(pad) > 1 and isinstance(pad[1], str) else ""
                if not num:  # mounting holes etc.
                    continue
                net_node = sexpr.child(pad, "net")
                net = ""
                if net_node is not None:
                    strings = [x for x in net_node[1:] if isinstance(x, str)]
                    net = strings[-1] if strings else ""
                pin = comp["pins"].setdefault(num, {"pad": num, "name": "", "type": "", "net": ""})
                pin["net"] = net or pin["net"]
                pin["name"] = pin["name"] or sexpr.value(sexpr.child(pad, "pinfunction"), default="")
                pin["type"] = pin["type"] or sexpr.value(sexpr.child(pad, "pintype"), default="")

    def _read_netlist_json(self, path: Path) -> None:
        import json
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for c in data.get("components", []):
            comp = self.components.setdefault(c["ref"], self._blank(c["ref"]))
            comp["value"] = comp["value"] or c.get("value", "")
            for p in c.get("pins", []):
                comp["pins"].setdefault(p["num"], {"pad": p["num"], "name": p.get("name", ""), "type": "", "net": ""})
        for net, nodes in data.get("nets", {}).items():
            for n in nodes:
                comp = self.components.get(n["ref"])
                if comp and n["pin"] in comp["pins"]:
                    comp["pins"][n["pin"]]["net"] = net

    # ------------------------------------------------------------------ assembly
    @staticmethod
    def _blank(ref: str) -> Dict[str, Any]:
        return {"ref": ref, "value": "", "footprint": "", "lib_id": "", "fields": {}, "pins": {},
                "dnp": False, "in_bom": True, "on_board": False, "side": ""}

    def _finish(self) -> None:
        for ref, comp in self.components.items():
            f = comp["fields"]
            comp["mpn"] = _first(f, MPN_FIELDS)
            comp["manufacturer"] = _first(f, MANUFACTURER_FIELDS)
            comp["datasheet"] = _clean(f.get("Datasheet"))
            comp["description"] = _clean(f.get("Description") or f.get("ki_description"))
            comp["distributor_pns"] = {k: v for k, v in f.items() if k in DISTRIBUTOR_FIELDS and _clean(v)}
            comp["other_fields"] = {k: v for k, v in f.items()
                                    if k not in _STANDARD_FIELDS and k not in comp["distributor_pns"]
                                    and k not in MPN_FIELDS and k not in MANUFACTURER_FIELDS}
            for pin in comp["pins"].values():
                if pin["net"]:
                    self.nets.setdefault(pin["net"], []).append({"ref": ref, "pad": pin["pad"], "pin_name": pin["name"]})

    # ------------------------------------------------------------------ queries
    @staticmethod
    def _sort_key(ref: str):
        head = ref.rstrip("0123456789")
        tail = ref[len(head):]
        return (head, int(tail) if tail.isdigit() else 0, ref)

    def refs(self) -> List[str]:
        return sorted(self.components, key=self._sort_key)

    def component_row(self, ref: str) -> Dict[str, Any]:
        c = self.components[ref]
        row = {k: c[k] for k in ("ref", "value", "footprint", "mpn", "manufacturer", "datasheet", "description")}
        if c["distributor_pns"]:
            row["distributor_pns"] = c["distributor_pns"]
        if c["dnp"]:
            row["dnp"] = True
        return row

    def component_detail(self, ref: str) -> Optional[Dict[str, Any]]:
        key = next((r for r in self.components if r.lower() == ref.strip().lower()), None)
        if key is None:
            return None
        c = self.components[key]
        out = self.component_row(key)
        out.update({"lib_id": c["lib_id"], "side": c["side"], "on_board": c["on_board"], "in_bom": c["in_bom"],
                    "other_fields": c["other_fields"]})
        pins = []
        for pad in sorted(c["pins"], key=self._sort_key):
            p = c["pins"][pad]
            peers = [f"{n['ref']}.{n['pad']}" + (f" ({n['pin_name']})" if n["pin_name"] and n["pin_name"] != n["pad"] else "")
                     for n in self.nets.get(p["net"], []) if n["ref"] != key]
            pins.append({"pad": pad, "name": p["name"], "type": p["type"], "net": p["net"] or "(unconnected)",
                         "connected_to": peers})
        out["pins"] = pins
        return out

    def net_detail(self, name: str) -> Optional[Dict[str, Any]]:
        key = next((n for n in self.nets if n.lower() == name.strip().lower()), None)
        if key is None:
            return None
        nodes = []
        for n in self.nets[key]:
            c = self.components[n["ref"]]
            nodes.append({"ref": n["ref"], "pad": n["pad"], "pin_name": n["pin_name"], "value": c["value"],
                          "mpn": c["mpn"]})
        return {"net": key, "node_count": len(nodes), "nodes": nodes}

    def overview(self) -> Dict[str, Any]:
        refs = self.refs()
        bom = [r for r in refs if self.components[r]["in_bom"] and not self.components[r]["dnp"]]
        return {
            "project": self.project.name,
            "directory": str(self.project.dir),
            "sources": self.sources,
            "component_count": len(refs),
            "bom_line_count": len(bom),
            "net_count": len(self.nets),
            "nets": sorted(self.nets, key=lambda n: (-len(self.nets[n]), n)),
            "missing_mpn": [r for r in bom if not self.components[r]["mpn"]],
            "missing_datasheet": [r for r in bom if not self.components[r]["datasheet"]],
            "components": [self.component_row(r) for r in refs],
        }
