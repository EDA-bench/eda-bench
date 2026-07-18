# EDA-bench

EDA-bench is a native [Harbor](https://www.harborframework.com/) dataset for evaluating agents on complete KiCad project construction. The repository contains the benchmark itself; Harbor supplies agent adapters, model configuration, sandbox lifecycle, retries, concurrency, trajectories, artifacts, result storage, and result inspection.

The active dataset is [`dataset/`](dataset). It contains 35 self-contained Harbor tasks and one benchmark-specific aggregate metric. There is no separate benchmark runner, provider harness, provenance uploader, or task download layer.

## Install Harbor

The dataset is validated against Harbor 0.19.0:

```bash
uv tool install 'harbor==0.19.0'
```

Docker must be available for local runs. Until the versioned images are published, build the shared agent and verifier images once:

```bash
./images/build.sh
```

Every task then runs independently with ordinary Harbor using the image references in its own `task.toml`.

## Run the benchmark

Run the complete local dataset with any Harbor-supported agent and model:

```bash
harbor run \
  --path dataset \
  --agent '<agent>' \
  --model '<model>' \
  --n-concurrent 4
```

Run one task while developing:

```bash
harbor run \
  --path dataset/usb_c_female_breakout \
  --agent '<agent>' \
  --model '<model>'
```

Run an oracle smoke test without configuring a model:

```bash
harbor run --path dataset/usb_c_female_breakout --agent oracle
```

Harbor writes jobs to `jobs/` by default. Each trial includes its resolved configuration, trajectory, verifier output, declared `final_project` artifact, and reward. Inspect them with:

```bash
harbor view jobs
```

## Task contract

Each task asks the agent to create a complete KiCad project under:

```text
/workspace/final_project/
```

The task instruction names the required `.kicad_pro`, `.kicad_sch`, and `.kicad_pcb` files. The agent environment includes KiCad and ngspice.

Grading runs in Harbor's `separate` verifier mode with networking disabled. Harbor stops the agent environment, transfers only the declared `/workspace/final_project` artifact, and starts the shared verifier image named in `task.toml`. The verifier evaluates the submitted schematic, PCB, connectivity, external I/O behavior, physical realization, ERC/DRC results, and task-specific functional contract. It writes:

- `reward.json`: Harbor reward channels (`reward`, `overall_score`, `task_score`, `build_success`, and `submission_exists`)
- `grading.json`: the complete deterministic grading record
- `work/`: generated ERC, DRC, and ngspice evidence

The verifier image contains the task reference project and scoring code. Those files are never mounted into the agent environment.

## Dataset layout

```text
dataset/
├── dataset.toml                 # Harbor dataset manifest and exact task digests
├── metric.py                    # difficulty-weighted benchmark aggregation
└── <task_id>/
    ├── instruction.md
    ├── task.toml                # Harbor schema, image refs, task selector
    ├── environment/             # required Harbor directory; image is prebuilt
    ├── contract/                # task-specific static and functional I/O data
    └── solution/                # Harbor oracle and sole reference project

images/                          # one agent image and one verifier image
verifier/                        # one shared KiCad evaluator implementation
```

`dataset/` owns task-specific data, `verifier/` owns shared scoring logic, and `images/` owns container dependencies. Rebuild the images and refresh the manifest after changing any of them:

```bash
harbor sync dataset
git diff -- dataset/dataset.toml
```

The custom metric preserves the benchmark's difficulty-weighted score: task rewards are weighted 1.0 for very easy, 1.5 for easy, 2.0 for medium, 3.0 for hard, 4.0 for very hard, and 5.0 for extreme. Missing rewards count as zero.

## Publishing later

Publishing is intentionally separate from development. When a release is approved, authenticate to the Harbor registry, verify the manifest is clean, and publish the public dataset:

```bash
harbor auth login
harbor auth status
harbor sync dataset
harbor publish dataset --public --tag '<version>'
```

Until a registry release exists, use `--path dataset`; do not use a registry dataset name.

## Research artifacts

The paper and `artifacts/` reports are retained research records. They are not executable benchmark infrastructure. New evaluations should use Harbor job results as the canonical run record.

See [`DATA_CARD.md`](DATA_CARD.md) for scope, access policy, grading details, licensing, and limitations.
