from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TaskEvaluation:
    raw: dict[str, Any]
    metrics: dict[str, Any]


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    title: str
    difficulty: str
    prompt: str
    task_dir: Path
    gold_dir: Path

    def evaluate_project(
        self,
        project_dir: Path,
        work_dir: Path,
    ) -> TaskEvaluation:
        from tasks.source_backed_task import grade_source_backed_task
        from tasks.source_backed_tasks import load_source_backed_task

        return grade_source_backed_task(
            self,
            project_dir,
            work_dir,
            spec=load_source_backed_task(self.task_dir),
        )


def load_task_spec(task_dir: Path) -> TaskSpec:
    task_dir = task_dir.absolute()
    config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
    metadata = config["metadata"]
    task = config["task"]
    return TaskSpec(
        task_id=str(task["name"]).rsplit("/", 1)[-1],
        title=str(task["description"]),
        difficulty=str(metadata["difficulty"]),
        prompt=(task_dir / "instruction.md").read_text(encoding="utf-8").strip(),
        task_dir=task_dir,
        gold_dir=task_dir / "solution",
    )
