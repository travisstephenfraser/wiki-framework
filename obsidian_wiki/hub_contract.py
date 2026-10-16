"""Hub contract checker (fork-local; no upstream counterpart).

A *contracted hub* is a project hub page that has been split and must not regrow:
it holds one current-state snapshot, links out to topic pages and monthly logs, and
never accumulates dated sections. Contracted hubs are listed in the vault registry
``_meta/hub-contracts.json``; a vault without that file is not checked at all, so this
module is inert until a hub opts in.

Deliberately standalone and stdlib-only: the vault's git pre-commit hook runs it as
``python3 -I hub_contract.py <tree>``, which forbids importing anything from the
framework (``-I`` drops the script directory, PYTHONPATH and user site-packages).

Exit codes: 0 = pass (warnings allowed), 3 = contract violation, 2 = could not run.
Any failure to evaluate a rule (bad registry, bad revision, git error, bad arguments)
is exit 2, never a pass.

Anchor semantics replicate Obsidian 1.12.7's subpath resolver (``FT`` in the app's
``app.js``): the subpath is split on ``#``; a single ``^id`` part is a block id matched
case-insensitively; otherwise headings are walked in document order and part *g*
matches a heading when ``LT(heading).lower() == LT(part).lower()`` and the heading is
deeper than the previously matched part. Like Obsidian, the walk never resets when it
leaves the matched section. ``LT`` replaces ASCII punctuation ``!"#$%&()*+,.:;<=>?@^`{|}~/[]\\``
and CR/LF with spaces and collapses whitespace. The first full match wins.

Headings: ATX (0-3 leading spaces) and setext (``===`` / ``---`` under a paragraph line),
outside fenced code. Headings inside list items or callouts are not recognised; this
vault does not author them.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REGISTRY = "_meta/hub-contracts.json"
EXIT_PASS, EXIT_ERROR, EXIT_VIOLATION = 0, 2, 3
SKIP_DIRS = {".git", ".obsidian", "_archives", "_raw"}

_LT_STRIP = re.compile(r'[!"#$%&()*+,.:;<=>?@^`{|}~/\[\]\\\r\n]')
_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*(?:[ \t]#+)?[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_LIST_OR_QUOTE = re.compile(r"^ {0,3}(?:[-*+][ \t]|\d+[.)][ \t]|>)")
_DATED_BOLD = re.compile(r"^[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+|>[ \t]*)*\*\*")
_WIKILINK = re.compile(r"\[\[([^\[\]]+?)\]\]")
_BLOCK_ID = re.compile(r"(?:^|\s)\^([A-Za-z0-9-]+)\s*$")
_LOG_NAME = re.compile(r"-(\d{4})-(\d{2})\.md$")


class CheckError(Exception):
    """A rule could not be evaluated; reported as exit 2, never as a pass."""


def lt(text: str) -> str:
    """Obsidian's ``stripHeading``: punctuation to spaces, whitespace collapsed."""
    return re.sub(r"\s+", " ", _LT_STRIP.sub(" ", text)).strip()


