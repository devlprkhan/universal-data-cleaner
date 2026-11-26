"""The documentation website builds at the repository root, without V1."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "v2"))

import build  # noqa: E402  (after sys.path)


def test_site_builds_at_the_root(tmp_path: Path) -> None:
    out = tmp_path / "site"

    assert build.main(out=out) == 0

    assert (out / "index.html").is_file()
    assert (out / "quickstart" / "index.html").is_file()
    assert (out / "api" / "index.html").is_file()
    assert (out / "adr" / "index.html").is_file()
    assert not (out / "v2").exists()


def test_pages_and_assets_use_root_paths(tmp_path: Path) -> None:
    out = tmp_path / "site"
    assert build.main(out=out) == 0

    home = (out / "index.html").read_text(encoding="utf-8")
    assert 'data-base=""' in home
    assert "Docs v1" not in home
    assert 'href="v2/' not in home
    assert (
        '<link rel="canonical" '
        'href="https://devlprkhan.github.io/universal-data-cleaner/"'
    ) in home

    search = (out / "assets" / "search-index.js").read_text(encoding="utf-8")
    assert '"href": "./"' in search
    assert '"href": "quickstart/"' in search
    assert '"href": "v2/' not in search

    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert (
        "<loc>https://devlprkhan.github.io/universal-data-cleaner/</loc>"
    ) in sitemap
    assert "/v2/" not in sitemap


def test_api_page_is_generated_from_the_package(tmp_path: Path) -> None:
    out = tmp_path / "site"
    assert build.main(out=out) == 0

    api = (out / "api" / "index.html").read_text(encoding="utf-8")
    assert 'id="data_cleaner.DataCleaner"' in api
    assert 'id="data_cleaner.DataCleaner.fit"' in api
    assert 'id="data_cleaner.read_csv_safe"' in api
    assert "doc-signature" in api
    assert "Unknown API object" not in api
    assert "Parameters:" in api


def test_v1_docs_are_retired() -> None:
    assert not (ROOT / "docs").exists()
    assert not (ROOT / "mkdocs.yml").exists()
