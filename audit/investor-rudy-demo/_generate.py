"""Static-site generator for /audit/investor-rudy-demo/.

Hero page for the Rudy-Trained Tactical Search investor demo. Sibling of
`/audit/investor-query-comparison/` — reuses its CSS conventions and chip
pattern but reframes the right-hand panel as a **trained ranker** rather
than anchor-similarity, and tags every result with a confidence tier so
the audience sees what was human-labelled vs propagated vs model-ranked.

Inputs:
  - _old_predicate_results.json (predicate top-10 per query)
  - _old_rudy_results.json      (right-panel fallback if no fresh model ranks)
  - parsed_intents.json          (QueryIntent v1, copied from sibling page)
  - rudy_semantic_index.jsonl    (per-window confidence_tier + propagated mech)
  - clip_card_index.json         (broadcast mp4 urls; labelled-clip lookup)
  - EXPECTED_PER_QUERY.md        (predictions, parsed and embedded per page)
  - artifacts/model_rankings.jsonl  (TRAIN workstream output, if present)

Outputs:
  - index.html        landing grid
  - q01.html ... q16.html
  - styles.css
  - results.json
  - query_intents.json
  - model_card.md
  - README.md
"""
from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from pathlib import Path
from textwrap import dedent

HERE = Path(__file__).parent
FWM = Path("/home/ubuntu/fwm")
SPRINT = FWM / "runs/rudy_demo_nl_retriever"
PRED_RESULTS = SPRINT / "artifacts/_old_predicate_results.json"
RUDY_RESULTS = SPRINT / "artifacts/_old_rudy_results.json"
INTENTS_SRC = Path("/tmp/tactical-similarity-demo/audit/investor-query-comparison/parsed_intents.json")
CLIP_CARD_INDEX = FWM / "runs/clip_card_index.json"
SEM_INDEX = SPRINT / "rudy_semantic_index.jsonl"
MODEL_RANKINGS = SPRINT / "artifacts/model_rankings.jsonl"
EXPECTED_MD = SPRINT / "EXPECTED_PER_QUERY.md"

ANIM_DIR = HERE / "animations"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_jsonl(p: Path):
    out = []
    if not p.exists():
        return out
    with p.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_expected(md_path: Path) -> dict[int, str]:
    if not md_path.exists():
        return {}
    text = md_path.read_text()
    # parse "## Q01 — ..." blocks
    out: dict[int, str] = {}
    blocks = re.split(r"^## (Q\d{2}) ", text, flags=re.MULTILINE)
    # split returns [pre, qid, body, qid, body, ...]
    for i in range(1, len(blocks), 2):
        qid = blocks[i]
        body = blocks[i + 1]
        try:
            n = int(qid[1:])
        except ValueError:
            continue
        # strip the headline title line and capture the rest up to next H2 or H1
        body = body.split("\n---\n", 1)[0]
        # Keep first 12 lines for compactness
        lines = body.strip().splitlines()
        if lines and not lines[0].startswith("- "):
            lines = lines[1:]
        compact = "\n".join(lines[:14])
        out[n] = compact
    return out


# ---------------------------------------------------------------------------
# Media index — broadcast > local animation (relative to HERE)
# ---------------------------------------------------------------------------
def build_media_index(broadcast_map: dict[str, str]) -> dict[str, dict]:
    media: dict[str, dict] = {}
    for wid, url in broadcast_map.items():
        if url:
            media[wid] = {"url": url, "kind": "broadcast"}
    for f in ANIM_DIR.rglob("*.mp4"):
        wid = f.stem.replace("_", ":", 3)
        if wid in media:
            continue
        rel = f.relative_to(HERE)
        media[wid] = {"url": str(rel), "kind": "animation"}
    return media


# ---------------------------------------------------------------------------
# Chip helpers
# ---------------------------------------------------------------------------
def _chip(text: str, cls: str = "") -> str:
    cls = (" " + cls) if cls else ""
    return f"<span class='chip{cls}'>{html.escape(str(text))}</span>"


ZONE_LABEL = {
    "defensive_third": "defensive",
    "middle_third": "middle",
    "final_third": "final",
    "attacking_third": "attacking",
}
LANE_LABEL = {
    "left": "left",
    "left_half_space": "left-hs",
    "central": "central",
    "right_half_space": "right-hs",
    "right": "right",
    "half_space_left": "left-hs",
    "half_space_right": "right-hs",
}


def render_pred_card_chips(facts: dict, raw_chips: list[str] | None = None) -> str:
    chips = []
    if facts.get("dominant_lane"):
        chips.append(_chip(f"lane: {LANE_LABEL.get(facts['dominant_lane'], facts['dominant_lane'])}"))
    if facts.get("start_zone"):
        chips.append(_chip(f"start: {ZONE_LABEL.get(facts['start_zone'], facts['start_zone'])}"))
    if facts.get("end_zone"):
        chips.append(_chip(f"end: {ZONE_LABEL.get(facts['end_zone'], facts['end_zone'])}"))
    if facts.get("enters_box"):
        chips.append(_chip("box ✓", "chip-pos"))
    if facts.get("under_pressure"):
        chips.append(_chip("pressure", "chip-press"))
    if facts.get("dangerous"):
        chips.append(_chip("dangerous", "chip-danger"))
    if facts.get("crosses_central_lane"):
        chips.append(_chip("switch ✓", "chip-pos"))
    if facts.get("possession_loss_in_window"):
        chips.append(_chip("turnover", "chip-loss"))
    if facts.get("x_progression_m") is not None and abs(facts["x_progression_m"]) >= 5:
        chips.append(_chip(f"+{facts['x_progression_m']:.0f}m"))
    return " ".join(chips)


