import json
import re
import shutil
from types import SimpleNamespace
from pathlib import Path

import tasks.io_simulation_oracles as io_oracles
from tasks.kicad_common import load_board_model
from tasks.source_backed_task import _boundary_references, _source_board_path, remove_footprint_block
from tasks.source_backed_tasks import load_source_backed_task_catalog
from tasks.specs import load_all_task_specs, load_task_ids
from tasks.task_packs import (
    stage_task_pack,
    stage_runtime_task_pack,
    verify_task_canaries,
    verify_task_pack_pytest,
    write_task_pack_manifest,
)


def test_active_power_integrity_is_scored_relative_to_reference() -> None:
    submission = {
        "active_with_signal_count": 6,
        "score": 1 / 3,
    }
    reference = {
        "active_with_signal_count": 6,
        "score": 1 / 3,
    }

    assert io_oracles._relative_active_power_integrity_score(submission, reference) == 1.0


def test_fabrication_geometry_is_scored_relative_to_reference() -> None:
    submission = {
        "track_count": 12,
        "via_count": 4,
        "outline_area_mm2": 0.0,
        "score": 0.8,
    }
    reference = {
        "track_count": 12,
        "via_count": 4,
        "outline_area_mm2": 0.0,
        "score": 0.8,
    }

    assert io_oracles._relative_fabrication_geometry_score(submission, reference) == 1.0


def _net_ids_by_name(board_text: str) -> dict[str, str]:
    return {
        match.group(2): match.group(1)
        for match in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"\)', board_text)
    }


def _remove_top_level_blocks(board_text: str, heads: set[str]) -> str:
    kept: list[str] = []
    skipping = False
    depth = 0
    for line in board_text.splitlines():
        stripped = line.lstrip()
        if not skipping and any(stripped.startswith(f"({head}") for head in heads):
            skipping = True
            depth = line.count("(") - line.count(")")
            if depth <= 0:
                skipping = False
            continue
        if skipping:
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                skipping = False
            continue
        kept.append(line)
    return "\n".join(kept) + "\n"


def test_task_catalog_matches_enabled_source_backed_catalog() -> None:
    task_ids = set(load_task_ids())
    assert len(task_ids) == 40
    assert "led_red_5v_5ma" not in task_ids


def test_source_backed_pack_is_standalone(tmp_path: Path) -> None:
    task = load_all_task_specs()["nanoupdi"]
    pack_dir = stage_task_pack(task, tmp_path)
    metadata = json.loads((pack_dir / "task.json").read_text(encoding="utf-8"))
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()

    assert (pack_dir / "task.py").exists()
    assert (pack_dir / "task.toml").exists()
    assert (pack_dir / "prompt.txt").exists()
    assert (pack_dir / "gold" / "reference").is_dir()
    assert (pack_dir / "source_snapshot").is_dir()
    assert (pack_dir / "tasks" / "source_backed_task.py").exists()
    assert (pack_dir / "tasks" / "source_backed_tasks.toml").exists()
    assert (pack_dir / "io_contract.json").exists()
    assert (pack_dir / "functional_contract.json").exists()
    assert (pack_dir / "tests" / "test_pack.py").exists()
    assert (pack_dir / "pyproject.toml").exists()
    assert metadata["standalone"] is True
    assert metadata["runtime_task_dir"] == "."
    assert metadata["contains_reference_artifact"] is True
    assert metadata["reference_artifact_visibility"] == "public_huggingface_full_pack"
    assert metadata["scoring_mode"] == "explicit_io_simulation"
    assert metadata["scoring_supported"] is True
    assert metadata["unsupported_reason"] == ""
    assert metadata["io_contract_path"] == "io_contract.json"
    assert metadata["functional_contract_path"] == "functional_contract.json"
    assert metadata["canaries"]["mutations"] == "canaries/mutations"
    assert metadata["canaries"]["mutation_max_score"] == 0.75
    mutation_dirs = sorted(path.name for path in (pack_dir / "canaries" / "mutations").iterdir() if path.is_dir())
    assert "missing_board_outline" in mutation_dirs
    assert "unrouted_external_nets" in mutation_dirs
    assert "swapped_connector_pins" in mutation_dirs
    assert "active_device_without_power_or_ground" in mutation_dirs
    assert "frozen_non_boundary_mutation_references" not in metadata
    assert catalog[task.task_id].task_id == task.task_id


