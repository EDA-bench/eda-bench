from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tasks.kicad_common import (
    BoardFootprint,
    BoardModel,
    Point,
)
from tasks.io_simulation_oracles import evaluate_with_io_simulation_oracle
from tasks.source_backed_tasks import SourceBackedTaskSpec
from tasks.specs import TaskEvaluation, TaskSpec

BOUNDARY_FOOTPRINT_TOKENS = (
    "AUDIO",
    "BARREL",
    "BAT",
    "BNC",
    "BUTTON",
    "CARD",
    "COAX",
    "CONN",
    "CONNECTOR",
    "ETH",
    "FAN",
    "FFC",
    "FPC",
    "GPIO",
    "HAT",
    "HEADER",
    "HDMI",
    "JST",
    "MICROSD",
    "M.2",
    "M2",
    "PCIE",
    "PINHEADER",
    "PUSH",
    "RJ",
    "SAO",
    "SMA",
    "SOCKET",
    "SWITCH",
    "TERMINAL",
    "UART",
    "USB",
    "UFL",
)
BOUNDARY_REFERENCE_PREFIXES = ("CN", "CON", "J", "M", "P", "SW", "X")
NON_BOUNDARY_REFERENCE_PREFIXES = ("#", "D", "FID", "G***", "H", "MH", "MK", "MP", "NT", "TP")
POWER_ROLE_TOKENS: tuple[tuple[str, str], ...] = (
    ("24V", "power_24v"),
    ("12V", "power_12v"),
    ("9V", "power_9v"),
    ("5V", "power_5v"),
    ("VBUS", "power_5v"),
    ("VSYS", "power_5v"),
    ("V_USB", "power_5v"),
    ("USB_VBUS", "power_5v"),
    ("3V8", "power_3v8"),
    ("3V6", "power_3v6"),
    ("3V3", "power_3v3"),
    ("3.3V", "power_3v3"),
    ("2V8", "power_2v8"),
    ("2V5", "power_2v5"),
    ("2V1", "power_2v1"),
    ("1V8", "power_1v8"),
    ("1.8V", "power_1v8"),
    ("1V2", "power_1v2"),
    ("1V1", "power_1v1"),
    ("VCC", "power_vcc"),
    ("VDD", "power_vdd"),
    ("VDDA", "power_vdda"),
    ("VBAT", "power_battery"),
    ("V_BAT", "power_battery"),
    ("BAT", "power_battery"),
)

MAX_SPICE_PORTS = 32
MAX_SPICE_PRIMITIVES = 256
SPICE_PAD_RESISTANCE_OHMS = 1e-3
SPICE_DEFAULT_CONDUCTIVE_PASSIVE_OHMS = 0.05
SPICE_LEAK_RESISTANCE_OHMS = 1e12


@dataclass(frozen=True)
class BoundaryPad:
    pad_name: str
    net: str
    role: str


@dataclass(frozen=True)
class BoundaryRef:
    reference: str
    value: str
    footprint: str
    pads: tuple[BoundaryPad, ...]


@dataclass(frozen=True)
class BoundaryNetGroup:
    role: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class ExternalPadNet:
    reference: str
    pad_name: str
    net: str
    role: str

    @property
    def member(self) -> str:
        return f"{self.reference}.{self.pad_name}"


@dataclass(frozen=True)
class SpicePort:
    member: str
    role: str
    net: str
    node: str


@dataclass(frozen=True)
class SpicePrimitive:
    reference: str
    kind: str
    value: str
    left_net: str
    right_net: str
    left_node: str
    right_node: str
    resistance_ohms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "kind": self.kind,
            "value": self.value,
            "left_net": self.left_net,
            "right_net": self.right_net,
            "left_node": self.left_node,
            "right_node": self.right_node,
            "resistance_ohms": self.resistance_ohms,
        }


@dataclass(frozen=True)
class RealizedCopperGraph:
    pad_nodes: dict[str, str]
    net_nodes: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class SpiceSimulationSignature:
    ports: tuple[SpicePort, ...]
    primitives: tuple[SpicePrimitive, ...]
    currents: tuple[tuple[str, str, float], ...]
    simulated: bool
    error: str
    netlist_path: str
    output_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ports": [
                {
                    "member": port.member,
                    "role": port.role,
                    "net": port.net,
                    "node": port.node,
                }
                for port in self.ports
            ],
            "primitive_count": len(self.primitives),
            "primitive_summary": dict(sorted(Counter(primitive.kind for primitive in self.primitives).items())),
            "simulated": self.simulated,
            "error": self.error,
            "netlist_path": self.netlist_path,
            "output_path": self.output_path,
            "current_count": len(self.currents),
        }


@dataclass(frozen=True)
class BoardExternalIoSignature:
    boundary_refs: tuple[BoundaryRef, ...]
    net_groups: tuple[BoundaryNetGroup, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_refs": [
                {
                    "reference": ref.reference,
                    "value": ref.value,
                    "footprint": ref.footprint,
                    "pads": [
                        {
                            "pad_name": pad.pad_name,
                            "net": pad.net,
                            "role": pad.role,
                        }
                        for pad in ref.pads
                    ],
                }
                for ref in self.boundary_refs
            ],
            "net_groups": [
                {
                    "role": group.role,
                    "members": list(group.members),
                }
                for group in self.net_groups
            ],
        }


def _natural_sort_key(value: str) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", value)
    key: list[Any] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return tuple(key)


def _norm(value: str) -> str:
    return str(value or "").upper().replace(" ", "")


def _is_ground_net(net_name: str) -> bool:
    normalized = _norm(net_name)
    return normalized in {"0", "AGND", "DGND", "EARTH", "GND", "GNDA", "GNDD", "PGND", "SHIELD"} or normalized.endswith("GND")


def _net_role(net_name: str) -> str:
    normalized = _norm(net_name)
    if not normalized or normalized.startswith("UNCONNECTED"):
        return "unconnected"
    if _is_ground_net(normalized):
        return "ground"
    for token, role in POWER_ROLE_TOKENS:
        if token in normalized:
            return role
    return "signal"


def _is_boundary_footprint(reference: str, footprint: BoardFootprint) -> bool:
    if reference.startswith(NON_BOUNDARY_REFERENCE_PREFIXES):
        return False
    normalized_value = _norm(footprint.value)
    normalized_footprint = _norm(footprint.footprint)
    if any(token in normalized_value or token in normalized_footprint for token in ("ESD", "LED", "LOGO", "MOUNTINGHOLE", "NETTIE", "TESTPOINT", "TVS")):
        return False
    if _reference_prefix(reference) == "K" and len(footprint.pads) >= 2:
        return True
    if reference.startswith(BOUNDARY_REFERENCE_PREFIXES):
        return True
    if _reference_prefix(reference) in {"IC", "U"}:
        return False
    return any(token in normalized_value or token in normalized_footprint for token in BOUNDARY_FOOTPRINT_TOKENS)


