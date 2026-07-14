# Trust-Ledger Adoption & Vault Backfill v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Status: DRAFT — requires multi-verifier review (superpowers-style, ≥3 independent reviewers) before ANY task executes.** The v1 plan (`2026-07-13-vault-schema-repair.md`) died in that review; this one doesn't skip it.

**Goal:** Give every vault page reproducible, auditable `base_confidence` + `lifecycle` trust metadata by adopting upstream's trust-ledger protocol (PR #132) instead of reviving the homegrown §S1 classifier — with all work branch-isolated so a second failure costs `git branch -D`, not a day of surgery.

**Architecture:** Confidence is a *human-approved judgment recorded in a fingerprinted ledger* (`_meta/trust-ledger.json`), validated by executable code (`obsidian_wiki/trust.py`, stdlib-only, 349-line test suite) — never recomputed from source-string heuristics. Agents draft per-page scores with lineage rationale; Travis approves; `trust-record` seals approvals with a SHA-256 fingerprint of material content (volatile fields excluded, so timestamp churn never reopens review). Partial coverage is a supported state: unledgered pages are simply "unreviewed," so the backfill can proceed hub-first without a 186-page big bang.

## Why v1 is superseded (deep-dive findings, 2026-07-14)

1. **Upstream independently hit the identical wall and pivoted, the same day as our merge.** PR #132 (`fix/deterministic-trust-ledger`, merged upstream 2026-07-12, in tags v2026.07.5/6) replaces source-string confidence recompute with the approved ledger. Its own docs: *"a deterministic tool cannot infer independent evidence lineages… never substitutes URL counting for review"* — the same verdict our 5-verifier red-team reached against the §S1 prose classifier, reached independently by a second measurer. Convergence is the signal.
2. **The fork missed it by hours.** Our 2026-07-12 merge took upstream through `bf48502` (#130); PR #131 (`2cc6426`, skill routing) and #132 (`6242472`→`e5cd869`→`e21b478`, merge `09279de`) landed after the snapshot. That is why "there's no backfill protocol in the repo": there is one upstream; we forked just before it existed.
3. **The annex meta-lesson is satisfied by construction.** "Design the procedure as executable code shipped with the skill — one implementation, no prose re-implementation." trust.py *is* that: one implementation, tested, no prose to re-derive. Verified importable from a repo checkout with zero non-stdlib deps — the no-pip-install constraint holds.
4. **Salvage from v1:** Task 8 (tier derivation: distinct incoming content-page links, threshold 10 → ~41 core = 22.5%, verified sound by the technical reviewer) and Task 6's outcome (`updated:` integrity — already restored by the surgical revert). Everything else in v1 is dead weight; §S1 is abandoned, not fixed.

## Global Constraints

- Repo: `/Users/travis/Developer/.vault/obsidian-wiki` (REPO), branch `trust-ledger-adoption`. Vault: `/Users/travis/Developer/.vault/wiki-vault` (VAULT), branch `schema-v2-backfill`. **`main` in both repos is never touched until the final merge gates.** Unlike v1, vault work is COMMITTED on its branch after every task — rollback is branch deletion, and every gate has a restore point.
- Preserve fork-local patches through all cherry-picks: `WIKI_SCHEMA_PHASE` opt-out switch, wiki-query Step 0 visibility guard, manifest-history guard, project-hub index exemption, provenance-drift exemptions (see [[wiki-maintenance-protocol]] "Fork and upstream-merge discipline").
- Do NOT pull the rest of upstream past `bf48502`: the manifest-schema rename (`cc8768e`), pre-write snapshot auto-commits (`cb9d732`/`9113e17`) are known traps (wiki-maintenance-protocol trap list). Cherry-picks only, enumerated below. Optional rider: `95424e4` (cache relative-key fix, #136) — pure code fix, no trap strings; include only if Travis opts in.
- Page bodies are IMMUTABLE. Only frontmatter fields `base_confidence`, `lifecycle`, `lifecycle_changed`, `tier` may be added/changed, plus `_meta/trust-ledger.json` and `log.md`/`hot.md` bookkeeping (explicit carve-out — v1 forgot it).
- Every script dry-runs first, prints a full report, and is idempotent (second `--apply` → 0 changes).
- `updated:` is NEVER bumped by this plan (the ledger fingerprint excludes it; trust metadata is not a content change).
- No pip install. All CLI use runs from the repo checkout: `python3 -c "import sys; sys.path.insert(0,'REPO'); from obsidian_wiki…"` or `python3 -m obsidian_wiki` from REPO.

## Open decisions (Travis, before execution)

- **D1 — Review depth for 186 pages:** (a) per-page approval for core tier (~41) + bulk-by-category approval with 10% spot-checks for the tail, or (b) core tier only in this pass, tail stays unreviewed (supported state). Recommendation: (a).
- **D2 — Include `95424e4` cache fix rider?** Recommendation: yes (it's the #136 fix, independently verified real).
- **D3 — Post-backfill enforcement:** flip `WIKI_SCHEMA_PHASE` to enforce trust fields on new pages once the write-template gate (T5) ships, or stay opt-out and run `trust-check` manually via the weekly cadence. Recommendation: flip after one clean week.

---

### Task 0: Branches, baselines, and preflight

- [ ] **Step 1:** Verify both repos clean (`git status --short` → empty) and record HEADs in the task log. If dirty: STOP, report.
- [ ] **Step 2:** `git -C REPO switch -c trust-ledger-adoption` ; `git -C VAULT switch -c schema-v2-backfill`.
- [ ] **Step 3:** Fetch upstream into REPO (`git remote add upstream https://github.com/Ar9av/obsidian-wiki 2>/dev/null; git fetch upstream`). Confirm the five commits exist: `2cc6426 6242472 e5cd869 e21b478 95424e4`.
- [ ] **Step 4:** Snapshot the vault content dirs for the A-integrity byte-compare (the task v1 forgot): `tar -cf /tmp/vault-pre-v2.tar -C VAULT concepts entities skills references synthesis journal projects`.

### Task 1: Cherry-pick the trust ledger + skill routing onto the repo branch

- [ ] **Step 1:** `git cherry-pick 2cc6426` (skill-table routing for wiki-context-pack / wiki-stage-commit / obsidian-layout-adjustment — closes the registry gap recorded on [[obsidian-wiki]] 2026-07-14). Resolve conflicts in CLAUDE.md/AGENTS.md skill table preserving fork-added rows.
- [ ] **Step 2:** `git cherry-pick 6242472 e5cd869 e21b478` (PR #132). Expected conflict surface: `.skills/wiki-lint/SKILL.md` (fork's Check 12 opt-out) and `.skills/llm-wiki/SKILL.md`. Resolution rule: upstream's new text WINS on confidence mechanics (the manual formula + ledger sections replace the fork's 12a–12e auto-rewrite machinery and the Phase 1/2/3 table); the fork's `WIKI_SCHEMA_PHASE=0` opt-out is re-applied AROUND the new check ("if WIKI_SCHEMA_PHASE=0, skip this check entirely") as a fork-local patch on top.
- [ ] **Step 3 (D2, optional):** `git cherry-pick 95424e4`.
- [ ] **Step 4:** Run the imported tests from the checkout: `python3 -m pytest REPO/tests/test_trust.py REPO/tests/test_lint.py -q`. Gate: all pass. If pytest unavailable, STOP and report (do not pip install; use `python3 -m unittest` fallback only if the tests support it).
- [ ] **Step 5:** Verify fork patches survived: grep for the visibility guard, manifest-history guard, project-hub exemption, `WIKI_SCHEMA_PHASE` — all present. Commit any conflict-resolution fixups on the branch.

### Task 2: Reconcile skill prose end-to-end on the repo branch

- [ ] **Step 1:** `wiki-lint/SKILL.md`: confirm the old 12e "rewrite base_confidence automatically" text and the stale Phase table are gone (upstream's replacement includes neither); confirm the fork opt-out gate wraps the new check; `grep -c "trust-record" → ≥1`, `grep -c "Rule 12e" → 0`.
- [ ] **Step 2:** `llm-wiki/SKILL.md`: confirm the formula section reads as *manual base score* ("not a deterministic URL classifier") and the source-quality table survives as review guidance.
- [ ] **Step 3:** `wiki-status`/`wiki-narrate`/`daily-update`: grep for references to the old auto-recompute or phase table; align any stragglers with one-line edits (list each in the commit message).

### Task 3: Write-template schema gate (closes the 2026-07-14 gap)

- [ ] **Step 1:** In `wiki-update`, `wiki-synthesize`, `wiki-capture` (full mode + RAW-FORMAT note), `wiki-ingest`, and `vault-skill-factory`: make every instruction that writes `base_confidence`/`lifecycle`/`lifecycle_changed`/`tier` conditional — "include these fields only when `WIKI_SCHEMA_PHASE` ≥ 1 in the resolved config; when 0, omit them." vault-skill-factory's maturity filter gets the documented fallback: "when the vault is schema-free (`WIKI_SCHEMA_PHASE=0`), judge maturity by incoming-link count and documented application count."
- [ ] **Step 2:** Verify: `grep -rn "base_confidence" .skills/*/SKILL.md` shows every write-site guarded; run one grep per skill in the commit message.
- [ ] **Step 3:** Update [[wiki-maintenance-protocol]]'s fork-patch list is NOT done here (vault edit) — flag it for T8.

### Task 4: STOP — multi-verifier review gate

- [ ] **Step 1:** Commit the repo branch; do NOT merge. Launch ≥3 independent verifiers against this plan's execution so far + remaining tasks (coverage / executability / technical-empirical, mirroring the v1 review). Technical verifier must include: running `trust-record`+`trust-check` against a **scratch copy** of the real vault to prove the tooling handles 186 real pages (encoding, folded YAML, `>-` titles, visibility tags) before the real run.
- [ ] **Step 2:** Findings resolved or explicitly waived by Travis → proceed. Otherwise the plan stops here and the branches document the state.

### Task 5: Tier derivation on the vault branch (v1-T8 salvage, verified sound)

- [ ] **Step 1:** `tier_derive.py` (from v1 spec): distinct incoming content-page wikilinks; `core` iff ≥ 10 else `supporting`; never `peripheral`; system files excluded as sources. Dry-run gate: core ≤ 25% (~≤46; expected ≈41).
- [ ] **Step 2:** Apply; append `TIER_DERIVE` entry to `VAULT/log.md`; commit on branch. Idempotency re-run → 0.

### Task 6: Lifecycle + confidence drafting (agents draft, Travis approves)

- [ ] **Step 1:** Batch-assign `lifecycle: draft` + `lifecycle_changed: <today>` to every content page lacking the field (dry-run count printed first). This is the honest floor — promotions are human-only.
- [ ] **Step 2:** Per D1 scope: agents produce a **review table** per category — page, proposed `base_confidence` (upstream manual formula: lineage count × 0.5 + reviewed quality × 0.5, then claim-coverage judgment), the independent-evidence lineages identified, and a one-line rationale. No vault writes in this step. Output: `SCRATCHPAD/confidence-review-<category>.md`.
- [ ] **Step 3:** Travis reviews per D1 (per-page for core, bulk+spot-check for tail). Approved rows only proceed. Any page whose evidence doesn't support its claims gets flagged "repair first" and is EXCLUDED (stays unreviewed) — never scored around.
- [ ] **Step 4:** Propose `lifecycle: reviewed` for the approved set (they were just reviewed — that's what the state means); Travis confirms the list. `verified` is proposed for nothing (needs independent verification beyond this pass).

### Task 7: Apply + seal the ledger

- [ ] **Step 1:** Apply approved `base_confidence`/`lifecycle` values by script (dry-run → apply → idempotency). Bodies untouched; `updated:` untouched. Commit on branch.
- [ ] **Step 2:** From the repo checkout: `trust-record VAULT --pages <approved list> --reviewed-at <Travis-supplied ISO timestamp>` (partial recording is supported and intended). Then `trust-check VAULT --strict --json` → gate: zero errors on the ledgered set; unledgered pages report as unreviewed (expected, not a failure).
- [ ] **Step 3:** Commit `_meta/trust-ledger.json` on the vault branch.

### Task 8: Bookkeeping (vault branch)

- [ ] **Step 1:** `log.md`: one `SCHEMA_V2` entry (pages scored, ledgered count, unreviewed count, tier counts, branch name). `hot.md`: Recent Activity + Active Threads (backfill state, D3 decision pending).
- [ ] **Step 2:** [[obsidian-wiki]] entity: fork-state update (trust ledger adopted, registry gap closed, write-template gate shipped — resolves both 2026-07-14 gaps). [[wiki-maintenance-protocol]]: move "write-template schema gate" onto the fork-patch list; strike the superseded parts of the trap list (schema-enforcement trap now moot — we adopted the machinery deliberately); note the ledger file in the weekly cadence (`trust-check` after material edits).

### Task 9: Acceptance & merge gates

- [ ] **A1 Reproducibility:** `trust-check --strict` green; re-running it after a no-op day stays green (fingerprints stable across timestamp-only churn).
- [ ] **A2 Body integrity:** byte-compare bodies vs the T0 tar snapshot → 0 diffs outside frontmatter.
- [ ] **A3 Tier sanity:** core ≤ 25%, 0 peripheral, `TIER_DERIVE` logged.
- [ ] **A4 Test suite:** `test_trust.py` + `test_lint.py` pass on the repo branch.
- [ ] **A5 Fork patches:** all five fork-local patches present post-cherry-pick (greps from T1 Step 5).
- [ ] **A6 Idempotency:** every script's re-run → 0 changes.
- [ ] **Merge gate:** Travis sign-off → merge `trust-ledger-adoption` → repo main, push; merge `schema-v2-backfill` → vault main, push. On abort at any point: `git branch -D` both, `main` was never touched.

---

## ANNEX-awareness checklist (v1 findings this plan must not repeat)

| v1 finding | How v2 addresses it |
|---|---|
| §S1 prose classifier non-deterministic across executors | Abandoned; upstream trust.py is the single executable implementation, with tests |
| T5 manifest-key gate deadlock | No manifest-key source rewrites in scope (v1-T5's 8 source fixes are OUT of this plan; separate small task if wanted) |
| No pre-plan snapshot task | T0 Step 4 creates it before anything runs |
| No rollback story | Branch-first on both repos; every task commits on-branch |
| log/hot edits violated body-immutability constraint as written | Explicit carve-out in Global Constraints |
| `git add -A` sweeping unrelated files | Branches start clean (T0 Step 1 gate); per-task scoped commits |
| A1 self-verified | T4 requires an independent verifier to run the tooling on a scratch vault copy |
| Auto-promote Action 3 interaction | Old consolidate Action 3 keys on confidence>0.7 + age; post-adoption, lifecycle promotion is ledger-gated — T2 Step 3 checks consolidate text for coherence |
