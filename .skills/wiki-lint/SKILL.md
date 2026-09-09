---
name: wiki-lint
description: >
  Audit and maintain the health of the Obsidian wiki. Use this skill when the user wants to check their
  wiki for issues, find orphaned pages, detect contradictions, identify stale content, fix broken wikilinks,
  or perform general maintenance on their knowledge base. Also triggers on "clean up the wiki",
  "what needs fixing", "audit my notes", or "wiki health check". Add --consolidate to switch from
  report-only to act-and-report mode (the "dream cycle"): fixes broken links, adds missing cross-references
  for orphans, corrects lifecycle states, demotes stale peripheral pages, normalizes tag aliases, and adds
  contradiction callouts — all with a dry-run preview and explicit user confirmation before any writes.
---

# Wiki Lint — Health Audit

You are performing a health check on an Obsidian wiki. Your goal is to find and fix structural issues that degrade the wiki's value over time.

**Before scanning anything:** follow the Retrieval Primitives table in `llm-wiki/SKILL.md`. Prefer frontmatter-scoped greps and section-anchored reads over full-page reads. On a large vault, blindly reading every page to lint it is exactly what this framework is built to avoid.

## Before You Start

1. **Resolve config** — follow the Config Resolution Protocol in `llm-wiki/SKILL.md` (inline `@name` override → walk up CWD for `.env` → `~/.obsidian-wiki/config` → prompt setup). This gives `OBSIDIAN_VAULT_PATH`
2. Read `index.md` for the full page inventory
3. Read `log.md` for recent activity context

## Lint Checks

Run these checks in order. Report findings as you go.

### 1. Orphaned Pages

Find pages with zero incoming wikilinks. These are knowledge islands that nothing connects to.

**How to check:**
- Glob all `.md` files in the vault
- For each page, Grep the rest of the vault for `[[page-name]]` references
- Pages with zero incoming links (except `index.md` and `log.md`) are orphans

**How to fix:**
- Identify which existing pages should link to the orphan
- Add wikilinks in appropriate sections

### 2. Broken Wikilinks

Find `[[wikilinks]]` that point to pages that don't exist.

