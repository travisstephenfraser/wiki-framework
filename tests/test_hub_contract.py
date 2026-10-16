"""Hub contract checker (fork-local; pinned in the fork-guard CI job).

Every rule has a planted violation that must fail and a clean fixture that must pass, so
a rule that silently stops firing turns this file red. Fixtures are synthetic on purpose:
this repository is public and must never carry real vault content.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from obsidian_wiki import hub_contract as hc

MODULE = Path(hc.__file__)

HUB = """---
title: Demo
category: project
hub_contract: 1
summary: >-
    Demo hub.
---
# Demo

Demo is a synthetic project.

## Current state

### State as of 2026-10-15 (shipping)

Shipped the thing. **Ruling 2026-10-15:** keep it.

## Scale as of 2026-09-30

Forty widgets.

## Related

- [[demo-topic]] — topics
- [[demo-log-2026-10]] — October log
- [[old]] — frozen older page

## Maintenance contract

Records go to the month log; topics go to their page.
"""

TOPIC = """---
title: Demo topic
---
# Demo topic

## Phase 3: Cutover (2026-05-03 → 2026-05-18)

Why we self-host.

### Gotchas

A detail.

## Ask Rubi — in-UI assistant (v1)

Paragraph with a block id. ^ip-basis

## Duplicate

first

## Duplicate

second
"""

LOG = """---
title: Demo log — October 2026 (2026-10)
---
# Demo log — October 2026

## State as of 2026-10-14 (prior)

Earlier status.
"""

OLD = """---
title: Old
---
# Old

## 2026-01-05 — Kickoff

