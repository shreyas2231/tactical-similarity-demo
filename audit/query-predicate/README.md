# /audit/query-predicate/ — internal audit page

Static HTML view of the deterministic predicate compiler over the curated
12-query test set. Sister surface to `/audit/predicate/` (per-predicate
audit). Not a replacement for `/query/` (the deployed LLM demo).

## Files

- `index.html` — landing page, query cards
- `q01.html` … `q12.html` — one detail page per query
- `styles.css` — shared stylesheet
- `_generate.py` — generator script (run from this directory)

## Adding a new query

1. Append to `TEST_QUERIES` in
   `fwm/eval/predicate_query_compiler_v0.py`.
2. Re-run the audit:
   ```
   cd /home/ubuntu/fwm
   python -m eval.predicate_query_compiler_v0
   ```
   This rewrites
   `runs/skillcorner_predicate_index_v0/stage2_query_audit/results.json`.
3. Re-run this generator:
   ```
   cd /tmp/tactical-similarity-demo/audit/query-predicate
   python3 _generate.py
   ```
4. Commit + push as usual.

## Hard constraints

- No `player_id`, no `team_filter` (compiler rejects them).
- v9c canonical demo, BEST_CHECKPOINT, `/query/`, reranker_v0 unchanged.
- Banner caveat (“candidate moments, not exhaustive retrieval”) on every
  page — do not remove.
