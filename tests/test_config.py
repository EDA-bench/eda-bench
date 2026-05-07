from pathlib import Path

import pytest

from bench.config import env_flag, env_positive_float


def test_env_flag_reads_boolean_values(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "ENABLED=yes\nDISABLED=0\n",
        encoding="utf-8",
    )

    assert env_flag("ENABLED", root=tmp_path)
    assert not env_flag("DISABLED", root=tmp_path)
    assert env_flag("MISSING_TRUE", default=True, root=tmp_path)
    assert not env_flag("MISSING_FALSE", default=False, root=tmp_path)


def test_env_flag_rejects_unknown_values(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("FLAG=maybe\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="FLAG must be a boolean-like value"):
        env_flag("FLAG", root=tmp_path)


def test_env_positive_float_reads_optional_value(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TIMEOUT=12.5\n", encoding="utf-8")

    assert env_positive_float("TIMEOUT", root=tmp_path) == 12.5
    assert env_positive_float("MISSING", root=tmp_path) is None


def test_env_positive_float_rejects_invalid_values(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TIMEOUT=0\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="TIMEOUT must be a positive number"):
        env_positive_float("TIMEOUT", root=tmp_path)