**How to check:**
- **Mask code first.** Blank fenced blocks (```` ``` ````/`~~~`) and inline code spans in the page **body** before extracting anything. A wikilink inside backticks is an *illustration of the syntax, not a reference to a page* — Obsidian does not render it as a link either. Skipping this mints a broken link every time a page documents wikilink syntax: it happened three times in one session on 2026-08-29, including inside the page describing the fix. **Do not mask frontmatter** — `relationships:` targets live there and are real typed edges that must keep resolving. Strip fences *before* inline spans, so a fenced block containing stray backticks cannot leave an unbalanced span behind. (Fork policy, commit `d633ed7`; implemented in `lint.py::_strip_code`.)
- Grep the masked text for `\[\[.*?\]\]` across all pages
- Extract the link target: drop everything from the first `|` (alias) or `#` (heading/block anchor), and **unescape a table-escaped `\|` before splitting** — `[[page\|Alias]]` must yield `page`, never `page\`
- Skip a target whose extension is an attachment type (`.png`, `.jpg`, `.gif`, `.svg`, `.webp`, `.pdf`, `.canvas`, `.base`, audio and video): it is an embed, not a page link, and has no entry in the `.md` inventory this check compares against
- Do **not** treat every dot as an extension — `[[Node.js]]`, `[[Next.js]]`, and `[[v1.2 release notes]]` are page links whose names happen to contain a dot, and dropping them would both miss real broken links and make the target page look like an orphan
- Strip an explicit `.md` suffix from what remains, then check if a corresponding `.md` file exists
- **Nested-bracket edge case:** a wikilink inside an inline footnote reads `^[[[page#heading|text]]]` — three opening brackets in a row. A greedy `[[...]]` match swallows the leading `^[` and yields a bogus target. Match the *innermost* `[[...]]` pair. Live example: `projects/strava-pm/skills/pm-casing-framework.md`.

**Why this recipe is this specific:** the earlier three-line version ("extract the link targets, check a `.md` exists") is not merely noisy — Consolidate Action 1 consumes this check's output and used to rewrite what it found. Measured on a 247-page vault, the naive recipe flags **597** links as broken where **2** are genuine: 530 plain aliases, 114 heading anchors, 8 table-escaped pipes. Upstream fixed the same defect in PR #206 for exactly this reason.

**Cross-check (optional):** `python3 -m obsidian_wiki lint <vault> --json` implements this recipe in code (`_WIKILINK_RE`, `_normalise_node_id`, `_strip_code`) and is the faster path on a large vault. **One divergence to know:** `lint.py` skips `_meta/`, so a link whose target lives there (e.g. `[[machine-parity]]` → `_meta/machine-parity.md`) is reported broken by the CLI but is not broken. The prose recipe above globs every page and is correct on those. Reconcile in favour of the prose.

**How to fix:**
- If the target was renamed, update the link
- If the target should exist, create it
- If the link is wrong, remove or correct it
- **Never convert a link to plain text just because it did not resolve** — see Consolidate Action 1. A broken link that stays visible gets fixed on a later pass; a silently unlinked one does not.

### 3. Missing Frontmatter

Every page should have: title, category, tags, sources, created, updated.

**How to check:**
- Grep frontmatter blocks (scope to `^---` at file heads) instead of reading every page in full
- Flag pages missing required fields

**How to fix:**
- Add missing fields with reasonable defaults

### 3a. Missing Summary (soft warning)

Every page *should* have a `summary:` frontmatter field — 1–2 sentences, ≤200 chars. This is what cheap retrieval (e.g. `wiki-query`'s index-only mode) reads to avoid opening page bodies.

**How to check:**
- Grep frontmatter for `^summary:` across the vault
- Flag pages without it, **but as a soft warning, not an error** — older pages predating this field are fine; the check exists to nudge ingest skills into filling it on new writes.
- Also flag pages whose summary exceeds 200 chars.

**How to fix:**
- Re-ingest the page, or manually write a short summary (1–2 sentences of the page's content).

### 4. Stale Content

Pages whose `updated` timestamp is old relative to their sources.

**How to check:**
- Compare page `updated` timestamps to source file modification times
- Flag pages where sources have been modified after the page was last updated

### 5. Contradictions

Claims that conflict across pages.

**How to check:**
- This requires reading related pages and comparing claims
- Focus on pages that share tags or are heavily cross-referenced
- Look for phrases like "however", "in contrast", "despite" that may signal existing acknowledged contradictions vs. unacknowledged ones

**How to fix:**
- Add an "Open Questions" section noting the contradiction
- Reference both sources and their claims

### 6. Index Consistency

Verify `index.md` matches the actual page inventory.

**How to check:**
- Compare pages listed in `index.md` to actual files on disk
- Check that summaries in `index.md` still match page content
- **Project-hub exemption:** a page is considered indexed if it appears in `index.md` OR is wikilinked from its project hub page (`projects/<name>/<name>.md`). Project-scoped pages deliberately stay off the root index and live on their hub — do not flag them as missing, and never "fix" by bulk-adding hub-listed pages to `index.md`. Only flag pages reachable from neither the index nor any hub.

### 7. Provenance Honesty

Check whether pages are being honest about how much of their content is inferred vs extracted. See the Provenance Markers section in `llm-wiki` for the convention.

> **Heading renamed and the numeric drift rule retired, 2026-09-09.** Upstream still ships both as "Provenance Drift". This is a deliberate fork divergence and a **trap patch** — a merge that restores the drift rule reintroduces a measurement known to be defective on this vault. Evidence, and the criterion for reversing this, are in "Retired: the drift rule" at the end of this check.

**How to check:**

- For each page with a `provenance:` block or any `^[inferred]`/`^[ambiguous]` markers, count **claim units** and how many carry each marker
- **Claim unit** = one bullet (`-`/`*`) or numbered list item. It is *not* a non-blank line. Using lines as the denominator silently inflates `extracted`, because prose paragraphs, headings, table rows, and code lines all land in the denominator while only bullets typically carry markers. On a real page this read 0.05 inferred by line vs 0.21 by claim unit — a 4× understatement, entirely an artifact of the denominator.

  **⚠ This definition is under review and is the fork's outlier.** Upstream `wiki-lint` and this fork's own write-side spec (`llm-wiki`, Provenance Markers) both say *sentences/bullets*; only this file says bullets-only. The two definitions differ by roughly **5×** on real pages, which is enough to move every threshold below. Until that is resolved, treat any fraction this check produces as denominator-dependent and **do not tune a threshold against it**. Whichever definition wins, record it in the LINT log line (see Instrumentation).

- **Exclude markers inside code from the numerator.** Blank fenced blocks and inline code spans in the body before counting, exactly as Check 2 does. Otherwise the page that *defines* these markers reads as maximally synthetic, because the check is counting its own vocabulary — the measurement reading its own inputs. (Measured 2026-09-09: 2 pages, 3 markers. Small in aggregate, but it lands precisely on the pages documenting the instrument, which is where a self-reading measurement does the most damage.)
- Compute rough fractions (`extracted`, `inferred`, `ambiguous`)
- **Run the boundedness assertions below before reporting any fraction.**
- Apply these thresholds:
  - **AMBIGUOUS > 15%**: flag as "speculation-heavy" — even 1-in-7 claims being genuinely uncertain is a signal the page needs tighter sourcing or should be moved to `synthesis/`
  - **INFERRED > 40% with no `sources:` in frontmatter**: flag as "unsourced synthesis" — the page is making connections but has nothing to cite
  - **Hub pages** (top 10 by incoming wikilink count) with INFERRED > 20%: flag as "high-traffic page with questionable provenance" — errors on hub pages propagate to every page that links to them
- **Skip** pages with no `provenance:` frontmatter and no markers — treated as fully extracted by convention
- **Marker grammar**: match markers by prefix, not exact literal — `^[inferred` covers `^[inferred]` and long-form variants like `^[inferred from X]`; `^[ambiguous` likewise. Explicit extracted marks (`^[extracted]`, `^[stated directly]`) count as marked-extracted claims, not as unmarked.

#### Boundedness assertions (required — raise, do not warn)

A fraction outside [0,1] is not a finding about a page, it is proof the instrument is broken. Check all three **before** any number reaches the report. On failure, **raise and suppress that page's fractions**; never round, clamp, or print the impossible value.

1. **`claim_units > 0` before dividing.** A page with markers and zero claim units is a divide-by-zero, not a 100%-anything page. Report it as a measurement failure naming the page.
2. **`markers <= claim_units`.** If a page carries more markers than the denominator has units, the denominator does not contain the numerator's population. That is a unit mismatch, and no tolerance value repairs a unit mismatch.
3. **`0 <= fraction <= 1`** for every computed fraction on every page.

**Expect assertion 2 to fire today, and expect that to be correct.** Measured 2026-09-09 on 247 content pages: **18 pages carry more markers than bullets**, because this vault's house style puts markers on prose paragraphs. The assertion is not a bug report about those pages, it is the bullets-only denominator refusing to produce a number it cannot justify. It clears when the denominator question is settled — not before, and not by loosening the assertion.

#### Known-answer fixture (required)

Assertions that only ever pass prove nothing. Per `guards-that-do-not-guard`, every absence assertion needs a presence one, so this check carries pages that must go **red** and a page that must go **green**. Anchor on the *property*, not on the counts — these pages are live and their marker counts move.

| anchor | property | must |
|---|---|---|
| `projects/cs160-prog1/cs160-prog1.md` | markers present, **zero** bullets | **RAISE** assertion 1 (divide-by-zero) |
| `skills/cross-link-detector-traps.md` | markers **exceed** bullets | **RAISE** assertion 2 (unit mismatch) |
| `references/macos-migration.md` | markers ≤ bullets, all fractions in range | **PASS** — fractions reported, nothing raised |

If all three pass, or all three raise, the fixture is not discriminating and the check is untrustworthy regardless of what it reported. Reference values measured 2026-09-09 under the bullets denominator, recorded so fixture drift is visible rather than silent: cs160-prog1 = 6 markers / 0 bullets; cross-link-detector-traps = 24 markers / 5 bullets; macos-migration = 6 markers / 6 bullets, inferred 0.500, ambiguous 0.000.

#### Degeneracy assertion (required)

After computing findings, check the direction split. If **every** flagged page — or all but one — moves on the same field in the same direction, **the measurement is broken; report that and suppress the page list.** A real population is mixed. A one-directional sweep means the estimator is reading its own denominator, marker convention, or gate, not the pages. This costs one comparison and is the difference between reporting one defect and filing 25 false ones. (Fork-local; no upstream equivalent. Also relied on by Check 8 and by `cross-linker` — do not delete it with the drift rule.)

#### Retired: the drift rule (2026-09-09)

The rule "flag any `provenance:` field more than 0.20 off the recomputed value" is **deleted**, along with its density gate, its residual-bias tolerance, and its How-to-fix. Retired, not repaired.

Why, kept because the evidence is the reversal criterion:

| measure | value |
|---|---|
| LINT runs recording `prov_issues` | 21 |
| page edits ever attributable to provenance drift | **1** (2026-04-18, predates the current marker spec) |
| pages admitted by the ratio gate on the current vault | 41 of 247 (2026-09-09) |
| standing state per this skill's own former text | "expect the degeneracy assertion to fire" |

Every run since 2026-05-14 resolved to a statement about the instrument rather than about a page: *"dismissed as noise, denominator too small"*, *"20 recompute hits dismissed as documented sparse-marking false-positive class"*, *"CHECK 7 IS DEFECTIVE AS SPECIFIED"*, and finally *"recomputed to −0.20 extracted, impossible."* A rule whose only possible output is "the instrument is broken" is not a quiet guard; it is a permanently red light with an empty action list, across five months.

The structural reason it cannot work: it differences a **holistic write-time judgment** against a **marker count**. Those are different populations — `measurement-universe-mismatch` by name — and no tolerance value repairs a unit mismatch. Measured 2026-08-13/15: declared `extracted` runs a systematic **~0.13 low** against any marker-based recompute (mean absolute error 0.126 against the documented "fraction with no marker" definition, 0.125 against a marked-claims-only definition — statistically indistinguishable, i.e. the write skills follow *neither* documented definition and emit holistic estimates). A 0.20 tolerance clips the tail of a systematic offset rather than detecting per-page drift, so survivors are one-directional by construction.

Two lessons worth keeping even though the rule is gone. **A density gate must be a ratio, not a count**: an absolute threshold does not scale with page length, and on 2026-08-13 the count gate admitted 25 pages of which every one drifted the same way, while the ratio gate admitted 27 and split 18-high/8-low. **Never auto-overwrite a declaration with an estimate**: writing the recompute over the declared block destroys the better number and makes the page self-consistent with a defective measure, so the finding disappears on the next run for the wrong reason.

**Reversal criterion (pre-registered).** Reinstate a drift comparison only when the write side and the lint side compute `provenance:` by the *same* documented rule, and a run demonstrates a mixed-direction flagged population. Absent both, it stays retired.

**How to fix:**
- For ambiguous-heavy: re-ingest from sources, resolve the uncertain claims, or split speculative content into a `synthesis/` page
- For unsourced synthesis: add `sources:` to frontmatter or clearly label the page as synthesis
- For hub pages with INFERRED > 20%: prioritize for re-ingestion — errors here have the widest blast radius
- For a raised boundedness assertion: **fix the instrument, not the page.** The page is not wrong; the count is. Resolve the denominator question first.

#### Instrumentation (record on every run)

Add to the `LINT` log line, so the next person to argue about the denominator has more than one run to argue from:

- `prov_units_definition=` — `bullets` or `sentences+bullets`. Which denominator this run used.
- `prov_pages_gated=` — pages skipped by the no-block/no-marker skip rule.
- `prov_assert_raised=` — how many boundedness assertions fired.
- `prov_over_unity=` — pages where `markers > claim_units`. This is the number that decides the denominator question; log it every run, unconditionally, even when it is zero.

### 8. Fragmented Tag Clusters

Checks whether pages that share a tag are actually linked to each other. Tags imply a topic cluster; if those pages don't reference each other, the cluster is fragmented — knowledge islands that should be woven together.

**Exclude system tags first.** Skip every `status/` and `visibility/` tag. Pages do not link each
other for sharing a lifecycle state, so cohesion over `#status/active` measures nothing.

**How to check:** for each *domain* tag on ≥ 5 pages, build the subgraph of those pages and the
wikilinks between them (either direction), then compute:

- `isolated` = pages with **zero** in-tag links; `isolated_frac = isolated / n`
- `components` = connected components in the subgraph
- `cohesion = actual_links / (n × (n−1) / 2)` — **context only, not the primary gate**

Flag when **`isolated_frac > 0.30`**, or when **`n ≤ 12` and `cohesion < 0.15`**.

**Cohesion alone is n-biased — never threshold on it at scale.** The denominator `n(n−1)/2` grows
quadratically while a page's realistic link budget does not, so a large tag is mathematically
unable to clear a fixed 0.15 bar: `#ai` at n=66 would need 322 internal links, i.e. every page
linking ~10 others *within that one tag*. The failure is not hypothetical — measured on this vault
(2026-08-29): `#validation` (n=47) scores cohesion 0.119 and reads "fragmented", yet it has **zero
isolated pages and exactly one connected component** — every page reaches every other. The raw
cohesion gate flagged 9 tags; the isolation gate flagged 1, and that 1 was the only group a human
read confirmed. `isolated_frac` and `components` are n-invariant, which is why they carry the gate.

**Known-answer anchor:** `#calibration` (n=5) sat at cohesion 0.000 with 5/5 pages isolated across
2 lints (2026-08-13, 2026-08-29). After the cross-linker pass added 6 edges it reads cohesion 0.600,
0 isolated, 1 component. A revision of this check must flag it in the first state and clear it in
the second; if it does neither, the metric is broken, not the vault.

**How to fix:**
- Run the `cross-linker` skill targeted at the fragmented tag — it will surface and insert the missing links
- Prefer linking the **isolated** pages specifically; they are the finding, not the cohesion number
- If a tag group is large (n > 15) and genuinely fragmented (high `isolated_frac`, several components), consider splitting it into more specific sub-tags

### 9. Visibility Tag Consistency

Checks that `visibility/` tags are applied correctly and aren't silently missing where they matter.

**How to check:**

- **Untagged PII patterns:** Grep page bodies for patterns that commonly indicate sensitive data — lines containing `password`, `api_key`, `secret`, `token`, `ssn`, `email:`, `phone:` followed by an actual value (not a field description). If a page matches and lacks `visibility/pii` or `visibility/internal`, flag it as a likely mis-classification.
- **`visibility/pii` without `sources:`:** A page tagged `visibility/pii` should always have a `sources:` frontmatter field — if there's no provenance, there's no way to verify the classification. Flag any `visibility/pii` page missing `sources:`.
- **Visibility tags in taxonomy:** `visibility/` tags are system tags. A dedicated reserved/system section in `_meta/taxonomy.md` that *documents* them (and states they don't count toward the tag limit) is the sanctioned layout — do not flag it. Flag only when `visibility/` tags are listed among the countable domain/project/descriptor tags, where they'd be miscounted toward the 5-tag limit.

**How to fix:**
- For untagged PII patterns: add `visibility/pii` (or `visibility/internal` if it's team-context rather than personal data) to the page's frontmatter tags
- For missing `sources:`: add provenance or escalate to the user — don't auto-fill
- For taxonomy contamination: move the `visibility/` entries out of the countable tag tables into a reserved/system section of `_meta/taxonomy.md`

### 10. Misc Promotion Candidates

Find pages in `misc/` that have accumulated enough project affinity to be promoted.

**How to check:**
- Glob `$OBSIDIAN_VAULT_PATH/misc/*.md`
- For each page, read the `affinity` frontmatter field
- Flag pages where any single project's score ≥ 3

**How to fix:**
- Run the `cross-linker` skill first if affinity scores look stale (e.g., `affinity: {}` on a page with many wikilinks)
- To promote: move the page to `projects/<project-name>/references/` (or another appropriate category), update its `category` frontmatter, remove `promotion_status`, and grep the vault for backlinks to update them

### 11. Synthesis Gaps

Identify high-value synthesis opportunities the wiki is missing — concept pairs that co-occur across many pages but have no `synthesis/` page connecting them.

**How to check:**
- List all pages in `synthesis/` — collect the concept pairs each one already covers (from its `[[wikilinks]]` or title)
- Pick 10-15 frequently linked concepts from `concepts/` and `entities/`
- For each pair, run a quick grep to count pages that link to both:
  ```bash
  grep -rl "\[\[ConceptA\]\]" "$OBSIDIAN_VAULT_PATH" --include="*.md" > /tmp/a.txt
  grep -rl "\[\[ConceptB\]\]" "$OBSIDIAN_VAULT_PATH" --include="*.md" > /tmp/b.txt
  comm -12 <(sort /tmp/a.txt) <(sort /tmp/b.txt) | wc -l
  ```
- Flag pairs with co-occurrence ≥ 3 that have no existing synthesis page

**How to fix:**
- Run `/wiki-synthesize` to automatically discover and fill the top gaps

### 12. Confidence and Lifecycle Schema

Enforces the confidence + lifecycle frontmatter schema (see `llm-wiki/SKILL.md`, Confidence and Lifecycle section). **Opt-out:** if `WIKI_SCHEMA_PHASE=0` in the resolved config, skip Check 12 entirely (all rules, all output) — the vault has opted out of the confidence/lifecycle schema.

Two modes:
- **`--check`** (default, read-only) — reports errors and warnings
- **`--consolidate`** — may apply separately approved structural maintenance, but **never rewrites `base_confidence`**

Confidence is a semantic judgment. A deterministic tool cannot infer independent evidence lineages or whole-page claim coverage from source strings alone. Confidence automation therefore validates an explicitly approved manual trust ledger; it never substitutes URL counting for review.

#### Rule 12a — `lifecycle` enum validation

**How to check:** Grep frontmatter for `^lifecycle:` across all pages. Flag any value not in `{draft, reviewed, verified, disputed, archived}`.

**How to fix:** n/a (only a human should set lifecycle state)

#### Rule 12b — `base_confidence` range

**How to check:** Grep frontmatter for `^base_confidence:` across all pages. Flag any value outside `[0.0, 1.0]` or any page missing the field entirely.

**How to fix:** n/a (wrong value means the skill computed it wrong — surface for manual correction)

#### Rule 12c — Stale page report (computed overlay)

Staleness is never stored — it is computed at read time: `is_stale = (today − updated) > 90 days`.

**How to check:** For each page, read `updated:` from frontmatter and compute `is_stale`. If stale, also check `lifecycle:`. Report:
- Stale pages with `lifecycle: verified` with a louder annotation (these are the most dangerous — high-trust pages that may be wrong)
- All other stale pages as a standard warning

**How to fix:** `--fix` does **not** rewrite `lifecycle`. Staleness clears automatically when a re-ingest bumps `updated`.

#### Rule 12d — Supersession integrity

**How to check:** For each page with `superseded_by: "[[target]]"`:
- Verify the target page exists
- Verify the target page is not itself `archived` (no circular or chained supersession)
- Verify there are no cycles (A supersedes B which supersedes A)
- Warn if `lifecycle != archived` while `superseded_by` is set (inconsistent state)

**How to fix:** n/a — flag for human resolution

#### Rule 12e — Confidence review integrity

**How to check:** Run the deterministic ledger validator first:

```bash
obsidian-wiki trust-check "$OBSIDIAN_VAULT_PATH" --strict --json --pretty
```

Use `--strict` for CI and scheduled gates: stale, unreviewed, or missing-page
warnings then return nonzero. Without `--strict`, `trust-check` remains a
read-only reporting command and returns nonzero only for hard ledger errors or
score mismatches.

The approved ledger lives at `_meta/trust-ledger.json`. Each entry records the human-reviewed score plus a SHA-256 fingerprint of material page content and evidence metadata. The fingerprint excludes volatile bookkeeping (`updated`, `base_confidence`, and lifecycle transition fields), so timestamp-only edits do not reopen review.

Interpret results as follows:

- `reviewed` — current material fingerprint and stored score both match the approved review; do **not** recompute from source strings.
- `stale` — body, summary, sources, provenance, tags, or relationships changed; perform a new manual lineage + claim-coverage review.
- `unreviewed` — page has no approved ledger entry; manual review is required.
- `score_mismatches` — material content still matches, but stored `base_confidence` differs from the approved value; fail the lint.
- `errors` — malformed/missing ledger data; fail the lint.

For a separately approved full-vault review, record the accepted state explicitly:

```bash
obsidian-wiki trust-record "$OBSIDIAN_VAULT_PATH" \
  --all --reviewed-at "<ISO-8601 timestamp>" --approved --json --pretty
```

After a separately approved review of only specific stale/unreviewed pages, update only those entries:

```bash
obsidian-wiki trust-record "$OBSIDIAN_VAULT_PATH" \
  --page "concepts/example.md" --page "skills/example.md" \
  --reviewed-at "<ISO-8601 timestamp>" --approved --json --pretty
```

`--approved` means a human approved every score being recorded. It is a workflow
assertion, not a cryptographic signature: keep `_meta/trust-ledger.json` under
version control and require human diff review before merging ledger changes.
`--all` is valid only after a full-vault review; use repeatable `--page` for
partial reviews so unrelated stale pages remain open. Never run `trust-record`
merely to silence warnings.

**Manual recomputation protocol for stale/unreviewed pages:**

1. Decompose the page into material claims and map each claim to evidence.
2. Collapse dependent evidence into independent lineages: files/commits from one repository, retries in one task chain, snapshots plus their captured source, duplicate memories, and parent/child tasks each count once.
3. Assign reviewed quality per independent lineage using `llm-wiki` buckets.
4. Compute the raw base score, then assess whole-page claim coverage. The formula is a starting point, not an automatic target.
5. Classify the result as `raise`, `keep`, `lower`, or `repair first`; require approval before changing `base_confidence` or refreshing the ledger.

**How to fix:** There is no automatic confidence fix. Apply only an explicitly approved exact patch, verify its scope, then refresh only the reviewed ledger state. `--consolidate` must never rewrite `base_confidence`.

#### Current enforcement

Full enforcement is active. Every non-reserved content page must contain a
finite `base_confidence` in `[0.0, 1.0]` and a documented lifecycle value.
Missing or malformed trust fields, malformed ledger data, and a missing required
ledger are hard errors. New pages with valid trust fields but no approved ledger
entry are `unreviewed`; material changes to approved pages are `stale`.

**Phase determination (fork-local):** `WIKI_SCHEMA_PHASE` in the resolved config gates enforcement — `0` skips Check 12 entirely (see Opt-out above), `1` downgrades every finding in this check to a warning (transition mode for a vault mid-backfill), `2`/`3`/unset applies the full enforcement described above.

#### Output additions

Add to the Wiki Health Report:

```markdown
### Confidence/Lifecycle Issues (N found)
- `concepts/foo.md` — missing `lifecycle` field (warning: Phase 1)
- `entities/bar.md` — `lifecycle: stalestate` is not a valid enum value
- `concepts/scaling.md` — `base_confidence: 1.4` is out of range [0.0, 1.0]
- `synthesis/old-analysis.md` — STALE (last updated 2025-10-01, 182 days ago) lifecycle=verified ⚠️ HIGH PRIORITY
- `concepts/outdated.md` — STALE (last updated 2025-11-15, 137 days ago) lifecycle=draft
- `entities/tool-v1.md` — `superseded_by: [[entities/tool-v2]]` but lifecycle=draft (expected archived)
- `concepts/drift-example.md` — confidence review stale: material fingerprint changed; manual lineage + coverage review required
- `entities/mismatch.md` — confidence mismatch: stored=0.80, approved=0.59
```

Append to the `LINT` log entry:
```
- [TIMESTAMP] LINT ... lifecycle_issues=N
```

### 13. Typed Relationships Validity

Validate `relationships:` frontmatter blocks. Skip pages that have no `relationships:` block — the field is optional.

**Allowed types:** `extends`, `implements`, `contradicts`, `derived_from`, `uses`, `replaces`, `related_to`

**How to check:**
- Grep frontmatter for `^relationships:` across all vault pages
- For each page that has a `relationships:` block, read its frontmatter (not the full page body)
- For each entry in the block:
  1. **Type validation** — flag any `type:` value not in the allowed set above
  2. **Broken target** — strip `[[` and `]]` from the `target:` string, normalize (lowercase, spaces→hyphens, strip `.md`), and check whether a `.md` file at that path exists in the vault. Flag unresolved targets.
     Before normalizing, drop everything from the first `|` (alias) or `#` (heading/block anchor), unescaping a table-escaped `\|` first: a pipe-aliased or heading-anchored target is not broken just because the literal bracket contents do not match a filename. (Ported from upstream PR #206.)
  3. **Self-reference** — flag any entry where the resolved target equals the page's own node id

**How to fix:**
- Invalid type: correct the value to the nearest allowed type, or use `related_to` when the type is ambiguous
- Broken target: update or remove the entry; if the target page should exist, create it first
- Self-reference: remove the entry

**Output additions:**

```markdown
### Typed Relationship Issues (N found)
- `concepts/foo.md` — relationships[1]: type "contradication" is not an allowed type (did you mean "contradicts"?)
- `concepts/bar.md` — relationships[0]: target "[[skills/nonexistent-skill]]" resolves to no page in vault
- `entities/baz.md` — relationships[2]: self-reference (target resolves to this page's own id)
```

Append to the `LINT` log entry:
```
... relationship_issues=N
```

### 14. People and Entity Types

Enforces the `type:` and `people:` keys (see `llm-wiki/SKILL.md`, *Entity pages: `type:` and `people:`*). **Opt-out:** if `WIKI_PEOPLE_KEYS=0` in the resolved config, skip Check 14 entirely; unset means on.

The failure this guards is silent by construction: a person who is never recorded produces no error anywhere else, and coverage drifts back to ad hoc the moment attention moves.

**Allowed `type:` values:** `person`, `self`, `organization`, `tool`, `device`

**How to check:**
- Read the frontmatter (not the body) of every `entities/` page, and grep `^people:` and `^type: self` across the whole vault
- Build the set of recorded people: the title and `aliases:` of every `type: person` page, plus every name in every `people:` list. Compare names case-insensitively after trimming
- Then:
  1. **Untyped or mistyped entity** — an `entities/` page with no `type:`, or a value outside the allowed set
  2. **Owner count** — exactly one page carries `type: self`; zero is a warning, two or more is an error
  3. **Double record** — a name that is both a `type: person` page (by title or alias) and a `people:` entry, or appears in two `people:` lists
  4. **Retired form** — `person` inside `tags:` on any page
  5. **Unrecorded person (judgement, warning)** — a person named in the body of three or more pages who is on neither route. This is read, not grepped: organisations, products and places also look like two capitalised words, so decide as a reader, and report the top of the list with the page each appears on most. Never create the record from lint; hand it to the next `/wiki-update` or `/wiki-ingest`

**How to fix:**
- Untyped entity: add `type:` with the right value; a page that is a pair or a company is `organization`, hardware is `device`, software and models are `tool`
- Mistyped: correct to the nearest allowed value
- Owner count: one `type: self` on the owner's page; every other person is `person`
- Double record: keep the entity page and remove the `people:` entry, or keep exactly one `people:` entry on the page that is the primary source
- Retired form: remove the `person` tag; set `type: person` on an entity page, or add the name to `people:` on the page that is their primary source
- Unrecorded person: report only, with the page where they appear most, so the next update can run the fold gate's step 3a

**Output additions:**

```markdown
### People and Entity Type Issues (N found)
- `entities/devbox.md` — no `type:` (allowed: person, self, organization, tool, device)
- `entities/foo.md` — `type: laptop` is not an allowed value (did you mean `device`?)
- vault — `type: self` on 2 pages: `entities/a.md`, `entities/b.md`
- "Jane Doe" — recorded twice: `entities/jane-doe.md` (type: person) and `people:` on `projects/x/x.md`
- `entities/albert-deng.md` — `person` in tags is a retired form; use `type: person`
- "John Roe" (warning) — named on 4 pages, on neither route; most on `projects/y/y.md`
```

Append to the `LINT` log entry:
```
... people_issues=N
```

## Output Format

Report findings as a structured list:

```markdown
## Wiki Health Report

### Orphaned Pages (N found)
- `concepts/foo.md` — no incoming links

### Broken Wikilinks (N found)
- `entities/bar.md:15` — links to [[nonexistent-page]]

### Missing Frontmatter (N found)
- `skills/baz.md` — missing: tags, sources

### Stale Content (N found)
- `references/paper-x.md` — source modified 2024-03-10, page last updated 2024-01-05

### Contradictions (N found)
- `concepts/scaling.md` claims "X" but `synthesis/efficiency.md` claims "not X"

### Index Issues (N found)
- `concepts/new-page.md` exists on disk but not in index.md

### Missing Summary (N found — soft)
- `concepts/foo.md` — no `summary:` field
- `entities/bar.md` — summary exceeds 200 chars

### Provenance Issues (N found)
- `concepts/scaling.md` — AMBIGUOUS > 15%: 22% of claims are ambiguous (re-source or move to synthesis/)
- `projects/some-project/some-project.md` — ⚠ MEASUREMENT: 6 markers, 0 claim units — cannot divide, fractions suppressed (assertion 1)
- `concepts/transformers.md` — hub page (31 incoming links) with INFERRED=28%: errors here propagate widely
- `synthesis/speculation.md` — unsourced synthesis: no `sources:` field, 55% inferred

### Fragmented Tag Clusters (N found)
- **#systems** — 7 pages, cohesion=0.06 ⚠️ — run cross-linker on this tag
- **#databases** — 5 pages, cohesion=0.10 ⚠️

### Visibility Issues (N found)
- `entities/user-records.md` — contains `email:` value pattern but no `visibility/pii` tag
- `concepts/auth-flow.md` — tagged `visibility/pii` but missing `sources:` frontmatter
- `_meta/taxonomy.md` — `visibility/` tag listed inside a countable domain-tag table (belongs in the Reserved section)

### Misc Promotion Candidates (N found)
Pages in misc/ that have ≥ 3 connections to a single project and are ready to be promoted:

| Page | Top Project | Affinity Score |
|---|---|---|
| `misc/web-martinfowler-articles-microservices.md` | `obsidian-wiki` | 4 |

### Typed Relationship Issues (N found)
- `concepts/foo.md` — relationships[1]: type "contradication" is not an allowed type
- `concepts/bar.md` — relationships[0]: target "[[skills/nonexistent]]" resolves to no page

### People and Entity Type Issues (N found)
- `entities/devbox.md` — no `type:` (allowed: person, self, organization, tool, device)
- "Jane Doe" — recorded twice: `entities/jane-doe.md` and `people:` on `projects/x/x.md`

### Synthesis Gaps (N found)
Concept pairs that co-occur frequently but have no synthesis page:

| Pair | Co-occurrence | Suggested Action |
|---|---|---|
| [[Caching]] × [[Consistency]] | 5 pages | Run `/wiki-synthesize` |
| [[Testing]] × [[Observability]] | 3 pages | Run `/wiki-synthesize` |
```

## After Linting

Append to `log.md`:
```
- [TIMESTAMP] LINT issues_found=N orphans=X broken_links=Y stale=Z contradictions=W prov_issues=P missing_summary=S fragmented_clusters=F visibility_issues=V promotion_candidates=C synthesis_gaps=G relationship_issues=R prov_units_definition=U prov_pages_gated=GP prov_assert_raised=AR prov_over_unity=OU
```

Offer to fix issues automatically or let the user decide which to address.

---

## Consolidate Mode (`--consolidate`)

Triggered by `wiki-lint --consolidate`. Switches from report-only to **act-and-report** — the "dream cycle" that runs periodically so the wiki self-heals.

### Safety protocol

**Always run in dry-run first.** Before writing anything:

1. Run all lint checks (1–13 above, including 3a).
2. Print the planned consolidation actions as a structured list (see Dry-Run Output below).
3. Ask the user: `"Apply these N changes? [yes / no / select]"`.
4. Only proceed with writes after explicit confirmation. If the user selects individual actions, apply only those.
5. Never merge pages — use `wiki-dedup` for that. Only link, promote, demote, and flag.

### Consolidation actions (in order, after confirmation)

#### Action 1: Fix broken wikilinks

For each broken `[[Target]]` found in Check 2:
- Search the vault for a page whose title or filename is the closest fuzzy match (use `Grep` across `index.md` titles)
- If a unique best match exists (edit distance ≤ 2 characters or same root word): rewrite the link. Note the rewrite: `[[Oringal]] → [[corrected-page]]`.
- If no match or ambiguous: **leave the link exactly as it is and report it.** Do **not** convert it to plain text. This branch is non-negotiable: the destructive version has no upside, and Check 2 has been wrong before — under the pre-2026-09-09 recipe it flagged 597 links on a 247-page vault where 2 were genuine, so "no match" was overwhelmingly evidence about the checker, not the link. A broken link that stays visible gets fixed on a later pass; a silently unlinked one is unrecoverable without git archaeology. You may add `<!-- broken link: no match found -->` beside it, but never touch the `[[...]]` itself.
- Never create a new page just to satisfy a broken link.

#### Action 2: Add missing cross-references for orphans

For each orphan page found in Check 1 (zero incoming links):
- Grep the vault body text for mentions of the page's title or aliases (case-insensitive).
- For each mention found in another page, add a `[[wikilink]]` replacing the plain-text mention.
- Limit to 3 insertions per orphan — don't flood pages with links.
- This is scoped to orphans only (different from `cross-linker` which runs broadly).

#### Action 3: Correct lifecycle states

Apply these rules automatically (they don't require human judgment — they enforce the documented state machine):
- **Promote `draft` → `reviewed`:** ONLY for pages that have an **approved, non-stale entry in `_meta/trust-ledger.json`** (a recorded human review is what `reviewed` means) AND `lifecycle: draft` AND `created` > 30 days ago. Set `lifecycle: reviewed`, `lifecycle_changed: <today>`, `lifecycle_reason: "auto-promoted by wiki-lint --consolidate: ledger-approved review, age>30d"`. Never promote from `base_confidence` alone — a stored score is a draft estimate, not evidence a review happened.
- **Demote `verified` → `stale`:** NOT a state transition — `stale` is a computed overlay, not a lifecycle value. Instead: for verified pages where `is_stale = (today − updated) > 180 days`, add a callout at the top of the page body: `> ⚠️ **Stale**: This page was last updated <date>. Verify before relying on it.` Only add if the callout isn't already present.
- **Do not change `reviewed` → `verified` or any other transition** — those are human-only.

#### Action 4: Tier demotion

For pages with `tier: supporting` (or unset) that have 0 incoming links AND haven't been updated in 90+ days:
- Emit a list of **proposed** demotions for the user to review. Do NOT write `tier: peripheral` automatically — wiki-query skips peripheral pages at retrieval time, so an automatic demotion silently removes pages from search; demotion is human-only.
- Do not demote `tier: core` pages automatically — those were manually set. Exception: when the vault log's most recent `TIER_DERIVE` entry shows tiers came from a bulk derivation, they may be re-derived with the same logged procedure and threshold.

#### Action 5: Tag normalization

Read `_meta/taxonomy.md` for the alias mapping (e.g., `ml → machine-learning`). For each page, replace known alias tags with their canonical form in the `tags:` frontmatter field. This is a subset of `tag-taxonomy`'s work — only alias fixes, no full audit.

#### Action 6: Contradiction callouts

For each pair of pages marked as contradicting each other (via `relationships: contradicts` in frontmatter, or flagged in Check 5):
- Check whether a `> ⚠️ Contradiction flagged with [[Other Page]]` callout already exists near the relevant claim.
- If not, add it at the end of the "Key Ideas" section (or before "Open Questions" if no "Key Ideas" section). Keep it concise — one line.
- Do not resolve the contradiction; only flag it visually.

### Action 7: Write consolidation report

After all actions, write a report to `synthesis/consolidation-<YYYY-MM-DD>.md`:

```markdown
---
title: Consolidation Report <YYYY-MM-DD>
category: synthesis
tags: [maintenance, consolidation]
sources: []
summary: Auto-generated consolidation report from wiki-lint --consolidate run on <date>.
lifecycle: draft
lifecycle_changed: <date>
tier: peripheral
created: <ISO timestamp>
updated: <ISO timestamp>
---

# Consolidation Report — <YYYY-MM-DD>

## Summary
- Broken links fixed: N
- Cross-references added: M
- Lifecycle states updated: K
- Tier demotions: D
- Tags normalized: T
- Contradiction callouts added: C

## Broken Link Fixes
- `concepts/foo.md:12` — [[OldTarget]] → [[correct-target]]
- `entities/bar.md:8` — [[Missing]] → `Missing` (no match found)

## Cross-References Added (orphan rescue)
- `concepts/baz.md` — now linked from: [[concepts/alpha]], [[skills/beta]]

## Lifecycle Updates
- `concepts/old-draft.md` — draft → reviewed (age 45d, confidence 0.74)
- `synthesis/stale-verified.md` — stale callout added (last updated 2025-10-01)

## Tier Demotions
- `concepts/unused-concept.md` — supporting → peripheral (0 links, 120 days stale)

## Tag Normalizations
- `entities/some-tool.md` — `ml` → `machine-learning`

## Contradiction Callouts
- `concepts/scaling.md` — flagged contradiction with [[synthesis/efficiency]]
```

### Dry-Run Output (shown before any writes)

```
wiki-lint --consolidate — Dry Run

Planned actions (N total):
[1] Fix broken link: concepts/foo.md:12 [[OldTarget]] → [[correct-target]]
[2] Add cross-ref: concepts/baz.md ← [[concepts/alpha]] (orphan rescue)
[3] Lifecycle: concepts/old-draft.md → reviewed (age 45d, confidence 0.74)
[4] Tier demotion: concepts/unused.md → peripheral (0 links, 112 days stale)
[5] Tag alias: entities/some-tool.md: ml → machine-learning
[6] Contradiction callout: concepts/scaling.md ↔ [[synthesis/efficiency]]

Apply these 6 changes? [yes / no / select by number]
```

### Log entry for consolidate mode

```
- [TIMESTAMP] LINT_CONSOLIDATE links_fixed=N orphans_rescued=M lifecycle_updates=K tier_demotions=D tag_fixes=T contradiction_callouts=C report=synthesis/consolidation-YYYY-MM-DD.md
```

## QMD Refresh After Vault Writes

QMD is a search index, not the source of truth. If `$QMD_WIKI_COLLECTION` is empty or unset, skip this step. Run it only after this skill has written or rewritten vault markdown. If QMD refresh fails, do not roll back the vault changes; report the QMD status separately.

Use `$QMD_CLI` if set; otherwise use `qmd`.

```bash
${QMD_CLI:-qmd} update
```

If the output says vectors are needed or embeddings may be stale, run:

```bash
${QMD_CLI:-qmd} embed
```

Verify the collection with either:

```bash
${QMD_CLI:-qmd} ls "$QMD_WIKI_COLLECTION"
```

or, when a specific page path is known:

```bash
${QMD_CLI:-qmd} get "qmd://$QMD_WIKI_COLLECTION/<page>.md" -l 5
```

Record one of:
- `QMD refreshed: update + embed + verified`
- `QMD refreshed: update only + verified`
- `QMD skipped: QMD_WIKI_COLLECTION unset`
- `QMD skipped: qmd CLI unavailable`
- `QMD failed: <short error summary>`