# ---------------------------------------------------------------------------
# Confidence tier (the trust boundary)
# ---------------------------------------------------------------------------
def confidence_tag(item: dict, *, panel: str, sem_row: dict | None,
                   labelled_clip_ids: set[str], intent_mech: str | None) -> tuple[str, str, str]:
    """Return (label, emoji, css_class).

    Panel == 'predicate'  →  ⚪ MODEL-RANKED never applies; this is PREDICATE-MATCH.
    Panel == 'rudy'       →  apply the LABELLED / SUGGESTED / MODEL-RANKED tier ladder.
    """
    wid = item["window_id"]
    if panel == "predicate":
        return ("PREDICATE-MATCH", "🟦", "conf-tag-pred")

    # Rudy panel
    if wid in labelled_clip_ids:
        return ("LABELLED", "🟢", "conf-tag-labelled")
    tier = (sem_row or {}).get("confidence_tier")
    if tier == "labelled":
        return ("LABELLED", "🟢", "conf-tag-labelled")
    if tier == "propagated_high":
        prop_mech = (sem_row or {}).get("propagated_mechanism")
        if intent_mech and prop_mech and (intent_mech == prop_mech
                                          or intent_mech in prop_mech
                                          or prop_mech in intent_mech):
            return ("SUGGESTED", "🟣", "conf-tag-suggested")
        return ("SUGGESTED", "🟣", "conf-tag-suggested")
    return ("MODEL-RANKED", "⚪", "conf-tag-model")


# ---------------------------------------------------------------------------
# Card renderers
# ---------------------------------------------------------------------------
def media_tile(wid: str, media: dict, *, small: bool = False) -> str:
    info = media.get(wid)
    klass = "vid vid-small" if small else "vid"
    if info is None:
        return f'<div class="no-mp4{" no-mp4-small" if small else ""}">no media for {html.escape(wid)}</div>'
    if info["kind"] == "broadcast":
        return (
            f'<video src="{html.escape(info["url"])}" controls preload="none" muted class="{klass}"></video>'
            f'<div class="media-tag tag-broadcast">🟢 BROADCAST</div>'
        )
    return (
        f'<video src="{html.escape(info["url"])}" controls preload="none" muted class="{klass} vid-anim"></video>'
        f'<div class="media-tag tag-anim">🟣 PITCH ANIMATION</div>'
    )


def render_pred_card(rank: int, item: dict, media: dict,
                     sem_by_wid: dict, labelled: set[str], intent_mech: str | None,
                     *, small: bool = False) -> str:
    wid = item["window_id"]
    facts = item.get("predicate_facts", {}) or {}
    chips_html = render_pred_card_chips(facts, item.get("predicate_chips"))
    score = item.get("score", 0.0)
    tag_lbl, tag_emoji, tag_cls = confidence_tag(
        item, panel="predicate",
        sem_row=sem_by_wid.get(wid), labelled_clip_ids=labelled, intent_mech=intent_mech,
    )
    tile = media_tile(wid, media, small=small)
    klass = "card card-small" if small else "card"
    return dedent(f"""
        <div class='{klass} card-pred'>
          <div class='card-head'>
            <span class='rank'>#{rank}</span>
            <span class='conf-tag {tag_cls}'>{tag_emoji} {tag_lbl}</span>
            <span class='wid' title='{html.escape(wid)}'>{html.escape(wid)}</span>
          </div>
          {tile}
          <div class='chips'>{chips_html}</div>
          <div class='score'>predicate {score:.4f}</div>
        </div>
    """).strip()


def render_rudy_card(rank: int, item: dict, media: dict,
                     sem_by_wid: dict, labelled: set[str], intent_mech: str | None,
                     *, small: bool = False) -> str:
    wid = item["window_id"]
    sem_row = sem_by_wid.get(wid, {})
    tag_lbl, tag_emoji, tag_cls = confidence_tag(
        item, panel="rudy",
        sem_row=sem_row, labelled_clip_ids=labelled, intent_mech=intent_mech,
    )

    chips = []
    # Nearest Rudy anchor
    anchor = item.get("anchor_window_id") or sem_row.get("nearest_anchor_window_id")
    if anchor:
        chips.append(_chip(f"anchor {anchor.split(':')[-1]}", "chip-rudy-overlap"))
    mech = (item.get("propagated_mechanism")
            or item.get("matched_anchor_mechanism")
            or sem_row.get("propagated_mechanism"))
    if mech:
        chips.append(_chip(f"mech: {mech}", "chip-rudy-mech"))
    score = item.get("final_score") or item.get("ensemble_score") or item.get("model_score")
    if score is not None:
        chips.append(_chip(f"score {score:.3f}", "chip-rudy-score"))
    overlap = item.get("predicate_overlap") or []
    for tag in overlap[:3]:
        chips.append(_chip(tag, "chip-rudy-overlap"))
    chips_html = " ".join(chips)

    # Score components in monospace
    comps = item.get("reranker_contribs") or {}
    if comps:
        comp_line = " ".join(f"{k}={v:.2f}" for k, v in list(comps.items())[:5])
    else:
        v9c = item.get("v9c_score")
        v11p = item.get("v11p_score")
        bits = []
        if v9c is not None: bits.append(f"v9c={v9c:.3f}")
        if v11p is not None: bits.append(f"v11p={v11p:.3f}")
        comp_line = " · ".join(bits) if bits else ""

    tile = media_tile(wid, media, small=small)
    klass = "card card-small" if small else "card"
    return dedent(f"""
        <div class='{klass} card-rudy'>
          <div class='card-head'>
            <span class='rank rank-rudy'>#{rank}</span>
            <span class='conf-tag {tag_cls}'>{tag_emoji} {tag_lbl}</span>
            <span class='wid' title='{html.escape(wid)}'>{html.escape(wid)}</span>
          </div>
          {tile}
          <div class='chips'>{chips_html}</div>
          <div class='score'>{html.escape(comp_line)}</div>
        </div>
    """).strip()


