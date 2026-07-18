# /// script
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
from pathlib import Path


DIFFICULTIES = ['very hard', 'easy', 'hard', 'hard', 'extreme', 'hard', 'hard', 'very hard', 'extreme', 'hard', 'very hard', 'hard', 'medium', 'extreme', 'extreme', 'easy', 'hard', 'very hard', 'very hard', 'very easy', 'hard', 'hard', 'very hard', 'easy', 'hard', 'very hard', 'easy', 'hard', 'hard', 'medium', 'medium', 'medium', 'very easy', 'easy', 'extreme']
WEIGHTS = {'very easy': 1.0, 'easy': 1.5, 'medium': 2.0, 'hard': 3.0, 'very hard': 4.0, 'extreme': 5.0}


def main(input_path: Path, output_path: Path) -> None:
    rewards = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines()]
    if len(rewards) != len(DIFFICULTIES):
        raise ValueError(f"expected {len(DIFFICULTIES)} task rewards, got {len(rewards)}")
    scores: list[float] = []
    weights: list[float] = []
    grouped: dict[str, list[float]] = {difficulty: [] for difficulty in WEIGHTS}
    for difficulty, reward in zip(DIFFICULTIES, rewards, strict=True):
        score = 0.0 if reward is None else float(reward.get("overall_score", reward.get("reward", 0.0)))
        score = max(0.0, min(1.0, score))
        weight = WEIGHTS[difficulty]
        scores.append(score * weight)
        weights.append(weight)
        grouped[difficulty].append(score)
    benchmark_score = sum(scores) / sum(weights) if weights else 0.0
    output = {"benchmark_score": benchmark_score}
    output.update({
        f"{difficulty}_score": sum(values) / len(values)
        for difficulty, values in grouped.items()
        if values
    })
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input-path", type=Path, required=True)
    parser.add_argument("-o", "--output-path", type=Path, required=True)
    args = parser.parse_args()
    main(args.input_path, args.output_path)
