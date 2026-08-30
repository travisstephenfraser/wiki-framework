"""Tests for vault linting."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from obsidian_wiki.lint import lint_vault
from obsidian_wiki.trust import build_trust_ledger, write_trust_ledger


def _page(
    vault: Path,
    relpath: str,
    *,
    title: str | None = None,
    summary: str | None = "Short summary.",
    tags: str = "[test]",
    sources: str = "[manual]",
    created: str = "2026-07-01",
    updated: str = "2026-07-01",
    links: list[str] | None = None,
    include_frontmatter: bool = True,
) -> Path:
    path = vault / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if include_frontmatter:
        lines.extend(
            [
                "---",
                f"title: {title or path.stem}",
                "category: concepts",
                f"tags: {tags}",
                f"sources: {sources}",
                f"created: {created}",
                f"updated: {updated}",
                "base_confidence: 0.80",
                "lifecycle: reviewed",
            ]
        )
        if summary is not None:
            lines.append(f"summary: {summary}")
        lines.append("---")
    lines.append(f"# {title or path.stem}")
    for link in links or []:
        lines.append(f"[[{link}]]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, "-m", "obsidian_wiki.cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_lint_vault_passes_clean_graph(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _page(vault, "index.md", links=["alpha"])
    _page(vault, "log.md", links=["alpha"])
    _page(vault, "hot.md", links=["alpha"])
    _page(vault, "concepts/alpha.md", links=["beta"])
    _page(vault, "concepts/beta.md", links=["alpha"])
    ledger = build_trust_ledger(vault, reviewed_at="2026-07-12T17:38:39+07:00")
    write_trust_ledger(vault / "_meta" / "trust-ledger.json", ledger, vault=vault)

    report = lint_vault(vault)

    assert report["status"] == "pass"
    assert report["findings"]["broken_links"] == []
    assert report["findings"]["missing_frontmatter"] == []


def test_lint_vault_fails_on_broken_links_and_missing_frontmatter(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _page(vault, "concepts/alpha.md", links=["ghost"])
    _page(vault, "concepts/beta.md", include_frontmatter=False)

    report = lint_vault(vault)

    assert report["status"] == "fail"
    assert report["findings"]["broken_links"] == [{"page": "concepts/alpha.md", "target": "ghost"}]
    assert any(item["page"] == "concepts/beta.md" for item in report["findings"]["missing_frontmatter"])


def test_lint_vault_warns_on_duplicates_missing_summaries_and_orphans(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _page(vault, "concepts/alpha.md", title="Same Title", summary=None)
    _page(vault, "references/beta.md", title="Same Title")
    ledger = build_trust_ledger(vault, reviewed_at="2026-07-12T17:38:39+07:00")
    write_trust_ledger(vault / "_meta" / "trust-ledger.json", ledger, vault=vault)

    report = lint_vault(vault)

    assert report["status"] == "warn"
    assert report["findings"]["duplicate_titles"]
    assert "concepts/alpha.md" in report["findings"]["missing_summaries"]
    assert "references/beta.md" in report["findings"]["orphan_pages"]


def test_lint_cli_uses_configured_vault_and_strict_mode(tmp_path: Path) -> None:
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    _page(vault, "concepts/alpha.md", summary=None)

    config_dir = home / ".obsidian-wiki"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config").write_text(f'OBSIDIAN_VAULT_PATH="{vault}"\n', encoding="utf-8")
    ledger = build_trust_ledger(vault, reviewed_at="2026-07-12T17:38:39+07:00")
    write_trust_ledger(vault / "_meta" / "trust-ledger.json", ledger)

    proc = _run(home, "lint", "--json", "--strict")

    assert proc.returncode == 1
    data = json.loads(proc.stdout)
    assert data["status"] == "warn"
    assert "concepts/alpha.md" in data["findings"]["missing_summaries"]


def test_lint_vault_parses_escaped_pipe_and_footnote_wrapped_wikilinks(tmp_path: Path) -> None:
    """Regression: table-escaped pipes and footnote-wrapped links are not broken links.

    `[[page\\|Alias]]` is valid Obsidian inside a Markdown table cell, and
    `^[[[page|alias]]]` is a wikilink inside a footnote. Both previously captured a
    malformed target (`page\\` and `[page`) and reported as broken_links, which put a
    standing false-positive floor under every lint run.
    """
    vault = tmp_path / "vault"
    _page(vault, "concepts/alpha.md")
    body = (
        "| col | col |\n"
        "|---|---|\n"
        "| [[alpha\\|Alpha]] | cell |\n\n"
        "Footnote ^[[[alpha#Section|see here]]] inline.\n"
    )
    page = _page(vault, "concepts/beta.md")
    page.write_text(page.read_text() + body, encoding="utf-8")

    report = lint_vault(vault)

    assert report["findings"]["broken_links"] == []


def test_lint_vault_still_reports_genuinely_broken_escaped_link(tmp_path: Path) -> None:
    """The escaped-pipe fix must not blind lint to a real missing target."""
    vault = tmp_path / "vault"
    page = _page(vault, "concepts/alpha.md")
    page.write_text(page.read_text() + "\n| [[ghost\\|Ghost]] |\n", encoding="utf-8")

    report = lint_vault(vault)

    assert {"page": "concepts/alpha.md", "target": "ghost"} in report["findings"]["broken_links"]


# ---------------------------------------------------------------------------
# Link-extraction coverage (mutation-driven)
#
# The two tests above assert an ABSENCE (`broken_links == []`), which any
# under-matching pattern satisfies. Mutation testing proved that inadequate: a
# pattern losing 464 of 3728 real links, one blind to every heading-anchored
# link, and one that drops the `[`-exclusion entirely all passed the full suite.
# These assert PRESENCE — each form must resolve to a specific target — so an
# under-matching pattern fails instead of passing quietly.
# ---------------------------------------------------------------------------

WIKILINK_FORMS = [
    ("plain", "[[ghost]]"),
    ("alias", "[[ghost|Alias]]"),
    ("heading", "[[ghost#Section]]"),
    ("heading+alias", "[[ghost#Section|Alias]]"),
    ("escaped pipe (table)", r"| [[ghost\|Alias]] |"),
    ("escaped pipe + heading", r"[[ghost\|Alias]] and [[ghost#Sec]]"),
    ("footnote-wrapped", "^[[[ghost|see]]]"),
    ("footnote, no alias", "^[[[ghost]]]"),
    ("path-qualified", "[[concepts/ghost]]"),
]


@pytest.mark.parametrize("label,form", WIKILINK_FORMS, ids=[f[0] for f in WIKILINK_FORMS])
def test_every_wikilink_form_resolves_to_its_target(tmp_path: Path, label: str, form: str) -> None:
    """Each form must be extracted AND resolved to `ghost`, so a missing target reports."""
    vault = tmp_path / "vault"
    page = _page(vault, "concepts/alpha.md")
    page.write_text(page.read_text() + "\n" + form + "\n", encoding="utf-8")

    report = lint_vault(vault)

    targets = [b["target"] for b in report["findings"]["broken_links"]]
    assert "ghost" in targets, f"{label}: link not extracted or not resolved -> {targets}"


def test_link_count_is_stable_across_forms(tmp_path: Path) -> None:
    """Total extracted links must equal the number written.

    A pattern that silently drops a form keeps `broken_links` plausible while the
    graph shrinks. This asserts the count directly, which is what an absence
    assertion cannot do.
    """
    vault = tmp_path / "vault"
    _page(vault, "concepts/ghost.md")
    page = _page(vault, "concepts/alpha.md")
    body = "\n".join(form for _, form in WIKILINK_FORMS)
    page.write_text(page.read_text() + "\n" + body + "\n", encoding="utf-8")

    report = lint_vault(vault)

    # 9 forms, one of which ("escaped pipe + heading") contains two links.
    assert report["stats"]["link_count"] == len(WIKILINK_FORMS) + 1
    assert report["findings"]["broken_links"] == []


# ---------------------------------------------------------------------------
# log.md is bookkeeping, not a content page
#
# `log.md` is an append-only activity log whose entries carry free-text
# `note="..."` fields. Those notes quote vault content verbatim -- including
# wikilink syntax -- so lint counted a QUOTED `[[target]]` as a real link and
# reported it broken when the target did not exist. Observed three times on the
# reference vault: the 2026-08-13 LINT entry documenting a `^[[[page#anchor]]]`
# false positive became one, and a 2026-08-29 note describing a repointed
# `[[linkedin-writing]]` link added two more. Lint was reading its own history.
#
# Only `log` is exempt. `index.md`, `hot.md` and `_insights.md` are curated or
# generated CONTENT -- a dangling link in any of them is a real defect (a page
# was renamed and the catalog was not updated), so they must keep reporting.
# ---------------------------------------------------------------------------


def test_quoted_wikilink_in_log_note_is_not_a_broken_link(tmp_path: Path) -> None:
    """A dangling link quoted inside a log note is bookkeeping, not a vault defect."""
    vault = tmp_path / "vault"
    _page(vault, "concepts/alpha.md", links=["ghost"])
    log = _page(vault, "log.md")
    log.write_text(
        log.read_text()
        + '- [2026-08-29T10:00:00-0700] LINT note="repointed [[phantom]] to [[alpha]]"\n',
        encoding="utf-8",
    )

    report = lint_vault(vault)

    targets = [b["target"] for b in report["findings"]["broken_links"]]
    # Presence: a real content page's dangling link still reports, so an
    # over-broad fix that silences broken_links entirely fails here.
    assert "ghost" in targets
    assert "phantom" not in targets


@pytest.mark.parametrize("stem", ["index", "hot", "_insights"])
def test_dangling_links_in_other_reserved_pages_still_report(
    tmp_path: Path, stem: str
) -> None:
    """Only `log` is exempt -- the catalog pages must keep reporting broken links."""
    vault = tmp_path / "vault"
    _page(vault, "concepts/alpha.md")
    _page(vault, f"{stem}.md", links=["phantom"])

    report = lint_vault(vault)

    targets = [b["target"] for b in report["findings"]["broken_links"]]
    assert "phantom" in targets, f"{stem}.md must still report dangling links"


def test_log_still_counts_as_a_link_source_for_orphan_detection(tmp_path: Path) -> None:
    """The exemption covers reporting only; log.md must not stop feeding incoming links.

    Excluding log.md from link extraction outright would inflate the orphan
    count -- the same class of error as excluding index.md, which the vault's
    own history records producing a 70-of-74-orphans report.
    """
    vault = tmp_path / "vault"
    _page(vault, "concepts/alpha.md")
    _page(vault, "log.md", links=["alpha"])

    report = lint_vault(vault)

    orphans = [o["page"] if isinstance(o, dict) else o for o in report["findings"]["orphan_pages"]]
    assert "concepts/alpha.md" not in orphans


# ---------------------------------------------------------------------------
# A wikilink inside code is an illustration, not a reference
#
# Documenting wikilink syntax anywhere in the vault used to create a broken
# link: the extractor scanned raw text, so a double-bracket reference written
# inside backticks to EXPLAIN the syntax was counted as a real link and
# reported broken. Hit three times in one session on 2026-08-29 while writing
# up the log.md exemption -- the page describing the bug reproduced it.
#
# Masking is scoped to the BODY. Frontmatter must keep resolving, because
# `relationships:` targets live there and are real typed edges.
# ---------------------------------------------------------------------------


def test_wikilink_in_inline_code_is_not_a_link(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    page = _page(vault, "concepts/alpha.md", links=["ghost"])
    page.write_text(
        page.read_text() + "\nWriting `[[phantom]]` in prose documents the syntax.\n",
        encoding="utf-8",
    )

    report = lint_vault(vault)

    targets = [b["target"] for b in report["findings"]["broken_links"]]
    # Presence assertion: a real prose link must still report, so an over-broad
    # mask that kills all extraction fails here rather than passing quietly.
    assert "ghost" in targets
    assert "phantom" not in targets


def test_wikilink_in_fenced_code_block_is_not_a_link(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    page = _page(vault, "concepts/alpha.md", links=["ghost"])
    page.write_text(
        page.read_text() + "\n```markdown\n[[phantom]]\n```\n",
        encoding="utf-8",
    )

    report = lint_vault(vault)

    targets = [b["target"] for b in report["findings"]["broken_links"]]
    assert "ghost" in targets
    assert "phantom" not in targets


def test_frontmatter_relationship_targets_still_resolve(tmp_path: Path) -> None:
    """Masking must not reach frontmatter -- typed edges are real links."""
    vault = tmp_path / "vault"
    page = _page(vault, "concepts/alpha.md")
    text = page.read_text().replace(
        "lifecycle: reviewed",
        'lifecycle: reviewed\nrelationships:\n  - target: "[[phantom]]"\n    type: related_to',
    )
    page.write_text(text, encoding="utf-8")

    report = lint_vault(vault)

    targets = [b["target"] for b in report["findings"]["broken_links"]]
    assert "phantom" in targets, "frontmatter relationship target must still be checked"