# ---------------------------------------------------------------------------
# Diff row helpers
# ---------------------------------------------------------------------------
def compute_diff(pred_top: list[dict], rudy_top: list[dict]):
    pred_set = {c["window_id"] for c in pred_top}
    rudy_set = {c["window_id"] for c in rudy_top}
    overlap_wids = pred_set & rudy_set
    overlap, seen = [], set()
    for c in pred_top:
        if c["window_id"] in overlap_wids and c["window_id"] not in seen:
            overlap.append(("pred", c))
            seen.add(c["window_id"])
    pred_only = [("pred", c) for c in pred_top if c["window_id"] not in overlap_wids]
    rudy_only = [("rudy", c) for c in rudy_top if c["window_id"] not in overlap_wids]
    return pred_only[:3], overlap[:3], rudy_only[:3]


def what_rudy_adds(pred_top, rudy_top, intent, sem_by_wid, labelled, model_source):
    pred_set = {c["window_id"] for c in pred_top}
    rudy_set = {c["window_id"] for c in rudy_top}
    only_rudy = [c for c in rudy_top if c["window_id"] not in pred_set]
    only_pred = [c for c in pred_top if c["window_id"] not in rudy_set]
    if not only_rudy and not only_pred:
        return "Both panels return the same windows for this query — predicate and Rudy agree."
    n_labelled = sum(1 for c in only_rudy
                     if c["window_id"] in labelled
                     or (sem_by_wid.get(c["window_id"], {}).get("confidence_tier") == "labelled"))
    mechs = []
    for c in only_rudy:
        m = (c.get("propagated_mechanism")
             or c.get("matched_anchor_mechanism")
             or sem_by_wid.get(c["window_id"], {}).get("propagated_mechanism"))
        if m and m not in mechs:
            mechs.append(m)
    intent_mech = intent.get("primary_mechanism") or "unspecified"
    parts = []
    if only_rudy:
        parts.append(
            f"Rudy adds <b>{len(only_rudy)}</b> window(s) absent from predicate top-5"
            + (f", of which <b>{n_labelled}</b> are human-labelled clips" if n_labelled else "")
            + f". Surfaced mechanisms: <code>{', '.join(mechs[:3]) or 'mixed'}</code>"
            f" — Rudy's expert labels group these by tactical mechanism (target intent: "
            f"<code>{intent_mech}</code>) rather than by literal predicate match."
        )
    if only_pred:
        parts.append(
            f"Predicate keeps <b>{len(only_pred)}</b> window(s) that Rudy demotes — typically "
            "windows that match the spatial filter but don't share the labelled tactical mechanism."
        )
    if model_source == "fallback":
        parts.append(
            "<em>Note: rankings shown here come from the prior ensemble + rules reranker baseline; "
            "fresh trained-model rankings were unavailable at generation time.</em>"
        )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Banner / chrome (mandated copy)
# ---------------------------------------------------------------------------
def banner_html(model_source: str) -> str:
    fallback_line = ""
    if model_source == "fallback":
        fallback_line = ("<div class='banner-sub'><b>Model rankings fallback:</b> using "
                         "the prior <code>ensemble + reranker_v0</code> baseline. Trained-model "
                         "rankings will replace this once <code>artifacts/model_rankings.jsonl</code> "
                         "ships from the TRAIN workstream.</div>")
    return dedent(f"""
        <div class='banner'>
          <div class='banner-line'><b>Internal investor demo.</b> Trained on Rudy's <b>175 hand-labelled clips</b> + <b>46 analyst pair judgments</b>.</div>
          <div class='banner-line'><b>Demo-tuned.</b> Awaiting fresh query-window labels (queue ready at <a href='label-queue/'>/audit/investor-rudy-demo/label-queue/</a>).</div>
          <div class='banner-line'><b>Not exhaustive production search.</b> Right-hand panel is candidate ranking, not ground truth.</div>
          {fallback_line}
        </div>
    """).strip()


def page_head(title: str) -> str:
    return dedent(f"""\
        <!doctype html>
        <html><head><meta charset='utf-8'>
        <title>{html.escape(title)}</title>
        <meta name='viewport' content='width=device-width, initial-scale=1'>
        <link rel='stylesheet' href='styles.css'>
        </head><body>
    """)


def page_foot() -> str:
    return "</body></html>\n"


