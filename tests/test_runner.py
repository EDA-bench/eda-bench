import pytest

from bench.provenance import HFProvenanceStore, _hf_retry_delay_seconds, _should_skip_snapshot
from bench.runner import (
    _json_serializable,
    _materialize_runtime_task_dir,
    _prune_task_bundle,
    _safe_rmtree,
    _select_tasks,
    _write_model_artifacts,
    summarize_harness,
)
from harnesses.utils import AgentRunResult


def test_materialize_runtime_task_dir_dereferences_symlinks(tmp_path) -> None:
    blob = tmp_path / "blob.txt"
    blob.write_text("task data", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    (source / "prompt.txt").symlink_to(blob)

    target = _materialize_runtime_task_dir(source, tmp_path / "target")

    copied = target / "prompt.txt"
    assert copied.read_text(encoding="utf-8") == "task data"
    assert not copied.is_symlink()


def test_safe_rmtree_uses_docker_cleanup_for_root_owned_files(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "target"
    target.mkdir()

    def fake_rmtree(path):
        raise PermissionError(path)

    def fake_default_container_image():
        return "agent-image"

    def fake_run(cmd, **kwargs):
        assert cmd[:2] == ["docker", "run"]
        assert "agent-image" in cmd
        target.rmdir()
        return type("Proc", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr("bench.runner.shutil.rmtree", fake_rmtree)
    monkeypatch.setattr("bench.runner.default_container_image", fake_default_container_image)
    monkeypatch.setattr("bench.runner.subprocess.run", fake_run)

    _safe_rmtree(target)

    assert not target.exists()


def test_safe_rmtree_warns_when_cleanup_fails(tmp_path, monkeypatch, capsys) -> None:
    target = tmp_path / "target"
    target.mkdir()

    def fake_rmtree(path):
        raise PermissionError(path)

    def fake_default_container_image():
        return "agent-image"

    def fake_run(cmd, **kwargs):
        return type(
            "Proc",
            (),
            {"returncode": 1, "stderr": "cleanup unavailable", "stdout": ""},
        )()

    monkeypatch.setattr("bench.runner.shutil.rmtree", fake_rmtree)
    monkeypatch.setattr("bench.runner.default_container_image", fake_default_container_image)
    monkeypatch.setattr("bench.runner.subprocess.run", fake_run)

    _safe_rmtree(target)

    assert target.exists()
    assert "warning: failed to remove" in capsys.readouterr().err


def test_prune_task_bundle_removes_generated_dependency_dirs(tmp_path) -> None:
    task_root = tmp_path / "task"
    keep_file = task_root / "workspace" / "design.kicad_pcb"
    venv_file = task_root / "workspace" / ".venv" / "lib" / "package.py"
    pyc_file = task_root / "workspace" / "__pycache__" / "module.pyc"
    keep_file.parent.mkdir(parents=True)
    venv_file.parent.mkdir(parents=True)
    pyc_file.parent.mkdir(parents=True)
    keep_file.write_text("pcb", encoding="utf-8")
    venv_file.write_text("package", encoding="utf-8")
    pyc_file.write_text("bytecode", encoding="utf-8")

    _prune_task_bundle(task_root)

    assert keep_file.exists()
    assert not (task_root / "workspace" / ".venv").exists()
    assert not (task_root / "workspace" / "__pycache__").exists()


def test_json_serializable_handles_tuple_keys_and_sets() -> None:
    payload = {
        ("connector", 1): {"pins": {3, 1, 2}},
        "path": object(),
    }

    converted = _json_serializable(payload)

    assert converted["('connector', 1)"] == {"pins": [1, 2, 3]}
    assert isinstance(converted["path"], str)


def test_write_model_artifacts_can_omit_large_transcripts(tmp_path) -> None:
    result = AgentRunResult(
        response="done",
        error=None,
        stdout='{"type":"event","payload":"large"}\n',
        stderr="stderr text",
        returncode=0,
        command=["agent"],
        session_id="session",
        usage={"tokens": 1},
        parsed_events=[{"type": "event", "payload": "large"}],
    )

    summary = _write_model_artifacts(
        stdout_file=tmp_path / "stdout.txt",
        stderr_file=tmp_path / "stderr.txt",
        response_file=tmp_path / "response.txt",
        events_file=tmp_path / "events.jsonl",
        parsed_events_file=tmp_path / "events.parsed.json",
        run_result=result,
        upload_transcripts=False,
    )

    assert summary["enabled"] is False
    assert (tmp_path / "response.txt").read_text(encoding="utf-8") == "done"
    assert "large" not in (tmp_path / "stdout.txt").read_text(encoding="utf-8")
    assert (tmp_path / "stderr.txt").read_text(encoding="utf-8") == ""
    assert "stdout_bytes_omitted" in (tmp_path / "events.jsonl").read_text(
        encoding="utf-8"
    )


def test_select_tasks_filters_requested_ids() -> None:
    task_defs = {"one": "task one", "two": "task two"}  # type: ignore[dict-item]

    assert _select_tasks(task_defs, ["two", "one"]) == ["task two", "task one"]


def test_select_tasks_rejects_unknown_ids() -> None:
    task_defs = {"one": "task one"}  # type: ignore[dict-item]

    with pytest.raises(RuntimeError, match="unknown task id\\(s\\): missing"):
        _select_tasks(task_defs, ["missing"])


def test_summarize_harness_includes_difficulty_breakdown() -> None:
    rows = [
        {"difficulty": "very easy", "metrics": {"overall_score": 1.0}},
        {"difficulty": "easy", "metrics": {"overall_score": 1.0}},
        {"difficulty": "easy", "metrics": {"overall_score": 0.5}},
        {"difficulty": "hard", "metrics": {"overall_score": 0.25}},
        {"difficulty": "extreme", "metrics": {"overall_score": 0.0}},
    ]
    summary = summarize_harness(rows)
    assert summary["task_count"] == 5
    expected_weighted = (
        1.0 * 1.0
        + 1.0 * 1.5
        + 0.5 * 1.5
        + 0.25 * 3.0
        + 0.0 * 5.0
    ) / (1.0 + 1.5 + 1.5 + 3.0 + 5.0)
    assert summary["benchmark_score"] == pytest.approx(expected_weighted)
    assert summary["unweighted_score"] == pytest.approx((1.0 + 1.0 + 0.5 + 0.25 + 0.0) / 5)
    assert list(summary["by_difficulty"]) == ["very easy", "easy", "hard", "extreme"]
    assert summary["by_difficulty"]["very easy"] == pytest.approx(1.0)
    assert summary["by_difficulty"]["easy"] == pytest.approx(0.75)
    assert summary["by_difficulty"]["hard"] == pytest.approx(0.25)
    assert summary["by_difficulty"]["extreme"] == pytest.approx(0.0)
    assert summary["task_count_by_difficulty"] == {
        "very easy": 1,
        "easy": 2,
        "hard": 1,
        "extreme": 1,
    }


def test_provenance_snapshot_excludes_hidden_references(tmp_path) -> None:
    hidden_gold = tmp_path / "tasks" / "example" / "gold" / "reference.kicad_pcb"
    hidden_gold.parent.mkdir(parents=True)
    hidden_gold.write_text("", encoding="utf-8")
    third_party = tmp_path / "third_party" / "upstream_designs" / "board.kicad_pcb"
    third_party.parent.mkdir(parents=True)
    third_party.write_text("", encoding="utf-8")
    runtime_home = tmp_path / ".tmp" / "runtime_homes" / "agent" / "config.toml"
    runtime_home.parent.mkdir(parents=True)
    runtime_home.write_text("", encoding="utf-8")
    public_code = tmp_path / "bench" / "runner.py"
    public_code.parent.mkdir(parents=True)
    public_code.write_text("", encoding="utf-8")

    assert _should_skip_snapshot(hidden_gold, tmp_path)
    assert _should_skip_snapshot(third_party, tmp_path)
    assert _should_skip_snapshot(runtime_home, tmp_path)
    assert not _should_skip_snapshot(public_code, tmp_path)


def test_hf_provenance_store_defaults_to_public() -> None:
    assert HFProvenanceStore.__dataclass_fields__["private"].default is False


def test_hf_retry_delay_parses_rate_limit_messages() -> None:
    exc = RuntimeError("429 Too Many Requests. Retry after 98 seconds")

    assert _hf_retry_delay_seconds(exc) == 103  # type: ignore[arg-type]


def test_hf_retry_delay_retries_server_errors() -> None:
    exc = RuntimeError("500 Internal Server Error")

    assert _hf_retry_delay_seconds(exc) == 60  # type: ignore[arg-type]
