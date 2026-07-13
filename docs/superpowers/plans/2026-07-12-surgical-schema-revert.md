# Surgical Schema Revert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) — this plan is small and sequential. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Remove the 2026-07-13 schema layer (confidence/lifecycle/tier fields + derived sources + `updated:` bumps) from the vault while keeping every verified-good change (upstream merge, trap patches, summary trims, fold, link fixes), close the five live prose gaps in the repo, and end with a vault git commit as a durable restore point.

**Architecture:** One deterministic Python script performs two mechanical operations against the BACKUP ground truth (strip fields BACKUP lacks; restore sources/updated lines BACKUP has). No classification, no formulas, no judgment. Acceptance is a single tight criterion: post-revert vault differs from BACKUP **only** in `summary:` fields (≤88 pages) and the two bookkeeping files.

**Tech Stack:** Python 3 stdlib, git.

## Global Constraints

- VAULT `/Users/travis/Developer/.vault/wiki-vault` · REPO `/Users/travis/Developer/.vault/obsidian-wiki` · BACKUP `/Users/travis/Developer/.vault/.vault-backup-pre-schema-2026-07-12` (durable copy; 193 .md files) · SCRATCHPAD `/private/tmp/claude-501/-Users-travis-Developer--vault-obsidian-wiki/f98a8a94-cb7a-4b6b-8220-72a3c04b6438/scratchpad`.
- Content scope: dirs `concepts entities skills references synthesis journal projects`, excluding `_`-prefixed dirs.
- Page bodies are immutable. `log.md` and `hot.md` are bookkeeping files exempt from body-immutability (append/edit per T2 only).
- Local date is 2026-07-12; timestamps in log entries use `date -u`.
- Every script op: dry-run first, hard gates (exact counts, STOP outside them), idempotent on re-run.
- Repo changes commit + push to `origin main`. Vault commits ONLY in T6, after T5's independent audit passes.

### Task 1: Vault revert script

**Files:** Create `SCRATCHPAD/surgical_revert.py` with exactly this content; no modifications during execution — a gate failure means STOP and report, not edit-and-retry.

```python
#!/usr/bin/env python3
"""Surgical schema revert. Op A: delete the 4 schema field lines from any content
page whose BACKUP copy lacks that field. Op B: on pages whose current updated: is
2026-07-13, restore the BACKUP sources: block and updated: line verbatim."""
import os, re, sys, json

VAULT = "/Users/travis/Developer/.vault/wiki-vault"
BACKUP = "/Users/travis/Developer/.vault/.vault-backup-pre-schema-2026-07-12"
CATS = ["concepts", "entities", "skills", "references", "synthesis", "journal", "projects"]
FIELDS = ["base_confidence", "lifecycle", "lifecycle_changed", "tier"]
APPLY = "--apply" in sys.argv

def front_span(text):
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    return None if end < 0 else end + 4  # index just past closing fence

def sources_block_re():
    # matches "sources:" line plus any indented "- " continuation lines,
    # swallowing one trailing newline when a blank line follows so Op B
    # restores BACKUP's blank-line-before-fence byte-verbatim
    # (verifier-tested: full-vault sim = 94 byte-identical + 88 summary-only + 0 else)
    return re.compile(r"^sources:[^\n]*(?:\n[ \t]+-[^\n]*)*(?:\n(?=\n))?", re.M)

report = {"opA_pages": [], "opB_pages": [], "errors": []}
for cat in CATS:
    root = os.path.join(VAULT, cat)
    if not os.path.isdir(root):
        continue
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith("_")]
        for fn in fns:
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dp, fn)
            rel = os.path.relpath(path, VAULT)
            bpath = os.path.join(BACKUP, rel)
            text = open(path, encoding="utf-8").read()
            span = front_span(text)
            if span is None:
                continue
            inner, body = text[:span], text[span:]
            btext = open(bpath, encoding="utf-8").read() if os.path.exists(bpath) else None
            new_inner = inner
            # Op A — strip fields absent from BACKUP copy
            stripped = []
            if btext is not None:
                bspan = front_span(btext)
                binner = btext[:bspan] if bspan else ""
                for f in FIELDS:
                    if re.search(rf"^{f}:", new_inner, re.M) and not re.search(rf"^{f}:", binner, re.M):
                        new_inner, n = re.subn(rf"^{f}:[^\n]*\n", "", new_inner, count=1, flags=re.M)
                        if n == 1:
                            stripped.append(f)
                        else:
                            report["errors"].append(f"{rel}: strip failed for {f}")
            if stripped:
                report["opA_pages"].append({"page": rel, "stripped": stripped})
            # Op B — restore sources/updated from BACKUP where updated: is 2026-07-13
            if btext is not None and re.search(r"^updated: 2026-07-13$", new_inner, re.M):
                bspan = front_span(btext)
                binner = btext[:bspan]
                bsrc = sources_block_re().search(binner)
                bupd = re.search(r"^updated:[^\n]*$", binner, re.M)
                if not bsrc or not bupd:
                    report["errors"].append(f"{rel}: BACKUP missing sources/updated")
                else:
                    new_inner = sources_block_re().sub(lambda m: bsrc.group(0), new_inner, count=1)
                    new_inner = re.sub(r"^updated:[^\n]*$", lambda m: bupd.group(0), new_inner, count=1, flags=re.M)
                    report["opB_pages"].append(rel)
            if (new_inner != inner) and APPLY and not report["errors"]:
                open(path, "w", encoding="utf-8").write(new_inner + body)

out = {"apply": APPLY, "opA_count": len(report["opA_pages"]), "opB_count": len(report["opB_pages"]),
       "errors": report["errors"]}
json.dump(report, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "surgical-report.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
```

