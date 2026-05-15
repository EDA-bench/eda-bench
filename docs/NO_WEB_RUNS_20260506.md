# No-Web Runs: May 6, 2026

These runs are NeurIPS submission-time access-policy calibration. They use the
same public runtime task packs and grader path as the reported web-enabled rows,
but Codex web access is disabled by harness config. Report completed full
sweeps only, and do not mix them with the default web leaderboard unless the
access policy is shown in the table.

## Launched Sweeps

| Harness family | Configs | Scratch root | Status |
|---|---|---|---|
| Codex GPT-5.5 no-web | low, medium, high, xhigh | `/tmp` | Medium/high/xhigh completed; low not reported |
| Codex GPT-5.4 no-web | low, medium, high, xhigh | `/mnt/eda-bench-runs/tmp` | Xhigh completed; other configs not reported |
| Codex GPT-5.4-mini no-web | low, medium, high, xhigh | `/mnt/eda-bench-runs/tmp` | Medium/high completed; low/xhigh not reported |

## Completed Full Sweeps

These rows are present in the Hugging Face provenance dataset.

| Harness | Weighted score | Unweighted score | Build successes | HF run |
|---|---:|---:|---:|---|
| Codex GPT-5.5 no-web medium | 0.0000 | 0.0000 | 0/40 | `evals/harnesses/codex__gpt-5.5-no_web-medium_20260507T033319Z_3432012` |
| Codex GPT-5.5 no-web high | 0.0000 | 0.0000 | 0/40 | `evals/harnesses/codex__gpt-5.5-no_web-high_20260507T033319Z_3432018` |
| Codex GPT-5.5 no-web xhigh | 0.0000 | 0.0000 | 0/40 | `evals/harnesses/codex__gpt-5.5-no_web-xhigh_20260507T033319Z_3432017` |
| Codex GPT-5.4 no-web xhigh | 0.0000 | 0.0000 | 0/40 | `evals/harnesses/codex__gpt-5.4-no_web-xhigh_20260507T033528Z_3439753` |
| Codex GPT-5.4-mini no-web medium | 0.0000 | 0.0000 | 0/40 | `evals/harnesses/codex__gpt-5.4-mini-no_web-medium_20260507T033724Z_3448333` |
| Codex GPT-5.4-mini no-web high | 0.0000 | 0.0000 | 0/40 | `evals/harnesses/codex__gpt-5.4-mini-no_web-high_20260507T033724Z_3448341` |

## Reporting Rule

For every completed run, record:

- Hugging Face run id;
- task-pack revision;
- local git commit and grader revision;
- weighted score;
- unweighted score;
- build count;
- token/cost accounting;
- whether any task timed out or failed before grading.

If only a subset of these sweeps finishes before the submission deadline, use
the completed rows as calibration controls. Mark missing rows as not reported,
not as zero.
