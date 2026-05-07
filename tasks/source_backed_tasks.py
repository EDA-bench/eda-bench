from __future__ import annotations

import tomllib
import os
from dataclasses import dataclass
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parent / "source_backed_tasks.toml"


def _default_catalog_path() -> Path:
    task_pack_root = os.environ.get("EDA_BENCH_TASK_PACK_ROOT", "").strip()
    if task_pack_root:
        candidate = Path(task_pack_root) / "tasks" / "source_backed_tasks.toml"
        if candidate.exists():
            return candidate
    return CATALOG_PATH


@dataclass(frozen=True)
class SourceBackedSource:
    key: str
    name: str
    owner: str
    repo_url: str
    commit: str
    license: str
    design_format: str
    vendored_root: Path
    readme_path: Path
    license_path: Path | None
    notes: str


@dataclass(frozen=True)
class SourceBackedTaskSpec:
    task_id: str
    title: str
    difficulty: str
    enabled: bool
    project_stem: str
    source: SourceBackedSource
    reference_project_dir: Path
    reference_schematic: Path
    reference_board: Path
    canary_removed_references: tuple[str, ...]
    canary_ignored_references: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class SourceBackedTaskCatalog:
    strategy: str
    status: str
    last_reviewed: str
    vendor_root: Path
    notes: str
    sources: tuple[SourceBackedSource, ...]
    tasks: tuple[SourceBackedTaskSpec, ...]

    def sources_by_key(self) -> dict[str, SourceBackedSource]:
        return {source.key: source for source in self.sources}

    def tasks_by_id(self) -> dict[str, SourceBackedTaskSpec]:
        return {task.task_id: task for task in self.tasks}


def _resolve(repo_root: Path, value: str) -> Path:
    return (repo_root / value).absolute()


def load_source_backed_task_catalog(
    path: Path | None = None,
    *,
    include_disabled: bool = False,
) -> SourceBackedTaskCatalog:
    path = path or _default_catalog_path()
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    repo_root = path.absolute().parent.parent
    policy = payload["policy"]

    sources: list[SourceBackedSource] = []
    for raw_source in payload.get("source", []):
        license_path_value = str(raw_source.get("license_path", "")).strip()
        sources.append(
            SourceBackedSource(
                key=str(raw_source["key"]),
                name=str(raw_source["name"]),
                owner=str(raw_source["owner"]),
                repo_url=str(raw_source["repo_url"]),
                commit=str(raw_source["commit"]),
                license=str(raw_source["license"]),
                design_format=str(raw_source["design_format"]),
                vendored_root=_resolve(repo_root, str(raw_source["vendored_root"])),
                readme_path=_resolve(repo_root, str(raw_source["readme_path"])),
                license_path=_resolve(repo_root, license_path_value) if license_path_value else None,
                notes=str(raw_source["notes"]),
            )
        )

    source_map = {source.key: source for source in sources}
    tasks: list[SourceBackedTaskSpec] = []
    for raw_task in payload.get("task", []):
        source_key = str(raw_task["source_key"])
        canary_removed_references = tuple(
            str(value)
            for value in raw_task.get("canary_removed_references", [])
            if str(value).strip()
        )
        canary_ignored_references = tuple(
            str(value)
            for value in raw_task.get("canary_ignored_references", [])
            if str(value).strip()
        )
        tasks.append(
            SourceBackedTaskSpec(
                task_id=str(raw_task["task_id"]),
                title=str(raw_task["title"]),
                difficulty=str(raw_task["difficulty"]),
                enabled=bool(raw_task.get("enabled", True)),
                project_stem=str(raw_task["project_stem"]),
                source=source_map[source_key],
                reference_project_dir=_resolve(repo_root, str(raw_task["reference_project_dir"])),
                reference_schematic=_resolve(repo_root, str(raw_task["reference_schematic"])),
                reference_board=_resolve(repo_root, str(raw_task["reference_board"])),
                canary_removed_references=canary_removed_references,
                canary_ignored_references=canary_ignored_references,
                notes=str(raw_task["notes"]),
            )
        )

    if not include_disabled:
        tasks = [task for task in tasks if task.enabled]

    return SourceBackedTaskCatalog(
        strategy=str(policy["strategy"]),
        status=str(policy["status"]),
        last_reviewed=str(policy["last_reviewed"]),
        vendor_root=_resolve(repo_root, str(policy["vendor_root"])),
        notes=str(policy["notes"]).strip(),
        sources=tuple(sources),
        tasks=tuple(tasks),
    )