def _boundary_references(board: BoardModel) -> tuple[str, ...]:
    refs = [
        reference
        for reference, footprint in board.footprints.items()
        if footprint.pads and _is_boundary_footprint(reference, footprint)
    ]
    return tuple(sorted(refs, key=_natural_sort_key))


def build_external_io_signature(board: BoardModel) -> BoardExternalIoSignature:
    boundary_refs = _boundary_references(board)
    ref_signatures: list[BoundaryRef] = []
    selected_pad_members: dict[str, list[str]] = {}
    selected_net_roles: dict[str, str] = {}

    for reference in boundary_refs:
        footprint = board.footprints[reference]
        pads: list[BoundaryPad] = []
        for pad_name, pad in sorted(footprint.pads.items(), key=lambda item: _natural_sort_key(item[0])):
            role = _net_role(pad.net)
            pads.append(BoundaryPad(pad_name=pad_name, net=pad.net, role=role))
            if pad.net and role != "unconnected":
                selected_pad_members.setdefault(pad.net, []).append(f"{reference}.{pad_name}")
                selected_net_roles.setdefault(pad.net, role)
        ref_signatures.append(
            BoundaryRef(
                reference=reference,
                value=footprint.value,
                footprint=footprint.footprint,
                pads=tuple(pads),
            )
        )

    groups: list[BoundaryNetGroup] = []
    for net_name, members in selected_pad_members.items():
        if len(members) < 2:
            continue
        groups.append(
            BoundaryNetGroup(
                role=selected_net_roles[net_name],
                members=tuple(sorted(members, key=_natural_sort_key)),
            )
        )

    groups.sort(key=lambda group: (group.role, group.members))
    return BoardExternalIoSignature(
        boundary_refs=tuple(ref_signatures),
        net_groups=tuple(groups),
    )


def external_pad_nets(board: BoardModel) -> tuple[ExternalPadNet, ...]:
    pads: list[ExternalPadNet] = []
    for reference in _boundary_references(board):
        footprint = board.footprints[reference]
        for pad_name, pad in sorted(footprint.pads.items(), key=lambda item: _natural_sort_key(item[0])):
            pads.append(
                ExternalPadNet(
                    reference=reference,
                    pad_name=pad_name,
                    net=pad.net,
                    role=_net_role(pad.net),
                )
            )
    return tuple(pads)


def _ref_map(signature: BoardExternalIoSignature) -> dict[str, BoundaryRef]:
    return {ref.reference: ref for ref in signature.boundary_refs}


