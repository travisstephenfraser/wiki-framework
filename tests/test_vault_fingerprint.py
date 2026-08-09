"""Self-test for scripts/vault_fingerprint.rb, the vault corruption detector.

The detector is a Ruby script driven by hand during risky bulk operations, so it
had no coverage at all. That is the dangerous shape for a measurement tool: a
future edit can turn it into something that always reports IDENTICAL, and
nothing would say so — the tool's own output is the only thing anyone reads.

An adversarial review of the first version found it did exactly that on several
real damage classes. Each test below pins one of those, so a regression fails
here instead of during the operation the tool is supposed to guard.

The tests assert BOTH directions: damage must be reported, and benign churn must
not be. A detector that reports everything is as useless as one that reports
nothing, because an operator learns to ignore it either way.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "vault_fingerprint.rb"

pytestmark = pytest.mark.skipif(
    shutil.which("ruby") is None or not SCRIPT.is_file(),
    reason="ruby or vault_fingerprint.rb not available",
)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ruby", str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def _page(vault: Path, rel: str, *, body: str = "# Body\n", **fields: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "title": rel,
        "category": "concepts",
        "tags": "[test]",
        "summary": "S.",
        "created": "2026-07-01",
        "updated": "2026-07-01",
        **fields,
    }
    lines = "\n".join(f"{k}: {v}" for k, v in fm.items())
    p.write_text(f"---\n{lines}\n---\n{body}", encoding="utf-8")
    return p


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A vault large enough that the degeneracy heuristics engage (>= 10 pages)."""
    v = tmp_path / "vault"
    for i in range(14):
        _page(
            v,
            f"concepts/p{i}.md",
            body=f"# P{i}\n\nSee [[p{(i + 1) % 14}]] and [[p{(i + 2) % 14}]].\n",
            base_confidence=f"0.{50 + i}",
            lifecycle="draft" if i % 2 else "reviewed",
        )
    return v


def _capture(vault: Path, out: Path) -> None:
    r = _run("capture", str(vault), str(out))
    assert r.returncode == 0, f"capture failed: {r.stderr}"


def _compare(before: Path, after: Path) -> subprocess.CompletedProcess:
    return _run("compare", str(before), str(after))


def _mutate_and_compare(
    vault: Path, tmp_path: Path, mutate
) -> subprocess.CompletedProcess:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    _capture(vault, before)
    mutate(vault)
    _capture(vault, after)
    return _compare(before, after)


# --------------------------------------------------------------------------
# Must NOT fire — a detector that cries wolf gets ignored
# --------------------------------------------------------------------------


def test_unchanged_vault_is_reported_identical(vault: Path, tmp_path: Path) -> None:
    r = _mutate_and_compare(vault, tmp_path, lambda _v: None)
    assert r.returncode == 0, r.stdout
    assert "RESULT: IDENTICAL" in r.stdout


# --------------------------------------------------------------------------
# Must fire — each was reported clean by the first version of the detector
# --------------------------------------------------------------------------


def test_pure_addition_is_not_clean(vault: Path, tmp_path: Path) -> None:
    """A leftover .orig/.rej or a duplicated page is the likeliest merge artifact.

    v1 omitted additions from its `clean` predicate, so it printed
    'RESULT: IDENTICAL' and exited 0 on the line right after 'pages +1'.
    """
    r = _mutate_and_compare(
        vault, tmp_path, lambda v: (v / "concepts" / "p0.md.orig").write_text("x\n")
    )
    assert r.returncode == 1, r.stdout
    assert "RESULT: DIFFERENCES PRESENT" in r.stdout


def test_wikilink_removal_is_reported(vault: Path, tmp_path: Path) -> None:
    """The link graph is what makes this a wiki rather than a folder of text.

    v1 had no link awareness: destroying links made the link-damage metric go
    DOWN, and the only signal was a body-change count indistinguishable from
    ordinary migration churn.
    """

    def mangle(v: Path) -> None:
        p = v / "concepts" / "p0.md"
        p.write_text(
            p.read_text().replace("[[", "[").replace("]]", "]"), encoding="utf-8"
        )

    r = _mutate_and_compare(vault, tmp_path, mangle)
    assert r.returncode == 1, r.stdout
    assert "LINKS" in r.stdout
    assert "removed across" in r.stdout


