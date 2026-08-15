"""
KiCad 10 S-Expression Parser & Generator
Provides utilities to parse, construct, and serialize KiCad 10 files (.kicad_sch, .kicad_pcb, .kicad_pro).
"""

import uuid
from typing import List, Dict, Any, Tuple, Optional


def generate_uuid() -> str:
    """Generate a valid KiCad UUID string."""
    return str(uuid.uuid4())


class SExprBuilder:
    """Helper to build structured S-expressions with indentation."""

    def __init__(self, tag: str):
        self.tag = tag
        self.attributes: List[Any] = []
        self.children: List[Any] = []

    def add_attr(self, attr: Any) -> 'SExprBuilder':
        self.attributes.append(attr)
        return self

    def add_child(self, child: Any) -> 'SExprBuilder':
        self.children.append(child)
        return self

    def to_string(self, indent_level: int = 0) -> str:
        pad = "  " * indent_level
        attr_strs = []
        for a in self.attributes:
            if isinstance(a, str) and not a.startswith('"') and not a.startswith("("):
                if any(c in a for c in " \t\n()"):
                    attr_strs.append(f'"{a}"')
                else:
                    attr_strs.append(a)
            elif isinstance(a, (int, float)):
                attr_strs.append(str(a))
            else:
                attr_strs.append(str(a))

        attrs_line = " ".join(attr_strs)
        header = f"({self.tag} {attrs_line}".strip()

        if not self.children:
            return f"{pad}{header})"

        child_strs = []
        for c in self.children:
            if isinstance(c, SExprBuilder):
                child_strs.append(c.to_string(indent_level + 1))
            elif isinstance(c, str):
                child_strs.append(f"{pad}  {c}")
            else:
                child_strs.append(f"{pad}  {str(c)}")

        children_block = "\n".join(child_strs)
        return f"{pad}{header}\n{children_block}\n{pad})"


