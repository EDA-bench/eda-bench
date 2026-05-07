from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bench.config import env_b64_json_value, env_value, set_env_b64_json_value
from harnesses.utils import (
    AgentRunResult,
    CONTAINER_CODEX_DIR,
    CONTAINER_FINAL_PROJECT_DIR,
    CONTAINER_WORKDIR,
    REASONING_EFFORTS,
    RUNTIME_HOME_TMP_ROOT,
    harness,
    parse_json_events,
    sanitize_command_for_logging,
)

CODEX_AUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_AUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_JWT_CLAIM_PATH = "https://api.openai.com/auth"


def make_harness(model: str, mode: str, level: str):
    return harness(
        f"codex/{model}-{mode}-{level}",
        provider="codex",
        strategy="agent_project",
        model=model,
        reasoning_effort=REASONING_EFFORTS[level],
        access=mode,
    )


def build_prompt(_spec: Any, task_prompt: str) -> tuple[str | None, str]:
    prompt = "\n".join(
        [
            "You are the root owner of this Linux container.",
            "Subagents are enabled.",
            "Work only inside /workspace.",
            "Read the task assets in /task.",
            (
                "Use the Codex /goals feature if it is available: create a goal for "
                "completing this KiCad task, keep working until the final project is "
                "actually complete, and mark the goal complete before your final response."
            ),
            (
                f"If /task/starter exists, copy it to {CONTAINER_FINAL_PROJECT_DIR} and modify only "
                "what is needed. Otherwise create the KiCad project from scratch in that directory."
            ),
            "The final answer must be a short plain-text summary.",
            task_prompt.strip(),
        ]
    ).strip()
    return None, prompt


def _parse_result(stdout: str) -> tuple[str, str, dict[str, Any], list[dict[str, Any]]]:
    events = parse_json_events(stdout)
    session_id = ""
    response = ""
    usage: dict[str, Any] = {}
    for event in events:
        if event.get("type") == "thread.started":
            session_id = str(event.get("thread_id", ""))
        if event.get("type") == "item.completed":
            item = event.get("item")
            if (
                isinstance(item, dict)
                and item.get("type") == "agent_message"
                and isinstance(item.get("text"), str)
            ):
                response = item["text"].strip()
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = dict(event["usage"])
    return response, session_id, usage, events


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid JWT")
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload + padding)
    value = json.loads(decoded.decode("utf-8"))
    if not isinstance(value, dict):
        raise TypeError("JWT payload must decode to an object")
    return value


def _codex_tokens(payload: dict[str, Any]) -> dict[str, Any]:
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        raise ValueError("Codex auth payload is missing tokens")
    access = str(tokens.get("access_token", "")).strip()
    refresh = str(tokens.get("refresh_token", "")).strip()
    if not access or not refresh:
        raise ValueError("Codex auth payload is missing access or refresh token")
    return tokens


