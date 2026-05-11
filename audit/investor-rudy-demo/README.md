# /audit/investor-rudy-demo/

Investor hero page for the **Rudy-Trained Tactical Search** prototype. Sibling
of `/audit/investor-query-comparison/`, focused on:

- **Honesty about the training data.** Trained on 175 hand-labelled clips +
  46 analyst pair judgments — the page mentions this on every banner and in
  the model card.
- **Confidence tagging.** Every result card carries one of
  `🟢 LABELLED`, `🟣 SUGGESTED`, `⚪ MODEL-RANKED`, `🟦 PREDICATE-MATCH`.
- **EXPECTED-vs-ACTUAL guard.** Each detail page embeds the pre-written
  expectation (from `runs/rudy_demo_nl_retriever/EXPECTED_PER_QUERY.md`).
- **Rudy labelling queue.** The CTA links to `label-queue/`, a single-page
  static UI Rudy can use to grade 200+ pre-mined candidates.

## Files
- `index.html` — landing grid + CTA to label queue.
- `q01.html` … `q16.html` — one detail page per curated query.
- `styles.css` — page styling (purple-stripe Rudy theme; reuses sibling-page
  patterns).
- `_generate.py` — emits the above (run from this directory).
- `results.json` — combined rankings (predicate + Rudy panels) per query.
- `query_intents.json` — public copy of `parsed_intents.json`.
- `model_card.md` — architecture, training data, caveats.
- `animations/` — pitch-animation MP4s (105×68, no player_id).
- `label-queue/` — single-page labelling UI (see its README).

## Hard constraints (locked)
- Banner copy includes the exact phrases: *"Demo-tuned"*, *"Awaiting fresh
  query-window labels"*, *"Not exhaustive production search"*.
- v9c, v11p, BEST_CHECKPOINT, `/query/`, `reranker_v0.py` — unchanged.
- No team filter; no `player_id` propagation; both honest-fail panels
  refuse cleanly on Q11 and Q12.

## Re-running
    cd /tmp/tactical-similarity-demo/audit/investor-rudy-demo
    python3 _generate.py
