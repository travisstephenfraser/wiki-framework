# Plan: Merge 48 upstream commits (Ar9av/obsidian-wiki)

_Status: **SPEC v5 — safety work EXECUTED, merge NOT executed.** 2026-08-09. Two adversarial
rounds, 11 independent verifiers. Round 1 Contradicted v1's central recommendation; round 2
Contradicted three of v3's five new claims. Every `[RT]` fact was verified by a verifier given no
plan text. `[DONE]` marks work now landed, with the commit. `[OPEN]` marks what is still
unverified._

> ## ⛔ VERDICT AFTER ROUND 3: **NO-GO.** Read §10 before acting on anything below.
>
> A third adversarial round (5 verifiers, run against the work itself rather than the plan)
> **Contradicted** both the corruption detector and the overall readiness claim. The
> "monitor now exists" table immediately below is **the claim that was refuted** — it is
> retained as the record of what was believed, not as current status. The detector on disk
> reports `RESULT: IDENTICAL` on real damage, and the vault's link graph — the thing that
> makes it a wiki — is invisible to every check in this plan.
>
> Recommendation carried forward: **not a safer merge, a smaller one** (§10).

**Verdict as of round 2 (SUPERSEDED): merge, but not yet.** Nothing found argues against
merging. Everything found argues that the safety machinery must exist first. Governing
principle: **do not operate without a monitor.**

**"The monitor now exists" — REFUTED in round 3, see §10.** Landed 2026-08-09 in `b8cb369`
(framework) and `86e2df9` (vault):

| Was | Now |
|---|---|
| lint `status: fail` on 8 false-positive broken links | `broken_links: 0`, `status: warn` — warn is the honest signal (17 stale ledger entries) |
| 7 pages whose frontmatter never parsed as YAML | **0** — and a parsed-frontmatter diff can now see all of them |
| Scope guard's only test inside the conflict it guards; lint half untested | `tests/test_fork_scope.py`; pulling the exclusion from **either** module fails 2 of 3 |
| No corruption detection of any kind | `scripts/vault_fingerprint.rb`, anchored against a real migration |
| 213 tests, no venv | 217 tests + 11 subtests green |

**Still outstanding before the merge may start:** P3.1–P3.3 (install-surface reconciliation, 6
unregistered project skills, lowercase symlink targets).

---

## 0. Position

```
merge-base  bf48502   2026-07-09      ours 8640339 (19 ahead)   upstream 8753916 (48 ahead)
trial merge: 8 conflicts — cli.py(13) lint.py(13) trust.py(26, add/add)
             test_trust.py(10, add/add) wiki-lint/SKILL.md(2) AGENTS.md README.md cache.py(2)
```

Vault, **as found 2026-08-09 (pre-fix)**: 226 `.md` · 203 lint-visible · 199 trust-visible ·
ledger 44 entries (27 matching, **17 drifted**) · **7 pages with invalid YAML frontmatter** · 17
with none · lint **`fail`** on 8 **false-positive** broken links. `[RT]`

Vault, **now (post-fix, `86e2df9`)**: 226 `.md` · **0 parse errors** · `broken_links: 0` ·
lint **`warn`**, the honest signal for 17 stale ledger entries. Ledger untouched — 44 entries,
`reviewed_at` unchanged.

---

## 1. P0 — DONE 2026-08-09

**`_raw/` backed up** to `/Users/travis/Developer/.vault/.raw-backup-2026-08-09.tar.gz`, 10/10 files verified. `[DONE]`

**Why it mattered — and why this is a standing exposure, not just a merge risk.** `_raw/` is the
least protected data in the system and it holds irreplaceable primary sources. `[RT]`

