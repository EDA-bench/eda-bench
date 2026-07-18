from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceBackedSource:
    repo_url: str
    commit: str
    license: str


@dataclass(frozen=True)
class SourceBackedTaskSpec:
    task_id: str
    project_stem: str
    source: SourceBackedSource
    reference_board: Path


def load_source_backed_task(task_dir: Path) -> SourceBackedTaskSpec:
    config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
    metadata = config["metadata"]
    task_id = str(config["task"]["name"]).rsplit("/", 1)[-1]
    boards = tuple((task_dir / "solution/reference").glob("*.kicad_pcb"))
    if len(boards) != 1:
        raise ValueError(f"{task_id} must contain exactly one reference PCB, found {len(boards)}")
    return SourceBackedTaskSpec(
        task_id=task_id,
        project_stem=str(metadata["project_stem"]),
        source=SourceBackedSource(
            repo_url=str(metadata["source_repo_url"]),
            commit=str(metadata["source_commit"]),
            license=str(metadata["source_license"]),
        ),
        reference_board=boards[0].absolute(),
    )
