from bench.accounting import (
    normalize_usage,
    path_size_stats,
    summarize_report_accounting,
    usage_costs,
)


def test_codex_usage_cost_counts_cached_input_once() -> None:
    usage = {
        "input_tokens": 2_000_000,
        "cached_input_tokens": 500_000,
        "output_tokens": 100_000,
        "reasoning_output_tokens": 25_000,
    }

    normalized = normalize_usage("codex", usage)
    costs = usage_costs("codex", "gpt-5.5", usage)

    assert normalized["uncached_input_tokens"] == 1_500_000
    assert normalized["cached_input_tokens"] == 500_000
    assert costs["estimated_openai_api_usd"] == 10.75
    assert costs["estimated_codex_credits"] == 268.75


def test_summarize_report_accounting_tracks_tokens_cost_and_provenance() -> None:
    report = {
        "harness": {"id": "codex/gpt-5.5-web-low", "provider": "codex", "model": "gpt-5.5"},
        "rows": [
            {
                "usage": {
                    "input_tokens": 1_000_000,
                    "cached_input_tokens": 900_000,
                    "output_tokens": 10_000,
                },
                "artifacts": {
                    "model_transcripts": {
                        "stdout_bytes_omitted": 100,
                        "stderr_bytes_omitted": 5,
                    }
                },
                "accounting": {
                    "provenance": {
                        "task_bundle_bytes": 1_000,
                        "task_bundle_file_count": 10,
                    }
                },
            }
        ],
        "accounting": {"provenance": {"metadata_bytes": 250, "metadata_file_count": 2}},
    }

    summary = summarize_report_accounting(report)

    assert summary["token_usage"]["total_tokens"] == 1_010_000
    assert summary["cost"]["estimated_openai_api_usd"] == 1.25
    assert summary["cost"]["estimated_codex_credits"] == 31.25
    assert summary["provenance"]["task_bundle_bytes"] == 1_000
    assert summary["provenance"]["metadata_bytes"] == 250
    assert summary["provenance"]["model_transcript_bytes_omitted"] == 105


def test_path_size_stats_counts_files(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("abc", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("de", encoding="utf-8")

    stats = path_size_stats(tmp_path)

    assert stats == {"bytes": 5, "file_count": 2}