# ---------------------------------------------------------------------------
# Confidence-tier legend (the trust-boundary explainer)
# ---------------------------------------------------------------------------
LEGEND = dedent("""
    <section class='legend block'>
      <h3>Confidence tags — the trust boundary</h3>
      <div class='legend-row'>
        <span class='conf-tag conf-tag-labelled'>🟢 LABELLED</span>
        <span class='legend-sub'>window is one of Rudy's 175 hand-labelled clip cards.</span>
      </div>
      <div class='legend-row'>
        <span class='conf-tag conf-tag-suggested'>🟣 SUGGESTED</span>
        <span class='legend-sub'>high-similarity to a labelled anchor (<code>confidence_tier=propagated_high</code>) — model-inferred, not a human label.</span>
      </div>
      <div class='legend-row'>
        <span class='conf-tag conf-tag-model'>⚪ MODEL-RANKED</span>
        <span class='legend-sub'>trained ranker placed it in top-5 with no labelled / propagated-high anchor.</span>
      </div>
      <div class='legend-row'>
        <span class='conf-tag conf-tag-pred'>🟦 PREDICATE-MATCH</span>
        <span class='legend-sub'>matched the deterministic predicate filter (left panel only).</span>
      </div>
    </section>
""").strip()


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------
def landing_thumbnail(pred_q: dict, rudy_q: dict, media: dict) -> str:
    if not pred_q.get("rejected") and pred_q.get("top_10"):
        wid = pred_q["top_10"][0]["window_id"]
        return media_tile(wid, media, small=True)
    if rudy_q.get("top_10"):
        wid = rudy_q["top_10"][0]["window_id"]
        return media_tile(wid, media, small=True)
    return '<div class="no-mp4 no-mp4-small">honest fail</div>'


def render_landing(pred_results, rudy_results, intents, media, sem_by_wid, labelled,
                   model_source: str) -> str:
    cards = []
    for i, pred_q in enumerate(pred_results, start=1):
        rudy_q = rudy_results.get(str(i), {"top_10": []})
        intent = intents.get(str(i), {})
        qid = f"q{i:02d}"
        rejected = pred_q.get("rejected", False)
        rudy_top = rudy_q.get("top_10", [])

        intent_chips = pred_q.get("intent_chips") or []
        chips = " ".join(_chip(c, "chip-explain") for c in intent_chips[:3]) or "<span class='muted'>no chips</span>"
        thumb = landing_thumbnail(pred_q, rudy_q, media)
        n_pred = pred_q.get("n_candidates_total", 0)
        n_rudy = len(rudy_top)
        if rejected and not rudy_top:
            verdict, vcls = "Honest fail", "verdict-fail"
            stats = "<span class='rej'>both reject</span>"
        elif rejected:
            verdict, vcls = "Rudy only", "verdict-rudy"
            stats = f"<span class='rej'>predicate rejects</span> · rudy <b>{n_rudy}</b>"
        elif not rudy_top:
            verdict, vcls = "Predicate only", "verdict-pred"
            stats = f"predicate <b>{n_pred}</b> · <span class='rej'>rudy empty</span>"
        else:
            pred_set5 = {c["window_id"] for c in pred_q["top_10"][:5]}
            rudy_set5 = {c["window_id"] for c in rudy_top[:5]}
            overlap = pred_set5 & rudy_set5
            if len(overlap) >= 3:
                verdict, vcls = "Both agree", "verdict-agree"
            elif overlap:
                verdict, vcls = "Complementary", "verdict-comp"
            else:
                verdict, vcls = "Disjoint", "verdict-disjoint"
            stats = f"predicate <b>{n_pred}</b> · rudy <b>{n_rudy}</b>"

        cards.append(dedent(f"""
            <a class='qcard{' qcard-rejected' if (rejected and not rudy_top) else ''}' href='{qid}.html'>
              <div class='qcard-head'>
                <span class='qid'>Q{i:02d}</span>
                <span class='verdict {vcls}'>{html.escape(verdict)}</span>
              </div>
              <div class='qthumb'>{thumb}</div>
              <div class='qtext'>{html.escape(pred_q['query'])}</div>
              <div class='qchips'>{chips}</div>
              <div class='qstats'>{stats}</div>
            </a>
        """).strip())

    body = dedent(f"""
        <header class='page-head'>
          <div class='breadcrumb'>/audit/investor-rudy-demo/</div>
          <h1>Rudy-Trained Tactical Search — Investor Demo</h1>
          <p class='lead'>
            Hero page for the Rudy-trained tactical retriever. Left column: SkillCorner
            predicate search (deterministic filters). Right column: <b>Rudy-Trained
            Tactical Search</b> — a ranker built on Rudy's <b>175 hand-labelled clip
            cards</b> and <b>46 analyst pair judgments</b>, with propagated soft labels
            over a 7,187-window bank. Every result card carries a <b>confidence tag</b>
            so the audience can tell human labels from model inferences.
          </p>
          {banner_html(model_source)}
        </header>

        {LEGEND}

        <h2 class='qgrid-header'>Curated query gallery (16)</h2>
        <section class='qgrid'>
          {''.join(cards)}
        </section>

        <section class='cta-block'>
          <h2>Want to extend the training set?</h2>
          <p>The <a href='label-queue/'>Rudy labelling queue</a> contains 200+ pre-mined
             (query, window) candidates ready for fast grading. Each export ships as
             JSONL ready for the next training run.</p>
          <p><a class='cta-btn' href='label-queue/'>Open the labelling UI →</a></p>
        </section>

        <footer class='page-foot'>
          <p>Sources: <code>_old_predicate_results.json</code> · <code>_old_rudy_results.json</code>
             · <code>rudy_semantic_index.jsonl</code> · <code>clip_card_index.json</code>
             · <code>EXPECTED_PER_QUERY.md</code></p>
          <p>Sister surface: <a href='../investor-query-comparison/'>/audit/investor-query-comparison/</a></p>
        </footer>
    """)
    return page_head("Rudy-Trained Tactical Search — investor demo") + body + page_foot()