def test_runtime_task_pack_does_not_mount_reference_artifact(tmp_path: Path) -> None:
    task = load_all_task_specs()["nanoupdi"]
    pack_dir = stage_runtime_task_pack(task, tmp_path)
    metadata = json.loads((pack_dir / "task.json").read_text(encoding="utf-8"))

    assert (pack_dir / "prompt.txt").exists()
    assert (pack_dir / "task.toml").exists()
    assert (pack_dir / "README.md").exists()
    assert not (pack_dir / "gold").exists()
    assert not (pack_dir / "source_snapshot").exists()
    assert not (pack_dir / "canaries").exists()
    assert not (pack_dir / "tasks").exists()
    assert not (pack_dir / "io_contract.json").exists()
    assert not (pack_dir / "functional_contract.json").exists()
    assert metadata["contains_reference_artifact"] is False
    assert metadata["reference_artifact_visibility"] == "not_mounted_in_runtime"
    assert metadata["public_reference_artifact"]["available_to_agent_runtime"] is False
    assert metadata["public_reference_artifact"]["available_in_huggingface_full_pack"] is True
    assert metadata["runtime_reference_artifact"]["available_in_mounted_runtime"] is False
    assert metadata["scoring_mode"] == "explicit_io_simulation"
    assert metadata["scoring_supported"] is True
    assert metadata["unsupported_reason"] == ""


def test_source_backed_task_canaries_use_io_simulation_oracle(tmp_path: Path) -> None:
    task = load_all_task_specs()["nanoupdi"]
    pack_dir = stage_task_pack(task, tmp_path)
    scores = verify_task_canaries(task, pack_dir)
    assert scores["supported"] is True
    assert scores["verified"] is True
    assert scores["pass_score"] == 1.0
    assert scores["fail_score"] < 1.0
    assert scores["mutation_scores"]
    assert max(scores["mutation_scores"].values()) <= 0.75


