# /audit/investor-rudy-demo/label-queue/

Single-page static UI for Rudy to grade the pre-mined (query, window)
candidate queue produced by the `rudy_demo_nl_retriever` sprint.

## Files
- `index.html` — labelling UI (vanilla JS, no build).
- `label_queue.json` — 200+ candidate items mined from predicate top-10,
  Rudy ensemble top-10, anchor windows, random/diverse picks, and
  hard-negative seeds. Each item carries the query text, window media
  URL (broadcast or pitch animation), predicate chips, and Rudy anchor
  chips.
- `label_queue.jsonl` — the same data in JSONL for downstream training.

## Workflow
1. Open `index.html` in a browser.
2. Watch the clip, read the chips.
3. **Grade** with `1`=Strong, `2`=Partial, `3`=Miss.
4. Mark **Showable** with `y` (yes) or `n` (no).
5. Optionally fill **Why match**, **Why not**, and **Primary tactical concept**.
6. Press `Enter` (or click "next") to advance. `Backspace` to go back.
7. Labels save to `localStorage` (`rudy_demo_labels_v1`) automatically.
8. Click **Export JSONL ↓** when finished — downloads
   `rudy_demo_labels_<timestamp>.jsonl` for the training workstream to
   ingest.

## Filters
- **Show only unlabelled** — focus on remaining items.
- **Query** — restrict to one QID.
- **Source** — predicate_top10 / rudy_ensemble / anchor / random_diverse /
  hard_negative.

## Schema (output JSONL row)
```json
{
  "qid": "Q05",
  "window_id": "1899585:1899585:271:54266",
  "query_text": "press break through the centre",
  "grade": "strong" | "partial" | "miss",
  "showable": "yes" | "no",
  "why_match": "free text",
  "why_not": "free text",
  "concept": "free text",
  "labelled_at": "ISO timestamp"
}
```

## Honesty notes
- Labels are stored in this browser only. Different machines = different
  localStorage. **Export to JSONL** before closing if you want to keep them.
- The queue is candidate-mined, not random — Rudy is intentionally seeing
  what the existing systems already think is likely.