# ---------------------------------------------------------------------------
# Detail page
# ---------------------------------------------------------------------------
def render_detail(idx: int, pred_q: dict, rudy_q: dict, intent: dict, media: dict,
                  sem_by_wid: dict, labelled: set[str], expected: dict, model_source: str,
                  prev_qid: str | None, next_qid: str | None) -> str:
    qnum = f"Q{idx:02d}"
    pred_rejected = pred_q.get("rejected", False)
    pred_top = pred_q.get("top_10", [])[:5]
    rudy_top = rudy_q.get("top_10", [])[:5]
    intent_mech = intent.get("primary_mechanism")

    intent_chips = pred_q.get("intent_chips") or []
    extras = []
    if intent.get("rudy_analogy_mode"):
        extras.append("rudy_analogy_mode")
    if intent_mech:
        extras.append(f"mech: {intent_mech}")
    chips_html = " ".join(_chip(c, "chip-explain") for c in intent_chips)
    extras_html = " ".join(_chip(c, "chip-rudy-explain") for c in extras)

    # ---- EXPECTED note ----
    exp_block = ""
    exp_text = expected.get(idx)
    if exp_text:
        exp_block = dedent(f"""
            <section class='expected-block'>
              <h3>EXPECTED (written before generating results)</h3>
              <pre>{html.escape(exp_text)}</pre>
            </section>
        """)

    # ---- left column: predicate ----
    if pred_rejected:
        pred_block = dedent(f"""
            <section class='reject-box col-pred'>
              <h3>SkillCorner Predicate Search rejected</h3>
              <p class='reject-reason'>{html.escape(pred_q.get('rejection_reason') or 'rejected')}</p>
              <p class='muted'>The deterministic predicate compiler has no team filter and no
                concept of "vague tactical interest", so it refuses cleanly rather than
                inventing results.</p>
            </section>
        """)
    else:
        n_total = pred_q.get("n_candidates_total", 0)
        cards_html = "".join(
            render_pred_card(i + 1, c, media, sem_by_wid, labelled, intent_mech)
            for i, c in enumerate(pred_top)
        ) or "<p class='muted'>no predicate candidates</p>"
        pred_block = dedent(f"""
            <section class='block col-pred'>
              <div class='col-head col-head-pred'>
                <span class='col-title'>🔍 SkillCorner Predicate Search</span>
                <span class='col-sub'>{n_total} candidates · top 5</span>
              </div>
              <div class='card-grid'>{cards_html}</div>
            </section>
        """)

    # ---- right column: Rudy-trained ----
    if not rudy_top:
        rudy_block = dedent(f"""
            <section class='reject-box col-rudy'>
              <h3>Rudy-Trained Tactical Search returned no results</h3>
              <p class='reject-reason'>Intent has no usable anchor mechanism — the trained ranker
                refuses to invent results rather than degrade silently.</p>
            </section>
        """)
    else:
        anchors = rudy_q.get("anchors", [])[:3]
        anchor_chips = " ".join(_chip(f"anchor: {a.get('primary_mechanism','?')}", "chip-rudy-overlap")
                                for a in anchors)
        cards_html = "".join(
            render_rudy_card(i + 1, c, media, sem_by_wid, labelled, intent_mech)
            for i, c in enumerate(rudy_top)
        )
        source_tag = ("trained ranker" if model_source == "model"
                      else "ensemble + reranker baseline (trained-model fallback)")
        rudy_block = dedent(f"""
            <section class='block col-rudy'>
              <div class='col-head col-head-rudy'>
                <span class='col-title'>🧠 Rudy-Trained Tactical Search</span>
                <span class='col-sub'>{len(rudy_q.get('top_10', []))} candidates · top 5 · {html.escape(source_tag)}</span>
              </div>
              <div class='chips chip-row-anchors'>{anchor_chips}</div>
              <div class='card-grid'>{cards_html}</div>
            </section>
        """)

    # ---- diff row ----
    if pred_top and rudy_top:
        pred_only, overlap, rudy_only = compute_diff(pred_top, rudy_top)
        n_pred_only = len({c["window_id"] for c in pred_top} - {c["window_id"] for c in rudy_top})
        n_rudy_only = len({c["window_id"] for c in rudy_top} - {c["window_id"] for c in pred_top})
        n_overlap = len({c["window_id"] for c in pred_top} & {c["window_id"] for c in rudy_top})

        def panel(title, sub, items, css):
            if not items:
                inner = "<p class='muted'>(none)</p>"
            else:
                cards = []
                for k, c in items:
                    if k == "pred":
                        cards.append(render_pred_card(0, c, media, sem_by_wid, labelled, intent_mech, small=True))
                    else:
                        cards.append(render_rudy_card(0, c, media, sem_by_wid, labelled, intent_mech, small=True))
                inner = "<div class='card-grid'>" + "".join(cards) + "</div>"
            return dedent(f"""
                <section class='block diff-panel {css}'>
                  <h3 class='diff-title'>{title}</h3>
                  <p class='diff-sub'>{sub}</p>
                  {inner}
                </section>
            """).strip()

        diff_row = dedent(f"""
            <section class='diff-row'>
              {panel('Predicate-only', f'{n_pred_only} window(s) only in predicate top-5.', pred_only, 'diff-pred')}
              {panel('Overlap', f'{n_overlap} window(s) in both — agreement.', overlap, 'diff-overlap')}
              {panel('Rudy-only', f'{n_rudy_only} window(s) Rudy ranks that predicate misses.', rudy_only, 'diff-rudy')}
            </section>
        """)
    else:
        diff_row = dedent("""
            <section class='diff-row'>
              <section class='block diff-panel diff-empty'>
                <h3 class='diff-title'>Diff unavailable</h3>
                <p class='diff-sub'>One side returned no results — see honest-fail above.</p>
              </section>
            </section>
        """)

    rudy_add_prose = what_rudy_adds(pred_top, rudy_top, intent, sem_by_wid, labelled, model_source)
    add_block = dedent(f"""
        <section class='block prose-block'>
          <h3>What Rudy labels added</h3>
          <p>{rudy_add_prose}</p>
        </section>
    """)

    nav_prev = f"<a class='nav-link' href='{prev_qid}.html'>← {prev_qid}</a>" if prev_qid else "<span></span>"
    nav_next = f"<a class='nav-link' href='{next_qid}.html'>{next_qid} →</a>" if next_qid else "<span></span>"

    body = dedent(f"""
        <header class='page-head'>
          <div class='breadcrumb'>
            <a href='index.html'>/audit/investor-rudy-demo/</a> · {qnum}
          </div>
          <h1><span class='qid-large'>{qnum}.</span> {html.escape(pred_q['query'])}</h1>
          <div class='chips chip-row-large'>{chips_html} {extras_html}</div>
          {banner_html(model_source)}
        </header>

        {exp_block}

        <div class='two-col'>
          {pred_block}
          {rudy_block}
        </div>

        {diff_row}

        {add_block}

        {LEGEND}

        <nav class='nav-row'>
          {nav_prev}
          <a class='nav-link nav-home' href='index.html'>all queries</a>
          {nav_next}
        </nav>

        <footer class='page-foot'>
          <p>Generator: <code>_generate.py</code> · sources: <code>_old_predicate_results.json</code>,
             <code>_old_rudy_results.json</code>, <code>rudy_semantic_index.jsonl</code></p>
        </footer>
    """)
    return page_head(f"{qnum} — {pred_q['query']}") + body + page_foot()


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------
STYLES = r"""
* { box-sizing: border-box; }
body {
  font: 14px/1.55 -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  margin: 0 auto; padding: 18px 24px; background: #f5f6f8; color: #222;
  max-width: 1700px;
}
a { color: #1a4d8a; text-decoration: none; }
a:hover { text-decoration: underline; }
code { font: 12px ui-monospace, Menlo, monospace; background: #eef0f4; padding: 1px 4px; border-radius: 3px; }
.muted { color: #888; }

.page-head { margin-bottom: 18px; }
.page-head h1 { margin: 4px 0 6px 0; font-size: 22px; }
.qid-large { color: #8a4a00; font-family: ui-monospace, Menlo, monospace; }
.breadcrumb { font: 12px ui-monospace, Menlo, monospace; color: #888; margin-bottom: 4px; }
.lead { color: #555; margin: 0 0 10px 0; max-width: 980px; }
.page-foot { margin-top: 28px; padding-top: 14px; border-top: 1px solid #ddd;
  font-size: 12px; color: #888; }

/* Banner (Rudy-demo theme — purple stripe) */
.banner {
  background: #f5edff; border: 1px solid #6a3eaa; border-left-width: 4px;
  padding: 10px 14px; border-radius: 5px; margin-bottom: 14px; color: #3a1f6a;
}
.banner b { color: #2a155a; }
.banner-line { font-size: 13px; }
.banner-line + .banner-line { margin-top: 3px; }
.banner-sub { font-size: 12px; color: #4a2f8a; margin-top: 6px; }

/* EXPECTED block */
.expected-block { background: #fffceb; border: 1px solid #d4b400; border-left: 4px solid #d4b400;
  padding: 10px 14px; border-radius: 5px; margin-bottom: 14px; }
.expected-block h3 { margin: 0 0 6px 0; font-size: 13px; color: #7a5800; }
.expected-block pre { margin: 0; white-space: pre-wrap; font: 12px ui-monospace, Menlo, monospace;
  color: #4a3a00; background: transparent; }

/* Legend */
.legend { background: #fff; padding: 10px 14px; margin-bottom: 14px; }
.legend h3 { margin: 0 0 8px 0; font-size: 13px; }
.legend-row { display: flex; gap: 10px; align-items: center; margin-bottom: 4px; font-size: 12px; }
.legend-sub { color: #555; }

/* Landing grid */
.qgrid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
.qcard { display: block; background: #fff; border: 1px solid #ddd; border-radius: 6px;
  padding: 12px 14px; color: inherit; transition: box-shadow .1s, border-color .1s; }
.qcard:hover { text-decoration: none; border-color: #6a3eaa;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.qcard-rejected { background: #fff8e1; border-color: #d4a017; }
.qcard-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.qid { font: 11px ui-monospace, Menlo, monospace; background: #6a3eaa; color: #fff;
  padding: 2px 7px; border-radius: 3px; font-weight: 700; }
.qthumb { margin-bottom: 8px; }
.qtext { font-size: 14px; font-weight: 500; margin-bottom: 8px; min-height: 2.6em; }
.qchips { margin-bottom: 8px; min-height: 22px; }
.qstats { font-size: 12px; color: #555; }
.qstats b { color: #222; }
.qgrid-header { margin: 20px 0 10px 0; font-size: 16px; }

.verdict { font-size: 10px; padding: 2px 8px; border-radius: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.3px; }
.verdict-agree    { background: #d6f0d6; color: #1a5f1a; }
.verdict-comp     { background: #e8e0fc; color: #4a2a8a; }
.verdict-disjoint { background: #ffe5dc; color: #b8551a; }
.verdict-pred     { background: #cfe2ff; color: #1a4d8a; }
.verdict-rudy     { background: #fde2c1; color: #8a4a00; }
.verdict-fail     { background: #f8e0e0; color: #8a1a1a; }

/* Two-col layout */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }
@media (max-width: 1100px) { .two-col { grid-template-columns: 1fr; } }
.col-pred { border-left: 4px solid #1a4d8a; background: #fbfcfe; }
.col-rudy { border-left: 4px solid #6a3eaa; background: #faf6ff; }

.col-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px;
  border-bottom: 1px solid #e3e7ee; padding-bottom: 6px; }
.col-head-pred .col-title { color: #1a4d8a; font-weight: 700; font-size: 15px; }
.col-head-rudy .col-title { color: #6a3eaa; font-weight: 700; font-size: 15px; }
.col-sub { font-size: 12px; color: #888; }
.chip-row-anchors { margin-bottom: 8px; }

.block { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 12px 14px; }
.prose-block { margin-top: 18px; border-left: 4px solid #6a3eaa; background: #faf6ff; }
.prose-block h3 { margin: 0 0 6px 0; font-size: 14px; color: #4a2a8a; }
.prose-block p  { margin: 0; color: #333; }

/* Cards */
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.card { background: #fafbfd; border: 1px solid #e3e7ee; border-radius: 5px; padding: 8px; position: relative; }
.card-pred { background: #f6f9fd; }
.card-rudy { background: #f7f0ff; border-color: #d4c0f0; }
.card-small { font-size: 11px; }
.card-small .vid { max-height: 90px; }
.card-head { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; flex-wrap: wrap; }

.rank { background: #1a4d8a; color: #fff; padding: 1px 7px; border-radius: 3px;
  font-weight: 700; font-size: 10px; }
.rank-rudy { background: #6a3eaa; }
.wid { font: 10px ui-monospace, Menlo, monospace; color: #666; flex: 1;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Confidence tags (the trust boundary) */
.conf-tag { font-size: 9.5px; padding: 1px 6px; border-radius: 3px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.3px; white-space: nowrap; }
.conf-tag-labelled  { background: #1a7c1a; color: #fff; }
.conf-tag-suggested { background: #6a3eaa; color: #fff; }
.conf-tag-model     { background: #888; color: #fff; }
.conf-tag-pred      { background: #1a4d8a; color: #fff; }

.vid { width: 100%; max-height: 130px; background: #000; border-radius: 3px; margin-bottom: 5px; }
.vid-anim { background: #2a2a3a; }
.no-mp4 { height: 90px; background: #f0f1f4; display: flex; align-items: center;
  justify-content: center; color: #999; font-size: 11px; font-style: italic;
  border-radius: 3px; margin-bottom: 5px; }
.no-mp4-small { height: 72px; }

.media-tag { font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px;
  margin-bottom: 5px; display: inline-block; letter-spacing: 0.3px; }
.tag-broadcast { background: #d6f0d6; color: #1a5f1a; }
.tag-anim { background: #e8e0fc; color: #4a2a8a; }
.tag-inline { padding: 0 5px; font-size: 11px; border-radius: 3px; }

.chips { display: flex; flex-wrap: wrap; gap: 3px; }
.chip { background: #eef2fa; color: #1a4d8a; padding: 1px 6px; border-radius: 3px; font-size: 10.5px; }
.chip-pos { background: #dcf3dc; color: #1a7c1a; }
.chip-press { background: #ffe5dc; color: #b8551a; }
.chip-danger { background: #fde0e0; color: #b03030; }
.chip-loss { background: #fff3cd; color: #5a4108; }
.chip-explain { background: #eef; color: #1a4d8a; padding: 2px 8px; font-size: 11px; }
.chip-rudy-explain { background: #ece0fc; color: #4a2a8a; padding: 2px 8px; font-size: 11px; }
.chip-rudy-mech    { background: #ece0fc; color: #4a2a8a; }
.chip-rudy-score   { background: #f0e5fc; color: #553285; }
.chip-rudy-overlap { background: #e8d4f7; color: #4a2a8a; }
.chip-row-large { margin-top: 2px; }
.score { font: 10px ui-monospace, Menlo, monospace; color: #777; margin-top: 4px; }

.reject-box { background: #fff8e1; border: 1px solid #d4a017; border-radius: 6px; padding: 14px 16px; }
.reject-box h3 { margin: 0 0 8px 0; color: #7a5500; font-size: 14px; }
.reject-reason { font-size: 13px; color: #5a4108; margin: 0 0 8px 0; }
.col-pred.reject-box { border-left: 4px solid #1a4d8a; }
.col-rudy.reject-box { border-left: 4px solid #6a3eaa; }

.diff-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; margin-top: 18px; }
@media (max-width: 1100px) { .diff-row { grid-template-columns: 1fr; } }
.diff-panel { padding: 12px 14px; }
.diff-pred    { border-top: 4px solid #1a4d8a; }
.diff-overlap { border-top: 4px solid #1a7c1a; background: #f6fbf6; }
.diff-rudy    { border-top: 4px solid #6a3eaa; }
.diff-empty   { border-top: 4px solid #888; grid-column: 1 / -1; text-align: center; padding: 18px; }
.diff-title { margin: 0 0 4px 0; font-size: 13px; }
.diff-sub   { margin: 0 0 10px 0; font-size: 12px; color: #666; }

.nav-row { display: flex; justify-content: space-between; align-items: center;
  margin-top: 22px; padding-top: 14px; border-top: 1px solid #ddd; }
.nav-link { font: 12px ui-monospace, Menlo, monospace; padding: 4px 10px;
  background: #fff; border: 1px solid #ccc; border-radius: 4px; color: #1a4d8a; }
.nav-link:hover { background: #eef; text-decoration: none; }
.nav-home { background: #6a3eaa; color: #fff; border-color: #6a3eaa; }
.nav-home:hover { background: #4a2880; color: #fff; }
.rej { color: #b8860b; font-weight: 700; }

.cta-block { background: #fff; border: 1px solid #6a3eaa; border-left-width: 4px;
  border-radius: 6px; padding: 14px 16px; margin-top: 20px; }
.cta-block h2 { margin: 0 0 6px 0; font-size: 16px; color: #4a2a8a; }
.cta-btn { display: inline-block; background: #6a3eaa; color: #fff; padding: 6px 14px;
  border-radius: 4px; font-weight: 700; margin-top: 4px; }
.cta-btn:hover { background: #4a2880; color: #fff; text-decoration: none; }
"""