def compare_external_io(
    submission: BoardExternalIoSignature,
    reference: BoardExternalIoSignature,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    submission_refs = tuple(ref.reference for ref in submission.boundary_refs)
    reference_refs = tuple(ref.reference for ref in reference.boundary_refs)
    checks.append(
        {
            "name": "boundary_references",
            "passed": submission_refs == reference_refs,
            "detail": ""
            if submission_refs == reference_refs
            else f"got {list(submission_refs)}, expected {list(reference_refs)}",
        }
    )

    submission_map = _ref_map(submission)
    reference_map = _ref_map(reference)
    for reference_name in sorted(set(submission_map) | set(reference_map), key=_natural_sort_key):
        submission_ref = submission_map.get(reference_name)
        reference_ref = reference_map.get(reference_name)
        if submission_ref is None or reference_ref is None:
            continue

        submission_pad_names = tuple(pad.pad_name for pad in submission_ref.pads)
        reference_pad_names = tuple(pad.pad_name for pad in reference_ref.pads)
        checks.append(
            {
                "name": f"{reference_name}.pad_names",
                "passed": submission_pad_names == reference_pad_names,
                "detail": ""
                if submission_pad_names == reference_pad_names
                else f"got {list(submission_pad_names)}, expected {list(reference_pad_names)}",
            }
        )

        submission_pad_roles = tuple((pad.pad_name, pad.role) for pad in submission_ref.pads)
        reference_pad_roles = tuple((pad.pad_name, pad.role) for pad in reference_ref.pads)
        checks.append(
            {
                "name": f"{reference_name}.pad_roles",
                "passed": submission_pad_roles == reference_pad_roles,
                "detail": ""
                if submission_pad_roles == reference_pad_roles
                else f"got {list(submission_pad_roles)}, expected {list(reference_pad_roles)}",
            }
        )

    submission_groups = tuple((group.role, group.members) for group in submission.net_groups)
    reference_groups = tuple((group.role, group.members) for group in reference.net_groups)
    checks.append(
        {
            "name": "boundary_net_groups",
            "passed": submission_groups == reference_groups,
            "detail": ""
            if submission_groups == reference_groups
            else f"got {list(submission_groups)}, expected {list(reference_groups)}",
        }
    )
    return checks


def _loose_token(value: str) -> str:
    normalized = _norm(value)
    normalized = normalized.replace("_", "").replace("-", "").replace(".", "")
    return re.sub(r"[^A-Z0-9]+", "", normalized)


def _footprint_family(value: str) -> str:
    normalized = _norm(value)
    if ":" in normalized:
        normalized = normalized.split(":", 1)[1]
    normalized = normalized.replace("_", "-")
    return re.split(r"[-_/]", normalized)[0]


def _counter_f1(submission: Counter[tuple[Any, ...]], reference: Counter[tuple[Any, ...]]) -> float:
    if not submission and not reference:
        return 1.0
    if not submission or not reference:
        return 0.0
    overlap = sum(min(submission[key], reference[key]) for key in set(submission) | set(reference))
    precision = overlap / max(1, sum(submission.values()))
    recall = overlap / max(1, sum(reference.values()))
    if precision + recall <= 0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


def _ratio_score(submission: int | float, reference: int | float) -> float:
    submission_value = float(submission)
    reference_value = float(reference)
    if reference_value <= 0:
        return 1.0 if submission_value <= 0 else 0.0
    return max(0.0, 1.0 - min(1.0, abs(submission_value - reference_value) / reference_value))


def _boundary_counter(signature: BoardExternalIoSignature) -> Counter[tuple[Any, ...]]:
    return Counter(
        (
            _loose_token(ref.value),
            _footprint_family(ref.footprint),
            tuple(pad.role for pad in ref.pads),
        )
        for ref in signature.boundary_refs
    )


def _boundary_role_counter(signature: BoardExternalIoSignature) -> Counter[tuple[Any, ...]]:
    counter: Counter[tuple[Any, ...]] = Counter()
    for ref in signature.boundary_refs:
        for pad in ref.pads:
            counter[(pad.role,)] += 1
    return counter


def _boundary_pad_net_label_counter(signature: BoardExternalIoSignature) -> Counter[tuple[Any, ...]]:
    return Counter(
        (
            ref.reference,
            pad.pad_name,
            pad.role,
            _loose_token(pad.net),
        )
        for ref in signature.boundary_refs
        for pad in ref.pads
    )


def _boundary_topology_counter(signature: BoardExternalIoSignature) -> Counter[tuple[Any, ...]]:
    return Counter((group.role, len(group.members)) for group in signature.net_groups)


def _signature_pad_roles(signature: BoardExternalIoSignature) -> dict[str, str]:
    return {
        f"{ref.reference}.{pad.pad_name}": pad.role
        for ref in signature.boundary_refs
        for pad in ref.pads
    }


def _external_stimulus_response_counter(
    signature: BoardExternalIoSignature,
) -> Counter[tuple[Any, ...]]:
    pad_roles = _signature_pad_roles(signature)
    observed_by_member: dict[str, list[str]] = {member: [] for member in pad_roles}
    for group in signature.net_groups:
        for member in group.members:
            observed_by_member.setdefault(member, [])
            observed_by_member[member].extend(
                pad_roles[other]
                for other in group.members
                if other != member and other in pad_roles
            )
    counter: Counter[tuple[Any, ...]] = Counter()
    for member, driver_role in pad_roles.items():
        observed_roles = Counter(observed_by_member.get(member, []))
        response = tuple(sorted((role, count) for role, count in observed_roles.items()))
        counter[(driver_role, response)] += 1
    return counter


def _external_exact_pair_counter(signature: BoardExternalIoSignature) -> Counter[tuple[Any, ...]]:
    counter: Counter[tuple[Any, ...]] = Counter()
    for group in signature.net_groups:
        members = tuple(sorted(group.members, key=_natural_sort_key))
        for left_index, left in enumerate(members):
            for right in members[left_index + 1 :]:
                counter[(group.role, left, right)] += 1
    return counter


def _external_role_pair_counter(signature: BoardExternalIoSignature) -> Counter[tuple[Any, ...]]:
    pad_roles = _signature_pad_roles(signature)
    counter: Counter[tuple[Any, ...]] = Counter()
    for group in signature.net_groups:
        members = tuple(sorted(group.members, key=_natural_sort_key))
        for left_index, left in enumerate(members):
            for right in members[left_index + 1 :]:
                role_pair = tuple(sorted((pad_roles.get(left, ""), pad_roles.get(right, ""))))
                counter[(group.role, *role_pair)] += 1
    return counter


def _spread_select(items: list[ExternalPadNet], count: int) -> list[ExternalPadNet]:
    if count <= 0:
        return []
    if len(items) <= count:
        return list(items)
    if count == 1:
        return [items[0]]
    indexes = {
        round(index * (len(items) - 1) / (count - 1))
        for index in range(count)
    }
    return [items[index] for index in sorted(indexes)]


def _selected_spice_pad_nets(board: BoardModel, *, max_ports: int = MAX_SPICE_PORTS) -> tuple[ExternalPadNet, ...]:
    pads = [
        pad
        for pad in external_pad_nets(board)
        if pad.net and pad.role != "unconnected"
    ]
    pads.sort(key=lambda pad: (_natural_sort_key(pad.reference), _natural_sort_key(pad.pad_name), pad.net))
    if len(pads) <= max_ports:
        return tuple(pads)

    selected: list[ExternalPadNet] = []
    selected_members: set[str] = set()

    pads_by_net: dict[str, list[ExternalPadNet]] = {}
    for pad in pads:
        pads_by_net.setdefault(pad.net, []).append(pad)
    multi_member_signal_nets = [
        net
        for net, net_pads in pads_by_net.items()
        if _net_role(net) == "signal" and len({pad.reference for pad in net_pads}) >= 2
    ]
    multi_member_signal_nets.sort(key=_natural_sort_key)
    for net in _spread_select(multi_member_signal_nets, min(8, max_ports // 4)):
        for pad in _spread_select(pads_by_net[net], min(2, max_ports - len(selected))):
            if pad.member not in selected_members:
                selected.append(pad)
                selected_members.add(pad.member)
        if len(selected) >= max_ports:
            break

    role_budgets = (
        ("ground", 6),
        ("power", 10),
        ("signal", 12),
    )
    for role_name, budget in role_budgets:
        if role_name == "power":
            candidates = [pad for pad in pads if pad.role.startswith("power_")]
        else:
            candidates = [pad for pad in pads if pad.role == role_name]
        for pad in _spread_select(candidates, min(budget, max_ports - len(selected))):
            if pad.member not in selected_members:
                selected.append(pad)
                selected_members.add(pad.member)
        if len(selected) >= max_ports:
            break

    remaining = [pad for pad in pads if pad.member not in selected_members]
    for pad in _spread_select(remaining, max_ports - len(selected)):
        if pad.member not in selected_members:
            selected.append(pad)
            selected_members.add(pad.member)

    selected.sort(key=lambda pad: (_natural_sort_key(pad.reference), _natural_sort_key(pad.pad_name), pad.net))
    return tuple(selected[:max_ports])


class _DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: str) -> str:
        self.add(item)
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if _natural_sort_key(right_root) < _natural_sort_key(left_root):
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root


def _point_key(point: Point) -> tuple[int, int]:
    return (round(point.x * 1000), round(point.y * 1000))


def _point_segment_distance_mm(point: Point, start: Point, end: Point) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.hypot(point.x - start.x, point.y - start.y)
    t = ((point.x - start.x) * dx + (point.y - start.y) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    closest_x = start.x + t * dx
    closest_y = start.y + t * dy
    return math.hypot(point.x - closest_x, point.y - closest_y)


def _route_node(net: str, layer: str, point: Point) -> str:
    x, y = _point_key(point)
    return f"route:{net}:{layer}:{x}:{y}"


def _pad_member(reference: str, pad_name: str) -> str:
    return f"{reference}.{pad_name}"


def _realized_copper_graph(board: BoardModel, *, connect_logical_nets: bool = False) -> RealizedCopperGraph:
    dsu = _DisjointSet()
    pad_nodes: dict[str, str] = {}
    pads_by_net: dict[str, list[str]] = {}
    route_nodes_by_net: dict[str, list[str]] = {}
    route_nodes_by_net_point: dict[tuple[str, tuple[int, int]], list[str]] = {}
    route_segments_by_net: dict[str, list[tuple[str, str, Point, Point, float]]] = {}

    for reference, footprint in board.footprints.items():
        for pad_name, pad in footprint.pads.items():
            if not pad.net or _net_role(pad.net) == "unconnected":
                continue
            member = _pad_member(reference, pad_name)
            node = f"pad:{member}"
            dsu.add(node)
            pad_nodes[member] = node
            pads_by_net.setdefault(pad.net, []).append(node)

    for index, track in enumerate(board.tracks):
        if not track.net or _net_role(track.net) == "unconnected":
            continue
        start_node = _route_node(track.net, track.layer, track.start)
        end_node = _route_node(track.net, track.layer, track.end)
        dsu.union(start_node, end_node)
        route_segments_by_net.setdefault(track.net, []).append(
            (start_node, end_node, track.start, track.end, max(float(track.width or 0.25), 0.05))
        )
        for node, point in ((start_node, track.start), (end_node, track.end)):
            route_nodes_by_net.setdefault(track.net, []).append(node)
            route_nodes_by_net_point.setdefault((track.net, _point_key(point)), []).append(node)

    for via in board.vias:
        if not via.net or _net_role(via.net) == "unconnected":
            continue
        nodes = route_nodes_by_net_point.get((via.net, _point_key(via.at)), [])
        if len(nodes) >= 2:
            first = nodes[0]
            for node in nodes[1:]:
                dsu.union(first, node)

    for reference, footprint in board.footprints.items():
        for pad_name, pad in footprint.pads.items():
            member = _pad_member(reference, pad_name)
            pad_node = pad_nodes.get(member)
            if pad_node is None:
                continue
            for route_node in route_nodes_by_net_point.get((pad.net, _point_key(pad.at)), []):
                dsu.union(pad_node, route_node)
            for start_node, end_node, start, end, width in route_segments_by_net.get(pad.net, []):
                pad_radius = 0.5 * max(float(getattr(pad, "size_x", 0.0) or 0.0), float(getattr(pad, "size_y", 0.0) or 0.0))
                contact_tolerance = max(0.20, (width * 0.5) + pad_radius + 0.03)
                if _point_segment_distance_mm(pad.at, start, end) <= contact_tolerance:
                    dsu.union(pad_node, start_node)
                    dsu.union(pad_node, end_node)

    if connect_logical_nets:
        for net, nodes in pads_by_net.items():
            if len(nodes) < 2:
                continue
            first = nodes[0]
            for node in nodes[1:]:
                dsu.union(first, node)
            for route_node in route_nodes_by_net.get(net, []):
                dsu.union(first, route_node)

    for net in board.zone_nets:
        nodes = [*pads_by_net.get(net, []), *route_nodes_by_net.get(net, [])]
        if len(nodes) >= 2:
            first = nodes[0]
            for node in nodes[1:]:
                dsu.union(first, node)

    root_to_realized: dict[str, str] = {}
    resolved_pad_nodes: dict[str, str] = {}
    for member, node in sorted(pad_nodes.items(), key=lambda item: _natural_sort_key(item[0])):
        root = dsu.find(node)
        root_to_realized.setdefault(root, f"rc{len(root_to_realized)}")
        resolved_pad_nodes[member] = root_to_realized[root]

    net_nodes: dict[str, list[str]] = {}
    for member, realized_node in resolved_pad_nodes.items():
        reference, pad_name = member.split(".", 1)
        pad = board.footprints[reference].pads[pad_name]
        net_nodes.setdefault(pad.net, []).append(realized_node)

    return RealizedCopperGraph(
        pad_nodes=resolved_pad_nodes,
        net_nodes={
            net: tuple(sorted(set(nodes), key=_natural_sort_key))
            for net, nodes in net_nodes.items()
        },
    )


def _reference_prefix(reference: str) -> str:
    match = re.match(r"^[A-Za-z]+", reference or "")
    return match.group(0).upper() if match else ""


def _dnp_like(value: str) -> bool:
    normalized = _loose_token(value)
    return normalized in {"DNI", "DNF", "DNP", "NC", "NOPOP", "NP", "OPEN"}


def _parse_resistance_ohms(value: str) -> float | None:
    if _dnp_like(value):
        return None
    normalized = _norm(value)
    normalized = (
        normalized.replace("OHMS", "R")
        .replace("OHM", "R")
        .replace("Ω", "R")
        .replace(",", ".")
    )
    normalized = re.sub(r"\([^)]*\)", "", normalized)
    normalized = re.sub(r"[^0-9A-Z.+-]", "", normalized)
    normalized = re.sub(r"([KMGT])R$", r"\1", normalized)
    if not normalized:
        return None

    engineering_match = re.search(r"(\d+)(R|K|M)(\d+)$", normalized)
    if engineering_match:
        whole, suffix, fraction = engineering_match.groups()
        multiplier = {"R": 1.0, "K": 1e3, "M": 1e6}[suffix]
        return max(1e-3, float(f"{whole}.{fraction}") * multiplier)

    suffix_match = re.search(r"([-+]?\d+(?:\.\d+)?)(MEG|[RKMGT])?$", normalized)
    if suffix_match is None:
        tolerance_match = re.search(r"([-+]?\d+(?:\.\d+)?)(MEG|[RKMGT])\d+$", normalized)
        if tolerance_match is None:
            return None
        number, suffix = tolerance_match.groups()
    else:
        number, suffix = suffix_match.groups()
    multiplier = {
        None: 1.0,
        "R": 1.0,
        "K": 1e3,
        "M": 1e6,
        "MEG": 1e6,
        "G": 1e9,
        "T": 1e12,
    }.get(suffix)
    if multiplier is None:
        return None
    return max(1e-3, float(number) * multiplier)


def _conductive_passive_resistance(reference: str, value: str) -> tuple[str, float] | None:
    prefix = _reference_prefix(reference)
    if prefix == "R":
        resistance = _parse_resistance_ohms(value)
        if resistance is None:
            return None
        return "resistor", resistance
    if prefix in {"F", "FB", "L", "NT"}:
        if _dnp_like(value):
            return None
        resistance = _parse_resistance_ohms(value)
        return "conductive_passive", resistance or SPICE_DEFAULT_CONDUCTIVE_PASSIVE_OHMS
    return None


def _spice_conductive_primitives(
    board: BoardModel,
    realized_graph: RealizedCopperGraph,
) -> tuple[SpicePrimitive, ...]:
    primitives: list[SpicePrimitive] = []
    for reference, footprint in sorted(board.footprints.items(), key=lambda item: _natural_sort_key(item[0])):
        passive = _conductive_passive_resistance(reference, footprint.value)
        if passive is None:
            continue
        connected_pads = [pad for pad in footprint.pads.values() if pad.net and _net_role(pad.net) != "unconnected"]
        unique_nets = tuple(dict.fromkeys(pad.net for pad in connected_pads))
        if len(unique_nets) != 2:
            continue
        left_pad = next(pad for pad in connected_pads if pad.net == unique_nets[0])
        right_pad = next(pad for pad in connected_pads if pad.net == unique_nets[1])
        left_node = realized_graph.pad_nodes.get(_pad_member(reference, left_pad.name))
        right_node = realized_graph.pad_nodes.get(_pad_member(reference, right_pad.name))
        if left_node is None or right_node is None or left_node == right_node:
            continue
        kind, resistance = passive
        primitives.append(
            SpicePrimitive(
                reference=reference,
                kind=kind,
                value=footprint.value,
                left_net=unique_nets[0],
                right_net=unique_nets[1],
                left_node=left_node,
                right_node=right_node,
                resistance_ohms=resistance,
            )
        )
    return tuple(primitives)


def _selected_spice_primitives(
    board: BoardModel,
    ports: tuple[SpicePort, ...],
    realized_graph: RealizedCopperGraph,
    *,
    max_primitives: int = MAX_SPICE_PRIMITIVES,
) -> tuple[SpicePrimitive, ...]:
    primitives = _spice_conductive_primitives(board, realized_graph)
    frontier = {port.node for port in ports if port.node}
    if not frontier:
        return ()
    selected: list[SpicePrimitive] = []
    selected_refs: set[str] = set()
    reachable = set(frontier)
    while len(selected) < max_primitives:
        added = False
        for primitive in primitives:
            if primitive.reference in selected_refs:
                continue
            if primitive.left_node not in reachable and primitive.right_node not in reachable:
                continue
            selected.append(primitive)
            selected_refs.add(primitive.reference)
            reachable.add(primitive.left_node)
            reachable.add(primitive.right_node)
            added = True
            if len(selected) >= max_primitives:
                break
        if not added:
            break
    return tuple(selected)


def _spice_net_name(index: int) -> str:
    return f"n{index}"


def _write_spice_boundary_response_netlist(
    board: BoardModel,
    path: Path,
) -> tuple[tuple[SpicePort, ...], tuple[SpicePrimitive, ...]]:
    realized_graph = _realized_copper_graph(board)
    selected_pads = _selected_spice_pad_nets(board)
    ports = tuple(
        SpicePort(
            member=pad.member,
            role=pad.role,
            net=pad.net,
            node=realized_graph.pad_nodes.get(pad.member, f"isolated:{pad.member}"),
        )
        for pad in selected_pads
    )
    primitives = _selected_spice_primitives(board, ports, realized_graph)
    realized_nodes = sorted(
        {
            *{port.node for port in ports if port.node},
            *{primitive.left_node for primitive in primitives},
            *{primitive.right_node for primitive in primitives},
        },
        key=_natural_sort_key,
    )
    spice_nodes = {node: _spice_net_name(index) for index, node in enumerate(realized_nodes)}
    lines = [
        "* EDA Bench external boundary-response simulation",
        "* Boundary pads are driven as SPICE ports on realized copper nodes.",
        "* Simple conductive passives connected to realized boundary copper are modeled.",
        "* Hidden IC models are intentionally not used.",
        ".option noacct",
    ]
    for index, port in enumerate(ports):
        node = spice_nodes[port.node]
        lines.append(f"RPAD{index} p{index} {node} {SPICE_PAD_RESISTANCE_OHMS:.9g}")
        lines.append(f"VPORT{index} p{index} 0 0")
    for index, primitive in enumerate(primitives):
        lines.append(
            f"RPRIM{index} {spice_nodes[primitive.left_node]} {spice_nodes[primitive.right_node]} {primitive.resistance_ohms:.9g}"
        )
    for index, node in enumerate(realized_nodes):
        lines.append(f"RLEAK{index} {spice_nodes[node]} 0 {SPICE_LEAK_RESISTANCE_OHMS:.9g}")
    lines.extend(
        [
            ".control",
            "set noaskquit",
        ]
    )
    current_terms = " ".join(f"@vport{index}[i]" for index in range(len(ports)))
    for driver_index in range(len(ports)):
        lines.append(f"echo EDA_BENCH_DRIVER {driver_index}")
        lines.append(f"alter VPORT{driver_index} = 1")
        lines.append("op")
        lines.append(f"print {current_terms}")
        lines.append(f"alter VPORT{driver_index} = 0")
    lines.extend(
        [
            "quit",
            ".endc",
            ".end",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ports, primitives


def _parse_spice_port_currents(output: str, ports: tuple[SpicePort, ...]) -> tuple[tuple[str, str, float], ...]:
    current_driver: int | None = None
    current_re = re.compile(r"@vport(\d+)\[i\]\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
    currents: list[tuple[str, str, float]] = []
    for line in output.splitlines():
        if line.startswith("EDA_BENCH_DRIVER"):
            parts = line.split()
            current_driver = int(parts[-1])
            continue
        if current_driver is None:
            continue
        match = current_re.search(line)
        if match is None:
            continue
        observed_index = int(match.group(1))
        if current_driver >= len(ports) or observed_index >= len(ports):
            continue
        currents.append(
            (
                ports[current_driver].member,
                ports[observed_index].member,
                float(match.group(2)),
            )
        )
    return tuple(currents)


def _simulate_external_spice_signature(
    board: BoardModel,
    work_dir: Path,
    *,
    label: str,
) -> SpiceSimulationSignature:
    spice_dir = work_dir / "spice"
    spice_dir.mkdir(parents=True, exist_ok=True)
    netlist_path = spice_dir / f"{label}.cir"
    output_path = spice_dir / f"{label}.log"
    ports, primitives = _write_spice_boundary_response_netlist(board, netlist_path)
    if not ports:
        output_path.write_text("No connected external ports selected.\n", encoding="utf-8")
        return SpiceSimulationSignature(
            ports=ports,
            primitives=primitives,
            currents=(),
            simulated=True,
            error="",
            netlist_path=str(netlist_path),
            output_path=str(output_path),
        )
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        message = "ngspice not found on PATH"
        output_path.write_text(message + "\n", encoding="utf-8")
        return SpiceSimulationSignature(
            ports=ports,
            primitives=primitives,
            currents=(),
            simulated=False,
            error=message,
            netlist_path=str(netlist_path),
            output_path=str(output_path),
        )
    try:
        with tempfile.TemporaryDirectory(prefix="eda_spice_") as tmp:
            proc = subprocess.run(
                [ngspice, "-b", "-n", str(netlist_path)],
                cwd=tmp,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(str(part) for part in (exc.stdout, exc.stderr) if part)
        message = "ngspice timed out after 30 seconds"
        output_path.write_text(f"{message}\n{output}", encoding="utf-8")
        return SpiceSimulationSignature(
            ports=ports,
            primitives=primitives,
            currents=(),
            simulated=False,
            error=message,
            netlist_path=str(netlist_path),
            output_path=str(output_path),
        )
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    output_path.write_text(output, encoding="utf-8")
    if proc.returncode != 0:
        return SpiceSimulationSignature(
            ports=ports,
            primitives=primitives,
            currents=(),
            simulated=False,
            error=f"ngspice exited with {proc.returncode}",
            netlist_path=str(netlist_path),
            output_path=str(output_path),
        )
    currents = _parse_spice_port_currents(output, ports)
    expected_current_count = len(ports) * len(ports)
    if len(currents) != expected_current_count:
        return SpiceSimulationSignature(
            ports=ports,
            primitives=primitives,
            currents=currents,
            simulated=False,
            error=f"parsed {len(currents)} of {expected_current_count} expected SPICE port currents",
            netlist_path=str(netlist_path),
            output_path=str(output_path),
        )
    return SpiceSimulationSignature(
        ports=ports,
        primitives=primitives,
        currents=currents,
        simulated=True,
        error="",
        netlist_path=str(netlist_path),
        output_path=str(output_path),
    )


def _current_bucket(current: float) -> str:
    magnitude = abs(current)
    if magnitude < 1e-12:
        return "open"
    bucket = round(math.log10(magnitude) * 2.0) / 2.0
    return f"1e{bucket:+.1f}"


def _spice_port_counter(signature: SpiceSimulationSignature) -> Counter[tuple[Any, ...]]:
    return Counter((port.member, port.role) for port in signature.ports)


def _spice_port_role_counter(signature: SpiceSimulationSignature) -> Counter[tuple[Any, ...]]:
    return Counter((port.role,) for port in signature.ports)


def _spice_primitive_counter(signature: SpiceSimulationSignature) -> Counter[tuple[Any, ...]]:
    return Counter(
        (
            primitive.kind,
            _current_bucket(1.0 / primitive.resistance_ohms),
        )
        for primitive in signature.primitives
    )


def _spice_exact_current_counter(signature: SpiceSimulationSignature) -> Counter[tuple[Any, ...]]:
    return Counter(
        (driver, observed, _current_bucket(current))
        for driver, observed, current in signature.currents
    )


def _spice_role_current_counter(signature: SpiceSimulationSignature) -> Counter[tuple[Any, ...]]:
    roles = {port.member: port.role for port in signature.ports}
    return Counter(
        (
            roles.get(driver, ""),
            roles.get(observed, ""),
            _current_bucket(current),
        )
        for driver, observed, current in signature.currents
    )


def _spice_boundary_response_scores(
    submission_board: BoardModel,
    reference_board: BoardModel,
    work_dir: Path,
) -> dict[str, Any]:
    submission_signature = _simulate_external_spice_signature(
        submission_board,
        work_dir,
        label="submission",
    )
    reference_signature = _simulate_external_spice_signature(
        reference_board,
        work_dir,
        label="reference",
    )
    if not submission_signature.simulated or not reference_signature.simulated:
        errors = "; ".join(
            error
            for error in (submission_signature.error, reference_signature.error)
            if error
        )
        return {
            "score": 0.0,
            "subscores": [_subscore("ngspice_boundary_response_simulation", 0.0, errors)],
            "submission_spice": submission_signature.to_dict(),
            "reference_spice": reference_signature.to_dict(),
        }

    subscores = [
        (0.10, _subscore("spice_port_role_multiset", _counter_f1(_spice_port_role_counter(submission_signature), _spice_port_role_counter(reference_signature)))),
        (0.15, _subscore("spice_exact_port_presence", _counter_f1(_spice_port_counter(submission_signature), _spice_port_counter(reference_signature)))),
        (0.15, _subscore("spice_conductive_passive_profile", _counter_f1(_spice_primitive_counter(submission_signature), _spice_primitive_counter(reference_signature)))),
        (0.25, _subscore("spice_role_current_matrix", _counter_f1(_spice_role_current_counter(submission_signature), _spice_role_current_counter(reference_signature)))),
        (0.35, _subscore("spice_exact_current_matrix", _counter_f1(_spice_exact_current_counter(submission_signature), _spice_exact_current_counter(reference_signature)))),
    ]
    return {
        "score": _weighted_subscores(subscores),
        "subscores": [item for _weight, item in subscores],
        "submission_spice": submission_signature.to_dict(),
        "reference_spice": reference_signature.to_dict(),
    }


def _routed_nets(board: BoardModel) -> set[str]:
    routed_nets = {track.net for track in board.tracks if track.net}
    routed_nets.update(via.net for via in board.vias if via.net)
    routed_nets.update(board.zone_nets)
    return routed_nets


def _external_net_members(board: BoardModel) -> dict[str, list[str]]:
    boundary_refs = set(_boundary_references(board))
    members: dict[str, list[str]] = {}
    for reference in boundary_refs:
        footprint = board.footprints[reference]
        for pad_name, pad in footprint.pads.items():
            if not pad.net or _net_role(pad.net) == "unconnected":
                continue
            members.setdefault(pad.net, []).append(f"{reference}.{pad_name}")
    return members


def _external_net_role_counter(board: BoardModel) -> Counter[tuple[Any, ...]]:
    return Counter(
        (_net_role(net), min(len(members), 16))
        for net, members in _external_net_members(board).items()
        if len(members) >= 2
    )


def _routed_external_net_role_counter(board: BoardModel) -> Counter[tuple[Any, ...]]:
    routed_nets = _routed_nets(board)
    return Counter(
        (_net_role(net), min(len(members), 16))
        for net, members in _external_net_members(board).items()
        if len(members) >= 2 and net in routed_nets
    )


def _routed_external_role_counter(board: BoardModel) -> Counter[tuple[Any, ...]]:
    routed_nets = _routed_nets(board)
    return Counter(
        (_net_role(net),)
        for net, members in _external_net_members(board).items()
        if len(members) >= 2 and net in routed_nets
    )


def _zone_role_counter(board: BoardModel) -> Counter[tuple[Any, ...]]:
    return Counter((_net_role(net),) for net in board.zone_nets if _net_role(net) != "unconnected")


def _bbox_area(board: BoardModel) -> float:
    bbox = board.outline_bbox()
    if bbox is None:
        return 0.0
    min_x, min_y, max_x, max_y = bbox
    return max(0.0, max_x - min_x) * max(0.0, max_y - min_y)


def _subscore(name: str, score: float, detail: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "score": max(0.0, min(1.0, float(score))),
        "detail": detail,
    }


def _weighted_subscores(items: list[tuple[float, dict[str, Any]]]) -> float:
    total_weight = sum(weight for weight, _item in items)
    if total_weight <= 0:
        return 0.0
    return sum(weight * float(item["score"]) for weight, item in items) / total_weight


def _resolve_reference_board_path(spec: SourceBackedTaskSpec) -> Path:
    if spec.reference_board.exists():
        return spec.reference_board
    matches = sorted(spec.source.vendored_root.rglob("*.kicad_pcb"))
    if not matches:
        raise FileNotFoundError(f"no KiCad board found under {spec.source.vendored_root}")
    for path in matches:
        if path.stem == spec.project_stem:
            return path
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(
        f"ambiguous KiCad boards under {spec.source.vendored_root}: {[path.name for path in matches]}"
    )


def _source_project_dir(spec: SourceBackedTaskSpec) -> Path:
    board_path = _resolve_reference_board_path(spec)
    return board_path.parent


def _source_board_path(source_dir: Path, project_stem: str) -> Path:
    expected_board = source_dir / f"{project_stem}.kicad_pcb"
    if expected_board.exists():
        return expected_board
    matches = sorted(source_dir.glob("*.kicad_pcb"))
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"could not resolve source board for {project_stem} under {source_dir}")


def _find_balanced_block(text: str, start: int) -> tuple[int, int, str]:
    depth = 0
    end = None
    in_string = False
    escaped = False
    for current in range(start, len(text)):
        char = text[current]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "\"":
                in_string = False
            continue
        if char == "\"":
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                end = current + 1
                break
    if end is None:
        raise ValueError("balanced block end not found")
    return start, end, text[start:end]


def _footprint_block_has_reference(block: str, reference: str) -> bool:
    quoted_reference = re.escape(reference)
    return (
        f'(property "Reference" "{reference}"' in block
        or f'(fp_text reference "{reference}"' in block
        or re.search(rf"\(fp_text\s+reference\s+{quoted_reference}(?=[\s\)])", block) is not None
    )


def _extract_footprint_block(text: str, reference: str) -> tuple[int, int, str]:
    scan_from = 0
    while True:
        footprint_start = text.find("(footprint ", scan_from)
        module_start = text.find("(module ", scan_from)
        starts = [index for index in (footprint_start, module_start) if index != -1]
        if not starts:
            break
        start = min(starts)
        _, end, block = _find_balanced_block(text, start)
        if _footprint_block_has_reference(block, reference):
            return start, end, block
        scan_from = end
    raise ValueError(f"reference {reference} not found")


def _extract_pad_block(footprint_block: str, pad_name: str) -> tuple[int, int, str]:
    scan_from = 0
    while True:
        start = footprint_block.find("(pad ", scan_from)
        if start == -1:
            break
        _, end, block = _find_balanced_block(footprint_block, start)
        parsed = parse_pad_block(block)
        if parsed == pad_name:
            return start, end, block
        scan_from = end
    raise ValueError(f"pad {pad_name} not found")


def parse_pad_block(block: str) -> str:
    from tasks.kicad_common import parse_sexpr, string_item

    node = parse_sexpr(block)
    if not isinstance(node, list) or not node or node[0] != "pad":
        raise ValueError("not a KiCad pad block")
    return string_item(node, 1)


def _net_name_to_id(text: str) -> dict[str, str]:
    from tasks.kicad_common import children, string_item

    root = load_board_text(text)
    if not isinstance(root, list):
        raise ValueError("board root is not a list")
    return {
        string_item(net_node, 2): string_item(net_node, 1)
        for net_node in children(root, "net")
        if string_item(net_node, 1)
    }


def _fast_net_name_to_id(text: str) -> dict[str, str]:
    net_ids: dict[str, str] = {}
    net_re = re.compile(r'\(net\s+(-?\d+)\s+("[^"\\]*(?:\\.[^"\\]*)*"|[^\s\)]+)\)')
    for match in net_re.finditer(text):
        raw_name = match.group(2)
        if raw_name.startswith('"') and raw_name.endswith('"'):
            net_name = raw_name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        else:
            net_name = raw_name
        net_ids.setdefault(net_name, match.group(1))
    return net_ids


def load_board_text(text: str) -> Any:
    from tasks.kicad_common import parse_sexpr

    return parse_sexpr(text)


def _quote_kicad_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
    return f'"{escaped}"'


def _net_expr(net_id: str, net_name: str) -> str:
    return f"(net {net_id} {_quote_kicad_string(net_name)})"


def _replace_or_insert_pad_net(pad_block: str, net_expr: str | None) -> str:
    net_start = pad_block.find("(net ")
    if net_start != -1:
        net_start, net_end, _ = _find_balanced_block(pad_block, net_start)
        if net_expr is None:
            return pad_block[:net_start].rstrip() + pad_block[net_end:]
        return pad_block[:net_start] + net_expr + pad_block[net_end:]
    if net_expr is None:
        return pad_block
    return pad_block.rstrip()[:-1].rstrip() + f" {net_expr})"


def _replace_pad_net_for_reference(
    text: str,
    reference: str,
    pad_name: str,
    net_expr: str | None,
) -> str:
    pieces: list[str] = []
    cursor = 0
    scan_from = 0
    updates = 0
    while True:
        footprint_start = text.find("(footprint ", scan_from)
        module_start = text.find("(module ", scan_from)
        starts = [index for index in (footprint_start, module_start) if index != -1]
        if not starts:
            break
        start = min(starts)
        _, end, footprint_block = _find_balanced_block(text, start)
        updated_footprint = footprint_block
        if _footprint_block_has_reference(footprint_block, reference):
            updated_footprint, footprint_updates = _replace_pad_net_in_footprint(
                footprint_block,
                pad_name,
                net_expr,
            )
            updates += footprint_updates
        pieces.append(text[cursor:start])
        pieces.append(updated_footprint)
        cursor = end
        scan_from = end
    pieces.append(text[cursor:])
    if updates == 0:
        raise ValueError(f"reference {reference} pad {pad_name} not found")
    return "".join(pieces)


def _replace_pad_net_in_footprint(
    footprint_block: str,
    pad_name: str,
    net_expr: str | None,
) -> tuple[str, int]:
    pieces: list[str] = []
    cursor = 0
    scan_from = 0
    updates = 0
    while True:
        start = footprint_block.find("(pad ", scan_from)
        if start == -1:
            break
        _, end, pad_block = _find_balanced_block(footprint_block, start)
        updated_pad = pad_block
        if parse_pad_block(pad_block) == pad_name:
            updated_pad = _replace_or_insert_pad_net(pad_block, net_expr)
            updates += 1
        pieces.append(footprint_block[cursor:start])
        pieces.append(updated_pad)
        cursor = end
        scan_from = end
    pieces.append(footprint_block[cursor:])
    return "".join(pieces), updates


def set_pad_net(text: str, reference: str, pad_name: str, target_net: str) -> str:
    net_ids = _net_name_to_id(text)
    if target_net not in net_ids:
        raise ValueError(f"target net {target_net!r} not found")
    return _replace_pad_net_for_reference(
        text,
        reference,
        pad_name,
        _net_expr(net_ids[target_net], target_net),
    )


def clear_pad_net(text: str, reference: str, pad_name: str) -> str:
    return _replace_pad_net_for_reference(text, reference, pad_name, None)


def _block_uses_net(block: str, net_id: str, net_name: str) -> bool:
    return (
        f"(net {net_id}" in block
        or f"(net_name {_quote_kicad_string(net_name)})" in block
        or f"(net_name {net_name})" in block
    )


def remove_routing_for_net(text: str, net_name: str) -> str:
    net_ids = _fast_net_name_to_id(text)
    net_id = net_ids.get(net_name)
    if net_id is None:
        raise ValueError(f"net {net_name!r} not found")
    pieces: list[str] = []
    cursor = 0
    removals = 0
    route_block_re = re.compile(r"\((segment|via|zone)\b")
    for match in route_block_re.finditer(text):
        start = match.start()
        if start < cursor:
            continue
        _, end, block = _find_balanced_block(text, start)
        pieces.append(text[cursor:start])
        if _block_uses_net(block, net_id, net_name):
            removals += 1
        else:
            pieces.append(block)
        cursor = end
    pieces.append(text[cursor:])
    if removals == 0:
        raise ValueError(f"routing for net {net_name!r} not found")
    return "".join(pieces)


def remove_footprint_block(text: str, reference: str) -> str:
    start, end, _ = _extract_footprint_block(text, reference)
    return text[:start].rstrip() + "\n\n" + text[end:].lstrip()


def get_footprint_block(text: str, reference: str) -> str:
    _, _, block = _extract_footprint_block(text, reference)
    return block


def rename_footprint_block_reference(block: str, new_reference: str) -> str:
    updated = re.sub(
        r'(\(property "Reference" ")([^"]+)(")',
        rf"\g<1>{new_reference}\g<3>",
        block,
        count=1,
    )
    updated = re.sub(
        r'(\(fp_text reference\s+")([^"]+)(")',
        rf"\g<1>{new_reference}\g<3>",
        updated,
        count=1,
    )
    updated = re.sub(
        r"(\(fp_text reference\s+)([^\s\)]+)",
        rf"\g<1>{new_reference}",
        updated,
        count=1,
    )
    return updated


def add_footprint_block(text: str, block: str) -> str:
    stripped = text.rstrip()
    if not stripped.endswith(")"):
        raise ValueError("board text must end with a top-level closing parenthesis")
    return stripped[:-1].rstrip() + "\n\n" + block.strip() + "\n)\n"


def _clip_output(value: str, limit: int = 2000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n... truncated ..."


def _kicad_cli_pcb_drc_validation(
    board_path: Path,
    work_dir: Path,
    *,
    image: str,
) -> dict[str, Any]:
    report_path = work_dir / "kicad_pcb_drc.json"
    command: list[str]
    if shutil.which("kicad-cli") is not None:
        command = [
            "kicad-cli",
            "pcb",
            "drc",
            "--format",
            "json",
            "--output",
            str(report_path),
            str(board_path),
        ]
    elif image and shutil.which("docker") is not None:
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--mount",
            f"type=bind,src={board_path.parent.resolve()},dst=/project,readonly",
            "--mount",
            f"type=bind,src={work_dir.resolve()},dst=/work",
            "--entrypoint",
            "kicad-cli",
            image,
            "pcb",
            "drc",
            "--format",
            "json",
            "--output",
            "/work/kicad_pcb_drc.json",
            f"/project/{board_path.name}",
        ]
    else:
        return {
            "score": 1.0,
            "available": False,
            "skipped": True,
            "detail": "kicad-cli unavailable outside benchmark container",
            "report_path": str(report_path),
        }

    try:
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(str(part) for part in (exc.stdout, exc.stderr) if part)
        return {
            "score": 0.0,
            "available": True,
            "skipped": False,
            "detail": "kicad-cli pcb drc timed out",
            "stdout": _clip_output(output),
            "report_path": str(report_path),
        }

    # Treat any nonzero DRC exit as a violation; KiCad reports clean boards with 0.
    report_exists = report_path.exists()
    missing_cli = proc.returncode == 127 and "kicad-cli" in proc.stderr
    if missing_cli:
        return {
            "score": 1.0,
            "available": False,
            "skipped": True,
            "detail": "kicad-cli unavailable in configured runtime",
            "returncode": proc.returncode,
            "stdout": _clip_output(proc.stdout),
            "stderr": _clip_output(proc.stderr),
            "report_path": str(report_path),
            "report_exists": report_exists,
        }
    score = 1.0 if report_exists and proc.returncode == 0 else 0.0
    return {
        "score": score,
        "available": True,
        "skipped": False,
        "detail": "" if score == 1.0 else f"kicad-cli pcb drc reported violations or exited {proc.returncode}",
        "returncode": proc.returncode,
        "stdout": _clip_output(proc.stdout),
        "stderr": _clip_output(proc.stderr),
        "report_path": str(report_path),
        "report_exists": report_exists,
    }


def grade_source_backed_task(
    task: TaskSpec,
    project_dir: Path,
    work_dir: Path,
    *,
    image: str,
    spec: SourceBackedTaskSpec,
) -> TaskEvaluation:
    return evaluate_with_io_simulation_oracle(
        task,
        project_dir,
        work_dir,
        source_metadata={
            "source_repo_url": spec.source.repo_url,
            "source_commit": spec.source.commit,
            "license": spec.source.license,
            "project_stem": spec.project_stem,
            "reference_board": str(_resolve_reference_board_path(spec)),
            "source_spec": spec,
        },
    )
