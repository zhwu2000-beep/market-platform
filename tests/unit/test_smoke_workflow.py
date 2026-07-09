from __future__ import annotations

from pathlib import Path


def test_twelve_data_smoke_script_exists() -> None:
    script_path = Path("scripts") / "smoke_twelve_data.ps1"
    script_text = script_path.read_text(encoding="utf-8")

    assert script_path.exists()
    assert "TWELVE_DATA_API_KEY" in script_text
    assert "providers" in script_text
    assert "health" in script_text
    assert "data" in script_text
    assert "fetch" in script_text
    assert "latest" in script_text
    assert "intraday" in script_text
    assert "--cache" in script_text


def test_smoke_docs_reference_release_workflow() -> None:
    docs_path = Path("docs") / "smoke.md"
    docs_text = docs_path.read_text(encoding="utf-8")

    assert "uv run ruff check src tests" in docs_text
    assert "uv run mypy src" in docs_text
    assert "uv run pytest --basetemp" in docs_text
    assert "TWELVE_DATA_API_KEY" in docs_text
    assert "--cache --refresh" in docs_text
    assert ".market-platform/cache/" in docs_text
    assert "tmp\\smoke_twelve_data\\" in docs_text
