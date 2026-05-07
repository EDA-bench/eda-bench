from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from textwrap import dedent
from typing import Any

from bench.config import env_value
from bench.provenance import load_hf_provenance_config, resolve_hf_token
from huggingface_hub import HfApi, snapshot_download
from tasks.io_simulation_oracles import build_functional_io_contract, build_static_io_contract
from tasks.kicad_common import load_board_model
from tasks.source_backed_task import (
    _fast_net_name_to_id,
    _find_balanced_block,
    _footprint_block_has_reference,
    _net_expr,
    _net_role,
    _reference_prefix,
    _replace_pad_net_in_footprint,
    _resolve_reference_board_path,
    _source_board_path,
    build_external_io_signature,
    remove_footprint_block,
    remove_routing_for_net,
)
from tasks.source_backed_tasks import SourceBackedTaskSpec, load_source_backed_task_catalog
from tasks.specs import TaskSpec, load_all_task_specs, load_task_spec

MANIFEST_PATH = Path(__file__).resolve().with_name("task_pack_manifest.json")
DEFAULT_PATH_PREFIX = "task-packs/v2"
DEFAULT_FULL_PATH_PREFIX = "full-task-packs/v2"
PACK_VERSION = 2
FAIL_CANARY_MAX_SCORE = 0.75
MUTATION_CANARY_MAX_SCORE = 0.75
_EXCLUDED_TASK_ASSET_NAMES = {"__pycache__"}
_RUNTIME_TASK_ASSET_NAMES = {"prompt.txt", "task.toml"}
_SOURCE_BACKED_SUPPORT_FILES = (
    "__init__.py",
    "io_simulation_oracles.py",
    "kicad_common.py",
    "source_backed_task.py",
    "source_backed_tasks.py",
    "specs.py",
)

@dataclass(frozen=True)
class TaskPackManifest:
    repo_id: str
    path_prefix: str
    full_path_prefix: str
    revision: str
    generated_at: str
    task_ids: tuple[str, ...]

    def pack_path(self, task_id: str) -> str:
        return f"{self.path_prefix}/{task_id}"

    def runtime_path(self, task_id: str) -> str:
        return self.pack_path(task_id)

    def full_pack_path(self, task_id: str) -> str:
        return f"{self.full_path_prefix}/{task_id}"

    def canary_path(self, task_id: str) -> str:
        return f"{self.full_pack_path(task_id)}/canaries"


def _source_backed_specs(include_disabled: bool = False) -> dict[str, SourceBackedTaskSpec]:
    return load_source_backed_task_catalog(include_disabled=include_disabled).tasks_by_id()


def _source_spec_for_task(task: TaskSpec, *, include_disabled: bool = True) -> SourceBackedTaskSpec:
    pack_catalog = task.task_dir / "tasks" / "source_backed_tasks.toml"
    catalog = load_source_backed_task_catalog(
        path=pack_catalog if pack_catalog.exists() else None,
        include_disabled=include_disabled,
    )
    return catalog.tasks_by_id()[task.task_id]


def _task_pack_repo_id(repo_root: Path) -> str:
    task_pack_repo_id = env_value("HF_TASK_PACK_REPO_ID", root=repo_root)
    if task_pack_repo_id:
        return task_pack_repo_id
    return load_hf_provenance_config(repo_root).repo_id


def load_task_pack_manifest(path: Path = MANIFEST_PATH) -> TaskPackManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    task_ids = payload.get("task_ids", [])
    if not isinstance(task_ids, list) or not all(isinstance(item, str) for item in task_ids):
        raise TypeError(f"invalid task_ids in {path}")
    return TaskPackManifest(
        repo_id=str(payload["repo_id"]),
        path_prefix=str(payload["path_prefix"]).strip("/"),
        full_path_prefix=str(payload.get("full_path_prefix", DEFAULT_FULL_PATH_PREFIX)).strip("/"),
        revision=str(payload["revision"]),
        generated_at=str(payload["generated_at"]),
        task_ids=tuple(task_ids),
    )