- [ ] **Step 1:** Dry-run: `python3 SCRATCHPAD/surgical_revert.py`. **Hard gates (STOP on any miss):** `opA_count == 181`, `opB_count == 47`, `errors == []`.
- [ ] **Step 2:** Apply: `python3 SCRATCHPAD/surgical_revert.py --apply`. Same gate values expected.
- [ ] **Step 3:** Idempotency: re-run dry-run → `opA_count == 0`, `opB_count == 0` (no page still has a strippable field or `updated: 2026-07-13`).
- [ ] **Step 4:** Spot checks: `grep -rc "^base_confidence:" VAULT/concepts VAULT/skills | grep -v ":0" | wc -l` → `0`; `grep -c "^base_confidence: 0.6" VAULT/references/macos-migration.md` → `1` (stub keeps its born-with fields); `grep -c "sources: \[\]" VAULT/projects/rubrica/rubrica.md` → `1` (restored).

### Task 2: Bookkeeping

- [ ] **Step 1:** Append to `VAULT/log.md` (TS = `date -u +%Y-%m-%dT%H:%M:%SZ`):
`- [TS] REVERT scope=schema-layer detail="base_confidence/lifecycle/lifecycle_changed/tier stripped from 181 pages; sources+updated restored from pre-schema backup on 47 pages; summary trims, fold, and link fixes retained. Reason: 3-verifier red-team + 3-verifier plan review found the confidence system irreproducible under the canonical formula (see obsidian-wiki repo docs/superpowers/plans/2026-07-13-vault-schema-repair.md ANNEX). Schema is now opt-in via WIKI_SCHEMA_PHASE."`
- [ ] **Step 2:** In `VAULT/hot.md`, replace the entire `## Active Threads` section body with:
`- Schema layer REVERTED 2026-07-12 after adversarial review found confidence values irreproducible (full findings: repo plan doc annex). Kept: 88 summary trims, fork/upstream-merge discipline fold, link fixes. Check 12 disabled via WIKI_SCHEMA_PHASE=0. Revisit only as executable-code design, per annex meta-lesson.`
and update the frontmatter `updated:` to the current UTC timestamp.

### Task 3: Repo — schema off-switch

**Files:** Modify `REPO/.skills/wiki-lint/SKILL.md`, `REPO/.env`, `/Users/travis/.obsidian-wiki/config`, `REPO/.env.example`.

- [ ] **Step 1:** wiki-lint, Check 12 intro (anchor, verbatim+unique: `Enforces the confidence + lifecycle frontmatter schema`): append after that sentence — ` **Opt-out:** if `WIKI_SCHEMA_PHASE=0` in the resolved config, skip Check 12 entirely (all rules, all output) — the vault has opted out of the confidence/lifecycle schema.`
- [ ] **Step 2:** Append `WIKI_SCHEMA_PHASE=0` to `REPO/.env`; append `WIKI_SCHEMA_PHASE=0` to `/Users/travis/.obsidian-wiki/config`; append to `REPO/.env.example`: `# Confidence/lifecycle schema check (wiki-lint Check 12): 0=off, 1=warnings (default), 2/3=escalating.` + `WIKI_SCHEMA_PHASE=0`.
- [ ] **Step 3:** Verify: `grep -c "WIKI_SCHEMA_PHASE" REPO/.skills/wiki-lint/SKILL.md` → `2` (phase anchor + opt-out); `grep -c "WIKI_SCHEMA_PHASE=0" REPO/.env /Users/travis/.obsidian-wiki/config REPO/.env.example` → 1 each.

