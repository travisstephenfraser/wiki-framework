"""Fork-local: the hub-contract rule must stay in every skill that writes project pages.

The rule exists because the skills' fold gate ("default to folding into an existing hub") is
what grew one project hub to 1,300+ lines. Upstream does not carry this text, so an upstream
merge that resolves a SKILL.md toward upstream silently restores the regrowth path. This test
fails that merge in CI (fork-guard job) instead of letting it land.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent / ".skills"
MARKER = "Hub contract (fork-local)"

WRITERS = [
    "wiki-update",
    "wiki-ingest",
    "wiki-capture",
    "wiki-research",
    "wiki-agent",
    "wiki-synthesize",
    "wiki-import",
    "wiki-lint",
    "cross-linker",
    "wiki-dedup",
    "claude-history-ingest",
    "codex-history-ingest",
    "hermes-history-ingest",
    "openclaw-history-ingest",
    "copilot-history-ingest",
    "pi-history-ingest",
]


def _skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def test_canonical_rule_lives_in_llm_wiki() -> None:
    text = _skill("llm-wiki")
    assert "### Hub contract (fork-local)" in text
    for phrase in (
        "Never fold into the hub.",
        "Replace Current state; never stack it.",
        "No dated sections on the hub",
        "unless the parent is a contracted hub",
    ):
        assert phrase in text, phrase


@pytest.mark.parametrize("name", WRITERS)
def test_every_writer_points_at_the_contract(name: str) -> None:
    text = _skill(name)
    assert MARKER in text
    assert "never add a dated section" in text


@pytest.mark.parametrize(
    "name,phrase",
    [
        ("wiki-update", "Exception: never merge into a contracted hub"),
        (
            "wiki-ingest",
            "do not add a subsection: route by its `## Maintenance contract`",
        ),
        ("cross-linker", "make link-only edits"),
        ("wiki-dedup", "two pages that both derive from the same contracted hub"),
    ],
)
def test_writer_specific_rules(name: str, phrase: str) -> None:
    assert phrase in _skill(name)