def test_false_to_null_is_reported(vault: Path, tmp_path: Path) -> None:
    """`h[k] || h[k.to_sym]` collapsed false and nil onto one hash in v1."""

    def flip(v: Path) -> None:
        p = v / "concepts" / "p0.md"
        p.write_text(
            p.read_text().replace("lifecycle: reviewed", "lifecycle: null"),
            encoding="utf-8",
        )

    r = _mutate_and_compare(vault, tmp_path, flip)
    assert r.returncode == 1, r.stdout
    assert "lifecycle" in r.stdout


def test_page_deletion_is_reported(vault: Path, tmp_path: Path) -> None:
    r = _mutate_and_compare(
        vault, tmp_path, lambda v: (v / "concepts" / "p0.md").unlink()
    )
    assert r.returncode == 1, r.stdout
    assert "REMOVED PAGE" in r.stdout


def test_body_change_is_reported(vault: Path, tmp_path: Path) -> None:
    def truncate(v: Path) -> None:
        (v / "concepts" / "p3.md").write_text("---\ntitle: x\n---\n", encoding="utf-8")

    r = _mutate_and_compare(vault, tmp_path, truncate)
    assert r.returncode == 1, r.stdout


def test_invalid_utf8_does_not_crash_the_run(vault: Path, tmp_path: Path) -> None:
    """v1 raised an unhandled ArgumentError that killed capture without naming the file."""
    (vault / "concepts" / "p1.md").write_bytes(b"---\ntitle: x\n---\n\xff\xfe body\n")
    out = tmp_path / "m.json"
    r = _run("capture", str(vault), str(out))
    assert r.returncode == 0, f"capture must degrade, not crash: {r.stderr}"
    man = json.loads(out.read_text())
    statuses = {p["status"] for p in man["blind_spots"]}
    assert "ENCODING_ERROR" in statuses
    assert any("p1.md" in p["page"] for p in man["blind_spots"])


def test_blind_pages_still_produce_a_manifest(vault: Path, tmp_path: Path) -> None:
    """A parse error is the damage class this tool hunts, not a reason to refuse.

    v1 raised on it, wrote nothing, and labelled it 'measurement may be reading
    itself' -- failing closed exactly when an operator most needs a diff.
    """
    p = vault / "concepts" / "p2.md"
    p.write_text("---\nsummary: bad: unquoted: colons\n---\n# B\n", encoding="utf-8")
    out = tmp_path / "m.json"
    r = _run("capture", str(vault), str(out))
    assert r.returncode == 0, r.stderr
    assert out.is_file(), "manifest must still be written when pages are blind"
    assert "PARSE_ERROR" in {
        b["status"] for b in json.loads(out.read_text())["blind_spots"]
    }
    assert "WARNING" in r.stderr


# --------------------------------------------------------------------------
# The anchor must be capable of failing, or it is not a known-answer test
# --------------------------------------------------------------------------


def test_anchor_passes_when_the_expectation_holds(vault: Path, tmp_path: Path) -> None:
    post = tmp_path / "post"
    shutil.copytree(vault, post)
    for i in range(14):
        p = post / "concepts" / f"p{i}.md"
        p.write_text(
            p.read_text().replace("---\ntitle:", "---\ntier: core\ntitle:", 1),
            encoding="utf-8",
        )
    expect = tmp_path / "expect.json"
    expect.write_text(
        json.dumps(
            {
                "fields_added": {"String/tier": 14},
                "pages_added": 0,
                "pages_removed": 0,
                "blind": 0,
            }
        )
    )
    r = _run("anchor", str(vault), str(post), str(expect))
    assert r.returncode == 0, r.stdout
    assert "ANCHOR: PASS" in r.stdout


def test_anchor_fails_on_a_wrong_expectation(vault: Path, tmp_path: Path) -> None:
    post = tmp_path / "post"
    shutil.copytree(vault, post)
    expect = tmp_path / "expect.json"
    expect.write_text(json.dumps({"fields_added": {"String/tier": 14}}))
    r = _run("anchor", str(vault), str(post), str(expect))
    assert r.returncode == 1, f"anchor must fail when nothing changed: {r.stdout}"
    assert "ANCHOR: FAIL" in r.stdout


def test_anchor_fails_on_a_wiped_tree(vault: Path, tmp_path: Path) -> None:
    """v1 exited 0 here, which is the clearest proof it asserted nothing."""
    post = tmp_path / "post"
    post.mkdir()
    expect = tmp_path / "expect.json"
    expect.write_text(json.dumps({"pages_removed": 0}))
    r = _run("anchor", str(vault), str(post), str(expect))
    assert r.returncode == 1, r.stdout
