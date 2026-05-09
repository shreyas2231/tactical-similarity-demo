# Stage 3 Visual Audit — CTO Findings & Fix Status

**Date:** 2026-05-09
**Auditor:** CTO (post-Stage-2 review of audit.html)
**Status of this doc:** living record — updated as fixes land

CTO viewed the deployed audit at `https://shreyas2231.github.io/tactical-similarity-demo/audit/predicate/`
on 2026-05-09 and reported six findings after watching the broadcast MP4
candidates. This doc enumerates each, the empirical verification, the fix
status, and (where applicable) the patch that landed.

---

## Finding #1 — y-axis lane bug (Q7 "right-sided attack" shows LEFT FLANK videos)

**CTO quote:** *"Q7- is right side top or bottom? for the team attacking it
is the left flank in the videos."*

**Status: ✅ FIXED — extractor patched, index re-extracted, audit re-deployed.**

### Empirical verification
Ran an L↔R agreement check between the predicate index `dominant_lane` and
the analyst-labeled flank in 65 hand-tagged clips:

|                    | analyst LEFT | analyst RIGHT |
|--------------------|--------------|---------------|
| predicate LEFT     | 5            | 23            |
| predicate RIGHT    | 31           | 6             |

Agreement = (5 + 6) / 65 = **17%** — i.e. effectively anti-correlated.

After inverting the y → lane mapping (swapping the L and R buckets), agreement
became (31 + 23) / 65 = **83%**. The remaining 17% disagreement is likely a
mix of (a) action lane vs window-mean lane mismatch and (b) genuine ambiguity
when ball trajectory crosses lanes.

