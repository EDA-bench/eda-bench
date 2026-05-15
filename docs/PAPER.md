# EDA Bench Paper Notes

Canonical NeurIPS draft: `paper/neurips_2026.tex`.

Use the TeX draft as the source of truth for submission text. The current
NeurIPS release uses the 35-task license-triaged public manifest, reports
saved-project regrades with `uv run regrade-provenance`, and frames public
source visibility as a reproducibility and realism tradeoff similar to
SWE-bench rather than as a deliberately public-answer task.

Current release facts:

- Released task count: 35 source-backed KiCad tasks.
- Quarantined candidate tasks: `cm5io_official`, `mixed_signal_stm32_dev_board`,
  `rp2350b_dev_board`, `stm32f_audio_codec`, and `ef28_badge`.
- Validation: 35/35 released references score 1.0 and 35/35 released structural
  fail canaries score at most 0.15.
- Mutation history: 162 generated mutation canaries were validated on the
  original 40-task candidate set.
- Best released-task baseline: Codex GPT-5.5 web xhigh, weighted score 0.0458,
  unweighted score 0.0500, builds 21/35.

Do not copy older 40-task draft text into the paper. If a result or artifact
claim depends on the quarantined candidate tasks, label it as candidate-set
history rather than released-task evidence.
