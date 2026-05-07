from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError

from bench.config import env_flag, env_value, required_env_value

HF_DATASET_BASE_URL = "https://huggingface.co/datasets"
HF_UPLOAD_RETRY_LIMIT = 3


def resolve_hf_token(repo_root: Path | None = None) -> str | None:
    value = env_value("HF_TOKEN", root=repo_root)
    return value or None


@dataclass(frozen=True)
class HFProvenanceConfig:
    repo_id: str


@dataclass
class HFProvenanceStore:
    repo_id: str
    path_prefix: str
    private: bool = False
    token: str | None = None

    def __post_init__(self) -> None:
        self.api = HfApi(token=self.token or resolve_hf_token())
        self.path_prefix = self.path_prefix.strip("/")
        self.api.create_repo(
            repo_id=self.repo_id,
            repo_type="dataset",
            private=self.private,
            exist_ok=True,
        )
        self.api.update_repo_settings(
            repo_id=self.repo_id,
            repo_type="dataset",
            private=self.private,
            token=self.token or resolve_hf_token(),
        )

    def repo_path(self, relative_path: str) -> str:
        relative = relative_path.strip("/")
        if not self.path_prefix:
            return relative
        return f"{self.path_prefix}/{relative}" if relative else self.path_prefix

    def file_url(self, relative_path: str) -> str:
        path_in_repo = quote(self.repo_path(relative_path), safe="/")
        return f"{HF_DATASET_BASE_URL}/{self.repo_id}/blob/main/{path_in_repo}"

    def tree_url(self, relative_path: str = "") -> str:
        path_in_repo = quote(self.repo_path(relative_path), safe="/")
        return f"{HF_DATASET_BASE_URL}/{self.repo_id}/tree/main/{path_in_repo}"

    def _upload_with_retry(self, upload_call):
        for attempt in range(1, HF_UPLOAD_RETRY_LIMIT + 1):
            try:
                return upload_call()
            except HfHubHTTPError as exc:
                delay = _hf_retry_delay_seconds(exc)
                if delay is None or attempt == HF_UPLOAD_RETRY_LIMIT:
                    raise
                time.sleep(delay)
        raise RuntimeError("unreachable HF upload retry state")

    def upload_file(self, local_path: Path, relative_path: str, commit_message: str) -> str:
        path_in_repo = self.repo_path(relative_path)
        self._upload_with_retry(
            lambda: self.api.upload_file(
                path_or_fileobj=str(local_path),
                path_in_repo=path_in_repo,
                repo_id=self.repo_id,
                repo_type="dataset",
                commit_message=commit_message,
            )
        )
        return self.file_url(relative_path)

    def upload_directory(
        self, local_dir: Path, relative_path: str, commit_message: str
    ) -> str:
        path_in_repo = self.repo_path(relative_path)
        self._upload_with_retry(
            lambda: self.api.upload_folder(
                folder_path=str(local_dir),
                path_in_repo=path_in_repo,
                repo_id=self.repo_id,
                repo_type="dataset",
                commit_message=commit_message,
            )
        )
        return self.tree_url(relative_path)


def load_hf_provenance_config(repo_root: Path) -> HFProvenanceConfig:
    return HFProvenanceConfig(
        repo_id=required_env_value("HF_PROVENANCE_REPO_ID", root=repo_root),
    )


def _hf_retry_delay_seconds(exc: HfHubHTTPError) -> int | None:
    message = str(exc)
    if any(status in message for status in ("500", "502", "503", "504")):
        return 60
    if "429" not in message and "rate limit" not in message.lower():
        return None
    match = re.search(r"Retry after (\d+) seconds", message)
    if match:
        return int(match.group(1)) + 5
    if "about 1 hour" in message.lower():
        return 65 * 60
    return 120


