from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bench.config import required_env_value

OPENAI_API_USD_PER_1M = {
    "gpt-5.5": {"input": 5.00, "cached_input": 0.50, "output": 30.00},
    "gpt-5.4": {"input": 2.50, "cached_input": 0.25, "output": 15.00},
    "gpt-5.4-mini": {"input": 0.75, "cached_input": 0.075, "output": 4.50},
}

CODEX_CREDITS_PER_1M = {
    "gpt-5.5": {"input": 125.0, "cached_input": 12.50, "output": 750.0},
    "gpt-5.4": {"input": 62.50, "cached_input": 6.250, "output": 375.0},
    "gpt-5.4-mini": {"input": 18.75, "cached_input": 1.875, "output": 113.0},
    "gpt-5.3-codex": {"input": 43.75, "cached_input": 4.375, "output": 350.0},
    "gpt-5.2": {"input": 43.75, "cached_input": 4.375, "output": 350.0},
}


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _int_number(value: Any) -> int:
    return int(max(0.0, _number(value)))


def _round_cost(value: float) -> float:
    return round(float(value), 6)


def path_size_stats(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"bytes": 0, "file_count": 0}
    if path.is_file():
        return {"bytes": path.stat().st_size, "file_count": 1}
    total_bytes = 0
    file_count = 0
    for item in path.rglob("*"):
        if item.is_file():
            file_count += 1
            total_bytes += item.stat().st_size
    return {"bytes": total_bytes, "file_count": file_count}


def normalize_usage(provider: str, usage: dict[str, Any]) -> dict[str, int]:
    provider = provider.lower().strip()
    if "input_tokens" in usage or "cached_input_tokens" in usage:
        input_total = _int_number(usage.get("input_tokens"))
        cached_input = _int_number(usage.get("cached_input_tokens"))
        uncached_input = max(0, input_total - cached_input)
        output = _int_number(usage.get("output_tokens"))
        return {
            "input_tokens": input_total,
            "uncached_input_tokens": uncached_input,
            "cached_input_tokens": cached_input,
            "cache_write_tokens": 0,
            "output_tokens": output,
            "reasoning_output_tokens": _int_number(usage.get("reasoning_output_tokens")),
            "total_tokens": input_total + output,
        }
    if provider == "pi" or "cacheRead" in usage:
        uncached_input = _int_number(usage.get("input"))
        cached_input = _int_number(usage.get("cacheRead"))
        cache_write = _int_number(usage.get("cacheWrite"))
        output = _int_number(usage.get("output"))
        total = _int_number(usage.get("totalTokens"))
        if not total:
            total = uncached_input + cached_input + cache_write + output
        return {
            "input_tokens": uncached_input + cached_input + cache_write,
            "uncached_input_tokens": uncached_input,
            "cached_input_tokens": cached_input,
            "cache_write_tokens": cache_write,
            "output_tokens": output,
            "reasoning_output_tokens": 0,
            "total_tokens": total,
        }
    input_tokens = _int_number(usage.get("input", usage.get("prompt_tokens")))
    output = _int_number(usage.get("output", usage.get("completion_tokens")))
    return {
        "input_tokens": input_tokens,
        "uncached_input_tokens": input_tokens,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": output,
        "reasoning_output_tokens": 0,
        "total_tokens": input_tokens + output,
    }


def _apply_token_rates(usage: dict[str, int], rates: dict[str, float]) -> float:
    return (
        usage["uncached_input_tokens"] * rates["input"]
        + usage["cached_input_tokens"] * rates["cached_input"]
        + usage["output_tokens"] * rates["output"]
    ) / 1_000_000


