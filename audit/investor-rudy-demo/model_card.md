# Model card — Rudy-Trained Tactical Search (demo build)

## Architecture
- **Dual-tower fusion MLP** (spec §9): query-intent tower + window-embedding tower,
  fused with `[q, w, q·w, |q-w|, scalar pair feats]`, ranked by margin loss.
- Query features: one-hot QueryIntent (`primary_mechanism`, `lane`, `zone_*`,
  `pressure`, `progression`, `box_entry`, `switch_play`, `carry`, `pass`, `danger`,
  `turnover`, `rudy_analogy_mode`) + optional `query_id` one-hot.
- Window features: v9c (288-d) + v11p (288-d) + ~20 numeric predicate fields.
- Pair scalar features: cosine to v9c query anchor, predicate match score,
  same/different propagated mechanism, anchor agreement score, hard-negative flag.

## Training data (this demo)
- **175 hand-labelled clip cards** (`runs/clip_card_index.json`) — `primary_mechanism`,
  `progression_zone`, `progression_lane`, `pressure_context`, `severity`, free-form
  `rationale_text`.
- **46 analyst pair judgments** (`data/analyst_labels_v3/analyst_pairs_train_rudy_v3_internal.parquet`)
  — `positive` / `hard_near_miss` / etc. with shared-mechanism tags.
- **Seed pair rationales** (`analyst_pack_session_1/seed_pairs.csv`) — additional
  pair-relation labels.
- **Propagated soft labels** (`rudy_demo_nl_retriever/rudy_semantic_index.jsonl`)
  — `confidence_tier` ∈ {`labelled`, `propagated_high`, `propagated_med`,
  `propagated_weak`}. Soft-positive training rows use the `propagated_high`
  tier only.

The trainer bridges from window-window pair labels to **query-window** labels
by treating each labelled clip's `primary_mechanism` as a target for the
corresponding query intent (spec §9.2).

## Caveats
- **Fresh query-window labels not available this sprint.** The model is
  trained on a bridge over existing window-level expertise; the label queue
  at `/audit/investor-rudy-demo/label-queue/` is the next-step bottleneck.
- **Demo-tuned**, not a production foundation model. Generalisation outside
  the curated 16 queries is not claimed.
- **Propagated labels are explicitly tiered**. The investor page shows
  `🟢 LABELLED`, `🟣 SUGGESTED`, `⚪ MODEL-RANKED`, `🟦 PREDICATE-MATCH` so
  the audience cannot confuse model inference with human signal.
- **Right panel may fall back to ensemble + reranker baseline** if the trained
  ranker artefact (`artifacts/model_rankings.jsonl`) is not present at
  generation time. The banner indicates which mode rendered.

## What this doesn't prove
- That the model generalises to queries outside the 16-query curated set.
- That `propagated_high` labels would survive Rudy's review.
- That the right panel beats the left panel in retrieval recall at scale —
  scale-level claims require fresh query-window labels (queue is ready).
