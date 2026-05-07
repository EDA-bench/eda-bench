from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.accounting import (
    path_size_stats,
    row_accounting,
    summarize_report_accounting,
)
from bench.config import (
    env_flag,
    env_positive_float,
    required_env_value,
    summarize_overall_score,
)
from bench.provenance import (
    HFProvenanceStore,
    load_hf_provenance_config,
    resolve_hf_token,
    write_docker_bundle,
    write_provenance_bundle,
)
from harnesses import utils as harness_utils
from tasks import specs as task_specs
from tasks.task_packs import resolve_runtime_task_dir

CONTAINER_WORKDIR = harness_utils.CONTAINER_WORKDIR
CONTAINER_TASK_DIR = harness_utils.CONTAINER_TASK_DIR
CONTAINER_FINAL_PROJECT_DIR = harness_utils.CONTAINER_FINAL_PROJECT_DIR
HF_HARNESS_PATH_PREFIX = "evals/harnesses"
TASK_BUNDLE_PRUNE_DIR_NAMES = {
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "env",
    "node_modules",
    "venv",
}
TASK_BUNDLE_PRUNE_FILE_SUFFIXES = {".pyc", ".pyo"}


@dataclass(frozen=True)
class BindMount:
    source: Path
    target: str
    read_only: bool = False


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_json_serializable(payload), indent=2) + "\n",
        encoding="utf-8",
    )


def _json_serializable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_serializable(item) for item in value]
    if isinstance(value, set):
        return [_json_serializable(item) for item in sorted(value, key=repr)]
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def default_container_image() -> str:
    return required_env_value("EDA_BENCH_AGENT_IMAGE")


def ensure_docker_image_available(image: str) -> None:
    proc = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "docker image inspect failed"
        raise RuntimeError(f"Docker image '{image}' is not available: {detail}")


def docker_run_command(
    *,
    image: str,
    entrypoint: str,
    mounts: list[BindMount],
    env: dict[str, str],
    args: list[str],
    workdir: str = CONTAINER_WORKDIR,
    remove: bool = True,
    container_name: str = "",
    network: str = "bridge",
) -> list[str]:
    cmd = ["docker", "run"]
    if remove:
        cmd.append("--rm")
    if container_name:
        cmd.extend(["--name", container_name])
    cmd.extend(
        [
            "--init",
            "--network",
            network,
            "--workdir",
            workdir,
            "--entrypoint",
            entrypoint,
        ]
    )
    for key, value in env.items():
        cmd.extend(["-e", f"{key}={value}"])
    for mount in mounts:
        spec = f"type=bind,src={mount.source},dst={mount.target}"
        if mount.read_only:
            spec += ",readonly"
        cmd.extend(["--mount", spec])
    cmd.append(image)
    cmd.extend(args)
    return cmd


def _completed_process_payload(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    args = proc.args
    if isinstance(args, (list, tuple)):
        command = harness_utils.sanitize_command_for_logging([str(item) for item in args])
    else:
        command = [str(args)]
    return {
        "args": command,
        "returncode": int(proc.returncode),
        "stdout": proc.stdout if isinstance(proc.stdout, str) else "",
        "stderr": proc.stderr if isinstance(proc.stderr, str) else "",
    }


def _container_export_status_path(container_export_path: Path) -> Path:
    return container_export_path.with_suffix(container_export_path.suffix + ".status.json")


def _harness_timeout_seconds(root: Path | None = None) -> float | None:
    return env_positive_float("EDA_BENCH_HARNESS_TIMEOUT_SECONDS", root=root)


def _run_docker_subprocess(
    cmd: list[str],
    *,
    timeout_seconds: float | None,
    container_name: str,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="ignore")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="ignore")
        cleanup_detail = ""
        if container_name:
            cleanup_proc = subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False,
            )
            cleanup_detail = cleanup_proc.stderr.strip() or cleanup_proc.stdout.strip()
        detail = f"docker run timed out after {timeout_seconds:g} seconds"
        if cleanup_detail:
            detail = f"{detail}; cleanup: {cleanup_detail}"
        stderr = f"{stderr.rstrip()}\n{detail}\n".lstrip()
        return subprocess.CompletedProcess(cmd, 124, stdout, stderr)


