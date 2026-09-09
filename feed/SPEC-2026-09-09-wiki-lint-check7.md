# Spec and Plan: wiki-lint Check 2 hazard + Check 7 provenance repair

Date: 2026-09-09
Status: draft for review, nothing implemented
Repos touched: `obsidian-wiki` (skill text only). Vault change only in task 7.

---

## 1. Why this exists

A `/wiki-lint` run on 2026-09-09 produced a provenance figure of **`extracted = -0.20`** on
`skills/cross-link-detector-traps.md`. A negative fraction is structurally impossible, so the check
was measuring something other than what it claims to measure.

Investigating that produced two results, and the smaller one turned out to be the urgent one.

The check's defect is real but its conclusion was already reached three weeks ago and never executed.
Meanwhile a *different* check, Check 2, carries a live hazard that can destroy vault content, and
upstream published the fix for it three days ago.

---

## 2. What is already decided (read this before re-litigating anything)

Two prior rulings bound this work. Both were recorded and neither was carried out.

**2026-08-15, `log.md` CORRECTION.** After a full re-measurement:

> "the drift rule yields NO trustworthy per-page finding on this vault and its assertion should fire;
> the Check 7 threshold rules (ambiguous>15%, unsourced synthesis, hub pages) are unaffected and stay
> live. Real repair is upstream, align the ingest skills to compute `provenance:` the way lint
> recomputes it, **or drop the numeric block**."

Tasks 1, 2 and 7 below are that ruling. They are not new findings. A five-verifier adversarial pass on
2026-09-09 re-derived the same conclusion independently, which is convergent validation and worth
recording, but it is not novelty.

**2026-08-15, `log.md` SKILL_PATCH.** The claim-unit denominator was *deliberately* changed that day
from non-blank lines to bullets-only, because the line denominator understated inferred by roughly 4x
(0.05 versus 0.21 on a hand-checked page). Anyone proposing to change that definition again is making
the second permanent edit to the same rule inside a month, and the first draft of this spec did exactly
that before the history was checked.

**Precedent worth internalising.** The trust-schema pilot carried a pre-registered kill criterion:
*if trust fields changed no real retrieval or decision, kill = phase 0 + strip fields + delete ledger*.
It was resolved 2026-08-09 as "keep the fields, but the ledger is untended," and the follow-on
tend-or-exit choice "was ruled out by the evidence, but the choice was never made." That is twice a
metadata layer has been kept-but-unused rather than decided. Task 7 is the third instance of the same
question and should not be allowed to resolve by default.

---

## 3. Task 0: the Check 2 hazard (do this first)

**Severity: destructive. Unrelated to Check 7. Highest priority in this document.**

Check 2's recipe as written in the fork:

> - Grep for `\[\[.*?\]\]` across all pages
> - Extract the link targets
> - Check if a corresponding `.md` file exists

This has no handling for pipe aliases, heading anchors, block anchors, non-markdown embeds, or
table-escaped pipes. Consolidate mode's Action 1 then acts on the result:

> If no match or ambiguous: convert to plain text (`~~[[Target]]~~` → `Target`)

So `/wiki-lint --consolidate` would unlink every valid `[[page\|Alias]]` inside a markdown table and
every `![[diagram.png]]` embed in the vault.

**This is not theoretical.** A link sweep during this session flagged 9 broken links; 6 were
`rubrica\|Rubrica` table-escaped pipes and 1 was a `[[target]]` illustration inside backticks. Only 2
were genuine. Under consolidate mode that is 7 destroyed references.

**Upstream already fixed it.** PR #206 (2026-09-06) exists precisely because the naive recipe "caused
destructive rewrites during consolidate mode"; upstream's `lint.py` was already correct and only the
prose was wrong. PR #204 (closing issue #176) fixed the same class in code: `[[beta\|B]]` captured as
`beta\`, plus `.md` suffix handling and an attachment allowlist for `.png` / `.pdf` / `.canvas` /
`.base`.

**Fix:** rewrite Check 2's recipe to strip everything from the first `|` or `#` before comparing,
unescape `\|` before alias splitting, skip non-`.md` extensions via an attachment allowlist, strip
explicit `.md` suffixes, and ignore wikilinks inside fenced or inline code. The last clause is already
fork policy from commit `d633ed7` ("a wikilink inside code is an illustration, not a reference") and
should be stated inside Check 2 rather than left implicit.

**Also add to Action 1:** never unlink on a no-match. Report and leave the text alone. The destructive
branch has no upside; a broken link that stays visible gets fixed, a silently unlinked one does not.

---