def test_task_specific_calibrated_oracle_is_recorded(tmp_path: Path) -> None:
    task = load_all_task_specs()["usb_c_female_breakout"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    evaluation = task.evaluate_project(source_spec.reference_project_dir, tmp_path / "work", image="")

    assert evaluation.metrics["overall_score"] == 1.0
    calibrated = evaluation.raw["oracle"]["calibrated_task_oracle"]
    assert calibrated["name"] == "usb_c_breakout_continuity_orientation"
    assert all(check["passed"] for check in calibrated["checks"])


def test_staged_source_backed_pack_pytest_runs(tmp_path: Path) -> None:
    task = load_all_task_specs()["nanoupdi"]
    pack_dir = stage_task_pack(task, tmp_path)
    verify_task_pack_pytest(pack_dir)


def test_io_simulation_score_is_refdes_invariant_for_equivalent_board(tmp_path: Path) -> None:
    task = load_all_task_specs()["usb_c_female_breakout"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    submission_dir = tmp_path / "submission"
    shutil.copytree(source_spec.reference_project_dir, submission_dir)
    board_path = _source_board_path(submission_dir, source_spec.project_stem)
    board_text = board_path.read_text(encoding="utf-8")
    board_path.write_text(
        board_text.replace('"K1"', '"J101"').replace('"K2"', '"J102"'),
        encoding="utf-8",
    )

    evaluation = task.evaluate_project(submission_dir, tmp_path / "work", image="")
    component = evaluation.raw["score_components"]["io_simulation"]
    diagnostic = {
        item["name"]: item["score"]
        for item in component["subscores"]
        if item["name"] == "diagnostic_exact_reference_io_partition"
    }
    assert evaluation.metrics["overall_score"] == 1.0
    assert diagnostic["diagnostic_exact_reference_io_partition"] == 0.0


def test_io_simulation_caps_board_with_missing_routed_copper(tmp_path: Path) -> None:
    task = load_all_task_specs()["usb_c_female_breakout"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    submission_dir = tmp_path / "submission"
    shutil.copytree(source_spec.reference_project_dir, submission_dir)
    board_path = _source_board_path(submission_dir, source_spec.project_stem)
    board_path.write_text(
        _remove_top_level_blocks(board_path.read_text(encoding="utf-8"), {"segment", "via", "zone"}),
        encoding="utf-8",
    )

    evaluation = task.evaluate_project(submission_dir, tmp_path / "work", image="")
    component = evaluation.raw["score_components"]["io_simulation"]
    cap_names = {cap["name"] for cap in component["score_caps"]}
    assert evaluation.metrics["overall_score"] == 0.0
    assert "too_little_routed_copper_for_reference_interfaces" in cap_names


def test_io_simulation_caps_zone_heavy_board_with_all_copper_removed(tmp_path: Path) -> None:
    task = load_all_task_specs()["nanoupdi"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    submission_dir = tmp_path / "submission"
    shutil.copytree(source_spec.reference_project_dir, submission_dir)
    board_path = _source_board_path(submission_dir, source_spec.project_stem)
    board_path.write_text(
        _remove_top_level_blocks(board_path.read_text(encoding="utf-8"), {"segment", "via", "zone"}),
        encoding="utf-8",
    )

    evaluation = task.evaluate_project(submission_dir, tmp_path / "work", image="")
    component = evaluation.raw["score_components"]["io_simulation"]
    cap_names = {cap["name"] for cap in component["score_caps"]}
    assert evaluation.metrics["overall_score"] == 0.0
    assert "too_little_routed_copper_for_reference_interfaces" in cap_names


def test_io_simulation_tolerates_plausible_route_width_changes(tmp_path: Path) -> None:
    task = load_all_task_specs()["usb_c_female_breakout"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    submission_dir = tmp_path / "submission"
    shutil.copytree(source_spec.reference_project_dir, submission_dir)
    board_path = _source_board_path(submission_dir, source_spec.project_stem)
    board_lines = []
    for line in board_path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("(segment "):
            line = re.sub(r"\(width\s+[0-9.]+\)", "(width 0.35)", line)
        board_lines.append(line)
    board_path.write_text("\n".join(board_lines) + "\n", encoding="utf-8")

    evaluation = task.evaluate_project(submission_dir, tmp_path / "work", image="")
    component = evaluation.raw["score_components"]["io_simulation"]
    subscore_by_name = {item["name"]: item["score"] for item in component["subscores"]}
    assert evaluation.metrics["overall_score"] >= 0.85
    assert subscore_by_name["diagnostic_external_net_routed_geometry_contract"] < 1.0


def test_io_simulation_caps_implausibly_tiny_trace_widths(tmp_path: Path) -> None:
    task = load_all_task_specs()["usb_c_female_breakout"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    submission_dir = tmp_path / "submission"
    shutil.copytree(source_spec.reference_project_dir, submission_dir)
    board_path = _source_board_path(submission_dir, source_spec.project_stem)
    board_lines = []
    for line in board_path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("(segment "):
            line = re.sub(r"\(width\s+[0-9.]+\)", "(width 0.03)", line)
        board_lines.append(line)
    board_path.write_text("\n".join(board_lines) + "\n", encoding="utf-8")

    evaluation = task.evaluate_project(submission_dir, tmp_path / "work", image="")
    component = evaluation.raw["score_components"]["io_simulation"]
    cap_names = {cap["name"] for cap in component["score_caps"]}
    subscore_by_name = {item["name"]: item["score"] for item in component["subscores"]}
    assert subscore_by_name["pcb_fabrication_geometry"] < 1.0
    assert evaluation.metrics["overall_score"] <= 0.35
    assert "implausible_min_trace_width" in cap_names


def test_io_simulation_tolerates_generic_signal_net_names(tmp_path: Path) -> None:
    task = load_all_task_specs()["usb_c_female_breakout"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    submission_dir = tmp_path / "submission"
    shutil.copytree(source_spec.reference_project_dir, submission_dir)
    board_path = _source_board_path(submission_dir, source_spec.project_stem)
    board_text = board_path.read_text(encoding="utf-8")
    for index, net_name in enumerate(("CC1", "CC2", "D+", "D-", "SBU1", "SBU2"), start=1):
        board_text = board_text.replace(f'"{net_name}"', f'"SIG{index}"')
    board_path.write_text(board_text, encoding="utf-8")

    evaluation = task.evaluate_project(submission_dir, tmp_path / "work", image="")
    assert evaluation.metrics["overall_score"] >= 0.95


def test_io_simulation_caps_wrong_external_connector_pin_mapping(tmp_path: Path) -> None:
    task = load_all_task_specs()["usb_c_female_breakout"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    submission_dir = tmp_path / "submission"
    shutil.copytree(source_spec.reference_project_dir, submission_dir)
    board_path = _source_board_path(submission_dir, source_spec.project_stem)
    board_text = board_path.read_text(encoding="utf-8")
    original_pad = (
        '(pad "5" thru_hole circle locked (at 1.27 0 270) (size 1.7 1.7) '
        '(drill 1) (layers *.Cu *.Mask)\n      (net 4 "D+")'
    )
    wrong_pad = (
        '(pad "5" thru_hole circle locked (at 1.27 0 270) (size 1.7 1.7) '
        '(drill 1) (layers *.Cu *.Mask)\n      (net 5 "D-")'
    )
    assert original_pad in board_text
    board_path.write_text(board_text.replace(original_pad, wrong_pad, 1), encoding="utf-8")

    evaluation = task.evaluate_project(submission_dir, tmp_path / "work", image="")
    component = evaluation.raw["score_components"]["io_simulation"]
    subscore_by_name = {item["name"]: item["score"] for item in component["subscores"]}
    cap_names = {cap["name"] for cap in component["score_caps"]}
    assert subscore_by_name["semantic_external_io_net_verification"] < 0.85
    assert evaluation.metrics["overall_score"] <= 0.20
    assert "incomplete_external_io_pin_net_mapping" in cap_names


def test_io_simulation_caps_board_with_functional_transfer_elements_removed(tmp_path: Path) -> None:
    task = load_all_task_specs()["bq24295_power_path_board"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    submission_dir = tmp_path / "submission"
    shutil.copytree(source_spec.reference_project_dir, submission_dir)
    board_path = _source_board_path(submission_dir, source_spec.project_stem)
    board = load_board_model(board_path)
    boundary_references = set(_boundary_references(board))
    board_text = board_path.read_text(encoding="utf-8")
    for reference in list(board.footprints):
        if reference in boundary_references:
            continue
        board_text = remove_footprint_block(board_text, reference)
    board_path.write_text(board_text, encoding="utf-8")

    evaluation = task.evaluate_project(submission_dir, tmp_path / "work", image="")
    component = evaluation.raw["score_components"]["io_simulation"]
    cap_names = {cap["name"] for cap in component["score_caps"]}
    assert evaluation.metrics["overall_score"] <= 0.05
    assert "missing_simulated_signal_io_transfer_response" in cap_names
    assert "missing_task_required_internal_functional_realization" in cap_names
    assert "missing_reference_component_function_realization" in cap_names
    assert "missing_active_device_power_integrity" in cap_names


def test_io_simulation_caps_excess_kicad_drc_errors(tmp_path: Path, monkeypatch) -> None:
    task = load_all_task_specs()["usb_c_female_breakout"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    submission_dir = tmp_path / "submission"
    shutil.copytree(source_spec.reference_project_dir, submission_dir)

    def fake_drc_validation(board_path: Path, work_dir: Path, *, label: str) -> dict[str, object]:
        error_count = 1 if label == "submission" else 0
        return {
            "available": True,
            "skipped": False,
            "score": 0.0 if error_count else 1.0,
            "issue_counts": {
                "error": error_count,
                "warning": 0,
                "exclusion": 0,
                "unknown": 0,
                "total": error_count,
            },
            "detail": "",
            "report_path": str(work_dir / f"{label}.json"),
        }

    monkeypatch.setattr(io_oracles, "_kicad_cli_drc_validation", fake_drc_validation)

    evaluation = task.evaluate_project(submission_dir, tmp_path / "work", image="")
    component = evaluation.raw["score_components"]["io_simulation"]
    cap_names = {cap["name"] for cap in component["score_caps"]}
    subscore_by_name = {item["name"]: item["score"] for item in component["subscores"]}
    assert subscore_by_name["kicad_drc_manufacturability"] < 1.0
    assert evaluation.metrics["overall_score"] <= 0.25
    assert "kicad_drc_error_violations" in cap_names


def test_io_simulation_caps_excess_kicad_erc_errors(tmp_path: Path, monkeypatch) -> None:
    task = load_all_task_specs()["usb_c_female_breakout"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    submission_dir = tmp_path / "submission"
    shutil.copytree(source_spec.reference_project_dir, submission_dir)

    def fake_erc_validation(schematic_path: Path | None, work_dir: Path, *, label: str) -> dict[str, object]:
        error_count = 1 if label == "submission" else 0
        return {
            "available": True,
            "skipped": False,
            "score": 0.0 if error_count else 1.0,
            "issue_counts": {
                "error": error_count,
                "warning": 0,
                "exclusion": 0,
                "unknown": 0,
                "total": error_count,
            },
            "detail": "",
            "report_path": str(work_dir / f"{label}.json"),
        }

    monkeypatch.setattr(io_oracles, "_kicad_cli_erc_validation", fake_erc_validation)

    evaluation = task.evaluate_project(submission_dir, tmp_path / "work", image="")
    component = evaluation.raw["score_components"]["io_simulation"]
    cap_names = {cap["name"] for cap in component["score_caps"]}
    subscore_by_name = {item["name"]: item["score"] for item in component["subscores"]}
    assert subscore_by_name["kicad_erc_electrical_rules"] < 1.0
    assert evaluation.metrics["overall_score"] <= 0.25
    assert "kicad_erc_error_violations" in cap_names


def test_kicad_drc_retries_without_schematic_parity_for_older_cli(tmp_path: Path, monkeypatch) -> None:
    board_path = tmp_path / "board.kicad_pcb"
    board_path.write_text("(kicad_pcb)\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        _ = kwargs
        commands.append(list(command))
        if "--schematic-parity" in command:
            return SimpleNamespace(returncode=2, stdout="", stderr="unrecognized option '--schematic-parity'")
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_text('{"violations": []}\n', encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(io_oracles.shutil, "which", lambda name: "/usr/bin/kicad-cli" if name == "kicad-cli" else None)
    monkeypatch.setattr(io_oracles.subprocess, "run", fake_run)

    result = io_oracles._kicad_cli_drc_validation(board_path, tmp_path / "work", label="submission")

    assert result["score"] == 1.0
    assert result["schematic_parity_used"] is False
    assert len(commands) == 2
    assert "--schematic-parity" in commands[0]
    assert "--schematic-parity" not in commands[1]


def test_io_simulation_caps_external_power_ground_short(tmp_path: Path) -> None:
    task = load_all_task_specs()["nanoupdi"]
    catalog = load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    ).tasks_by_id()
    source_spec = catalog[task.task_id]
    submission_dir = tmp_path / "submission"
    shutil.copytree(source_spec.reference_project_dir, submission_dir)
    board_path = _source_board_path(submission_dir, source_spec.project_stem)
    board_text = board_path.read_text(encoding="utf-8")
    net_ids = _net_ids_by_name(board_text)
    x0, y0, x1, y1 = 147.4, 77.1, 156.4, 98.1
    xm = (x0 + x1) / 2
    ym = (y0 + y1) / 2
    injected = (
        f'\n  (segment (start {x0:.3f} {ym:.3f}) (end {x1:.3f} {ym:.3f}) '
        f'(width 0.5) (layer "F.Cu") (net {net_ids["+5V"]}) (uuid "eda-bench-test-short-pwr"))\n'
        f'  (segment (start {xm:.3f} {y0:.3f}) (end {xm:.3f} {y1:.3f}) '
        f'(width 0.5) (layer "F.Cu") (net {net_ids["GND"]}) (uuid "eda-bench-test-short-gnd"))\n'
    )
    insert_at = board_text.rfind("\n)")
    board_path.write_text(board_text[:insert_at] + injected + board_text[insert_at:], encoding="utf-8")

    evaluation = task.evaluate_project(submission_dir, tmp_path / "work", image="")
    component = evaluation.raw["score_components"]["io_simulation"]
    cap_names = {cap["name"] for cap in component["score_caps"]}
    assert evaluation.metrics["overall_score"] == 0.0
    assert "power_ground_external_short" in cap_names
    assert "power_ground_board_short" in cap_names


def test_resolve_runtime_task_dir_uses_pack_root(tmp_path: Path) -> None:
    manifest_path = Path("tasks/task_pack_manifest.json")
    original_manifest = manifest_path.read_text(encoding="utf-8")
    try:
        write_task_pack_manifest(
            repo_id="dummy/repo",
            path_prefix="task-packs/v2",
            full_path_prefix="full-task-packs/v2",
            revision="deadbeef",
            task_ids=["nanoupdi"],
            path=manifest_path,
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["path_prefix"] == "task-packs/v2"
        assert "nanoupdi" in manifest["task_ids"]
    finally:
        manifest_path.write_text(original_manifest, encoding="utf-8")
