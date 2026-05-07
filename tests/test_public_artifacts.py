from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _archive_members(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    if path.suffixes[-2:] == [".tar", ".gz"]:
        with tarfile.open(path, "r:gz") as archive:
            return archive.getnames()
    raise AssertionError(f"unexpected build artifact: {path}")


def _repo_relative(member: str) -> Path:
    path = Path(member)
    parts = path.parts
    if parts and parts[0].startswith("eda_bench-"):
        return Path(*parts[1:])
    return path


def _is_task_artifact_path(path: Path) -> bool:
    parts = path.parts
    if not parts:
        return False
    if len(parts) >= 2 and parts[:2] == ("third_party", "upstream_designs"):
        return True
    if "source_snapshot" in parts or "canaries" in parts:
        return True
    return len(parts) >= 3 and parts[0] == "tasks" and parts[2] == "gold"


def test_python_build_artifacts_exclude_task_artifacts(tmp_path: Path) -> None:
    out_dir = tmp_path / "dist"
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(out_dir)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    artifacts = sorted(out_dir.iterdir())
    assert artifacts
    leaked: list[str] = []
    for artifact in artifacts:
        for member in _archive_members(artifact):
            relative = _repo_relative(member)
            if _is_task_artifact_path(relative):
                leaked.append(f"{artifact.name}:{member}")
    assert leaked == []
