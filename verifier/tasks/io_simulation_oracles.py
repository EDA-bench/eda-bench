from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

from tasks.kicad_common import load_schematic_symbols
from tasks.specs import TaskEvaluation, TaskSpec

GRADING_MODEL = "explicit PCB workability oracle score v2"
MISSING_ORACLE_REASON = "missing_explicit_io_simulation_oracle"


@dataclass(frozen=True)
class IoSimulationOracle:
    task_id: str
    description: str

    def evaluate(
        self,
        task: TaskSpec,
        project_dir: Path,
        work_dir: Path,
        *,
        source_metadata: dict[str, Any],
    ) -> TaskEvaluation:
        return evaluate_behavioral_io_simulation(
            task,
            project_dir,
            work_dir,
            source_metadata=source_metadata,
        )


@dataclass(frozen=True)
class CalibrationCheck:
    name: str
    subscore_name: str
    min_score: float
    cap: float
    detail: str


@dataclass(frozen=True)
class CalibratedIoSimulationOracle(IoSimulationOracle):
    calibration_name: str
    checks: tuple[CalibrationCheck, ...]

    def evaluate(
        self,
        task: TaskSpec,
        project_dir: Path,
        work_dir: Path,
        *,
        source_metadata: dict[str, Any],
    ) -> TaskEvaluation:
        evaluation = evaluate_behavioral_io_simulation(
            task,
            project_dir,
            work_dir,
            source_metadata=source_metadata,
        )
        return _apply_calibrated_checks(evaluation, self)


ORACLES: dict[str, IoSimulationOracle] = {
    "usb_c_female_breakout": CalibratedIoSimulationOracle(
        task_id="usb_c_female_breakout",
        description="calibrated USB-C breakout continuity and connector-orientation oracle",
        calibration_name="usb_c_breakout_continuity_orientation",
        checks=(
            CalibrationCheck(
                "usb_c_refdes_invariant_pin_semantics",
                "semantic_external_io_net_verification",
                0.99,
                0.20,
                "USB-C breakout pins must preserve refdes-invariant external net semantics.",
            ),
            CalibrationCheck(
                "usb_c_routed_continuity_and_short_safety",
                "external_io_electrical_health",
                1.00,
                0.15,
                "USB-C breakout nets must be routed without isolated external pads or shorts.",
            ),
            CalibrationCheck(
                "usb_c_pcb_geometry_response",
                "pcb_geometry_boundary_family_waveform_response",
                1.00,
                0.25,
                "PCB-derived geometry simulation must produce finite boundary responses.",
            ),
        ),
    ),
    "rs485_transceiver_breakout": CalibratedIoSimulationOracle(
        task_id="rs485_transceiver_breakout",
        description="calibrated RS-485 active-transceiver boundary oracle",
        calibration_name="rs485_active_transceiver_io",
        checks=(
            CalibrationCheck(
                "rs485_connector_semantics",
                "semantic_external_io_net_verification",
                0.95,
                0.20,
                "RS-485 connector-visible pin/net semantics must match the contract.",
            ),
            CalibrationCheck(
                "rs485_active_component_function",
                "reference_component_function_realization",
                0.85,
                0.25,
                "The transceiver, passives, and protection/function profile must be realized.",
            ),
            CalibrationCheck(
                "rs485_active_power_integrity",
                "active_device_power_integrity",
                0.90,
                0.25,
                "Signal-bearing active devices must retain power and ground connectivity.",
            ),
        ),
    ),
    "bq24295_power_path_board": CalibratedIoSimulationOracle(
        task_id="bq24295_power_path_board",
        description="calibrated charger and power-path role oracle",
        calibration_name="bq24295_power_path_roles",
        checks=(
            CalibrationCheck(
                "bq24295_power_path_component_function",
                "reference_component_function_realization",
                0.85,
                0.25,
                "Power-path active devices, passives, decoupling, and protection roles must be present.",
            ),
            CalibrationCheck(
                "bq24295_power_path_active_power",
                "active_device_power_integrity",
                0.90,
                0.25,
                "Power-path active devices must retain power and ground connectivity.",
            ),
            CalibrationCheck(
                "bq24295_external_power_safety",
                "external_io_electrical_health",
                1.00,
                0.15,
                "External power/battery/load nets must remain routed and short-safe.",
            ),
        ),
    ),
    "m2_pcie_adapter": CalibratedIoSimulationOracle(
        task_id="m2_pcie_adapter",
        description="calibrated high-speed M.2/PCIe differential-pair oracle",
        calibration_name="m2_pcie_high_speed_pairs",
        checks=(
            CalibrationCheck(
                "m2_pcie_connector_semantics",
                "semantic_external_io_net_verification",
                0.95,
                0.20,
                "M.2/PCIe connector-visible pin/net semantics must match the contract.",
            ),
            CalibrationCheck(
                "m2_pcie_differential_pair_geometry",
                "pcb_high_speed_differential_pair_quality",
                0.90,
                0.25,
                "Required high-speed pair families must have plausible skew, impedance, and spacing.",
            ),
            CalibrationCheck(
                "m2_pcie_geometry_response",
                "pcb_geometry_boundary_family_waveform_response",
                1.00,
                0.25,
                "PCB-derived geometry simulation must produce finite boundary responses.",
            ),
        ),
    ),
}
DEFAULT_ORACLE = IoSimulationOracle(
    task_id="*",
    description=(
        "ngspice PCB-geometry and behavioral I/O oracle: declared boundary ports "
        "receive transient stimuli while routed trace parasitics, same-layer "
        "trace shorts, and boundary-port voltage waveforms are measured"
    ),
)


def get_io_simulation_oracle(task_id: str) -> IoSimulationOracle | None:
    return ORACLES.get(task_id, DEFAULT_ORACLE)


def _apply_calibrated_checks(
    evaluation: TaskEvaluation,
    oracle: CalibratedIoSimulationOracle,
) -> TaskEvaluation:
    raw = dict(evaluation.raw)
    components = dict(raw.get("score_components") or {})
    io_component = dict(components.get("io_simulation") or {})
    if not io_component:
        return evaluation

    subscore_by_name = {
        str(item.get("name")): float(item.get("score", 0.0))
        for item in io_component.get("subscores", [])
        if isinstance(item, dict)
    }
    calibrated_checks: list[dict[str, Any]] = []
    score_caps = list(io_component.get("score_caps", []))
    for check in oracle.checks:
        score = subscore_by_name.get(check.subscore_name, 0.0)
        passed = score >= check.min_score
        record = {
            "name": check.name,
            "source_subscore": check.subscore_name,
            "score": score,
            "min_score": check.min_score,
            "passed": passed,
            "detail": check.detail,
        }
        calibrated_checks.append(record)
        if not passed:
            score_caps.append(
                {
                    "name": f"calibrated_{check.name}",
                    "cap": check.cap,
                    "detail": (
                        f"{check.subscore_name} score {score:.3f}; "
                        f"required >= {check.min_score:.3f}. {check.detail}"
                    ),
                }
            )

    if score_caps:
        io_component["score"] = min(float(io_component.get("score", 0.0)), *(float(item["cap"]) for item in score_caps))
    io_component["score_caps"] = score_caps
    io_component["calibrated_task_checks"] = calibrated_checks
    components["io_simulation"] = io_component
    raw["score_components"] = components
    raw_oracle = dict(raw.get("oracle") or {})
    raw_oracle["calibrated_task_oracle"] = {
        "name": oracle.calibration_name,
        "description": oracle.description,
        "checks": calibrated_checks,
    }
    raw["oracle"] = raw_oracle

    metrics = dict(evaluation.metrics)
    score = float(io_component["score"])
    metrics["task_score"] = score
    metrics["overall_score"] = score
    metrics["reward"] = score
    return TaskEvaluation(raw=raw, metrics=metrics)


def _missing_submission(task: TaskSpec, project_dir: Path, work_dir: Path, message: str) -> TaskEvaluation:
    work_dir.mkdir(parents=True, exist_ok=True)
    raw = {
        "task_id": task.task_id,
        "project_dir": str(project_dir),
        "grading_model": GRADING_MODEL,
        "scoring_mode": "explicit_io_simulation",
        "supported": True,
        "unsupported": False,
        "failures": [message],
        "score_components": {},
        "oracle": None,
    }
    metrics = {
        "submission_exists": 0.0,
        "build_success": 0.0,
        "task_score": 0.0,
        "overall_score": 0.0,
        "reward": 0.0,
        "error_message": message,
    }
    return TaskEvaluation(raw=raw, metrics=metrics)


def _subscore(name: str, score: float, detail: str = "") -> dict[str, Any]:
    bounded = max(0.0, min(1.0, float(score)))
    return {"name": name, "score": bounded, "detail": detail}


def _counter_f1(left: Any, right: Any) -> float:
    if not left and not right:
        return 1.0
    overlap = sum((left & right).values())
    total = sum(left.values()) + sum(right.values())
    if total == 0:
        return 1.0
    return 2.0 * overlap / total


def _counter_recall(submission: Any, reference: Any) -> float:
    if not reference:
        return 1.0
    overlap = sum((submission & reference).values())
    total = sum(reference.values())
    if total <= 0:
        return 1.0
    return max(0.0, min(1.0, overlap / total))


def _counter_to_records(counter: Counter[tuple[str, ...]]) -> list[dict[str, Any]]:
    return [
        {"key": list(key), "count": count}
        for key, count in sorted(counter.items())
    ]


def _counter_from_records(records: Any) -> Counter[tuple[str, ...]]:
    counter: Counter[tuple[str, ...]] = Counter()
    if not isinstance(records, list):
        return counter
    for record in records:
        if not isinstance(record, dict):
            continue
        key = record.get("key")
        count = record.get("count", 0)
        if not isinstance(key, list):
            continue
        try:
            counter[tuple(str(part) for part in key)] += int(count)
        except (TypeError, ValueError):
            continue
    return counter


def _weighted_subscores(items: list[tuple[float, dict[str, Any]]]) -> float:
    total_weight = sum(weight for weight, _item in items)
    if total_weight <= 0:
        return 0.0
    return sum(weight * float(item["score"]) for weight, item in items) / total_weight


@dataclass(frozen=True)
class BehavioralTracePoint:
    driver: str
    observed: str
    sample: str
    voltage: float


@dataclass(frozen=True)
class BehavioralSimulationSignature:
    ports: tuple[Any, ...]
    drivers: tuple[Any, ...]
    traces: tuple[BehavioralTracePoint, ...]
    model_summary: dict[str, int]
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
            "drivers": [driver.member for driver in self.drivers],
            "trace_count": len(self.traces),
            "trace_summary": dict(sorted(Counter(trace.sample for trace in self.traces).items())),
            "model_summary": self.model_summary,
            "simulated": self.simulated,
            "error": self.error,
            "netlist_path": self.netlist_path,
            "output_path": self.output_path,
        }


@dataclass(frozen=True)
class PcbGeometryTracePoint:
    driver: str
    observed: str
    sample: str
    voltage: float


@dataclass(frozen=True)
class PcbGeometrySimulationSignature:
    ports: tuple[Any, ...]
    drivers: tuple[Any, ...]
    traces: tuple[PcbGeometryTracePoint, ...]
    impedance_profile: tuple[tuple[str, ...], ...]
    collision_profile: tuple[tuple[str, ...], ...]
    high_speed_pair_profile: tuple[tuple[str, ...], ...]
    model_summary: dict[str, int]
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
            "drivers": [driver.member for driver in self.drivers],
            "trace_count": len(self.traces),
            "trace_summary": dict(sorted(Counter(trace.sample for trace in self.traces).items())),
            "impedance_profile": dict(sorted(Counter(self.impedance_profile).items())),
            "collision_profile": dict(sorted(Counter(self.collision_profile).items())),
            "high_speed_pair_profile": dict(sorted(Counter(self.high_speed_pair_profile).items())),
            "model_summary": self.model_summary,
            "simulated": self.simulated,
            "error": self.error,
            "netlist_path": self.netlist_path,
            "output_path": self.output_path,
        }


@dataclass(frozen=True)
class KnownIoCheck:
    name: str
    score: float
    detail: str

    def to_dict(self) -> dict[str, Any]:
        bounded = max(0.0, min(1.0, float(self.score)))
        return {"name": self.name, "score": bounded, "detail": self.detail}


@dataclass(frozen=True)
class KnownIoVerificationSignature:
    task_id: str
    interface_refs: tuple[str, ...]
    reference_members: tuple[str, ...]
    checks: tuple[KnownIoCheck, ...]
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "interface_refs": list(self.interface_refs),
            "reference_members": list(self.reference_members),
            "checks": [check.to_dict() for check in self.checks],
            "score": max(0.0, min(1.0, float(self.score))),
        }


def _loose_numeric_value(value: str, *, kind: str) -> float | None:
    normalized = str(value or "").upper().replace("Ω", "R").replace(",", ".")
    normalized = re.sub(r"\([^)]*\)", "", normalized)
    match = re.search(r"([-+]?\d+(?:\.\d+)?)(P|N|U|µ|M|K|MEG|G|F|H|R)?", normalized)
    if match is None:
        return None
    number = float(match.group(1))
    suffix = match.group(2) or ""
    multipliers = {
        "P": 1e-12,
        "N": 1e-9,
        "U": 1e-6,
        "µ": 1e-6,
        "M": 1e-3 if kind in {"capacitance", "inductance"} else 1e6,
        "K": 1e3,
        "MEG": 1e6,
        "G": 1e9,
        "F": 1.0,
        "H": 1.0,
        "R": 1.0,
        "": 1.0,
    }
    return max(1e-15, number * multipliers.get(suffix, 1.0))


def _voltage_for_role(role: str) -> float:
    if "5v" in role.lower():
        return 5.0
    if "3v3" in role.lower() or "3v" in role.lower():
        return 3.3
    if "1v8" in role.lower():
        return 1.8
    if "1v2" in role.lower():
        return 1.2
    if "1v1" in role.lower():
        return 1.1
    if role == "ground":
        return 0.0
    if role.startswith("power_"):
        return 3.3
    return 1.8


def _stable_unit_interval(*parts: str) -> float:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _spice_value(value: float) -> str:
    return f"{value:.9g}"


def _trace_bucket(voltage: float) -> str:
    if voltage < 0.05:
        return "low"
    if voltage < 0.4:
        return "weak_low"
    if voltage < 1.2:
        return "mid"
    if voltage < 2.4:
        return "logic"
    if voltage < 4.0:
        return "high_3v3"
    return "high_5v"


def _trace_exact_counter(signature: BehavioralSimulationSignature) -> Counter[tuple[str, str, str, str]]:
    return Counter(
        (trace.driver, trace.observed, trace.sample, _trace_bucket(trace.voltage))
        for trace in signature.traces
    )


def _trace_role_counter(signature: BehavioralSimulationSignature) -> Counter[tuple[str, str, str, str]]:
    roles = {port.member: port.role for port in signature.ports}
    return Counter(
        (
            roles.get(trace.driver, ""),
            roles.get(trace.observed, ""),
            trace.sample,
            _trace_bucket(trace.voltage),
        )
        for trace in signature.traces
    )


def _behavioral_port_counter(signature: BehavioralSimulationSignature) -> Counter[tuple[str, str]]:
    return Counter((port.member, port.role) for port in signature.ports)


def _geometry_trace_exact_counter(signature: PcbGeometrySimulationSignature) -> Counter[tuple[str, str, str, str]]:
    return Counter(
        (trace.driver, trace.observed, trace.sample, _trace_bucket(trace.voltage))
        for trace in signature.traces
    )


def _geometry_trace_role_counter(signature: PcbGeometrySimulationSignature) -> Counter[tuple[str, str, str, str]]:
    roles = {port.member: port.role for port in signature.ports}
    return Counter(
        (
            roles.get(trace.driver, ""),
            roles.get(trace.observed, ""),
            trace.sample,
            _trace_bucket(trace.voltage),
        )
        for trace in signature.traces
    )


def _geometry_impedance_counter(signature: PcbGeometrySimulationSignature) -> Counter[tuple[str, ...]]:
    return Counter(signature.impedance_profile)


def _geometry_collision_counter(signature: PcbGeometrySimulationSignature) -> Counter[tuple[str, ...]]:
    return Counter(signature.collision_profile)


def _geometry_high_speed_pair_counter(signature: PcbGeometrySimulationSignature) -> Counter[tuple[str, ...]]:
    return Counter(signature.high_speed_pair_profile)


def _high_speed_family_counter(profile: Any) -> Counter[tuple[str, ...]]:
    counter: Counter[tuple[str, ...]] = Counter()
    for item in profile or ():
        if item:
            counter[(str(item[0]),)] += 1
    return counter


def _z0_from_bucket(bucket: str) -> float | None:
    match = re.search(r"^(\d+)ohm$", str(bucket))
    if match is None:
        return None
    return float(match.group(1))


def _impedance_plausibility_score(signature: PcbGeometrySimulationSignature) -> float:
    if not signature.impedance_profile:
        return 1.0
    passed = 0
    total = 0
    for item in signature.impedance_profile:
        if len(item) < 4:
            continue
        role = _role_family(str(item[0]))
        z0 = _z0_from_bucket(str(item[3]))
        if z0 is None:
            continue
        total += 1
        if role in {"power", "ground"}:
            passed += int(12.0 <= z0 <= 180.0)
        else:
            passed += int(25.0 <= z0 <= 150.0)
    if total <= 0:
        return 1.0
    return passed / total


def _impedance_scoring_score(signature: PcbGeometrySimulationSignature) -> float:
    return min(1.0, _impedance_plausibility_score(signature) / 0.35)


def _high_speed_pair_absolute_quality(profile: Any) -> float:
    passed = 0.0
    total = 0
    for item in profile or ():
        if len(item) < 6:
            continue
        _family, _length, skew, _width, z0_bucket, spacing = item[:6]
        z0 = _z0_from_bucket(str(z0_bucket))
        total += 1
        if skew in {"skew_lt2pct", "skew_2to5pct", "skew_5to10pct"}:
            passed += 0.35
        elif skew == "skew_10to25pct":
            passed += 0.15
        if z0 is not None and 35.0 <= z0 <= 120.0:
            passed += 0.35
        elif z0 is not None and 25.0 <= z0 <= 150.0:
            passed += 0.15
        if spacing not in {"spacing_unknown", "lt0p08mm"}:
            passed += 0.30
        elif spacing == "lt0p08mm":
            passed += 0.10
    if total <= 0:
        return 1.0
    return passed / total


def _high_speed_pair_quality_score(
    signature: PcbGeometrySimulationSignature,
    reference_profile: Counter[tuple[str, ...]],
    reference_pairs: Any,
) -> float:
    if not reference_profile and not signature.high_speed_pair_profile:
        return 1.0
    if reference_profile and not signature.high_speed_pair_profile:
        return 0.0
    absolute_quality = _high_speed_pair_absolute_quality(signature.high_speed_pair_profile)
    reference_quality = _high_speed_pair_absolute_quality(reference_pairs)
    quality = min(1.0, absolute_quality / max(reference_quality, 0.01))
    family_recall = _counter_recall(
        _high_speed_family_counter(signature.high_speed_pair_profile),
        reference_profile,
    )
    if family_recall < 1.0 and ("generic_diff",) in _high_speed_family_counter(signature.high_speed_pair_profile):
        family_recall = 1.0
    return max(0.0, min(1.0, 0.65 * quality + 0.35 * family_recall))


def _known_io_exact_score(signature: KnownIoVerificationSignature | None) -> float:
    if signature is None:
        return 1.0
    return max(0.0, min(1.0, float(signature.score)))


def _role_family(role: str) -> str:
    return "power" if role.startswith("power_") else role


def _reference_prefix(reference: str) -> str:
    match = re.match(r"^[A-Za-z]+", str(reference or ""))
    return match.group(0).upper() if match else ""


def _loose_token(value: str) -> str:
    normalized = str(value or "").upper().replace(" ", "")
    normalized = normalized.replace("_", "").replace("-", "").replace(".", "")
    return re.sub(r"[^A-Z0-9]+", "", normalized)