Started.
"""

LINKER = """---
title: Linker
---
See [[demo-topic#Phase 3 Cutover 2026-05-03 → 2026-05-18]],
[[demo-topic#phase 3: cutover (2026-05-03 → 2026-05-18)#gotchas]],
[[demo-topic#^IP-BASIS]], and [[demo#Current state]].
`[[demo-topic#Not a real heading]]` is an example inside code, not a link.
"""

REGISTRY = {
    "version": 1,
    "hubs": [
        {
            "hub": "projects/demo/demo.md",
            "project_dir": "projects/demo",
            "budget_bytes": {"warn": 3000, "fail": 6000},
            "heading_date_allowlist": ["Scale as of"],
            "log_glob": "projects/demo/demo-log-*.md",
            "log_warn_bytes": 50000,
            "contracted_pages": ["projects/demo/demo-topic.md"],
            "frozen_dated_sections": {"projects/demo/old.md": ["2026-01-05 — Kickoff"]},
        }
    ],
}


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    _write(tmp_path, hc.REGISTRY, json.dumps(REGISTRY))
    _write(tmp_path, "projects/demo/demo.md", HUB)
    _write(tmp_path, "projects/demo/demo-topic.md", TOPIC)
    _write(tmp_path, "projects/demo/demo-log-2026-10.md", LOG)
    _write(tmp_path, "projects/demo/old.md", OLD)
    _write(tmp_path, "concepts/linker.md", LINKER)
    return tmp_path


def _rules(root: Path, **kw) -> tuple[int, set[str]]:
    code, findings = hc.run(root, **kw)
    return code, {f.rule for f in findings if f.severity == "violation"}


def _edit(root: Path, rel: str, old: str, new: str) -> None:
    p = root / rel
    text = p.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    p.write_text(text.replace(old, new), encoding="utf-8")


# --------------------------------------------------------------------------- clean


def test_clean_fixture_passes(vault: Path) -> None:
    code, findings = hc.run(vault)
    assert code == hc.EXIT_PASS, [f.render() for f in findings]
    assert not findings


def test_inert_without_registry(vault: Path) -> None:
    (vault / hc.REGISTRY).unlink()
    _edit(
        vault,
        "projects/demo/demo.md",
        "## Related",
        "## Exam run (2026-04-20)\n\n## Related",
    )
    assert hc.run(vault) == (hc.EXIT_PASS, [])


# ----------------------------------------------------------- one planted error per rule


PLANTED = [
    ("R1-flag", "projects/demo/demo.md", "hub_contract: 1\n", ""),
    (
        "R2-current-state",
        "projects/demo/demo.md",
        "## Scale as of",
        "## Current state\n\n## Scale as of",
    ),
    (
        "R2-current-state",  # a stacked second snapshot: how the hub actually regrew
        "projects/demo/demo.md",
        "## Scale as of",
        "### State as of 2026-10-14 (prior)\n\nOld.\n\n## Scale as of",
    ),
    (
        "R3-dated-heading",
        "projects/demo/demo.md",
        "## Related",
        "## Exam run (2026-04-20)\n\nx\n\n## Related",
    ),
    (
        "R3-dated-heading",
        "projects/demo/demo.md",
        "## Related",
        "## 2026-07-09: Hardening\n\nx\n\n## Related",
    ),
    (
        "R4-dated-bold",
        "projects/demo/demo.md",
        "## Related",
        "**Engineering status 2026-08-15:** did things.\n\n## Related",
    ),
    (
        "R5-related",
        "projects/demo/demo.md",
        "## Maintenance contract",
        "## Related\n\n## Maintenance contract",
    ),
    (
        "R8-anchor",
        "concepts/linker.md",
        "[[demo-topic#^IP-BASIS]]",
        "[[demo-topic#Ask Rubi]]",
    ),
    (
        "R8-anchor",
        "concepts/linker.md",
        "[[demo-topic#^IP-BASIS]]",
        "[[demo-topic#^no-such-block]]",
    ),
    (
        "R9-log-month",
        "projects/demo/demo-log-2026-10.md",
        "2026-10-14 (prior)",
        "2026-09-30 (prior)",
    ),
    (
        "R11-frozen",
        "projects/demo/old.md",
        "Started.",
        "Started.\n\n## 2026-10-12 — New dated thing\n\nx",
    ),
]


@pytest.mark.parametrize(
    "rule,rel,old,new", PLANTED, ids=[f"{p[0]}-{i}" for i, p in enumerate(PLANTED)]
)
def test_planted_violation_fails(
    vault: Path, rule: str, rel: str, old: str, new: str
) -> None:
    _edit(vault, rel, old, new)
    code, rules = _rules(vault)
    assert code == hc.EXIT_VIOLATION
    assert rule in rules, rules


def test_budget_fail_and_warn(vault: Path) -> None:
    _edit(
        vault,
        "projects/demo/demo.md",
        "Forty widgets.",
        "Forty widgets.\n" + "x" * 2600,
    )
    code, findings = hc.run(vault)
    assert code == hc.EXIT_PASS
    assert {f.rule for f in findings if f.severity == "warning"} == {"R6-budget"}
    _edit(
        vault,
        "projects/demo/demo.md",
        "Forty widgets.",
        "Forty widgets.\n" + "x" * 5600,
    )
    assert "R6-budget" in _rules(vault)[1]


def test_unlinked_project_page_fails(vault: Path) -> None:
    _write(
        vault, "projects/demo/concepts/new-spoke.md", "---\ntitle: New\n---\n# New\n"
    )
    assert "R7-unlinked-page" in _rules(vault)[1]


def test_unregistered_hub_missing(vault: Path) -> None:
    (vault / "projects/demo/demo.md").unlink()
    assert "R0-hub-missing" in _rules(vault)[1]


def test_bad_registry_is_an_error_not_a_pass(vault: Path) -> None:
    _write(vault, hc.REGISTRY, json.dumps({"version": 2}))
    assert hc.main([str(vault)]) == hc.EXIT_ERROR


def test_snapshot_inside_current_state_is_not_flagged(vault: Path) -> None:
    # The dated `###` snapshot and its dated bold ruling live in Current state legitimately.
    assert hc.run(vault)[0] == hc.EXIT_PASS


# ------------------------------------------------------------------- anchor semantics


@pytest.mark.parametrize(
    "heading,link,match",
    [
        (
            "Phase 3: Postgres Cutover (2026-05-03 → 2026-05-18)",
            "Phase 3 Postgres Cutover 2026-05-03 → 2026-05-18",
            True,
        ),
        ("Phase 3: Postgres Cutover", "phase 3: postgres cutover", True),
        (
            "Ask Rubi — in-UI assistant (v1)",
            "Ask Rubi - in-UI assistant v1",
            False,
        ),  # em dash is kept
        ("Ask Rubi — in-UI assistant (v1)", "Ask Rubi", False),  # no prefix matching
        ("What's new", "What's new", True),
        ("a/b & c", "a b c", True),
    ],
)
def test_lt_matches_obsidian(heading: str, link: str, match: bool) -> None:
    assert (hc.lt(heading).lower() == hc.lt(link).lower()) is match


def test_nested_and_duplicate_and_block(vault: Path) -> None:
    page = hc.parse_page("t", TOPIC)
    assert hc.resolve_subpath(
        page, "Phase 3: Cutover (2026-05-03 → 2026-05-18)#Gotchas"
    )
    assert not hc.resolve_subpath(
        page, "Gotchas#Phase 3: Cutover (2026-05-03 → 2026-05-18)"
    )
    assert hc.resolve_subpath(page, "Duplicate")
    assert hc.resolve_subpath(page, "^IP-Basis")
    assert not hc.resolve_subpath(page, "^ip")


# ------------------------------------------------------------------- roll conservation


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(vault: Path) -> Path:
    _git(vault, "init", "-q")
    _git(vault, "-c", "user.email=t@example.com", "-c", "user.name=t", "add", "-A")
    _git(
        vault,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "-qm",
        "base",
    )
    return vault


NEW_SNAPSHOT = "### State as of 2026-10-16 (next)\n\nNew status."
OLD_SNAPSHOT_HEADING = "### State as of 2026-10-15 (shipping)\n\nShipped the thing. **Ruling 2026-10-15:** keep it."


def test_roll_without_log_copy_fails(repo: Path) -> None:
    _edit(repo, "projects/demo/demo.md", OLD_SNAPSHOT_HEADING, NEW_SNAPSHOT)
    assert "R10-roll" in _rules(repo, since="HEAD")[1]


def test_roll_into_log_passes_even_with_link_wraps(repo: Path) -> None:
    _edit(repo, "projects/demo/demo.md", OLD_SNAPSHOT_HEADING, NEW_SNAPSHOT)
    _edit(
        repo,
        "projects/demo/demo-log-2026-10.md",
        "## State as of 2026-10-14 (prior)",
        "## State as of 2026-10-15 (shipping)\n\nShipped the [[demo-topic|thing]]. "
        "**Ruling 2026-10-15:** keep it.\n\n## State as of 2026-10-14 (prior)",
    )
    code, findings = hc.run(repo, since="HEAD")
    assert code == hc.EXIT_PASS, [f.render() for f in findings]


def test_roll_reads_history_from_repo_option(repo: Path, tmp_path_factory) -> None:
    # The pre-commit hook checks an exported copy of the index; history comes from --repo.
    export = tmp_path_factory.mktemp("index")
    _edit(repo, "projects/demo/demo.md", OLD_SNAPSHOT_HEADING, NEW_SNAPSHOT)
    _git(repo, "add", "-A")
    _git(repo, "checkout-index", "-a", f"--prefix={export}/")
    assert "R10-roll" in _rules(export, since="HEAD", repo=repo)[1]


# ------------------------------------------------------------------------- isolation


def test_runs_standalone_under_isolated_python(vault: Path) -> None:
    # The hook runs `python3 -I hub_contract.py`; that must not need the package.
    r = subprocess.run(
        [sys.executable, "-I", str(MODULE), str(vault)], capture_output=True, text=True
    )
    assert r.returncode == hc.EXIT_PASS, r.stdout + r.stderr
    _edit(vault, "projects/demo/demo.md", "hub_contract: 1\n", "")
    r = subprocess.run(
        [sys.executable, "-I", str(MODULE), str(vault)], capture_output=True, text=True
    )
    assert r.returncode == hc.EXIT_VIOLATION
    assert "Routing rules (from the hub)" in r.stdout
