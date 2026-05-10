# /audit/investor-query-comparison/ — investor-facing comparison page

Static HTML demo that puts deterministic predicate retrieval next to
Rudy tactical-similarity retrieval over the same 7,306 SkillCorner
windows. Emitted by Workstream PAGE in the
`investor_query_comparison` sprint.

## What this is

- **Left column:** Predicate Search — explicit football predicates
  (lane, zone, pressure, progression, box) compiled from the parsed
  intent.
- **Right column:** Rudy Tactical Similarity Search — anchor windows
  drawn from Rudy's expert-label index, then v9c+v11p ensemble +
  reranker_v0 over the corpus.
- **Diff row:** predicate-only / overlap / rudy-only — the
  complementarity payoff visualised.

## Files

- `index.html` — landing grid with verdict pills
- `q01.html` … `q16.html` — one detail page per query
- `styles.css` — shared stylesheet
- `_generate.py` — generator (run from this directory)
- `parsed_intents.json` — public copy of `query_intents.json`
- `animations/` — pitch-animation MP4s for windows without broadcast
  video (anonymised top-down, 105×68, no `player_id`)

## Hard constraints

- Banner caveat on every page: *Internal investor demo — candidate
  retrieval, not exhaustive production search. Predicate Search and
  Rudy Tactical Similarity Search are complementary modes; neither
  claims ground truth.*
- No `player_id`, no team filter — both refused cleanly.
- v9c, v11p, BEST_CHECKPOINT, `/query/`, reranker_v0, and the deployed
  demo at `/` are unchanged.

## Re-running

    cd /tmp/tactical-similarity-demo/audit/investor-query-comparison
    python3 _generate.py