INTERFACE_FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "antenna": ("ANT", "RF", "SMA", "UFL", "U.FL", "GNSS", "LORA"),
    "audio": ("AUDIO", "I2S", "I2C/I2S", "CODEC", "MIC", "LINEIN", "LINEOUT", "HP", "SPK", "WM8731"),
    "battery": ("BAT", "VBAT", "LIPO", "LI-ION", "CHARGER", "BATT"),
    "camera": ("CAM", "CAMERA", "CSI", "OV9281"),
    "can": ("CAN", "CANH", "CANL"),
    "debug": ("SWD", "JTAG", "DEBUG", "PROGRAM", "PROG", "UPDI", "BOOT", "RESET", "NRST"),
    "display": ("DISPLAY", "DSI", "EDP", "HDMI", "LVDS", "LCD"),
    "dmx": ("DMX",),
    "eeprom": ("EEPROM", "ID_SC", "ID_SD"),
    "encoder": ("ENCODER", "ROTARY_ENCODER"),
    "ethernet": ("ETH", "ETHERNET", "RJ45", "MDI", "MDX", "MAGJACK"),
    "fan": ("FAN",),
    "flash": ("FLASH", "QSPI", "OSPI"),
    "gpio": ("GPIO", "HEADER", "BREAKOUT", "EXPANSION"),
    "hdmi": ("HDMI",),
    "i2c": ("I2C", "SDA", "SCL", "EASYC"),
    "m2": ("M.2", "M2", "KEY-M", "KEY B", "MODEM"),
    "mipi": ("MIPI", "CSI", "DSI"),
    "motor": ("MOTOR", "H-BRIDGE", "HBRIDGE", "MC33887"),
    "pcie": ("PCIE", "PCI-E", "PCI_EXPRESS", "PERST", "REFCLK", "PET", "PER"),
    "power": ("POWER", "VBUS", "VCC", "VIN", "VOUT", "VUSB", "+5V", "5V", "+3V3", "3V3", "3.3V", "GND"),
    "rs485": ("RS485", "RS-485", "MAX485", "A/B", "485"),
    "rtc": ("RTC", "COIN", "CR2032"),
    "sdcard": ("SDCARD", "MICROSD", "SDIO", "SD_", "DAT0", "CMD", "CLK"),
    "sim": ("SIM", "USIM", "SIMCARD"),
    "spi": ("SPI", "MOSI", "MISO", "SCK", "SCLK", "NCS"),
    "uart": ("UART", "TXD", "RXD", "TX", "RX", "SERIAL"),
    "usb": ("USB", "USB-C", "USBC", "TYPE-C", "TYPE C", "D+", "D-", "DP", "DN", "VBUS", "CC1", "CC2"),
}


def _count_bucket(count: int) -> str:
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count == 2:
        return "2"
    if count <= 4:
        return "3to4"
    if count <= 8:
        return "5to8"
    if count <= 16:
        return "9to16"
    return "gt16"


def _interface_text_families(text: str) -> set[str]:
    normalized = f" {str(text or '').upper().replace('-', '_')} "
    families: set[str] = set()
    for family, keywords in INTERFACE_FAMILY_KEYWORDS.items():
        for keyword in keywords:
            keyword_normalized = str(keyword).upper().replace("-", "_")
            if not keyword_normalized:
                continue
            if re.fullmatch(r"[A-Z0-9_]+", keyword_normalized):
                matched = re.search(rf"(?<![A-Z0-9]){re.escape(keyword_normalized)}(?![A-Z0-9])", normalized) is not None
            else:
                matched = keyword_normalized in normalized
            if matched:
                families.add(family)
                break
    if re.search(r"\bD[+-]\b", normalized) or " D_P " in normalized or " D_N " in normalized:
        families.add("usb")
    if re.search(r"\b(?:TX|RX)D?\d*\b", normalized):
        families.add("uart")
    if re.search(r"\b(?:SDA|SCL)\d*\b", normalized):
        families.add("i2c")
    if re.search(r"\b(?:MOSI|MISO|SCK|SCLK|CS|NCS)\d*\b", normalized):
        families.add("spi")
    if re.search(r"\b(?:CANH|CANL)\b", normalized):
        families.add("can")
    if re.search(r"\b(?:A|B|Y|Z)485\b", normalized):
        families.add("rs485")
    return families


def _required_interface_families_from_task(task: TaskSpec) -> tuple[str, ...]:
    text = f"{task.task_id} {task.title} {task.prompt}"
    families = _interface_text_families(text)
    if any(token in text.lower() for token in ("power", "rail", "regulat", "battery", "usb", "input")):
        families.add("power")
    if "breakout" in text.lower():
        families.add("gpio")
    return tuple(sorted(families))


def _external_net_family_counter(board: Any) -> Counter[tuple[str, ...]]:
    profile: Counter[tuple[str, ...]] = Counter()
    for net, role_counts in _external_net_pad_roles(board).items():
        role = role_counts.most_common(1)[0][0] if role_counts else "signal"
        families = set(_net_interface_families(net, role))
        for family in families:
            profile[(family,)] += 1
    return profile


def _routed_external_net_family_counter(board: Any) -> Counter[tuple[str, ...]]:
    from tasks.source_backed_task import _net_role

    external_nets = set(_external_net_pad_roles(board))
    routed_nets = {
        track.net
        for track in board.tracks
        if track.net in external_nets and _track_length_mm(track) > 0.001
    } | {
        net
        for net in set(board.zone_nets) & external_nets
        if _net_role(net) != "signal"
    }
    profile: Counter[tuple[str, ...]] = Counter()
    for net in routed_nets:
        families = _net_interface_families(net, _net_role(net))
        for family in families:
            profile[(family,)] += 1
    return profile


def _required_family_recall(observed: Counter[tuple[str, ...]], required_families: tuple[str, ...]) -> float:
    if not required_families:
        return 1.0
    observed_families = {key[0] for key, count in observed.items() if key and count > 0}
    matched = 0
    for family in required_families:
        if family in observed_families:
            matched += 1
        elif family != "power" and "gpio" in observed_families:
            matched += 1
    return matched / len(required_families)


def _net_interface_families(net: str, role: str) -> tuple[str, ...]:
    role_family = _role_family(role)
    if role_family in {"power", "ground"}:
        return ("power",)
    families = set(_interface_text_families(net))
    families.discard("power")
    if not families:
        families.add("gpio")
    return tuple(sorted(families))


def _connector_kind(reference: str, footprint: Any) -> str:
    text = f"{reference} {getattr(footprint, 'footprint', '')} {getattr(footprint, 'value', '')}".upper()
    pad_names = {str(name).upper() for name in (getattr(footprint, "pads", {}) or {})}
    if {"A1", "A4", "A5", "A6", "A7", "A8", "A9", "A12", "B1", "B4", "B5", "B6", "B7", "B8", "B9", "B12"} & pad_names:
        return "usb"
    for kind, tokens in (
        ("usb", ("USB", "TYPE_C", "TYPE-C")),
        ("hdmi", ("HDMI",)),
        ("m2", ("M.2", "M2", "NGFF")),
        ("pcie", ("PCIE", "PCI-E", "PCI_EXPRESS")),
        ("ethernet", ("RJ45", "ETH", "MAGJACK")),
        ("ffc", ("FFC", "FPC")),
        ("sdcard", ("MICROSD", "SDCARD", "MICRO_SD")),
        ("sim", ("SIM", "USIM")),
        ("audio", ("AUDIO", "JACK", "PHONE")),
        ("rf", ("SMA", "UFL", "U.FL", "COAX", "ANT")),
        ("battery", ("BAT", "LIPO", "CR20")),
        ("fan", ("FAN",)),
        ("switch", ("SWITCH", "BUTTON", "PUSH")),
        ("terminal", ("TERMINAL", "SCREW")),
        ("header", ("HEADER", "PINHEADER", "CONN_", "SOCKET")),
    ):
        if any(token in text for token in tokens):
            return kind
    from tasks.source_backed_task import _reference_prefix

    prefix = _reference_prefix(reference)
    if prefix == "SW":
        return "switch"
    if prefix in {"J", "K", "P", "CN", "CON", "X"}:
        return "connector"
    return "external"


def _pad_semantic_token(pad_name: str) -> str:
    normalized = re.sub(r"[^A-Z0-9+-]+", "_", str(pad_name or "").upper()).strip("_")
    if not normalized:
        return "pad"
    aliases = {
        "+": "P",
        "-": "N",
        "D+": "DP",
        "D-": "DN",
    }
    return aliases.get(normalized, normalized)


def _semantic_endpoint_families(reference: str, footprint: Any, connector_kind: str, pad_name: str, role: str) -> set[str]:
    role_family = _role_family(role)
    if role_family in {"power", "ground"}:
        return {"power"}
    text = (
        f"{reference} {connector_kind} {getattr(footprint, 'footprint', '')} "
        f"{getattr(footprint, 'value', '')} {pad_name}"
    )
    families = _interface_text_families(text)
    families.discard("power")
    return families or {"gpio"}


def _external_semantic_net_counter(board: Any) -> Counter[tuple[str, ...]]:
    from tasks.source_backed_task import _natural_sort_key, _net_role

    references = _interface_references(board)
    endpoints_by_net: dict[str, list[tuple[str, str, str, str]]] = {}
    families_by_net: dict[str, set[str]] = {}
    for reference in references:
        footprint = board.footprints.get(reference)
        if footprint is None:
            continue
        connector_kind = _connector_kind(reference, footprint)
        for pad_name, pad in footprint.pads.items():
            role = _net_role(pad.net)
            if not pad.net or role == "unconnected":
                continue
            endpoint_families = _semantic_endpoint_families(reference, footprint, connector_kind, pad_name, role)
            families_by_net.setdefault(pad.net, set()).update(endpoint_families)
            family_token = ".".join(sorted(endpoint_families))
            endpoints_by_net.setdefault(pad.net, []).append(
                (
                    connector_kind,
                    _role_family(role),
                    family_token,
                    _pad_semantic_token(pad_name),
                )
            )

    profile: Counter[tuple[str, ...]] = Counter()
    for net, endpoints in sorted(endpoints_by_net.items(), key=lambda item: _natural_sort_key(item[0])):
        role = _role_family(_net_role(net))
        net_families = set(_net_interface_families(net, role)) | families_by_net.get(net, set())
        if len(net_families) > 1:
            net_families.discard("gpio")
        families = ".".join(sorted(net_families)) or "generic"
        normalized_endpoints = tuple(
            f"{kind}:{endpoint_role}:{endpoint_families}:{pad}"
            for kind, endpoint_role, endpoint_families, pad in sorted(endpoints)
        )
        if len(normalized_endpoints) <= 8:
            endpoint_key = normalized_endpoints
        else:
            endpoint_key = (
                *normalized_endpoints[:4],
                f"more:{_count_bucket(len(normalized_endpoints) - 8)}",
                *normalized_endpoints[-4:],
            )
        profile[("semantic_external_net", role, families, _count_bucket(len(endpoints)), *endpoint_key)] += 1
    return profile


