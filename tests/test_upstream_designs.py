from tasks.kicad_common import load_board_model
from tasks.source_backed_task import build_external_io_signature
from tasks.source_backed_tasks import load_source_backed_task_catalog
from tasks.specs import load_all_task_specs


def _catalog_for(task_id: str):
    task = load_all_task_specs()[task_id]
    return load_source_backed_task_catalog(
        path=task.task_dir / "tasks" / "source_backed_tasks.toml",
        include_disabled=True,
    )


def test_source_backed_task_catalog_is_actionable() -> None:
    catalog = _catalog_for("nanoupdi")
    assert catalog.strategy
    assert catalog.vendor_root.exists()
    assert catalog.tasks
    source_keys = catalog.sources_by_key()
    for task in catalog.tasks:
        assert task.task_id
        assert task.source.key in source_keys
        assert task.reference_project_dir.exists()
        assert task.reference_schematic.exists()
        assert task.reference_board.exists()
        assert task.notes


def test_source_backed_sources_are_vendored_and_attributable() -> None:
    catalog = _catalog_for("nanoupdi")
    assert catalog.sources
    active_source_keys = {task.source.key for task in catalog.tasks if task.enabled}
    for source in catalog.sources:
        if source.key not in active_source_keys:
            continue
        assert source.name
        assert source.repo_url.startswith("https://")
        assert source.commit
        assert len(source.commit) == 40 or source.commit.startswith("RP-")
        assert source.vendored_root.exists()
        assert source.readme_path.exists()
        assert source.license_path is not None
        assert source.license_path.exists()


def test_curated_canary_removed_references_are_boundary_refs() -> None:
    catalog = _catalog_for("nanoupdi")
    for task in catalog.tasks:
        if not task.canary_removed_references:
            continue
        board = load_board_model(task.reference_board)
        boundary_refs = {ref.reference for ref in build_external_io_signature(board).boundary_refs}
        assert set(task.canary_removed_references) <= boundary_refs


def test_curated_canary_ignored_references_are_not_boundary_refs_and_are_dense() -> None:
    catalog = _catalog_for("nanoupdi")
    for task in catalog.tasks:
        board = load_board_model(task.reference_board)
        boundary_refs = {ref.reference for ref in build_external_io_signature(board).boundary_refs}
        board_refs = set(board.footprints)
        assert len(task.canary_ignored_references) >= 10
        assert set(task.canary_ignored_references) <= board_refs
        assert set(task.canary_ignored_references).isdisjoint(boundary_refs)
