from __future__ import annotations

import json
import subprocess
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

from bench.config import env_value
from harnesses.utils import (
    AgentRunResult,
    CONTAINER_FINAL_PROJECT_DIR,
    CONTAINER_PI_DIR,
    PI_WEB_EXTENSION_CONTAINER_PATH,
    REASONING_EFFORTS,
    RUNTIME_HOME_TMP_ROOT,
    harness,
    parse_json_events,
    sanitize_command_for_logging,
)


PI_MODEL_PROVIDERS = {
    "gemini-3.1-pro-preview": "google",
    "deepseek/deepseek-v4-pro": "vercel-ai-gateway",
}


def make_harness(model: str, mode: str, level: str):
    return harness(
        f"pi/{model}-{mode}-{level}",
        provider="pi",
        strategy="agent_project",
        model=model,
        reasoning_effort=REASONING_EFFORTS[level],
        access=mode,
    )


def build_prompt(_spec: Any, task_prompt: str) -> tuple[str | None, str]:
    prompt = "\n".join(
        [
            "You are the root owner of this Linux container.",
            "Work only inside /workspace.",
            "Read the task assets in /task.",
            (
                f"If /task/starter exists, copy it to {CONTAINER_FINAL_PROJECT_DIR} and modify only "
                "what is needed. Otherwise create the KiCad project from scratch in that directory."
            ),
            "The final answer must be a short plain-text summary.",
            task_prompt.strip(),
        ]
    ).strip()
    return None, prompt


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(part for part in parts if part).strip()


