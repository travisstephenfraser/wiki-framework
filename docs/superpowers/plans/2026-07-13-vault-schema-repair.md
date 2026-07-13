# Vault Schema Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the six defect classes found by the 5-verifier red-team of the 2026-07-13 schema migration, so that every stored `base_confidence` is reproducible by any executor of the published procedure, `updated:` reflects content changes only, `tier` matches its cost-control purpose, all sources name recorded origins, and the fork's skill prose is internally consistent.

**Architecture:** One canonical, deterministic Ordered Source Classification Procedure is published in `llm-wiki/SKILL.md` (spec §S1); every consumer — lint Rule 12e, the recompute script, future ingests — implements it verbatim. Vault data repairs (sources, updated, confidence, tier) run as dry-run-gated scripts against that single procedure. Repo prose patches close every coherence gap the verifiers cited.

**Tech Stack:** Markdown skill documents, Python 3 (stdlib only) migration scripts, git (repo commits; vault stays uncommitted for Travis's manual sync).

## Global Constraints

- Vault: `/Users/travis/Developer/.vault/wiki-vault` (VAULT). Repo: `/Users/travis/Developer/.vault/obsidian-wiki` (REPO). Scratch dir for scripts/reports: `/private/tmp/claude-501/-Users-travis-Developer--vault-obsidian-wiki/f98a8a94-cb7a-4b6b-8220-72a3c04b6438/scratchpad` (SCRATCHPAD). Backup snapshot (pre-migration ground truth): `SCRATCHPAD/vault-backup` (BACKUP).
- Content scope everywhere: the 7 category dirs (`concepts entities skills references synthesis journal projects`), excluding any `_`-prefixed directory. `_raw/` and `_archives/` are staging/history — never scored, never edited by this plan.
- Vault page bodies (content after the closing `---` fence) are IMMUTABLE in this plan, with exactly two exceptions: none. Only frontmatter fields `sources`, `updated`, `base_confidence`, `tier`, `summary` may change, and only on the pages each task names.
- Every script runs dry-run first and prints a report; apply only after the task's gate condition passes.
- Scripts must be idempotent: a second `--apply` run changes zero files.
- Repo changes are committed (messages given per task) and pushed to `origin main`. Vault changes stay uncommitted.
- No `Date.now`-style ambiguity: today's local date is 2026-07-12; `lifecycle_changed` values already written as 2026-07-13 are NOT churned (cosmetic, one day, not worth 181-file noise).
- Rounding convention everywhere: `round(x, 2)` (Python banker's rounding acceptable; both compare sides use the same function).

---

## SPEC §S1 — Ordered Source Classification Procedure (the canonical artifact)

A source string `s` (stripped) is classified by the FIRST matching rule. All regexes case-insensitive. This exact text is published in `llm-wiki/SKILL.md` (T1) and implemented verbatim in `canonical_conf.py` (T7).

| # | Rule (first match wins) | Bucket | Score |
|---|---|---|---|
| 1 | `arxiv\|doi\.org\|proceedings\|neurips\|icml\|\bacl\b` | paper | 1.0 |
| 2 | `\.gov\b\|docs\.anthropic\|platform\.openai\|developer\.apple\|cloud\.google` | official | 0.9 |
| 3 | `docs\.\|readthedocs\|/documentation` | documentation | 0.85 |
| 4 | `github\.com\|gitlab\.com` | repository | 0.75 |
| 5 | `^https?://` (anything not caught above) | blog | 0.55 |
| 6 | `^(~/)?projects/[a-z0-9_-]+$` — bare first-party workspace ref | repository | 0.75 |
| 7 | contains `\.pdf` AND a 4-digit year `\b(19\|20)\d{2}\b`, OR contains `doi\|issn`, OR a year plus a publication word `\b(journal\|educ\|review\|quarterly\|press\|proc)\b` | book | 0.8 |
| 8 | ends `\.md` (non-URL) OR starts `[[` — vault-internal page ref | unknown | 0.4 |
| 9 | `\bsessions?\b\|\bconversation\b\|^agent:\|\.jsonl\b\|claude-desktop\|history ingest` | session_transcript | 0.5 |
| 10 | everything else | unknown | 0.4 |

**Why this order:** rule 6 before 9 fixes the `projects/global-claude` substring bug (never match bare product names like `claude`/`codex`/`hermes` — only explicit session markers); rule 8 before 9 keeps vault-internal transcripts classified as vault-internal.

**source_id (dedup):** lowercase, collapse whitespace; if the string contains a DOI (`10\.\d{4,}/\S+`) or arXiv id (`\d{4}\.\d{4,5}`), the id IS the source_id (this collapses a paper's DOI + citation + PDF into one source); GitHub URLs → `github.com/<owner>/<repo>`; other URLs → host+path; else the normalized string.

**Formula (unchanged, from llm-wiki):** `base_confidence = round(min(N/3, 1.0) * 0.5 + avg_quality * 0.5, 2)` over deduped source_ids. `N == 0` → `0.2`, flag `EMPTY_SOURCES`.

**Drift (12e):** `|stored − round(recomputed, 2)| > 0.05`, content scope only.

## SPEC §S2 — Acceptance criteria (whole plan)

- A1 **Reproducibility:** a fresh implementation of §S1 written only from the published skill text recomputes every content page's `base_confidence` within 0.05 (target: exact match on ≥ 95%, zero outside 0.05).
- A2 **Staleness integrity:** every content page's `updated:` equals its BACKUP value (source corrections are metadata, not content — the 8 T5 pages revert like the rest). Pages absent from BACKUP (`references/macos-migration.md`) are exempt.
- A3 **Tier sanity:** `core` ≤ 25% of content pages; 0 `peripheral` (demotion is human-only); `TIER_DERIVE` logged.
- A4 **Provenance:** all 8 misattributed pages carry the corrected sources of T5; every manifest key cited on any page is confirmed by that manifest entry's `pages_created`/`pages_updated`.
- A5 **Prose coherence:** the six verifier-cited contradictions (T3 list) are gone — verified by the exact greps in T11.
- A6 **Integrity:** bodies byte-identical to current state; YAML well-formed on all files; both scripts idempotent.

---

### Task 1: Publish §S1 in llm-wiki + sync provenance-marker grammar

**Files:**
- Modify: `REPO/.skills/llm-wiki/SKILL.md` (Confidence and Lifecycle section, ~line 393; Provenance Markers section, ~lines 304–334; tier note ~line 470)
- Modify: `REPO/.claude/skills/wiki-capture/references/RAW-FORMAT.md`

**Interfaces:** Produces the canonical §S1 text that T2 references and T7 implements. Anchor strings below are verbatim from the current files (verifier-cited); Read each file before editing.

- [ ] **Step 1:** In `llm-wiki/SKILL.md`, directly after the existing **Source-quality scores** table (anchor: the table row `| \`llm_generated\` | 0.3 | LLM self-reflections |`), insert a new subsection titled `### Ordered classification procedure (normative)` containing the §S1 rule table, the order rationale, the source_id rules, and the rounding/drift convention — copied verbatim from §S1 above, prefixed with: "Any executor recomputing `base_confidence` (lint Rule 12e, backfills, ingest updates) MUST classify with this exact first-match-wins procedure. Judgment-call classification is what makes stored values irreproducible."
- [ ] **Step 2:** Same file, Provenance Markers section: after the marker table (which defines only `^[inferred]`/`^[ambiguous]`), add: "Long-form variants (`^[inferred from X]`, `^[extracted from Y]`, `^[stated directly]`) count as their prefix marker; explicit extracted marks count as marked-extracted claims. Drift recomputation only runs on pages with ≥10 inline markers and skips pages whose `provenance:` block has no inline markers at all — see wiki-lint Check 7."
- [ ] **Step 3:** Same file, tier promotion note (anchor: `promote to core when ≥5 incoming links`): replace with "promote to core when the page is among the vault's true hubs — top ~10–15% by incoming content-page links (a fixed ≥5 degenerates in dense vaults; bulk derivations must log a `TIER_DERIVE` entry and use a threshold selecting ≤25% of pages)."
- [ ] **Step 4:** In `RAW-FORMAT.md`, after the confidence-calibration table, add: "This calibration is a **staging-time estimate** for `_raw/` files only. On promotion, `wiki-ingest` recomputes `base_confidence` with the llm-wiki formula + Ordered Classification Procedure; the staged value is discarded, not copied."
- [ ] **Step 5:** Verify: `grep -c "Ordered classification procedure" REPO/.skills/llm-wiki/SKILL.md` → 1; `grep -c "staging-time estimate" REPO/.claude/skills/wiki-capture/references/RAW-FORMAT.md` → 1.

### Task 2: Harden wiki-lint 12e + fix stale template + consolidate ratchet

**Files:**
- Modify: `REPO/.skills/wiki-lint/SKILL.md`

**Interfaces:** Consumes §S1 (published in T1). Anchors verbatim from verifier cites.

- [ ] **Step 1:** Rule 12e (anchor: `recompute \`base_confidence\` using the formula in \`llm-wiki/SKILL.md\``): append — "Classify sources with the **Ordered classification procedure (normative)** in llm-wiki; round the recomputed value to 2 decimals before the 0.05 comparison. Scope: category directories only; skip `_raw/` and `_archives/`."
- [ ] **Step 2:** 12e fix mode (anchor: `Rewrite the \`base_confidence\` field to the recomputed value. This is the **only rule** that mutates frontmatter automatically.`): replace the second sentence with "Before rewriting, present the full per-page table (stored, recomputed, per-source classification) and require explicit user confirmation; never rewrite silently."
- [ ] **Step 3:** Output template stale example (anchor: `contains \`visibility/internal\` entry (system tag must not be in taxonomy)`): replace that example line with `` `_meta/taxonomy.md` — `visibility/` tag listed inside a countable domain-tag table (belongs in the Reserved section) ``.
- [ ] **Step 4:** Consolidate Action 4 (anchor: the clause refusing to demote `core` because it was `manually set`): append "— except when the vault log's most recent `TIER_DERIVE` entry shows the tier came from a bulk derivation; bulk-derived tiers may be re-derived with the same logged procedure."
- [ ] **Step 5:** Verify greps: `grep -c "Ordered classification procedure" .skills/wiki-lint/SKILL.md` → ≥1; `grep -c "must not be in taxonomy" .skills/wiki-lint/SKILL.md` → 0; `grep -c "TIER_DERIVE" .skills/wiki-lint/SKILL.md` → ≥1.

### Task 3: Prose coherence — daily-update, AGENTS.md, wiki-update, wiki-query, .env.example

**Files:**
- Modify: `REPO/.skills/daily-update/SKILL.md` (~lines 73–76), `REPO/AGENTS.md` (line ~29; CLAUDE.md is a symlink — one edit), `REPO/.skills/wiki-update/SKILL.md` (~line 183), `REPO/.skills/wiki-query/SKILL.md` (~line 103), `REPO/.env.example`

- [ ] **Step 1:** daily-update impl-validator spec (anchor: `Does index.md list at least as many pages as exist in the vault?`): replace with "Is every vault page either listed in index.md or wikilinked from its project hub (`projects/<name>/<name>.md`)? Project-scoped pages deliberately stay off the root index — never bulk-add them."
- [ ] **Step 2:** AGENTS.md vault-structure comment (anchor: `Master index — every page listed, always kept current`): replace with `Master index — every page listed here or reachable from its project hub; project-scoped pages live on hub pages`.
- [ ] **Step 3:** wiki-update (anchor: `Add entries for any new pages created`): append " — except project-scoped pages, which are linked from their project hub instead of the root index (Page Creation Discipline)."
- [ ] **Step 4:** wiki-query index description (anchor: `It lists every page with a one-line description and tags`): replace with "It lists every global page with a one-line description and tags; project-scoped pages appear on their project hubs (`projects/<name>/<name>.md`), so when the query touches a project, also scan that hub's link list."
- [ ] **Step 5:** `.env.example`: append `\n# Lint schema-migration phase for Check 12 (1 = warnings only). Set 2 or 3 to escalate.\nWIKI_SCHEMA_PHASE=1\n`.
- [ ] **Step 6:** Verify greps: `grep -c "at least as many pages" .skills/daily-update/SKILL.md` → 0; `grep -c "every page listed, always kept current" AGENTS.md` → 0; `grep -c "WIKI_SCHEMA_PHASE" .env.example` → 1.

### Task 4: Commit + push repo patches

- [ ] **Step 1:** `git -C REPO add -A && git -C REPO commit` with exactly this message (plus the session's standard Co-Authored-By/Claude-Session trailer):
```
Publish canonical source-classification procedure; close red-team coherence gaps

- llm-wiki: Ordered classification procedure (normative) — deterministic
  first-match rules, source_id dedup, rounding; marker-grammar sync;
  hub-aware tier promotion note
- wiki-lint: 12e classifies via the published procedure, --fix confirm
  gate, Check 9 template example updated, consolidate Action 4 honors
  TIER_DERIVE bulk derivations
- daily-update/AGENTS.md/wiki-update/wiki-query: project-hub index
  convention documented end to end
- RAW-FORMAT: staged confidence is a staging-time estimate, recomputed
  at promotion; .env.example: WIKI_SCHEMA_PHASE
```
- [ ] **Step 2:** `git -C REPO push origin main`. Expected: fast-forward.

### Task 5: Fix the 8 misattributed sources (vault)

**Files:** Modify frontmatter `sources:` blocks only, on exactly these pages. Every manifest key below MUST be verified present in `VAULT/.manifest.json` with the page listed in that entry's `pages_created`/`pages_updated` before writing (the verifier confirmed each; re-verify at execution).

| Page | New `sources:` list (replace entire block) |
|---|---|
| `entities/josh-grossman.md` | the manifest key whose entry references `Rubrica-private/feed/Grading_Demo.pdf` (2026-04-21 CDSS demo transcript) — cite the key verbatim; second entry: `GSI email (quoted in body, 2026-04)` |
| `entities/andrew-bray.md` | same transcript manifest key |
| `entities/t14.md` | manifest key for the `breach-5.25` entry; `journal/2026-05-11-openclaw-experiment-and-devbox-hardening.md`; `projects/rubrica` |
| `journal/2026-04-19-fastapi-starter-ship.md` | `projects/fastapi-react-starter` (same-day wiki-update sync, manifest projects.last_synced 2026-04-19) |
| `concepts/frame-rotation.md` | `live claude session (2026-04-29, analytical-lens distillation)`; `secondary literature cited inline (Schön & Rein 1994; Lakoff; Tilly)` |
| `concepts/demonstrated-not-asserted.md` | `live claude synthesis session (vault commit e502e09)` |
| `projects/strava-pm/skills/pm-casing-framework.md` | `_raw/claude-desktop/conversations.json`; `projects/strava-pm` |
| `projects/strava-pm/concepts/conquer-feature.md` | `claude session 8cab0924 (devbox jsonl)`; `claude session cd3844d3 (devbox jsonl)` |

- [ ] **Step 1:** For each page: `grep -n "pages_created\|pages_updated" VAULT/.manifest.json` context around each claimed key; confirm the page path appears. If any key is not confirmed, STOP and report — do not write an unconfirmed source.
- [ ] **Step 2:** Edit each page's `sources:` block to the table above (list form, `  - ` items). Touch nothing else (T6 handles `updated:`, T7 handles confidence).
- [ ] **Step 3:** Verify: for all 8 pages, `sources:` no longer equals the pre-fix value; `grep -c "session file unrecorded" VAULT/entities/josh-grossman.md` → 0 (likewise andrew-bray, t14, the journal, frame-rotation, demonstrated-not-asserted).

### Task 6: Revert `updated:` on the 47 sources-backfill pages (vault)

**Files:** the 47 pages with `updated: 2026-07-13` (48 matches minus `hot.md`).

- [ ] **Step 1:** Script `revert_updated.py`: for each content page whose current `updated:` is `2026-07-13`, read the same relative path in BACKUP and restore BACKUP's `updated:` line verbatim. Dry-run prints old→new per page. Gate: exactly 47 pages, every BACKUP value non-empty and ≠ 2026-07-13.
- [ ] **Step 2:** Apply; verify `grep -rl "^updated: 2026-07-13" VAULT/{concepts,entities,skills,references,synthesis,journal,projects} | wc -l` → 0, and re-run dry-run → 0 pages.

### Task 7: Global confidence recompute with the canonical classifier (vault)

**Files:** Create `SCRATCHPAD/canonical_conf.py` implementing §S1 verbatim (rule table as an ordered list of `(bucket, score, regex)`; source_id + formula + rounding as specified). It rewrites `base_confidence:` on any content page where `|stored − recomputed| > 0` (exact alignment, not just >0.05 — the point is reproducibility), EXCEPT pages with `sources: []`→ keep 0.2/EMPTY flag path (there should be none left after T5/T6; gate on it).

- [ ] **Step 1:** Dry-run. Gate conditions: (a) zero EMPTY_SOURCES pages; (b) the three old cohorts unify — every page whose sole source is a bare `projects/<name>` recomputes to 0.54; (c) the 7 previously-unreachable pages land at their formula values (spot-list them in the report); (d) total pages changed plausibly ≈ 100–130.
- [ ] **Step 2:** Review the dry-run distribution table (report it to Travis in the run summary), then `--apply`.
- [ ] **Step 3:** Idempotency: re-run dry-run → 0 changes.
- [ ] **Step 4:** Reproducibility probe (mini-A1): re-run the RED-TEAM verifier's independently-written recompute (`SCRATCHPAD/verify2/recompute.py`) if compatible, else a fresh grep-based sample of 15 pages hand-checked against §S1. Expected: 0 outside 0.05.

### Task 8: Re-derive tier (vault)

**Files:** Create `SCRATCHPAD/tier_derive.py`: count distinct incoming content-page wikilinks per page (system files `index.md`/`hot.md`/`_insights.md`/`log.md` excluded as link sources; self-links excluded); set `tier: core` iff incoming ≥ 10, else `tier: supporting`. Never write `peripheral`.

- [ ] **Step 1:** Dry-run. Gate: resulting core count ≤ 25% of content pages (~≤46). If >25%, raise threshold to 12 and re-gate.
- [ ] **Step 2:** Apply; append to `VAULT/log.md`: `- [TS] TIER_DERIVE threshold=<n> core=<count> supporting=<count> method="distinct incoming content-page wikilinks; bulk derivation, re-derivable per wiki-lint Action 4"`.
- [ ] **Step 3:** Idempotency re-run → 0 changes.

### Task 9: Restore the two lossy summaries (vault)

- [ ] **Step 1:** `projects/personal-website/personal-website.md` summary → exactly: `Travis's Vercel portfolio + Ask Travis chatbot with hidden chat CLI commands. 2026-06 cartographic redesign; 2026-07 Ratchet case study, Build School hub, corpus refresh (assistant-content-drift #2).` (verify ≤200 chars).
- [ ] **Step 2:** `skills/red-team-validation.md` summary → exactly: `Adversarial validation before commitment. Killed the Wellness Engine consumer thesis 2026-03-27; operationalized as the /red-team skill 2026-07-04 (independent verifiers, evidence symmetry).` (≤200).
- [ ] **Step 3:** Verify both with the whitespace-collapsed length check.

### Task 10: Bookkeeping (vault)

- [ ] **Step 1:** `log.md`: one `REPAIR` entry naming: sources fixed (8), updated reverted (47), confidence recomputed (N from T7), tier re-derived, summaries restored (2), and the §S1 pointer.
- [ ] **Step 2:** `hot.md`: update Recent Activity + Active Threads (red-team findings repaired; remaining human item: lifecycle promotions).

### Task 11: Acceptance verification (A1–A6)

- [ ] **Step 1 (A1):** fresh recompute per §S1 over all content pages: 0 outside 0.05.
- [ ] **Step 2 (A2):** for all content pages, `updated:` equals BACKUP value OR page not in BACKUP (macos-migration) — script compare, expected 0 mismatches.
- [ ] **Step 3 (A3):** tier distribution printed; core ≤ 25%; `grep -c TIER_DERIVE VAULT/log.md` → ≥1.
- [ ] **Step 4 (A4):** manifest-support check for every manifest-key source on the 8 pages → all confirmed.
- [ ] **Step 5 (A5):** the six greps from T2/T3 Step-verify lines, all passing.
- [ ] **Step 6 (A6):** body-immutability: byte-compare bodies vs CURRENT pre-plan state snapshot (take `rsync` snapshot of VAULT before T5); YAML structural check all files; both scripts idempotent.
- [ ] **Step 7:** Report the full A1–A6 table to Travis.

---

## ANNEX: Verification-team findings (2026-07-13 run) — PLAN NOT EXECUTED

Three independent reviewers attacked this plan before execution. Status: **parked pending owner decision** (surgical schema revert vs repair). If this plan is ever revived, every item below must be resolved first.

### Coverage reviewer — GAPS FOUND
1. wiki-lint consolidate Action 3 (auto-promote draft→reviewed at confidence>0.7, age>30d) unaddressed; T7's recompute changes its firing set silently.
2. Omitted-additional-contributors (C5.2, e.g. entities/devbox.md missing breach-5.25 + macos-migration manifest keys) — no task, no stated deferral.
3. T7 gate (c) promises 7 unreachable pages resolve; `_raw/_archived/...` page is scope-excluded by Global Constraints — silent descope.
4. T1 Step 2 supplements rather than replaces llm-wiki's unconditional-drift sentence (~:334).
5. A5's greps skip all T1 edits and T3 Steps 3–4 — those fixes unverified.

### Executability reviewer — 3 CRITICAL of 13
1. **T5 deadlock:** manifest `projects` entries use `pages_in_vault`, not `pages_created/updated`; ≥3 of 8 rows unconfirmable under Step 1's command → STOP fires.
2. **Snapshot never created:** T11's pre-plan body-compare snapshot has no creating task.
3. **No rollback story:** mid-sequence gate failure has no restore point that preserves the migration AND pre-existing dirty files; both backups lived in /private/tmp (now copied to `/Users/travis/Developer/.vault/.vault-backup-pre-schema-2026-07-12/`).
Also: T5 josh-grossman source string under-specified (0.75 vs 0.4 depending on formatting); T1 Step 3 anchor not verbatim (line 470 has an "or is flagged as a bridge" clause); §S1 source_id conflicts with llm-wiki's existing source_id table (dual normative spec); T8/T10 violate the body-immutability constraint as written (log.md/hot.md need a carve-out); A1 self-verified; `git add -A` sweeps unrelated files.

### Technical reviewer — §S1 FAILS ITS OWN PURPOSE (empirical, scripts in scratchpad/planverify/)
1. **§S1 non-deterministic:** two textual ambiguities (rule 7 OR-grouping; rule 6 case-sensitivity) diverge on 14 real pages (7.7%) — beyond A1's tolerance. The exact claim-2 failure class, reproduced inside the fix.
2. Rule order false-hits: `\bjournal\b`+year classifies vault-internal journal refs as book 0.8 (rule 8 must precede rule 7); "Voice Journal", "browser review with Gemini" → book.
3. Rule 1 requires literal `doi.org`; the vault's only DOI citation can never classify as paper; the "DOI+citation+PDF collapse" dedup claim is false on the actual Schinske trio.
4. T7 gate (d) wrong: true rewrite count = 132 (stated ≈100–130); gate (c) unexecutable (7 pages never enumerated; 2 recompute to their stored values and can't appear in a change report).
5. Verified sound: Task 6 (updated-revert, all 47 safe incl. timestamp formats) and Task 8 (threshold 10 → 41 core = 22.5%, stable across counting variants).

### Meta-lesson
A deterministic-by-construction classifier still sprouted executor-divergence on its first independent implementation. Trust metadata at this reliability bar costs more verification than a solo-user vault returns; if revived, design the procedure as executable code shipped with the skill (one implementation, no prose re-implementation), not as prose to be re-implemented.