def run_docker_command(
    *,
    image: str,
    entrypoint: str,
    mounts: list[BindMount],
    env: dict[str, str],
    args: list[str],
    workdir: str = CONTAINER_WORKDIR,
    container_export_path: Path | None = None,
    container_name: str = "",
    network: str = "bridge",
) -> subprocess.CompletedProcess[str]:
    remove = container_export_path is None
    cmd = docker_run_command(
        image=image,
        entrypoint=entrypoint,
        mounts=mounts,
        env=env,
        args=args,
        workdir=workdir,
        remove=remove,
        container_name=container_name,
        network=network,
    )
    proc = _run_docker_subprocess(
        cmd,
        timeout_seconds=_harness_timeout_seconds(Path.cwd()),
        container_name=container_name,
    )
    if container_export_path is None:
        return proc
    if not container_name:
        raise ValueError("container_name is required when saving the post-run container image")
    container_export_path.parent.mkdir(parents=True, exist_ok=True)
    status = {
        "container_name": container_name,
        "container_export_path": str(container_export_path),
        "run": _completed_process_payload(proc),
        "container_found_after_run": False,
        "committed_image": False,
        "saved_image": False,
        "removed_image": False,
        "removed_container": False,
        "exported": False,
        "export_size_bytes": 0,
        "export_error": None,
        "cleanup_error": None,
        "steps": [],
    }

    def record_step(stage: str, step_proc: subprocess.CompletedProcess[str]) -> subprocess.CompletedProcess[str]:
        status["steps"].append({"stage": stage, **_completed_process_payload(step_proc)})
        return step_proc

    after_image = f"eda-bench-after:{container_name.lower()}"
    try:
        inspect_proc = record_step(
            "inspect_container",
            subprocess.run(
                ["docker", "container", "inspect", container_name],
                capture_output=True,
                text=True,
                check=False,
            ),
        )
        status["container_found_after_run"] = inspect_proc.returncode == 0
        if inspect_proc.returncode != 0:
            detail = inspect_proc.stderr.strip() or inspect_proc.stdout.strip()
            status["export_error"] = detail or "post-run container not found"
            return proc
        commit_proc = record_step(
            "commit_image",
            subprocess.run(
                ["docker", "commit", container_name, after_image],
                capture_output=True,
                text=True,
                check=False,
            ),
        )
        status["committed_image"] = commit_proc.returncode == 0
        if commit_proc.returncode != 0:
            detail = commit_proc.stderr.strip() or commit_proc.stdout.strip()
            status["export_error"] = detail or "docker commit failed"
            return proc
        save_proc = record_step(
            "save_image",
            subprocess.run(
                ["docker", "save", "--output", str(container_export_path), after_image],
                capture_output=True,
                text=True,
                check=False,
            ),
        )
        status["saved_image"] = save_proc.returncode == 0
        if save_proc.returncode != 0:
            detail = save_proc.stderr.strip() or save_proc.stdout.strip()
            status["export_error"] = detail or "docker save failed"
        image_rm_proc = record_step(
            "remove_image",
            subprocess.run(
                ["docker", "image", "rm", after_image],
                capture_output=True,
                text=True,
                check=False,
            ),
        )
        status["removed_image"] = image_rm_proc.returncode == 0
        if image_rm_proc.returncode != 0 and status["cleanup_error"] is None:
            detail = image_rm_proc.stderr.strip() or image_rm_proc.stdout.strip()
            status["cleanup_error"] = detail or "docker image rm failed"
        return proc
    finally:
        remove_proc = record_step(
            "remove_container",
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False,
            ),
        )
        status["removed_container"] = remove_proc.returncode == 0
        if remove_proc.returncode != 0 and status["cleanup_error"] is None:
            detail = remove_proc.stderr.strip() or remove_proc.stdout.strip()
            status["cleanup_error"] = detail or "docker rm failed"
        if container_export_path.exists():
            status["exported"] = True
            status["export_size_bytes"] = container_export_path.stat().st_size
        _write_json(_container_export_status_path(container_export_path), status)


