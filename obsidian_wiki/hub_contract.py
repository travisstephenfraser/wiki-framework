"""Hub contract checker (fork-local; no upstream counterpart).

A *contracted hub* is a project hub page that has been split and must not regrow:
it holds one current-state snapshot, links out to topic pages and monthly logs, and
never accumulates dated sections. Contracted hubs are listed in the vault registry
``_meta/hub-contracts.json``; a vault without that file is not checked at all, so this
module is inert until a hub opts in.

Deliberately standalone and stdlib-only: the vault's git pre-commit hook runs it as
``python3 -I hub_contract.py <vault>``, which forbids importing anything from the
framework (``-I`` drops the script directory, PYTHONPATH and user site-packages).

Exit codes: 0 = pass (warnings allowed), 3 = contract violation, 2 = could not run.

Anchor semantics replicate Obsidian 1.12.7's subpath resolver (extracted from the
app's ``app.js``): the subpath is split on ``#``; a single ``^id`` part is a block id
matched case-insensitively; otherwise headings are walked in order and part *g*
matches a heading when ``LT(heading).lower() == LT(part).lower()`` and the heading is
deeper than the previous matched part, where ``LT`` replaces ASCII punctuation
``!"#$%&()*+,.:;<=>?@^`{|}~/[]\\`` and CR/LF with spaces and collapses whitespace.
The first full match wins.
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
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_WIKILINK = re.compile(r"\[\[([^\[\]]+?)\]\]")
_BLOCK_ID = re.compile(r"(?:^|\s)\^([A-Za-z0-9-]+)\s*$")
_LOG_NAME = re.compile(r"-(\d{4})-(\d{2})\.md$")


def lt(text: str) -> str:
    """Obsidian's ``stripHeading``: punctuation to spaces, whitespace collapsed."""
    return re.sub(r"\s+", " ", _LT_STRIP.sub(" ", text)).strip()


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


@dataclass
class Finding:
    rule: str
    severity: str  # "violation" | "warning"
    where: str
    message: str

    def render(self) -> str:
        return f"[{self.severity}] {self.rule} {self.where}: {self.message}"


def parse_page(rel: str, text: str) -> Page:
    page = Page(rel=rel, text=text)
    lines = text.split("\n")
    start = 0
    if lines and lines[0] == "---":
        for i in range(1, len(lines)):
            if lines[i] == "---":
                page.frontmatter = "\n".join(lines[1:i])
                start = i + 1
                break
    page.body_offset = start
    fence = None
    for i in range(start, len(lines)):
        line = lines[i]
        m = _FENCE.match(line)
        if m:
            marker = m.group(1)[0]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence:
            continue
        h = _HEADING.match(line)
        if h:
            page.headings.append((i + 1, len(h.group(1)), h.group(2)))
            continue
        b = _BLOCK_ID.search(line)
        if b:
            page.blocks.add(b.group(1).lower())
    return page


def strip_code(text: str) -> str:
    """Blank fenced blocks and inline code so example links are not treated as links."""
    out, fence = [], None
    for line in text.split("\n"):
        m = _FENCE.match(line)
        if m:
            marker = m.group(1)[0]
            fence = marker if fence is None else (None if marker == fence else fence)
            out.append("")
            continue
        out.append(
            "" if fence else re.sub(r"`[^`\n]*`", lambda x: " " * len(x.group(0)), line)
        )
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
            self.pages[rel.as_posix()] = parse_page(
                rel.as_posix(), p.read_text(encoding="utf-8", errors="replace")
            )
        self.by_stem: dict[str, list[str]] = {}
        for rel in self.pages:
            self.by_stem.setdefault(Path(rel).stem.lower(), []).append(rel)

    def resolve(self, target: str, source: str) -> str | None:
        if not target:
            return source
        t = target[:-3] if target.lower().endswith(".md") else target
        t = t.strip("/")
        for rel in self.pages:
            if rel[:-3].lower() == t.lower():
                return rel
        cands = self.by_stem.get(Path(t).name.lower())
        return cands[0] if cands else None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


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
    current = [
        h for h in hub.headings if h[1] == 2 and h[2].strip().lower() == "current state"
    ]
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

    for i, line in enumerate(lines, start=1):
        if i <= hub.body_offset or cs_range[0] <= i < cs_range[1]:
            continue
        if line.lstrip().startswith("**") and _DATE.search(line.lstrip()[:80]):
            out.append(
                Finding(
                    "R4-dated-bold",
                    "violation",
                    f"{hub_rel}:{i}",
                    "date-led bold paragraph on a contracted hub (records go to the month log)",
                )
            )

    related = [
        h for h in hub.headings if h[1] == 2 and h[2].strip().lower() == "related"
    ]
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

    linked = {vault.resolve(t, hub_rel) for _, (t, _s) in link_targets(hub.text)}
    project_dir = spec.get("project_dir", str(Path(hub_rel).parent))
    for rel in vault.pages:
        if (
            rel != hub_rel
            and rel.startswith(project_dir.rstrip("/") + "/")
            and rel not in linked
        ):
            out.append(
                Finding(
                    "R7-unlinked-page",
                    "violation",
                    rel,
                    f"project page is not linked from the hub {hub_rel}",
                )
            )

    log_glob = spec.get("log_glob")
    log_pages = (
        sorted(
            str(p.relative_to(vault.root).as_posix()) for p in vault.root.glob(log_glob)
        )
        if log_glob
        else []
    )
    log_warn = spec.get("log_warn_bytes")
    for rel in log_pages:
        page = vault.pages.get(rel)
        m = _LOG_NAME.search(rel)
        if page is None or not m:
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
            continue
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


