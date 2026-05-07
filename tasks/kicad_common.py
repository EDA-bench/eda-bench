from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SExpr = str | list["SExpr"]


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class SchematicSymbol:
    reference: str
    value: str
    footprint: str
    lib_id: str
    at: Point


@dataclass(frozen=True)
class BoardPad:
    name: str
    net: str
    at: Point
    size_x: float = 0.0
    size_y: float = 0.0
    layers: tuple[str, ...] = ()


@dataclass(frozen=True)
class BoardFootprint:
    footprint: str
    reference: str
    value: str
    properties: dict[str, str]
    at: Point
    rotation_degrees: float
    pads: dict[str, BoardPad]


@dataclass(frozen=True)
class BoardTrack:
    net: str
    layer: str
    start: Point
    end: Point
    width: float = 0.0


@dataclass(frozen=True)
class BoardVia:
    net: str
    at: Point
    size: float = 0.0
    drill: float = 0.0


@dataclass(frozen=True)
class BoardModel:
    footprints: dict[str, BoardFootprint]
    tracks: list[BoardTrack]
    vias: list[BoardVia]
    outline_points: list[Point]
    zone_nets: frozenset[str]

    def outline_bbox(self) -> tuple[float, float, float, float] | None:
        if not self.outline_points:
            return None
        xs = [point.x for point in self.outline_points]
        ys = [point.y for point in self.outline_points]
        return min(xs), min(ys), max(xs), max(ys)

    def track_count_by_net(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for track in self.tracks:
            counts[track.net] = counts.get(track.net, 0) + 1
        return counts


def _tokenize_sexpr(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "()":
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            index += 1
            value_chars: list[str] = []
            while index < len(text):
                current = text[index]
                if current == "\\" and index + 1 < len(text):
                    value_chars.append(text[index + 1])
                    index += 2
                    continue
                if current == '"':
                    index += 1
                    break
                value_chars.append(current)
                index += 1
            tokens.append("".join(value_chars))
            continue
        start = index
        while index < len(text) and not text[index].isspace() and text[index] not in "()":
            index += 1
        tokens.append(text[start:index])
    return tokens


def parse_sexpr(text: str) -> SExpr:
    tokens = _tokenize_sexpr(text)
    stack: list[list[SExpr]] = []
    root: list[SExpr] | None = None
    for token in tokens:
        if token == "(":
            node: list[SExpr] = []
            if stack:
                stack[-1].append(node)
            stack.append(node)
            continue
        if token == ")":
            if not stack:
                raise ValueError("unexpected closing paren")
            root = stack.pop()
            continue
        if not stack:
            raise ValueError("unexpected atom outside root expression")
        stack[-1].append(token)
    if stack:
        raise ValueError("unterminated s-expression")
    if root is None:
        raise ValueError("empty s-expression")
    return root


def load_sexpr(path: Path) -> SExpr:
    return parse_sexpr(path.read_text(encoding="utf-8"))


def node_head(node: SExpr) -> str:
    if isinstance(node, list) and node and isinstance(node[0], str):
        return node[0]
    return ""


def children(node: SExpr, head: str) -> list[list[SExpr]]:
    if not isinstance(node, list):
        return []
    return [
        child
        for child in node[1:]
        if isinstance(child, list) and node_head(child) == head
    ]


def child(node: SExpr, head: str) -> list[SExpr] | None:
    for candidate in children(node, head):
        return candidate
    return None


def string_item(node: list[SExpr] | None, index: int, *, default: str = "") -> str:
    if node is None:
        return default
    if index < len(node) and isinstance(node[index], str):
        return node[index]
    return default


def point_from_node(node: list[SExpr] | None, *, start_index: int = 1) -> Point:
    if node is None:
        return Point(0.0, 0.0)
    return Point(
        float(string_item(node, start_index, default="0")),
        float(string_item(node, start_index + 1, default="0")),
    )


def float_item(node: list[SExpr] | None, index: int, *, default: float = 0.0) -> float:
    raw = string_item(node, index)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def property_value(node: list[SExpr], name: str) -> str:
    for prop in children(node, "property"):
        if string_item(prop, 1) == name:
            return string_item(prop, 2)
    return ""


def _symbol_instance_values(root: list[SExpr]) -> dict[str, str]:
    values: dict[str, str] = {}
    symbol_instances = child(root, "symbol_instances")
    if symbol_instances is None:
        return values
    for path in children(symbol_instances, "path"):
        reference = string_item(child(path, "reference"), 1)
        value = string_item(child(path, "value"), 1)
        if reference:
            values[reference] = value
    return values


def load_schematic_symbols(path: Path) -> dict[str, SchematicSymbol]:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("(kicad_sch"):
        root = parse_sexpr(text)
        if not isinstance(root, list) or node_head(root) != "kicad_sch":
            raise ValueError(f"{path} is not a KiCad schematic")
        instance_values = _symbol_instance_values(root)
        symbols: dict[str, SchematicSymbol] = {}
        for node in children(root, "symbol"):
            reference = property_value(node, "Reference")
            if not reference:
                continue
            at = point_from_node(child(node, "at"))
            value = property_value(node, "Value")
            symbols[reference] = SchematicSymbol(
                reference=reference,
                value=instance_values.get(reference, value),
                footprint=property_value(node, "Footprint"),
                lib_id=string_item(child(node, "lib_id"), 1),
                at=at,
            )
        return symbols
    return _load_legacy_schematic_symbols(text)


def _load_legacy_schematic_symbols(text: str) -> dict[str, SchematicSymbol]:
    symbols: dict[str, SchematicSymbol] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip() != "$Comp":
            index += 1
            continue

        block: list[str] = []
        index += 1
        while index < len(lines) and lines[index].strip() != "$EndComp":
            block.append(lines[index])
            index += 1
        index += 1

        lib_id = ""
        reference = ""
        value = ""
        footprint = ""
        at = Point(0.0, 0.0)
        for line in block:
            stripped = line.strip()
            if stripped.startswith("L "):
                parts = stripped.split(maxsplit=2)
                if len(parts) >= 3:
                    lib_id = parts[1]
                    reference = parts[2]
            elif stripped.startswith("P "):
                parts = stripped.split()
                if len(parts) >= 3:
                    at = Point(float(parts[1]), float(parts[2]))
            elif stripped.startswith("F 0 "):
                reference = _legacy_quoted_value(stripped) or reference
            elif stripped.startswith("F 1 "):
                value = _legacy_quoted_value(stripped)
            elif stripped.startswith("F 2 "):
                footprint = _legacy_quoted_value(stripped)

        if not reference or reference.startswith("#PWR"):
            continue
        symbols[reference] = SchematicSymbol(
            reference=reference,
            value=value,
            footprint=footprint,
            lib_id=lib_id,
            at=at,
        )
    return symbols


def _legacy_quoted_value(line: str) -> str:
    first_quote = line.find('"')
    if first_quote < 0:
        return ""
    second_quote = line.find('"', first_quote + 1)
    if second_quote < 0:
        return ""
    return line[first_quote + 1 : second_quote]


def load_board_model(path: Path) -> BoardModel:
    root = load_sexpr(path)
    if not isinstance(root, list) or node_head(root) != "kicad_pcb":
        raise ValueError(f"{path} is not a KiCad board")

    net_names = {
        int(string_item(net_node, 1, default="-1")): string_item(net_node, 2)
        for net_node in children(root, "net")
        if string_item(net_node, 1, default="-1").lstrip("-").isdigit()
    }

    footprints: dict[str, BoardFootprint] = {}
    for footprint_node in [*children(root, "footprint"), *children(root, "module")]:
        reference = ""
        value = ""
        properties = {
            string_item(prop_node, 1): string_item(prop_node, 2)
            for prop_node in children(footprint_node, "property")
            if string_item(prop_node, 1)
        }
        for text_node in children(footprint_node, "fp_text"):
            kind = string_item(text_node, 1)
            if kind == "reference":
                reference = string_item(text_node, 2)
            if kind == "value":
                value = string_item(text_node, 2)
        if not reference:
            reference = property_value(footprint_node, "Reference")
        if not value:
            value = property_value(footprint_node, "Value")
        if not reference:
            continue
        at_node = child(footprint_node, "at")
        footprint_at = point_from_node(at_node)
        pads: dict[str, BoardPad] = {}
        for pad_node in children(footprint_node, "pad"):
            pad_name = string_item(pad_node, 1)
            net_node = child(pad_node, "net")
            net_name = ""
            if net_node is not None:
                net_id = string_item(net_node, 1, default="-1")
                if net_id.lstrip("-").isdigit():
                    net_name = net_names.get(int(net_id), string_item(net_node, 2))
                else:
                    net_name = string_item(net_node, 2)
            pad_at = point_from_node(child(pad_node, "at"))
            size_node = child(pad_node, "size")
            layers_node = child(pad_node, "layers")
            pad_point = _transform_footprint_point(
                footprint_at=footprint_at,
                local_point=pad_at,
                rotation_degrees=float(string_item(at_node, 3, default="0")),
            )
            pads[pad_name] = BoardPad(
                name=pad_name,
                net=net_name,
                at=pad_point,
                size_x=float_item(size_node, 1, default=0.0),
                size_y=float_item(size_node, 2, default=0.0),
                layers=tuple(str(item) for item in (layers_node[1:] if layers_node else ()) if isinstance(item, str)),
            )
        footprints[reference] = BoardFootprint(
            footprint=string_item(footprint_node, 1),
            reference=reference,
            value=value,
            properties=properties,
            at=footprint_at,
            rotation_degrees=float(string_item(at_node, 3, default="0")),
            pads=pads,
        )

    tracks: list[BoardTrack] = []
    for segment_node in children(root, "segment"):
        net_id = string_item(child(segment_node, "net"), 1)
        net_name = ""
        if net_id.lstrip("-").isdigit():
            net_name = net_names.get(int(net_id), "")
        tracks.append(
            BoardTrack(
                net=net_name,
                layer=string_item(child(segment_node, "layer"), 1),
                start=point_from_node(child(segment_node, "start")),
                end=point_from_node(child(segment_node, "end")),
                width=float_item(child(segment_node, "width"), 1, default=0.25),
            )
        )

    vias: list[BoardVia] = []
    for via_node in children(root, "via"):
        net_id = string_item(child(via_node, "net"), 1)
        net_name = ""
        if net_id.lstrip("-").isdigit():
            net_name = net_names.get(int(net_id), "")
        vias.append(
            BoardVia(
                net=net_name,
                at=point_from_node(child(via_node, "at")),
                size=float_item(child(via_node, "size"), 1, default=0.6),
                drill=float_item(child(via_node, "drill"), 1, default=0.3),
            )
        )

    outline_points: list[Point] = []
    for shape_head in ("gr_line", "gr_arc", "gr_rect", "gr_circle"):
        for shape_node in children(root, shape_head):
            layer_name = string_item(child(shape_node, "layer"), 1)
            if layer_name != "Edge.Cuts":
                continue
            outline_points.extend(_outline_points_from_shape(shape_node, shape_head))

    zone_nets = frozenset(_zone_net_names(root, net_names))

    return BoardModel(
        footprints=footprints,
        tracks=tracks,
        vias=vias,
        outline_points=outline_points,
        zone_nets=zone_nets,
    )


def _transform_footprint_point(
    *,
    footprint_at: Point,
    local_point: Point,
    rotation_degrees: float,
) -> Point:
    if abs(rotation_degrees) <= 1e-6:
        return Point(footprint_at.x + local_point.x, footprint_at.y + local_point.y)
    radians = math.radians(-rotation_degrees)
    cos_theta = math.cos(radians)
    sin_theta = math.sin(radians)
    rotated_x = (local_point.x * cos_theta) - (local_point.y * sin_theta)
    rotated_y = (local_point.x * sin_theta) + (local_point.y * cos_theta)
    return Point(footprint_at.x + rotated_x, footprint_at.y + rotated_y)


def _outline_points_from_shape(node: list[SExpr], head: str) -> list[Point]:
    if head == "gr_circle":
        center = point_from_node(child(node, "center"))
        end = point_from_node(child(node, "end"))
        radius = math.hypot(center.x - end.x, center.y - end.y)
        return [
            Point(center.x - radius, center.y - radius),
            Point(center.x + radius, center.y + radius),
        ]
    return [
        point_from_node(child(node, "start")),
        point_from_node(child(node, "end")),
    ]


def _zone_net_names(root: list[SExpr], net_names: dict[int, str]) -> list[str]:
    zone_nets: list[str] = []
    for zone_node in children(root, "zone"):
        net_name = ""
        net_name_node = child(zone_node, "net_name")
        if net_name_node is not None:
            net_name = string_item(net_name_node, 1)
        if not net_name:
            net_node = child(zone_node, "net")
            if net_node is not None:
                net_id = string_item(net_node, 1, default="-1")
                if net_id.lstrip("-").isdigit():
                    net_name = net_names.get(int(net_id), string_item(net_node, 2))
                else:
                    net_name = string_item(net_node, 2)
        if net_name:
            zone_nets.append(net_name)
    return zone_nets


def nearly_equal(left: float, right: float, tolerance: float) -> bool:
    return abs(left - right) <= tolerance


def require_keys(mapping: dict[str, object], expected: Iterable[str], *, label: str) -> list[str]:
    missing = [key for key in expected if key not in mapping]
    if missing:
        return [f"missing {label}: {', '.join(missing)}"]
    return []
