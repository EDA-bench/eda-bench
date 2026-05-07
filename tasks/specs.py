from __future__ import annotations

import importlib.util
import os
import sys
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TASKS_ROOT = Path(__file__).resolve().parent
DIFFICULTY_LEVELS = {
    "very easy": 1,
    "easy": 2,
    "medium": 3,
    "hard": 4,
    "very hard": 5,
    "extreme": 6,
}


@dataclass(frozen=True)
class TaskEvaluation:
    raw: dict[str, Any]
    metrics: dict[str, Any]


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    title: str
    difficulty: str
    enabled: bool
    prompt: str
    task_dir: Path
    grader_module_path: Path
    gold_dir: Path | None = None

    def evaluate_project(
        self,
        project_dir: Path,
        work_dir: Path,
        *,
        image: str,
    ) -> TaskEvaluation:
        module = load_task_module(self.grader_module_path)
        grader = getattr(module, "grade", None)
        if not callable(grader):
            raise AttributeError(f"task module {self.grader_module_path} must define `grade`")
        return grader(self, project_dir, work_dir, image=image)

    def gold_samples(self) -> dict[str, Path]:
        if self.gold_dir is None or not self.gold_dir.exists():
            return {}
        return {
            path.name: path
            for path in sorted(self.gold_dir.iterdir())
            if path.is_dir()
        }


def load_task_module(path: Path) -> Any:
    module_name = "_eda_bench_task_" + path.parent.name
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load task module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    with _task_pack_root_env(path.parent):
        spec.loader.exec_module(module)
    return module


def load_task_spec(task_dir: Path) -> TaskSpec:
    config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
    prompt = (task_dir / str(config["prompt_file"])).read_text(encoding="utf-8").strip()
    gold_dir_value = str(config.get("gold_dir", "")).strip()
    return TaskSpec(
        task_id=str(config["task_id"]),
        title=str(config["title"]),
        difficulty=str(config["difficulty"]),
        enabled=bool(config.get("enabled", True)),
        prompt=prompt,
        task_dir=task_dir.absolute(),
        grader_module_path=(task_dir / str(config["grader"])).absolute(),
        gold_dir=(task_dir / gold_dir_value).absolute() if gold_dir_value else None,
    )


def _load_local_task_specs(*, include_disabled: bool = False) -> dict[str, TaskSpec]:
    specs: dict[str, TaskSpec] = {}
    for task_toml in sorted(TASKS_ROOT.glob("*/task.toml")):
        spec = load_task_spec(task_toml.parent)
        if not include_disabled and not spec.enabled:
            continue
        specs[spec.task_id] = spec
    return specs


def _load_hf_task_specs(*, include_disabled: bool = False) -> dict[str, TaskSpec]:
    from tasks.task_packs import load_task_pack_manifest, resolve_full_task_dir

    specs: dict[str, TaskSpec] = {}
    manifest = load_task_pack_manifest()
    repo_root = TASKS_ROOT.parent
    for task_id in manifest.task_ids:
        task_dir = resolve_full_task_dir(task_id, repo_root)
        spec = load_task_spec(task_dir)
        if not include_disabled and not spec.enabled:
            continue
        specs[spec.task_id] = spec
    return specs


def load_all_task_specs(*, include_disabled: bool = False) -> dict[str, TaskSpec]:
    local_specs = _load_local_task_specs(include_disabled=include_disabled)
    if local_specs:
        return local_specs
    return _load_hf_task_specs(include_disabled=include_disabled)


def load_task_ids(*, include_disabled: bool = False) -> tuple[str, ...]:
    local_specs = _load_local_task_specs(include_disabled=include_disabled)
    if local_specs:
        return tuple(local_specs)
    from tasks.task_packs import load_task_pack_manifest

    return load_task_pack_manifest().task_ids
@contextmanager
def _task_pack_root_env(task_dir: Path):
    previous = os.environ.get("EDA_BENCH_TASK_PACK_ROOT")
    os.environ["EDA_BENCH_TASK_PACK_ROOT"] = str(task_dir)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("EDA_BENCH_TASK_PACK_ROOT", None)
        else:
            os.environ["EDA_BENCH_TASK_PACK_ROOT"] = previous