def write_task_pack_manifest(
    *,
    repo_id: str,
    path_prefix: str,
    full_path_prefix: str = DEFAULT_FULL_PATH_PREFIX,
    revision: str,
    task_ids: list[str],
    path: Path = MANIFEST_PATH,
) -> Path:
    payload = {
        "repo_id": repo_id,
        "path_prefix": path_prefix.strip("/"),
        "full_path_prefix": full_path_prefix.strip("/"),
        "revision": revision,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_ids": sorted(task_ids),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _copy_task_assets(task: TaskSpec, pack_dir: Path) -> None:
    for asset in sorted(task.task_dir.iterdir()):
        if asset.name in _EXCLUDED_TASK_ASSET_NAMES:
            continue
        target = pack_dir / asset.name
        if asset.is_dir():
            shutil.copytree(asset, target)
        else:
            shutil.copy2(asset, target)


def _copy_runtime_task_assets(task: TaskSpec, pack_dir: Path) -> None:
    for asset_name in sorted(_RUNTIME_TASK_ASSET_NAMES):
        asset = task.task_dir / asset_name
        if asset.exists():
            shutil.copy2(asset, pack_dir / asset.name)


def _write_pack_metadata(task: TaskSpec, pack_dir: Path) -> None:
    source_spec = _source_spec_for_task(task)
    payload: dict[str, Any] = {
        "task_id": task.task_id,
        "title": task.title,
        "difficulty": task.difficulty,
        "pack_version": PACK_VERSION,
        "standalone": True,
        "contains_reference_artifact": True,
        "reference_artifact_visibility": "public_huggingface_full_pack",
        "scoring_mode": "explicit_io_simulation",
        "scoring_supported": True,
        "unsupported_reason": "",
        "runtime_task_dir": ".",
        "io_contract_path": "io_contract.json",
        "functional_contract_path": "functional_contract.json",
        "grader_support_dir": "tasks",
        "pytest_dir": "tests",
        "canaries": {
            "pass": "canaries/pass",
            "fail": "canaries/fail",
            "fail_max_score": FAIL_CANARY_MAX_SCORE,
            "mutations": "canaries/mutations",
            "mutation_max_score": MUTATION_CANARY_MAX_SCORE,
        },
    }
    if source_spec is not None:
        payload["source_snapshot"] = {
            "repo_url": source_spec.source.repo_url,
            "commit": source_spec.source.commit,
            "license": source_spec.source.license,
            "path": "source_snapshot",
        }
    (pack_dir / "task.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_runtime_pack_metadata(task: TaskSpec, pack_dir: Path) -> None:
    source_spec = _source_spec_for_task(task)
    payload: dict[str, Any] = {
        "task_id": task.task_id,
        "title": task.title,
        "difficulty": task.difficulty,
        "pack_version": PACK_VERSION,
        "standalone": False,
        "contains_reference_artifact": False,
        "reference_artifact_visibility": "not_mounted_in_runtime",
        "scoring_mode": "explicit_io_simulation",
        "scoring_supported": True,
        "unsupported_reason": "",
        "runtime_task_dir": ".",
        "allowed_inputs": [
            "prompt.txt",
            "task.toml",
            "standard KiCad libraries installed in the agent image",
        ],
    }
    if source_spec is not None:
        payload["runtime_reference_artifact"] = {
            "repo_url": source_spec.source.repo_url,
            "commit": source_spec.source.commit,
            "license": source_spec.source.license,
            "available_in_mounted_runtime": False,
        }
        payload["public_reference_artifact"] = {
            "repo_url": source_spec.source.repo_url,
            "commit": source_spec.source.commit,
            "license": source_spec.source.license,
            "available_to_agent_runtime": False,
            "available_in_huggingface_full_pack": True,
        }
    (pack_dir / "task.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_pack_readme(task: TaskSpec, pack_dir: Path) -> None:
    source_spec = _source_spec_for_task(task)
    snapshot_line = ""
    if source_spec is not None:
        snapshot_line = f"- `source_snapshot/`: vendored upstream design snapshot from `{source_spec.source.repo_url}` at `{source_spec.source.commit}`\n"
    text = dedent(
        f"""
        # {task.title}

        Standalone EDA Bench task pack for `{task.task_id}`.

        Contents:
        - `prompt.txt`, `task.toml`, `task.py`, `gold/`, and any task-local assets
        - `tasks/`: duplicated grader support package for this task pack only
        - `io_contract.json`: refdes-invariant external-I/O semantic, topology, and PCB-geometry contract used by the grader
        - `functional_contract.json`: task-semantic external-interface families and routed-I/O requirements used by the grader
        - `tests/test_pack.py`: standalone pytest suite for the I/O simulation oracle
        - `canaries/pass` and `canaries/fail`: frozen submissions for oracle validation
        {snapshot_line}- `task.json`: pack metadata, including scoring support status

        Run locally:

        ```bash
        PYTHONPATH=. uv run pytest -q
        ```
        """
    ).strip()
    (pack_dir / "README.md").write_text(text + "\n", encoding="utf-8")


def _write_runtime_pack_readme(task: TaskSpec, pack_dir: Path) -> None:
    text = dedent(
        f"""
        # {task.title}

        Public runtime task pack for `{task.task_id}`.

        This pack intentionally contains only the prompt and task metadata used by
        an evaluated agent. Hidden reference designs, source snapshots, canaries,
        and grader code are not mounted into the agent container.
        """
    ).strip()
    (pack_dir / "README.md").write_text(text + "\n", encoding="utf-8")


def _write_pack_pyproject(task: TaskSpec, pack_dir: Path) -> None:
    project_name = f"eda-bench-task-{task.task_id.replace('_', '-')}"
    text = dedent(
        f"""
        [project]
        name = "{project_name}"
        version = "0.0.0"
        requires-python = ">=3.11"
        dependencies = ["pytest>=8.0"]

        [tool.pytest.ini_options]
        testpaths = ["tests"]
        addopts = "-q"
        """
    ).strip()
    (pack_dir / "pyproject.toml").write_text(text + "\n", encoding="utf-8")


def _copy_support_package(pack_dir: Path, support_files: tuple[str, ...]) -> None:
    tasks_dir = pack_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    tasks_root = Path(__file__).resolve().parent
    for filename in support_files:
        shutil.copy2(tasks_root / filename, tasks_dir / filename)


def _relative_to(path: Path, root: Path) -> str:
    return path.absolute().relative_to(root.absolute()).as_posix()


def _single_reference_file_name(project_dir: Path, suffix: str, fallback: str) -> str:
    matches = sorted(project_dir.glob(f"*{suffix}"))
    if len(matches) == 1:
        return matches[0].name
    for path in matches:
        if path.name == fallback:
            return path.name
    return fallback


def _write_minimal_source_catalog(pack_dir: Path, spec: SourceBackedTaskSpec) -> None:
    tasks_dir = pack_dir / "tasks"
    readme_path = spec.source.readme_path if spec.source.readme_path.exists() else spec.source.vendored_root / "README.md"
    reference_schematic_name = _single_reference_file_name(
        spec.reference_project_dir,
        ".kicad_sch",
        spec.reference_schematic.name,
    )
    reference_board_name = _single_reference_file_name(
        spec.reference_project_dir,
        ".kicad_pcb",
        spec.reference_board.name,
    )
    lines = [
        "[policy]",
        'strategy = "standalone-source-backed-task-pack"',
        'status = "frozen"',
        f'last_reviewed = "{datetime.now(timezone.utc).date().isoformat()}"',
        'vendor_root = "source_snapshot"',
        f'notes = "Generated standalone task-pack catalog containing only {spec.task_id}."',
        "",
        "[[source]]",
        f'key = "{spec.source.key}"',
        f'name = "{spec.source.name}"',
        f'owner = "{spec.source.owner}"',
        f'repo_url = "{spec.source.repo_url}"',
        f'commit = "{spec.source.commit}"',
        f'license = "{spec.source.license}"',
        f'design_format = "{spec.source.design_format}"',
        'vendored_root = "source_snapshot"',
        f'readme_path = "source_snapshot/{_relative_to(readme_path, spec.source.vendored_root)}"',
    ]
    if spec.source.license_path is not None and spec.source.license_path.exists():
        lines.append(
            f'license_path = "source_snapshot/{_relative_to(spec.source.license_path, spec.source.vendored_root)}"'
        )
    lines.extend(
        [
            f"notes = {json.dumps(spec.source.notes)}",
            "",
            "[[task]]",
            f'task_id = "{spec.task_id}"',
            f'title = "{spec.title}"',
            f'difficulty = "{spec.difficulty}"',
            "enabled = true",
            f'project_stem = "{spec.project_stem}"',
            f'source_key = "{spec.source.key}"',
            'reference_project_dir = "gold/reference"',
            f'reference_schematic = "gold/reference/{reference_schematic_name}"',
            f'reference_board = "gold/reference/{reference_board_name}"',
            f"canary_removed_references = {json.dumps(list(spec.canary_removed_references))}",
            f"canary_ignored_references = {json.dumps(list(spec.canary_ignored_references))}",
            f"notes = {json.dumps(spec.notes)}",
        ]
    )
    text = "\n".join(lines)
    (tasks_dir / "source_backed_tasks.toml").write_text(text + "\n", encoding="utf-8")


def _write_source_backed_grader(task: TaskSpec, pack_dir: Path) -> None:
    grader_text = dedent(
        """
        from __future__ import annotations

        from pathlib import Path

        from tasks.source_backed_task import grade_source_backed_task
        from tasks.source_backed_tasks import load_source_backed_task_catalog
        from tasks.specs import TaskEvaluation, TaskSpec


        CATALOG = load_source_backed_task_catalog(include_disabled=True).tasks_by_id()
        TASK_ID = Path(__file__).absolute().parent.name


        def grade(task: TaskSpec, project_dir: Path, work_dir: Path, *, image: str) -> TaskEvaluation:
            return grade_source_backed_task(
                task,
                project_dir,
                work_dir,
                image=image,
                spec=CATALOG[TASK_ID],
            )
        """
    ).strip()
    (pack_dir / "task.py").write_text(grader_text + "\n", encoding="utf-8")


def _write_static_io_contract(task: TaskSpec, pack_dir: Path) -> None:
    source_spec = _source_spec_for_task(task)
    board = load_board_model(_resolve_reference_board_path(source_spec))
    payload = build_static_io_contract(task, board)
    (pack_dir / "io_contract.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_functional_io_contract(task: TaskSpec, pack_dir: Path) -> None:
    source_spec = _source_spec_for_task(task)
    board = load_board_model(_resolve_reference_board_path(source_spec))
    payload = build_functional_io_contract(task, board)
    (pack_dir / "functional_contract.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_source_backed_pack_tests(task: TaskSpec, pack_dir: Path) -> None:
    test_text = dedent(
        """
        from __future__ import annotations

        import json
        import sys
        from pathlib import Path

        ROOT = Path(__file__).resolve().parents[1]
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))

        from tasks.specs import load_task_spec

        TASK = load_task_spec(ROOT)
        METADATA = json.loads((ROOT / "task.json").read_text(encoding="utf-8"))


        def test_pack_is_standalone() -> None:
            assert (ROOT / "task.py").exists()
            assert (ROOT / "task.toml").exists()
            assert (ROOT / "prompt.txt").exists()
            assert (ROOT / "tests" / "test_pack.py").exists()
            assert (ROOT / "tasks" / "source_backed_task.py").exists()
            assert (ROOT / "tasks" / "source_backed_tasks.toml").exists()
            assert (ROOT / "io_contract.json").exists()
            assert (ROOT / "functional_contract.json").exists()
            assert (ROOT / "source_snapshot").is_dir()
            assert (ROOT / "canaries" / "mutations").is_dir()
            assert METADATA["standalone"] is True
            assert METADATA["grader_support_dir"] == "tasks"
            assert METADATA["contains_reference_artifact"] is True
            assert METADATA["reference_artifact_visibility"] == "public_huggingface_full_pack"
            assert METADATA["scoring_mode"] == "explicit_io_simulation"
            assert METADATA["scoring_supported"] is True
            assert METADATA["unsupported_reason"] == ""
            assert METADATA["io_contract_path"] == "io_contract.json"
            assert METADATA["functional_contract_path"] == "functional_contract.json"
            assert METADATA["canaries"]["mutations"] == "canaries/mutations"


        def test_grader_uses_explicit_io_simulation_oracle() -> None:
            evaluation = TASK.evaluate_project(ROOT / "gold" / "reference", ROOT / ".pytest_cache" / "reference", image="")
            assert evaluation.raw["grading_model"] == "explicit PCB workability oracle score v2"
            assert evaluation.raw["scoring_mode"] == "explicit_io_simulation"
            assert evaluation.raw["unsupported"] is False
            assert set(evaluation.raw["score_components"]) == {"io_simulation"}
            assert evaluation.raw["score_components"]["io_simulation"]["reference_simulation"]["simulated"] is True
            assert evaluation.raw["score_components"]["io_simulation"]["submission_simulation"]["simulated"] is True
            assert evaluation.raw["score_components"]["io_simulation"]["reference_pcb_geometry_simulation"]["simulated"] is True
            assert evaluation.raw["score_components"]["io_simulation"]["submission_pcb_geometry_simulation"]["simulated"] is True
            assert evaluation.metrics["overall_score"] == 1.0
        """
    ).strip()
    tests_dir = pack_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_pack.py").write_text(test_text + "\n", encoding="utf-8")


def _reference_submission_dir(task: TaskSpec, out_dir: Path) -> Path:
    source_spec = _source_spec_for_task(task)
    source_dir = source_spec.reference_project_dir
    dst = out_dir / "reference"
    _copytree(source_dir, dst)
    project_file = dst / f"{source_spec.project_stem}.kicad_pro"
    if not project_file.exists():
        project_file.write_text('{"board": {}, "meta": {"version": 1}, "schematic": {}}\n', encoding="utf-8")
    return dst


def _failing_submission_dir(task: TaskSpec, out_dir: Path) -> Path:
    source_spec = _source_spec_for_task(task)

    reference_dir = _reference_submission_dir(task, out_dir / "tmp")
    dst = out_dir / "fail"
    _copytree(reference_dir, dst)
    reference_board_path = _resolve_reference_board_path(source_spec)
    local_board_path = _source_board_path(dst, source_spec.project_stem)
    board = load_board_model(reference_board_path)
    signature = build_external_io_signature(board)
    if not signature.boundary_refs:
        raise ValueError(f"{task.task_id} does not expose any boundary references")
    boundary_references = {ref.reference for ref in signature.boundary_refs}
    available_references = set(board.footprints)
    active_internal_references = tuple(
        sorted(
            reference
            for reference, footprint in board.footprints.items()
            if reference not in boundary_references
            and footprint.pads
            and _reference_prefix(reference) in {"IC", "Q", "U"}
        )
    )
    removed_references = active_internal_references or tuple(ref.reference for ref in signature.boundary_refs)
    missing_references = sorted(set(removed_references) - available_references)
    if missing_references:
        raise ValueError(
            f"{task.task_id} canary_removed_references not found in board refs: {missing_references}"
        )
    board_text = local_board_path.read_text(encoding="utf-8")
    for removed_reference in removed_references:
        board_text = remove_footprint_block(board_text, removed_reference)
    local_board_path.write_text(board_text, encoding="utf-8")
    shutil.rmtree(reference_dir.parent)
    return dst


def _copy_reference_submission(task: TaskSpec, out_dir: Path, name: str) -> Path:
    reference_dir = _reference_submission_dir(task, out_dir / f"_{name}_src")
    dst = out_dir / name
    _copytree(reference_dir, dst)
    shutil.rmtree(reference_dir.parent)
    return dst


def _external_connected_pads(board: Any) -> list[tuple[str, str, str, str]]:
    pads: list[tuple[str, str, str, str]] = []
    for boundary_ref in build_external_io_signature(board).boundary_refs:
        for pad in boundary_ref.pads:
            if not pad.net or pad.role == "unconnected":
                continue
            pads.append((boundary_ref.reference, pad.pad_name, pad.net, pad.role))
    return pads


def _remove_edge_cuts(text: str) -> str:
    pieces: list[str] = []
    cursor = 0
    removals = 0
    graphic_block_re = re.compile(r"\((gr_line|gr_arc|gr_rect|gr_circle|gr_poly|gr_curve)\b")
    for match in graphic_block_re.finditer(text):
        start = match.start()
        if start < cursor:
            continue
        _, end, block = _find_balanced_block(text, start)
        pieces.append(text[cursor:start])
        if "Edge.Cuts" in block:
            removals += 1
        else:
            pieces.append(block)
        cursor = end
    pieces.append(text[cursor:])
    if removals == 0:
        raise ValueError("no Edge.Cuts board outline graphics found")
    return "".join(pieces)


def _bulk_replace_pad_nets(
    text: str,
    replacements: dict[tuple[str, str], str | None],
) -> str:
    if not replacements:
        raise ValueError("no pad replacements requested")
    by_reference: dict[str, dict[str, str | None]] = {}
    for (reference, pad_name), net_expr in replacements.items():
        by_reference.setdefault(reference, {})[pad_name] = net_expr

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
        for reference, pad_replacements in by_reference.items():
            if not _footprint_block_has_reference(updated_footprint, reference):
                continue
            for pad_name, net_expr in pad_replacements.items():
                updated_footprint, footprint_updates = _replace_pad_net_in_footprint(
                    updated_footprint,
                    pad_name,
                    net_expr,
                )
                updates += footprint_updates
            break
        pieces.append(text[cursor:start])
        pieces.append(updated_footprint)
        cursor = end
        scan_from = end
    pieces.append(text[cursor:])
    if updates == 0:
        raise ValueError("no requested pads were updated")
    return "".join(pieces)


def _write_mutated_board(
    task: TaskSpec,
    out_dir: Path,
    mutation_name: str,
    mutate: Any,
) -> Path | None:
    dst = _copy_reference_submission(task, out_dir, mutation_name)
    source_spec = _source_spec_for_task(task)
    board_path = _source_board_path(dst, source_spec.project_stem)
    board_text = board_path.read_text(encoding="utf-8")
    try:
        mutated_text = mutate(board_text, load_board_model(board_path))
    except Exception:
        shutil.rmtree(dst)
        return None
    if mutated_text == board_text:
        shutil.rmtree(dst)
        return None
    board_path.write_text(mutated_text, encoding="utf-8")
    return dst


def _mutate_missing_board_outline(text: str, _board: Any) -> str:
    if _board.outline_bbox() is None:
        raise ValueError("reference board has no parsed outline")
    return _remove_edge_cuts(text)


def _mutate_unrouted_external_nets(text: str, board: Any) -> str:
    mutated = text
    routed_nets = {track.net for track in board.tracks if track.net} | {via.net for via in board.vias if via.net} | set(board.zone_nets)
    external_nets = {
        net
        for _reference, _pad_name, net, role in _external_connected_pads(board)
        if role != "unconnected" and net in routed_nets
    }
    removals = 0
    for net in sorted(external_nets):
        try:
            mutated = remove_routing_for_net(mutated, net)
            removals += 1
        except ValueError:
            continue
    if removals == 0:
        raise ValueError("no routed external nets found")
    return mutated


def _mutate_isolated_connector_pads(text: str, board: Any) -> str:
    connected_pads = _external_connected_pads(board)
    if not connected_pads:
        raise ValueError("no connected boundary connector pads found")
    replacements = {
        (reference, pad_name): None
        for reference, pad_name, _net, _role in connected_pads
    }
    return _bulk_replace_pad_nets(text, replacements)


def _mutate_power_ground_short(text: str, board: Any) -> str:
    ground_nets = sorted(
        {
            net
            for _reference, _pad_name, net, role in _external_connected_pads(board)
            if role == "ground"
        }
    )
    if not ground_nets:
        raise ValueError("no external ground net found")
    targets = [
        (reference, pad_name)
        for reference, pad_name, _net, role in _external_connected_pads(board)
        if role in {"power", "signal"}
    ]
    if not targets:
        raise ValueError("no external power or signal pad found")
    net_ids = _fast_net_name_to_id(text)
    ground_net_id = net_ids.get(ground_nets[0])
    if ground_net_id is None:
        raise ValueError(f"ground net {ground_nets[0]!r} not found")
    replacements = {
        (reference, pad_name): _net_expr(ground_net_id, ground_nets[0])
        for reference, pad_name in targets
    }
    return _bulk_replace_pad_nets(text, replacements)


def _mutate_swapped_connector_pins(text: str, board: Any) -> str:
    net_ids = _fast_net_name_to_id(text)
    for boundary_ref in build_external_io_signature(board).boundary_refs:
        candidates = [
            pad
            for pad in boundary_ref.pads
            if pad.net
            and pad.role != "unconnected"
            and pad.net in net_ids
        ]
        for left_index, left in enumerate(candidates):
            for right in candidates[left_index + 1 :]:
                if left.net == right.net:
                    continue
                replacements = {
                    (boundary_ref.reference, left.pad_name): _net_expr(net_ids[right.net], right.net),
                    (boundary_ref.reference, right.pad_name): _net_expr(net_ids[left.net], left.net),
                }
                return _bulk_replace_pad_nets(text, replacements)
    raise ValueError("no swappable external connector pins found")


def _mutate_active_without_power_or_ground(text: str, board: Any) -> str:
    boundary_refs = {ref.reference for ref in build_external_io_signature(board).boundary_refs}
    for reference, footprint in sorted(board.footprints.items()):
        if reference in boundary_refs or _reference_prefix(reference) not in {"IC", "Q", "U"}:
            continue
        power_or_ground_pads = [
            pad_name
            for pad_name, pad in sorted(footprint.pads.items())
            if pad.net and (_net_role(pad.net) == "ground" or _net_role(pad.net).startswith("power_"))
        ]
        signal_pads = [
            pad
            for pad in footprint.pads.values()
            if pad.net and _net_role(pad.net) == "signal"
        ]
        if not power_or_ground_pads or not signal_pads:
            continue
        replacements = {
            (reference, pad_name): None
            for pad_name in power_or_ground_pads
        }
        return _bulk_replace_pad_nets(text, replacements)
    raise ValueError("no signal-bearing active device with power or ground pads found")


_HIGH_SPEED_NET_TOKENS = (
    "DP",
    "DM",
    "D+",
    "D-",
    "USB",
    "PCIE",
    "PCI",
    "RX",
    "TX",
    "CSI",
    "DSI",
    "LVDS",
    "HDMI",
    "MIPI",
    "CLK",
)


def _looks_high_speed_net(net_name: str) -> bool:
    normalized = re.sub(r"[^A-Z0-9+\\-]+", "_", net_name.upper())
    return any(token in normalized for token in _HIGH_SPEED_NET_TOKENS)


def _mutate_missing_high_speed_routes(text: str, board: Any) -> str:
    candidate_nets = {
        track.net
        for track in board.tracks
        if track.net and _looks_high_speed_net(track.net)
    }
    if not candidate_nets:
        raise ValueError("no high-speed-like routed nets found")
    mutated = text
    removals = 0
    for net in sorted(candidate_nets):
        try:
            mutated = remove_routing_for_net(mutated, net)
            removals += 1
        except ValueError:
            continue
    if removals == 0:
        raise ValueError("no high-speed-like routes removed")
    return mutated


def stage_task_mutation_canaries(task: TaskSpec, out_dir: Path) -> dict[str, str]:
    mutation_dir = out_dir / "canaries" / "mutations"
    mutation_dir.mkdir(parents=True, exist_ok=True)
    mutators: list[tuple[str, Any]] = [
        ("missing_board_outline", _mutate_missing_board_outline),
        ("unrouted_external_nets", _mutate_unrouted_external_nets),
        ("isolated_connector_pads", _mutate_isolated_connector_pads),
        ("swapped_connector_pins", _mutate_swapped_connector_pins),
        ("power_or_signal_tied_to_ground", _mutate_power_ground_short),
        ("active_device_without_power_or_ground", _mutate_active_without_power_or_ground),
    ]
    if task.task_id in {"m2_pcie_adapter", "cm4_csi_adapter", "cm4_lvds_adapter", "cm5io_official"}:
        mutators.append(("missing_high_speed_routes", _mutate_missing_high_speed_routes))
    staged: dict[str, str] = {}
    for name, mutator in mutators:
        dst = _write_mutated_board(task, mutation_dir, name, mutator)
        if dst is not None:
            staged[name] = f"canaries/mutations/{name}"
    return staged


def stage_task_canaries(task: TaskSpec, out_dir: Path) -> Path:
    canary_dir = out_dir / "canaries"
    pass_dir = canary_dir / "pass"
    fail_dir = canary_dir / "fail"
    if canary_dir.exists():
        shutil.rmtree(canary_dir)
    _copytree(_reference_submission_dir(task, out_dir / "_pass_src"), pass_dir)
    shutil.rmtree(out_dir / "_pass_src")
    _copytree(_failing_submission_dir(task, out_dir / "_fail_src"), fail_dir)
    shutil.rmtree(out_dir / "_fail_src")
    stage_task_mutation_canaries(task, out_dir)
    return canary_dir


def stage_task_pack(task: TaskSpec, out_dir: Path) -> Path:
    pack_dir = out_dir / task.task_id
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True, exist_ok=True)

    _copy_task_assets(task, pack_dir)
    source_spec = _source_spec_for_task(task)
    _write_source_backed_grader(task, pack_dir)
    _copy_support_package(pack_dir, _SOURCE_BACKED_SUPPORT_FILES)
    _copytree(source_spec.source.vendored_root, pack_dir / "source_snapshot")
    _write_minimal_source_catalog(pack_dir, source_spec)
    _write_static_io_contract(task, pack_dir)
    _write_functional_io_contract(task, pack_dir)
    _write_source_backed_pack_tests(task, pack_dir)
    _write_pack_metadata(task, pack_dir)
    _write_pack_readme(task, pack_dir)
    _write_pack_pyproject(task, pack_dir)
    stage_task_canaries(task, pack_dir)
    return pack_dir


def stage_runtime_task_pack(task: TaskSpec, out_dir: Path) -> Path:
    pack_dir = out_dir / task.task_id
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True, exist_ok=True)
    _copy_runtime_task_assets(task, pack_dir)
    _write_runtime_pack_metadata(task, pack_dir)
    _write_runtime_pack_readme(task, pack_dir)
    return pack_dir


def verify_task_canaries(task: TaskSpec, pack_dir: Path) -> dict[str, Any]:
    pack_task = load_task_spec(pack_dir)
    canary_dir = pack_dir / "canaries"
    grading_root = pack_dir / "_grading"
    if grading_root.exists():
        shutil.rmtree(grading_root)
    image = env_value("EDA_BENCH_AGENT_IMAGE")
    pass_eval = pack_task.evaluate_project(canary_dir / "pass", grading_root / "pass", image=image)
    if pass_eval.raw.get("unsupported"):
        shutil.rmtree(grading_root)
        return {
            "supported": False,
            "verified": False,
            "unsupported_reason": str(pass_eval.raw.get("unsupported_reason", "")),
            "pass_score": None,
            "fail_score": None,
        }
    fail_eval = pack_task.evaluate_project(canary_dir / "fail", grading_root / "fail", image=image)
    pass_score = float(pass_eval.metrics["overall_score"])
    fail_score = float(fail_eval.metrics["overall_score"])
    if pass_score < 1.0:
        shutil.rmtree(grading_root)
        raise RuntimeError(f"{task.task_id} pass canary scored {pass_score:.3f}")
    if fail_score > FAIL_CANARY_MAX_SCORE:
        shutil.rmtree(grading_root)
        raise RuntimeError(
            f"{task.task_id} fail canary scored {fail_score:.3f}; "
            f"expected <= {FAIL_CANARY_MAX_SCORE:.3f}"
        )
    mutation_scores: dict[str, float] = {}
    mutation_dir = canary_dir / "mutations"
    if mutation_dir.exists():
        for mutation in sorted(path for path in mutation_dir.iterdir() if path.is_dir()):
            mutation_eval = pack_task.evaluate_project(mutation, grading_root / f"mutation_{mutation.name}", image=image)
            mutation_score = float(mutation_eval.metrics["overall_score"])
            mutation_scores[mutation.name] = mutation_score
            if mutation_score > MUTATION_CANARY_MAX_SCORE:
                shutil.rmtree(grading_root)
                raise RuntimeError(
                    f"{task.task_id} mutation canary {mutation.name} scored {mutation_score:.3f}; "
                    f"expected <= {MUTATION_CANARY_MAX_SCORE:.3f}"
                )
    shutil.rmtree(grading_root)
    return {
        "supported": True,
        "verified": True,
        "pass_score": pass_score,
        "fail_score": fail_score,
        "mutation_scores": mutation_scores,
    }


def verify_task_pack_pytest(pack_dir: Path) -> None:
    proc = subprocess.run(
        ["uv", "run", "pytest", "-q"],
        cwd=pack_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = "\n".join(
            part
            for part in (
                proc.stdout.strip(),
                proc.stderr.strip(),
            )
            if part
        )
        raise RuntimeError(
            f"task-pack pytest failed for {pack_dir} with exit code {proc.returncode}\n{detail}"
        )


@lru_cache(maxsize=8)
def _snapshot_prefix_root(
    *,
    repo_id: str,
    revision: str,
    path_prefix: str,
    token: str | None,
) -> Path:
    snapshot_kwargs = {
        "repo_id": repo_id,
        "repo_type": "dataset",
        "revision": revision,
        "token": token,
        "allow_patterns": [f"{path_prefix}/**"],
    }
    try:
        snapshot_root = Path(snapshot_download(**snapshot_kwargs, local_files_only=True))
        prefix_root = snapshot_root / path_prefix
        if prefix_root.exists():
            return prefix_root
    except Exception:
        pass
    snapshot_root = Path(snapshot_download(**snapshot_kwargs))
    prefix_root = snapshot_root / path_prefix
    if not prefix_root.exists():
        raise FileNotFoundError(
            f"downloaded snapshot is missing task-pack prefix {path_prefix}: {prefix_root}"
        )
    return prefix_root


def resolve_runtime_task_dir(task: TaskSpec, repo_root: Path) -> Path:
    manifest = load_task_pack_manifest()
    if task.task_id not in manifest.task_ids:
        raise KeyError(f"{task.task_id} is missing from {MANIFEST_PATH}")
    prefix_root = _snapshot_prefix_root(
        repo_id=manifest.repo_id,
        revision=manifest.revision,
        path_prefix=manifest.path_prefix,
        token=resolve_hf_token(repo_root),
    )
    pack_dir = prefix_root / task.task_id
    if not pack_dir.exists():
        raise FileNotFoundError(
            f"downloaded snapshot is missing task pack for {task.task_id}: {pack_dir}"
        )
    return pack_dir


def resolve_full_task_dir(task_id: str, repo_root: Path) -> Path:
    manifest = load_task_pack_manifest()
    if task_id not in manifest.task_ids:
        raise KeyError(f"{task_id} is missing from {MANIFEST_PATH}")
    prefix_root = _snapshot_prefix_root(
        repo_id=manifest.repo_id,
        revision=manifest.revision,
        path_prefix=manifest.full_path_prefix,
        token=resolve_hf_token(repo_root),
    )
    pack_dir = prefix_root / task_id
    if not pack_dir.exists():
        raise FileNotFoundError(
            f"downloaded snapshot is missing full task pack for {task_id}: {pack_dir}"
        )
    return pack_dir


def publish_task_packs(
    *,
    repo_root: Path,
    repo_id: str,
    path_prefix: str = DEFAULT_PATH_PREFIX,
    full_path_prefix: str = DEFAULT_FULL_PATH_PREFIX,
) -> Path:
    tasks = load_all_task_specs()
    token = resolve_hf_token(repo_root)
    api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
    for prefix in (path_prefix, full_path_prefix):
        try:
            api.delete_folder(
                path_in_repo=prefix,
                repo_id=repo_id,
                repo_type="dataset",
                token=token,
                commit_message=f"Clear stale EDA Bench task packs at {prefix}",
            )
        except Exception as exc:
            if "404" not in str(exc) and "Entry Not Found" not in str(exc):
                raise
    staging_root = Path(tempfile.mkdtemp(prefix="eda_task_packs_"))
    try:
        upload_root = staging_root / path_prefix
        full_upload_root = staging_root / full_path_prefix
        summaries: list[dict[str, Any]] = []
        for task in tasks.values():
            full_pack_dir = stage_task_pack(task, full_upload_root)
            summary: dict[str, Any] = {
                "task_id": task.task_id,
                "difficulty": task.difficulty,
                "enabled": task.enabled,
            }
            if task.enabled:
                summary.update(verify_task_canaries(task, full_pack_dir))
                stage_runtime_task_pack(task, upload_root)
            else:
                summary.update(
                    {
                        "pass_score": None,
                        "fail_score": None,
                        "verified": False,
                    }
                )
                stage_runtime_task_pack(task, upload_root)
            summaries.append(summary)
        (upload_root / "index.json").write_text(
            json.dumps(sorted(summaries, key=lambda item: item["task_id"]), indent=2) + "\n",
            encoding="utf-8",
        )
        api.upload_large_folder(
            repo_id=repo_id,
            repo_type="dataset",
            folder_path=staging_root,
            allow_patterns=[f"{full_path_prefix}/**"],
            ignore_patterns=["**/__pycache__/**", "**/*.pyc", "**/.pytest_cache/**", "**/_grading/**"],
        )
        api.upload_folder(
            repo_id=repo_id,
            repo_type="dataset",
            folder_path=str(upload_root),
            path_in_repo=path_prefix,
            token=token,
            commit_message=f"Update runtime EDA Bench task packs at {path_prefix}",
            ignore_patterns=["**/__pycache__/**", "**/*.pyc", "**/.pytest_cache/**"],
        )
        repo_info = api.repo_info(repo_id=repo_id, repo_type="dataset", token=token)
        revision = str(getattr(repo_info, "sha", "")).strip()
        if not revision:
            raise RuntimeError(f"failed to resolve dataset revision for {repo_id}")
        manifest_path = write_task_pack_manifest(
            repo_id=repo_id,
            path_prefix=path_prefix,
            full_path_prefix=full_path_prefix,
            revision=revision,
            task_ids=list(tasks),
        )
        for metadata_file in ("LICENSES.md",):
            api.upload_file(
                repo_id=repo_id,
                repo_type="dataset",
                path_or_fileobj=str(repo_root / metadata_file),
                path_in_repo=metadata_file,
                token=token,
                commit_message=f"Update EDA Bench {metadata_file}",
            )
        return manifest_path
    finally:
        shutil.rmtree(staging_root)


def publish_task_packs_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish standalone EDA Bench task packs to Hugging Face.")
    parser.add_argument("--repo-id", default="", help="HF dataset repo id. Defaults to HF_PROVENANCE_REPO_ID.")
    parser.add_argument("--path-prefix", default=DEFAULT_PATH_PREFIX, help="Path prefix inside the dataset repo.")
    parser.add_argument("--full-path-prefix", default=DEFAULT_FULL_PATH_PREFIX, help="Path prefix for full grader task packs inside the dataset repo.")
    args = parser.parse_args(argv)
    repo_root = Path.cwd()
    repo_id = args.repo_id.strip() or _task_pack_repo_id(repo_root)
    manifest_path = publish_task_packs(
        repo_root=repo_root,
        repo_id=repo_id,
        path_prefix=args.path_prefix,
        full_path_prefix=args.full_path_prefix,
    )
    print(manifest_path)
    return 0


def verify_task_canaries_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and verify local standalone task-pack canaries.")
    parser.add_argument("--task-id", action="append", default=[], help="Optional task id filter.")
    parser.add_argument("--run-pack-pytest", action="store_true", help="Also run the staged pack-local pytest suite.")
    args = parser.parse_args(argv)

    selected = set(args.task_id)
    staging_root = Path(tempfile.mkdtemp(prefix="eda_task_pack_verify_"))
    try:
        for task in load_all_task_specs(include_disabled=True).values():
            if selected and task.task_id not in selected:
                continue
            if not task.enabled:
                print(f"{task.task_id}\tskipped=disabled")
                continue
            pack_dir = stage_task_pack(task, staging_root)
            result = verify_task_canaries(task, pack_dir)
            if args.run_pack_pytest:
                verify_task_pack_pytest(pack_dir)
            if not result.get("supported", True):
                print(f"{task.task_id}\tunsupported={result['unsupported_reason']}")
            else:
                print(
                    f"{task.task_id}\tpass={result['pass_score']:.3f}\tfail={result['fail_score']:.3f}"
                    f"\tmutations={len(result.get('mutation_scores', {}))}"
                )
        return 0
    finally:
        shutil.rmtree(staging_root)
