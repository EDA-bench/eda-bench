from __future__ import annotations

import json
import os
from pathlib import Path

from tasks.specs import load_task_spec


TASK_ID = os.environ["EDA_BENCH_TASK_ID"]
TASK_ROOT = Path("/opt/eda-bench/dataset") / TASK_ID
SUBMISSION = Path("/workspace/final_project")
VERIFIER_LOGS = Path("/logs/verifier")


def json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def main() -> None:
    VERIFIER_LOGS.mkdir(parents=True, exist_ok=True)
    task = load_task_spec(TASK_ROOT)
    if task.task_id != TASK_ID:
        raise ValueError(f"expected task {TASK_ID}, loaded {task.task_id}")
    evaluation = task.evaluate_project(SUBMISSION, VERIFIER_LOGS / "work")
    result = json_safe(
        {"task_id": TASK_ID, "raw": evaluation.raw, "metrics": evaluation.metrics}
    )
    (VERIFIER_LOGS / "grading.json").write_text(
        json.dumps(result, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    numeric = (
        "reward",
        "overall_score",
        "task_score",
        "build_success",
        "submission_exists",
    )
    rewards = {
        key: float(evaluation.metrics[key])
        for key in numeric
        if isinstance(evaluation.metrics.get(key), (int, float))
        and not isinstance(evaluation.metrics.get(key), bool)
    }
    (VERIFIER_LOGS / "reward.json").write_text(
        json.dumps(rewards, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
