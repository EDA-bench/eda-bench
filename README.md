# EDA Bench

EDA Bench is a reproducible benchmark harness for evaluating web-enabled agents
that produce KiCad PCB projects. The code runs model harnesses in a pinned Docker
environment, downloads frozen task packs from Hugging Face, grades submitted
KiCad projects with explicit I/O simulation oracles, and uploads run provenance.

This repository contains the public benchmark code artifact, paper PDF, and
small media/result artifacts. The task dataset and dataset metadata live on
Hugging Face at
[`oof-baroomf/eda-bench-tasks`](https://huggingface.co/datasets/oof-baroomf/eda-bench-tasks).
This repository does not vendor reference PCB projects, task-pack archives,
grading answers, or duplicate dataset metadata.

## Contents

- `bench/`: runner, environment loading, provenance upload, and accounting
- `harnesses/`: Codex CLI and Pi coding-agent harness definitions
- `tasks/`: task-pack loading, source-backed task specs, and oracle code
- `tests/`: regression tests for packaging, configuration, harnesses, runner,
  task loading, and website generation
- `website/`: static leaderboard generation from uploaded provenance
- `tasks/task_pack_manifest.json`: pinned Hugging Face task-pack revision used
  by the released code
- `paper/main.pdf`: public paper PDF only; LaTeX sources are intentionally not
  included in this repository
- `artifacts/`: small public media/result artifacts used by the paper

Dataset metadata such as `DATA_CARD.md`, `croissant.json`, and
`task_catalog.json` is kept in the Hugging Face dataset, not duplicated here.

## Reproducible Setup

Install dependencies with the checked-in lockfile:

```bash
uv sync --dev
```

Build the agent execution image:

```bash
docker build -t eda-bench-agent .
```

Create `.env` from `.env.example` and set the required private credentials for
the harnesses you intend to run. At minimum, a Codex run needs:

- `EDA_BENCH_AGENT_IMAGE=eda-bench-agent`
- `HF_PROVENANCE_REPO_ID`
- `HF_TOKEN`
- `CODEX_AUTH_JSON_B64`

The task packs are resolved from `tasks/task_pack_manifest.json`. That manifest
pins:

- dataset repo: `oof-baroomf/eda-bench-tasks`
- task-pack revision: `38bad28072e5c09657ef15fd56f9eb24841eaa48`
- runtime path prefix: `task-packs/v2`
- full grader path prefix: `full-task-packs/v2`

## Basic Checks

Run the test suite:

```bash
uv run pytest -q
```

List available harnesses and tasks:

```bash
uv run list-harnesses
uv run list-tasks
```

Run a single-task smoke evaluation:

```bash
uv run eval-harness \
  --harness harnesses/codex/harnesses.py:gpt_5_5_web_high \
  --task-id usb_c_female_breakout
```

Run the built-in matrix:

```bash
uv run eval-matrix
```

Refresh the static website from uploaded provenance:

```bash
uv run update-website
```

## Reproducibility Notes

The released code intentionally separates executable benchmark code from task
artifacts. Evaluated agents receive only the runtime task pack for each task.
Full grader packs, reference projects, canaries, contracts, and source snapshots
are downloaded by the benchmark code for grading and auditability; they are not
vendored in this repository or mounted into evaluated agent runtimes.

Every run records the task-pack revision, local git commit, Docker image/tool
versions, prompts, command lines, stdout/stderr, final projects, grading
artifacts, and accounting summaries in the configured Hugging Face provenance
dataset. Set `EDA_BENCH_UPLOAD_MODEL_TRANSCRIPTS=0` to replace raw model
transcripts with byte-count summaries, and set
`EDA_BENCH_UPLOAD_CONTAINER_IMAGES=0` to skip large Docker image tar uploads.

Scores are produced by explicit I/O simulation only. The current public task set
uses an ngspice PCB-geometry plus behavioral transient I/O oracle. Reference
designator matching, exact component inventory, footprint similarity, route
shape, and outline similarity are diagnostic outputs, not primary scoring
signals.

The default benchmark is open-book: the built-in web harnesses may discover
public upstream hardware projects. Results should therefore be interpreted as
web-enabled task performance under fixed prompts, tooling, task-pack revision,
and recorded provenance.