## 4. Task 1: retire the drift rule

Delete the numeric drift comparison and its How-to-fix. Keep the degeneracy assertion as a documented
pattern; it is fork-local IP with no upstream equivalent and it is reused by Check 8 and by
`cross-linker`.

Evidence for retirement:

| measure | value |
|---|---|
| LINT runs recording `prov_issues` | 13 |
| page edits ever attributable to provenance drift | **1** (2026-04-18, predates the current marker spec) |
| pages eligible under the current density gate | 3 of 231 |
| standing state per the skill's own text | "expect the degeneracy assertion to fire" |

Every run since 2026-05-14 resolved to a statement about the instrument rather than about a page:
*"dismissed as noise, denominator too small"*; *"20 recompute hits dismissed as documented
sparse-marking false-positive class"*; *"CHECK 7 IS DEFECTIVE AS SPECIFIED"*; and now *"recomputed to
-0.20, impossible."* A rule whose only possible output is "the instrument is broken" is not a guard
producing no event, it is a permanently red light with an empty action list across five months.

The deeper reason it cannot work: it differences a *holistic write-time judgment* against a *marker
count*. Those are different populations, which is `measurement-universe-mismatch` by name, and no
tolerance value repairs a unit mismatch.

---

## 5. Task 2: keep the three threshold rules

`ambiguous > 15%`, `unsourced synthesis`, and `hub inferred > 20%` stay. They are not dead, they are
merely quiet, and the distinction is measurable:

| rule | current worst page | threshold |
|---|---|---|
| unsourced synthesis | 0.385 | 0.40 |
| hub inferred | 0.144 | 0.20 |
| ambiguous | 0.077 | 0.15 |

All three sit near their thresholds with real headroom, so they would fire on a genuinely bad page.
Zero findings here means the vault is honest, not that the rule is broken. My earlier framing that
"Check 7 produces zero findings" bundled a live check with a dead one and was wrong.

---

## 6. Task 3: the denominator (REOPENED, needs a decision)

This is the one item the red-team and the upstream review disagree about, so it is flagged rather than
resolved.

Three definitions are currently in play:

| source | definition |
|---|---|
| upstream `wiki-lint` | "count **sentences/bullets**" |
| fork `llm-wiki:342` (write side) | "rough fraction of **sentences/bullets** with no marker" |
| fork `wiki-lint` (2026-08-15 patch) | "**bullet or numbered list item**, NOT a non-blank line" |

**The fork's lint is the outlier.** Upstream and the fork's own write-side documentation agree with
each other and disagree with the fork's lint. That is very likely the root of the "write skills follow
neither definition" finding recorded on 2026-08-15.

Measured evidence on where markers actually live (246 content pages, 1,672 markers):

| location | share |
|---|---|
| standalone prose paragraph | 65.3% |
| list item, wrapped continuation line | 22.3% |
| list item, marker on the bullet line | 11.0% |
| heading / table / blockquote | 1.4% |

A caution about that table. An earlier version of this analysis reported 87.8% prose, which was wrong:
the vault hard-wraps near 100 characters and markers trail the final wrapped line, so 373 markers that
actually terminate bullets were misread as prose. Any future measurement here must attribute wrapped
continuation lines to their parent bullet or it will repeat the error.

**Three options:**

- **(i) Keep bullets-only, repair boundedness only.** Lowest risk, no second n=1 redefinition. Leaves
  the fork diverged from upstream and from its own write side.
- **(ii) Align to sentences/bullets.** Matches upstream and `llm-wiki`, removes the divergence, and is
  supported by two independent sources rather than one page. Requires measurement before adoption.
- **(iii) Adopt the partition definition** proposed during the red-team, where markers cut the text and
  every marker-bearing position is a counted unit. Bounded by construction at every granularity, but
  not verifiable by eye and needs an arbitrary five-word floor.

**Recommendation: (ii), gated on measurement.** The argument that killed (i) is that "do not redefine
on n=1" was the right rule when the only evidence was one page; upstream plus the fork's own write-side
doc is a second and third independent source, and aligning to the documented convention is not the same
act as inventing a fourth definition. But it must be measured first, and the measurement must report
what happens to the three surviving threshold rules, since `unsourced synthesis` sits 0.015 from its
threshold and a denominator change could flip it.

**Do not implement task 3 without that measurement.**

---

## 7. Task 4: boundedness assertions (the genuinely new work)

No upstream equivalent exists. Add to Check 7, raising rather than warning:

- `markers <= claim_units`
- `0 <= fraction <= 1` for every page
- `claim_units > 0` before dividing