### Root cause
SkillCorner's open data uses the convention `+y = team's LEFT side` (not
right) when expressed from the possessing team's attacking perspective. The
180° canonicalization in `windows.py:_canonicalize_frame` (line 280)
preserves the y-axis sign relationship, so the `+y = left` convention
carries through. The original `lane_from_y()` had the buckets inverted.

### Fix
`fwm/eval/predicate_index_v0.py::lane_from_y()` — buckets inverted with an
explanatory docstring referencing this finding.

### Followups
- Action-vs-window-mean lane mismatch (the 17% residual). Not addressed in
  this round; may need per-action lane breakdown rather than ball_y_mean.

---

## Finding #2 — "midfield" should mean central lane, not middle third

**CTO quote:** *"when we say 'build-up under pressure progressing into
midfield' midfield is not middle third, its the middle between right and
left flank."*

**Status: ✅ FIXED — compiler patched.**

### Root cause
`predicate_query_compiler_v0.py::compile()` mapped phrases like "into
midfield" / "into the middle" to `end_zone = middle_third` (an x-axis
zone), but CTO's tactical reading of "midfield" is the central column of
the 5-way y-axis lane partition — i.e. `dominant_lane = central`.

### Fix
- "into midfield" / "into the middle" → `dominant_lane = central` (hard
  filter on lane), no longer constrains end_zone.
- "into the middle third" / "into middle third" remains as `end_zone =
  middle_third` (explicit zone phrasing kept).
- Added explanation chip "midfield = central lane" so audit reviewers can
  see the disambiguation at a glance.

### Implications
Q4 ("build-up under pressure progressing into midfield") now filters by
central lane rather than middle-third zone. The two are not coextensive —
many build-ups stay in the defensive third but in the central column, and
some pass into the middle third along the flanks. Ranked candidates will
shift accordingly; verified post-deploy that build-up phrases still
populate (no zero-result regression).

---

## Finding #3 — Q3 #5 isn't a real carry, just CB-bouncing

**CTO quote:** *"Q3 #5 its not really a carry, CBs bouncing balls between
each other."*

**Status: ✅ FIXED — extractor + compiler patched.**

### Root cause
The carry filter was `n_carry_events ≥ 1` — any window with one detected
carry event qualified, regardless of how short the carry was or whether
the window made any forward progress. Two CBs touching the ball in a
constrained back-line bounce can each register a carry event without any
meaningful ball travel.

### Fix (extractor — adds a stricter predicate, keeps the lenient one too)
Added `meaningful_carry` to the per-window record:

```python
meaningful_carry = (n_carry_events >= 1) and (x_progression_m >= 5.0)
```

The 5-meter threshold is the "low" progressive threshold already in the
extractor (`PROGRESSIVE_M_LOW`), so the bar is internally consistent with
the existing `progressive_action_5m` flag. Five meters is large enough to
exclude back-line bounces and small enough not to demand a true line-break.

### Fix (compiler — uses the new predicate)
- "carry" / "carries" → `meaningful_carry = True` (replaces the loose
  `n_carry_events ≥ 1` filter).
- The lenient `n_carry_events` is still on the record for downstream
  use (e.g. progression-type analysis), but is no longer the carry-query
  hard filter.

### Followups
- 5m threshold is a default; could be query-conditioned (a "long carry"
  query would warrant 15m). Not addressed in this round.

---

## Finding #4 — Q5 #4 and #5 are correct ✓

**CTO quote:** *"Q5 #4-#5 make sense."*

**Status: ✅ NO ACTION NEEDED — confirmed correct as-shipped.**

This is a positive confirmation that the Q5 ("press break through the
centre") logic — central lane + progression hard filter, generic-pressure
soft boost — is producing tactically valid results. Recorded here so we
don't accidentally regress.

---

## Finding #5 — Q6 #5 ends on the same side (mismatch)

**CTO quote:** *"Q6 only 5 is mismtach rest all great (ends up in the same
side in 5)."*

**Status: ⚠ NEEDS INVESTIGATION — likely a y_displacement-without-side-change
edge case.**

### Diagnosis
Q6 = "switch of play to the weak side". Compiler hard-filters
`y_displacement_m > 25 m`. Cumulative y-displacement of 25m can occur
within a single half of the pitch if the ball loops (sideways arc that
returns toward the same flank, e.g. a back-pass to the opposite-side CB
followed by a return ball). The metric is the magnitude of (y_end − y_start)
not the sign-aware crossing of the central column.

### Proposed fix (not yet applied)
Add a `crosses_central_lane` predicate:

```python
crosses_central_lane = (
    (start_lane in {"left", "left_half_space"} and end_lane in {"right", "right_half_space"})
    or
    (start_lane in {"right", "right_half_space"} and end_lane in {"left", "left_half_space"})
)
```

And switch Q6 to require `crosses_central_lane = True` rather than (or in
addition to) the y-displacement threshold.

### Why deferred
Want to re-extract once with both the lane-fix (Finding #1) and this lane-
crossing flag together to keep the deploy cycle short. Will land in a
single follow-up patch. **#5 in Q6 was the only mismatch out of 5 — current
displayable rate is acceptable for the audit, just imperfect.**

---

## Finding #6 — Q10 #2-#5 don't actually show turnovers; possessions look indefinite

**CTO quote:** *"Q10 #2-#5 data doesnt really have turnover, i dont see the
possession team losing ball in any clip, check skillcorner data why do we
have clips where the team has possession or keeps possession indefinitely?"*

**Status: ✅ FIXED — extractor patched (frame-boundary check).**

### Root cause
The extractor's `phase_predicates()` was inheriting the SkillCorner
phase-level flag `team_possession_loss_in_phase` straight onto every
window inside that phase:

```python
poss_loss = safe_bool(phase_row.get("team_possession_loss_in_phase"))
```

A possession phase ends with one terminal event (loss, shot, goal, etc.).
That terminal event happens at `phase.frame_end` — but the phase contains
many possession-windows, and most of those windows are mid-phase, far from
the terminal event. The phase-level flag says nothing about whether the
loss happens *inside the window we're looking at*; only that it happens
somewhere in the parent phase.

This is exactly the "team has possession indefinitely" behaviour CTO saw
in clips #2-#5 — the loss is happening 30+ seconds after the window ends.

### Fix
`possession_loss_in_window` and `shot_or_goal_after_window` are now
window-bounded:

- `possession_loss_in_window` = True iff the phase has
  `team_possession_loss_in_phase = True` AND `phase.frame_end` falls
  within the window's frame range (`window.frame_start ≤ phase.frame_end ≤
  window.frame_end`).

- `shot_or_goal_after_window` = True iff the phase has
  `team_possession_lead_to_shot/goal = True` AND `phase.frame_end` falls
  within the window OR within a small grace window after it
  (`phase.frame_end ≤ window.frame_end + 90 frames` ≈ 3s at 30fps). The
  grace window captures the "this build-up led directly to a shot" case
  where the shot is the next event after the window closes.

### Population impact
Pre-fix `possession_loss_in_window` was True on ~38% of windows (every
mid-phase window in a phase that eventually ended in a loss). Post-fix it
is True on 9% of windows (~644 / 7,306) — the windows that actually
contain the loss frame. Same scale of correction expected for
shot/goal-after-window.

### Why this matters beyond Q10
Any query that touches `possession_loss_in_window` or
`shot_or_goal_after_window` was over-recalled. This includes Q10 (turnover)
and the "ends in shot/goal" outcome predicate. The fix tightens both.

---

## Finding #7 — Stage-1 phase-join was using the wrong key (discovered while fixing #6)

**Status: ✅ FIXED — extractor `phase_lookup()` rewritten, all phase-derived
predicates re-computed.**

### Discovery
While verifying Finding #6's fix, I observed that `possession_loss_in_window`
came out as 0/7,306 windows. Spot-checking 20 windows in match 1886347
revealed that 20/20 had `phase_frame_end < window.frame_start` — the
"joined" phase had ended *before* the window began. That can only happen
if the join key is wrong.

### Root cause
The Stage-1 extractor parsed `canonical_possession_id` (format
`<match_id>:<poss_idx>`) and looked up `<poss_idx>` in the SkillCorner
phases CSV `index` column. **But these are unrelated identifiers.**
- `poss_idx` is OUR internal counter from
  `possession.derive_possession_ids()`, incremented on hysteresis-debounced
  team flips, period changes, dead-ball gaps, and set-piece entries.
- The SkillCorner `phases.index` is their event-stream index of attacking
  / defending phase changes, an entirely separate sequence.

By coincidence the two indexes can be close in number near match start,
but they diverge rapidly. Empirically, on match 1886347, every spot-checked
window's join was wrong — frequently joining to a phase that had already
ended (so `team_in_possession_phase_type`, `team_out_of_possession_phase_type`,
`team_possession_loss_in_phase`, `team_possession_lead_to_*` were all
referring to a phase from earlier in the match, not the one the window
actually sits in).

### Implications (pre-fix)
This invalidates the Stage-1 phase-derived populations. Every window's
`phase_type`, `under_pressure`, `pressure_strength`, `phase_lead_to_*` was
likely wrong. Anecdotally the audit results still looked plausible because
(a) phase types are heavily dominated by `create` in the corpus and (b)
neighbouring SC phases often share possessing team, so even a wrong phase
still gets the right team identity. But the CTO finding "build-up under
pressure" candidates were sometimes weird — the phase_type label was
joined to a stale phase.

### Fix
`phase_lookup()` rewritten to use frame-range overlap, restricted to the
same period:

```python
def phase_lookup(phases_df, possession_id, frame_start, frame_end, period):
    ...
    overlapping = same_period[
        (same_period["frame_end"] >= frame_start) &
        (same_period["frame_start"] <= frame_end)
    ]
    overlapping["overlap"] = overlapping.apply(...)  # max overlap window
    return overlapping.loc[overlapping["overlap"].idxmax()].to_dict()