# ---------------------------------------------------------------------------
# Model card + README
# ---------------------------------------------------------------------------
MODEL_CARD = """\
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
"""


README = """\
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
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    pred_doc = json.loads(PRED_RESULTS.read_text())
    rudy_doc = json.loads(RUDY_RESULTS.read_text())
    intents = json.loads(INTENTS_SRC.read_text())
    clip_idx = json.loads(CLIP_CARD_INDEX.read_text())
    broadcast_map = {c["clip_id"]: c.get("mp4_url") for c in clip_idx["cards"] if c.get("mp4_url")}
    labelled_clip_ids = {c["clip_id"] for c in clip_idx["cards"]}
    expected = load_expected(EXPECTED_MD)

    # Semantic index
    sem_rows = load_jsonl(SEM_INDEX)
    sem_by_wid = {r["window_id"]: r for r in sem_rows}

    # Model rankings — prefer trained model, else fall back to ensemble baseline
    model_rows = load_jsonl(MODEL_RANKINGS)
    model_source = "fallback"
    if model_rows:
        # Convert model_rankings.jsonl into the same shape as rudy_doc[qid].top_10
        by_qid: dict[str, list[dict]] = defaultdict(list)
        for r in model_rows:
            qid = str(r.get("query_id") or r.get("qid") or "").lstrip("Q").lstrip("q").lstrip("0") or "0"
            by_qid[qid].append(r)
        for qid, rows in by_qid.items():
            rows.sort(key=lambda x: -x.get("model_score", x.get("score", 0)))
            rudy_doc.setdefault(qid, {})
            rudy_doc[qid]["top_10"] = rows[:10]
        model_source = "model"

    media = build_media_index(broadcast_map)

    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "styles.css").write_text(STYLES.lstrip())
    (HERE / "README.md").write_text(README)
    (HERE / "model_card.md").write_text(MODEL_CARD)
    (HERE / "query_intents.json").write_text(json.dumps(intents, indent=2))

    pred_results = pred_doc["queries"]

    # Combined results.json (predicate + Rudy top-5 per query)
    combined = {
        "schema_version": "investor_rudy_demo.v0",
        "model_source": model_source,
        "n_queries": len(pred_results),
        "queries": {},
    }
    for i, pred_q in enumerate(pred_results, start=1):
        rudy_q = rudy_doc.get(str(i), {"top_10": [], "anchors": []})
        combined["queries"][str(i)] = {
            "query": pred_q["query"],
            "intent": intents.get(str(i), {}),
            "predicate_top5": pred_q.get("top_10", [])[:5],
            "rudy_top5": rudy_q.get("top_10", [])[:5],
            "rejected_predicate": pred_q.get("rejected", False),
        }
    (HERE / "results.json").write_text(json.dumps(combined, indent=2, default=str))

    n = len(pred_results)
    (HERE / "index.html").write_text(
        render_landing(pred_results, rudy_doc, intents, media, sem_by_wid, labelled_clip_ids, model_source)
    )
    for i, pred_q in enumerate(pred_results, start=1):
        rudy_q = rudy_doc.get(str(i), {"top_10": [], "anchors": []})
        intent = intents.get(str(i), {})
        prev_qid = f"q{i-1:02d}" if i > 1 else None
        next_qid = f"q{i+1:02d}" if i < n else None
        (HERE / f"q{i:02d}.html").write_text(
            render_detail(i, pred_q, rudy_q, intent, media, sem_by_wid, labelled_clip_ids,
                          expected, model_source, prev_qid, next_qid)
        )

    print(f"wrote {n} detail pages + index.html + styles.css + results.json + model_card.md + README.md")
    print(f"media index size: {len(media)} (broadcast={sum(1 for v in media.values() if v['kind']=='broadcast')}, "
          f"animation={sum(1 for v in media.values() if v['kind']=='animation')})")
    print(f"model source: {model_source}")
    print(f"labelled clip ids: {len(labelled_clip_ids)}")
    print(f"semantic index rows: {len(sem_rows)}")


if __name__ == "__main__":
    main()