The third is not hypothetical: `projects/cs160-prog1/cs160-prog1.md` has zero bullets and one
`^[inferred]` inside a table row, which is a divide-by-zero under the current definition.

Also exclude backticked and fenced marker mentions from the numerator. The page that *defines* the
markers, and two others that discuss them, currently read as maximally synthetic because the check
counts its own vocabulary. That is the measurement reading its own inputs.

**Add a known-answer fixture**, matching what Check 8 already has with `#calibration`: one hand-counted
page asserted in both directions, so the check is proven able to go red as well as green. Per
`guards-that-do-not-guard`, for every absence assertion add a presence one.

---

## 8. Task 5 and 6: numbers and instrumentation

**Task 5.** The "~0.13 low" calibration finding stays valid; it was measured under the bullets
denominator. Only "the ratio gate admits 27" is stale, it admits 41 of 246 today. Record the measured
prose-versus-bullet spread: the container rule reports 3.02x where the authorial truth is 1.84x, so
roughly 1.6x of that gap is manufactured by the unit rule and should be disclosed rather than chased.

**Task 6.** Log `prov_units_definition`, `prov_pages_gated` and `prov_assert_raised` on every LINT
entry. This is the same instrument-before-legislating move applied to `cross-linker` earlier today, and
it exists so the next person to propose a denominator change has more than one run to argue from.

---

## 9. Task 7: drop the numeric `provenance:` block (decided: option a)

213 pages carry it. Once task 1 lands, **nothing reads it**: 13 skills write the block, and the only
consumer is the drift rule being retired. `wiki-query` does not mention provenance at all.

The inline markers are the actual provenance record and are untouched. Only the frontmatter summary
goes, and it can be regenerated from markers at any time, so this is recoverable.

**The cost, stated plainly.** Upstream is explicit that "the numeric frontmatter block is kept when
present; drift flags indicate when it needs refresh, not removal." Dropping it is therefore a permanent
fork divergence, and the 13 write skills will attempt to re-add it on every upstream merge.

**This must be recorded as a trap patch** in the merge-constraints memory alongside the existing ones
(wiki-query Step 0 visibility guard, wiki-ingest manifest-entry protection, Check 6 project-hub
exemption, the Check 7 YAML-provenance exemption, write-template schema gates). If it is not recorded,
it reverts silently at the next merge and this decision gets made a fourth time.

**Pre-registered reversal criterion**, so this does not resolve by default the way the last two did:
reintroduce the block only if a concrete retrieval need appears, specifically a `wiki-query` mode that
filters or ranks on speculation level and demonstrably cannot afford to compute it from markers at
query time. Absent that, it stays gone.

---

## 10. Order of work

| # | task | risk | gate |
|---|---|---|---|
| 0 | Check 2 recipe + non-destructive Action 1 | **destructive if skipped** | none, do it now |
| 1 | Retire drift rule | low | none, executes the 08-15 ruling |
| 2 | Keep threshold rules | none | no change required |
| 4 | Boundedness assertions + fixture | low | none |
| 5 | Correct stale numbers | none | none |
| 6 | Instrumentation | none | none |
| 3 | Denominator decision | **medium** | measurement first, then choose |
| 7 | Drop the block + record trap patch | low, but permanent divergence | trap patch recorded in the same change |

Tasks 0, 1, 2, 4, 5, 6 are skill-text edits in `obsidian-wiki` with no vault writes. Task 7 touches 213
vault pages and should be its own commit.

---

## 11. Validation

- Re-run the full lint after tasks 0 and 4. `cross-link-detector-traps.md` must recompute inside [0,1]
  or raise; no page may produce a value outside [0,1]; `cs160-prog1` must not divide by zero.
- Check 2 must report exactly 2 broken links on the current vault, not 9. The 6 escaped-pipe links and
  the 1 backticked illustration must not appear.
- Check 8's `#calibration` anchor must still read 0 isolated, 1 component, cohesion 0.600.
- The three threshold rules must produce the same findings before and after task 4, since task 4
  changes boundedness, not thresholds. If they move, something else changed.

---

## 12. Open questions for Travis

1. **Task 3:** approve the measurement, or keep bullets-only and accept the divergence?
2. **Task 0 scope:** port upstream's recipe wording from #206, or write our own from its description?
   Nothing has been copied from upstream yet; this review was read-only.
3. **Anything else in the 48-commit upstream backlog worth revisiting** now that #204 and #206 are
   known to be real fixes for problems we independently hit?

---

## Appendix: evidence provenance