### Task 4: Repo — five live prose fixes (anchors verified verbatim+unique by the executability reviewer)

- [ ] **Step 1:** `REPO/.skills/daily-update/SKILL.md` — anchor `Does index.md list at least as many pages as exist in the vault?` → replace with `Is every vault page either listed in index.md or wikilinked from its project hub (projects/<name>/<name>.md)? Project-scoped pages deliberately stay off the root index — never bulk-add them.`
- [ ] **Step 2:** `REPO/AGENTS.md` — anchor `Master index — every page listed, always kept current` → replace with `Master index — every page listed here or reachable from its project hub; project-scoped pages live on hub pages`.
- [ ] **Step 3:** `REPO/.skills/wiki-update/SKILL.md` — anchor `Add entries for any new pages created` → append ` — except project-scoped pages, which are linked from their project hub instead of the root index (Page Creation Discipline)`.
- [ ] **Step 4:** `REPO/.skills/wiki-query/SKILL.md` — anchor `It lists every page with a one-line description and tags` → replace with `It lists every global page with a one-line description and tags; project-scoped pages live on their project hubs (projects/<name>/<name>.md), so when a query touches a project, also scan that hub's link list`.
- [ ] **Step 5:** `REPO/.skills/wiki-lint/SKILL.md` — anchor `contains \`visibility/internal\` entry (system tag must not be in taxonomy)` → replace with `\`visibility/\` tag listed inside a countable domain-tag table (belongs in the Reserved section)`.
- [ ] **Step 6:** Verify greps: `at least as many pages` → 0 in daily-update; `every page listed, always kept current` → 0 in AGENTS.md; `must not be in taxonomy` → 0 in wiki-lint.
- [ ] **Step 7:** Commit these six repo files plus the plan docs (`git add .skills/wiki-lint/SKILL.md .skills/daily-update/SKILL.md .skills/wiki-update/SKILL.md .skills/wiki-query/SKILL.md AGENTS.md .env.example docs/` — note: `.env` is local config, never committed; verify it is untracked/ignored at execution and exclude it either way) with message:
```
Schema opt-out switch + five live prose coherence fixes

- wiki-lint Check 12: WIKI_SCHEMA_PHASE=0 skips the schema check (vault
  opted out after adversarial review; see plan doc annex)
- daily-update/AGENTS.md/wiki-update/wiki-query: project-hub index
  convention documented at every surface that stated the old rule
- wiki-lint Check 9 template example updated to the Reserved-section rule
```
plus the session trailer, then `git push origin main`.

### Task 5: Independent acceptance audit (fresh agent, read-only, before any vault commit)

- [ ] **Step 1:** Dispatch a read-only agent with ONLY this claim: "VAULT content pages (7 category dirs, excluding `_`-prefixed) differ from BACKUP in exactly one way: `summary:` frontmatter fields on at most 88 pages. Zero differences in any other frontmatter field, zero body differences, zero files added/removed (macos-migration.md exists in both). `log.md` and `hot.md` are exempt bookkeeping files. Every file's frontmatter parses." Agent must do a full field-by-field + byte-body diff (claim-1 methodology) and return CONFIRMED or the violation list.
- [ ] **Step 2:** Gate: CONFIRMED with zero violations. Any violation → STOP, report to Travis, do NOT commit the vault.

### Task 6: Vault commit (durable restore point) — only after T5 CONFIRMED

- [ ] **Step 1:** `git -C VAULT add -A && git -C VAULT commit` with message:
```
Restore point: merge-era improvements, schema layer reverted

Kept: 88 summary trims (<=200 chars), fork/upstream-merge discipline
section on wiki-maintenance-protocol, dangling-link fixes +
macos-migration stub, ingest fold of merge findings.
Reverted: confidence/lifecycle/tier backfill and derived-sources pass
(irreproducible under canonical recompute; full adversarial findings in
obsidian-wiki repo, plan doc 2026-07-13 annex). Schema now opt-in via
WIKI_SCHEMA_PHASE.
Includes pre-existing uncommitted work from before this session.
```
plus the session trailer.
- [ ] **Step 2:** `git -C VAULT log --oneline -1` to confirm; report the commit hash. Do NOT push the vault (Travis's manual two-machine flow); recommend he push when back.
