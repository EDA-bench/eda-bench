# Mutation Canary Sweep: May 6, 2026

This records the full generated-mutation canary sweep for the current task-pack
builder and oracle code.

Command shape:

```bash
uv run verify-task-canaries --task-id <task_id>
```

The sweep was run per task with three local workers. Each task stages a fresh
full task pack, grades the pass canary, grades the structural fail canary, and
grades all generated mutation canaries that apply to that task.

## Summary

| Metric | Value |
|---|---:|
| Tasks | 40 |
| Passed tasks | 40 |
| Failed tasks | 0 |
| Generated mutation canaries graded | 162 |
| Pass canary score range | 1.0 to 1.0 |
| Structural fail canary max score | 0.15 |
| Mutation canary threshold | 0.75 |
| Parallel wall time | 2012 s |
| Sum of per-task runtimes | 5681 s |
| Workers | 3 |

One task, `ef28_badge`, initially staged a missing-outline mutation even though
the reference board has no parsed outline under the benchmark board parser. The
task-pack builder now skips the missing-outline mutation when the parsed
reference has no outline, and the rerun passed.

## Slowest Tasks

| Task | Runtime | Mutation canaries |
|---|---:|---:|
| `jetson_orin_baseboard` | 1252 s | 4 |
| `cm4_baseboard` | 863 s | 4 |
| `cm5io_official` | 249 s | 5 |
| `zynq_som` | 235 s | 4 |
| `ict_baseboard` | 227 s | 4 |
| `cm4_lvds_adapter` | 211 s | 5 |
| `adau1452_dsp_core` | 191 s | 4 |
| `ftdi_toolkit` | 178 s | 4 |
| `core_v_mcu_devkit` | 176 s | 4 |
| `mowi` | 172 s | 4 |

Detailed per-task logs were written to local scratch during the run. They are
intentionally not committed.