Everything in section 3 comes from upstream issue #176, PR #204, PR #206 and the fork's own SKILL.md.
Sections 4 through 8 come from a five-verifier adversarial pass on 2026-09-09 plus direct measurement
over 246 content pages. Section 2 comes from `wiki-vault/log.md` entries dated 2026-08-15, the
2026-08-09 checkpoint resolution recorded in `feed/HANDOFF-2026-08-13.md`, and the merge-constraints
memory.

Two claims in the first draft of this spec were wrong and are corrected above: the 87.8% prose figure
(hard-wrap artifact, true value 65.3%) and "Check 7 produces zero findings" (only the drift rule is
dead; three rules remain live). Three hub-page provenance findings reported in the 2026-09-09 lint
were also false and are withdrawn.

---

## FINDINGS (independent review, 2026-09-09, Fable 5.1, read-only)

Every number in sections 3 through 9 was re-derived against the live files. Verdict per task, then
the corrections, then the implementation routing.

### F0. Task 0 (Check 2 hazard): real, mis-sized both ways, root cause missed

- **Vault census (247 content pages, 5,031 wikilinks):** 530 plain aliases, 114 heading anchors,
  8 escaped pipes (5 in content pages: `concepts/independent-measurer-discipline.md` ×3,
  `projects/mountaineers-pitch/mountaineers-pitch.md` ×2; 2 rubrica, 2 gavel, 1 mountaineers-pitch;
  the other 2 are in `log.md`, which lint exempts), **0 embeds** (`![[`), 0 non-`.md` targets,
  8 wikilinks inside code spans. Section 3's "6 were `rubrica\|Rubrica`" is wrong on count and
  on target; the embed half of the hazard is theoretical on this vault today.
- **Not silent.** Consolidate mode mandates a dry-run listing every action plus explicit
  confirmation. The unlinks would appear as 5 lines Travis has to notice. Thin, not silent.
- **Worse than claimed if read literally.** "Extract the link targets, check the `.md` exists"
  yields **597** false broken links (aliases + anchors). The escaped-pipe residue is what survives
  an agent that already knows to split on `|`. A true-to-the-prose consolidate would propose
  unlinking hundreds.
- **Root cause the spec misses:** the fork already has compiled link logic in
  `obsidian_wiki/lint.py`. `_WIKILINK_RE` handles `\|`, `|` and `#` since 2026-08-09 (b8cb369e);
  `_normalise_node_id` strips `.md`; code-span masking landed in d633ed7. Check 2's prose never
  tells the agent to run it (`obsidian-wiki lint`, README:50). The correct fix is to make Check 2
  *call* lint.py rather than re-describe regexes in prose. Caveats: lint.py skips `_meta`, so it
  would flag the 3 `[[machine-parity]]` links (target lives at `_meta/machine-parity.md`), and it
  lacks #204's attachment allowlist (moot today, 0 embeds).
- **Upstream claims verified via GitHub API:** #204 MERGED 2026-09-03, #206 MERGED 2026-09-06,
  #176 CLOSED 2026-09-03. Local `upstream/main` is stale at 3f29e56 (2026-08-31, #205); neither PR
  is fetched. #206 also rewrites **Check 13's** relationship-target recipe; the spec omits that.
- **Fix sufficiency:** sufficient. "Never unlink on no-match" is the load-bearing half. Add one
  edge case: a wikilink wrapped in an inline footnote, `^[[[page#h|x]]]`, occurs once
  (`projects/strava-pm/skills/pm-casing-framework.md:99`) and defeats a greedy `[[…]]` grep.
- **Correct-recipe broken links on the current vault:** 2 genuine, both in
  `journal/2026-09-01-bray-jsdse-citation-request.md` (`writing-style-casual`,
  `commercial-position-and-ip-basis`). Matches the 2026-09-09 LINT entry.

### F7. Task 7 (drop the numeric block): reversible via git only; deletion filter underspecified

- 213 numeric blocks confirmed, each exactly `extracted/inferred/ambiguous`, no other sub-keys.
  **But 243 pages carry a `provenance:` key; 30 are narrative attributions** (e.g.
  `projects/strava-pm/strava-pm.md:5` lists devbox JSONL ids). The spec never says "numeric only".
  An agent grepping `^provenance:` deletes 30 source records.
- **Readers:** nothing in `obsidian_wiki/`, `scripts/`, `tests/`, `_meta/*.base`, or `.obsidian`.
  Skill-side: the drift rule (retiring), `wiki-dedup/SKILL.md:178` ("recompute after merging"),
  `wiki-capture/SKILL.md:255` checklist. 15 skills contain `provenance:` (spec says 13).