def _capture(cmd: list[str], cwd: Path | None = None) -> dict[str, object]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _should_skip_snapshot(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    parts = relative.parts
    if not parts:
        return False
    if path.name == ".env" or path.name.startswith(".env."):
        return True
    blocked_names = {
        ".git",
        ".venv",
        ".pytest_cache",
        ".mypy_cache",
        "__pycache__",
        ".ruff_cache",
        ".cache",
        ".tmp",
        ".idea",
        ".vscode",
        "dist",
        "build",
    }
    if any(part in blocked_names for part in parts):
        return True
    if parts[0] == "third_party":
        return True
    if len(parts) >= 3 and parts[0] == "tasks" and parts[2] == "gold":
        return True
    return False


def _write_repo_snapshot(out_dir: Path, cwd: Path) -> str:
    archive_name = "repo_snapshot.tar.gz"
    archive_path = out_dir / archive_name
    with tarfile.open(archive_path, "w:gz") as tar:
        for path in sorted(cwd.rglob("*")):
            if _should_skip_snapshot(path, cwd):
                continue
            arcname = Path("repo_snapshot") / path.relative_to(cwd)
            tar.add(path, arcname=str(arcname), recursive=False)
    return archive_name


def write_provenance_bundle(out_dir: Path, cwd: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    system_meta = {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "uname": platform.uname()._asdict(),
        "cwd": str(cwd),
        "repo_env": {
            "EDA_BENCH_AGENT_IMAGE": env_value("EDA_BENCH_AGENT_IMAGE"),
            "EDA_BENCH_UPLOAD_CONTAINER_IMAGES": env_flag(
                "EDA_BENCH_UPLOAD_CONTAINER_IMAGES",
                default=True,
            ),
            "EDA_BENCH_UPLOAD_MODEL_TRANSCRIPTS": env_flag(
                "EDA_BENCH_UPLOAD_MODEL_TRANSCRIPTS",
                default=True,
            ),
            "EDA_BENCH_UPLOAD_TASK_BUNDLES_INCREMENTALLY": env_flag(
                "EDA_BENCH_UPLOAD_TASK_BUNDLES_INCREMENTALLY",
                default=True,
            ),
            "EDA_BENCH_UPLOAD_PARTIAL_REPORTS": env_flag(
                "EDA_BENCH_UPLOAD_PARTIAL_REPORTS",
                default=True,
            ),
            "EDA_BENCH_HARNESS_TIMEOUT_SECONDS": env_value(
                "EDA_BENCH_HARNESS_TIMEOUT_SECONDS"
            ),
            "HF_PROVENANCE_REPO_ID": env_value("HF_PROVENANCE_REPO_ID"),
            "HF_TOKEN": bool(env_value("HF_TOKEN")),
            "CODEX_AUTH_JSON_B64": bool(env_value("CODEX_AUTH_JSON_B64")),
            "CODEX_CONFIG_TOML": bool(env_value("CODEX_CONFIG_TOML")),
            "GEMINI_API_KEY": bool(env_value("GEMINI_API_KEY")),
            "GOOGLE_API_KEY": bool(env_value("GOOGLE_API_KEY")),
            "AI_GATEWAY_API_KEY": bool(env_value("AI_GATEWAY_API_KEY")),
            "VERCEL_AI_GATEWAY_API_KEY": bool(env_value("VERCEL_AI_GATEWAY_API_KEY")),
            "EXA_API_KEY": bool(env_value("EXA_API_KEY")),
            "PERPLEXITY_API_KEY": bool(env_value("PERPLEXITY_API_KEY")),
            "PI_WEB_SEARCH_PROVIDER": env_value("PI_WEB_SEARCH_PROVIDER"),
        },
    }
    (out_dir / "system_info.json").write_text(
        json.dumps(system_meta, indent=2) + "\n", encoding="utf-8"
    )

    version_commands = {
        "python_version.txt": ["python", "--version"],
        "uv_version.txt": ["uv", "--version"],
        "docker_version.txt": ["docker", "--version"],
    }
    if shutil.which("codex"):
        version_commands["codex_version.txt"] = ["codex", "--version"]
    if shutil.which("pi"):
        version_commands["pi_version.txt"] = ["pi", "--version"]
    for filename, cmd in version_commands.items():
        result = _capture(cmd, cwd=cwd)
        body = result["stdout"] or result["stderr"] or ""
        (out_dir / filename).write_text(str(body), encoding="utf-8", errors="ignore")

    freeze = _capture(["uv", "pip", "freeze"], cwd=cwd)
    (out_dir / "uv_pip_freeze.txt").write_text(
        str(freeze["stdout"] or freeze["stderr"] or ""),
        encoding="utf-8",
        errors="ignore",
    )

    git_meta = {
        "rev_parse_head": _capture(["git", "rev-parse", "HEAD"], cwd=cwd),
        "branch": _capture(["git", "branch", "--show-current"], cwd=cwd),
        "status": _capture(["git", "status", "--short"], cwd=cwd),
        "tracked_files": _capture(["git", "ls-files"], cwd=cwd),
        "untracked_files": _capture(
            ["git", "ls-files", "--others", "--exclude-standard"], cwd=cwd
        ),
        "diff": _capture(
            [
                "git",
                "diff",
                "--binary",
                "--",
                ".",
                ":(exclude).env",
                ":(exclude).env.*",
            ],
            cwd=cwd,
        ),
        "diff_cached": _capture(
            [
                "git",
                "diff",
                "--cached",
                "--binary",
                "--",
                ".",
                ":(exclude).env",
                ":(exclude).env.*",
            ],
            cwd=cwd,
        ),
    }
    (out_dir / "git_metadata.json").write_text(
        json.dumps(git_meta, indent=2) + "\n", encoding="utf-8"
    )
    repo_snapshot = _write_repo_snapshot(out_dir, cwd)

    files = {
        "system_info": "system_info.json",
        "python_version": "python_version.txt",
        "uv_version": "uv_version.txt",
        "docker_version": "docker_version.txt",
        "uv_pip_freeze": "uv_pip_freeze.txt",
        "git_metadata": "git_metadata.json",
        "repo_snapshot": repo_snapshot,
    }
    if "codex_version.txt" in version_commands:
        files["codex_version"] = "codex_version.txt"
    if "pi_version.txt" in version_commands:
        files["pi_version"] = "pi_version.txt"
    return {key: str((out_dir / value).name) for key, value in files.items()}


def write_docker_bundle(
    out_dir: Path,
    cwd: Path,
    image: str,
    *,
    include_image: bool = True,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    inspect = _capture(["docker", "image", "inspect", image], cwd=cwd)
    (out_dir / "docker_image_inspect.json").write_text(
        json.dumps(inspect, indent=2) + "\n", encoding="utf-8"
    )
    files = {
        "docker_image_inspect": "docker_image_inspect.json",
    }
    if include_image:
        image_tar = out_dir / "docker_image_before.tar"
        subprocess.run(
            ["docker", "save", "--output", str(image_tar), image],
            cwd=cwd,
            check=True,
        )
        files["docker_image_tar"] = image_tar.name
    else:
        skipped = out_dir / "docker_image_before_skipped.txt"
        skipped.write_text(
            "Docker image tar capture disabled by EDA_BENCH_UPLOAD_CONTAINER_IMAGES.\n",
            encoding="utf-8",
        )
        files["docker_image_tar_skipped"] = skipped.name
    return files
