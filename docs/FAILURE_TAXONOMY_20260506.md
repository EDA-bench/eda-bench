# Failure Taxonomy: May 6, 2026 Baseline Runs

These counts are computed from saved Hugging Face grading artifacts for the run
IDs listed in `docs/BASELINE_REGRADE_20260506.md`. Score caps are not mutually
exclusive: one submitted board can trigger several caps.

The final paper table reports a no-model regrade of saved final projects under a
newer local oracle revision. The taxonomy below is still useful because it uses
the task-local `raw_metrics.json` files preserved with the original provenance.

## Cap Counts

| Harness group | Buildable rows in saved reports | Most common caps |
|---|---:|---|
| Codex GPT-5.5 web low | 34 | same-layer trace shorts 31; wrong external I/O pin/net mapping 30; missing component-function realization 30; isolated external I/O pads 27; split required external-net continuity 26; power-ground board short 25 |
| Codex GPT-5.5 web medium | 40 | wrong external I/O pin/net mapping 32; missing component-function realization 29; split required external-net continuity 29; same-layer trace shorts 25; isolated external I/O pads 24; power-ground board short 22 |
| Codex GPT-5.5 web high | 13 | missing component-function realization 10; split required external-net continuity 9; wrong external I/O pin/net mapping 9; isolated external I/O pads 8; same-layer trace shorts 5 |
| Codex GPT-5.5 web xhigh | 22 | split required external-net continuity 14; isolated external I/O pads 13; wrong external I/O pin/net mapping 13; missing component-function realization 8; weak component-function realization 6; missing or implausible high-speed pair geometry 6 |
| Pi Gemini 3.1 Pro Preview web high | 1 | missing active-device power integrity 1; split required external-net continuity 1; isolated external I/O pads 1 |
| Pi DeepSeek V4 Pro web high | 0 | no buildable submissions |

## Interpretation

The dominant failures are not parser failures alone. The strongest harnesses
often produce KiCad projects that build, but the projects fail on external
connector semantics, routed continuity, isolated pads, short safety, active
device realization, active power/ground integrity, and high-speed differential
pair plausibility.

This is the main empirical evidence that EDA Bench is measuring a different
property than project creation or visual plausibility.
