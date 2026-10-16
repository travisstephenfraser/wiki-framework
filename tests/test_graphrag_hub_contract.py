"""Fork-local: graph-query must not answer from a contracted hub's summary alone.

Kept out of tests/test_graphrag.py on purpose (that file is upstream's; a guard that shares
a conflict hunk with what it guards gets deleted in the same merge resolution).

Before the patch, any question containing the hub's title scored >= 10 on the hub and set
``index_only`` with an empty ``should_read``, so the answer came from the hub's summary.
Measured on the real vault (2026-10-15): 12 of 13 real past project queries took that path.
"""

from __future__ import annotations

from pathlib import Path

from obsidian_wiki.graphrag import build_index, query


def _page(vault: Path, name: str, front: str, body: str = "") -> None:
    (vault / f"{name}.md").write_text(
        f"---\n{front}\n---\n# {name}\n{body}\n", encoding="utf-8"
    )


def _vault(tmp_path: Path, *, contracted: bool) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    flag = "hub_contract: 1\n" if contracted else ""
    _page(
        v,
        "demo",
        f"title: Demo\nsummary: Hub; pricing lives on demo-strategy.\ntier: core\n{flag}".rstrip(),
        "[[demo-strategy]] [[demo-engineering]] [[demo-log-2026-10]]",
    )
    _page(
        v,
        "demo-strategy",
        "title: Demo strategy\nsummary: Pricing tiers and positioning.",
    )
    _page(
        v,
        "demo-engineering",
        "title: Demo engineering\nsummary: Architecture and design.",
    )
    _page(
        v,
        "demo-log-2026-10",
        "title: Demo log — October 2026 (2026-10)\nsummary: October records.",
    )
    return v


def test_index_records_the_flag(tmp_path: Path) -> None:
    idx = build_index(_vault(tmp_path, contracted=True))
    assert idx["demo"]["hub_contract"] is True
    assert idx["demo-strategy"]["hub_contract"] is False


def test_contracted_hub_routes_to_pages(tmp_path: Path) -> None:
    r = query(_vault(tmp_path, contracted=True), "demo pricing")
    assert r["candidates"][0]["page"] == "demo.md"  # the hub still ranks first
    assert r["index_only"] is False
    assert r["should_read"], "a contracted hub must never yield an empty reading list"
    assert "demo-strategy.md" in r["should_read"]


def test_contracted_hub_is_read_for_its_current_state(tmp_path: Path) -> None:
    # The hub holds the one Current state snapshot and is budget-capped, so it is read, first,
    # alongside the best topic pages. Excluding it lost current-state facts on real queries
    # (rubrica split G10, 2026-10-16: two facts PRESENT in both baselines fell to PARTIAL in both
    # split runs, each on a question whose top candidate was the hub).
    r = query(_vault(tmp_path, contracted=True), "demo pricing", max_should_read=3)
    assert r["should_read"][0] == "demo.md"
    assert len(r["should_read"]) <= 3
    assert sum(p == "demo.md" for p in r["should_read"]) == 1


def test_uncontracted_behaviour_unchanged(tmp_path: Path) -> None:
    # Control: the same vault without the flag keeps upstream's index-only behaviour.
    r = query(_vault(tmp_path, contracted=False), "demo pricing")
    assert r["candidates"][0]["page"] == "demo.md"
    assert r["index_only"] is True
    assert r["should_read"] == []


def test_quoted_flag_agrees_with_the_checker(tmp_path: Path) -> None:
    from obsidian_wiki.hub_contract import frontmatter_value

    v = tmp_path / "vault"
    v.mkdir()
    _page(v, "demo", 'title: Demo\nsummary: Hub.\nhub_contract: "1"')
    assert build_index(v)["demo"]["hub_contract"] is True
    assert frontmatter_value('hub_contract: "1"', "hub_contract") == "1"


def test_hub_as_only_candidate_still_yields_a_reading_list(tmp_path: Path) -> None:
    v = tmp_path / "vault"
    v.mkdir()
    _page(v, "demo", "title: Demo\nsummary: Hub.\ntier: core\nhub_contract: 1")
    r = query(v, "demo")
    assert r["index_only"] is False
    assert r["should_read"] == ["demo.md"]