`_raw/` is in `SKIP_DIRS` **and** `TRUST_SKIP_DIRS`, is **gitignored**, and is **untracked** — so
lint, trust-check, any frontmatter fingerprint, and `git status` are all blind to it. It is also
the one directory the framework documents itself as deleting from (`.gitignore`: *"files are
consumed and deleted by wiki-ingest"*). ~260 KB currently: the Tripp check-in (69 KB), Albert sync
(57 KB), Cady/Alex intro (49 KB), Mountaineers transcript (41 KB), Khalil/Molly chat (32 KB).

Three of those arrived on 2026-08-09 from the transcripts-out-of-git decision. That decision was
right; it also moved irreplaceable sources into the blindest location in the system. **This is a
standing exposure, not a merge risk** — fix it regardless of what happens to this plan.

---

## 2. The design decision — settled, with a corrected hazard

**Keep `WIKI_SCHEMA_PHASE`. Adopt upstream's knobs alongside it. Do not migrate.** `[RT]`

The two govern different surfaces: `WIKI_SCHEMA_PHASE` has **zero Python readers** and gates what
write-skills **emit**; upstream's knobs parameterise the validator and gate what it **reports**.
Migration is impossible in any case — phase 2/3 are undifferentiated aliases, and our own
`.env.example` says the Python commands never read the variable.

### 2.1 CORRECTION to v3 — phase 0 is not unusable

v3 claimed phase 0 becomes unusable post-merge. **False.** `OBSIDIAN_REQUIRED_TRUST_FIELDS=updated`
drops `base_confidence`/`lifecycle` from requiredness while satisfying it via `updated`, which is
in `REQUIRED_FRONTMATTER` on both branches and is never phase-gated. A phase-0 vault was measured
at **`status: pass`, exit 0 — even under `OBSIDIAN_TRUST_STRICT=1`**. This is what upstream's
`not_applicable` / `base_confidence_absent_by_owner_schema` path exists for. Default behaviour is
`warn`/exit 0, not fail. **The devbox is a config task, not a correctness blocker.** `[RT]`

### 2.2 The real interaction bug — `tier` voids human approvals

The two layers gate **different four-field sets**:

| | fields |
|---|---|
| phase gate | `base_confidence` `lifecycle` `lifecycle_changed` **`tier`** |
| validator allowlist | `base_confidence` `lifecycle` `lifecycle_changed` **`updated`** |

They disagree on `tier`, and `tier` is **not** in `_VOLATILE_CONFIDENCE_KEYS`, so it **is** hashed
into `page_fingerprint`. Measured: bumping `updated` → fingerprint stable; churning the three
confidence fields → stable; **dropping `tier` → fingerprint changes → page goes `stale`,
`material_fingerprint_changed`.** `confidence_review_stale` is inside `trust_fails`, so under
strict this hard-fails — and **there is no escape hatch**, because `tier` is rejected by both
`OBSIDIAN_REQUIRED_TRUST_FIELDS` and `--required-trust-field` (argparse `choices`). `[RT]`

**Consequence: any phase-driven change in `tier` presence silently invalidates all 44 human trust
approvals.** Treat `tier` as frozen for the duration of this work. Assert ledger `reviewed_at`
unchanged as the tripwire (§5, gate 8).

### 2.3 Two documented-invocation defects

- **The escape hatch is inert as the skills invoke it.** `_resolve_schema_command_context` sets
  `config = {}` when the vault is passed **positionally**, and both branches' `wiki-lint` skill
  runs exactly `obsidian-wiki trust-check "$OBSIDIAN_VAULT_PATH" --strict`. The skill resolves the
  config, takes the vault path out of it, passes the path, and the CLI discards the rest —
  including `OBSIDIAN_REQUIRED_TRUST_FIELDS` and `OBSIDIAN_TRUST_STRICT`. Use `@name` or no-arg
  form. `[RT]`
- **Phase `1` and strict `1` mean opposite things.** Phase 1 = "downgrades every finding to a
  warning"; `OBSIDIAN_TRUST_STRICT=1` = "failures rather than warnings". We are at phase 1 with 17
  stale pages, and Rule 12e hard-codes `--strict` *inside* phase-gated Check 12. `[RT]`

---

## 3. Vault-writing surfaces the merge introduces

`[RT]` — full 48/48 commit classification. 34 of 41 non-trust commits are inert. These are not:

| Commit | Trigger | Writes |
|---|---|---|
| `b4e82e3` | **`obsidian-wiki setup`** with any vault path | 11 subdirs + `index.md`, `log.md`, `hot.md`, `.manifest.json`, `.obsidian/*` |
| `ea45081` | `setup` (interactive), `sync-setup`, `sync` | `git init`, `.gitignore`, remote, `add -A`, commit, **push** |
| `cb9d732`/`9113e17` | cross-linker · wiki-dedup · wiki-lint | `git add -A && git commit` in the vault |
| `8a70487` | `/wiki-narrate` **every run** | `log.md` append; `_readouts/` + page on `--save` |
| `14bdb41` | wiki-setup skill | `.manifest.json` |
| `3288eb6` | Cursor/Kiro/agent harnesses | rule text: "update `.manifest.json`, `index.md`, `log.md` after every operation" |

**`obsidian-wiki setup` becomes the most dangerous command in the system**, and three things push
you toward it: `_check_stale` nags after any version change; the bogus "34 skills missing" warning
invites it; and it silently **clobbers `~/.obsidian-wiki/config`**, dropping `WIKI_SCHEMA_PHASE`
(`write_config` writes exactly three keys). Unset = full enforcement, invisible to both checks
because the variable has no Python readers. `[RT]`

**Hard rule: `setup`, `sync`, and the three snapshotting skills are forbidden during this work and
may never be used as verification steps.**

---

## 4. Pre-merge work

### P1 — Make the monitor real `[DONE — b8cb369, 86e2df9]`

1. **`_WIKILINK_RE` fixed.** Escaped table pipes (`[[page\|Alias]]`) and footnote-wrapped links
   (`^[[[page|alias]]]`) captured malformed targets. Vault: `broken_links` 8 → **0**, status
   `fail` → `warn`. Two regression tests, one asserting the fix did **not** blind lint to a
   genuinely missing target.
2. **7 unparseable frontmatters fixed.** 4 block-mapping scalars containing `": "` → folded
   scalars (the convention 201 pages already use); 3 flow-sequence scalars containing `":"` →
   quoted. **Representation only** — each verified by parsing the new value and comparing against
   the pre-fix text: 7/7 IDENTICAL. Vault parse errors **7 → 0**.
3. **`scripts/vault_fingerprint.rb` built** to the measured shape: path-keyed · field-level ·
   type-tagged · raw-hash fallback where parsing fails · body hash · whole-tree envelope
   including gitignored paths · degeneracy assert that **raises**.
4. **Validated, not assumed:**
   - *Known-answer anchor* against the real T5–T9 migration reproduces
     `ADDED = {tier, base_confidence, lifecycle, lifecycle_changed}` at 180 pages (vault log
     records the backfill at 181) and `PARSE-ERROR = 6`, both matching independently derived
     ground truth.
   - *9 seeded corruption classes detected*: date mangled · list→string · float→string · enum
     flipped · field stripped · body truncated · page deleted · **gitignored `_raw` file
     deleted** · control (no change) correctly clean.
   - *Zero field-level false positives* on a full 209-page lossless YAML round-trip. A
     raw-hash-only design flags 200/202 on that same operation.

   **Building it surfaced two bugs in itself, both caught only by the anchor:** a missing
   `require 'time'` (`Time#iso8601` is not in `date`) that threw on every datetime, and a
   `rescue StandardError` broad enough to relabel that crash as *"the vault's YAML is bad"* — a
   defect laundered into a benign category, which is precisely the failure the tool exists to
   catch. The rescue is now `Psych::SyntaxError` only, so real bugs crash loudly. **This is the
   argument for the anchor: without ground truth the tool reported a plausible, wrong number and
   nothing would have contradicted it.**

### P2 — Decouple guard from guarded `[DONE — b8cb369]`

`tests/test_fork_scope.py` now holds the `_meta`/`_generated-skills` assertions, out of the
add/add conflict on `tests/test_trust.py`, plus the previously-missing lint-side coverage.
**Proven in a scratch copy:** pulling the exclusion from `lint.py` alone → 2 of 3 fail (it
previously passed 213/213); from `trust.py` alone → 2 of 3 fail; restored → green.

Still to do at merge time: **re-apply**, do not preserve. Upstream's `trust.py` is a 723-line
rewrite against our 562; the fix is a two-token patch onto *their* file, measured at **78/78**
where dropping it gives 77 green and the bug back. `[RT]`

### P3 — Install surface

4. **`[DONE]`** `/tmp/ow-testenv` recreated; **217 passed + 11 subtests**.
1. **`[OPEN]`** Reconcile `cli.py:117` (all skills) against `setup.sh:177` (deliberate 2-skill
   subset) — the "34 missing" warning is a measurement bug, and the reflex it invites
   (`obsidian-wiki setup`) is the single most destructive command post-merge (§3).
2. **`[OPEN]`** Register the 6 unlinked project-local skills.
3. **`[OPEN]`** Fix the lowercase `/Users/travis/developer/` symlink targets **before the devbox
   sees them** — they resolve only on case-insensitive APFS.

## 5. Invariants — corrected inventory

v3's I1–I4 double-counted, mis-described I3, and omitted the largest one. `[RT]`

| id | What it actually is | Merge behaviour | Check |
|---|---|---|---|
| **I1** | `_meta`/`_generated-skills` in `SKIP_DIRS` (`lint.py:13`) + `TRUST_SKIP_DIRS` (`trust.py:27`) | add/add conflict — **re-apply** | **behavioural** (P2.1) |
| **I2** | Page Creation Discipline gate, 5 skill files | clean auto-merge | grep → **doc-test** |
| **I3** | *Corrected:* one bullet at `wiki-lint/SKILL.md:122`, scoped to *"`provenance:` block + zero inline markers"* — **not** synthesis/concepts. v3 described `scratch_lint.js`, which `07a9851` **deleted**. Same line as I4's fourth item — **de-duplicated** | clean auto-merge | not behaviourally checkable; no code implements it |
| **I4** | Visibility guard · manifest-history rule · project-hub exemption (drift exemption = I3) | clean auto-merge | grep → **doc-test** |
| **I5** | **`WIKI_SCHEMA_PHASE`** — 23 files, zero upstream awareness. *Omitted from v3 entirely* | survives by upstream ignorance; rides on two heavily-rewritten skill files | file-count check (23) |

Loss impact if I1 goes: **17 unconditional findings** (9 `missing_frontmatter`, 8
`trust_metadata_errors`), outside `trust_fails`, unrelaxable by any knob or phase. `[RT]`

**No invariant dies silently** — every one either conflicts loudly or auto-merges intact. The
failure mode is a plausible-but-wrong resolution of a loud conflict. That is an attention problem,
not a detection problem. `[RT]`

Watch for two merge artifacts: a **duplicated `### 11. Synthesis Gaps`** in the merged
`wiki-lint/SKILL.md`, and upstream's new `context_pack.py` emitting vault content with
**`public_only: bool = False`** — visibility filtering off by default, on a surface I4 never
covered. `[RT]`

---

## 6. Sequence

| # | Step | Gate |
|---|---|---|
| 0 | **P0: back up `_raw/`** | copy exists outside the vault |
| 1 | P1, P2, P3 committed to `main` | anchor reproduces the T5–T9 profile; degeneracy assert raises on a seeded dupe; both scope tests fail when the exclusion is pulled from **either** file; 213+ green |
| 2 | Branch `merge/upstream-2026-08`; snapshot vault + ledger + `~/.obsidian-wiki/config` + `.env` | tarball incl. gitignored paths |
| 3 | **Capture the baseline with the NEW build** against a pristine pre-merge copy | old-tool vs new-tool findings diff is **unsound**: upstream changes findings keys, shrinks `REQUIRED_FRONTMATTER` 8→6, and alters scope — same vault yields *fewer* findings, masking regressions `[RT]` |
| 4 | `git merge upstream/main` | 8 conflicts expected; 4 of 5 cherry-picks dedupe; `588e80d` manual |
| 5 | Resolve file-by-file against §5. Never bulk `--ours`/`--theirs` | `git grep -c "_generated-skills" -- obsidian_wiki/{lint,trust}.py` == 2 |
| 6 | Tests green | 78/78 on the re-applied patch; ours + upstream's suites |
| 7 | Precedence note (§2) written | committed |
| 8 | Vault dry-run: `python3 -m obsidian_wiki lint` / `trust-check`, **read-only** `[RT]` | scope asserts: 199 trust pages, 203 lint pages, ledger **44 entries with `reviewed_at` unchanged** ← self-concealment tripwire |
| 9 | Corruption manifest + full-tree hash vs step 3 | byte-identical |
| 10 | Config assert: `WIKI_SCHEMA_PHASE` still present | — |
| 11 | Devbox: pull, align config (§2.1) | both machines agree |
| 12 | Merge to `main`, push | — |

**Prohibited throughout, in writing:** `obsidian-wiki setup` · `sync` / `sync-setup` ·
`trust-record --all` · the `wiki-lint` / `cross-linker` / `wiki-dedup` skills.

`trust-record --all` earns its own line: it recomputes every `material_fingerprint` from current
on-disk state, converting trust-check into a tautology and **permanently destroying** the ability
to detect body mutation. It is also the natural reflex when the scope change makes trust-check
fail. `[RT]`

---

## 7. Rollback

Framework: branch-based through step 11. Vault: untouched, but snapshotted at step 2 anyway —
"untouched" is a claim, and §3 shows how a differently-named command could violate it. Ledger:
backed up; regenerable, but **regenerating destroys the baseline** (above). Detection is the
corruption manifest; without it, rollback is a coin-flip on whether anyone notices in time.

---

## 8. Deferred

Tend the ledger on the documented weekly cadence or exit it via #162's `not_applicable` path —
"keep and drift" is ruled out. `[RT]` · The 155-page unreviewed tail · Upstream `--correction`
mode vs the vault's alias-hook convention · `3288eb6` agent context / `4bf87a8` session brain,
reviewed on merit not as merge cargo.

## 9. Still unverified

| id | Claim | Status |
|---|---|---|
| O1 | `vault_fingerprint.rb` as built and anchored has no remaining gap that matters for this merge | `[OPEN]` — built and validated, but validated **by its author**; the anchor already caught two self-inflicted bugs, so a third is not unlikely |
| O2 | The 7 frontmatter fixes changed representation only, on every field, with no semantic drift | `[OPEN]` — self-verified 7/7 IDENTICAL; not independently checked |
| O3 | The `_WIKILINK_RE` change does not blind lint to any link class it previously caught | `[OPEN]` — one regression test asserts a genuinely-missing target still reports; the space of link forms was not enumerated |
| O4 | `tests/test_fork_scope.py` survives an **actual** merge resolution, not just a scratch mutation | `[OPEN]` — proven against hand-removal, never against a real conflict resolution |
| O5 | No interaction defect beyond §2.2–2.3 — `--consolidate`, `wiki-rebuild`/`export`/`import` round-trips, and `OBSIDIAN_ALLOWED_RELATIONSHIP_TYPES` were **not** covered | `[OPEN]` |
| O6 | `update_trust_ledger`'s deletion of newly-`not_applicable` entries is non-destructive under a config change | `[OPEN]` — partially evidenced only |
| O7 | Doc-tests for I2/I4 fail when the prose is removed | `[OPEN]` — not yet written |

---

# 10. Round 3 — the work itself red-teamed (2026-08-09)

Five verifiers, each given a neutral claim about the *completed work*, none given this plan
or the commit messages. Round 3 attacked what rounds 1–2 produced.

| # | Claim | Verdict |
|---|---|---|
| R1 | `vault_fingerprint.rb` is an adequate corruption detector | **Contradicted** |
| R2 | The 7 frontmatter fixes are value- and consumer-neutral | Partially — value ✅, consumer ❌ |
| R3 | The `_WIKILINK_RE` change is strictly better | Partially — crux ✅, tests inadequate |
| R4 | The fork-scope guard is robust against a real merge | Partially — (b) ✅, (c) ❌ |
| R5 | The work is sufficient to perform the merge | **Contradicted — NO-GO** |

## 10.1 The convergent finding: the link graph is unguarded

Three verifiers reached it independently.

**Destroying links makes the link-damage metric go down.** 1,227 wikilinks mangled across 40
pages on a copy: lint status `warn` → `warn`; `broken_links` 0 → **0**; `links` 3728 → 2501.
`vault_fingerprint.rb` reports only `BODY: 41 page(s)` — indistinguishable from the 181–187
pages a real migration changes by design. **The detector has no link awareness at all.** This
is the exact failure `~/.claude/rules/measurement-sanity.md` demands an assertion against, built
into the instrument meant to prevent one.

Corroborating, from the other two: `graphrag.py:45` and `graph_analysis.py:40` still carry the
**old** wikilink pattern, so the graph the vault is queried through is still wrong in the same 8
places lint stopped reporting (R3). And upstream's new `context_pack.py:16` defines a **fourth**
vault scanner with its own `SKIP_DIRS`, uncovered by the fork guard (R4).

## 10.2 Detector defects (R1) — the script on disk is DEFECTIVE

| id | Defect |
|---|---|
| D1 | `clean` omits `pages_added`/`tree_added` → **`RESULT: IDENTICAL`, exit 0 on any addition**, while the line above prints `pages +1`. Leftover `.orig`/`.rej` files and duplicated pages are the likeliest merge artifacts |
| D2 | `h[k] \|\| h[k.to_sym]` collapses `false` and `nil` onto `sha("n:")` |
| D3 | Non-String YAML keys (`2026: alpha`) always hash as `n:` |
| D4 | `raw_fm_sha256` compared **only** in the `PARSE_ERROR` branch — captured and never read for the ~92% that parse |
| D5 | That branch is unreachable: the degeneracy check raises before `File.write` |
| D6 | `anchor` asserts nothing, exits 0 even on a wiped vault |
| D7 | Invalid UTF-8 crashes uncaught |
| D9 | A parse error is labelled "measurement may be reading itself" — wrong diagnosis, and it refuses to write a manifest |

**The anchor did not validate anything.** It reports **180** against a git-documented **186**
(`8f58fdb`); the 6-page gap is the unparseable pages. The reconciliation `180 + 6 == 186` was
performed *in a human's head*, not in code. A known-answer test that cannot fail is not one.

## 10.3 Test adequacy (R3) — mutation-proven inadequate

Baseline 217 passing. Mutants that **survive all tests**: a pattern losing **464 of 3728 real
links** (12% of the graph); a pattern blind to every heading-anchored link; a pattern that drops
the `[`-exclusion entirely. Structural cause: the footnote test asserts an **absence**
(`broken_links == []`), which any under-matching implementation satisfies. Only the escaped-pipe
half has a presence assertion.

## 10.4 The guard is real but nothing runs it (R4)

Good news, better than claimed: the guard file **never conflicts** (upstream has no such file),
survives `git checkout upstream/main -- .`, and fails behaviourally — driving real `lint_vault`
and `build_trust_ledger` calls, not constant checks. Under `--theirs` on all 9 conflicts, all
3 tests fail with messages naming the exact directories.

Bad news: **no CI, no hook, no scheduled job runs the suite.** And pytest aborts the whole
session on any collection error, so two plausible per-file resolutions leave the exclusion gone
*and* `pytest tests/` collecting **zero tests** — one of them erroring inside the guard's own
file with an unrelated `ImportError` that reads as stale-fork noise.

## 10.5 Operational state (R5)

- **No baseline was ever captured.** A comparator with no `before.json` detects nothing.
- Safety commits were **unpushed** until 2026-08-09; all three backups sit on one volume with
  **no Time Machine**.
- **Devbox offline 5 days**; ruby presence there unverified, and the detector needs it.
- **No benefit for this merge is written down anywhere** outside this document. The 48 commits
  weight heavily toward README translations, `wiki-narrate`, and history-ingest skills for other
  agents.

## 10.6 Revised recommendation

**Not a safer merge — a smaller one.** Cherry-pick `5016cde` + `95424e4` (cache), `9c260f7`
(packaging), `14bdb41`; **decline `2363445`** (`strict_trust` duplicates the fork's own gate).

Preconditions before *any* merge, cherry-pick included:

1. Fix D1–D7/D9, then re-anchor with a stored `expect.json` the tool cannot influence.
2. **Add link-count awareness** — per-page wikilink counts and a total-delta assertion. Without
   it the detector cannot see the vault's most valuable structure.
3. Commit a baseline: `links: 3728, broken_links: 0, pages: 203, parse_error: 0`, plus a real
   captured manifest.
4. Port the wikilink pattern to `graphrag.py` and `graph_analysis.py`.
5. Add presence-asserting link tests (kill the M2/M9/M11/M12 mutants).
6. A CI job running `pytest tests/ -q --continue-on-collection-errors`, or the guard is
   decorative.
7. Extend the guard to `context_pack.SKIP_DIRS`.
8. Bring the devbox up, or explicitly accept deferred reconciliation.
