from tasks.specs import load_all_task_specs
from website.update_website import ImportedReport, _report_is_publishable

ACTIVE_TASK_IDS = sorted(load_all_task_specs())


def _report_with_rows(rows: list[dict[str, object]]) -> ImportedReport:
    return ImportedReport(
        report={
            "harness": {"id": "codex/test"},
            "benchmark_task_count": len(ACTIVE_TASK_IDS),
            "tasks": ACTIVE_TASK_IDS,
            "rows": rows,
        },
        run_name="run",
        source_path="hf://repo/run/report.json",
    )


def test_report_is_publishable_for_clean_rows() -> None:
    assert _report_is_publishable(
        _report_with_rows(
            [
                {
                    "task_id": task_id,
                    "error": None,
                    "grader_error": None,
                    "provenance_error": None,
                    "metrics": {"overall_score": 0.5},
                }
                for task_id in ACTIVE_TASK_IDS
            ]
        )
    )


def test_report_is_not_publishable_for_row_errors() -> None:
    assert not _report_is_publishable(
        _report_with_rows(
            [
                {
                    "task_id": task_id,
                    "error": "codex exit 1",
                    "grader_error": None,
                    "provenance_error": None,
                }
                for task_id in ACTIVE_TASK_IDS
            ]
        )
    )


def test_report_is_not_publishable_for_grader_or_provenance_errors() -> None:
    assert not _report_is_publishable(
        _report_with_rows(
            [
                {
                    "task_id": task_id,
                    "error": None,
                    "grader_error": "ValueError: bad task",
                    "provenance_error": None,
                }
                for task_id in ACTIVE_TASK_IDS
            ]
        )
    )
    assert not _report_is_publishable(
        _report_with_rows(
            [
                {
                    "task_id": task_id,
                    "error": None,
                    "grader_error": None,
                    "provenance_error": "missing uploaded post-run container image",
                }
                for task_id in ACTIVE_TASK_IDS
            ]
        )
    )


def test_report_is_not_publishable_for_partial_runs() -> None:
    assert not _report_is_publishable(
        _report_with_rows(
            [
                {
                    "task_id": ACTIVE_TASK_IDS[0],
                    "error": None,
                    "grader_error": None,
                    "provenance_error": None,
                    "metrics": {"overall_score": 1.0},
                }
            ]
        )
    )