def normalise(text: str) -> str:
    """Strip a UTF-8 BOM and normalise CRLF/CR line endings."""
    if text.startswith("﻿"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_text(path: Path) -> str:
    return normalise(path.read_text(encoding="utf-8", errors="replace"))


@dataclass
class Page:
    rel: str
    text: str
    frontmatter: str = ""
    body_offset: int = 0  # number of lines before the body
    headings: list[tuple[int, int, str]] = field(
        default_factory=list
    )  # (line, level, text)
    blocks: set[str] = field(default_factory=set)
    fenced: set[int] = field(default_factory=set)  # 1-based lines inside fenced code


@dataclass
class Finding:
    rule: str
    severity: str  # "violation" | "warning"
    where: str
    message: str

    def render(self) -> str:
        return f"[{self.severity}] {self.rule} {self.where}: {self.message}"


def parse_page(rel: str, text: str) -> Page:
    text = normalise(text)
    page = Page(rel=rel, text=text)
    lines = text.split("\n")
    start = 0
    if lines and lines[0].rstrip() == "---":
        for i in range(1, len(lines)):
            if lines[i].rstrip() in ("---", "..."):
                page.frontmatter = "\n".join(lines[1:i])
                start = i + 1
                break
    page.body_offset = start
    fence: tuple[str, int] | None = None
    prev_para = False  # previous line can be a setext heading's text
    for i in range(start, len(lines)):
        line, n = lines[i], i + 1
        if fence:
            page.fenced.add(n)
            m = re.match(
                rf"^ {{0,3}}({re.escape(fence[0])}{{{fence[1]},}})[ \t]*$", line
            )
            if m:
                fence = None
            prev_para = False
            continue
        m = _FENCE_OPEN.match(line)
        if m:
            fence = (m.group(1)[0], len(m.group(1)))
            page.fenced.add(n)
            prev_para = False
            continue
        if not line.strip():
            prev_para = False
            continue
        s = _SETEXT.match(line)
        if s and prev_para:
            level = 1 if s.group(1).startswith("=") else 2
            page.headings.append((n - 1, level, lines[i - 1].strip()))
            prev_para = False
            continue
        h = _ATX.match(line)
        if h:
            page.headings.append((n, len(h.group(1)), (h.group(2) or "").strip()))
            prev_para = False
            continue
        b = _BLOCK_ID.search(line)
        if b:
            page.blocks.add(b.group(1).lower())
        prev_para = not _LIST_OR_QUOTE.match(line)
    return page


def strip_code(text: str) -> str:
    """Blank fenced blocks and inline code so example links are not treated as links."""
    page = parse_page("", text)
    out = []
    for n, line in enumerate(page.text.split("\n"), start=1):
        if n in page.fenced:
            out.append("")
        else:
            out.append(re.sub(r"`[^`\n]*`", lambda x: " " * len(x.group(0)), line))
    return "\n".join(out)


def resolve_subpath(page: Page, subpath: str) -> bool:
    parts = [p for p in subpath.split("#") if p]
    if not parts:
        return True
    if len(parts) == 1 and parts[0].startswith("^"):
        return parts[0][1:].lower() in page.blocks
    matched, depth = 0, 0
    for _line, level, text in page.headings:
        if level > depth and lt(text).lower() == lt(parts[matched]).lower():
            matched, depth = matched + 1, level
            if matched == len(parts):
                return True
    return False


def split_link(raw: str) -> tuple[str, str]:
    """Return (target, subpath) for the inside of a ``[[...]]``; alias dropped."""
    raw = raw.replace("\\|", "|").split("|", 1)[0]
    target, _, sub = raw.partition("#")
    return target.strip(), sub


def link_targets(text: str):
    for m in _WIKILINK.finditer(strip_code(text)):
        yield m.start(), split_link(m.group(1))


def frontmatter_value(fm: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", fm, re.M)
    return m.group(1).strip("'\"") if m else None


def section_lines(page: Page, heading_line: int) -> tuple[int, int]:
    """1-based [start, end) line range of the section opened at heading_line."""
    level = next(lvl for ln, lvl, _ in page.headings if ln == heading_line)
    end = len(page.text.split("\n")) + 1
    for ln, lvl, _ in page.headings:
        if ln > heading_line and lvl <= level:
            end = ln
            break
    return heading_line, end


class Vault:
    def __init__(self, root: Path):
        self.root = root
        self.pages: dict[str, Page] = {}
        for p in sorted(root.rglob("*.md")):
            rel = p.relative_to(root)
            if set(rel.parts) & SKIP_DIRS:
                continue
            self.pages[rel.as_posix()] = parse_page(rel.as_posix(), read_text(p))
        self.by_stem: dict[str, list[str]] = {}
        for rel in self.pages:
            self.by_stem.setdefault(Path(rel).stem.lower(), []).append(rel)

    def resolve(self, target: str, source: str) -> str | None:
        """Exact path, then path suffix, then basename (same folder as the source first)."""
        if not target:
            return source
        t = (
            (target[:-3] if target.lower().endswith(".md") else target)
            .strip("/")
            .lower()
        )
        for rel in self.pages:
            if rel[:-3].lower() == t:
                return rel
        if "/" in t:
            suffix = [rel for rel in self.pages if rel[:-3].lower().endswith("/" + t)]
            if suffix:
                return suffix[0]
        cands = self.by_stem.get(t.rsplit("/", 1)[-1], [])
        if not cands:
            return None
        here = str(Path(source).parent)
        same = [c for c in cands if str(Path(c).parent) == here]
        return (same or cands)[0]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _log_pages(vault: Vault, spec: dict) -> list[str]:
    glob = spec.get("log_glob")
    if not glob:
        return []
    return sorted(p.relative_to(vault.root).as_posix() for p in vault.root.glob(glob))


def check_hub(vault: Vault, spec: dict) -> list[Finding]:
    out: list[Finding] = []
    hub_rel = spec["hub"]
    hub = vault.pages.get(hub_rel)
    if hub is None:
        return [
            Finding(
                "R0-hub-missing", "violation", hub_rel, "registered hub does not exist"
            )
        ]

    project_dir = spec.get("project_dir", str(Path(hub_rel).parent))
    if project_dir in ("", "."):
        raise CheckError(
            f"{hub_rel}: project_dir must name the hub's project folder, not the vault root"
        )
    for rel in [
        *spec.get("contracted_pages", []),
        *spec.get("frozen_dated_sections", {}),
    ]:
        if rel not in vault.pages:
            out.append(
                Finding(
                    "R0-registry",
                    "violation",
                    rel,
                    "page named in the registry does not exist (renamed or deleted?)",
                )
            )
    log_pages = _log_pages(vault, spec)
    if spec.get("log_glob") and not log_pages:
        out.append(
            Finding(
                "R0-registry", "warning", spec["log_glob"], "log_glob matches no files"
            )
        )

    if frontmatter_value(hub.frontmatter, "hub_contract") != "1":
        out.append(
            Finding(
                "R1-flag",
                "violation",
                hub_rel,
                "registered hub lacks `hub_contract: 1` in frontmatter",
            )
        )

    lines = hub.text.split("\n")
    current = [h for h in hub.headings if h[1] == 2 and h[2].lower() == "current state"]
    snapshot_line = None
    cs_range = (0, 0)
    if len(current) != 1:
        out.append(
            Finding(
                "R2-current-state",
                "violation",
                hub_rel,
                f"expected exactly one `## Current state`, found {len(current)}",
            )
        )
    else:
        cs_range = section_lines(hub, current[0][0])
        subs = [
            h for h in hub.headings if cs_range[0] < h[0] < cs_range[1] and h[1] == 3
        ]
        if len(subs) != 1:
            out.append(
                Finding(
                    "R2-current-state",
                    "violation",
                    f"{hub_rel}:{current[0][0]}",
                    f"`## Current state` must hold exactly one `###` snapshot, found {len(subs)}"
                    " (replace the snapshot; move the previous one to its month log)",
                )
            )
        else:
            snapshot_line = subs[0][0]

    allow = [a.lower() for a in spec.get("heading_date_allowlist", [])]
    for ln, level, text in hub.headings:
        if level not in (2, 3) or ln == snapshot_line:
            continue
        if _DATE.search(text) and not any(text.lower().startswith(a) for a in allow):
            out.append(
                Finding(
                    "R3-dated-heading",
                    "violation",
                    f"{hub_rel}:{ln}",
                    f"dated heading on a contracted hub: {text!r} (records go to the month log)",
                )
            )

    for n, line in enumerate(lines, start=1):
        if n <= hub.body_offset or n in hub.fenced or cs_range[0] <= n < cs_range[1]:
            continue
        m = _DATED_BOLD.match(line)
        if m and _DATE.search(line[m.end() : m.end() + 80]):
            out.append(
                Finding(
                    "R4-dated-bold",
                    "violation",
                    f"{hub_rel}:{n}",
                    "date-led bold entry on a contracted hub (records go to the month log)",
                )
            )

    related = [h for h in hub.headings if h[1] == 2 and h[2].lower() == "related"]
    if len(related) != 1:
        out.append(
            Finding(
                "R5-related",
                "violation",
                hub_rel,
                f"expected exactly one `## Related`, found {len(related)}",
            )
        )

    size = len(hub.text.encode("utf-8"))
    budget = spec.get("budget_bytes", {})
    if budget.get("fail") and size > budget["fail"]:
        out.append(
            Finding(
                "R6-budget",
                "violation",
                hub_rel,
                f"{size} bytes exceeds the {budget['fail']}-byte limit",
            )
        )
    elif budget.get("warn") and size > budget["warn"]:
        out.append(
            Finding(
                "R6-budget",
                "warning",
                hub_rel,
                f"{size} bytes exceeds the {budget['warn']}-byte warning level",
            )
        )

    linked = {vault.resolve(t, hub_rel) for _, (t, _sub) in link_targets(hub.text)}
    prefix = project_dir.strip("/") + "/"
    for rel in vault.pages:
        if rel != hub_rel and rel.startswith(prefix) and rel not in linked:
            out.append(
                Finding(
                    "R7-unlinked-page",
                    "violation",
                    rel,
                    f"project page is not linked from the hub {hub_rel}",
                )
            )

    log_warn = spec.get("log_warn_bytes")
    for rel in log_pages:
        page = vault.pages.get(rel)
        m = _LOG_NAME.search(rel)
        if page is None or not m:
            out.append(
                Finding(
                    "R0-registry",
                    "violation",
                    rel,
                    "log_glob matched a file that is not a `<name>-YYYY-MM.md` page",
                )
            )
            continue
        month = (m.group(1), m.group(2))
        for ln, level, text in page.headings:
            d = _DATE.search(text)
            if level == 2 and d and (d.group(1), d.group(2)) != month:
                out.append(
                    Finding(
                        "R9-log-month",
                        "violation",
                        f"{rel}:{ln}",
                        f"record dated {d.group(0)} filed in the {month[0]}-{month[1]} log",
                    )
                )
        if log_warn and len(page.text.encode("utf-8")) > log_warn:
            out.append(
                Finding(
                    "R6-budget",
                    "warning",
                    rel,
                    f"log exceeds {log_warn} bytes; a candidate for compaction once closed",
                )
            )

    contracted = {hub_rel, *spec.get("contracted_pages", []), *log_pages}
    for src_rel, src in vault.pages.items():
        if src_rel == "log.md":
            continue  # append-only history; its anchors are not repointed
        for pos, (target, sub) in link_targets(src.text):
            if not sub:
                continue
            dest = vault.resolve(target, src_rel)
            if dest is None or dest not in contracted:
                continue
            if not resolve_subpath(vault.pages[dest], sub):
                line = src.text[:pos].count("\n") + 1
                out.append(
                    Finding(
                        "R8-anchor",
                        "violation",
                        f"{src_rel}:{line}",
                        f"[[{target}#{sub}]] does not resolve in {dest}",
                    )
                )

    for rel, baseline in spec.get("frozen_dated_sections", {}).items():
        page = vault.pages.get(rel)
        if page is None:
            continue  # reported above as R0-registry
        allowed = {lt(b).lower() for b in baseline}
        for ln, level, text in page.headings:
            if (
                level in (2, 3)
                and _DATE.search(text)
                and lt(text).lower() not in allowed
            ):
                out.append(
                    Finding(
                        "R11-frozen",
                        "violation",
                        f"{rel}:{ln}",
                        f"new dated section on a frozen page: {text!r} (records go to the month log)",
                    )
                )
    return out


def _normalise_for_roll(text: str) -> str:
    """Display text of links, whitespace collapsed: cross-linker wraps are not changes."""

    def repl(m: re.Match) -> str:
        inner = m.group(1).replace("\\|", "|")
        return inner.split("|", 1)[1] if "|" in inner else inner

    return re.sub(r"\s+", " ", _WIKILINK.sub(repl, text)).strip()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True
        )
    except OSError as exc:  # git missing from PATH
        raise CheckError(f"cannot run git: {exc}") from exc


def verify_history(repo: Path, since: str) -> None:
    r = _git(repo, "rev-parse", "--is-inside-work-tree")
    if r.returncode != 0 or r.stdout.strip() != "true":
        raise CheckError(f"--repo {repo} is not a git work tree: {r.stderr.strip()}")
    r = _git(repo, "rev-parse", "--verify", "--quiet", f"{since}^{{commit}}")
    if r.returncode != 0:
        raise CheckError(f"--since {since!r} is not a commit in {repo}")


def git_show(repo: Path, rev: str, rel: str) -> str | None:
    """File contents at rev; None only when the path genuinely does not exist there."""
    if _git(repo, "cat-file", "-e", f"{rev}:{rel}").returncode != 0:
        return None  # rev was verified, so the path is absent (e.g. a hub new in this commit)
    r = _git(repo, "show", f"{rev}:{rel}")
    if r.returncode != 0:
        raise CheckError(f"git show {rev}:{rel} failed: {r.stderr.strip()}")
    return r.stdout


def snapshot_block(page: Page) -> tuple[str, str] | None:
    """(heading text, body) of the single `###` under `## Current state`, if well formed."""
    current = [
        h for h in page.headings if h[1] == 2 and h[2].lower() == "current state"
    ]
    if len(current) != 1:
        return None
    start, end = section_lines(page, current[0][0])
    subs = [h for h in page.headings if start < h[0] < end and h[1] == 3]
    if len(subs) != 1:
        return None
    s_start, s_end = section_lines(page, subs[0][0])
    lines = page.text.split("\n")
    return subs[0][2], "\n".join(lines[s_start : min(s_end, end) - 1])


def check_roll(vault: Vault, spec: dict, since: str, repo: Path) -> list[Finding]:
    """A snapshot that left the hub between `since` and the checked tree must be in a log."""
    hub_rel = spec["hub"]
    old_text = git_show(repo, since, hub_rel)
    if old_text is None:
        return []  # the hub did not exist at `since`
    old = snapshot_block(parse_page(hub_rel, old_text))
    new_page = vault.pages.get(hub_rel)
    new = snapshot_block(new_page) if new_page else None
    if old is None or (new is not None and lt(new[0]).lower() == lt(old[0]).lower()):
        return []  # nothing rolled (same-heading edits are not checked; see the module docstring)
    heading, body = old
    want_body = _normalise_for_roll(body)
    for rel in _log_pages(vault, spec):
        log = vault.pages.get(rel)
        if log is None:
            continue
        for ln, level, text in log.headings:
            if level == 2 and lt(text).lower() == lt(heading).lower():
                start, end = section_lines(log, ln)
                section = "\n".join(log.text.split("\n")[start : end - 1])
                if want_body in _normalise_for_roll(section):
                    return []
    return [
        Finding(
            "R10-roll",
            "violation",
            hub_rel,
            f"snapshot {heading!r} left the hub but is not verbatim under a matching `##` "
            "in any month log (promote it to `##` in the log for its date)",
        )
    ]


def run(
    root: Path, since: str | None = None, repo: Path | None = None
) -> tuple[int, list[Finding]]:
    reg_path = root / REGISTRY
    if not reg_path.exists():
        return EXIT_PASS, []  # inert: no hub has opted in
    try:
        registry = json.loads(read_text(reg_path))
    except json.JSONDecodeError as exc:
        raise CheckError(f"{REGISTRY}: invalid JSON: {exc}") from exc
    if registry.get("version") != 1 or not isinstance(registry.get("hubs"), list):
        raise CheckError(f"{REGISTRY}: expected version 1 with a `hubs` list")
    if since:
        repo = repo or root
        verify_history(repo, since)
    vault = Vault(root)
    findings: list[Finding] = []
    for spec in registry["hubs"]:
        findings += check_hub(vault, spec)
        if since and repo is not None:
            findings += check_roll(vault, spec, since, repo)
    code = (
        EXIT_VIOLATION
        if any(f.severity == "violation" for f in findings)
        else EXIT_PASS
    )
    return code, findings


def contract_text(root: Path) -> str:
    """The `## Maintenance contract` section of each registered hub, for the hook to print."""
    reg_path = root / REGISTRY
    if not reg_path.exists():
        return ""
    chunks = []
    for spec in json.loads(read_text(reg_path)).get("hubs", []):
        p = root / spec["hub"]
        if not p.exists():
            continue
        page = parse_page(spec["hub"], read_text(p))
        for ln, level, text in page.headings:
            if level == 2 and text.lower() == "maintenance contract":
                start, end = section_lines(page, ln)
                chunks.append(
                    "\n".join(page.text.split("\n")[start - 1 : end - 1]).rstrip()
                )
    return "\n\n".join(chunks)


USAGE = "usage: hub_contract.py <tree> [--since <rev>] [--repo <repo-root>] [--json]"


def main(argv: list[str]) -> int:
    try:
        args = list(argv)
        as_json = "--json" in args
        if as_json:
            args.remove("--json")
        opts: dict[str, str] = {}
        for flag in ("--since", "--repo"):
            if flag in args:
                i = args.index(flag)
                if i + 1 >= len(args) or args[i + 1].startswith("--"):
                    raise CheckError(f"{flag} needs a value; {USAGE}")
                opts[flag] = args[i + 1]
                del args[i : i + 2]
        if len(args) != 1:
            raise CheckError(USAGE)
        root = Path(args[0])
        repo = Path(opts["--repo"]) if "--repo" in opts else None
        code, findings = run(root, opts.get("--since"), repo)
        if as_json:
            print(
                json.dumps(
                    {"exit": code, "findings": [f.__dict__ for f in findings]}, indent=2
                )
            )
        else:
            for f in findings:
                print(f.render())
            if code == EXIT_VIOLATION:
                try:
                    text = contract_text(root)
                except (
                    Exception
                ):  # printing the routing table is a courtesy, never a gate
                    text = ""
                if text:
                    print("\nRouting rules (from the hub):\n" + text)
        return code
    except Exception as exc:  # any failure to evaluate is "could not run", never a pass
        print(f"hub-contract: could not run: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