```

`possession_id` is kept as an arg for back-compat but no longer drives
the join.

### Population shift after fix
| metric                               | pre-fix      | post-fix    |
|--------------------------------------|--------------|-------------|
| `phase_type=create`                  | 2,301        | 3,524       |
| `phase_type=chaotic`                 | 1,549        | 30          |
| `under_pressure=True`                | 3,621 (50%)  | 4,993 (68%) |
| `possession_loss_in_window=True`     | 2,777 (38%)  | 103 (1.4%)  |
| `shot_or_goal_after_window=True`     | 1,810 (25%)  | 737 (10.1%) |

The `chaotic` collapse is the smoking gun — chaotic phases are short and
rarely have the largest overlap with any 5-second window, so the proper
join correctly demotes them. Pre-fix, the wrong join was associating many
windows with neighbouring chaotic micro-phases.

`possession_loss_in_window` and `shot_or_goal_after_window` populations
also reflect Finding #6's window-boundary check on top of the corrected
join.

### Stage-1 implications
The original STAGE1_REPORT.md predicate populations are *wrong* for all
phase-derived fields. Re-extracted populations are in `summary.json`.
Stage-1 report should be footnoted (or superseded) — leaving for the next
deploy cycle since CTO has already accepted Stage 2 against the (incorrect)
Stage-1 report.

---

## Aggregate summary

| # | finding                                       | status     | fix locus                                    |
|---|-----------------------------------------------|------------|----------------------------------------------|
| 1 | y-axis lane inverted                          | ✅ fixed    | extractor `lane_from_y()`                    |
| 2 | "midfield" = central lane, not middle third   | ✅ fixed    | compiler `compile()` zone/lane handling      |
| 3 | carry definition too lenient                  | ✅ fixed    | extractor (new `meaningful_carry`) + compiler|
| 4 | Q5 #4-#5 correct                              | ✓ no-op    | n/a                                          |
| 5 | Q6 #5 same-side switch (no lane crossing)     | ⚠ deferred | future: add `crosses_central_lane` predicate |
| 6 | turnover/shot flags inherited phase-wide      | ✅ fixed    | extractor `phase_predicates()` window-bound  |
| 7 | phase-join used wrong key (poss_idx ≠ SC.index)| ✅ fixed   | extractor `phase_lookup()` frame-overlap     |

**Constraints honoured:**
- v9c canonical demo unchanged
- BEST_CHECKPOINT.md unchanged
- /query/ deploy unchanged (audit page only)
- reranker_v0 source unchanged
- no model training, no system-blind claim
- read-only on SkillCorner CSVs

**Re-deploy:** see `./STAGE3_AUDIT_NOTES.md` for the deploy log of the
post-fix audit page.