def _git_show(root: Path, rev: str, rel: str) -> str | None:
    r = subprocess.run(
        ["git", "-C", str(root), "show", f"{rev}:{rel}"], capture_output=True, text=True
    )
    return r.stdout if r.returncode == 0 else None


def snapshot_block(page: Page) -> tuple[str, str] | None:
    """(heading text, body) of the single `###` under `## Current state`, if well formed."""
    current = [
        h
        for h in page.headings
        if h[1] == 2 and h[2].strip().lower() == "current state"
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
    old_text = _git_show(repo, since, hub_rel)
    if old_text is None:
        return []
    old = snapshot_block(parse_page(hub_rel, old_text))
    new_page = vault.pages.get(hub_rel)
    new = snapshot_block(new_page) if new_page else None
    if old is None or (new is not None and lt(new[0]).lower() == lt(old[0]).lower()):
        return []
    heading, body = old
    log_glob = spec.get("log_glob", "")
    logs = (
        [
            vault.pages[p.relative_to(vault.root).as_posix()]
            for p in vault.root.glob(log_glob)
        ]
        if log_glob
        else []
    )
    want_body = _normalise_for_roll(body)
    for log in logs:
        has_heading = any(
            level == 2 and lt(text).lower() == lt(heading).lower()
            for _ln, level, text in log.headings
        )
        if has_heading and want_body in _normalise_for_roll(log.text):
            return []
    return [
        Finding(
            "R10-roll",
            "violation",
            hub_rel,
            f"snapshot {heading!r} left the hub but is not verbatim in any month log "
            "(promote it to `##` in the log for its date)",
        )
    ]


def run(
    root: Path, since: str | None = None, repo: Path | None = None
) -> tuple[int, list[Finding]]:
    reg_path = root / REGISTRY
    if not reg_path.exists():
        return EXIT_PASS, []  # inert: no hub has opted in
    registry = json.loads(reg_path.read_text(encoding="utf-8"))
    if registry.get("version") != 1 or not isinstance(registry.get("hubs"), list):
        raise ValueError(f"{REGISTRY}: expected version 1 with a `hubs` list")
    vault = Vault(root)
    findings: list[Finding] = []
    for spec in registry["hubs"]:
        findings += check_hub(vault, spec)
        if since:
            findings += check_roll(vault, spec, since, repo or root)
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
    for spec in json.loads(reg_path.read_text(encoding="utf-8")).get("hubs", []):
        p = root / spec["hub"]
        if not p.exists():
            continue
        page = parse_page(spec["hub"], p.read_text(encoding="utf-8"))
        for ln, level, text in page.headings:
            if level == 2 and text.strip().lower() == "maintenance contract":
                start, end = section_lines(page, ln)
                chunks.append(
                    "\n".join(page.text.split("\n")[start - 1 : end - 1]).rstrip()
                )
    return "\n\n".join(chunks)


def main(argv: list[str]) -> int:
    args = list(argv)
    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    opts: dict[str, str] = {}
    for flag in ("--since", "--repo"):
        if flag in args:
            i = args.index(flag)
            opts[flag] = args[i + 1]
            del args[i : i + 2]
    since = opts.get("--since")
    repo = Path(opts["--repo"]) if "--repo" in opts else None
    if len(args) != 1:
        print(
            "usage: hub_contract.py <tree> [--since <rev>] [--repo <repo-root>] [--json]",
            file=sys.stderr,
        )
        return EXIT_ERROR
    root = Path(args[0])
    try:
        code, findings = run(root, since, repo)
    except Exception as exc:  # any failure to evaluate is "could not run", never a pass
        print(f"hub-contract: could not run: {exc}", file=sys.stderr)
        return EXIT_ERROR
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
            text = contract_text(root)
            if text:
                print("\nRouting rules (from the hub):\n" + text)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