def usage_costs(provider: str, model: str, usage: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_usage(provider, usage)
    costs: dict[str, Any] = {}
    api_rates = OPENAI_API_USD_PER_1M.get(model)
    if api_rates:
        costs["estimated_openai_api_usd"] = _round_cost(
            _apply_token_rates(normalized, api_rates)
        )
    codex_rates = CODEX_CREDITS_PER_1M.get(model)
    if provider == "codex" and codex_rates:
        costs["estimated_codex_credits"] = _round_cost(
            _apply_token_rates(normalized, codex_rates)
        )
    provider_cost = usage.get("cost")
    if isinstance(provider_cost, dict) and "total" in provider_cost:
        costs["provider_reported_cost"] = _round_cost(_number(provider_cost["total"]))
    return costs


def row_accounting(provider: str, model: str, row: dict[str, Any]) -> dict[str, Any]:
    usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
    artifacts = row.get("artifacts") if isinstance(row.get("artifacts"), dict) else {}
    transcripts = artifacts.get("model_transcripts")
    if not isinstance(transcripts, dict):
        transcripts = {}
    provenance = {
        "model_transcript_bytes_included": _int_number(transcripts.get("stdout_bytes"))
        + _int_number(transcripts.get("stderr_bytes")),
        "model_transcript_bytes_omitted": _int_number(
            transcripts.get("stdout_bytes_omitted")
        )
        + _int_number(transcripts.get("stderr_bytes_omitted")),
    }
    existing = row.get("accounting")
    if isinstance(existing, dict) and isinstance(existing.get("provenance"), dict):
        provenance.update(existing["provenance"])
    return {
        "tokens": normalize_usage(provider, usage),
        "cost": usage_costs(provider, model, usage),
        "provenance": provenance,
    }


def _add_token_totals(total: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        total[key] = int(total.get(key, 0)) + int(value)


def _add_cost_totals(total: dict[str, float], costs: dict[str, Any]) -> None:
    for key, value in costs.items():
        total[key] = _round_cost(float(total.get(key, 0.0)) + _number(value))


def summarize_report_accounting(report: dict[str, Any]) -> dict[str, Any]:
    harness = report.get("harness") if isinstance(report.get("harness"), dict) else {}
    provider = str(harness.get("provider") or "")
    model = str(harness.get("model") or "")
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    token_totals: dict[str, int] = {}
    cost_totals: dict[str, float] = {}
    provenance_totals: dict[str, int] = {
        "task_bundle_bytes": 0,
        "task_bundle_file_count": 0,
        "container_image_after_bytes": 0,
        "metadata_bytes": 0,
        "metadata_file_count": 0,
        "model_transcript_bytes_included": 0,
        "model_transcript_bytes_omitted": 0,
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        accounting = row_accounting(provider, model, row)
        _add_token_totals(token_totals, accounting["tokens"])
        _add_cost_totals(cost_totals, accounting["cost"])
        for key, value in accounting["provenance"].items():
            provenance_totals[key] = int(provenance_totals.get(key, 0)) + _int_number(value)
    report_accounting = report.get("accounting")
    if isinstance(report_accounting, dict):
        provenance = report_accounting.get("provenance")
        if isinstance(provenance, dict):
            for key in ("metadata_bytes", "metadata_file_count", "report_json_bytes"):
                if key in provenance:
                    provenance_totals[key] = _int_number(provenance[key])
    notes = []
    if model not in OPENAI_API_USD_PER_1M and not cost_totals.get("provider_reported_cost"):
        notes.append(f"no price table for {provider}/{model}; token totals only")
    return {
        "harness_id": harness.get("id"),
        "provider": provider,
        "model": model,
        "task_count": len(rows),
        "token_usage": token_totals,
        "cost": cost_totals,
        "provenance": provenance_totals,
        "notes": notes,
    }


def aggregate_accounting(items: list[dict[str, Any]]) -> dict[str, Any]:
    token_totals: dict[str, int] = {}
    cost_totals: dict[str, float] = {}
    provenance_totals: dict[str, int] = {}
    task_count = 0
    for item in items:
        task_count += _int_number(item.get("task_count"))
        for key, value in dict(item.get("token_usage") or {}).items():
            token_totals[key] = int(token_totals.get(key, 0)) + _int_number(value)
        for key, value in dict(item.get("cost") or {}).items():
            cost_totals[key] = _round_cost(float(cost_totals.get(key, 0.0)) + _number(value))
        for key, value in dict(item.get("provenance") or {}).items():
            provenance_totals[key] = int(provenance_totals.get(key, 0)) + _int_number(value)
    return {
        "run_count": len(items),
        "task_count": task_count,
        "token_usage": token_totals,
        "cost": cost_totals,
        "provenance": provenance_totals,
    }


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _hf_report(repo_id: str, run: str, token: str | None) -> dict[str, Any]:
    from huggingface_hub import hf_hub_download

    report_path = hf_hub_download(
        repo_id=repo_id,
        repo_type="dataset",
        filename=f"evals/harnesses/{run}/report.json",
        token=token,
    )
    return _load_report(Path(report_path))


def _hf_remote_stats(repo_id: str, run: str, token: str | None) -> dict[str, int]:
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    path = f"evals/harnesses/{run}"
    total_bytes = 0
    file_count = 0
    for item in api.list_repo_tree(
        repo_id=repo_id,
        repo_type="dataset",
        path_in_repo=path,
        recursive=True,
    ):
        size = getattr(item, "size", None)
        if size is not None:
            file_count += 1
            total_bytes += int(size)
    return {"remote_hf_bytes": total_bytes, "remote_hf_file_count": file_count}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize token cost and provenance volume for eval reports."
    )
    parser.add_argument("report", nargs="*", type=Path, help="Local report.json path")
    parser.add_argument("--hf-repo", default="", help="HF dataset repo for --hf-run")
    parser.add_argument("--hf-run", action="append", default=[], help="HF run directory name")
    parser.add_argument(
        "--remote-size",
        action="store_true",
        help="Also sum remote HF file sizes for --hf-run entries.",
    )
    args = parser.parse_args(argv)
    if not args.report and not args.hf_run:
        parser.error("provide at least one report path or --hf-run")
    token = required_env_value("HF_TOKEN") if args.hf_run else None
    runs: list[dict[str, Any]] = []
    for path in args.report:
        runs.append({"source": str(path), **summarize_report_accounting(_load_report(path))})
    for run in args.hf_run:
        if not args.hf_repo:
            parser.error("--hf-repo is required with --hf-run")
        summary = summarize_report_accounting(_hf_report(args.hf_repo, run, token))
        if args.remote_size:
            summary["provenance"].update(_hf_remote_stats(args.hf_repo, run, token))
        runs.append({"source": f"{args.hf_repo}/{run}", **summary})
    payload = {"runs": runs, "total": aggregate_accounting(runs)}
    print(json.dumps(payload, indent=2) + "\n")
    return 0