def _rfc3339_utc(timestamp: int | float) -> str:
    return (
        datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _normalize_codex_auth_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    last_refresh = normalized.get("last_refresh")
    if isinstance(last_refresh, (int, float)):
        normalized["last_refresh"] = _rfc3339_utc(last_refresh)
    return normalized


def has_codex_auth_token() -> bool:
    try:
        current_codex_auth_payload(refresh_buffer_seconds=0)
    except Exception:
        return False
    return True


def _codex_access_token_expired(
    payload: dict[str, Any], buffer_seconds: int = 300
) -> bool:
    access = str(_codex_tokens(payload)["access_token"])
    token_payload = _decode_jwt_payload(access)
    expires_at = int(token_payload.get("exp", 0))
    return expires_at <= int(time.time()) + buffer_seconds


def _refresh_codex_auth_payload(payload: dict[str, Any]) -> dict[str, Any]:
    refresh_token = str(_codex_tokens(payload)["refresh_token"])
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CODEX_AUTH_CLIENT_ID,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        CODEX_AUTH_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        refreshed = json.load(response)
    if not isinstance(refreshed, dict):
        raise TypeError("Codex refresh response must be a JSON object")
    access = str(refreshed.get("access_token", "")).strip()
    refresh = str(refreshed.get("refresh_token", "")).strip()
    if not access or not refresh:
        raise ValueError("Codex refresh response is missing access or refresh token")
    next_payload = dict(payload)
    next_tokens = dict(_codex_tokens(payload))
    next_tokens["access_token"] = access
    next_tokens["refresh_token"] = refresh
    next_payload["tokens"] = next_tokens
    next_payload["last_refresh"] = _rfc3339_utc(time.time())
    set_env_b64_json_value("CODEX_AUTH_JSON_B64", next_payload)
    return next_payload


def local_codex_auth_payload() -> dict[str, Any]:
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    auth_path = codex_home / "auth.json"
    if not auth_path.exists():
        raise FileNotFoundError(f"Codex auth file not found: {auth_path}")
    payload = json.loads(auth_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Codex auth file must contain a JSON object")
    _codex_tokens(payload)
    return _normalize_codex_auth_payload(payload)


def _fresh_codex_auth_payload(
    payload: dict[str, Any], *, refresh_buffer_seconds: int
) -> dict[str, Any]:
    if _codex_access_token_expired(payload, buffer_seconds=refresh_buffer_seconds):
        return _refresh_codex_auth_payload(payload)
    return payload


def current_codex_auth_payload(*, refresh_buffer_seconds: int = 3600) -> dict[str, Any]:
    try:
        payload = env_b64_json_value("CODEX_AUTH_JSON_B64")
        payload = _normalize_codex_auth_payload(payload)
        return _fresh_codex_auth_payload(
            payload,
            refresh_buffer_seconds=refresh_buffer_seconds,
        )
    except Exception:
        payload = local_codex_auth_payload()
        payload = _normalize_codex_auth_payload(payload)
        payload = _fresh_codex_auth_payload(
            payload,
            refresh_buffer_seconds=refresh_buffer_seconds,
        )
        set_env_b64_json_value("CODEX_AUTH_JSON_B64", payload)
        return payload


def codex_oauth_credentials() -> dict[str, Any]:
    payload = current_codex_auth_payload()
    tokens = _codex_tokens(payload)
    access = str(tokens["access_token"])
    refresh = str(tokens["refresh_token"])
    token_payload = _decode_jwt_payload(access)
    auth_claim = token_payload.get(CODEX_JWT_CLAIM_PATH)
    if not isinstance(auth_claim, dict):
        raise ValueError("Codex access token is missing auth claim")
    account_id = str(auth_claim.get("chatgpt_account_id", "")).strip()
    if not account_id:
        raise ValueError("Codex access token is missing chatgpt account id")
    expires_at = int(token_payload.get("exp", 0)) * 1000
    if expires_at <= 0:
        raise ValueError("Codex access token is missing exp")
    return {
        "access": access,
        "refresh": refresh,
        "accountId": account_id,
        "expires": expires_at,
    }


def write_codex_runtime_home(target_dir: Path) -> Path:
    payload = current_codex_auth_payload()
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "auth.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    config_toml = env_value("CODEX_CONFIG_TOML")
    if config_toml:
        (target_dir / "config.toml").write_text(config_toml + "\n", encoding="utf-8")
    return target_dir


def sync_codex_runtime_auth(runtime_codex_dir: Path) -> None:
    runtime_auth = runtime_codex_dir / "auth.json"
    if not runtime_auth.exists():
        return
    payload = json.loads(runtime_auth.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("runtime Codex auth payload must be a JSON object")
    _codex_tokens(payload)
    payload = _normalize_codex_auth_payload(payload)
    set_env_b64_json_value("CODEX_AUTH_JSON_B64", payload)


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
        docker_cmd = [
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
        ]
        for attempt in range(3):
            docker_proc = subprocess.run(
                docker_cmd,
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
            if attempt < 2:
                time.sleep(1.0)
    sudo_detail = ""
    if temp_dir.exists():
        sudo_proc = subprocess.run(
            ["sudo", "-n", "rm", "-rf", str(temp_dir)],
            check=False,
            capture_output=True,
            text=True,
        )
        if sudo_proc.returncode == 0 and not temp_dir.exists():
            return
        sudo_detail = (
            sudo_proc.stderr.strip()
            or sudo_proc.stdout.strip()
            or "sudo cleanup failed"
        )
    host_detail = proc.stderr.strip() or proc.stdout.strip() or "host cleanup failed"
    detail_parts = [host_detail]
    if docker_detail:
        detail_parts.append(docker_detail)
    if sudo_detail:
        detail_parts.append(sudo_detail)
    detail = " | ".join(detail_parts)
    print(f"warning: failed to remove runtime home {temp_dir}: {detail}", file=sys.stderr)


@contextmanager
def codex_runtime_home():
    RUNTIME_HOME_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix="eda_bench_codex_", dir=str(RUNTIME_HOME_TMP_ROOT))
    )
    with ExitStack() as stack:
        stack.callback(_cleanup_runtime_home, temp_dir)
        yield write_codex_runtime_home(temp_dir / ".codex")


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
    with codex_runtime_home() as auth_home:
        mounts = [
            runtime.BindMount(workdir.resolve(), runtime.CONTAINER_WORKDIR),
            runtime.BindMount(submission_dir.resolve(), runtime.CONTAINER_FINAL_PROJECT_DIR),
            runtime.BindMount(task_dir.resolve(), runtime.CONTAINER_TASK_DIR, read_only=True),
            runtime.BindMount(auth_home.resolve(), CONTAINER_CODEX_DIR),
        ]
        args = [
            "--dangerously-bypass-approvals-and-sandbox",
            "--enable",
            "multi_agent",
        ]
        if str(spec.access) == "web":
            args.append("--search")
        args.extend(
            [
            "exec",
            "--json",
            "-m",
            str(spec.model),
            "--skip-git-repo-check",
            "--ephemeral",
            "-C",
            CONTAINER_WORKDIR,
            "-c",
            'model_reasoning_summary="auto"',
            "-c",
            f'model_reasoning_effort="{spec.reasoning_effort}"',
            prompt,
            ]
        )
        cmd = runtime.docker_run_command(
            image=image,
            entrypoint="codex",
            mounts=mounts,
            env={},
            args=args,
            remove=container_export_path is None,
            container_name=container_name,
            network="none" if str(spec.access) == "offline" else "bridge",
        )
        proc = runtime.run_docker_command(
            image=image,
            entrypoint="codex",
            mounts=mounts,
            env={},
            args=args,
            container_export_path=container_export_path,
            container_name=container_name,
            network="none" if str(spec.access) == "offline" else "bridge",
        )
        sync_codex_runtime_auth(auth_home)
    response, session_id, usage, events = _parse_result(proc.stdout)
    safe_cmd = sanitize_command_for_logging(cmd)
    error = None
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        error = f"codex exit {proc.returncode}: {detail}"
    elif not events:
        error = "codex did not emit any JSON events"
    elif not usage:
        error = "codex did not emit usage data"
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