def _task_functional_score(
    task: TaskSpec,
    board: Any,
    required_families: tuple[str, ...],
    health: dict[str, Any],
    *,
    routed_required_families: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    _ = task
    routed_required_families = routed_required_families if routed_required_families is not None else required_families
    external_net_families = _external_net_family_counter(board)
    routed_families = _routed_external_net_family_counter(board)
    interface_presence = _required_family_recall(external_net_families | routed_families, required_families)
    routed_presence = _required_family_recall(routed_families, routed_required_families)
    external_net_count = int(health.get("external_net_count", 0))
    routed_external_net_count = int(health.get("routed_external_net_count", 0))
    route_coverage = routed_external_net_count / max(1, external_net_count)
    score = 0.55 * interface_presence + 0.45 * routed_presence
    return {
        "required_families": required_families,
        "routed_required_families": routed_required_families,
        "external_net_family_profile": _counter_to_records(external_net_families),
        "routed_external_net_family_profile": _counter_to_records(routed_families),
        "interface_presence_score": interface_presence,
        "routed_presence_score": routed_presence,
        "route_coverage_score": route_coverage,
        "score": max(0.0, min(1.0, score)),
    }


def _external_port_role_counter(signature: BehavioralSimulationSignature | PcbGeometrySimulationSignature) -> Counter[tuple[str, str]]:
    return Counter((_role_family(port.role), _count_bucket(1)) for port in signature.ports)


def _trace_shape_counter(signature: BehavioralSimulationSignature) -> Counter[tuple[str, str, str, str, str]]:
    roles = {port.member: _role_family(port.role) for port in signature.ports}
    by_driver_sample: dict[tuple[str, str, str], Counter[tuple[str, str]]] = {}
    for trace in signature.traces:
        driver_role = roles.get(trace.driver, "")
        observed_role = roles.get(trace.observed, "")
        by_driver_sample.setdefault((trace.driver, driver_role, trace.sample), Counter())[
            (observed_role, _trace_bucket(trace.voltage))
        ] += 1
    profile: Counter[tuple[str, str, str, str, str]] = Counter()
    for (_driver, driver_role, sample), observed_counts in by_driver_sample.items():
        for (observed_role, bucket), count in observed_counts.items():
            profile[(driver_role, sample, observed_role, bucket, _count_bucket(count))] += 1
    return profile


def _behavioral_measurement_quality_score(signature: BehavioralSimulationSignature) -> float:
    if not signature.simulated or not signature.ports or not signature.drivers:
        return 0.0
    expected = len(signature.ports) * len(signature.drivers) * 3
    if len(signature.traces) < expected:
        return max(0.0, min(1.0, len(signature.traces) / max(1, expected)))
    finite = sum(1 for trace in signature.traces if math.isfinite(trace.voltage))
    return finite / max(1, len(signature.traces))


def _transfer_strength_bucket(ratio: float) -> str:
    if ratio < 0.01:
        return ""
    if ratio < 0.05:
        return "weak"
    if ratio < 0.25:
        return "medium"
    if ratio < 0.75:
        return "strong"
    return "direct"


def _behavioral_transfer_response_counter(signature: BehavioralSimulationSignature) -> Counter[tuple[str, ...]]:
    ports = {port.member: port for port in signature.ports}
    roles = {port.member: _role_family(port.role) for port in signature.ports}
    voltages = {
        (trace.driver, trace.observed, trace.sample): abs(trace.voltage)
        for trace in signature.traces
        if math.isfinite(trace.voltage)
    }
    profile: Counter[tuple[str, ...]] = Counter()
    for trace in signature.traces:
        if trace.driver == trace.observed or not math.isfinite(trace.voltage):
            continue
        self_voltage = voltages.get((trace.driver, trace.driver, trace.sample), 0.0)
        if self_voltage < 1e-9:
            continue
        strength = _transfer_strength_bucket(abs(trace.voltage) / self_voltage)
        if not strength:
            continue
        driver = ports.get(trace.driver)
        observed = ports.get(trace.observed)
        relation = "same_node" if driver is not None and observed is not None and driver.node == observed.node else "cross_node"
        profile[(roles.get(trace.driver, ""), roles.get(trace.observed, ""), relation, strength)] += 1
    return profile


def _signal_transfer_response_counter(profile: Counter[tuple[str, ...]]) -> Counter[tuple[str, ...]]:
    return Counter(
        {key: count for key, count in profile.items() if len(key) >= 2 and "signal" in key[:2]}
    )


def _transfer_profile_counts(profile: Counter[tuple[str, ...]]) -> dict[str, int]:
    counts = {
        "total": 0,
        "signal_involved": 0,
        "signal_cross_node": 0,
        "signal_same_node": 0,
        "power_involved": 0,
        "cross_node": 0,
    }
    for key, count in profile.items():
        if len(key) < 4:
            continue
        driver_role, observed_role, relation, _strength = key[:4]
        amount = int(count)
        roles = {driver_role, observed_role}
        counts["total"] += amount
        if relation == "cross_node":
            counts["cross_node"] += amount
        if "signal" in roles:
            counts["signal_involved"] += amount
            if relation == "cross_node":
                counts["signal_cross_node"] += amount
            else:
                counts["signal_same_node"] += amount
        if "power" in roles:
            counts["power_involved"] += amount
    return counts


def _requires_signal_transfer(task: TaskSpec, required_families: tuple[str, ...]) -> bool:
    signal_families = set(required_families) - {"battery", "fan", "power", "rtc"}
    if signal_families:
        return True
    text = f"{task.task_id} {task.title} {task.prompt}".lower()
    signal_tokens = (
        "audio",
        "bus",
        "camera",
        "can",
        "control",
        "debug",
        "display",
        "dmx",
        "gpio",
        "hdmi",
        "i2c",
        "i2s",
        "jtag",
        "lvds",
        "mipi",
        "pcie",
        "programming",
        "rs-485",
        "rs485",
        "sdcard",
        "signal",
        "spi",
        "swd",
        "uart",
        "usb",
    )
    return any(token in text for token in signal_tokens)


def _is_simple_breakout_task(task: TaskSpec) -> bool:
    text = f"{task.task_id} {task.title} {task.prompt}".lower()
    if "simple breakout" not in text:
        return False
    active_or_transforming_tokens = (
        "battery",
        "bridge",
        "charger",
        "codec",
        "converter",
        "dev board",
        "development",
        "expander",
        "level",
        "mcu",
        "module",
        "output",
        "power-path",
        "power path",
        "programmer",
        "regulat",
        "transceiver",
        "uart bridge",
        "usb-uart",
        "usb uart",
    )
    return not any(token in text for token in active_or_transforming_tokens)


def _requires_cross_node_signal_transfer(task: TaskSpec) -> bool:
    text = f"{task.task_id} {task.title} {task.prompt}".lower()
    if _is_simple_breakout_task(task):
        return False
    if "passive adapter" in text or "passive adapt" in text:
        return False
    return any(
        token in text
        for token in (
            "bridge",
            "charger",
            "codec",
            "converter",
            "direction",
            "driver",
            "hub",
            "level",
            "power path",
            "power-path",
            "programmer",
            "transceiver",
        )
    )


def _observable_transfer_requirements(
    task: TaskSpec,
    required_families: tuple[str, ...],
    reference: BehavioralSimulationSignature | None,
    signature: BehavioralSimulationSignature | None = None,
) -> dict[str, bool]:
    _ = reference
    has_simulated_power_port = signature is None or any(port.role.startswith("power_") for port in signature.ports)
    signal_required = _requires_signal_transfer(task, required_families)
    return {
        "signal": signal_required,
        "cross_signal": signal_required and _requires_cross_node_signal_transfer(task),
        "power": "power" in required_families
        and not _is_simple_breakout_task(task)
        and has_simulated_power_port,
    }


def _behavioral_transfer_response_score(
    submission: BehavioralSimulationSignature,
    task: TaskSpec,
    required_families: tuple[str, ...],
    reference: BehavioralSimulationSignature | None = None,
) -> float:
    profile = _behavioral_transfer_response_counter(submission)
    counts = _transfer_profile_counts(profile)
    requirements = _observable_transfer_requirements(task, required_families, reference, submission)
    scores: list[float] = []
    if requirements["signal"]:
        scores.append(min(1.0, counts["signal_involved"] / 4.0))
        if requirements["cross_signal"]:
            scores.append(min(1.0, counts["signal_cross_node"] / 4.0))
    if requirements["power"]:
        scores.append(min(1.0, counts["power_involved"] / 4.0))
    if not scores:
        return 1.0
    return max(0.0, min(1.0, sum(scores) / len(scores)))


def _behavioral_boundary_response_score(
    submission: BehavioralSimulationSignature,
    task: TaskSpec,
    required_families: tuple[str, ...],
    reference: BehavioralSimulationSignature | None = None,
) -> float:
    measurement_score = _behavioral_measurement_quality_score(submission)
    transfer_score = _behavioral_transfer_response_score(submission, task, required_families, reference)
    return max(0.0, min(1.0, 0.40 * measurement_score + 0.60 * transfer_score))


def _geometry_trace_shape_counter(signature: PcbGeometrySimulationSignature) -> Counter[tuple[str, str, str, str, str]]:
    roles = {port.member: _role_family(port.role) for port in signature.ports}
    by_driver_sample: dict[tuple[str, str, str], Counter[tuple[str, str]]] = {}
    for trace in signature.traces:
        driver_role = roles.get(trace.driver, "")
        observed_role = roles.get(trace.observed, "")
        by_driver_sample.setdefault((trace.driver, driver_role, trace.sample), Counter())[
            (observed_role, _trace_bucket(trace.voltage))
        ] += 1
    profile: Counter[tuple[str, str, str, str, str]] = Counter()
    for (_driver, driver_role, sample), observed_counts in by_driver_sample.items():
        for (observed_role, bucket), count in observed_counts.items():
            profile[(driver_role, sample, observed_role, bucket, _count_bucket(count))] += 1
    return profile


def _geometry_measurement_quality_score(signature: PcbGeometrySimulationSignature) -> float:
    if not signature.simulated or not signature.ports or not signature.drivers:
        return 0.0
    expected = len(signature.ports) * len(signature.drivers) * 3
    if len(signature.traces) < expected:
        return max(0.0, min(1.0, len(signature.traces) / max(1, expected)))
    finite = sum(1 for trace in signature.traces if math.isfinite(trace.voltage))
    return finite / max(1, len(signature.traces))


def _realized_external_copper_counter(board: Any) -> Counter[tuple[str, ...]]:
    from tasks.source_backed_task import _net_role, _realized_copper_graph

    graph = _realized_copper_graph(board)
    external_refs = set(_interface_references(board))
    groups: dict[str, Counter[str]] = {}
    for reference in external_refs:
        footprint = board.footprints.get(reference)
        if footprint is None:
            continue
        for pad_name, pad in footprint.pads.items():
            role = _net_role(pad.net)
            if not pad.net or role == "unconnected":
                continue
            member = f"{reference}.{pad_name}"
            realized_node = graph.pad_nodes.get(member)
            if realized_node is None:
                continue
            groups.setdefault(realized_node, Counter())[_role_family(role)] += 1

    profile: Counter[tuple[str, ...]] = Counter()
    for role_counts in groups.values():
        if not role_counts:
            continue
        role_shape = tuple(
            f"{role}:{_count_bucket(count)}"
            for role, count in sorted(role_counts.items())
        )
        total = sum(role_counts.values())
        profile[(_count_bucket(total), *role_shape)] += 1
    return profile


def _external_net_degree_counter(board: Any) -> Counter[tuple[str, ...]]:
    from tasks.source_backed_task import _net_role

    external_refs = set(_interface_references(board))
    groups: dict[str, Counter[str]] = {}
    for reference in external_refs:
        footprint = board.footprints.get(reference)
        if footprint is None:
            continue
        for pad in footprint.pads.values():
            role = _net_role(pad.net)
            if not pad.net or role == "unconnected":
                continue
            groups.setdefault(pad.net, Counter())[_role_family(role)] += 1
    profile: Counter[tuple[str, ...]] = Counter()
    for role_counts in groups.values():
        if not role_counts:
            continue
        role_shape = tuple(f"{role}:{_count_bucket(count)}" for role, count in sorted(role_counts.items()))
        profile[(_count_bucket(sum(role_counts.values())), *role_shape)] += 1
    return profile


def _external_net_pad_roles(board: Any) -> dict[str, Counter[str]]:
    from tasks.source_backed_task import _net_role

    net_pad_roles: dict[str, Counter[str]] = {}
    for reference in _interface_references(board):
        footprint = board.footprints.get(reference)
        if footprint is None:
            continue
        for pad in footprint.pads.values():
            role = _net_role(pad.net)
            if not pad.net or role == "unconnected":
                continue
            net_pad_roles.setdefault(pad.net, Counter())[_role_family(role)] += 1
    return net_pad_roles


def _external_role_inventory_counter(board: Any) -> Counter[tuple[str, str]]:
    profile: Counter[tuple[str, str]] = Counter()
    for role_counts in _external_net_pad_roles(board).values():
        for role, count in role_counts.items():
            profile[(role, _count_bucket(count))] += 1
    return profile


def _track_count_bucket(count: int) -> str:
    if count <= 0:
        return "tracks_0"
    if count == 1:
        return "tracks_1"
    if count == 2:
        return "tracks_2"
    if count <= 5:
        return "tracks_3to5"
    if count <= 12:
        return "tracks_6to12"
    if count <= 32:
        return "tracks_13to32"
    return "tracks_gt32"


def _via_count_bucket(count: int) -> str:
    if count <= 0:
        return "vias_0"
    if count == 1:
        return "vias_1"
    if count == 2:
        return "vias_2"
    if count <= 5:
        return "vias_3to5"
    return "vias_gt5"


def _layer_count_bucket(count: int) -> str:
    if count <= 0:
        return "layers_0"
    if count == 1:
        return "layers_1"
    if count == 2:
        return "layers_2"
    return "layers_gt2"


def _route_length_bucket(length_mm: float) -> str:
    if length_mm <= 0.001:
        return "route_0mm"
    if length_mm < 2.0:
        return "route_lt2mm"
    if length_mm < 10.0:
        return "route_2to10mm"
    if length_mm < 50.0:
        return "route_10to50mm"
    if length_mm < 150.0:
        return "route_50to150mm"
    return "route_gte150mm"


def _external_net_route_counter(board: Any) -> Counter[tuple[str, ...]]:
    from tasks.source_backed_task import _net_role

    net_pad_roles = _external_net_pad_roles(board)

    tracks_by_net: dict[str, list[Any]] = {}
    for track in board.tracks:
        if track.net in net_pad_roles and _track_length_mm(track) > 0.001:
            tracks_by_net.setdefault(track.net, []).append(track)
    vias_by_net: Counter[str] = Counter(
        via.net
        for via in board.vias
        if via.net in net_pad_roles
    )

    profile: Counter[tuple[str, ...]] = Counter()
    for net, role_counts in net_pad_roles.items():
        role = _role_family(_net_role(net))
        tracks = tracks_by_net.get(net, [])
        total_length = sum(_track_length_mm(track) for track in tracks)
        layers = {track.layer for track in tracks}
        z0_buckets = Counter(
            _z0_bucket(
                _trace_rlc(
                    _track_length_mm(track),
                    max(float(getattr(track, "width", 0.25) or 0.25), 0.05),
                    track.layer,
                )[3]
            )
            for track in tracks
        )
        dominant_z0 = z0_buckets.most_common(1)[0][0] if z0_buckets else "z0_none"
        role_shape = tuple(f"{role_name}:{_count_bucket(count)}" for role_name, count in sorted(role_counts.items()))
        profile[
            (
                role,
                _count_bucket(sum(role_counts.values())),
                _track_count_bucket(len(tracks)),
                _route_length_bucket(total_length),
                _via_count_bucket(vias_by_net[net]),
                _layer_count_bucket(len(layers)),
                dominant_z0,
                *role_shape,
            )
        ] += 1
    return profile


def _routed_external_net_count(board: Any) -> int:
    from tasks.source_backed_task import _net_role

    external_nets = set(_external_net_pad_roles(board))
    return sum(
        1
        for net in external_nets
        if (_net_role(net) != "signal" and net in board.zone_nets)
        or any(track.net == net and _track_length_mm(track) > 0.001 for track in board.tracks)
    )


def _external_io_health_summary(board: Any) -> dict[str, Any]:
    from tasks.source_backed_task import _natural_sort_key, _realized_copper_graph

    graph = _realized_copper_graph(board)
    net_pad_roles = _external_net_pad_roles(board)
    external_members_by_net: dict[str, list[str]] = {}
    for reference in _interface_references(board):
        footprint = board.footprints.get(reference)
        if footprint is None:
            continue
        for pad_name, pad in footprint.pads.items():
            role_counts = net_pad_roles.get(pad.net)
            if not role_counts:
                continue
            member = f"{reference}.{pad_name}"
            external_members_by_net.setdefault(pad.net, []).append(member)

    members_by_node: dict[str, list[str]] = {}
    for member, realized_node in graph.pad_nodes.items():
        members_by_node.setdefault(realized_node, []).append(member)

    from tasks.source_backed_task import _net_role

    routed_nets = {
        track.net
        for track in board.tracks
        if track.net in net_pad_roles and _track_length_mm(track) > 0.001
    } | {
        net
        for net in set(board.zone_nets) & set(net_pad_roles)
        if _net_role(net) != "signal"
    }
    split_external_nets = 0
    isolated_external_pads = 0
    for net, members in external_members_by_net.items():
        realized_nodes = {
            graph.pad_nodes.get(member)
            for member in members
            if graph.pad_nodes.get(member) is not None
        }
        if len(realized_nodes) > 1 and net not in board.zone_nets:
            split_external_nets += 1
        for member in members:
            realized_node = graph.pad_nodes.get(member)
            if realized_node is None:
                isolated_external_pads += 1
                continue
            connected_members = members_by_node.get(realized_node, [])
            if len(connected_members) <= 1 and net not in board.zone_nets:
                isolated_external_pads += 1

    external_short_profile = _external_same_layer_short_profile(board)
    power_ground_shorts = sum(
        count
        for key, count in external_short_profile.items()
        if set(key) == {"ground", "power"}
    )
    power_signal_shorts = sum(
        count
        for key, count in external_short_profile.items()
        if set(key) in ({"power", "signal"}, {"ground", "signal"})
    )
    signal_signal_shorts = sum(
        count
        for key, count in external_short_profile.items()
        if key == ("signal", "signal")
    )
    external_net_count = len(net_pad_roles)
    external_pad_count = sum(sum(role_counts.values()) for role_counts in net_pad_roles.values())
    routed_external_net_count = len(routed_nets)
    continuity_score = 1.0 - min(1.0, split_external_nets / max(1, external_net_count))
    attachment_score = 1.0 - min(1.0, isolated_external_pads / max(1, external_pad_count))
    route_score = routed_external_net_count / max(1, external_net_count)
    short_penalty = min(1.0, power_ground_shorts + 0.5 * power_signal_shorts + 0.2 * signal_signal_shorts)
    short_safety_score = 1.0 - short_penalty
    health_score = (
        0.30 * route_score
        + 0.25 * continuity_score
        + 0.25 * attachment_score
        + 0.20 * short_safety_score
    )
    return {
        "external_net_count": external_net_count,
        "external_connected_pad_count": external_pad_count,
        "routed_external_net_count": routed_external_net_count,
        "split_external_net_count": split_external_nets,
        "isolated_external_pad_count": isolated_external_pads,
        "external_same_layer_short_profile": dict(sorted(external_short_profile.items())),
        "power_ground_short_count": power_ground_shorts,
        "power_signal_or_ground_signal_short_count": power_signal_shorts,
        "signal_signal_short_count": signal_signal_shorts,
        "route_coverage_score": route_score,
        "continuity_score": continuity_score,
        "attachment_score": attachment_score,
        "short_safety_score": short_safety_score,
        "health_score": max(0.0, min(1.0, health_score)),
        "example_external_nets": tuple(sorted(external_members_by_net, key=_natural_sort_key)[:12]),
    }


def _active_internal_features(board: Any) -> Counter[tuple[str, ...]]:
    from tasks.source_backed_task import _boundary_references, _net_role

    boundary_refs = set(_boundary_references(board))
    profile: Counter[tuple[str, ...]] = Counter()
    for reference, footprint in board.footprints.items():
        if reference in boundary_refs:
            continue
        prefix = _reference_prefix(reference)
        if prefix not in {"IC", "Q", "U"}:
            continue
        connected_roles: Counter[str] = Counter()
        connected_families: set[str] = set()
        distinct_nets: set[str] = set()
        for pad in footprint.pads.values():
            if not pad.net:
                continue
            role = _net_role(pad.net)
            if role == "unconnected":
                continue
            role_family = _role_family(role)
            connected_roles[role_family] += 1
            distinct_nets.add(pad.net)
            connected_families.update(_net_interface_families(pad.net, role))
        if not connected_roles:
            continue
        if connected_roles["power"] and connected_roles["ground"]:
            profile[("powered_active",)] += 1
        if connected_roles["signal"] >= 2 and len(distinct_nets) >= 2:
            profile[("signal_active",)] += 1
        if connected_roles["power"] >= 2 and len(distinct_nets) >= 2:
            profile[("power_path_active",)] += 1
        for family in connected_families - {"gpio", "power"}:
            profile[("active_interface_family", family)] += 1
    return profile


def _required_internal_features(task: TaskSpec, required_families: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    text = f"{task.task_id} {task.title} {task.prompt}".lower()
    requirements: list[tuple[str, ...]] = []
    if _is_simple_breakout_task(task) or "passive adapter" in text or "passive adapt" in text:
        return ()
    if any(token in text for token in ("charger", "power path", "power-path", "regulat", "buck", "boost", "converter")):
        requirements.append(("power_path_active",))
    if any(
        token in text
        for token in (
            "bridge",
            "codec",
            "direction",
            "driver",
            "hub",
            "level",
            "programmer",
            "transceiver",
            "translator",
        )
    ):
        requirements.append(("signal_active",))
    if requirements or _requires_cross_node_signal_transfer(task):
        requirements.append(("powered_active",))
    for family in set(required_families) - {"battery", "fan", "gpio", "power", "rtc"}:
        requirements.append(("active_interface_family", family))
    return tuple(dict.fromkeys(requirements))


def _internal_functional_realization_score(
    task: TaskSpec,
    board: Any,
    required_families: tuple[str, ...],
    *,
    required_features: tuple[tuple[str, ...], ...] | None = None,
) -> dict[str, Any]:
    requirements = required_features if required_features is not None else _required_internal_features(task, required_families)
    observed = _active_internal_features(board)
    if not requirements:
        score = 1.0
    else:
        score = _counter_recall(observed, Counter(requirements))
    return {
        "required_features": [list(item) for item in requirements],
        "observed_profile": _counter_to_records(observed),
        "score": max(0.0, min(1.0, score)),
    }


def _value_bucket(reference: str, value: str) -> str:
    prefix = _reference_prefix(reference)
    if prefix == "R":
        parsed = _loose_numeric_value(value, kind="resistance")
        if parsed is None:
            return "resistor_unknown"
        if parsed < 1.0:
            return "resistor_lt1"
        if parsed < 100.0:
            return "resistor_1to100"
        if parsed < 10_000.0:
            return "resistor_100to10k"
        if parsed < 1_000_000.0:
            return "resistor_10kto1m"
        return "resistor_gte1m"
    if prefix == "C":
        parsed = _loose_numeric_value(value, kind="capacitance")
        if parsed is None:
            return "capacitor_unknown"
        if parsed < 1e-9:
            return "capacitor_ltnf"
        if parsed < 1e-6:
            return "capacitor_nf_to_uf"
        if parsed < 100e-6:
            return "capacitor_uf"
        return "capacitor_bulk"
    if prefix in {"FB", "F", "L"}:
        return "series_filter"
    if prefix in {"D", "LED", "TVS"}:
        return "diode_or_protection"
    return "generic"


def _component_function_profile(board: Any) -> Counter[tuple[str, ...]]:
    from tasks.source_backed_task import _boundary_references, _net_role

    boundary_refs = set(_boundary_references(board))
    profile: Counter[tuple[str, ...]] = Counter()
    for reference, footprint in board.footprints.items():
        if reference in boundary_refs:
            continue
        prefix = _reference_prefix(reference)
        connected = [
            (pad.net, _role_family(_net_role(pad.net)))
            for pad in footprint.pads.values()
            if pad.net and _net_role(pad.net) != "unconnected"
        ]
        if not connected:
            continue
        roles = Counter(role for _net, role in connected)
        families = sorted(
            {
                family
                for net, role in connected
                for family in _net_interface_families(net, role)
                if family != "gpio"
            }
        )
        dominant_family = families[0] if len(families) == 1 else ("mixed" if families else "generic")
        role_shape = tuple(f"{role}:{_count_bucket(count)}" for role, count in sorted(roles.items()))
        if prefix in {"IC", "Q", "U"}:
            if roles["power"] and roles["ground"]:
                profile[("active_powered", dominant_family, *role_shape)] += 1
            if roles["signal"] >= 2:
                profile[("active_signal_path", dominant_family, _count_bucket(roles["signal"]))] += 1
            continue
        if prefix == "R":
            profile[("resistor", _value_bucket(reference, footprint.value), dominant_family, *role_shape)] += 1
            continue
        if prefix == "C":
            if roles["power"] and roles["ground"]:
                profile[("decoupling_capacitor", _value_bucket(reference, footprint.value), dominant_family)] += 1
            else:
                profile[("capacitor", _value_bucket(reference, footprint.value), dominant_family, *role_shape)] += 1
            continue
        if prefix in {"FB", "F", "L"}:
            profile[("series_filter", dominant_family, *role_shape)] += 1
            continue
        if prefix in {"D", "LED", "TVS"}:
            if roles["signal"] and (roles["power"] or roles["ground"]):
                profile[("signal_protection", dominant_family, *role_shape)] += 1
            else:
                profile[("diode_or_indicator", dominant_family, *role_shape)] += 1
    return profile


def _component_realization_score(submission_board: Any, reference_board: Any) -> dict[str, Any]:
    submission_profile = _component_function_profile(submission_board)
    reference_profile = _component_function_profile(reference_board)
    recall = _counter_recall(submission_profile, reference_profile)
    f1 = _counter_f1(submission_profile, reference_profile)
    return {
        "score": max(0.0, min(1.0, 0.75 * recall + 0.25 * f1)),
        "recall_score": recall,
        "f1_score": f1,
        "submission_profile": _counter_to_records(submission_profile),
        "reference_profile": _counter_to_records(reference_profile),
    }


def _active_power_integrity_summary(board: Any) -> dict[str, Any]:
    from tasks.source_backed_task import _boundary_references, _net_role

    boundary_refs = set(_boundary_references(board))
    active_count = 0
    active_with_signal_count = 0
    powered_active_count = 0
    signal_active_without_power: list[str] = []
    for reference, footprint in sorted(board.footprints.items()):
        if reference in boundary_refs or _reference_prefix(reference) not in {"IC", "Q", "U"}:
            continue
        roles = Counter(
            _role_family(_net_role(pad.net))
            for pad in footprint.pads.values()
            if pad.net and _net_role(pad.net) != "unconnected"
        )
        if not roles:
            continue
        active_count += 1
        if roles["signal"] > 0:
            active_with_signal_count += 1
            if roles["power"] > 0 and roles["ground"] > 0:
                powered_active_count += 1
            else:
                signal_active_without_power.append(reference)
    score = 1.0
    if active_with_signal_count > 0:
        score = powered_active_count / active_with_signal_count
    return {
        "active_count": active_count,
        "active_with_signal_count": active_with_signal_count,
        "powered_active_count": powered_active_count,
        "signal_active_without_power": signal_active_without_power[:32],
        "score": max(0.0, min(1.0, score)),
    }


def _relative_active_power_integrity_score(submission: dict[str, Any], reference: dict[str, Any]) -> float:
    reference_count = int(reference.get("active_with_signal_count", 0))
    if reference_count <= 0:
        return 1.0
    submission_count = int(submission.get("active_with_signal_count", 0))
    if submission_count <= 0:
        return 0.0
    reference_score = float(reference.get("score", 0.0))
    submission_score = float(submission.get("score", 0.0))
    if reference_score <= 0.0:
        return 1.0
    return max(0.0, min(1.0, submission_score / reference_score))


def _fabrication_geometry_summary(board: Any) -> dict[str, Any]:
    track_widths = [
        max(float(getattr(track, "width", 0.0) or 0.0), 0.0)
        for track in board.tracks
        if track.net and _track_length_mm(track) > 0.001
    ]
    tiny_track_count = sum(1 for width in track_widths if 0.0 < width < 0.075)
    narrow_track_count = sum(1 for width in track_widths if 0.0 < width < 0.10)
    via_annular_rings = [
        max(0.0, (float(getattr(via, "size", 0.0) or 0.0) - float(getattr(via, "drill", 0.0) or 0.0)) * 0.5)
        for via in board.vias
        if via.net
    ]
    invalid_via_count = sum(
        1
        for via in board.vias
        if via.net
        and (
            float(getattr(via, "size", 0.0) or 0.0) <= 0.0
            or float(getattr(via, "drill", 0.0) or 0.0) <= 0.0
            or float(getattr(via, "drill", 0.0) or 0.0) >= float(getattr(via, "size", 0.0) or 0.0)
        )
    )
    thin_annular_ring_count = sum(1 for ring in via_annular_rings if ring < 0.05)
    bbox = board.outline_bbox()
    outline_area = 0.0
    if bbox is not None:
        min_x, min_y, max_x, max_y = bbox
        outline_area = max(0.0, max_x - min_x) * max(0.0, max_y - min_y)
    track_score = 1.0 - min(1.0, tiny_track_count / max(1, len(track_widths)))
    via_score = 1.0 - min(1.0, (invalid_via_count + thin_annular_ring_count) / max(1, len(via_annular_rings)))
    outline_score = 1.0 if outline_area > 1.0 else 0.0
    score = 0.45 * track_score + 0.35 * via_score + 0.20 * outline_score
    return {
        "track_count": len(track_widths),
        "min_track_width_mm": min(track_widths) if track_widths else None,
        "tiny_track_count": tiny_track_count,
        "narrow_track_count": narrow_track_count,
        "via_count": len(via_annular_rings),
        "min_via_annular_ring_mm": min(via_annular_rings) if via_annular_rings else None,
        "invalid_via_count": invalid_via_count,
        "thin_annular_ring_count": thin_annular_ring_count,
        "outline_area_mm2": outline_area,
        "score": max(0.0, min(1.0, score)),
    }


def _relative_fabrication_geometry_score(submission: dict[str, Any], reference: dict[str, Any]) -> float:
    reference_track_count = int(reference.get("track_count", 0))
    reference_via_count = int(reference.get("via_count", 0))
    if reference_track_count <= 0 and reference_via_count <= 0 and float(reference.get("outline_area_mm2", 0.0)) <= 0.0:
        return 1.0
    reference_score = float(reference.get("score", 0.0))
    submission_score = float(submission.get("score", 0.0))
    if reference_score <= 0.0:
        return 1.0
    return max(0.0, min(1.0, submission_score / reference_score))


def _resolve_schematic_path(project_dir: Path, project_stem: str) -> Path | None:
    candidates = [
        project_dir / f"{project_stem}.kicad_sch",
        project_dir / f"{project_stem}.sch",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    matches = sorted([*project_dir.glob("*.kicad_sch"), *project_dir.glob("*.sch")])
    if len(matches) == 1:
        return matches[0]
    return None


def _schematic_board_consistency_score(board: Any, schematic_path: Path | None) -> dict[str, Any]:
    if schematic_path is None:
        return {
            "available": False,
            "score": 0.85,
            "detail": "schematic unavailable; board-only scoring applied",
            "checked_symbol_count": 0,
            "matched_symbol_count": 0,
            "missing_references": [],
            "mismatched_values": [],
            "mismatched_footprints": [],
        }
    try:
        symbols = load_schematic_symbols(schematic_path)
    except Exception as exc:
        return {
            "available": True,
            "score": 0.0,
            "detail": f"schematic parse failed: {type(exc).__name__}: {exc}",
            "checked_symbol_count": 0,
            "matched_symbol_count": 0,
            "missing_references": [],
            "mismatched_values": [],
            "mismatched_footprints": [],
        }
    checked = {
        reference: symbol
        for reference, symbol in symbols.items()
        if not reference.startswith("#")
        and _reference_prefix(reference) not in {"FID", "H", "MH", "MK", "MP", "TP"}
    }
    missing: list[str] = []
    mismatched_values: list[str] = []
    mismatched_footprints: list[str] = []
    matched = 0
    for reference, symbol in checked.items():
        footprint = board.footprints.get(reference)
        if footprint is None:
            missing.append(reference)
            continue
        matched += 1
        if symbol.value and footprint.value and _loose_token(symbol.value) != _loose_token(footprint.value):
            mismatched_values.append(reference)
        if symbol.footprint and footprint.footprint:
            schematic_family = symbol.footprint.split(":", 1)[-1].split("_", 1)[0]
            board_family = footprint.footprint.split(":", 1)[-1].split("_", 1)[0]
            if _loose_token(schematic_family) != _loose_token(board_family):
                mismatched_footprints.append(reference)
    total = max(1, len(checked))
    missing_score = 1.0 - min(1.0, len(missing) / total)
    value_score = 1.0 - min(1.0, len(mismatched_values) / total)
    footprint_score = 1.0 - min(1.0, len(mismatched_footprints) / total)
    score = 0.60 * missing_score + 0.25 * value_score + 0.15 * footprint_score
    return {
        "available": True,
        "score": max(0.0, min(1.0, score)),
        "detail": "",
        "schematic_path": str(schematic_path),
        "checked_symbol_count": len(checked),
        "matched_symbol_count": matched,
        "missing_references": missing[:32],
        "mismatched_values": mismatched_values[:32],
        "mismatched_footprints": mismatched_footprints[:32],
    }


def _relative_external_io_health_score(submission_health: dict[str, Any], reference_health: dict[str, Any]) -> float:
    reference_route = float(reference_health.get("route_coverage_score", 0.0))
    submission_route = float(submission_health.get("route_coverage_score", 0.0))
    route_score = 1.0 if reference_route <= 0.0 else min(1.0, submission_route / max(reference_route, 1e-9))
    external_net_count = max(1, int(reference_health.get("external_net_count", 0) or submission_health.get("external_net_count", 0) or 1))
    connected_pad_count = max(1, int(reference_health.get("external_connected_pad_count", 0) or submission_health.get("external_connected_pad_count", 0) or 1))
    excess_splits = max(0, int(submission_health.get("split_external_net_count", 0)) - int(reference_health.get("split_external_net_count", 0)))
    excess_isolated = max(0, int(submission_health.get("isolated_external_pad_count", 0)) - int(reference_health.get("isolated_external_pad_count", 0)))
    continuity_score = 1.0 - min(1.0, excess_splits / external_net_count)
    attachment_score = 1.0 - min(1.0, excess_isolated / connected_pad_count)
    short_safety_score = float(submission_health.get("short_safety_score", 0.0))
    return max(
        0.0,
        min(
            1.0,
            0.35 * route_score
            + 0.25 * continuity_score
            + 0.20 * attachment_score
            + 0.20 * short_safety_score,
        ),
    )


def _bucket_ratio(value: float, buckets: tuple[tuple[float, str], ...], fallback: str) -> str:
    for limit, label in buckets:
        if value < limit:
            return label
    return fallback


def _width_bucket(width_mm: float) -> str:
    return _bucket_ratio(width_mm, ((0.12, "lt0p12mm"), (0.18, "0p12to0p18mm"), (0.30, "0p18to0p30mm"), (0.60, "0p30to0p60mm")), "gte0p60mm")


def _spacing_bucket(spacing_mm: float | None) -> str:
    if spacing_mm is None or not math.isfinite(spacing_mm):
        return "spacing_unknown"
    return _bucket_ratio(spacing_mm, ((0.08, "lt0p08mm"), (0.15, "0p08to0p15mm"), (0.30, "0p15to0p30mm"), (0.60, "0p30to0p60mm")), "gte0p60mm")


def _skew_bucket(skew_ratio: float) -> str:
    return _bucket_ratio(skew_ratio, ((0.02, "skew_lt2pct"), (0.05, "skew_2to5pct"), (0.10, "skew_5to10pct"), (0.25, "skew_10to25pct")), "skew_gte25pct")


def _diff_pair_key(net_name: str) -> tuple[str, str] | None:
    normalized = re.sub(r"[^A-Z0-9+/-]+", "_", str(net_name or "").upper()).strip("_")
    if not normalized:
        return None
    patterns = (
        re.compile(r"^(.+?)(?:_|-)?(TX|RX)([PN])(\d*)$"),
        re.compile(r"^(.+?)(?:_|-)?(DP|DN)$"),
        re.compile(r"^(.+?)(?:_|-)?D([PN])$"),
        re.compile(r"^(.+?)([+-])$"),
        re.compile(r"^(.+?)(?:_|-)([PN])$"),
    )
    for pattern in patterns:
        match = pattern.match(normalized)
        if match is None:
            continue
        groups = match.groups()
        token = groups[-2] if groups[-1] and groups[-1].isdigit() else groups[-1]
        if token in {"+", "P", "DP"}:
            polarity = "P"
        elif token in {"-", "N", "DN"}:
            polarity = "N"
        else:
            continue
        base = normalized[: match.start(len(groups) if token in {"+", "-", "P", "N", "DP", "DN"} else 0)]
        if len(groups) >= 4 and groups[1] in {"TX", "RX"}:
            base = f"{groups[0]}_{groups[1]}{groups[3]}"
        elif token in {"DP", "DN"}:
            base = groups[0]
        elif token in {"P", "N"} and len(groups) >= 2:
            base = groups[0]
        base = re.sub(r"[_/-]+$", "", base)
        if base:
            return base, polarity
    return None


def _diff_pair_family(base: str) -> str:
    for token, family in (
        ("PCIE", "pcie"),
        ("USB", "usb"),
        ("LVDS", "lvds"),
        ("MIPI", "mipi"),
        ("DSI", "mipi"),
        ("CSI", "mipi"),
        ("EDP", "edp"),
        ("HDMI", "hdmi"),
        ("SATA", "sata"),
        ("ETH", "ethernet"),
        ("REFCLK", "clock"),
        ("CLK", "clock"),
        ("DATA", "high_speed_data"),
        ("D", "generic_diff"),
    ):
        if token in base:
            return family
    return "generic_diff"


def _high_speed_pair_profile(tracks: tuple[Any, ...]) -> tuple[tuple[str, ...], ...]:
    from tasks.source_backed_task import _net_role

    track_groups: dict[tuple[str, str], list[Any]] = {}
    signal_tracks_by_net: dict[str, list[Any]] = {}
    for track in tracks:
        if _net_role(track.net) != "signal":
            continue
        signal_tracks_by_net.setdefault(track.net, []).append(track)
        key = _diff_pair_key(track.net)
        if key is None:
            continue
        track_groups.setdefault(key, []).append(track)

    profile: list[tuple[str, ...]] = []

    def pair_record(family: str, positive_tracks: list[Any], negative_tracks: list[Any]) -> tuple[str, ...] | None:
        if not positive_tracks or not negative_tracks:
            return None

        def stats(group: list[Any]) -> tuple[float, float, float]:
            length = sum(_track_length_mm(track) for track in group)
            width = sum(max(float(getattr(track, "width", 0.25) or 0.25), 0.05) for track in group) / len(group)
            z0_values = [
                _trace_rlc(
                    _track_length_mm(track),
                    max(float(getattr(track, "width", 0.25) or 0.25), 0.05),
                    track.layer,
                )[3]
                for track in group
            ]
            z0 = sum(z0_values) / len(z0_values)
            return length, width, z0

        positive_length, positive_width, positive_z0 = stats(positive_tracks)
        negative_length, negative_width, negative_z0 = stats(negative_tracks)
        average_length = 0.5 * (positive_length + negative_length)
        skew_ratio = abs(positive_length - negative_length) / max(average_length, 0.001)
        average_width = 0.5 * (positive_width + negative_width)
        average_z0 = 0.5 * (positive_z0 + negative_z0)
        closest_spacing: float | None = None
        for positive in positive_tracks:
            positive_width_mm = max(float(getattr(positive, "width", 0.25) or 0.25), 0.05)
            for negative in negative_tracks:
                if positive.layer != negative.layer:
                    continue
                negative_width_mm = max(float(getattr(negative, "width", 0.25) or 0.25), 0.05)
                edge_spacing = _segment_distance_mm(positive.start, positive.end, negative.start, negative.end) - 0.5 * (positive_width_mm + negative_width_mm)
                closest_spacing = edge_spacing if closest_spacing is None else min(closest_spacing, edge_spacing)
        return (
            family,
            _length_bucket(average_length),
            _skew_bucket(skew_ratio),
            _width_bucket(average_width),
            _z0_bucket(average_z0),
            _spacing_bucket(closest_spacing),
        )

    paired_nets: set[str] = set()
    bases = sorted({base for base, _polarity in track_groups})
    for base in bases:
        positive_tracks = track_groups.get((base, "P"), [])
        negative_tracks = track_groups.get((base, "N"), [])
        record = pair_record(_diff_pair_family(base), positive_tracks, negative_tracks)
        if record is not None:
            profile.append(record)
            paired_nets.update(track.net for track in positive_tracks + negative_tracks)

    candidates = [
        (net, group)
        for net, group in signal_tracks_by_net.items()
        if net not in paired_nets and sum(_track_length_mm(track) for track in group) >= 2.0
    ]
    generic_pairs: list[tuple[float, str, str, list[Any], list[Any]]] = []
    for left_index, (left_net, left_tracks) in enumerate(candidates):
        for right_net, right_tracks in candidates[left_index + 1 :]:
            closest_spacing: float | None = None
            for left_track in left_tracks:
                left_width = max(float(getattr(left_track, "width", 0.25) or 0.25), 0.05)
                for right_track in right_tracks:
                    if left_track.layer != right_track.layer:
                        continue
                    right_width = max(float(getattr(right_track, "width", 0.25) or 0.25), 0.05)
                    edge_spacing = _segment_distance_mm(left_track.start, left_track.end, right_track.start, right_track.end) - 0.5 * (left_width + right_width)
                    closest_spacing = edge_spacing if closest_spacing is None else min(closest_spacing, edge_spacing)
            if closest_spacing is None or closest_spacing > 1.0:
                continue
            left_length = sum(_track_length_mm(track) for track in left_tracks)
            right_length = sum(_track_length_mm(track) for track in right_tracks)
            skew = abs(left_length - right_length) / max(0.001, 0.5 * (left_length + right_length))
            if skew > 0.35:
                continue
            generic_pairs.append((closest_spacing, left_net, right_net, left_tracks, right_tracks))
    for _spacing, left_net, right_net, left_tracks, right_tracks in sorted(generic_pairs)[:16]:
        if left_net in paired_nets or right_net in paired_nets:
            continue
        record = pair_record("generic_diff", left_tracks, right_tracks)
        if record is not None:
            profile.append(record)
            paired_nets.update((left_net, right_net))
    return tuple(sorted(profile))


def _member_net_role(board: Any, member: str) -> tuple[str, str] | None:
    from tasks.source_backed_task import _net_role

    if "." not in member:
        return None
    reference, pad_name = member.split(".", 1)
    footprint = board.footprints.get(reference)
    if footprint is None:
        return None
    pad = footprint.pads.get(pad_name)
    if pad is None:
        return None
    return pad.net, _net_role(pad.net)


def _interface_references(board: Any) -> tuple[str, ...]:
    from tasks.source_backed_task import _boundary_references, _natural_sort_key, _reference_prefix

    references = set(_boundary_references(board))
    for reference, footprint in board.footprints.items():
        if _reference_prefix(reference) == "K" and len(footprint.pads) >= 2:
            references.add(reference)
    return tuple(sorted(references, key=_natural_sort_key))


def _interface_members(board: Any, references: tuple[str, ...]) -> tuple[tuple[str, str, str], ...]:
    from tasks.source_backed_task import _natural_sort_key, _net_role

    members: list[tuple[str, str, str]] = []
    for reference in references:
        footprint = board.footprints.get(reference)
        if footprint is None:
            continue
        for pad_name, pad in sorted(footprint.pads.items(), key=lambda item: _natural_sort_key(item[0])):
            role = _net_role(pad.net)
            if not pad.net or role == "unconnected":
                continue
            members.append((f"{reference}.{pad_name}", pad.net, role))
    return tuple(members)


def _ratio_score(passed: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return max(0.0, min(1.0, passed / total))


def _known_io_verification_signature(task: TaskSpec, board: Any, reference_board: Any) -> KnownIoVerificationSignature:
    from tasks.source_backed_task import _natural_sort_key, _net_role

    interface_refs = _interface_references(reference_board)
    reference_members = _interface_members(reference_board, interface_refs)
    member_names = tuple(member for member, _net, _role in reference_members)
    checks: list[KnownIoCheck] = []

    present = 0
    role_checked = 0
    role_passed = 0
    submission_member_info: dict[str, tuple[str, str] | None] = {}
    for member, _reference_net, reference_role in reference_members:
        info = _member_net_role(board, member)
        submission_member_info[member] = info
        if info is not None and info[0] and info[1] != "unconnected":
            present += 1
        if reference_role == "ground" or reference_role.startswith("power_"):
            role_checked += 1
            if info is not None and _role_family(info[1]) == _role_family(reference_role):
                role_passed += 1
        elif reference_role == "signal":
            role_checked += 1
            if info is not None and info[1] == "signal":
                role_passed += 1
    checks.append(
        KnownIoCheck(
            name="reference_interface_pads_present",
            score=_ratio_score(present, len(reference_members)),
            detail=f"{present}/{len(reference_members)} reference external pads exist and are connected",
        )
    )
    checks.append(
        KnownIoCheck(
            name="reference_interface_pad_roles",
            score=_ratio_score(role_passed, role_checked),
            detail=f"{role_passed}/{role_checked} external pads preserve signal/power/ground roles",
        )
    )

    groups_by_net: dict[str, list[str]] = {}
    group_roles: dict[str, str] = {}
    for member, net, role in reference_members:
        groups_by_net.setdefault(net, []).append(member)
        group_roles.setdefault(net, role)
    groups = [
        (net, tuple(sorted(members, key=_natural_sort_key)), group_roles[net])
        for net, members in groups_by_net.items()
    ]
    groups.sort(key=lambda item: (_net_role(item[0]), item[1]))

    continuity_passed = 0
    continuity_total = 0
    for _net, members, _role in groups:
        if len(members) < 2:
            continue
        continuity_total += 1
        submission_nets = {
            submission_member_info.get(member, ("", ""))[0]
            for member in members
            if submission_member_info.get(member) is not None
        }
        if len(submission_nets) == 1 and "" not in submission_nets:
            continuity_passed += 1
    checks.append(
        KnownIoCheck(
            name="reference_external_net_continuity",
            score=_ratio_score(continuity_passed, continuity_total),
            detail=f"{continuity_passed}/{continuity_total} multi-pad external reference nets remain continuous",
        )
    )

    isolation_passed = 0
    isolation_total = 0
    max_isolation_pairs = 800
    for left_index, (_left_net, left_members, _left_role) in enumerate(groups):
        left_submission_nets = {
            submission_member_info.get(member, ("", ""))[0]
            for member in left_members
            if submission_member_info.get(member) is not None
        }
        left_submission_nets.discard("")
        for _right_net, right_members, _right_role in groups[left_index + 1 :]:
            if isolation_total >= max_isolation_pairs:
                break
            right_submission_nets = {
                submission_member_info.get(member, ("", ""))[0]
                for member in right_members
                if submission_member_info.get(member) is not None
            }
            right_submission_nets.discard("")
            isolation_total += 1
            if left_submission_nets and right_submission_nets and left_submission_nets.isdisjoint(right_submission_nets):
                isolation_passed += 1
        if isolation_total >= max_isolation_pairs:
            break
    checks.append(
        KnownIoCheck(
            name="reference_external_net_isolation",
            score=_ratio_score(isolation_passed, isolation_total),
            detail=f"{isolation_passed}/{isolation_total} distinct reference external nets remain isolated",
        )
    )

    # Exact refdes/pad assertions are retained for diagnostics. Functional
    # scoring uses the refdes-invariant contract and simulation profiles below.
    difficulty_weight = 2.0 if task.difficulty in {"very easy", "easy"} else 1.0
    weighted_score = (
        difficulty_weight * checks[0].score
        + difficulty_weight * checks[1].score
        + 2.0 * difficulty_weight * checks[2].score
        + checks[3].score
    ) / (4.0 * difficulty_weight + 1.0)
    return KnownIoVerificationSignature(
        task_id=task.task_id,
        interface_refs=interface_refs,
        reference_members=member_names,
        checks=tuple(checks),
        score=weighted_score,
    )


def build_static_io_contract(task: TaskSpec, board: Any) -> dict[str, Any]:
    selected_ports = tuple(_interface_members(board, _interface_references(board)))
    external_net_routes = _external_net_route_counter(board)
    semantic_external_nets = _external_semantic_net_counter(board)
    external_role_inventory = _external_role_inventory_counter(board)
    realized_external_copper = _realized_external_copper_counter(board)
    external_net_degrees = _external_net_degree_counter(board)
    external_nets = {net for _member, net, _role in selected_ports if net}
    selected_tracks = _selected_geometry_tracks(board, external_nets)
    impedance_profile: Counter[tuple[str, ...]] = Counter()
    for track in selected_tracks:
        from tasks.source_backed_task import _net_role

        length_mm = _track_length_mm(track)
        width_mm = max(float(getattr(track, "width", 0.25) or 0.25), 0.05)
        _resistance, _inductance, _capacitance, z0, _delay_s = _trace_rlc(length_mm, width_mm, track.layer)
        impedance_profile[(_role_family(_net_role(track.net)), track.layer, _length_bucket(length_mm), _z0_bucket(z0))] += 1
    high_speed_pair_profile = Counter(_high_speed_pair_profile(selected_tracks))
    health = _external_io_health_summary(board)
    return {
        "schema_version": 3,
        "task_id": task.task_id,
        "contract_kind": "refdes_invariant_external_io_function_and_pcb_health",
        "external_net_count": health["external_net_count"],
        "external_interface_ref_count": len(_interface_references(board)),
        "external_connected_pad_count": len(selected_ports),
        "routed_external_net_count": health["routed_external_net_count"],
        "selected_geometry_track_count": len(selected_tracks),
        "external_role_inventory_profile": _counter_to_records(external_role_inventory),
        "semantic_external_net_profile": _counter_to_records(semantic_external_nets),
        "external_net_route_profile": _counter_to_records(external_net_routes),
        "realized_external_copper_profile": _counter_to_records(realized_external_copper),
        "external_net_degree_profile": _counter_to_records(external_net_degrees),
        "impedance_profile": _counter_to_records(impedance_profile),
        "high_speed_pair_profile": _counter_to_records(high_speed_pair_profile),
        "high_speed_pair_family_profile": _counter_to_records(_high_speed_family_counter(high_speed_pair_profile)),
        "minimum_external_io_health": {
            "route_coverage_score": 0.95 if health["external_net_count"] >= 4 else 1.0,
            "continuity_score": 1.0,
            "attachment_score": 0.95,
            "short_safety_score": 1.0,
        },
    }


def build_functional_io_contract(task: TaskSpec, board: Any) -> dict[str, Any]:
    required_families = _required_interface_families_from_task(task)
    health = _external_io_health_summary(board)
    reference_interface_families = _external_net_family_counter(board)
    reference_routed_families = _routed_external_net_family_counter(board)
    observed_family_names = {key[0] for key, count in reference_interface_families.items() if key and count > 0}
    routed_family_names = {key[0] for key, count in reference_routed_families.items() if key and count > 0}
    scored_families = tuple(family for family in required_families if family in observed_family_names)
    scored_routed_families = tuple(family for family in scored_families if family in routed_family_names) or tuple(
        family for family in required_families if family in routed_family_names
    )
    functional = _task_functional_score(
        task,
        board,
        scored_families,
        health,
        routed_required_families=scored_routed_families,
    )
    return {
        "schema_version": 1,
        "task_id": task.task_id,
        "contract_kind": "task_semantic_external_io_function",
        "required_interface_families": list(required_families),
        "scored_interface_families": list(scored_families),
        "scored_routed_interface_families": list(scored_routed_families),
        "reference_interface_family_profile": _counter_to_records(reference_interface_families),
        "reference_external_net_family_profile": _counter_to_records(_external_net_family_counter(board)),
        "reference_routed_external_net_family_profile": _counter_to_records(reference_routed_families),
        "reference_functional_summary": functional,
    }


def _load_static_io_contract(task: TaskSpec, source_metadata: dict[str, Any], reference_board: Any) -> dict[str, Any]:
    contract_candidates: list[Path] = []
    for metadata_key in ("io_contract", "io_contract_path"):
        metadata_value = source_metadata.get(metadata_key)
        if not metadata_value:
            continue
        contract_path = Path(str(metadata_value))
        if not contract_path.is_absolute():
            contract_path = task.task_dir / contract_path
        contract_candidates.append(contract_path)
    contract_candidates.append(task.task_dir / "io_contract.json")
    for contract_path in contract_candidates:
        if contract_path.exists():
            try:
                payload = json.loads(contract_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and int(payload.get("schema_version", 0)) >= 1:
                return payload
    return build_static_io_contract(task, reference_board)


def _load_functional_io_contract(task: TaskSpec, source_metadata: dict[str, Any], reference_board: Any) -> dict[str, Any]:
    contract_candidates: list[Path] = []
    for metadata_key in ("functional_contract", "functional_contract_path"):
        metadata_value = source_metadata.get(metadata_key)
        if not metadata_value:
            continue
        contract_path = Path(str(metadata_value))
        if not contract_path.is_absolute():
            contract_path = task.task_dir / contract_path
        contract_candidates.append(contract_path)
    contract_candidates.append(task.task_dir / "functional_contract.json")
    for contract_path in contract_candidates:
        if contract_path.exists():
            try:
                payload = json.loads(contract_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and int(payload.get("schema_version", 0)) >= 1:
                return payload
    return build_functional_io_contract(task, reference_board)


def _behavioral_model_lines(
    board: Any,
    node_for_member: dict[str, str],
    boundary_refs: set[str],
    port_nodes: set[str],
) -> tuple[list[str], Counter[str]]:
    from tasks.source_backed_task import _net_role, _reference_prefix

    lines: list[str] = []
    summary: Counter[str] = Counter()
    model_index = 0
    for reference, footprint in sorted(board.footprints.items()):
        connected = [
            (pad_name, pad, node_for_member.get(f"{reference}.{pad_name}"))
            for pad_name, pad in sorted(footprint.pads.items())
            if pad.net and _net_role(pad.net) != "unconnected"
        ]
        connected = [(pad_name, pad, node) for pad_name, pad, node in connected if node]
        unique_nodes = tuple(dict.fromkeys(node for _pad_name, _pad, node in connected))
        if len(unique_nodes) < 1:
            continue
        prefix = _reference_prefix(reference)
        if len(unique_nodes) == 2:
            left, right = unique_nodes
            if prefix == "R":
                resistance = _loose_numeric_value(footprint.value, kind="resistance") or 10_000.0
                lines.append(f"RDEV{model_index} {left} {right} {_spice_value(max(1e-3, resistance))}")
                summary["resistor"] += 1
                model_index += 1
                continue
            if prefix == "C":
                lines.append(f"RCAP{model_index} {left} {right} 1e6")
                summary["capacitor"] += 1
                model_index += 1
                continue
            if prefix in {"L", "FB", "F"}:
                lines.append(f"RFERRITE{model_index} {left} {right} 0.05")
                summary["inductor_or_ferrite"] += 1
                model_index += 1
                continue
            if prefix in {"D", "LED"}:
                lines.append(f"RDIODE{model_index} {left} {right} 100k")
                summary["diode"] += 1
                model_index += 1
                continue

        if reference in boundary_refs or len(unique_nodes) < 2:
            continue

        signal_nodes = []
        power_nodes = []
        ground_nodes = []
        for _pad_name, pad, node in connected:
            role = _net_role(pad.net)
            if role == "ground":
                ground_nodes.append(node)
            elif role.startswith("power_"):
                power_nodes.append(node)
            else:
                signal_nodes.append(node)
        unique_signal_nodes = list(dict.fromkeys(signal_nodes))
        signal_nodes = [
            *[node for node in unique_signal_nodes if node in port_nodes],
            *[node for node in unique_signal_nodes if node not in port_nodes],
        ][:32]
        power_nodes = list(dict.fromkeys(power_nodes))
        ground_nodes = list(dict.fromkeys(ground_nodes))
        if power_nodes and ground_nodes:
            lines.append(f"RICDEC{model_index} {power_nodes[0]} {ground_nodes[0]} 1e6")
            summary["generic_power_decoupling"] += 1
            model_index += 1
        for node in signal_nodes:
            if power_nodes:
                resistance = 20_000.0 + 180_000.0 * _stable_unit_interval(reference, node, "pull")
                lines.append(f"RICBIAS{model_index} {node} {power_nodes[0]} {_spice_value(resistance)}")
                model_index += 1
        for left_index, left in enumerate(signal_nodes):
            for right in signal_nodes[left_index + 1 :]:
                resistance = 1_000.0 + 49_000.0 * _stable_unit_interval(reference, left, right)
                lines.append(f"RICPATH{model_index} {left} {right} {_spice_value(resistance)}")
                summary["generic_ic_signal_path"] += 1
                model_index += 1
    return lines, summary


def _write_behavioral_transient_netlist(board: Any, path: Path) -> tuple[tuple[Any, ...], tuple[Any, ...], dict[str, int], dict[str, str]]:
    from tasks.source_backed_task import (
        SPICE_LEAK_RESISTANCE_OHMS,
        SPICE_PAD_RESISTANCE_OHMS,
        _boundary_references,
        _natural_sort_key,
        _realized_copper_graph,
        _selected_spice_pad_nets,
        _spice_net_name,
        SpicePort,
    )

    realized_graph = _realized_copper_graph(board, connect_logical_nets=True)
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
    drivers = tuple(port for port in ports if port.role != "ground") or ports
    realized_nodes = sorted(
        set(realized_graph.pad_nodes.values()) | {port.node for port in ports if port.node},
        key=_natural_sort_key,
    )
    spice_nodes = {node: ("0" if node == "0" else _spice_net_name(index + 1)) for index, node in enumerate(realized_nodes)}
    node_for_member = {
        member: spice_nodes.get(node, _spice_net_name(len(spice_nodes) + index + 1))
        for index, (member, node) in enumerate(sorted(realized_graph.pad_nodes.items()))
    }
    model_lines, model_summary = _behavioral_model_lines(
        board,
        node_for_member,
        set(_boundary_references(board)),
        {spice_nodes[port.node] for port in ports if port.node in spice_nodes},
    )

    lines = [
        "* EDA Bench behavioral transient I/O simulation",
        "* External ports receive current-pulse stimuli; all port voltages are probed.",
        "* Generic behavioral models are deterministic model assumptions, not scoring features.",
        ".option noacct method=gear rshunt=1e12 gmin=1e-12",
        ".model DGEN D(Is=1e-12 Rs=0.5 Cjo=2p)",
    ]
    for index, port in enumerate(ports):
        internal = spice_nodes[port.node]
        external = f"p{index}"
        lines.append(f"RPAD{index} {external} {internal} {_spice_value(SPICE_PAD_RESISTANCE_OHMS)}")
        if port.role == "ground":
            lines.append(f"RGND{index} {external} 0 0.001")
        elif port.role.startswith("power_"):
            lines.append(f"RPTERM{index} {external} 0 1000000")
        elif port.role == "signal":
            lines.append(f"RSTERM{index} {external} 0 100000")
        lines.append(f"RPLEAK{index} {external} 0 {_spice_value(SPICE_LEAK_RESISTANCE_OHMS)}")
    lines.extend(model_lines)
    for index, node in enumerate(sorted(set(spice_nodes.values()), key=_natural_sort_key)):
        if node != "0":
            lines.append(f"RNLEAK{index} {node} 0 {_spice_value(SPICE_LEAK_RESISTANCE_OHMS)}")

    window_us = 12.0
    edge_us = 0.1
    sample_offsets = {"early": 2.0, "mid": 6.0, "late": 10.0}
    for driver_index, driver in enumerate(drivers):
        port_index = ports.index(driver)
        node = f"p{port_index}"
        start = driver_index * window_us + 1.0
        stop = start + 8.0
        amplitude = -0.001 if not driver.role.startswith("power_") else -0.02
        lines.append(
            f"ISTIM{driver_index} {node} 0 PWL(0 0 {start:.3f}u 0 "
            f"{start + edge_us:.3f}u {_spice_value(amplitude)} {stop:.3f}u {_spice_value(amplitude)} "
            f"{stop + edge_us:.3f}u 0)"
        )
    total_us = max(window_us, len(drivers) * window_us + 2.0)
    step_us = 0.25
    lines.extend([".control", "set noaskquit", f"tran {step_us:.3f}u {total_us:.3f}u"])
    measure_names: dict[str, str] = {}
    for driver_index, driver in enumerate(drivers):
        base = driver_index * window_us + 1.0
        for sample_name, offset in sample_offsets.items():
            sample_time = base + offset
            for port_index, observed in enumerate(ports):
                measure_name = f"m_{driver_index}_{port_index}_{sample_name}"
                measure_names[measure_name] = f"{driver.member}|{observed.member}|{sample_name}"
                lines.append(f"meas tran {measure_name} find v(p{port_index}) at={sample_time:.3f}u")
    lines.extend(["quit", ".endc", ".end"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    model_summary["ports"] = len(ports)
    model_summary["drivers"] = len(drivers)
    return ports, drivers, dict(model_summary), measure_names


def _parse_behavioral_measures(output: str, measure_names: dict[str, str]) -> tuple[BehavioralTracePoint, ...]:
    traces: list[BehavioralTracePoint] = []
    measure_re = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
    for line in output.splitlines():
        match = measure_re.search(line.strip())
        if match is None:
            continue
        name, raw_value = match.groups()
        spec = measure_names.get(name.lower()) or measure_names.get(name)
        if spec is None:
            continue
        driver, observed, sample = spec.split("|", 2)
        traces.append(
            BehavioralTracePoint(
                driver=driver,
                observed=observed,
                sample=sample,
                voltage=float(raw_value),
            )
        )
    return tuple(traces)


def _simulate_behavioral_io_signature(board: Any, work_dir: Path, *, label: str) -> BehavioralSimulationSignature:
    spice_dir = work_dir / "behavioral_spice"
    spice_dir.mkdir(parents=True, exist_ok=True)
    netlist_path = spice_dir / f"{label}.cir"
    output_path = spice_dir / f"{label}.log"
    ports, drivers, model_summary, measure_names = _write_behavioral_transient_netlist(board, netlist_path)
    if not ports:
        output_path.write_text("No connected external ports selected.\n", encoding="utf-8")
        return BehavioralSimulationSignature(ports, drivers, (), model_summary, False, "no declared I/O ports", str(netlist_path), str(output_path))
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        message = "ngspice not found on PATH"
        output_path.write_text(message + "\n", encoding="utf-8")
        return BehavioralSimulationSignature(ports, drivers, (), model_summary, False, message, str(netlist_path), str(output_path))
    try:
        with tempfile.TemporaryDirectory(prefix="eda_behavioral_spice_") as tmp:
            proc = subprocess.run(
                [ngspice, "-b", "-n", str(netlist_path)],
                cwd=tmp,
                check=False,
                capture_output=True,
                text=True,
                timeout=90,
            )
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(str(part) for part in (exc.stdout, exc.stderr) if part)
        message = "ngspice timed out after 90 seconds"
        output_path.write_text(f"{message}\n{output}", encoding="utf-8")
        return BehavioralSimulationSignature(ports, drivers, (), model_summary, False, message, str(netlist_path), str(output_path))
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    output_path.write_text(output, encoding="utf-8")
    if proc.returncode != 0:
        return BehavioralSimulationSignature(
            ports,
            drivers,
            (),
            model_summary,
            False,
            f"ngspice exited with {proc.returncode}",
            str(netlist_path),
            str(output_path),
        )
    traces = _parse_behavioral_measures(output, measure_names)
    expected = len(measure_names)
    if len(traces) != expected:
        return BehavioralSimulationSignature(
            ports,
            drivers,
            traces,
            model_summary,
            False,
            f"parsed {len(traces)} of {expected} expected transient measurements",
            str(netlist_path),
            str(output_path),
        )
    return BehavioralSimulationSignature(ports, drivers, traces, model_summary, True, "", str(netlist_path), str(output_path))


def _point_key_mm(point: Any) -> tuple[int, int]:
    return (round(float(point.x) * 1000.0), round(float(point.y) * 1000.0))


def _distance_mm(left: Any, right: Any) -> float:
    return math.hypot(float(left.x) - float(right.x), float(left.y) - float(right.y))


def _track_length_mm(track: Any) -> float:
    return _distance_mm(track.start, track.end)


def _segment_point_distance_mm(point: Any, left: Any, right: Any) -> float:
    dx = float(right.x) - float(left.x)
    dy = float(right.y) - float(left.y)
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-18:
        return _distance_mm(point, left)
    t = ((float(point.x) - float(left.x)) * dx + (float(point.y) - float(left.y)) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    projected_x = float(left.x) + t * dx
    projected_y = float(left.y) + t * dy
    return math.hypot(float(point.x) - projected_x, float(point.y) - projected_y)


def _orientation(a: Any, b: Any, c: Any) -> float:
    return (float(b.x) - float(a.x)) * (float(c.y) - float(a.y)) - (float(b.y) - float(a.y)) * (float(c.x) - float(a.x))


def _on_segment(left: Any, point: Any, right: Any) -> bool:
    epsilon = 1e-9
    if abs(_orientation(left, point, right)) > epsilon:
        return False
    return (
        min(float(left.x), float(right.x)) - epsilon <= float(point.x) <= max(float(left.x), float(right.x)) + epsilon
        and min(float(left.y), float(right.y)) - epsilon <= float(point.y) <= max(float(left.y), float(right.y)) + epsilon
    )


def _segments_intersect(left: Any, right: Any, other_left: Any, other_right: Any) -> bool:
    o1 = _orientation(left, right, other_left)
    o2 = _orientation(left, right, other_right)
    o3 = _orientation(other_left, other_right, left)
    o4 = _orientation(other_left, other_right, right)
    epsilon = 1e-9
    if abs(o1) <= epsilon and _on_segment(left, other_left, right):
        return True
    if abs(o2) <= epsilon and _on_segment(left, other_right, right):
        return True
    if abs(o3) <= epsilon and _on_segment(other_left, left, other_right):
        return True
    if abs(o4) <= epsilon and _on_segment(other_left, right, other_right):
        return True
    return ((o1 < 0.0) != (o2 < 0.0)) and ((o3 < 0.0) != (o4 < 0.0))


def _segment_distance_mm(left: Any, right: Any, other_left: Any, other_right: Any) -> float:
    if _segments_intersect(left, right, other_left, other_right):
        return 0.0
    return min(
        _segment_point_distance_mm(left, other_left, other_right),
        _segment_point_distance_mm(right, other_left, other_right),
        _segment_point_distance_mm(other_left, left, right),
        _segment_point_distance_mm(other_right, left, right),
    )


def _track_bbox(track: Any, margin_mm: float = 0.0) -> tuple[float, float, float, float]:
    half_width = max(float(getattr(track, "width", 0.25) or 0.25), 0.05) * 0.5 + margin_mm
    return (
        min(float(track.start.x), float(track.end.x)) - half_width,
        min(float(track.start.y), float(track.end.y)) - half_width,
        max(float(track.start.x), float(track.end.x)) + half_width,
        max(float(track.start.y), float(track.end.y)) + half_width,
    )


def _bboxes_overlap(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> bool:
    return not (left[2] < right[0] or right[2] < left[0] or left[3] < right[1] or right[3] < left[1])


def _layer_dielectric_height_mm(layer: str) -> float:
    if layer in {"F.Cu", "B.Cu"}:
        return 0.18
    return 0.25


def _trace_rlc(length_mm: float, width_mm: float, layer: str) -> tuple[float, float, float, float, float]:
    length_m = max(length_mm, 0.001) * 1e-3
    width_m = max(width_mm, 0.05) * 1e-3
    height_m = _layer_dielectric_height_mm(layer) * 1e-3
    copper_thickness_m = 35e-6
    er = 4.2
    ratio = max(width_m / height_m, 0.05)
    effective_er = (er + 1.0) / 2.0 + (er - 1.0) / 2.0 / math.sqrt(1.0 + 12.0 / ratio)
    if ratio <= 1.0:
        z0 = 60.0 / math.sqrt(effective_er) * math.log(8.0 / ratio + 0.25 * ratio)
    else:
        z0 = 120.0 * math.pi / (math.sqrt(effective_er) * (ratio + 1.393 + 0.667 * math.log(ratio + 1.444)))
    z0 = max(12.0, min(180.0, z0))
    delay_s = length_m * math.sqrt(effective_er) / 299_792_458.0
    resistance = max(1e-4, 1.724e-8 * length_m / (width_m * copper_thickness_m))
    inductance = max(1e-12, z0 * delay_s)
    capacitance = max(1e-15, delay_s / z0)
    return resistance, inductance, capacitance, z0, delay_s


def _z0_bucket(z0: float) -> str:
    return f"{round(z0 / 10.0) * 10:.0f}ohm"


def _length_bucket(length_mm: float) -> str:
    if length_mm < 2.0:
        return "lt2mm"
    if length_mm < 10.0:
        return "2to10mm"
    if length_mm < 50.0:
        return "10to50mm"
    return "gte50mm"


def _selected_geometry_tracks(board: Any, port_nets: set[str], *, max_tracks: int = 320) -> tuple[Any, ...]:
    from tasks.source_backed_task import _natural_sort_key, _net_role

    tracks = [
        track
        for track in board.tracks
        if track.net in port_nets and _net_role(track.net) != "unconnected" and _track_length_mm(track) > 0.001
    ]
    role_rank = {"signal": 0, "power": 1, "ground": 2}

    def sort_key(track: Any) -> tuple[Any, ...]:
        role = _net_role(track.net)
        family = "power" if role.startswith("power_") else role
        return (role_rank.get(family, 3), _natural_sort_key(track.net), -_track_length_mm(track), track.layer)

    return tuple(sorted(tracks, key=sort_key)[:max_tracks])


def _external_same_layer_short_profile(board: Any, *, max_tracks: int = 900) -> Counter[tuple[str, str]]:
    from tasks.source_backed_task import _net_role

    external_nets = set(_external_net_pad_roles(board))
    tracks = [
        track
        for track in board.tracks
        if track.net in external_nets and _net_role(track.net) != "unconnected" and _track_length_mm(track) > 0.001
    ]
    tracks = sorted(tracks, key=lambda track: (_role_family(_net_role(track.net)), track.net, track.layer, -_track_length_mm(track)))[:max_tracks]
    bboxes = [_track_bbox(track) for track in tracks]
    profile: Counter[tuple[str, str]] = Counter()
    for left_index, left_track in enumerate(tracks):
        left_role = _role_family(_net_role(left_track.net))
        left_width = max(float(getattr(left_track, "width", 0.25) or 0.25), 0.05)
        for right_track, right_bbox in zip(tracks[left_index + 1 :], bboxes[left_index + 1 :], strict=False):
            if left_track.net == right_track.net or left_track.layer != right_track.layer:
                continue
            if not _bboxes_overlap(bboxes[left_index], right_bbox):
                continue
            right_width = max(float(getattr(right_track, "width", 0.25) or 0.25), 0.05)
            distance = _segment_distance_mm(left_track.start, left_track.end, right_track.start, right_track.end)
            if distance <= 0.5 * (left_width + right_width):
                right_role = _role_family(_net_role(right_track.net))
                profile[tuple(sorted((left_role, right_role)))] += 1
    return profile


def _board_same_layer_short_profile(board: Any, *, max_tracks: int = 1400) -> Counter[tuple[str, str]]:
    from tasks.source_backed_task import _net_role

    tracks = [
        track
        for track in board.tracks
        if track.net and _net_role(track.net) != "unconnected" and _track_length_mm(track) > 0.001
    ]
    tracks = sorted(tracks, key=lambda track: (_role_family(_net_role(track.net)), track.net, track.layer, -_track_length_mm(track)))[:max_tracks]
    bboxes = [_track_bbox(track) for track in tracks]
    profile: Counter[tuple[str, str]] = Counter()
    for left_index, left_track in enumerate(tracks):
        left_role = _role_family(_net_role(left_track.net))
        left_width = max(float(getattr(left_track, "width", 0.25) or 0.25), 0.05)
        for right_track, right_bbox in zip(tracks[left_index + 1 :], bboxes[left_index + 1 :], strict=False):
            if left_track.net == right_track.net or left_track.layer != right_track.layer:
                continue
            if not _bboxes_overlap(bboxes[left_index], right_bbox):
                continue
            right_width = max(float(getattr(right_track, "width", 0.25) or 0.25), 0.05)
            distance = _segment_distance_mm(left_track.start, left_track.end, right_track.start, right_track.end)
            if distance <= 0.5 * (left_width + right_width):
                right_role = _role_family(_net_role(right_track.net))
                profile[tuple(sorted((left_role, right_role)))] += 1
    return profile


def _short_safety_summary(short_profile: Counter[tuple[str, str]]) -> dict[str, Any]:
    power_ground_shorts = sum(count for key, count in short_profile.items() if set(key) == {"ground", "power"})
    power_signal_shorts = sum(
        count
        for key, count in short_profile.items()
        if set(key) in ({"power", "signal"}, {"ground", "signal"})
    )
    signal_signal_shorts = sum(count for key, count in short_profile.items() if key == ("signal", "signal"))
    short_penalty = min(1.0, power_ground_shorts + 0.5 * power_signal_shorts + 0.2 * signal_signal_shorts)
    return {
        "same_layer_short_profile": dict(sorted(short_profile.items())),
        "power_ground_short_count": power_ground_shorts,
        "power_signal_or_ground_signal_short_count": power_signal_shorts,
        "signal_signal_short_count": signal_signal_shorts,
        "short_safety_score": 1.0 - short_penalty,
    }


def _write_pcb_geometry_transient_netlist(board: Any, path: Path) -> tuple[tuple[Any, ...], tuple[Any, ...], dict[str, int], dict[str, str], tuple[tuple[str, ...], ...], tuple[tuple[str, ...], ...], tuple[tuple[str, ...], ...]]:
    from tasks.source_backed_task import (
        SPICE_LEAK_RESISTANCE_OHMS,
        SPICE_PAD_RESISTANCE_OHMS,
        _natural_sort_key,
        _net_role,
        _realized_copper_graph,
        _selected_spice_pad_nets,
        SpicePort,
    )

    selected_pads = _selected_spice_pad_nets(board)
    realized_graph = _realized_copper_graph(board)
    ports = tuple(
        SpicePort(
            member=pad.member,
            role=pad.role,
            net=pad.net,
            node=realized_graph.pad_nodes.get(pad.member, f"isolated:{pad.member}"),
        )
        for pad in selected_pads
    )
    drivers = tuple(port for port in ports if port.role != "ground") or ports
    port_nets = {port.net for port in ports if port.net}
    tracks = _selected_geometry_tracks(board, port_nets)
    high_speed_pair_profile = _high_speed_pair_profile(tracks)
    node_names: dict[tuple[str, str, tuple[int, int]], str] = {}

    def node_for(net: str, layer: str, point: Any) -> str:
        key = (net, layer, _point_key_mm(point))
        node = node_names.get(key)
        if node is None:
            node = f"g{len(node_names) + 1}"
            node_names[key] = node
        return node

    lines = [
        "* EDA Bench PCB-geometry transient simulation",
        "* Routed copper is modeled as width/length/layer-derived R/L/C parasitics.",
        "* Same-layer trace intersections between different nets are modeled as low-ohm shorts.",
        "* Close parallel routed segments are modeled with deterministic coupling capacitance.",
        ".option noacct method=gear rshunt=1e12 gmin=1e-12",
    ]
    impedance_profile: list[tuple[str, ...]] = []
    collision_profile: list[tuple[str, ...]] = []
    model_summary: Counter[str] = Counter()

    track_nodes: list[tuple[Any, str, str, tuple[float, float, float, float]]] = []
    for index, track in enumerate(tracks):
        start_node = node_for(track.net, track.layer, track.start)
        end_node = node_for(track.net, track.layer, track.end)
        mid_node = f"gm{index}"
        length_mm = _track_length_mm(track)
        width_mm = max(float(getattr(track, "width", 0.25) or 0.25), 0.05)
        resistance, inductance, capacitance, z0, _delay_s = _trace_rlc(length_mm, width_mm, track.layer)
        lines.append(f"RGSEG{index} {start_node} {mid_node} {_spice_value(resistance)}")
        lines.append(f"LGSEG{index} {mid_node} {end_node} {_spice_value(inductance)}")
        lines.append(f"CGSA{index} {start_node} 0 {_spice_value(capacitance * 0.5)}")
        lines.append(f"CGSB{index} {end_node} 0 {_spice_value(capacitance * 0.5)}")
        role = _net_role(track.net)
        impedance_profile.append((role, track.layer, _length_bucket(length_mm), _z0_bucket(z0)))
        track_nodes.append((track, start_node, end_node, _track_bbox(track, margin_mm=0.2)))
        model_summary["trace_rlc_segments"] += 1

    via_index = 0
    for via in board.vias:
        if via.net not in port_nets or _net_role(via.net) == "unconnected":
            continue
        via_key = _point_key_mm(via.at)
        nodes = sorted(
            {
                node
                for (net, _layer, point_key), node in node_names.items()
                if net == via.net and point_key == via_key
            }
        )
        if len(nodes) < 2:
            continue
        first = nodes[0]
        for other in nodes[1:]:
            lines.append(f"RGVIA{via_index} {first} {other} 0.02")
            lines.append(f"CGVIA{via_index} {other} 0 0.02p")
            via_index += 1
            model_summary["vias"] += 1

    pad_nodes: dict[str, str] = {}
    for port_index, port in enumerate(ports):
        reference, pad_name = port.member.split(".", 1)
        pad = board.footprints[reference].pads[pad_name]
        candidate_nodes = sorted(
            {
                node
                for (net, _layer, point_key), node in node_names.items()
                if net == pad.net and point_key == _point_key_mm(pad.at)
            }
        )
        board_node = candidate_nodes[0] if candidate_nodes else f"gpad{port_index}"
        pad_nodes[port.member] = board_node
        external = f"pg{port_index}"
        lines.append(f"RGPAD{port_index} {external} {board_node} {_spice_value(SPICE_PAD_RESISTANCE_OHMS)}")
        if port.role == "ground":
            lines.append(f"RGGEOM{port_index} {external} 0 0.001")
        elif port.role.startswith("power_"):
            lines.append(f"RGTERM{port_index} {external} 0 1000000")
        else:
            lines.append(f"RGTERM{port_index} {external} 0 1000000")
        lines.append(f"RGPLEAK{port_index} {external} 0 {_spice_value(SPICE_LEAK_RESISTANCE_OHMS)}")
        model_summary["ports"] += 1

    collision_index = 0
    coupling_index = 0
    for left_index, (left_track, left_start, _left_end, left_bbox) in enumerate(track_nodes):
        left_width = max(float(getattr(left_track, "width", 0.25) or 0.25), 0.05)
        for right_track, right_start, _right_end, right_bbox in track_nodes[left_index + 1 :]:
            if left_track.net == right_track.net or left_track.layer != right_track.layer:
                continue
            right_width = max(float(getattr(right_track, "width", 0.25) or 0.25), 0.05)
            if not _bboxes_overlap(left_bbox, right_bbox):
                continue
            distance = _segment_distance_mm(left_track.start, left_track.end, right_track.start, right_track.end)
            clearance = 0.5 * (left_width + right_width)
            if distance <= clearance:
                lines.append(f"RGSHORT{collision_index} {left_start} {right_start} 0.01")
                collision_profile.append(
                    tuple(
                        sorted(
                            (
                                f"{_net_role(left_track.net)}:{left_track.layer}",
                                f"{_net_role(right_track.net)}:{right_track.layer}",
                            )
                        )
                    )
                )
                collision_index += 1
                model_summary["same_layer_trace_shorts"] += 1
                if collision_index >= 200:
                    continue
            elif distance <= clearance + 0.25 and coupling_index < 200:
                length_scale = min(_track_length_mm(left_track), _track_length_mm(right_track))
                coupling_cap = max(0.001e-12, min(0.2e-12, length_scale * 0.002e-12 / max(distance, 0.05)))
                lines.append(f"CGCOUP{coupling_index} {left_start} {right_start} {_spice_value(coupling_cap)}")
                coupling_index += 1
                model_summary["near_trace_couplings"] += 1

    for index, node in enumerate(sorted(set(node_names.values()) | set(pad_nodes.values()), key=_natural_sort_key)):
        lines.append(f"RGLEAK{index} {node} 0 {_spice_value(SPICE_LEAK_RESISTANCE_OHMS)}")

    window_ns = 30.0
    edge_ns = 0.4
    sample_offsets = {"incident": 2.0, "settled": 12.0, "late": 24.0}
    for driver_index, driver in enumerate(drivers):
        port_index = ports.index(driver)
        node = f"pg{port_index}"
        start = driver_index * window_ns + 1.0
        stop = start + 18.0
        amplitude = -0.001 if not driver.role.startswith("power_") else -0.01
        lines.append(
            f"IGSTIM{driver_index} {node} 0 PWL(0 0 {start:.3f}n 0 "
            f"{start + edge_ns:.3f}n {_spice_value(amplitude)} {stop:.3f}n {_spice_value(amplitude)} "
            f"{stop + edge_ns:.3f}n 0)"
        )
    total_ns = max(window_ns, len(drivers) * window_ns + 5.0)
    lines.extend([".control", "set noaskquit", f"tran 0.5n {total_ns:.3f}n"])
    measure_names: dict[str, str] = {}
    for driver_index, driver in enumerate(drivers):
        base = driver_index * window_ns + 1.0
        for sample_name, offset in sample_offsets.items():
            sample_time = base + offset
            for port_index, observed in enumerate(ports):
                measure_name = f"gm_{driver_index}_{port_index}_{sample_name}"
                measure_names[measure_name] = f"{driver.member}|{observed.member}|{sample_name}"
                lines.append(f"meas tran {measure_name} find v(pg{port_index}) at={sample_time:.3f}n")
    lines.extend(["quit", ".endc", ".end"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    model_summary["drivers"] = len(drivers)
    model_summary["selected_tracks"] = len(tracks)
    model_summary["impedance_samples"] = len(impedance_profile)
    model_summary["collision_samples"] = len(collision_profile)
    model_summary["high_speed_pair_samples"] = len(high_speed_pair_profile)
    return ports, drivers, dict(model_summary), measure_names, tuple(impedance_profile), tuple(collision_profile), high_speed_pair_profile


def _parse_pcb_geometry_measures(output: str, measure_names: dict[str, str]) -> tuple[PcbGeometryTracePoint, ...]:
    traces: list[PcbGeometryTracePoint] = []
    measure_re = re.compile(r"^([A-Za-z0-9_]+)\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
    for line in output.splitlines():
        match = measure_re.search(line.strip())
        if match is None:
            continue
        name, raw_value = match.groups()
        spec = measure_names.get(name.lower()) or measure_names.get(name)
        if spec is None:
            continue
        driver, observed, sample = spec.split("|", 2)
        traces.append(PcbGeometryTracePoint(driver=driver, observed=observed, sample=sample, voltage=float(raw_value)))
    return tuple(traces)


def _simulate_pcb_geometry_signature(board: Any, work_dir: Path, *, label: str) -> PcbGeometrySimulationSignature:
    spice_dir = work_dir / "pcb_geometry_spice"
    spice_dir.mkdir(parents=True, exist_ok=True)
    netlist_path = spice_dir / f"{label}.cir"
    output_path = spice_dir / f"{label}.log"
    ports, drivers, model_summary, measure_names, impedance_profile, collision_profile, high_speed_pair_profile = _write_pcb_geometry_transient_netlist(board, netlist_path)
    if not ports:
        output_path.write_text("No connected external ports selected.\n", encoding="utf-8")
        return PcbGeometrySimulationSignature(ports, drivers, (), impedance_profile, collision_profile, high_speed_pair_profile, model_summary, False, "no declared I/O ports", str(netlist_path), str(output_path))
    ngspice = shutil.which("ngspice")
    if ngspice is None:
        message = "ngspice not found on PATH"
        output_path.write_text(message + "\n", encoding="utf-8")
        return PcbGeometrySimulationSignature(ports, drivers, (), impedance_profile, collision_profile, high_speed_pair_profile, model_summary, False, message, str(netlist_path), str(output_path))
    try:
        with tempfile.TemporaryDirectory(prefix="eda_pcb_geometry_spice_") as tmp:
            proc = subprocess.run(
                [ngspice, "-b", "-n", str(netlist_path)],
                cwd=tmp,
                check=False,
                capture_output=True,
                text=True,
                timeout=90,
            )
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(str(part) for part in (exc.stdout, exc.stderr) if part)
        message = "ngspice timed out after 90 seconds"
        output_path.write_text(f"{message}\n{output}", encoding="utf-8")
        return PcbGeometrySimulationSignature(ports, drivers, (), impedance_profile, collision_profile, high_speed_pair_profile, model_summary, False, message, str(netlist_path), str(output_path))
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    output_path.write_text(output, encoding="utf-8")
    if proc.returncode != 0:
        return PcbGeometrySimulationSignature(
            ports,
            drivers,
            (),
            impedance_profile,
            collision_profile,
            high_speed_pair_profile,
            model_summary,
            False,
            f"ngspice exited with {proc.returncode}",
            str(netlist_path),
            str(output_path),
        )
    traces = _parse_pcb_geometry_measures(output, measure_names)
    expected = len(measure_names)
    if len(traces) != expected:
        return PcbGeometrySimulationSignature(
            ports,
            drivers,
            traces,
            impedance_profile,
            collision_profile,
            high_speed_pair_profile,
            model_summary,
            False,
            f"parsed {len(traces)} of {expected} expected PCB-geometry transient measurements",
            str(netlist_path),
            str(output_path),
        )
    return PcbGeometrySimulationSignature(ports, drivers, traces, impedance_profile, collision_profile, high_speed_pair_profile, model_summary, True, "", str(netlist_path), str(output_path))


def _clip_output(value: str, limit: int = 2000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n... truncated ..."


def _drc_issue_counts(payload: Any) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "exclusion": 0, "unknown": 0, "total": 0}

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        severity = value.get("severity")
        looks_like_issue = severity is not None and any(
            key in value
            for key in (
                "description",
                "items",
                "message",
                "rule",
                "type",
                "violating_items",
                "violations",
            )
        )
        if looks_like_issue:
            normalized = str(severity or "unknown").lower()
            if "error" in normalized:
                bucket = "error"
            elif "warn" in normalized:
                bucket = "warning"
            elif "excl" in normalized:
                bucket = "exclusion"
            else:
                bucket = "unknown"
            counts[bucket] += 1
            counts["total"] += 1
            return
        for item in value.values():
            visit(item)

    visit(payload)
    return counts


def _kicad_cli_drc_validation(board_path: Path, work_dir: Path, *, label: str) -> dict[str, Any]:
    drc_dir = work_dir / "kicad_drc"
    drc_dir.mkdir(parents=True, exist_ok=True)
    report_path = drc_dir / f"{label}.json"
    kicad_cli = shutil.which("kicad-cli")
    if kicad_cli is None:
        raise RuntimeError("kicad-cli is required by the EDA-bench verifier image")
    base_command = [
        kicad_cli,
        "pcb",
        "drc",
        "--format",
        "json",
        "--severity-all",
    ]
    suffix = ["--output", str(report_path), str(board_path)]
    try:
        proc = subprocess.run(
            [*base_command, "--schematic-parity", *suffix],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(str(part) for part in (exc.stdout, exc.stderr) if part)
        return {
            "available": True,
            "skipped": False,
            "score": 0.0,
            "issue_counts": {"error": 1, "warning": 0, "exclusion": 0, "unknown": 0, "total": 1},
            "detail": "kicad-cli pcb drc timed out",
            "stdout": _clip_output(output),
            "report_path": str(report_path),
        }

    payload: Any = {}
    counts = {"error": 0, "warning": 0, "exclusion": 0, "unknown": 0, "total": 0}
    if report_path.exists():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            counts = _drc_issue_counts(payload)
        except (OSError, json.JSONDecodeError) as exc:
            counts = {"error": 0, "warning": 0, "exclusion": 1, "unknown": 0, "total": 1}
            payload = {"parse_error": f"{type(exc).__name__}: {exc}"}
    elif proc.returncode != 0:
        counts = {"error": 1, "warning": 0, "exclusion": 0, "unknown": 0, "total": 1}
    score = 1.0 if counts["error"] == 0 else 0.0
    return {
        "available": True,
        "skipped": False,
        "score": score,
        "issue_counts": counts,
        "returncode": proc.returncode,
        "stdout": _clip_output(proc.stdout),
        "stderr": _clip_output(proc.stderr),
        "detail": "" if score == 1.0 else "kicad-cli pcb drc reported error-severity violations",
        "report_path": str(report_path),
        "report_exists": report_path.exists(),
        "report_schema": payload.get("schema_version") if isinstance(payload, dict) else None,
        "schematic_parity_used": True,
    }


def _relative_drc_score(submission_drc: dict[str, Any], reference_drc: dict[str, Any]) -> float:
    submission_counts = submission_drc.get("issue_counts") or {}
    reference_counts = reference_drc.get("issue_counts") or {}
    excess_errors = max(0, int(submission_counts.get("error", 0)) - int(reference_counts.get("error", 0)))
    excess_warnings = max(0, int(submission_counts.get("warning", 0)) - int(reference_counts.get("warning", 0)))
    weighted_excess = excess_errors + 0.2 * excess_warnings
    return max(0.0, min(1.0, 1.0 - min(1.0, weighted_excess / 5.0)))


def _kicad_cli_erc_validation(schematic_path: Path | None, work_dir: Path, *, label: str) -> dict[str, Any]:
    erc_dir = work_dir / "kicad_erc"
    erc_dir.mkdir(parents=True, exist_ok=True)
    report_path = erc_dir / f"{label}.json"
    if schematic_path is None:
        return {
            "available": False,
            "skipped": True,
            "score": 0.85,
            "issue_counts": {"error": 0, "warning": 0, "exclusion": 0, "unknown": 0, "total": 0},
            "detail": "schematic unavailable; ERC skipped",
            "report_path": str(report_path),
        }
    kicad_cli = shutil.which("kicad-cli")
    if kicad_cli is None:
        raise RuntimeError("kicad-cli is required by the EDA-bench verifier image")
    try:
        proc = subprocess.run(
            [
                kicad_cli,
                "sch",
                "erc",
                "--format",
                "json",
                "--severity-all",
                "--output",
                str(report_path),
                str(schematic_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(str(part) for part in (exc.stdout, exc.stderr) if part)
        return {
            "available": True,
            "skipped": False,
            "score": 0.0,
            "issue_counts": {"error": 1, "warning": 0, "exclusion": 0, "unknown": 0, "total": 1},
            "detail": "kicad-cli sch erc timed out",
            "stdout": _clip_output(output),
            "report_path": str(report_path),
        }

    payload: Any = {}
    counts = {"error": 0, "warning": 0, "exclusion": 0, "unknown": 0, "total": 0}
    if report_path.exists():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            counts = _drc_issue_counts(payload)
        except (OSError, json.JSONDecodeError) as exc:
            counts = {"error": 0, "warning": 0, "exclusion": 1, "unknown": 0, "total": 1}
            payload = {"parse_error": f"{type(exc).__name__}: {exc}"}
    elif proc.returncode != 0:
        counts = {"error": 1, "warning": 0, "exclusion": 0, "unknown": 0, "total": 1}
    score = 1.0 if counts["error"] == 0 else 0.0
    return {
        "available": True,
        "skipped": False,
        "score": score,
        "issue_counts": counts,
        "returncode": proc.returncode,
        "stdout": _clip_output(proc.stdout),
        "stderr": _clip_output(proc.stderr),
        "detail": "" if score == 1.0 else "kicad-cli sch erc reported error-severity violations",
        "report_path": str(report_path),
        "report_exists": report_path.exists(),
        "report_schema": payload.get("schema_version") if isinstance(payload, dict) else None,
    }


def _relative_erc_score(submission_erc: dict[str, Any], reference_erc: dict[str, Any]) -> float:
    if submission_erc.get("skipped") or not submission_erc.get("available"):
        return float(submission_erc.get("score", 1.0))
    submission_counts = submission_erc.get("issue_counts") or {}
    reference_counts = reference_erc.get("issue_counts") or {}
    excess_errors = max(0, int(submission_counts.get("error", 0)) - int(reference_counts.get("error", 0)))
    excess_warnings = max(0, int(submission_counts.get("warning", 0)) - int(reference_counts.get("warning", 0)))
    weighted_excess = excess_errors + 0.2 * excess_warnings
    return max(0.0, min(1.0, 1.0 - min(1.0, weighted_excess / 5.0)))


def evaluate_behavioral_io_simulation(
    task: TaskSpec,
    project_dir: Path,
    work_dir: Path,
    *,
    source_metadata: dict[str, Any],
) -> TaskEvaluation:
    from tasks.kicad_common import load_board_model
    from tasks.source_backed_task import _resolve_reference_board_path, _source_board_path

    work_dir.mkdir(parents=True, exist_ok=True)
    project_stem = str(source_metadata.get("project_stem", task.task_id))
    board_path = project_dir / f"{project_stem}.kicad_pcb"
    if not board_path.exists():
        return _missing_submission(
            task,
            project_dir,
            work_dir,
            f"missing required PCB file for I/O simulation: {board_path.name}",
        )

    reference_board_path = Path(str(source_metadata.get("reference_board", "")))
    if not reference_board_path.exists():
        spec = source_metadata.get("source_spec")
        if spec is not None:
            reference_board_path = _resolve_reference_board_path(spec)
    if not reference_board_path.exists():
        return unsupported_io_simulation_evaluation(
            task,
            project_dir,
            work_dir,
            source_metadata=source_metadata,
            reason="missing_reference_board_for_io_simulation",
        )

    raw: dict[str, Any] = {
        "task_id": task.task_id,
        "project_dir": str(project_dir),
        "grading_model": GRADING_MODEL,
        "scoring_mode": "explicit_io_simulation",
        "supported": True,
        "unsupported": False,
        "failures": [],
        "oracle": {
            "name": "pcb_geometry_and_behavioral_transient_io_ngspice",
            "simulator": "ngspice transient analysis",
            "port_declaration": "external boundary pads selected from the KiCad board interfaces",
            "stimuli": "deterministic transient current pulses applied to each declared non-ground I/O port",
            "probes": "voltage waveform samples at every declared I/O port for every stimulus",
            "models": (
                "actual routed PCB trace width/length/layer parasitics, via/pad resistance, "
                "same-layer trace-intersection shorts, close-trace coupling capacitance, "
                "leakage, R/C/L/diode passives, and deterministic generic IC behavioral coupling"
            ),
            "reference_board": str(reference_board_path),
            "submission_board": str(board_path),
        },
        "source_repo_url": source_metadata.get("source_repo_url", ""),
        "source_commit": source_metadata.get("source_commit", ""),
        "license": source_metadata.get("license", ""),
    }
    metrics = {
        "submission_exists": 1.0,
        "build_success": 0.0,
        "task_score": 0.0,
        "overall_score": 0.0,
        "reward": 0.0,
        "error_message": "",
    }

    try:
        submission_board = load_board_model(_source_board_path(project_dir, project_stem))
        reference_board = load_board_model(reference_board_path)
    except Exception as exc:
        message = f"I/O simulation setup failed: {type(exc).__name__}: {exc}"
        raw["failures"] = [message]
        metrics["error_message"] = message
        return TaskEvaluation(raw=raw, metrics=metrics)

    submission_schematic_path = _resolve_schematic_path(project_dir, project_stem)
    reference_schematic_path = _resolve_schematic_path(reference_board_path.parent, reference_board_path.stem)
    submission_signature = _simulate_behavioral_io_signature(submission_board, work_dir, label="submission_behavioral_io")
    reference_signature = _simulate_behavioral_io_signature(reference_board, work_dir, label="reference_behavioral_io")
    submission_geometry_signature = _simulate_pcb_geometry_signature(submission_board, work_dir, label="submission_pcb_geometry_io")
    reference_geometry_signature = _simulate_pcb_geometry_signature(reference_board, work_dir, label="reference_pcb_geometry_io")
    submission_known_signature = _known_io_verification_signature(task, submission_board, reference_board)
    reference_known_signature = _known_io_verification_signature(task, reference_board, reference_board)
    static_contract = _load_static_io_contract(task, source_metadata, reference_board)
    functional_contract = _load_functional_io_contract(task, source_metadata, reference_board)
    submission_realized_external_copper = _realized_external_copper_counter(submission_board)
    reference_realized_external_copper = _counter_from_records(static_contract.get("realized_external_copper_profile")) or _realized_external_copper_counter(reference_board)
    submission_external_net_degrees = _external_net_degree_counter(submission_board)
    reference_external_net_degrees = _counter_from_records(static_contract.get("external_net_degree_profile")) or _external_net_degree_counter(reference_board)
    submission_external_net_routes = _external_net_route_counter(submission_board)
    reference_external_net_routes = _counter_from_records(static_contract.get("external_net_route_profile")) or _external_net_route_counter(reference_board)
    submission_semantic_external_nets = _external_semantic_net_counter(submission_board)
    reference_semantic_external_nets = _counter_from_records(static_contract.get("semantic_external_net_profile")) or _external_semantic_net_counter(reference_board)
    semantic_external_net_score = _counter_f1(submission_semantic_external_nets, reference_semantic_external_nets)
    submission_role_inventory = _external_role_inventory_counter(submission_board)
    reference_role_inventory = _counter_from_records(static_contract.get("external_role_inventory_profile")) or _external_role_inventory_counter(reference_board)
    submission_health = _external_io_health_summary(submission_board)
    reference_health = _external_io_health_summary(reference_board)
    submission_board_short_safety = _short_safety_summary(_board_same_layer_short_profile(submission_board))
    reference_board_short_safety = _short_safety_summary(_board_same_layer_short_profile(reference_board))
    required_interface_families = tuple(str(item) for item in functional_contract.get("scored_interface_families", []))
    if not required_interface_families:
        required_interface_families = tuple(str(item) for item in functional_contract.get("required_interface_families", []))
    if not required_interface_families:
        required_interface_families = _required_interface_families_from_task(task)
    routed_required_interface_families = tuple(str(item) for item in functional_contract.get("scored_routed_interface_families", []))
    reference_observed_families = {
        key[0]
        for key, count in (_external_net_family_counter(reference_board) | _routed_external_net_family_counter(reference_board)).items()
        if key and count > 0
    }
    reference_routed_families = {
        key[0]
        for key, count in _routed_external_net_family_counter(reference_board).items()
        if key and count > 0
    }
    if reference_observed_families:
        required_interface_families = tuple(family for family in required_interface_families if family in reference_observed_families)
    if reference_routed_families:
        routed_required_interface_families = tuple(
            family for family in routed_required_interface_families if family in reference_routed_families
        )
    submission_functional = _task_functional_score(
        task,
        submission_board,
        required_interface_families,
        submission_health,
        routed_required_families=routed_required_interface_families,
    )
    reference_functional = _task_functional_score(
        task,
        reference_board,
        required_interface_families,
        reference_health,
        routed_required_families=routed_required_interface_families,
    )
    functional_score = float(submission_functional["score"])
    raw_internal_requirements = _required_internal_features(task, required_interface_families)
    reference_internal_profile = _active_internal_features(reference_board)
    supported_internal_requirements = tuple(
        requirement
        for requirement in raw_internal_requirements
        if reference_internal_profile[requirement] > 0
    )
    submission_internal_realization = _internal_functional_realization_score(
        task,
        submission_board,
        required_interface_families,
        required_features=supported_internal_requirements,
    )
    reference_internal_realization = _internal_functional_realization_score(
        task,
        reference_board,
        required_interface_families,
        required_features=supported_internal_requirements,
    )
    internal_realization_score = float(submission_internal_realization["score"])
    submission_drc = _kicad_cli_drc_validation(board_path, work_dir, label="submission")
    reference_drc = _kicad_cli_drc_validation(reference_board_path, work_dir, label="reference")
    drc_score = _relative_drc_score(submission_drc, reference_drc)
    submission_erc = _kicad_cli_erc_validation(submission_schematic_path, work_dir, label="submission")
    reference_erc = _kicad_cli_erc_validation(reference_schematic_path, work_dir, label="reference")
    erc_score = _relative_erc_score(submission_erc, reference_erc)
    submission_schematic_consistency = _schematic_board_consistency_score(submission_board, submission_schematic_path)
    reference_schematic_consistency = _schematic_board_consistency_score(reference_board, reference_schematic_path)
    schematic_consistency_score = (
        float(submission_schematic_consistency["score"])
        if reference_schematic_consistency.get("available")
        else 1.0
    )
    component_realization = _component_realization_score(submission_board, reference_board)
    component_realization_score = float(component_realization["score"])
    submission_active_power_integrity = _active_power_integrity_summary(submission_board)
    reference_active_power_integrity = _active_power_integrity_summary(reference_board)
    active_power_integrity_score = _relative_active_power_integrity_score(
        submission_active_power_integrity,
        reference_active_power_integrity,
    )
    submission_fabrication_geometry = _fabrication_geometry_summary(submission_board)
    reference_fabrication_geometry = _fabrication_geometry_summary(reference_board)
    fabrication_geometry_score = _relative_fabrication_geometry_score(
        submission_fabrication_geometry,
        reference_fabrication_geometry,
    )
    reference_high_speed_families = _high_speed_family_counter(reference_geometry_signature.high_speed_pair_profile)
    raw["oracle"]["declared_ports"] = [port.__dict__ for port in reference_signature.ports]
    raw["oracle"]["declared_driver_count"] = len(reference_signature.drivers)
    raw["oracle"]["declared_probe_count"] = len(reference_signature.ports)
    raw["oracle"]["known_interface_refs"] = list(reference_known_signature.interface_refs)
    raw["oracle"]["static_contract"] = {
        "schema_version": static_contract.get("schema_version"),
        "contract_kind": static_contract.get("contract_kind"),
        "external_net_count": static_contract.get("external_net_count"),
        "external_connected_pad_count": static_contract.get("external_connected_pad_count"),
        "routed_external_net_count": static_contract.get("routed_external_net_count"),
        "selected_geometry_track_count": static_contract.get("selected_geometry_track_count"),
        "semantic_external_net_count": sum(reference_semantic_external_nets.values()),
    }
    raw["oracle"]["functional_contract"] = {
        "schema_version": functional_contract.get("schema_version"),
        "contract_kind": functional_contract.get("contract_kind"),
        "required_interface_families": list(required_interface_families),
        "routed_required_interface_families": list(routed_required_interface_families),
    }

    if (
        not submission_signature.simulated
        or not reference_signature.simulated
        or not submission_geometry_signature.simulated
        or not reference_geometry_signature.simulated
    ):
        errors = "; ".join(
            error
            for error in (
                submission_signature.error,
                reference_signature.error,
                submission_geometry_signature.error,
                reference_geometry_signature.error,
            )
            if error
        )
        raw["failures"] = [errors or "I/O simulation did not complete"]
        raw["score_components"] = {
            "io_simulation": {
                "score": 0.0,
                "subscores": [_subscore("ngspice_io_and_pcb_geometry_simulation_completed", 0.0, errors)],
                "submission_simulation": submission_signature.to_dict(),
                "reference_simulation": reference_signature.to_dict(),
                "submission_pcb_geometry_simulation": submission_geometry_signature.to_dict(),
                "reference_pcb_geometry_simulation": reference_geometry_signature.to_dict(),
                "submission_known_io_verification": submission_known_signature.to_dict(),
                "reference_known_io_verification": reference_known_signature.to_dict(),
                "submission_realized_external_copper_profile": dict(sorted(submission_realized_external_copper.items())),
                "reference_realized_external_copper_profile": dict(sorted(reference_realized_external_copper.items())),
                "submission_external_net_degree_profile": dict(sorted(submission_external_net_degrees.items())),
                "reference_external_net_degree_profile": dict(sorted(reference_external_net_degrees.items())),
                "submission_external_net_route_profile": dict(sorted(submission_external_net_routes.items())),
                "reference_external_net_route_profile": dict(sorted(reference_external_net_routes.items())),
                "submission_semantic_external_net_profile": dict(sorted(submission_semantic_external_nets.items())),
                "reference_semantic_external_net_profile": dict(sorted(reference_semantic_external_nets.items())),
                "submission_role_inventory_profile": dict(sorted(submission_role_inventory.items())),
                "reference_role_inventory_profile": dict(sorted(reference_role_inventory.items())),
                "submission_external_io_health": submission_health,
                "reference_external_io_health": reference_health,
                "submission_board_short_safety": submission_board_short_safety,
                "reference_board_short_safety": reference_board_short_safety,
                "submission_functional_contract": submission_functional,
                "reference_functional_contract": reference_functional,
                "submission_internal_functional_realization": submission_internal_realization,
                "reference_internal_functional_realization": reference_internal_realization,
                "submission_kicad_drc": submission_drc,
                "reference_kicad_drc": reference_drc,
                "submission_kicad_erc": submission_erc,
                "reference_kicad_erc": reference_erc,
                "submission_schematic_board_consistency": submission_schematic_consistency,
                "reference_schematic_board_consistency": reference_schematic_consistency,
                "component_function_realization": component_realization,
                "submission_active_power_integrity": submission_active_power_integrity,
                "reference_active_power_integrity": reference_active_power_integrity,
                "submission_fabrication_geometry": submission_fabrication_geometry,
                "reference_fabrication_geometry": reference_fabrication_geometry,
            }
        }
        metrics["error_message"] = raw["failures"][0]
        return TaskEvaluation(raw=raw, metrics=metrics)

    subscores = [
        (
            0.0,
            _subscore(
                "diagnostic_exact_reference_io_partition",
                _known_io_exact_score(submission_known_signature),
                "diagnostic only; exact refdes/pad matching is not part of the functional score",
            ),
        ),
        (
            0.35,
            _subscore(
                "task_required_interface_function",
                functional_score,
                "task-semantic boundary-net interface families must be present and routed; component inventory is ignored",
            ),
        ),
        (
            0.40,
            _subscore(
                "semantic_external_io_net_verification",
                semantic_external_net_score,
                "refdes-invariant external connector pin/net mapping must match the task I/O contract; internal component identity is ignored",
            ),
        ),
        (
            0.0,
            _subscore(
                "diagnostic_external_port_role_inventory",
                _counter_recall(submission_role_inventory, reference_role_inventory),
                "diagnostic only; external role inventory is not part of the functional score",
            ),
        ),
        (
            0.0,
            _subscore(
                "diagnostic_realized_external_copper_topology",
                _counter_recall(submission_realized_external_copper, reference_realized_external_copper),
                "diagnostic only; role/degree copper topology is not part of the functional score",
            ),
        ),
        (
            0.0,
            _subscore(
                "diagnostic_external_net_routed_geometry_contract",
                _counter_f1(submission_external_net_routes, reference_external_net_routes),
                "diagnostic only; reference-like route length/count/layer buckets are not part of the functional score",
            ),
        ),
        (
            0.35,
            _subscore(
                "external_io_electrical_health",
                submission_health["short_safety_score"],
                "absolute external-net short safety; routed coverage, attachment, and continuity are enforced by hard caps",
            ),
        ),
        (
            0.20,
            _subscore(
                "internal_functional_realization",
                internal_realization_score,
                "task-required active/internal role features must be present without requiring exact component identity",
            ),
        ),
        (
            0.15,
            _subscore(
                "kicad_drc_manufacturability",
                drc_score,
                "relative KiCad PCB DRC cleanliness measured by the required kicad-cli runtime",
            ),
        ),
        (
            0.30,
            _subscore(
                "reference_component_function_realization",
                component_realization_score,
                "broad component-function profile must preserve active devices, passives, decoupling, filtering, and protection without exact refdes matching",
            ),
        ),
        (
            0.20,
            _subscore(
                "active_device_power_integrity",
                active_power_integrity_score,
                "active signal-bearing devices must have both power and ground connectivity",
            ),
        ),
        (
            0.0,
            _subscore(
                "diagnostic_schematic_board_consistency",
                schematic_consistency_score,
                "diagnostic only; submitted schematic/PCB refdes consistency is not a physical PCB function score",
            ),
        ),
        (
            0.15,
            _subscore(
                "kicad_erc_electrical_rules",
                erc_score,
                "relative KiCad schematic ERC cleanliness measured by the required kicad-cli runtime",
            ),
        ),
        (
            0.15,
            _subscore(
                "pcb_fabrication_geometry",
                fabrication_geometry_score,
                "reference-relative manufacturability checks for outline presence, trace width, and via annular ring sanity",
            ),
        ),
        (
            0.0,
            _subscore(
                "diagnostic_logical_external_net_degree_profile",
                _counter_recall(submission_external_net_degrees, reference_external_net_degrees),
                "diagnostic only; external net fanout shape is not part of the functional score",
            ),
        ),
        (
            0.0,
            _subscore(
                "diagnostic_exact_declared_port_presence",
                _counter_f1(_behavioral_port_counter(submission_signature), _behavioral_port_counter(reference_signature)),
                "diagnostic only; exact port member names are not part of the functional score",
            ),
        ),
        (
            0.25,
            _subscore(
                "behavioral_boundary_family_waveform_response",
                _behavioral_boundary_response_score(
                    submission_signature,
                    task,
                    required_interface_families,
                    reference_signature,
                ),
                "behavioral transient simulation must produce finite boundary-port measurements and task-level I/O transfer responses",
            ),
        ),
        (
            0.0,
            _subscore(
                "diagnostic_exact_behavioral_port_to_port_waveform_response",
                _counter_f1(_trace_exact_counter(submission_signature), _trace_exact_counter(reference_signature)),
                "diagnostic only; exact port member names are not part of the functional score",
            ),
        ),
        (
            0.20,
            _subscore(
                "pcb_geometry_boundary_family_waveform_response",
                _geometry_measurement_quality_score(submission_geometry_signature),
                "PCB-geometry transient simulation must produce finite boundary-port measurements",
            ),
        ),
        (
            0.0,
            _subscore(
                "diagnostic_exact_pcb_geometry_port_to_port_waveform_response",
                _counter_f1(_geometry_trace_exact_counter(submission_geometry_signature), _geometry_trace_exact_counter(reference_geometry_signature)),
                "diagnostic only; exact port member names are not part of the functional score",
            ),
        ),
        (
            0.10,
            _subscore(
                "pcb_impedance_plausibility",
                _impedance_scoring_score(submission_geometry_signature),
                "absolute routed-trace impedance plausibility rather than matching reference width buckets",
            ),
        ),
        (
            0.10,
            _subscore(
                "pcb_external_short_safety",
                submission_health["short_safety_score"],
                "same-layer intersections between distinct external nets are treated as electrical shorts",
            ),
        ),
        (
            0.15,
            _subscore(
                "pcb_board_short_safety",
                submission_board_short_safety["short_safety_score"],
                "same-layer intersections between any distinct board nets are treated as electrical shorts",
            ),
        ),
        (
            0.10,
            _subscore(
                "pcb_high_speed_differential_pair_quality",
                _high_speed_pair_quality_score(
                    submission_geometry_signature,
                    reference_high_speed_families,
                    reference_geometry_signature.high_speed_pair_profile,
                ),
                "required differential-pair families must exist with plausible skew, impedance, and spacing",
            ),
        ),
    ]
    io_score = _weighted_subscores(subscores)
    score_caps: list[dict[str, Any]] = []
    functional_interface_score = float(submission_functional["interface_presence_score"])
    functional_routed_score = float(submission_functional["routed_presence_score"])
    behavioral_shape_score = _behavioral_boundary_response_score(
        submission_signature,
        task,
        required_interface_families,
        reference_signature,
    )
    geometry_shape_score = _geometry_measurement_quality_score(submission_geometry_signature)
    impedance_score = _impedance_plausibility_score(submission_geometry_signature)
    high_speed_pair_score = _high_speed_pair_quality_score(
        submission_geometry_signature,
        reference_high_speed_families,
        reference_geometry_signature.high_speed_pair_profile,
    )
    submission_transfer_profile = _behavioral_transfer_response_counter(submission_signature)
    reference_transfer_profile = _behavioral_transfer_response_counter(reference_signature)
    transfer_response_score = _behavioral_transfer_response_score(
        submission_signature,
        task,
        required_interface_families,
        reference_signature,
    )
    transfer_counts = _transfer_profile_counts(submission_transfer_profile)
    transfer_requirements = _observable_transfer_requirements(
        task,
        required_interface_families,
        reference_signature,
        submission_signature,
    )
    internal_requirements = submission_internal_realization["required_features"]
    reference_tracks = int(static_contract.get("selected_geometry_track_count") or reference_geometry_signature.model_summary.get("selected_tracks", 0))
    submission_tracks = int(submission_geometry_signature.model_summary.get("selected_tracks", 0))
    if reference_semantic_external_nets and semantic_external_net_score < 0.50:
        score_caps.append(
            {
                "name": "wrong_external_io_pin_net_mapping",
                "cap": 0.05,
                "detail": f"semantic external I/O net verification score {semantic_external_net_score:.3f}",
            }
        )
    elif reference_semantic_external_nets and semantic_external_net_score < 0.85:
        score_caps.append(
            {
                "name": "incomplete_external_io_pin_net_mapping",
                "cap": 0.20,
                "detail": f"semantic external I/O net verification score {semantic_external_net_score:.3f}",
            }
        )
    elif reference_semantic_external_nets and semantic_external_net_score < 0.95:
        score_caps.append(
            {
                "name": "weak_external_io_pin_net_mapping",
                "cap": 0.55,
                "detail": f"semantic external I/O net verification score {semantic_external_net_score:.3f}",
            }
        )
    if required_interface_families and functional_interface_score < 0.50:
        score_caps.append(
            {
                "name": "missing_task_required_external_interfaces",
                "cap": 0.20,
                "detail": f"required interface-family presence {functional_interface_score:.3f}; required {list(required_interface_families)}",
            }
        )
    elif required_interface_families and functional_interface_score < 0.85:
        score_caps.append(
            {
                "name": "incomplete_task_required_external_interfaces",
                "cap": 0.60,
                "detail": f"required interface-family presence {functional_interface_score:.3f}; required {list(required_interface_families)}",
            }
        )
    if routed_required_interface_families and functional_routed_score < 0.50:
        score_caps.append(
            {
                "name": "missing_routed_task_required_interfaces",
                "cap": 0.05 if functional_routed_score <= 0.0 else 0.15,
                "detail": f"required routed interface-family presence {functional_routed_score:.3f}; required {list(routed_required_interface_families)}",
            }
        )
    elif (required_interface_families or routed_required_interface_families) and functional_score < 0.75:
        score_caps.append(
            {
                "name": "weak_task_required_io_function",
                "cap": 0.45,
                "detail": f"task-semantic I/O function score {functional_score:.3f}",
            }
        )
    if internal_requirements and internal_realization_score <= 0.0:
        score_caps.append(
            {
                "name": "missing_task_required_internal_functional_realization",
                "cap": 0.10,
                "detail": f"internal realization score {internal_realization_score:.3f}; required {internal_requirements}",
            }
        )
    elif internal_requirements and internal_realization_score < 0.75:
        score_caps.append(
            {
                "name": "weak_task_required_internal_functional_realization",
                "cap": 0.45,
                "detail": f"internal realization score {internal_realization_score:.3f}; required {internal_requirements}",
            }
        )
    if component_realization["reference_profile"] and component_realization_score < 0.35:
        score_caps.append(
            {
                "name": "missing_reference_component_function_realization",
                "cap": 0.10,
                "detail": f"component-function realization score {component_realization_score:.3f}",
            }
        )
    elif component_realization["reference_profile"] and component_realization_score < 0.65:
        score_caps.append(
            {
                "name": "weak_reference_component_function_realization",
                "cap": 0.35,
                "detail": f"component-function realization score {component_realization_score:.3f}",
            }
        )
    elif component_realization["reference_profile"] and component_realization_score < 0.85:
        score_caps.append(
            {
                "name": "incomplete_reference_component_function_realization",
                "cap": 0.65,
                "detail": f"component-function realization score {component_realization_score:.3f}",
            }
        )
    if int(reference_active_power_integrity.get("active_with_signal_count", 0)) > 0 and active_power_integrity_score < 0.50:
        score_caps.append(
            {
                "name": "missing_active_device_power_integrity",
                "cap": 0.15,
                "detail": f"active power integrity score {active_power_integrity_score:.3f}",
            }
        )
    elif int(reference_active_power_integrity.get("active_with_signal_count", 0)) > 0 and active_power_integrity_score < 0.90:
        score_caps.append(
            {
                "name": "weak_active_device_power_integrity",
                "cap": 0.55,
                "detail": f"active power integrity score {active_power_integrity_score:.3f}",
            }
        )
    excess_tiny_track_count = max(
        0,
        int(submission_fabrication_geometry["tiny_track_count"])
        - int(reference_fabrication_geometry.get("tiny_track_count", 0)),
    )
    if int(reference_fabrication_geometry.get("track_count", 0)) > 0 and excess_tiny_track_count > 0:
        score_caps.append(
            {
                "name": "implausible_min_trace_width",
                "cap": 0.35,
                "detail": (
                    f"excess tiny track widths below 0.075 mm: {excess_tiny_track_count}; "
                    f"submission {submission_fabrication_geometry['tiny_track_count']}; "
                    f"reference {reference_fabrication_geometry.get('tiny_track_count', 0)}"
                ),
            }
        )
    excess_invalid_via_count = max(
        0,
        int(submission_fabrication_geometry["invalid_via_count"])
        - int(reference_fabrication_geometry.get("invalid_via_count", 0)),
    )
    excess_thin_annular_ring_count = max(
        0,
        int(submission_fabrication_geometry["thin_annular_ring_count"])
        - int(reference_fabrication_geometry.get("thin_annular_ring_count", 0)),
    )
    if int(reference_fabrication_geometry.get("via_count", 0)) > 0 and (
        excess_invalid_via_count > 0 or excess_thin_annular_ring_count > 0
    ):
        score_caps.append(
            {
                "name": "implausible_via_geometry",
                "cap": 0.35,
                "detail": (
                    f"excess invalid vias {excess_invalid_via_count}; "
                    f"excess thin annular rings {excess_thin_annular_ring_count}; "
                    f"submission invalid/thin "
                    f"{submission_fabrication_geometry['invalid_via_count']}/"
                    f"{submission_fabrication_geometry['thin_annular_ring_count']}; "
                    f"reference invalid/thin "
                    f"{reference_fabrication_geometry.get('invalid_via_count', 0)}/"
                    f"{reference_fabrication_geometry.get('thin_annular_ring_count', 0)}"
                ),
            }
        )
    if (
        float(reference_fabrication_geometry.get("outline_area_mm2", 0.0)) > 1.0
        and float(submission_fabrication_geometry["outline_area_mm2"]) <= 1.0
    ):
        score_caps.append(
            {
                "name": "missing_board_outline",
                "cap": 0.30,
                "detail": "board outline area is missing or degenerate",
            }
        )
    reference_route_coverage_score = float(reference_health["route_coverage_score"])
    route_coverage_score = float(submission_health["route_coverage_score"])
    if reference_route_coverage_score >= 0.50 and route_coverage_score < 0.20:
        score_caps.append(
            {
                "name": "too_many_unrouted_external_nets",
                "cap": 0.15,
                "detail": f"external-net routed coverage {route_coverage_score:.3f}",
            }
        )
    elif reference_route_coverage_score >= 0.50 and route_coverage_score < 0.50:
        score_caps.append(
            {
                "name": "weak_external_net_route_coverage",
                "cap": 0.40,
                "detail": f"external-net routed coverage {route_coverage_score:.3f}",
            }
        )
    if reference_tracks > 0 and submission_tracks == 0:
        score_caps.append(
            {
                "name": "too_little_routed_copper_for_reference_interfaces",
                "cap": 0.0,
                "detail": f"selected geometry tracks {submission_tracks}, reference {reference_tracks}",
            }
        )
    if transfer_requirements["signal"] and transfer_counts["signal_involved"] <= 0:
        score_caps.append(
            {
                "name": "missing_simulated_signal_io_transfer_response",
                "cap": 0.05,
                "detail": "no simulated signal-involved I/O transfer response was measured",
            }
        )
    elif transfer_requirements["cross_signal"] and transfer_counts["signal_cross_node"] <= 0:
        score_caps.append(
            {
                "name": "missing_simulated_signal_io_transfer_response",
                "cap": 0.05,
                "detail": "no simulated signal-involved transfer between distinct external I/O nodes was measured",
            }
        )
    elif transfer_requirements["signal"] and transfer_response_score < 0.35:
        score_caps.append(
            {
                "name": "weak_simulated_io_transfer_response",
                "cap": 0.35,
                "detail": f"simulated I/O transfer response score {transfer_response_score:.3f}",
            }
        )
    if reference_tracks > 0 and 0 < submission_tracks < max(1, math.floor(reference_tracks * 0.05)):
        score_caps.append(
            {
                "name": "too_little_routed_copper_for_reference_interfaces",
                "cap": 0.15,
                "detail": f"selected geometry tracks {submission_tracks}, reference {reference_tracks}",
            }
        )
    excess_split_external_nets = max(
        0,
        int(submission_health["split_external_net_count"]) - int(reference_health["split_external_net_count"]),
    )
    excess_isolated_external_pads = max(
        0,
        int(submission_health["isolated_external_pad_count"]) - int(reference_health["isolated_external_pad_count"]),
    )
    if excess_split_external_nets > 0:
        score_caps.append(
            {
                "name": "split_required_external_net_continuity",
                "cap": 0.35,
                "detail": f"excess split external nets {excess_split_external_nets}",
            }
        )
    if excess_isolated_external_pads > max(0, math.floor(submission_health["external_connected_pad_count"] * 0.10)):
        score_caps.append(
            {
                "name": "isolated_external_io_pads",
                "cap": 0.30,
                "detail": f"excess isolated external pads {excess_isolated_external_pads} of {submission_health['external_connected_pad_count']}",
            }
        )
    if submission_health["power_ground_short_count"] > 0:
        score_caps.append(
            {
                "name": "power_ground_external_short",
                "cap": 0.0,
                "detail": f"power-ground external-net shorts {submission_health['power_ground_short_count']}",
            }
        )
    elif submission_health["power_signal_or_ground_signal_short_count"] > 0:
        score_caps.append(
            {
                "name": "power_or_ground_signal_external_short",
                "cap": 0.15,
                "detail": f"power/ground to signal external-net shorts {submission_health['power_signal_or_ground_signal_short_count']}",
            }
        )
    elif submission_health["signal_signal_short_count"] > 0:
        score_caps.append(
            {
                "name": "signal_signal_external_short",
                "cap": 0.15,
                "detail": f"signal-signal external-net shorts {submission_health['signal_signal_short_count']}",
            }
        )
    reference_board_power_ground_shorts = int(reference_board_short_safety["power_ground_short_count"])
    reference_board_power_signal_shorts = int(reference_board_short_safety["power_signal_or_ground_signal_short_count"])
    reference_board_signal_signal_shorts = int(reference_board_short_safety["signal_signal_short_count"])
    board_power_ground_shorts = max(
        0,
        int(submission_board_short_safety["power_ground_short_count"]) - reference_board_power_ground_shorts,
    )
    board_power_signal_shorts = max(
        0,
        int(submission_board_short_safety["power_signal_or_ground_signal_short_count"]) - reference_board_power_signal_shorts,
    )
    board_signal_signal_shorts = max(
        0,
        int(submission_board_short_safety["signal_signal_short_count"]) - reference_board_signal_signal_shorts,
    )
    if board_power_ground_shorts > 0:
        score_caps.append(
            {
                "name": "power_ground_board_short",
                "cap": 0.0,
                "detail": f"excess board-wide power-ground same-layer shorts {board_power_ground_shorts}",
            }
        )
    elif board_power_signal_shorts > 0:
        score_caps.append(
            {
                "name": "power_or_ground_signal_board_short",
                "cap": 0.15,
                "detail": f"excess board-wide power/ground to signal same-layer shorts {board_power_signal_shorts}",
            }
        )
    elif board_signal_signal_shorts > 0:
        score_caps.append(
            {
                "name": "signal_signal_board_short",
                "cap": 0.20,
                "detail": f"excess board-wide signal-signal same-layer shorts {board_signal_signal_shorts}",
            }
        )
    if submission_drc.get("available") and not submission_drc.get("skipped"):
        submission_drc_counts = submission_drc.get("issue_counts") or {}
        reference_drc_counts = reference_drc.get("issue_counts") or {}
        excess_drc_errors = max(
            0,
            int(submission_drc_counts.get("error", 0)) - int(reference_drc_counts.get("error", 0)),
        )
        excess_drc_warnings = max(
            0,
            int(submission_drc_counts.get("warning", 0)) - int(reference_drc_counts.get("warning", 0)),
        )
        if excess_drc_errors > 0:
            score_caps.append(
                {
                    "name": "kicad_drc_error_violations",
                    "cap": 0.25,
                    "detail": f"excess KiCad DRC errors {excess_drc_errors}",
                }
            )
        elif excess_drc_warnings >= 10:
            score_caps.append(
                {
                    "name": "excess_kicad_drc_warnings",
                    "cap": 0.65,
                    "detail": f"excess KiCad DRC warnings {excess_drc_warnings}",
                }
            )
    if submission_erc.get("available") and not submission_erc.get("skipped"):
        submission_erc_counts = submission_erc.get("issue_counts") or {}
        reference_erc_counts = reference_erc.get("issue_counts") or {}
        excess_erc_errors = max(
            0,
            int(submission_erc_counts.get("error", 0)) - int(reference_erc_counts.get("error", 0)),
        )
        excess_erc_warnings = max(
            0,
            int(submission_erc_counts.get("warning", 0)) - int(reference_erc_counts.get("warning", 0)),
        )
        if excess_erc_errors > 0:
            score_caps.append(
                {
                    "name": "kicad_erc_error_violations",
                    "cap": 0.25,
                    "detail": f"excess KiCad ERC errors {excess_erc_errors}",
                }
            )
        elif excess_erc_warnings >= 10:
            score_caps.append(
                {
                    "name": "excess_kicad_erc_warnings",
                    "cap": 0.65,
                    "detail": f"excess KiCad ERC warnings {excess_erc_warnings}",
                }
            )
    if reference_geometry_signature.impedance_profile and impedance_score < 0.20:
        score_caps.append(
            {
                "name": "implausible_pcb_impedance_profile",
                "cap": 0.45,
                "detail": f"PCB impedance plausibility score {impedance_score:.3f}",
            }
        )
    if reference_high_speed_families and high_speed_pair_score < 0.50:
        score_caps.append(
            {
                "name": "missing_or_implausible_high_speed_pair_geometry",
                "cap": 0.35,
                "detail": f"high-speed pair quality score {high_speed_pair_score:.3f}",
            }
        )
    if behavioral_shape_score < 0.20 and geometry_shape_score < 0.20:
        score_caps.append(
            {
                "name": "missing_simulated_io_transfer_response",
                "cap": 0.05,
                "detail": f"behavioral family response {behavioral_shape_score:.3f}, geometry family response {geometry_shape_score:.3f}",
            }
        )
    reference_shorts = int(reference_geometry_signature.model_summary.get("same_layer_trace_shorts", 0))
    submission_shorts = int(submission_geometry_signature.model_summary.get("same_layer_trace_shorts", 0))
    if submission_shorts > max(reference_shorts + 5, reference_shorts * 2):
        score_caps.append(
            {
                "name": "excess_same_layer_trace_shorts",
                "cap": 0.15,
                "detail": f"same-layer trace shorts {submission_shorts}, reference {reference_shorts}",
            }
        )
    if score_caps:
        io_score = min(io_score, *(float(item["cap"]) for item in score_caps))
    raw["score_components"] = {
        "io_simulation": {
            "score": io_score,
            "subscores": [item for _weight, item in subscores],
            "score_caps": score_caps,
            "submission_simulation": submission_signature.to_dict(),
            "reference_simulation": reference_signature.to_dict(),
            "submission_pcb_geometry_simulation": submission_geometry_signature.to_dict(),
            "reference_pcb_geometry_simulation": reference_geometry_signature.to_dict(),
            "submission_known_io_verification": submission_known_signature.to_dict(),
            "reference_known_io_verification": reference_known_signature.to_dict(),
            "submission_realized_external_copper_profile": dict(sorted(submission_realized_external_copper.items())),
            "reference_realized_external_copper_profile": dict(sorted(reference_realized_external_copper.items())),
            "submission_external_net_degree_profile": dict(sorted(submission_external_net_degrees.items())),
            "reference_external_net_degree_profile": dict(sorted(reference_external_net_degrees.items())),
            "submission_external_net_route_profile": dict(sorted(submission_external_net_routes.items())),
            "reference_external_net_route_profile": dict(sorted(reference_external_net_routes.items())),
            "submission_semantic_external_net_profile": dict(sorted(submission_semantic_external_nets.items())),
            "reference_semantic_external_net_profile": dict(sorted(reference_semantic_external_nets.items())),
            "submission_role_inventory_profile": dict(sorted(submission_role_inventory.items())),
            "reference_role_inventory_profile": dict(sorted(reference_role_inventory.items())),
            "submission_external_io_health": submission_health,
            "reference_external_io_health": reference_health,
            "submission_board_short_safety": submission_board_short_safety,
            "reference_board_short_safety": reference_board_short_safety,
            "submission_functional_contract": submission_functional,
            "reference_functional_contract": reference_functional,
            "submission_internal_functional_realization": submission_internal_realization,
            "reference_internal_functional_realization": reference_internal_realization,
            "submission_kicad_drc": submission_drc,
            "reference_kicad_drc": reference_drc,
            "submission_kicad_erc": submission_erc,
            "reference_kicad_erc": reference_erc,
            "submission_schematic_board_consistency": submission_schematic_consistency,
            "reference_schematic_board_consistency": reference_schematic_consistency,
            "component_function_realization": component_realization,
            "submission_active_power_integrity": submission_active_power_integrity,
            "reference_active_power_integrity": reference_active_power_integrity,
            "submission_fabrication_geometry": submission_fabrication_geometry,
            "reference_fabrication_geometry": reference_fabrication_geometry,
            "simulated_io_transfer_response_profile": {
                "submission": dict(sorted(submission_transfer_profile.items())),
                "reference_diagnostic": dict(sorted(reference_transfer_profile.items())),
                "submission_counts": transfer_counts,
                "reference_counts": _transfer_profile_counts(reference_transfer_profile),
                "requirements": transfer_requirements,
                "response_score": transfer_response_score,
            },
        }
    }
    metrics["build_success"] = 1.0
    metrics["task_score"] = io_score
    metrics["overall_score"] = io_score
    metrics["reward"] = io_score
    return TaskEvaluation(raw=raw, metrics=metrics)


def unsupported_io_simulation_evaluation(
    task: TaskSpec,
    project_dir: Path,
    work_dir: Path,
    *,
    source_metadata: dict[str, Any] | None = None,
    reason: str = MISSING_ORACLE_REASON,
) -> TaskEvaluation:
    work_dir.mkdir(parents=True, exist_ok=True)
    source_metadata = source_metadata or {}
    message = (
        f"{task.task_id} has no explicit I/O simulation oracle; "
        "proxy PCB, component, routing, and outline scores are disabled"
    )
    raw: dict[str, Any] = {
        "task_id": task.task_id,
        "project_dir": str(project_dir),
        "grading_model": GRADING_MODEL,
        "scoring_mode": "explicit_io_simulation",
        "supported": False,
        "unsupported": True,
        "unsupported_reason": reason,
        "failures": [message],
        "score_components": {},
        "oracle": None,
        "source_repo_url": source_metadata.get("source_repo_url", ""),
        "source_commit": source_metadata.get("source_commit", ""),
        "license": source_metadata.get("license", ""),
    }
    metrics = {
        "submission_exists": 0.0,
        "build_success": 0.0,
        "task_score": 0.0,
        "overall_score": 0.0,
        "reward": 0.0,
        "error_message": message,
    }
    return TaskEvaluation(raw=raw, metrics=metrics)


def evaluate_with_io_simulation_oracle(
    task: TaskSpec,
    project_dir: Path,
    work_dir: Path,
    *,
    source_metadata: dict[str, Any] | None = None,
) -> TaskEvaluation:
    oracle = get_io_simulation_oracle(task.task_id)
    if oracle is None:
        return unsupported_io_simulation_evaluation(
            task,
            project_dir,
            work_dir,
            source_metadata=source_metadata,
        )
    return oracle.evaluate(task, project_dir, work_dir, source_metadata=source_metadata or {})