def build_harness_prompt(spec: harness_utils.HarnessSpec, task_prompt: str) -> tuple[str | None, str]:
    module = harness_utils.harness_module(spec)
    builder = getattr(module, "build_prompt", None)
    if not callable(builder):
        raise AttributeError(f"harness module {spec.file_path} must define callable `build_prompt`")
    return builder(spec, task_prompt)


def run_harness(
    spec: harness_utils.HarnessSpec,
    *,
    system_prompt: str | None,
    prompt: str,
    workdir: Path,
    submission_dir: Path,
    task_dir: Path,
    image: str,
    container_export_path: Path | None = None,
    container_name: str = "",
) -> harness_utils.AgentRunResult:
    module = harness_utils.harness_module(spec)
    runner = getattr(module, "run", None)
    if not callable(runner):
        raise AttributeError(f"harness module {spec.file_path} must define callable `run`")
    return runner(
        runtime=sys.modules[__name__],
        spec=spec,
        system_prompt=system_prompt,
        prompt=prompt,
        workdir=workdir,
        submission_dir=submission_dir,
        task_dir=task_dir,
        image=image,
        container_export_path=container_export_path,
        container_name=container_name,
    )


def _container_provenance_error(
    status: dict[str, Any] | None, container_after_url: str | None
) -> str:
    if not isinstance(status, dict):
        return "missing post-run container provenance status"
    if str(status.get("export_error") or "").strip():
        return f"post-run container export failed: {status['export_error']}"
    if str(status.get("cleanup_error") or "").strip():
        return f"post-run container cleanup failed: {status['cleanup_error']}"
    required_flags = (
        "container_found_after_run",
        "committed_image",
        "saved_image",
        "removed_container",
        "exported",
    )
    missing = [name for name in required_flags if status.get(name) is not True]
    if missing:
        return "incomplete post-run container provenance: " + ", ".join(missing)
    if not str(container_after_url or "").strip():
        return "missing uploaded post-run container image"
    return ""


def summarize_harness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_difficulty: dict[str, list[float]] = {}
    task_scores: list[float] = []
    for row in rows:
        task_scores.append(float(row["metrics"]["overall_score"]))
        difficulty = str(row.get("difficulty") or "").strip().lower()
        if not difficulty:
            continue
        by_difficulty.setdefault(difficulty, []).append(
            float(row["metrics"]["overall_score"])
        )
    difficulty_summary = {
        difficulty: summarize_overall_score(
            [{"metrics": {"overall_score": score}} for score in scores]
        )
        for difficulty, scores in sorted(
            by_difficulty.items(),
            key=lambda item: task_specs.DIFFICULTY_LEVELS.get(item[0], 999),
        )
    }
    difficulty_counts = {
        difficulty: len(scores)
        for difficulty, scores in sorted(
            by_difficulty.items(),
            key=lambda item: task_specs.DIFFICULTY_LEVELS.get(item[0], 999),
        )
    }
    return {
        "benchmark_score": summarize_overall_score(rows),
        "unweighted_score": (
            sum(task_scores) / len(task_scores) if task_scores else 0.0
        ),
        "task_count": len(rows),
        "by_difficulty": difficulty_summary,
        "task_count_by_difficulty": difficulty_counts,
    }


