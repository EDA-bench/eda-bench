# Baseline Regrade Notes: May 6, 2026

These notes record the no-model regrade used by `paper/neurips_2026.tex`.

The executable path is `uv run regrade-provenance`. The regrade downloads saved
`submission/final_project` directories from the Hugging Face provenance dataset
and evaluates them with the current local oracle. It does not rerun any model
harness.

The provenance dataset is public:

- https://huggingface.co/datasets/eda-bench-neurips-2026/eda-bench-provenance

It contains the saved source reports, task bundles, final projects, grading
artifacts, and accounting summaries used for this table.

## Aggregate Results

The primary score is difficulty-weighted. The unweighted score is the mean
per-task score after applying the same regrade changes.

| Harness | Source runs | Released-task weighted score | Released-task unweighted score | Released-task builds |
|---|---:|---:|---:|---:|
| Codex GPT-5.5 web low | 1 | 0.0124 | 0.0143 | 31/35 |
| Codex GPT-5.5 web medium | 4 | 0.0279 | 0.0314 | 35/35 |
| Codex GPT-5.5 web high | 1 | 0.0293 | 0.0229 | 11/35 |
| Codex GPT-5.5 web xhigh | 4 | 0.0458 | 0.0500 | 21/35 |
| Pi Gemini 3.1 Pro Preview web high | 1 | 0.0113 | 0.0086 | 1/35 |
| Pi DeepSeek V4 Pro web high | 1 | 0.0000 | 0.0000 | 0/35 |

## Changed Task Scores

| Harness | Task | Old score | Regraded score | Build change |
|---|---|---:|---:|---|
| Codex GPT-5.5 web medium | `logic_level_converter_board` | 0.15 | 0.20 | none |
| Codex GPT-5.5 web xhigh | `ict_baseboard` | 0.00 | 0.05 | 0 -> 1 |
| Codex GPT-5.5 web xhigh | `mowi` | 0.00 | 0.00 | 0 -> 1 |
| Pi Gemini 3.1 Pro Preview web high | `adau1452_dsp_core` | 0.15 | 0.30 | none |

## Source Run IDs

- `codex__gpt-5.5-web-low_20260505T200208Z_2719115`
- `codex__gpt-5.5-web-medium_20260506T010715Z_2812175`
- `codex__gpt-5.5-web-medium_20260506T010715Z_2812182`
- `codex__gpt-5.5-web-medium_20260506T032737Z_2884928`
- `codex__gpt-5.5-web-medium_20260506T010716Z_2812190`
- `codex__gpt-5.5-web-high_20260505T200208Z_2719113`
- `codex__gpt-5.5-web-xhigh_20260506T032737Z_2884940`
- `codex__gpt-5.5-web-xhigh_20260506T032737Z_2884938`
- `codex__gpt-5.5-web-xhigh_20260506T032737Z_2884943`
- `codex__gpt-5.5-web-xhigh_20260506T034126Z_2891808`
- `pi__gemini-3.1-pro-preview-web-high_20260505T184850Z_2697190`
- `pi__deepseek__deepseek-v4-pro-web-high_20260505T200208Z_2719116`
