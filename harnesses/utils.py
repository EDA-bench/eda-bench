from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

CONTAINER_CODEX_DIR = "/root/.codex"
CONTAINER_PI_DIR = "/root/.pi"
CONTAINER_TASK_DIR = "/task"
CONTAINER_WORKDIR = "/workspace"
CONTAINER_FINAL_PROJECT_DIR = "/workspace/final_project"
PI_WEB_EXTENSION_CONTAINER_PATH = "/usr/local/lib/node_modules/pi-web-access/index.ts"
_SENSITIVE_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH")

REASONING_EFFORTS = {
    "low": "low",
    "medium": "medium",
    "med": "medium",
    "high": "high",
    "xhigh": "xhigh",
}

HARNESSES_ROOT = Path(__file__).resolve().parent
REPO_ROOT = HARNESSES_ROOT.parent
RUNTIME_HOME_TMP_ROOT = REPO_ROOT / ".tmp" / "runtime_homes"
BUILTIN_HARNESS_PROVIDERS = ("codex", "pi")


@dataclass(frozen=True)
class AgentRunResult:
    response: str
    error: str | None
    stdout: str
    stderr: str
    returncode: int | None
    command: list[str]
    session_id: str
    usage: dict[str, Any]
    parsed_events: list[dict[str, Any]]
    artifact_contents: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HarnessSpec:
    harness_id: str
    provider: str
    strategy: str
    model: str
    reasoning_effort: str
    access: str = "web"
    file_path: str = ""
    symbol_name: str = ""


def harness(
    harness_id: str,
    *,
    provider: str,
    strategy: str,
    model: str,
    reasoning_effort: str,
    access: str = "web",
) -> HarnessSpec:
    return HarnessSpec(
        harness_id=harness_id,
        provider=provider,
        strategy=strategy,
        model=model,
        reasoning_effort=reasoning_effort,
        access=access,
    )


def parse_json_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        value = json.loads(stripped)
        if isinstance(value, dict):
            events.append(value)
    return events


def _looks_sensitive_env_name(name: str) -> bool:
    upper = str(name or "").strip().upper()
    return bool(upper) and any(marker in upper for marker in _SENSITIVE_ENV_MARKERS)


def sanitize_command_for_logging(command: list[str]) -> list[str]:
    sanitized: list[str] = []
    index = 0
    while index < len(command):
        part = str(command[index])
        if part in {"-e", "--env"} and index + 1 < len(command):
            env_spec = str(command[index + 1])
            name, sep, _value = env_spec.partition("=")
            if sep and _looks_sensitive_env_name(name):
                sanitized.extend([part, f"{name}=REDACTED"])
            else:
                sanitized.extend([part, env_spec])
            index += 2
            continue
        sanitized.append(part)
        index += 1
    return sanitized


def model_to_slug(model: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(model)).strip("_")
    if not slug:
        raise ValueError(f"unsupported built-in harness model: {model}")
    return slug


def builtin_harness_name(model: str, access: str, level: str) -> str:
    return f"{model_to_slug(model)}_{access}_{level}"


def builtin_harness_ref(provider: str, model: str, access: str, level: str) -> str:
    return f"{(HARNESSES_ROOT / provider / 'harnesses.py').resolve()}:{builtin_harness_name(model, access, level)}"


def register_builtin_harnesses(
    namespace: dict[str, Any],
    *,
    configs: tuple[tuple[str, str, str], ...],
    make_harness: Callable[[str, str, str], Any],
) -> tuple[tuple[str, str, str], ...]:
    for model, access, level in configs:
        name = builtin_harness_name(model, access, level)

        def factory(
            model_name: str = model,
            access_mode: str = access,
            level_name: str = level,
        ):
            return make_harness(model_name, access_mode, level_name)

        factory.__name__ = name
        namespace[name] = factory
    return configs


def _load_module(path: Path, kind: str) -> Any:
    module_name = "_eda_bench_dynamic_" + re.sub(r"[^a-zA-Z0-9_]+", "_", path.as_posix())
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load {kind} module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def split_harness_ref(value: str | Path) -> tuple[Path, str]:
    if isinstance(value, Path):
        raw = value
        symbol_name = ""
    else:
        raw_text = value.strip()
        if ".py:" not in raw_text:
            raise ValueError(
                "harness refs must use the form path/to/harnesses.py:symbol_name"
            )
        path_text, symbol_name = raw_text.rsplit(":", 1)
        raw = Path(path_text)
    return raw, symbol_name.strip()


def resolve_harness_spec_path(value: str | Path) -> Path:
    raw, _ = split_harness_ref(value)
    candidate = raw if raw.suffix == ".py" else raw.with_suffix(".py")
    if candidate.exists():
        return candidate.resolve()
    raise FileNotFoundError(f"Harness spec path does not exist: {value}")


def load_harness_spec(value: str | Path) -> HarnessSpec:
    raw_path, symbol_name = split_harness_ref(value)
    if not symbol_name:
        raise ValueError("harness refs must name an exported symbol inside harnesses.py")
    resolved = resolve_harness_spec_path(raw_path)
    module = _load_module(resolved, "harness")
    exported = getattr(module, symbol_name, None)
    if exported is None:
        raise AttributeError(f"harness module {resolved} must define `{symbol_name}`")
    raw_spec = exported() if callable(exported) else exported
    return HarnessSpec(
        harness_id=str(raw_spec.harness_id),
        provider=str(raw_spec.provider),
        strategy=str(raw_spec.strategy),
        model=str(raw_spec.model),
        reasoning_effort=str(raw_spec.reasoning_effort),
        access=str(raw_spec.access),
        file_path=str(resolved),
        symbol_name=symbol_name,
    )


def harness_module(spec: HarnessSpec) -> Any:
    if not spec.file_path:
        raise ValueError("Harness spec is missing file_path")
    return _load_module(Path(spec.file_path), "harness")


def provider_module(provider: str) -> Any:
    return _load_module((HARNESSES_ROOT / provider / "harnesses.py").resolve(), "harness")


@lru_cache(maxsize=1)
def builtin_harness_matrix() -> tuple[tuple[str, str, str, str], ...]:
    matrix: list[tuple[str, str, str, str]] = []
    for provider in BUILTIN_HARNESS_PROVIDERS:
        module = provider_module(provider)
        configs = getattr(module, "SUPPORTED_CONFIGS", ())
        for model, access, level in configs:
            matrix.append((provider, str(model), str(access), str(level)))
    return tuple(matrix)