- **Missed writer:** the vault's own `_meta/ingest-rules.md:45` instructs every ingest to "write a
  `provenance:` block". A framework trap patch does not stop that; the vault rule must change too.
- **"Can be regenerated from markers" is false** by the spec's own 08-15 finding: declared values
  are holistic estimates matching neither marker definition (MAE 0.126 vs 0.125). Regeneration
  yields a different quantity. Reversibility = `git revert` (vault pushed at 0320831; `log.md` has
  an uncommitted modification at review time).
- Stated purpose being lost (`llm-wiki/SKILL.md:339`): "scan for speculation-heavy pages without
  reading them". No dashboard or query uses it today. `llm-wiki/SKILL.md:347` still documents the
  retired "≥10 inline markers" gate; not in Task 5.

### F3. Task 3 (denominator): evidence favours (ii) more than stated; Task 2 depends on it

- Under bullets-only, **18 of 247 pages have markers > bullets** (over-unity), not just
  cs160-prog1. cs160-prog1 has **6** markers (5 `^[extracted`, 1 `^[inferred`), not 1. Option (i)
  is not "lowest risk"; it is unbounded on 7% of the vault.
- **The denominator decides the "live" threshold rules.** Computed both ways:

  | page (top-10 hub by incoming) | inferred / bullets | inferred / sentences+bullets |
  |---|---|---|
  | `concepts/independent-measurer-discipline.md` (159 in) | **0.419** | 0.080 |
  | `projects/cosmos-mtb/cosmos-mtb.md` (69 in) | **0.423** | 0.056 |
  | `skills/multi-agent-review-pattern.md` (92 in) | **0.205** | 0.062 |
  | ambiguous, worst: `skills/cross-link-detector-traps.md` | **0.200** | 0.059 |

  Bullets-only fires the hub rule on three pages and the ambiguous rule on one. Sentences+bullets
  fires nothing. Section 5's table (hub 0.144, ambiguous 0.077) matches **neither** definition, so
  it was computed under an undeclared third one, and the appendix's "three hub-page findings were
  false and are withdrawn" uses the answer Task 3 leaves open. **Circular.** Thresholds tuned for
  one denominator are off by roughly 5x under the other; a denominator change needs a threshold
  re-derivation, not just a re-measurement.
- Unsourced synthesis: no page with an empty/missing `sources:` exceeds 0.40 under either
  definition (worst `entities/m5stack-devkits.md` 0.261 / 0.092). The 0.385 figure could not be
  reproduced.

### F4. Other corrections

- LINT entries recording `prov_issues`: **21**, not 13 (nonzero: 04-18=1, 05-14=6-soft, 05-20=54,
  08-13=7, 08-29=8, 09-09=4). Direction of the argument holds.
- Upstream backlog: 104 commits by `rev-list HEAD..upstream/main`, 31 fork-only. "48" unverified.
- Markers: 1,674 raw, 1,671 outside code (spec: 1,672). In-code markers touch 2 pages / 3 markers,
  so the Task 4 numerator clause is minor.
- Section 11's "three threshold rules must produce the same findings before and after task 4"
  cannot be asserted until Task 3 fixes the denominator; today it is denominator-dependent.
- The 2026-08-15 CORRECTION and SKILL_PATCH quotes in section 2 are accurate (`log.md:585-586`).

### Biggest risk

The Task 2 / Task 3 circularity: the spec declares the threshold rules healthy and dismisses three
hub findings before the number that decides both exists. Concrete vault risk: Task 7 deleting the
30 narrative `provenance:` blocks.

### Recommended order and routing

| task | change | route |
|---|---|---|
| 0 | Check 2: delegate to `obsidian-wiki lint` (or port #206 prose), never-unlink in Action 1, footnote edge case, Check 13 recipe from #206 | Opus, skill text only |
| 1, 4, 5, 6 | as spec, plus fix `llm-wiki/SKILL.md:347` | Opus, skill text only |
| 3 | measure both denominators on all four rules, re-derive thresholds, then decide | **Fable** (decision, not mechanics) |
| 2 | re-derive after 3; not "no change required" | with 3 |
| 7 | numeric-only filter (`extracted:`/`inferred:`/`ambiguous:` sub-keys, 213 pages), edit `_meta/ingest-rules.md:45`, `wiki-dedup:178`, `wiki-capture:255`, record trap patch, own commit, diff-count assertion `== 213` before commit | **Fable**, after 3 |

Fetch `upstream/main` before Task 0 so #204/#206 can be diffed rather than described.