class KiCad10SchematicGenerator:
    """Generates complete KiCad 10 .kicad_sch documents."""

    def __init__(self, title: str = "Irona KiCad 10 Schematic", company: str = "Irona AI"):
        self.title = title
        self.company = company
        self.symbols: List[Dict[str, Any]] = []
        self.wires: List[Dict[str, Any]] = []
        self.labels: List[Dict[str, Any]] = []
        self.junctions: List[Tuple[float, float]] = []
        self.sheet_uuid = generate_uuid()

    def add_symbol(
        self,
        lib_id: str,
        ref: str,
        value: str,
        footprint: str,
        x: float,
        y: float,
        angle: int = 0,
        pins: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        sym_uuid = generate_uuid()
        self.symbols.append({
            "uuid": sym_uuid,
            "lib_id": lib_id,
            "ref": ref,
            "value": value,
            "footprint": footprint,
            "x": x,
            "y": y,
            "angle": angle,
            "pins": pins or []
        })
        return sym_uuid

    def add_wire(self, start_x: float, start_y: float, end_x: float, end_y: float) -> str:
        wire_uuid = generate_uuid()
        self.wires.append({
            "uuid": wire_uuid,
            "start": (start_x, start_y),
            "end": (end_x, end_y)
        })
        return wire_uuid

    def add_label(self, name: str, x: float, y: float, angle: int = 0) -> str:
        lbl_uuid = generate_uuid()
        self.labels.append({
            "uuid": lbl_uuid,
            "name": name,
            "x": x,
            "y": y,
            "angle": angle
        })
        return lbl_uuid

    def add_junction(self, x: float, y: float) -> None:
        self.junctions.append((x, y))

    def serialize(self) -> str:
        """Serialize into valid KiCad 10 .kicad_sch S-expression."""
        lines = [
            '(kicad_sch',
            '  (version 20231120)',
            '  (generator "irona_schematic_engine")',
            '  (generator_version "10.0")',
            f'  (uuid "{self.sheet_uuid}")',
            '  (paper "A4")',
            '  (title_block',
            f'    (title "{self.title}")',
            f'    (company "{self.company}")',
            '  )'
        ]

        # Add symbols
        for sym in self.symbols:
            lines.append('  (symbol')
            lines.append(f'    (lib_id "{sym["lib_id"]}")')
            lines.append(f'    (at {sym["x"]} {sym["y"]} {sym["angle"]})')
            lines.append(f'    (unit 1)')
            lines.append(f'    (exclude_from_sim no)')
            lines.append(f'    (in_bom yes)')
            lines.append(f'    (on_board yes)')
            lines.append(f'    (dnp no)')
            lines.append(f'    (uuid "{sym["uuid"]}")')
            lines.append(f'    (property "Reference" "{sym["ref"]}" (at {sym["x"]} {sym["y"] - 3.81:.2f} 0) (effects (font (size 1.27 1.27))))')
            lines.append(f'    (property "Value" "{sym["value"]}" (at {sym["x"]} {sym["y"] + 3.81:.2f} 0) (effects (font (size 1.27 1.27))))')
            lines.append(f'    (property "Footprint" "{sym["footprint"]}" (at {sym["x"]} {sym["y"]} 0) (effects (font (size 1.27 1.27)) hide))')

            for pin in sym.get("pins", []):
                lines.append(f'    (pin "{pin.get("num", "1")}" (uuid "{generate_uuid()}"))')

            lines.append('  )')

        # Add wires
        for wire in self.wires:
            sx, sy = wire["start"]
            ex, ey = wire["end"]
            lines.append('  (wire')
            lines.append(f'    (pts (xy {sx:.2f} {sy:.2f}) (xy {ex:.2f} {ey:.2f}))')
            lines.append('    (stroke (width 0) (type default))')
            lines.append(f'    (uuid "{wire["uuid"]}")')
            lines.append('  )')

        # Add net labels
        for lbl in self.labels:
            lines.append(f'  (label "{lbl["name"]}" (at {lbl["x"]:.2f} {lbl["y"]:.2f} {lbl["angle"]})')
            lines.append('    (effects (font (size 1.27 1.27)))')
            lines.append(f'    (uuid "{lbl["uuid"]}")')
            lines.append('  )')

        # Add junctions
        for jx, jy in self.junctions:
            lines.append(f'  (junction (at {jx:.2f} {jy:.2f}) (diameter 0.914) (color 0 0 0 0) (uuid "{generate_uuid()}"))')

        lines.append(')')
        return "\n".join(lines) + "\n"


class KiCad10PCBGenerator:
    """Generates complete KiCad 10 .kicad_pcb documents with footprints, tracks, vias, and zones."""

    def __init__(self, title: str = "Irona KiCad 10 Board", width_mm: float = 60.0, height_mm: float = 40.0):
        self.title = title
        self.width_mm = width_mm
        self.height_mm = height_mm
        self.nets: Dict[str, int] = {"": 0}  # Net name -> ID
        self.footprints: List[Dict[str, Any]] = []
        self.tracks: List[Dict[str, Any]] = []
        self.vias: List[Dict[str, Any]] = []
        self.zones: List[Dict[str, Any]] = []

    def get_or_create_net(self, net_name: str) -> int:
        if net_name not in self.nets:
            self.nets[net_name] = len(self.nets)
        return self.nets[net_name]

    def add_footprint(
        self,
        lib_name: str,
        fp_name: str,
        ref: str,
        value: str,
        x: float,
        y: float,
        angle: float = 0.0,
        layer: str = "F.Cu",
        pads: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        fp_uuid = generate_uuid()
        self.footprints.append({
            "uuid": fp_uuid,
            "lib_name": lib_name,
            "fp_name": fp_name,
            "ref": ref,
            "value": value,
            "x": x,
            "y": y,
            "angle": angle,
            "layer": layer,
            "pads": pads or []
        })
        return fp_uuid

    def add_track(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        width: float = 0.25,
        layer: str = "F.Cu",
        net_name: str = ""
    ) -> str:
        net_id = self.get_or_create_net(net_name) if net_name else 0
        track_uuid = generate_uuid()
        self.tracks.append({
            "uuid": track_uuid,
            "start": (start_x, start_y),
            "end": (end_x, end_y),
            "width": width,
            "layer": layer,
            "net": net_id,
            "net_name": net_name
        })
        return track_uuid

    def add_via(
        self,
        x: float,
        y: float,
        size: float = 0.6,
        drill: float = 0.3,
        net_name: str = "",
        layers: Tuple[str, str] = ("F.Cu", "B.Cu")
    ) -> str:
        net_id = self.get_or_create_net(net_name) if net_name else 0
        via_uuid = generate_uuid()
        self.vias.append({
            "uuid": via_uuid,
            "at": (x, y),
            "size": size,
            "drill": drill,
            "net": net_id,
            "layers": layers
        })
        return via_uuid

    def add_zone(
        self,
        net_name: str,
        layer: str = "B.Cu",
        polygon: Optional[List[Tuple[float, float]]] = None
    ) -> str:
        net_id = self.get_or_create_net(net_name)
        zone_uuid = generate_uuid()
        if not polygon:
            polygon = [
                (0.0, 0.0),
                (self.width_mm, 0.0),
                (self.width_mm, self.height_mm),
                (0.0, self.height_mm)
            ]
        self.zones.append({
            "uuid": zone_uuid,
            "net": net_id,
            "net_name": net_name,
            "layer": layer,
            "polygon": polygon
        })
        return zone_uuid

    def serialize(self) -> str:
        """Serialize into valid KiCad 10 .kicad_pcb S-expression."""
        lines = [
            '(kicad_pcb',
            '  (version 20240108)',
            '  (generator "irona_pcb_router")',
            '  (generator_version "10.0")',
            '  (general',
            '    (thickness 1.6)',
            '    (legacy_teardrops no)',
            '  )',
            '  (paper "A4")',
            '  (layers',
            '    (0 "F.Cu" signal)',
            '    (31 "B.Cu" signal)',
            '    (36 "B.SilkS" user "B.Silkscreen")',
            '    (37 "F.SilkS" user "F.Silkscreen")',
            '    (38 "B.Mask" user)',
            '    (39 "F.Mask" user)',
            '    (44 "Edge.Cuts" user)',
            '    (46 "B.CrtYd" user "B.Courtyard")',
            '    (47 "F.CrtYd" user "F.Courtyard")',
            '    (48 "B.Fab" user)',
            '    (49 "F.Fab" user)',
            '  )',
            '  (setup',
            '    (stackup',
            '      (layer "F.SilkS" (type "Top Silk Screen"))',
            '      (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01) (color "Green"))',
            '      (layer "F.Cu" (type "copper") (thickness 0.035))',
            '      (layer "dielectric 1" (type "core") (thickness 1.51) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))',
            '      (layer "B.Cu" (type "copper") (thickness 0.035))',
            '      (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01) (color "Green"))',
            '      (layer "B.SilkS" (type "Bottom Silk Screen"))',
            '    )',
            '    (pad_to_mask_clearance 0)',
            '  )'
        ]

        # Declare Nets
        for net_name, net_id in sorted(self.nets.items(), key=lambda x: x[1]):
            lines.append(f'  (net {net_id} "{net_name}")')

        # Board Outline (Edge.Cuts)
        lines.append(
            f'  (gr_rect (start 0 0) (end {self.width_mm} {self.height_mm}) '
            f'(stroke (width 0.15) (type solid)) (fill none) (layer "Edge.Cuts") (uuid "{generate_uuid()}"))'
        )

        # Footprints
        for fp in self.footprints:
            lines.append(f'  (footprint "{fp["lib_name"]}:{fp["fp_name"]}" (layer "{fp["layer"]}")')
            lines.append(f'    (uuid "{fp["uuid"]}")')
            lines.append(f'    (at {fp["x"]:.2f} {fp["y"]:.2f} {fp["angle"]})')
            lines.append(f'    (property "Reference" "{fp["ref"]}" (at 0 -2.5 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))')
            lines.append(f'    (property "Value" "{fp["value"]}" (at 0 2.5 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))')

            for pad in fp.get("pads", []):
                pad_num = pad.get("num", "1")
                net_name = pad.get("net", "")
                net_id = self.nets.get(net_name, 0)
                px = pad.get("x", 0.0)
                py = pad.get("y", 0.0)
                pw = pad.get("w", 1.0)
                ph = pad.get("h", 1.2)
                lines.append(
                    f'    (pad "{pad_num}" smd rect (at {px:.2f} {py:.2f}) (size {pw} {ph}) '
                    f'(layers "{fp["layer"]}" "F.Paste" "F.Mask") (net {net_id} "{net_name}"))'
                )

            lines.append('  )')

        # Tracks
        for trk in self.tracks:
            sx, sy = trk["start"]
            ex, ey = trk["end"]
            lines.append(
                f'  (segment (start {sx:.2f} {sy:.2f}) (end {ex:.2f} {ey:.2f}) '
                f'(width {trk["width"]}) (layer "{trk["layer"]}") (net {trk["net"]}) (uuid "{trk["uuid"]}"))'
            )

        # Vias
        for via in self.vias:
            vx, vy = via["at"]
            l1, l2 = via["layers"]
            lines.append(
                f'  (via (at {vx:.2f} {vy:.2f}) (size {via["size"]}) (drill {via["drill"]}) '
                f'(layers "{l1}" "{l2}") (net {via["net"]}) (uuid "{via["uuid"]}"))'
            )

        # Zones
        for z in self.zones:
            pts_str = " ".join([f"(xy {px:.2f} {py:.2f})" for px, py in z["polygon"]])
            lines.append(f'  (zone (net {z["net"]}) (net_name "{z["net_name"]}") (layer "{z["layer"]}") (uuid "{z["uuid"]}")')
            lines.append('    (hatch edge 0.5)')
            lines.append('    (connect_pads (clearance 0.3))')
            lines.append('    (min_thickness 0.25)')
            lines.append('    (filled_areas_thickness no)')
            lines.append('    (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))')
            lines.append(f'    (polygon (pts {pts_str}))')
            lines.append('  )')

        lines.append(')')
        return "\n".join(lines) + "\n"
