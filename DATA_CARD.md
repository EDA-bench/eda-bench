# EDA-bench dataset card

## Summary

EDA-bench measures whether an agent can turn an engineering brief into a complete, internally consistent KiCad project. The Harbor dataset contains 35 tasks based on real PCB designs. Tasks span small breakouts through carrier boards and systems-on-module designs.

- Dataset directory: `dataset/`
- Harbor dataset name: `eda-bench/eda-bench`
- Harbor task schema: 1.3
- Required submission: `/workspace/final_project`
- Primary reward: `overall_score` in `[0, 1]`
- Aggregate metric: difficulty-weighted mean, with missing trials scored as zero

The dataset has not been published to the Harbor registry in this working copy. Local runs use `harbor run --path dataset`.

## What an agent receives

An agent receives only the task instruction and an isolated Debian Trixie environment containing KiCad 9, ngspice, Python, and ordinary command-line development tools. The task declares public network access during the agent phase, matching the benchmark's public-source reconstruction setting.

The agent does not receive the verifier image, reference project, functional contract, static I/O contract, or grading code.

## Submission format

Every task requires a directory at `/workspace/final_project` containing the specifically named:

- KiCad project file (`.kicad_pro`)
- schematic (`.kicad_sch`)
- PCB (`.kicad_pcb`)

The prompt describes the electrical interfaces, components, geometry, routing, power integrity, and completion criteria for the design.

## Verification

Harbor runs each verifier in a separate, no-network container. Only the declared final project artifact crosses from the agent environment into that container. The shared versioned verifier selects the task-specific contract and reference behavior named by `task.toml` and evaluates:

- required project files and parseability
- schematic and PCB connectivity
- external interface realization
- task-specific functional I/O contracts
- ngspice behavioral and geometry-derived simulations
- component-function realization
- power and short-circuit safety checks
- board outline, placement, routing, and fabrication geometry
- KiCad ERC and DRC evidence
- schematic/PCB consistency

The verifier emits a scalar `reward` and matching `overall_score`, plus diagnostic reward channels and a complete `grading.json` record. Harbor stores these with the trial instead of relying on a benchmark-specific provenance service.

## Aggregation

`dataset/metric.py` applies the benchmark's established per-task difficulty weights:

| Difficulty | Weight |
|---|---:|
| Very easy | 1.0 |
| Easy | 1.5 |
| Medium | 2.0 |
| Hard | 3.0 |
| Very hard | 4.0 |
| Extreme | 5.0 |

Scores are clamped to `[0, 1]`. Missing or failed trials contribute zero. The output includes `benchmark_score` and an unweighted mean for each represented difficulty tier.

## Provenance and licensing

Every Harbor task records the upstream repository URL, pinned source commit, source license, and project stem in its `[metadata]` table. The isolated verifier uses that metadata with the task's sole reference project for deterministic grading.

The benchmark code and task wrappers do not transfer ownership of upstream hardware designs. Redistribution of a task includes its embedded reference design, so each task must remain subject to its recorded upstream license and attribution requirements. See [`LICENSES.md`](LICENSES.md).

## Intended use

EDA-bench is intended for:

- evaluating tool-using agents on end-to-end PCB design
- comparing agents, models, prompts, and access policies under the same Harbor task revision
- error analysis using saved Harbor trajectories, artifacts, and verifier evidence
- producing rollout data for agent improvement

Comparisons should report the exact dataset digest or registry version, agent, model, Harbor version, number of attempts, network policy, and aggregate metric.

## Limitations

- The default agent environment permits public network access; results are not a closed-book memorization test.
- Public upstream designs may be discoverable independently of the benchmark.
- Automated KiCad, geometric, and simulation checks are useful engineering proxies, not manufacturing certification.
- A high score does not guarantee regulatory compliance, electromagnetic compatibility, safety certification, component availability, or successful fabrication.
- Scores are tied to the task-specific reference behavior and exact shared verifier image reference.