def _merge_usage_totals(total: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    merged = dict(total)
    for key, value in usage.items():
        if isinstance(value, dict):
            current = merged.get(key)
            if isinstance(current, dict):
                merged[key] = _merge_usage_totals(current, value)
            else:
                merged[key] = _merge_usage_totals({}, value)
            continue
        if isinstance(value, (int, float)):
            merged[key] = float(merged.get(key, 0) or 0) + float(value)
            if isinstance(value, int) and float(merged[key]).is_integer():
                merged[key] = int(merged[key])
            continue
        if key not in merged:
            merged[key] = value
    return merged


def _parse_result(stdout: str) -> tuple[str, str, dict[str, Any], list[dict[str, Any]]]:
    events = parse_json_events(stdout)
    session_id = ""
    response = ""
    usage_from_turns: dict[str, Any] = {}
    fallback_usage: dict[str, Any] = {}
    for event in events:
        if event.get("type") == "session":
            session_id = str(event.get("id", ""))
        event_type = str(event.get("type") or "")
        if event_type not in {"message_end", "turn_end", "agent_end"}:
            continue
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        text = _message_text(message)
        if text:
            response = text
        event_usage = message.get("usage")
        if not isinstance(event_usage, dict):
            continue
        if event_type == "turn_end":
            usage_from_turns = _merge_usage_totals(usage_from_turns, event_usage)
        elif not usage_from_turns:
            fallback_usage = _merge_usage_totals(fallback_usage, event_usage)
    return response, session_id, (usage_from_turns or fallback_usage), events


def _web_search_provider() -> str:
    configured = env_value("PI_WEB_SEARCH_PROVIDER")
    if configured:
        return configured
    if env_value("EXA_API_KEY"):
        return "exa"
    if env_value("GEMINI_API_KEY") or env_value("GOOGLE_API_KEY"):
        return "gemini"
    return "exa"


def write_pi_runtime_home(target_dir: Path) -> Path:
    agent_dir = target_dir / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    models_payload = {
        "providers": {
            "google": {
                "baseUrl": "https://generativelanguage.googleapis.com/v1beta",
                "api": "google-generative-ai",
                "apiKey": "GEMINI_API_KEY",
                "models": [
                    {
                        "id": "gemini-3.1-pro-preview",
                        "name": "Gemini 3.1 Pro Preview",
                        "reasoning": True,
                        "input": ["text", "image"],
                        "contextWindow": 1_000_000,
                        "maxTokens": 65_536,
                    }
                ],
            },
            "vercel-ai-gateway": {
                "baseUrl": "https://ai-gateway.vercel.sh/v1",
                "api": "openai-completions",
                "apiKey": "AI_GATEWAY_API_KEY",
                "models": [
                    {
                        "id": "deepseek/deepseek-v4-pro",
                        "name": "DeepSeek V4 Pro",
                        "reasoning": True,
                        "input": ["text"],
                        "contextWindow": 1_000_000,
                        "maxTokens": 384_000,
                        "compat": {
                            "vercelGatewayRouting": {
                                "only": ["deepseek", "fireworks", "novita"],
                                "order": ["deepseek", "fireworks", "novita"],
                            }
                        },
                    }
                ],
            },
        }
    }
    (agent_dir / "models.json").write_text(
        json.dumps(models_payload, indent=2) + "\n", encoding="utf-8"
    )
    (target_dir / "web-search.json").write_text(
        json.dumps({"provider": _web_search_provider()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return target_dir


def _cleanup_runtime_home(temp_dir: Path) -> None:
    proc = subprocess.run(
        ["rm", "-rf", str(temp_dir)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and not temp_dir.exists():
        return
    image = env_value("EDA_BENCH_AGENT_IMAGE")
    docker_detail = ""
    if image and temp_dir.exists():
        docker_proc = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--mount",
                f"type=bind,src={temp_dir.parent.resolve()},dst=/cleanup",
                "--entrypoint",
                "rm",
                image,
                "-rf",
                f"/cleanup/{temp_dir.name}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if docker_proc.returncode == 0 and not temp_dir.exists():
            return
        docker_detail = (
            docker_proc.stderr.strip()
            or docker_proc.stdout.strip()
            or "docker cleanup failed"
        )
    host_detail = proc.stderr.strip() or proc.stdout.strip() or "host cleanup failed"
    detail = host_detail if not docker_detail else f"{host_detail} | {docker_detail}"
    raise RuntimeError(f"failed to remove runtime home {temp_dir}: {detail}")


@contextmanager
def pi_runtime_home():
    RUNTIME_HOME_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix="eda_bench_pi_", dir=str(RUNTIME_HOME_TMP_ROOT))
    )
    with ExitStack() as stack:
        stack.callback(_cleanup_runtime_home, temp_dir)
        yield write_pi_runtime_home(temp_dir / ".pi")


def _pi_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for name in (
        "AI_GATEWAY_API_KEY",
        "VERCEL_AI_GATEWAY_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "EXA_API_KEY",
        "PERPLEXITY_API_KEY",
    ):
        value = env_value(name)
        if value:
            env[name] = value
    if "AI_GATEWAY_API_KEY" not in env and "VERCEL_AI_GATEWAY_API_KEY" in env:
        env["AI_GATEWAY_API_KEY"] = env["VERCEL_AI_GATEWAY_API_KEY"]
    if "GEMINI_API_KEY" not in env and "GOOGLE_API_KEY" in env:
        env["GEMINI_API_KEY"] = env["GOOGLE_API_KEY"]
    return env


def run(
    *,
    runtime: Any,
    spec: Any,
    system_prompt: str | None,
    prompt: str,
    workdir: Path,
    submission_dir: Path,
    image: str,
    task_dir: Path,
    container_export_path: Path | None = None,
    container_name: str = "",
) -> AgentRunResult:
    del system_prompt
    submission_dir.mkdir(parents=True, exist_ok=True)
    model_name = str(spec.model)
    provider_name = PI_MODEL_PROVIDERS.get(model_name)
    if not provider_name:
        raise ValueError(f"unsupported PI model: {model_name}")
    with pi_runtime_home() as auth_home:
        mounts = [
            runtime.BindMount(workdir.resolve(), runtime.CONTAINER_WORKDIR),
            runtime.BindMount(submission_dir.resolve(), runtime.CONTAINER_FINAL_PROJECT_DIR),
            runtime.BindMount(task_dir.resolve(), runtime.CONTAINER_TASK_DIR, read_only=True),
            runtime.BindMount(auth_home.resolve(), CONTAINER_PI_DIR),
        ]
        args = [
            "--provider",
            provider_name,
            "--model",
            model_name,
            "--mode",
            "json",
            "--thinking",
            str(spec.reasoning_effort),
            "--no-session",
            "--print",
        ]
        if str(spec.access) == "web":
            args.extend(["--extension", PI_WEB_EXTENSION_CONTAINER_PATH])
        else:
            args.append("--no-extensions")
        args.extend(["--tools", "read,bash,edit,write,grep,find,ls", prompt])
        env = _pi_env()
        cmd = runtime.docker_run_command(
            image=image,
            entrypoint="pi",
            mounts=mounts,
            env=env,
            args=args,
            remove=container_export_path is None,
            container_name=container_name,
            network="none" if str(spec.access) == "offline" else "bridge",
        )
        proc = runtime.run_docker_command(
            image=image,
            entrypoint="pi",
            mounts=mounts,
            env=env,
            args=args,
            container_export_path=container_export_path,
            container_name=container_name,
            network="none" if str(spec.access) == "offline" else "bridge",
        )
    response, session_id, usage, events = _parse_result(proc.stdout)
    safe_cmd = sanitize_command_for_logging(cmd)
    error = None
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        error = f"pi exit {proc.returncode}: {detail}"
    elif not events:
        error = "pi did not emit any JSON events"
    elif not usage:
        error = "pi did not emit usage data"
    return AgentRunResult(
        response=response,
        error=error,
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
        command=safe_cmd,
        session_id=session_id,
        usage=usage,
        parsed_events=events,
    )
