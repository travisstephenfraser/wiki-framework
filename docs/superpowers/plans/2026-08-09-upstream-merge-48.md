# Plan: Merge 48 upstream commits (Ar9av/obsidian-wiki)

_Status: **SPEC v4 — not executed.** 2026-08-09. Two adversarial rounds, 11 independent verifiers.
Round 1 Contradicted v1's central recommendation; round 2 Contradicted three of v3's five new
claims. Every `[RT]` fact below was verified against the repos by a verifier that was given no
plan text. `[OPEN]` marks what is still unverified._

**Verdict: merge, but not yet.** Nothing found argues against merging. Everything found argues
that the safety machinery must exist first. Governing principle: **do not operate without a
monitor**, and today there is no monitor.

---

## 0. Position

```
merge-base  bf48502   2026-07-09      ours 8640339 (19 ahead)   upstream 8753916 (48 ahead)
trial merge: 8 conflicts — cli.py(13) lint.py(13) trust.py(26, add/add)
             test_trust.py(10, add/add) wiki-lint/SKILL.md(2) AGENTS.md README.md cache.py(2)
```

Vault baseline **2026-08-09**: 226 `.md` · 203 lint-visible · 199 trust-visible · ledger 44
entries (27 matching, **17 drifted**) · 7 pages with **invalid YAML frontmatter** · 17 pages with
no frontmatter · lint `status: fail` on 8 **false-positive** broken links. `[RT]`

---

## 1. P0 — Do this before anything else

**Back up `_raw/`. It is the least protected data in the system and it holds irreplaceable
primary sources.** `[RT]`

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

### P1 — Make the monitor real

1. **Fix `_WIKILINK_RE`** to handle escaped pipes (`| [[rubrica\|Rubrica]] |`). 8 false positives
   are why lint's resting state is `fail`. Regression test with a `\|` table row. `[RT]`
2. **Fix the 7 YAML-invalid frontmatters** (`kunal-cholera`, `sai-shriya-surla`,
   `independent-measurer-discipline`, `2026-07-03-systems-decomposition-lens`, `haas-scheduler`,
   `mountaineers-pitch`, `travis-systems-mind`) — unquoted plain scalars containing `: `, and
   `agent:claude-session` inside a flow sequence. ~10 minutes; raises parsed-fingerprint coverage
   **96.7% → 100%** and removes the design's largest false negative. `[RT]`
3. **Build the corruption manifest** to this shape — **not** the page-level frontmatter hash v3
   specified, which was measured inadequate on all three axes:

   ```
   <relpath> \t parse_status \t raw_fm_sha256 \t body_sha256 \t {key: typed_value_hash, …}
   ```

   - **Path-keyed.** An unkeyed sorted multiset makes a frontmatter swap between two pages and a
     page rename **both invisible**. Proven. `[RT]`
   - **Type-tagged.** `key=str(value)` misses `tags: [a,b]` → `"a, b"` and `0.42` → `"0.42"`. The
     latter breaks `float()` in `trust._parse_confidence`. `[RT]`
   - **Raw hash as fallback where `parse_status != ok`.** A raw hash alone false-positives on
     **200/202 pages (99%)** after a lossless YAML round-trip — the single most likely thing a
     migration does. A parsed hash alone is blind to the 7 malformed pages, and the vault's *own*
     T5–T9 migration rewrote exactly those while a parsed diff reported `PARSE_ERROR → PARSE_ERROR`.
     Neither alone is adequate. `[RT]`
   - **Body hash.** Frontmatter is **4.9% of vault bytes**; **99.6% of the 3,711 wikilinks live in
     bodies**. Reuse `trust.page_fingerprint`, which already hashes body + non-volatile
     frontmatter and succeeds 199/199. `[RT]`
   - **Report field-level, not page-level.** The real T5–T9 migration flags 181–187 of 205 pages —
     an unreadable wall. The same data as an added/removed/changed key histogram is four lines.
     `[RT]`
   - **Degeneracy assert that raises.** 24 of 226 pages (10.6%) collapse onto two sentinels
     (`PARSE_ERROR`, `NO_FRONTMATTER`). Per the measurement-sanity rule, unrelated classes
     saturating one value means the instrument is reading itself. `[RT]`
4. **Known-answer anchor.** Run the tool across the real schema migration `e785310^ → 843493b` and
   assert the field profile is exactly `ADDED: tier, base_confidence, lifecycle,
   lifecycle_changed`. A control that has never fired is not a control. `[RT]`
5. **Full-tree hash including gitignored files** — path, size, mode, symlink target — as the outer
   envelope. Subsumes deletion, addition, rename, permission and non-markdown damage.

**Known limit, accepted:** the framework uses **no YAML library** anywhere; `lint`, `trust`, and
`graphrag` are hand-rolled line parsers. Flow vs block `tags` is YAML-identical but yields
`'[ai, validation, meta]'` vs `''` from `lint._parse_frontmatter_values`. A parsed fingerprint can
therefore say "no change" where a consumer sees one. `raw_fm_sha256` is the mitigation. `[RT]`

### P2 — Decouple guard from guarded

1. **I1 is a re-apply, not a preserve.** `trust.py` and `tests/test_trust.py` arrive as **add/add**
   conflicts; upstream's `trust.py` is 723 lines against our 562 and carries features we lack, so
   every incentive says take theirs — which drops the exclusion and its only test together.
   **Proven remedy:** apply the two-token patch to upstream's rewritten `TRUST_SKIP_DIRS`/
   `SKIP_DIRS` → **78/78 pass**. Without it, 77 pass and the bug is back. `[RT]`
2. **Land the guard test as a separate post-merge commit** so it cannot die inside the conflict it
   guards.
3. **Add the missing lint-side test** — removing that exclusion today passes 213/213. `[RT]`
4. **Convert I2/I4 from grep to doc-tests.** Upstream already ships the pattern
   (`test_pre_write_snapshot_docs.py`, `test_wiki_narrate_docs.py`, `test_session_brain_docs.py`).
   In-idiom and cheap. `[RT]`

### P3 — Install surface

Reconcile `cli.py:117` against `setup.sh:177` (the "34 missing" warning is a measurement bug —
`setup.sh` deliberately installs a 2-skill subset). Register the 6 unlinked project-local skills.
**Fix the lowercase `/Users/travis/developer/` symlink targets before the devbox sees them** —
they resolve only on case-insensitive APFS. Recreate `/tmp/ow-testenv`; green on HEAD. `[RT]`

---

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
| O1 | The corruption manifest as specified in P1.3 has no remaining gap that matters here | `[OPEN]` — must be built and anchored before it counts |
| O2 | Doc-tests for I2/I4 actually fail when the prose is removed | `[OPEN]` |
| O3 | No interaction defect beyond §2.2–2.3 exists — `--consolidate`, `wiki-rebuild`/`export`/`import` round-trips, and `OBSIDIAN_ALLOWED_RELATIONSHIP_TYPES` were **not** covered | `[OPEN]` |
| O4 | `update_trust_ledger`'s deletion of newly-`not_applicable` entries is non-destructive under a config change | `[OPEN]` — partially evidenced only |
