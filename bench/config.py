from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
ENV_KEY_ORDER = (
    "EDA_BENCH_AGENT_IMAGE",
    "EDA_BENCH_UPLOAD_CONTAINER_IMAGES",
    "EDA_BENCH_UPLOAD_MODEL_TRANSCRIPTS",
    "EDA_BENCH_UPLOAD_TASK_BUNDLES_INCREMENTALLY",
    "EDA_BENCH_UPLOAD_PARTIAL_REPORTS",
    "EDA_BENCH_HARNESS_TIMEOUT_SECONDS",
    "OPENAI_API_KEY",
    "AI_GATEWAY_API_KEY",
    "VERCEL_AI_GATEWAY_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "EXA_API_KEY",
    "PERPLEXITY_API_KEY",
    "PI_WEB_SEARCH_PROVIDER",
    "HF_TASK_PACK_REPO_ID",
    "HF_PROVENANCE_REPO_ID",
    "HF_TOKEN",
    "CODEX_AUTH_JSON_B64",
    "CODEX_CONFIG_TOML",
)


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _resolve_env_path(root: Path | None = None) -> Path:
    if root is None:
        return ENV_PATH
    candidate = Path(root)
    return candidate if candidate.name == ".env" else candidate / ".env"


def _render_env_value(value: str) -> str:
    if "\n" in value:
        raise ValueError("multi-line .env values are not supported")
    return value


def _render_env_file(values: dict[str, str]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for key in ENV_KEY_ORDER:
        if key in values:
            lines.append(f"{key}={_render_env_value(str(values[key]))}")
            seen.add(key)
    for key in sorted(values):
        if key in seen:
            continue
        lines.append(f"{key}={_render_env_value(str(values[key]))}")
    return "\n".join(lines) + "\n"


@lru_cache(maxsize=1)
def load_repo_env() -> dict[str, str]:
    return _parse_env_file(ENV_PATH)


def reload_repo_env() -> dict[str, str]:
    load_repo_env.cache_clear()
    return load_repo_env()


def load_env_file(root: Path | None = None) -> dict[str, str]:
    path = _resolve_env_path(root)
    if path == ENV_PATH:
        return load_repo_env()
    return _parse_env_file(path)


def env_value(name: str, default: str = "", root: Path | None = None) -> str:
    return str(load_env_file(root).get(name, default)).strip()


def env_flag(name: str, default: bool = False, root: Path | None = None) -> bool:
    raw_default = "1" if default else "0"
    value = env_value(name, raw_default, root=root).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise RuntimeError(f"{name} must be a boolean-like value in {_resolve_env_path(root)}")


def env_positive_float(name: str, root: Path | None = None) -> float | None:
    raw = env_value(name, root=root)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive number in {_resolve_env_path(root)}") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive number in {_resolve_env_path(root)}")
    return value


def required_env_value(name: str, root: Path | None = None) -> str:
    value = env_value(name, root=root)
    if not value:
        raise RuntimeError(f"{name} is required in {_resolve_env_path(root)}")
    return value


def update_repo_env(updates: dict[str, str]) -> dict[str, str]:
    values = dict(load_repo_env())
    for key, value in updates.items():
        values[str(key)] = str(value)
    ENV_PATH.write_text(_render_env_file(values), encoding="utf-8")
    return reload_repo_env()


def env_json_value(name: str) -> dict[str, Any]:
    raw = required_env_value(name)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError(f"{name} must decode to a JSON object")
    return payload


def env_b64_json_value(name: str) -> dict[str, Any]:
    raw = required_env_value(name)
    decoded = base64.b64decode(raw.encode("ascii")).decode("utf-8")
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise TypeError(f"{name} must decode to a JSON object")
    return payload


def set_env_b64_json_value(name: str, payload: dict[str, Any]) -> dict[str, str]:
    encoded = base64.b64encode(
        (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    ).decode("ascii")
    return update_repo_env({name: encoded})


def clamp_unit_interval(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


DIFFICULTY_SCORE_WEIGHTS = {
    "very easy": 1.0,
    "easy": 1.5,
    "medium": 2.0,
    "hard": 3.0,
    "very hard": 4.0,
    "extreme": 5.0,
}


def difficulty_score_weight(difficulty: str) -> float:
    return DIFFICULTY_SCORE_WEIGHTS.get(str(difficulty or "").strip().lower(), 1.0)


def summarize_overall_score(rows: list[dict[str, Any]]) -> float:
    weighted_scores: list[float] = []
    weights: list[float] = []
    for row in rows:
        score = float(row["metrics"]["overall_score"])
        weight = difficulty_score_weight(str(row.get("difficulty") or ""))
        weighted_scores.append(score * weight)
        weights.append(weight)
    if not weighted_scores:
        return 0.0
    return clamp_unit_interval(sum(weighted_scores) / sum(weights))