def _safe_rmtree(path: Path) -> None:
    if not path.exists():
        return
    detail_parts: list[str] = []
    try:
        shutil.rmtree(path)
        return
    except OSError as exc:
        image = default_container_image()
        cleanup_proc = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--mount",
                f"type=bind,src={path.parent.resolve()},dst=/cleanup",
                "--entrypoint",
                "rm",
                image,
                "-rf",
                f"/cleanup/{path.name}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if cleanup_proc.returncode == 0 and not path.exists():
            return
        detail = cleanup_proc.stderr.strip() or cleanup_proc.stdout.strip()
        detail_parts.append(detail or str(exc))
    if path.exists():
        sudo_proc = subprocess.run(
            ["sudo", "-n", "rm", "-rf", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if sudo_proc.returncode == 0 and not path.exists():
            return
        detail = sudo_proc.stderr.strip() or sudo_proc.stdout.strip()
        if detail:
            detail_parts.append(detail)
    detail = " | ".join(detail_parts) or "unknown cleanup failure"
    print(f"warning: failed to remove {path}: {detail}", file=sys.stderr)


def _prune_task_bundle(task_root: Path) -> None:
    if not task_root.exists():
        return
    prune_dirs = [
        path
        for path in task_root.rglob("*")
        if path.is_dir() and path.name in TASK_BUNDLE_PRUNE_DIR_NAMES
    ]
    for path in sorted(prune_dirs, key=lambda item: len(item.parts), reverse=True):
        _safe_rmtree(path)
    for path in task_root.rglob("*"):
        if path.is_file() and path.suffix in TASK_BUNDLE_PRUNE_FILE_SUFFIXES:
            path.unlink(missing_ok=True)


def _upload_model_transcripts(root: Path | None = None) -> bool:
    return env_flag("EDA_BENCH_UPLOAD_MODEL_TRANSCRIPTS", default=True, root=root)


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8", errors="ignore"))


def _write_model_artifacts(
    *,
    stdout_file: Path,
    stderr_file: Path,
    response_file: Path,
    events_file: Path,
    parsed_events_file: Path,
    run_result: harness_utils.AgentRunResult,
    upload_transcripts: bool,
) -> dict[str, Any]:
    response_file.write_text(run_result.response, encoding="utf-8", errors="ignore")
    if upload_transcripts:
        stdout_file.write_text(run_result.stdout, encoding="utf-8", errors="ignore")
        stderr_file.write_text(run_result.stderr, encoding="utf-8", errors="ignore")
        events_file.write_text(run_result.stdout, encoding="utf-8", errors="ignore")
        _write_json(parsed_events_file, run_result.parsed_events)
        return {
            "enabled": True,
            "stdout_bytes": _byte_len(run_result.stdout),
            "stderr_bytes": _byte_len(run_result.stderr),
            "parsed_event_count": len(run_result.parsed_events),
        }

    summary = {
        "enabled": False,
        "reason": "EDA_BENCH_UPLOAD_MODEL_TRANSCRIPTS=0",
        "stdout_bytes_omitted": _byte_len(run_result.stdout),
        "stderr_bytes_omitted": _byte_len(run_result.stderr),
        "parsed_event_count_omitted": len(run_result.parsed_events),
    }
    stdout_file.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    stderr_file.write_text("", encoding="utf-8")
    events_file.write_text(json.dumps(summary) + "\n", encoding="utf-8")
    _write_json(parsed_events_file, summary)
    return summary


def _materialize_runtime_task_dir(source: Path, target: Path) -> Path:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, symlinks=False)
    return target


def _select_tasks(
    task_defs: dict[str, task_specs.TaskSpec],
    requested_task_ids: list[str],
) -> list[task_specs.TaskSpec]:
    if requested_task_ids:
        missing = [task_id for task_id in requested_task_ids if task_id not in task_defs]
        if missing:
            raise RuntimeError("unknown task id(s): " + ", ".join(missing))
        return [task_defs[task_id] for task_id in requested_task_ids]
    return [task_defs[task_id] for task_id in task_specs.load_task_ids()]


def eval_harness_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate one harness spec against the EDA benchmark."
    )
    parser.add_argument("--harness", required=True, help="Path to a harness Python module")
    parser.add_argument(
        "--task-id",
        action="append",
        default=[],
        help="Evaluate only this task id. May be passed more than once.",
    )
    args = parser.parse_args(argv)

    image = default_container_image()
    ensure_docker_image_available(image)
    upload_container_images = env_flag(
        "EDA_BENCH_UPLOAD_CONTAINER_IMAGES",
        default=True,
        root=Path.cwd(),
    )
    upload_model_transcripts = _upload_model_transcripts(Path.cwd())
    upload_task_bundles_incrementally = env_flag(
        "EDA_BENCH_UPLOAD_TASK_BUNDLES_INCREMENTALLY",
        default=True,
        root=Path.cwd(),
    )
    upload_partial_reports = env_flag(
        "EDA_BENCH_UPLOAD_PARTIAL_REPORTS",
        default=True,
        root=Path.cwd(),
    )
    harness_timeout_seconds = _harness_timeout_seconds(Path.cwd())
    spec = harness_utils.load_harness_spec(args.harness)
    if spec.provider == "codex":
        from harnesses.codex.utils import has_codex_auth_token

        if not has_codex_auth_token():
            raise RuntimeError("CODEX_AUTH_JSON_B64 is required in .env")

    repo_root = Path.cwd()
    provenance_config = load_hf_provenance_config(repo_root)
    task_defs = task_specs.load_all_task_specs()
    tasks = _select_tasks(task_defs, args.task_id)
    git_head_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    git_head = git_head_proc.stdout.strip() if git_head_proc.returncode == 0 else ""

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", spec.harness_id.replace("/", "__")).strip("_")
    run_name = f"{run_slug}_{stamp}_{os.getpid()}"
    run_prefix = f"{HF_HARNESS_PATH_PREFIX}/{run_name}"
    storage = HFProvenanceStore(
        repo_id=provenance_config.repo_id,
        path_prefix=run_prefix,
        token=resolve_hf_token(repo_root),
    )

    out_root = Path(tempfile.mkdtemp(prefix="eda_bench_run_"))
    try:
        metadata_dir = out_root / "metadata"
        metadata_files = write_provenance_bundle(metadata_dir, repo_root)
        metadata_files.update(
            write_docker_bundle(
                metadata_dir / "docker",
                repo_root,
                image,
                include_image=upload_container_images,
            )
        )
        harness_copy = metadata_dir / "harness.py"
        harness_copy.write_text(
            Path(spec.file_path).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        metadata_files["harness"] = "harness.py"
        metadata_stats = path_size_stats(metadata_dir)
        metadata_dir_url = storage.upload_directory(
            metadata_dir, "metadata", "Upload harness eval metadata"
        )
        _safe_rmtree(metadata_dir)

        report: dict[str, Any] = {
            "timestamp_utc": stamp,
            "agent_image": image,
            "harness": {
                "id": spec.harness_id,
                "provider": spec.provider,
                "strategy": spec.strategy,
                "model": spec.model,
                "reasoning_effort": spec.reasoning_effort,
                "access": spec.access,
                "file_path": spec.file_path,
                "symbol_name": spec.symbol_name,
            },
            "tasks": [task.task_id for task in tasks],
            "git_head": git_head,
            "storage": {
                "backend": "huggingface_dataset",
                "repo_id": provenance_config.repo_id,
                "run_prefix": run_prefix,
                "run_url": storage.tree_url(""),
                "metadata_dir": metadata_dir_url,
                "metadata_files": metadata_files,
                "report_file": storage.file_url("report.json"),
                "container_images_enabled": upload_container_images,
                "model_transcripts_enabled": upload_model_transcripts,
                "task_bundles_incremental": upload_task_bundles_incrementally,
                "partial_reports_enabled": upload_partial_reports,
                "harness_timeout_seconds": harness_timeout_seconds,
            },
            "accounting": {
                "provenance": {
                    "metadata_bytes": metadata_stats["bytes"],
                    "metadata_file_count": metadata_stats["file_count"],
                }
            },
        }

        rows: list[dict[str, Any]] = []
        prompt_manifest: list[dict[str, str]] = []
        report_path = out_root / "report.json"
        for idx, task in enumerate(tasks, start=1):
            task_root = out_root / "tasks" / task.task_id
            workdir = task_root / "workspace"
            submission_dir = task_root / "submission" / "final_project"
            grading_dir = task_root / "grading"
            container_export_path = (
                task_root / "container_after.tar" if upload_container_images else None
            )
            container_name = (
                re.sub(
                    r"[^a-zA-Z0-9_.-]+", "-", f"eda-bench-{run_name}-{idx}"
                ).strip("-")[:120]
                if upload_container_images or harness_timeout_seconds is not None
                else ""
            )
            task_root.mkdir(parents=True, exist_ok=True)
            workdir.mkdir(parents=True, exist_ok=True)
            submission_dir.mkdir(parents=True, exist_ok=True)
            grading_dir.mkdir(parents=True, exist_ok=True)
            runtime_task_dir = _materialize_runtime_task_dir(
                resolve_runtime_task_dir(task, repo_root),
                task_root / "runtime_task",
            )

            system_prompt, prompt = build_harness_prompt(spec, task.prompt)
            start = time.time()
            run_result = run_harness(
                spec,
                system_prompt=system_prompt,
                prompt=prompt,
                workdir=workdir,
                submission_dir=submission_dir,
                task_dir=runtime_task_dir,
                image=image,
                container_export_path=container_export_path,
                container_name=container_name,
            )
            elapsed = time.time() - start

            grader_error = None
            try:
                evaluation = task.evaluate_project(submission_dir, grading_dir, image=image)
            except Exception as exc:
                grader_error = f"{type(exc).__name__}: {exc}"
                evaluation = task_specs.TaskEvaluation(
                    raw={
                        "project_dir": str(submission_dir),
                        "error_message": grader_error,
                    },
                    metrics={
                        "submission_exists": 0.0,
                        "build_success": 0.0,
                        "task_score": 0.0,
                        "overall_score": 0.0,
                        "reward": 0.0,
                        "error_message": grader_error,
                    },
                )

            prompt_file = task_root / "prompt.txt"
            system_prompt_file = task_root / "system_prompt.txt"
            stdout_file = task_root / "stdout.txt"
            stderr_file = task_root / "stderr.txt"
            response_file = task_root / "response.txt"
            events_file = task_root / "events.jsonl"
            parsed_events_file = task_root / "events.parsed.json"
            command_file = task_root / "command.json"
            session_file = task_root / "session.json"
            usage_file = task_root / "usage.json"
            grading_raw_file = grading_dir / "raw_metrics.json"
            grading_metrics_file = grading_dir / "normalized_metrics.json"
            prompt_file.write_text(prompt, encoding="utf-8")
            system_prompt_file.write_text(system_prompt or "", encoding="utf-8")
            prompt_manifest.append(
                {
                    "task_id": task.task_id,
                    "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    "system_prompt_sha256": hashlib.sha256((system_prompt or "").encode("utf-8")).hexdigest(),
                }
            )
            model_artifact_summary = _write_model_artifacts(
                stdout_file=stdout_file,
                stderr_file=stderr_file,
                response_file=response_file,
                events_file=events_file,
                parsed_events_file=parsed_events_file,
                run_result=run_result,
                upload_transcripts=upload_model_transcripts,
            )
            _write_json(command_file, run_result.command)
            _write_json(session_file, {"session_id": run_result.session_id})
            _write_json(usage_file, run_result.usage)
            _write_json(grading_raw_file, evaluation.raw)
            _write_json(grading_metrics_file, evaluation.metrics)
            _prune_task_bundle(task_root)
            task_bundle_stats = path_size_stats(task_root)
            container_export_stats = (
                path_size_stats(container_export_path)
                if container_export_path is not None
                else {"bytes": 0, "file_count": 0}
            )

            container_export_status: dict[str, Any] | None = None
            if container_export_path is not None:
                container_export_status_path = _container_export_status_path(container_export_path)
                if container_export_status_path.exists():
                    loaded_status = json.loads(
                        container_export_status_path.read_text(encoding="utf-8")
                    )
                    if isinstance(loaded_status, dict):
                        container_export_status = loaded_status
            remote_task_prefix = f"tasks/{task.task_id}"
            task_bundle_url = storage.tree_url(remote_task_prefix)
            container_after_url = None
            if container_export_path is not None and container_export_path.exists():
                container_after_url = storage.upload_file(
                    container_export_path,
                    f"{remote_task_prefix}/container_image_after.tar",
                    f"Upload post-run container image for {spec.harness_id} {task.task_id}",
                )
                container_export_path.unlink()
            provenance_error = (
                _container_provenance_error(container_export_status, container_after_url)
                if upload_container_images
                else ""
            )
            row = {
                "task_id": task.task_id,
                "difficulty": task.difficulty,
                "index": idx,
                "elapsed_s": elapsed,
                "metrics": evaluation.metrics,
                "error": run_result.error,
                "grader_error": grader_error,
                "provenance_error": provenance_error or None,
                "returncode": run_result.returncode,
                "session_id": run_result.session_id,
                "usage": run_result.usage,
                "artifacts": {
                    "container_image_after": container_after_url,
                    "task_bundle": task_bundle_url,
                    "model_transcripts": model_artifact_summary,
                },
            }
            row["accounting"] = row_accounting(spec.provider, spec.model, row)
            row["accounting"]["provenance"].update(
                {
                    "task_bundle_bytes": task_bundle_stats["bytes"],
                    "task_bundle_file_count": task_bundle_stats["file_count"],
                    "container_image_after_bytes": container_export_stats["bytes"],
                }
            )
            rows.append(row)
            report["benchmark_task_count"] = len(tasks)
            report["prompt_manifest"] = sorted(prompt_manifest, key=lambda item: item["task_id"])
            report["summary"] = summarize_harness(rows)
            report["rows"] = rows
            report["accounting"].update(summarize_report_accounting(report))
            _write_json(report_path, report)
            if upload_task_bundles_incrementally:
                task_bundle_url = storage.upload_directory(
                    task_root,
                    remote_task_prefix,
                    f"Upload task provenance for {spec.harness_id} {task.task_id}",
                )
                row["artifacts"]["task_bundle"] = task_bundle_url
                _write_json(report_path, report)
                _safe_rmtree(task_root)
            if upload_partial_reports:
                storage.upload_file(
                    report_path,
                    "report.partial.json",
                    "Update partial harness eval report",
                )
            print(
                f"[{spec.harness_id}] {idx}/{len(tasks)} {task.task_id}: "
                f"overall={evaluation.metrics['overall_score']:.3f} "
                f"build={evaluation.metrics['build_success']:.1f}",
                flush=True,
            )

        if not upload_task_bundles_incrementally:
            storage.upload_directory(
                out_root / "tasks",
                "tasks",
                f"Upload batched task provenance for {spec.harness_id}",
            )
        storage.upload_file(report_path, "report.json", "Finalize harness eval report")
        print(f"Saved provenance to HF: {storage.tree_url('')}")
        return 0
    finally:
        _safe_rmtree(out_root)


def eval_matrix_main(argv: list[str] | None = None) -> int:
    del argv
    for provider, model, access, level in harness_utils.builtin_harness_matrix():
        ref = harness_utils.builtin_harness_ref(provider, model, access, level)
        exit_code = eval_harness_main(["--harness", ref])
        if exit_code != 0:
            return exit_code
    return 0


def list_harnesses_main(argv: list[str] | None = None) -> int:
    del argv
    for provider, model, access, level in harness_utils.builtin_harness_matrix():
        print(harness_utils.builtin_harness_ref(provider, model, access, level))
    return 0


def list_tasks_main(argv: list[str] | None = None) -> int:
    del argv
    for task_id in task_specs.load_task_ids():
        print(task_id)
    return 0
