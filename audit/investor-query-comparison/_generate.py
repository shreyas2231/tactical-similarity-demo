"""Static-site generator for /audit/investor-query-comparison/.

Reads four artifacts produced by the IQC sprint and emits an investor-
facing two-column comparison page for each curated query plus a landing
grid:

    - runs/investor_query_comparison/artifacts/predicate_results.json
    - runs/investor_query_comparison/artifacts/rudy_results.json
    - runs/investor_query_comparison/artifacts/query_intents.json
    - runs/clip_card_index.json   (broadcast mp4 URLs by window_id)

Each detail page (qNN.html) puts predicate retrieval on the left, Rudy
tactical-similarity retrieval on the right, and a "diff row" of
predicate-only / overlap / rudy-only windows below. Honest-fails (team
filters, vague queries) render a rejection panel without fabricating
results.

Run from this directory:
    python3 _generate.py
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
from textwrap import dedent

HERE = Path(__file__).parent
FWM = Path("/home/ubuntu/fwm")
PRED_RESULTS = FWM / "runs/investor_query_comparison/artifacts/predicate_results.json"
RUDY_RESULTS = FWM / "runs/investor_query_comparison/artifacts/rudy_results.json"
INTENTS_FILE = FWM / "runs/investor_query_comparison/artifacts/query_intents.json"
CLIP_CARD_INDEX = FWM / "runs/clip_card_index.json"
RECOMMENDED_FILE = FWM / "runs/investor_query_comparison/artifacts/recommended_investor_queries.json"

LOCAL_ANIM_ROOT = HERE / "animations"  # populated by copy step


# ---------------------------------------------------------------------------
# Media URL resolver
# ---------------------------------------------------------------------------
def build_media_index(broadcast_map: dict[str, str]) -> dict[str, dict]:
    """For every window_id we know about, resolve the best media URL.

    Preference order:
      1. broadcast SkillCorner clip (clip_card_index)
      2. pitch animation (anonymised top-down render, copied locally)
    """
    media: dict[str, dict] = {}
    for wid, url in broadcast_map.items():
        if not url:
            continue
        media[wid] = {"url": url, "kind": "broadcast"}

    # Local animations (relative to a qNN.html page in this directory)
    for match_dir in LOCAL_ANIM_ROOT.glob("*"):
        if not match_dir.is_dir():
            continue
        for f in match_dir.glob("*.mp4"):
            stem = f.stem  # e.g. 1886347_1886347_104_23303
            wid = stem.replace("_", ":", 3)
            if wid in media:
                continue
            media[wid] = {
                "url": f"animations/{match_dir.name}/{f.name}",
                "kind": "animation",
            }
    return media


# ---------------------------------------------------------------------------
# Chip helpers
# ---------------------------------------------------------------------------
def _chip(text: str, cls: str = "") -> str:
    cls = (" " + cls) if cls else ""
    return f"<span class='chip{cls}'>{html.escape(text)}</span>"


ZONE_LABEL = {
    "defensive_third": "defensive",
    "middle_third": "middle",
    "final_third": "final",
}
LANE_LABEL = {
    "left": "left",
    "left_half_space": "left-hs",
    "central": "central",
    "right_half_space": "right-hs",
    "right": "right",
}
PHASE_LABEL = {
    "build_up": "build_up",
    "deep_build_up": "deep_build_up",
    "create": "create",
    "finish": "finish",
    "transition": "transition",
    "chaotic": "chaotic",
}


def render_pred_card_chips(facts: dict, raw_chips: list[str] | None = None) -> str:
    chips = []
    if facts.get("start_zone"):
        chips.append(_chip(f"start: {ZONE_LABEL.get(facts['start_zone'], facts['start_zone'])}"))
    if facts.get("end_zone"):
        chips.append(_chip(f"end: {ZONE_LABEL.get(facts['end_zone'], facts['end_zone'])}"))
    if facts.get("dominant_lane"):
        chips.append(_chip(f"lane: {LANE_LABEL.get(facts['dominant_lane'], facts['dominant_lane'])}"))
    if facts.get("enters_box"):
        chips.append(_chip("box \u2713", "chip-pos"))
    if facts.get("crosses_central_lane"):
        chips.append(_chip("switch \u2713", "chip-pos"))
    if facts.get("x_progression_m") is not None and abs(facts["x_progression_m"]) >= 5:
        chips.append(_chip(f"x_prog: {facts['x_progression_m']:+.0f}m"))
    if facts.get("y_displacement_m") is not None and abs(facts["y_displacement_m"]) >= 10:
        chips.append(_chip(f"y_disp: {facts['y_displacement_m']:+.0f}m"))
    if facts.get("phase_type"):
        chips.append(_chip(PHASE_LABEL.get(facts["phase_type"], facts["phase_type"]), "chip-phase"))
    if facts.get("under_pressure"):
        chips.append(_chip("under_pressure", "chip-press"))
    if facts.get("dangerous"):
        chips.append(_chip("dangerous", "chip-danger"))
    if facts.get("xthreat_delta") is not None and abs(facts["xthreat_delta"]) >= 0.02:
        chips.append(_chip(f"xT \u0394 {facts['xthreat_delta']:+.3f}"))
    if facts.get("possession_loss_in_window"):
        chips.append(_chip("turnover", "chip-loss"))
    return " ".join(chips)


def render_rudy_card_chips(c: dict) -> str:
    """Right-column chips: anchor mechanism, tier, similarity, predicate overlap."""
    chips = []
    mech = c.get("propagated_mechanism") or c.get("matched_anchor_mechanism")
    if mech:
        chips.append(_chip(f"mech: {mech}", "chip-rudy-mech"))
    v1 = c.get("propagated_v1_category") or c.get("matched_anchor_v1_category")
    if v1:
        chips.append(_chip(f"v1: {v1}", "chip-rudy-mech"))
    tier = c.get("confidence_tier")
    if tier:
        chips.append(_chip(f"tier: {tier}", f"chip-tier-{tier.replace('_','-')}"))
    cos = c.get("ensemble_score")
    if cos is not None:
        chips.append(_chip(f"cos {cos:.3f}", "chip-rudy-score"))
    # predicate overlap is the *qualitative* attributes Rudy says it found
    # in the matched window — render as soft chips
    for tag in (c.get("predicate_overlap") or [])[:4]:
        chips.append(_chip(tag, "chip-rudy-overlap"))
    return " ".join(chips)


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
            f'<div class="media-tag tag-broadcast">\U0001F7E2 BROADCAST</div>'
        )
    return (
        f'<video src="{html.escape(info["url"])}" controls preload="none" muted class="{klass} vid-anim"></video>'
        f'<div class="media-tag tag-anim">\U0001F7E3 PITCH ANIMATION</div>'
    )


def render_pred_card(rank: int, item: dict, media: dict, *, small: bool = False) -> str:
    wid = item["window_id"]
    conf = item.get("confidence", "n/a")
    score = item.get("score", 0.0)
    facts = item.get("predicate_facts", {}) or {}
    raw_chips = item.get("predicate_chips", [])
    tile = media_tile(wid, media, small=small)
    chips_html = render_pred_card_chips(facts, raw_chips)
    if not chips_html and raw_chips:
        chips_html = " ".join(_chip(c) for c in raw_chips[:4])
    klass = "card card-small" if small else "card"
    return dedent(f"""
        <div class='{klass} card-pred'>
          <div class='card-head'>
            <span class='rank'>#{rank}</span>
            <span class='wid' title='{html.escape(wid)}'>{html.escape(wid)}</span>
            <span class='conf conf-{conf}'>{html.escape(conf)}</span>
          </div>
          {tile}
          <div class='chips'>{chips_html}</div>
          <div class='score'>predicate score {score:.4f}</div>
        </div>
    """).strip()


def render_rudy_card(rank: int, item: dict, media: dict, *, small: bool = False) -> str:
    wid = item["window_id"]
    tier = item.get("confidence_tier", "unknown")
    final = item.get("final_score", 0.0)
    cos = item.get("ensemble_score", 0.0)
    tile = media_tile(wid, media, small=small)
    chips_html = render_rudy_card_chips(item)
    klass = "card card-small" if small else "card"
    return dedent(f"""
        <div class='{klass} card-rudy'>
          <div class='card-head'>
            <span class='rank rank-rudy'>#{rank}</span>
            <span class='wid' title='{html.escape(wid)}'>{html.escape(wid)}</span>
            <span class='conf conf-tier-{tier.replace("_","-")}'>{html.escape(tier)}</span>
          </div>
          {tile}
          <div class='chips'>{chips_html}</div>
          <div class='score'>cos {cos:.3f} &middot; rerank+score {final:.3f}</div>
        </div>
    """).strip()


# ---------------------------------------------------------------------------
# Diff row
# ---------------------------------------------------------------------------
def compute_diff(pred_top: list[dict], rudy_top: list[dict]):
    """Return (pred_only, overlap, rudy_only) as lists of (rank_in_panel, item)."""
    pred_set = {c["window_id"] for c in pred_top}
    rudy_set = {c["window_id"] for c in rudy_top}
    overlap_wids = pred_set & rudy_set

    overlap = []
    seen = set()
    for c in pred_top:
        if c["window_id"] in overlap_wids and c["window_id"] not in seen:
            overlap.append(("pred", c))
            seen.add(c["window_id"])
    pred_only = [("pred", c) for c in pred_top if c["window_id"] not in overlap_wids]
    rudy_only = [("rudy", c) for c in rudy_top if c["window_id"] not in overlap_wids]
    return pred_only[:3], overlap[:3], rudy_only[:3]


def render_diff_card(kind: str, item: dict, media: dict) -> str:
    if kind == "pred":
        return render_pred_card(0, item, media, small=True)
    return render_rudy_card(0, item, media, small=True)


# ---------------------------------------------------------------------------
# Verdict for landing card
# ---------------------------------------------------------------------------
def verdict_for_query(pred_q: dict, rudy_q: dict) -> tuple[str, str]:
    """Return (label, css_class) for the landing-page verdict pill."""
    pred_rejected = pred_q.get("rejected", False)
    rudy_top = rudy_q.get("top_10", [])
    if pred_rejected and not rudy_top:
        return ("Honest fail \u2014 both reject", "verdict-fail")
    if pred_rejected and rudy_top:
        return ("Rudy only \u2014 predicate rejects", "verdict-rudy")
    if not pred_rejected and not rudy_top:
        return ("Predicate only \u2014 Rudy empty", "verdict-pred")

    pred_top = pred_q.get("top_10", [])[:5]
    rudy_top5 = rudy_top[:5]
    overlap = {c["window_id"] for c in pred_top} & {c["window_id"] for c in rudy_top5}
    if len(overlap) >= 3:
        return ("Both agree", "verdict-agree")
    if len(overlap) >= 1:
        return ("Complementary", "verdict-comp")
    return ("Disjoint \u2014 different cuts", "verdict-disjoint")


def landing_thumbnail(pred_q: dict, rudy_q: dict, media: dict) -> str:
    """Pick a representative tile for the landing card."""
    if not pred_q.get("rejected") and pred_q.get("top_10"):
        wid = pred_q["top_10"][0]["window_id"]
        return media_tile(wid, media, small=True)
    if rudy_q.get("top_10"):
        wid = rudy_q["top_10"][0]["window_id"]
        return media_tile(wid, media, small=True)
    return '<div class="no-mp4 no-mp4-small">honest fail</div>'


# ---------------------------------------------------------------------------
# Banner / chrome
# ---------------------------------------------------------------------------
def banner_html() -> str:
    return dedent("""
        <div class='banner'>
          <div class='banner-line'><b>Internal investor demo &mdash; candidate retrieval, not exhaustive production search.</b></div>
          <div class='banner-line'>Predicate Search and Rudy Tactical Similarity Search are complementary modes; neither claims ground truth.</div>
          <div class='banner-sub'>Predicate column compiles deterministic football predicates (lane, zone, pressure,
            progression). Rudy column does anchor-then-similarity over expert tactical labels and learned embeddings
            (v9c + v11p + reranker_v0). Tiles tagged <span class='tag-broadcast tag-inline'>\U0001F7E2 broadcast</span>
            are SkillCorner clips; <span class='tag-anim tag-inline'>\U0001F7E3 pitch animation</span> tiles are
            anonymised top-down renders (105\u00d768, no player_id) for windows without broadcast video.</div>
        </div>
    """).strip()


def page_head(title: str, *, with_typable: bool = False) -> str:
    js = "<script src='typable.js' defer></script>" if with_typable else ""
    return dedent(f"""\
        <!doctype html>
        <html><head><meta charset='utf-8'>
        <title>{html.escape(title)}</title>
        <meta name='viewport' content='width=device-width, initial-scale=1'>
        <link rel='stylesheet' href='styles.css'>
        {js}
        </head><body>
    """)


def page_foot() -> str:
    return "</body></html>\n"


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------
def render_landing(pred_results: list[dict], rudy_results: dict, intents: dict, media: dict, *, recommended_ids: list[int] | None) -> str:
    cards = []
    for i, pred_q in enumerate(pred_results, start=1):
        rudy_q = rudy_results.get(str(i), {"top_10": []})
        intent = intents.get(str(i), {})
        qid = f"q{i:02d}"
        rejected = pred_q.get("rejected", False)
        rudy_top = rudy_q.get("top_10", [])

        verdict, vcls = verdict_for_query(pred_q, rudy_q)
        thumb = landing_thumbnail(pred_q, rudy_q, media)

        intent_chips = pred_q.get("intent_chips") or []
        chips = " ".join(_chip(c, "chip-explain") for c in intent_chips[:4]) or "<span class='muted'>no chips</span>"

        n_pred = pred_q.get("n_candidates_total", 0)
        n_rudy = len(rudy_top)
        if rejected and not rudy_top:
            stats = "<span class='rej'>both reject</span>"
        elif rejected:
            stats = f"<span class='rej'>predicate rejects</span> &middot; rudy <b>{n_rudy}</b>"
        elif not rudy_top:
            stats = f"predicate <b>{n_pred}</b> &middot; <span class='rej'>rudy empty</span>"
        else:
            stats = f"predicate <b>{n_pred}</b> &middot; rudy <b>{n_rudy}</b>"

        recommended_badge = ""
        if recommended_ids is not None and i in recommended_ids:
            recommended_badge = "<span class='qrec'>curated</span>"

        cards.append(dedent(f"""
            <a class='qcard{' qcard-rejected' if (rejected and not rudy_top) else ''}' href='{qid}.html'>
              <div class='qcard-head'>
                <span class='qid'>Q{i:02d}</span>
                <span class='verdict {vcls}'>{verdict}</span>
                {recommended_badge}
              </div>
              <div class='qthumb'>{thumb}</div>
              <div class='qtext'>{html.escape(pred_q['query'])}</div>
              <div class='qchips'>{chips}</div>
              <div class='qstats'>{stats}</div>
            </a>
        """).strip())

    rec_note = ""
    if recommended_ids is not None:
        rec_note = (f"<p class='lead'><b>Curated subset:</b> Workstream MINER recommended "
                    f"{len(recommended_ids)} queries with the most informative complementarity. "
                    "All 16 are shown; curated ones are flagged.</p>")
    else:
        rec_note = ("<p class='lead'><b>Curated subset:</b> MINER curation not yet available; "
                    "all 16 queries from <code>query_intents.json</code> are rendered.</p>")

    body = dedent(f"""
        <header class='page-head'>
          <div class='breadcrumb'>/audit/investor-query-comparison/</div>
          <h1>Predicate Search vs Rudy Tactical Similarity &mdash; Investor Demo</h1>
          <p class='lead'>
            Type your own tactical query below, or pick one of the curated examples. We retrieve in two
            complementary modes: explicit football predicates (lane, zone, pressure, progression) over
            7,306 SkillCorner windows, AND expert-label similarity over the same corpus using Rudy's
            tactical labels and learned embeddings.
          </p>
          {rec_note}
          {banner_html()}
        </header>

        <section class='typable'>
          <h2>Try your own query</h2>
          <p class='typable-sub'>Free-form query &rarr; deterministic intent parser &rarr;
            predicate retrieval &amp; Rudy similarity retrieval over the full 7,187-window bank. Live backend.</p>
          <form id='qform' onsubmit='return runQuery(event)'>
            <input id='qinput' type='text' placeholder='e.g. left flank progression into the box'
                   autocomplete='off' />
            <button type='submit' id='qbtn'>Search</button>
          </form>
          <div id='qexamples' class='typable-examples'>
            try:
            <a href='#' onclick='setQ("press break through the centre")'>press break through the centre</a> &middot;
            <a href='#' onclick='setQ("dangerous right-sided attack")'>dangerous right-sided attack</a> &middot;
            <a href='#' onclick='setQ("clips tactically similar to a press break")'>tactically similar to a press break</a> &middot;
            <a href='#' onclick='setQ("Liverpool high press")'>Liverpool high press</a> <span class='muted'>(honest fail)</span>
          </div>
          <div id='qteamexamples' class='typable-examples' style='margin-top:6px'>
            <b>team focus</b> (analyst-style questions per team, 7 questions answered):
            <a href='#' onclick='setTeam("4177")'>team 4177</a> &middot;
            <a href='#' onclick='setTeam("1804")'>team 1804</a> &middot;
            <a href='#' onclick='setTeam("2380")'>team 2380</a> &middot;
            <a href='#' onclick='setTeam("1802")'>team 1802</a>
            <span class='muted'>&mdash; or type "team &lt;id&gt;" / "how does 4177 build up"</span>
          </div>
          <div id='qstatus' class='qstatus'></div>
          <div id='qresult'></div>
        </section>

        <h2 class='qgrid-header'>Curated query gallery</h2>
        <section class='qgrid'>
          {''.join(cards)}
        </section>

        <footer class='page-foot'>
          <p>Sources:
             <code>predicate_results.json</code> &middot;
             <code>rudy_results.json</code> &middot;
             <code>query_intents.json</code> &middot;
             <code>clip_card_index.json</code> (broadcast urls)</p>
          <p>Sister surfaces:
             <a href='../query-predicate/'>/audit/query-predicate/</a> (predicate-only audit) &middot;
             <a href='../predicate/'>/audit/predicate/</a> (per-predicate audit) &middot;
             <a href='../../query/'>/query/</a> (deployed LLM demo, unchanged)
          </p>
        </footer>
    """)
    return page_head("Predicate vs Rudy \u2014 investor demo", with_typable=True) + body + page_foot()


# ---------------------------------------------------------------------------
# Detail page
# ---------------------------------------------------------------------------
def render_detail(idx: int, pred_q: dict, rudy_q: dict, intent: dict, media: dict,
                  prev_qid: str | None, next_qid: str | None) -> str:
    qnum = f"Q{idx:02d}"
    qid = f"q{idx:02d}"
    pred_rejected = pred_q.get("rejected", False)
    pred_top = pred_q.get("top_10", [])
    rudy_top = rudy_q.get("top_10", [])

    intent_chips = pred_q.get("intent_chips") or []
    rudy_chips = []
    if intent.get("rudy_analogy_mode"):
        rudy_chips.append("rudy_analogy_mode")
    if intent.get("primary_mechanism"):
        rudy_chips.append(f"mech:{intent['primary_mechanism']}")
    chips_html = " ".join(_chip(c, "chip-explain") for c in intent_chips)
    rudy_chips_html = " ".join(_chip(c, "chip-rudy-explain") for c in rudy_chips)

    # ---- left column: predicate ----
    if pred_rejected:
        pred_block = dedent(f"""
            <section class='reject-box col-pred'>
              <h3>Predicate Search rejected</h3>
              <p class='reject-reason'>{html.escape(pred_q.get('rejection_reason') or 'rejected')}</p>
              <p class='muted'>The deterministic predicate compiler refuses team filters
                 (no <code>team_filter</code> in the predicate index) and refuses queries with no
                 specific tactical predicate. This is the expected behaviour, not a bug.</p>
            </section>
        """)
    else:
        n_total = pred_q.get("n_candidates_total", 0)
        cards_html = "".join(render_pred_card(i + 1, c, media) for i, c in enumerate(pred_top))
        if not cards_html:
            cards_html = "<p class='muted'>no candidates passed predicate filters</p>"
        pred_block = dedent(f"""
            <section class='block col-pred'>
              <div class='col-head col-head-pred'>
                <span class='col-title'>Predicate Search</span>
                <span class='col-sub'>{n_total} candidates &middot; top 10</span>
              </div>
              <div class='card-grid'>{cards_html}</div>
            </section>
        """)

    # ---- right column: rudy ----
    rudy_intent_low = intent.get("confidence") == "low"
    rudy_unsupported = intent.get("unsupported") or []
    if not rudy_top:
        if rudy_intent_low and rudy_unsupported:
            reason = (f"team filter unsupported: {', '.join(rudy_unsupported)} \u2014 "
                      "Rudy's expert-label index is anonymised (no team_id), so this is "
                      "honestly rejected rather than silently degraded.")
        elif rudy_intent_low:
            reason = (f"low-confidence intent ({intent.get('rejection_reason') or 'no anchor mechanism'}) \u2014 "
                      "Rudy refuses to invent results when the intent has no usable anchor.")
        else:
            reason = "Rudy returned no results for this query."
        rudy_block = dedent(f"""
            <section class='reject-box col-rudy'>
              <h3>Rudy Tactical Similarity returned no results</h3>
              <p class='reject-reason'>{html.escape(reason)}</p>
            </section>
        """)
    else:
        anchors = rudy_q.get("anchors", [])
        anchor_chips = " ".join(_chip(f"anchor: {a.get('primary_mechanism','?')}", "chip-rudy-overlap")
                                for a in anchors[:3])
        cards_html = "".join(render_rudy_card(i + 1, c, media) for i, c in enumerate(rudy_top))
        rudy_block = dedent(f"""
            <section class='block col-rudy'>
              <div class='col-head col-head-rudy'>
                <span class='col-title'>Rudy Tactical Similarity</span>
                <span class='col-sub'>{len(rudy_top)} candidates &middot; {len(anchors)} anchors</span>
              </div>
              <div class='chips chip-row-anchors'>{anchor_chips}</div>
              <div class='card-grid'>{cards_html}</div>
            </section>
        """)

    # ---- diff row ----
    if pred_top and rudy_top:
        pred_only, overlap, rudy_only = compute_diff(pred_top, rudy_top)
        n_pred_only_total = len({c["window_id"] for c in pred_top} - {c["window_id"] for c in rudy_top})
        n_rudy_only_total = len({c["window_id"] for c in rudy_top} - {c["window_id"] for c in pred_top})
        n_overlap_total = len({c["window_id"] for c in pred_top} & {c["window_id"] for c in rudy_top})

        def panel(title: str, sub: str, kind: str, items, css: str) -> str:
            if not items:
                cards = "<p class='muted'>(none in top-10)</p>"
            else:
                cards = "<div class='card-grid'>" + "".join(
                    render_diff_card(k, c, media) for k, c in items
                ) + "</div>"
            return dedent(f"""
                <section class='block diff-panel {css}'>
                  <h3 class='diff-title'>{title}</h3>
                  <p class='diff-sub'>{sub}</p>
                  {cards}
                </section>
            """).strip()

        diff_row = dedent(f"""
            <section class='diff-row'>
              {panel('Predicate-only',
                     f'{n_pred_only_total} window(s) the predicate filters surface that Rudy doesn&#39;t put in its top-10. Showing top 3.',
                     'pred', pred_only, 'diff-pred')}
              {panel('Overlap',
                     f'{n_overlap_total} window(s) in both panels&#39; top-10 &mdash; the two systems agree.',
                     'pred', overlap, 'diff-overlap')}
              {panel('Rudy-only',
                     f'{n_rudy_only_total} window(s) Rudy surfaces that no predicate match in top-10. Showing top 3.',
                     'rudy', rudy_only, 'diff-rudy')}
            </section>
        """)
    else:
        diff_row = dedent("""
            <section class='diff-row'>
              <section class='block diff-panel diff-empty'>
                <h3 class='diff-title'>Diff row unavailable</h3>
                <p class='diff-sub'>One side returned no results, so there is no symmetric diff to draw. The honest-fail panel above shows why.</p>
              </section>
            </section>
        """)

    # ---- footer per-page ----
    n_pred_total = pred_q.get("n_candidates_total", 0)
    n_rudy_top = len(rudy_top)
    page_footer = dedent(f"""
        <section class='page-foot-blocks'>
          <div class='foot-block foot-shows'>
            <h3>What this shows</h3>
            <p>This query returned <b>{n_pred_total}</b> candidate(s) by predicate filters
               and <b>{n_rudy_top}</b> candidate(s) by Rudy similarity. The diff row highlights where
               the two modes disagree &mdash; that disagreement is the informative signal, not a defect.</p>
          </div>
          <div class='foot-block foot-not'>
            <h3>What this does not prove</h3>
            <p>Not exhaustive. Not ground truth. Predicate scoring is heuristic. Rudy <em>propagated</em>
               labels are inferred from the nearest hand-labelled anchor and are explicitly tiered
               (<code>labelled</code> &gt; <code>propagated_high</code> &gt; <code>propagated_med</code>);
               high-confidence propagation is not the same as a human label.</p>
          </div>
        </section>
    """)

    nav_prev = f"<a class='nav-link' href='{prev_qid}.html'>&larr; {prev_qid}</a>" if prev_qid else "<span></span>"
    nav_next = f"<a class='nav-link' href='{next_qid}.html'>{next_qid} &rarr;</a>" if next_qid else "<span></span>"

    body = dedent(f"""
        <header class='page-head'>
          <div class='breadcrumb'>
            <a href='index.html'>/audit/investor-query-comparison/</a> &middot; {qnum}
          </div>
          <h1><span class='qid-large'>{qnum}.</span> {html.escape(pred_q['query'])}</h1>
          <div class='chips chip-row-large'>{chips_html} {rudy_chips_html}</div>
          {banner_html()}
        </header>

        <div class='two-col'>
          {pred_block}
          {rudy_block}
        </div>

        {diff_row}

        {page_footer}

        <nav class='nav-row'>
          {nav_prev}
          <a class='nav-link nav-home' href='index.html'>all queries</a>
          {nav_next}
        </nav>

        <footer class='page-foot'>
          <p>Generator: <code>_generate.py</code> &middot;
             intent: <code>parsed_intents.json</code> entry {idx}</p>
        </footer>
    """)
    return page_head(f"{qnum} \u2014 {pred_q['query']}") + body + page_foot()


# ---------------------------------------------------------------------------
# Stylesheet (extends sister page's design tokens, adds two-column +
# Rudy palette + diff-row styling)
# ---------------------------------------------------------------------------
STYLES = r"""
* { box-sizing: border-box; }
body {
  font: 14px/1.55 -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  margin: 0; padding: 18px 24px; background: #f5f6f8; color: #222;
  max-width: 1700px; margin: 0 auto;
}
a { color: #1a4d8a; text-decoration: none; }
a:hover { text-decoration: underline; }
code { font: 12px ui-monospace, Menlo, monospace; background: #eef0f4; padding: 1px 4px; border-radius: 3px; }
.muted { color: #888; }

/* Page chrome */
.page-head { margin-bottom: 18px; }
.page-head h1 { margin: 4px 0 6px 0; font-size: 22px; }
.qid-large { color: #1a4d8a; font-family: ui-monospace, Menlo, monospace; }
.breadcrumb { font: 12px ui-monospace, Menlo, monospace; color: #888; margin-bottom: 4px; }
.lead { color: #555; margin: 0 0 10px 0; max-width: 920px; }
.page-foot { margin-top: 28px; padding-top: 14px; border-top: 1px solid #ddd;
  font-size: 12px; color: #888; }

/* Banner */
.banner {
  background: #fff3cd; border: 1px solid #d4a017; padding: 10px 14px;
  border-radius: 5px; margin-bottom: 14px; color: #5a4108;
}
.banner b { color: #7a5500; }
.banner-line { font-size: 13px; }
.banner-line + .banner-line { margin-top: 3px; }
.banner-sub { font-size: 12px; color: #7a6520; margin-top: 6px; }

/* Landing grid */
.qgrid {
  display: grid; gap: 14px;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}
.qcard {
  display: block; background: #fff; border: 1px solid #ddd; border-radius: 6px;
  padding: 12px 14px; color: inherit; transition: box-shadow 0.1s, border-color 0.1s;
}
.qcard:hover { text-decoration: none; border-color: #1a4d8a;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.qcard-rejected { background: #fff8e1; border-color: #d4a017; }
.qcard-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.qid { font: 11px ui-monospace, Menlo, monospace; background: #1a4d8a; color: #fff;
  padding: 2px 7px; border-radius: 3px; font-weight: 700; }
.qrec { font-size: 10px; padding: 2px 7px; background: #2e7d32; color: #fff;
  border-radius: 3px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; }
.qthumb { margin-bottom: 8px; }
.qtext { font-size: 14px; font-weight: 500; margin-bottom: 8px; min-height: 2.6em; }
.qchips { margin-bottom: 8px; min-height: 22px; }
.qstats { font-size: 12px; color: #555; }
.qstats b { color: #222; }

/* Verdict pills */
.verdict { font-size: 10px; padding: 2px 8px; border-radius: 10px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.3px; }
.verdict-agree    { background: #d6f0d6; color: #1a5f1a; }
.verdict-comp     { background: #e8e0fc; color: #4a2a8a; }
.verdict-disjoint { background: #ffe5dc; color: #b8551a; }
.verdict-pred     { background: #cfe2ff; color: #1a4d8a; }
.verdict-rudy     { background: #fde2c1; color: #8a4a00; }
.verdict-fail     { background: #f8e0e0; color: #8a1a1a; }

/* Detail two-column (predicate left, Rudy right) */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }
@media (max-width: 1100px) {
  .two-col { grid-template-columns: 1fr; }
}

.col-pred  { border-left: 4px solid #1a4d8a; background: #fbfcfe; }
.col-rudy  { border-left: 4px solid #8a4a00; background: #fdf9f3; }

.col-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px;
  border-bottom: 1px solid #e3e7ee; padding-bottom: 6px; }
.col-head-pred .col-title { color: #1a4d8a; font-weight: 700; font-size: 15px; }
.col-head-rudy .col-title { color: #8a4a00; font-weight: 700; font-size: 15px; }
.col-sub { font-size: 12px; color: #888; }

.chip-row-anchors { margin-bottom: 8px; }

/* Result block */
.block { background: #fff; border: 1px solid #ddd; border-radius: 6px;
  padding: 12px 14px; }
.block h2 { margin: 0 0 8px 0; font-size: 14px; }

/* Cards (results) */
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.card { background: #fafbfd; border: 1px solid #e3e7ee; border-radius: 5px; padding: 8px;
  position: relative; }
.card-pred { background: #f6f9fd; }
.card-rudy { background: #fdf6ec; border-color: #ead7b0; }
.card-small { font-size: 11px; }
.card-small .vid { max-height: 90px; }
.card-head { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
.rank { background: #1a4d8a; color: #fff; padding: 1px 7px; border-radius: 3px;
  font-weight: 700; font-size: 10px; }
.rank-rudy { background: #8a4a00; }
.wid { font: 10px ui-monospace, Menlo, monospace; color: #666; flex: 1;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conf { font-size: 9px; padding: 1px 6px; border-radius: 3px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.3px; }
.conf-high   { background: #1a7c1a; color: #fff; }
.conf-medium { background: #d4a017; color: #fff; }
.conf-low    { background: #b03030; color: #fff; }
.conf-na     { background: #888; color: #fff; }
.conf-tier-labelled        { background: #1a7c1a; color: #fff; }
.conf-tier-propagated-high { background: #6a8a3a; color: #fff; }
.conf-tier-propagated-med  { background: #d4a017; color: #fff; }
.conf-tier-propagated-weak { background: #b8551a; color: #fff; }
.conf-tier-unknown         { background: #888; color: #fff; }

.vid { width: 100%; max-height: 130px; background: #000; border-radius: 3px;
  margin-bottom: 5px; }
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
.chip { background: #eef2fa; color: #1a4d8a; padding: 1px 6px; border-radius: 3px;
  font-size: 10.5px; }
.chip-pos    { background: #dcf3dc; color: #1a7c1a; }
.chip-press  { background: #ffe5dc; color: #b8551a; }
.chip-danger { background: #fde0e0; color: #b03030; }
.chip-loss   { background: #fff3cd; color: #5a4108; }
.chip-phase  { background: #e8e0fc; color: #4a2a8a; }
.chip-explain { background: #eef; color: #1a4d8a; padding: 2px 8px; font-size: 11px; }
.chip-rudy-explain { background: #fde2c1; color: #8a4a00; padding: 2px 8px; font-size: 11px; }
.chip-rudy-mech { background: #fff1d8; color: #8a4a00; }
.chip-rudy-score { background: #f3e7d4; color: #553200; }
.chip-rudy-overlap { background: #f5ecdc; color: #6e4a1a; }
.chip-tier-labelled        { background: #d6f0d6; color: #1a5f1a; }
.chip-tier-propagated-high { background: #e8f5d9; color: #4a6f1a; }
.chip-tier-propagated-med  { background: #fff3cd; color: #5a4108; }
.chip-row-large { margin-top: 2px; }
.score { font: 10px ui-monospace, Menlo, monospace; color: #777; margin-top: 4px; }

/* Reject panel */
.reject-box { background: #fff8e1; border: 1px solid #d4a017; border-radius: 6px;
  padding: 14px 16px; }
.reject-box h3 { margin: 0 0 8px 0; color: #7a5500; font-size: 14px; }
.reject-reason { font-size: 13px; color: #5a4108; margin: 0 0 8px 0; }
.col-pred.reject-box { border-left: 4px solid #1a4d8a; }
.col-rudy.reject-box { border-left: 4px solid #8a4a00; }

/* Diff row */
.diff-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; margin-top: 18px; }
@media (max-width: 1100px) {
  .diff-row { grid-template-columns: 1fr; }
}
.diff-panel { padding: 12px 14px; }
.diff-pred    { border-top: 4px solid #1a4d8a; }
.diff-overlap { border-top: 4px solid #1a7c1a; background: #f6fbf6; }
.diff-rudy    { border-top: 4px solid #8a4a00; }
.diff-empty   { border-top: 4px solid #888; grid-column: 1 / -1; text-align: center; padding: 18px; }
.diff-title { margin: 0 0 4px 0; font-size: 13px; }
.diff-sub   { margin: 0 0 10px 0; font-size: 12px; color: #666; }

/* Per-page footer (what this shows / what this does not prove) */
.page-foot-blocks { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 18px; }
@media (max-width: 800px) { .page-foot-blocks { grid-template-columns: 1fr; } }
.foot-block { background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 12px 14px; }
.foot-block h3 { margin: 0 0 6px 0; font-size: 13px; }
.foot-block p  { margin: 0; font-size: 13px; color: #444; }
.foot-shows { border-left: 4px solid #1a7c1a; }
.foot-not   { border-left: 4px solid #d4a017; background: #fffbf0; }

/* Nav */
.nav-row { display: flex; justify-content: space-between; align-items: center;
  margin-top: 22px; padding-top: 14px; border-top: 1px solid #ddd; }
.nav-link { font: 12px ui-monospace, Menlo, monospace; padding: 4px 10px;
  background: #fff; border: 1px solid #ccc; border-radius: 4px; color: #1a4d8a; }
.nav-link:hover { background: #eef; text-decoration: none; }
.nav-home { background: #1a4d8a; color: #fff; border-color: #1a4d8a; }
.nav-home:hover { background: #163e6f; color: #fff; }
.rej { color: #b8860b; font-weight: 700; }
"""


README = """\
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
"""


def main() -> None:
    pred_doc = json.loads(PRED_RESULTS.read_text())
    rudy_doc = json.loads(RUDY_RESULTS.read_text())
    intents = json.loads(INTENTS_FILE.read_text())
    clip_idx = json.loads(CLIP_CARD_INDEX.read_text())
    broadcast_map = {c["clip_id"]: c.get("mp4_url") for c in clip_idx["cards"] if c.get("mp4_url")}

    recommended_ids: list[int] | None = None
    if RECOMMENDED_FILE.exists():
        try:
            rec_doc = json.loads(RECOMMENDED_FILE.read_text())
            ids = rec_doc.get("recommended_ids") or rec_doc.get("ids") or rec_doc.get("queries") or []
            recommended_ids = [int(x) for x in ids]
        except Exception:
            recommended_ids = None

    media = build_media_index(broadcast_map)

    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "styles.css").write_text(STYLES.lstrip())
    (HERE / "README.md").write_text(README)
    (HERE / "parsed_intents.json").write_text(json.dumps(intents, indent=2))

    pred_results = pred_doc["queries"]
    n = len(pred_results)
    (HERE / "index.html").write_text(
        render_landing(pred_results, rudy_doc, intents, media, recommended_ids=recommended_ids)
    )

    for i, pred_q in enumerate(pred_results, start=1):
        rudy_q = rudy_doc.get(str(i), {"top_10": [], "anchors": []})
        intent = intents.get(str(i), {})
        prev_qid = f"q{i-1:02d}" if i > 1 else None
        next_qid = f"q{i+1:02d}" if i < n else None
        (HERE / f"q{i:02d}.html").write_text(
            render_detail(i, pred_q, rudy_q, intent, media, prev_qid, next_qid)
        )

    print(f"wrote {n} detail pages + index.html + styles.css + README.md + parsed_intents.json")
    print(f"media index size: {len(media)} window_ids "
          f"(broadcast={sum(1 for v in media.values() if v['kind']=='broadcast')}, "
          f"animation={sum(1 for v in media.values() if v['kind']=='animation')})")


if __name__ == "__main__":
    main()
