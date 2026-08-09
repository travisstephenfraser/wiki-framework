"""Fork-local invariant: `_meta` and `_generated-skills` stay out of trust and lint scope.

This lives in its own file ON PURPOSE. It was previously the last test in
``tests/test_trust.py``, which arrives as an add/add conflict on every upstream merge —
so resolving that file toward upstream deleted the guard in the same motion that deleted
the thing it guards. Guard and guarded must not share a conflict hunk.

The invariant (fork commit ``bb44412``): both ``lint.SKIP_DIRS`` and
``trust.TRUST_SKIP_DIRS`` include ``_meta`` and ``_generated-skills``. Upstream carries
neither. Without them, a real vault reports ``missing_frontmatter`` and
``trust_metadata_errors`` for schema worktables and generated skill bundles — findings
that sit OUTSIDE the ``strict_trust`` gate, so no configuration can relax them — and
``build_trust_ledger`` raises outright, aborting ``trust-record --all``.

After any upstream merge, both tests here must pass. Removing the exclusion from either
module alone must fail; before this file existed, removing it from ``lint.py`` alone
passed the entire suite.
"""

from __future__ import annotations

from pathlib import Path

from obsidian_wiki.lint import SKIP_DIRS, lint_vault
from obsidian_wiki.trust import (
    TRUST_SKIP_DIRS,
    build_trust_ledger,
    check_trust_ledger,
    write_trust_ledger,
)

FORK_SCOPED_DIRS = ("_meta", "_generated-skills")


def _seed(vault: Path) -> None:
    """A real page, plus the two shapes that break scanners when scope is wrong."""
    page = vault / "concepts" / "real-page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\n"
        "title: Real Page\n"
        "category: concepts\n"
        "tags: [test]\n"
        "sources: [manual]\n"
        "summary: A real page.\n"
        "created: 2026-07-01\n"
        "updated: 2026-07-12T17:38:39+07:00\n"
        "base_confidence: 0.8\n"
        "lifecycle: draft\n"
        "---\n"
        "# Real Page\n",
        encoding="utf-8",
    )
    # A schema worktable: no frontmatter at all.
    meta = vault / "_meta" / "taxonomy.md"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text("# Tag Taxonomy\nno frontmatter at all\n", encoding="utf-8")
    # A generated skill bundle: frontmatter that is not a wiki page's frontmatter.
    generated = vault / "_generated-skills" / "some-skill" / "SKILL.md"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text("---\nname: some-skill\n---\n# Skill\n", encoding="utf-8")


def test_fork_scoped_dirs_are_declared_in_both_modules() -> None:
    """Cheap tripwire: a merge that drops either constant fails here first."""
    for name in FORK_SCOPED_DIRS:
        assert name in SKIP_DIRS, f"lint.SKIP_DIRS lost {name!r}"
        assert name in TRUST_SKIP_DIRS, f"trust.TRUST_SKIP_DIRS lost {name!r}"


def test_fork_scoped_dirs_excluded_from_trust_scope(tmp_path: Path) -> None:
    _seed(tmp_path)

    ledger = build_trust_ledger(tmp_path, reviewed_at="2026-07-14T12:00:00-07:00")
    recorded = set(ledger["pages"])
    assert "concepts/real-page.md" in recorded
    assert not any(
        p.startswith(tuple(f"{d}/" for d in FORK_SCOPED_DIRS)) for p in recorded
    )

    write_trust_ledger(tmp_path / "_meta" / "trust-ledger.json", ledger, vault=tmp_path)
    report = check_trust_ledger(tmp_path)
    assert not any(
        any(d in str(entry) for d in FORK_SCOPED_DIRS) for entry in report["errors"]
    ), report["errors"]


def test_fork_scoped_dirs_excluded_from_lint_scope(tmp_path: Path) -> None:
    """The half that had no coverage: removing the exclusion from lint.py alone
    previously passed the entire suite."""
    _seed(tmp_path)

    report = lint_vault(tmp_path)

    for bucket in ("missing_frontmatter", "missing_summaries", "orphan_pages"):
        offenders = [
            item
            for item in report["findings"].get(bucket, [])
            if any(d in str(item) for d in FORK_SCOPED_DIRS)
        ]
        assert offenders == [], f"{bucket} leaked fork-scoped dirs: {offenders}"
