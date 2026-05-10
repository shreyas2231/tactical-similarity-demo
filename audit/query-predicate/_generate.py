"""Static-site generator for /audit/query-predicate/.

Reads the 12-query audit results.json from the predicate compiler and emits
one landing page (index.html) plus one detail page (qNN.html) per query,
sharing styles.css. Banner + caveats are forced on every page.

Run from this directory:
    python3 _generate.py
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from textwrap import dedent

HERE = Path(__file__).parent
RESULTS = Path("/home/ubuntu/fwm/runs/skillcorner_predicate_index_v0/stage2_query_audit/results.json")


# ---------------------------------------------------------------------------
# Helpers — chip rendering for predicate summaries on coverage cards
# ---------------------------------------------------------------------------
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


def _chip(text: str, cls: str = "") -> str:
    cls = (" " + cls) if cls else ""
    return f"<span class='chip{cls}'>{html.escape(text)}</span>"


def render_predicate_chips(p: dict) -> str:
    chips = []
    if p.get("start_zone"):
        chips.append(_chip(f"start: {ZONE_LABEL.get(p['start_zone'], p['start_zone'])}"))
    if p.get("end_zone"):
        chips.append(_chip(f"end: {ZONE_LABEL.get(p['end_zone'], p['end_zone'])}"))
    if p.get("dominant_lane"):
        chips.append(_chip(f"lane: {LANE_LABEL.get(p['dominant_lane'], p['dominant_lane'])}"))
    if p.get("enters_box"):
        chips.append(_chip("box \u2713", "chip-pos"))
    if p.get("x_progression_m") is not None:
        chips.append(_chip(f"x_prog: {p['x_progression_m']:+.0f}m"))
    if p.get("y_displacement_m") is not None and abs(p["y_displacement_m"]) >= 10:
        chips.append(_chip(f"y_disp: {p['y_displacement_m']:+.0f}m"))
    if p.get("phase_type"):
        chips.append(_chip(PHASE_LABEL.get(p["phase_type"], p["phase_type"]), "chip-phase"))
    if p.get("under_pressure"):
        oop = p.get("phase_type_out_of_possession")
        oop_suffix = f" ({oop})" if oop else ""
        chips.append(_chip(f"under_pressure{oop_suffix}", "chip-press"))
    if p.get("dangerous"):
        chips.append(_chip("dangerous", "chip-danger"))
    if p.get("xthreat_delta") is not None and abs(p["xthreat_delta"]) >= 0.02:
        chips.append(_chip(f"xT \u0394 {p['xthreat_delta']:+.3f}"))
    if p.get("defensive_line_delta") is not None and abs(p["defensive_line_delta"]) >= 4:
        chips.append(_chip(f"def-line {p['defensive_line_delta']:+.0f}m"))
    if p.get("shot_or_goal_after_window"):
        chips.append(_chip("\u2192 shot/goal", "chip-pos"))
    if p.get("possession_loss_in_window"):
        chips.append(_chip("turnover", "chip-loss"))
    return " ".join(chips)


def render_card(rank: int, item: dict, *, with_video: bool) -> str:
    wid = item["window_id"]
    conf = item["confidence"]
    score = item.get("score", 0.0)
    mp4 = item.get("mp4_url")
    boosts = item.get("boosts", [])

    if with_video and mp4:
        media = (
            f'<video src="{html.escape(mp4)}" controls preload="none" muted class="vid"></video>'
        )
    elif with_video:
        media = '<div class="no-mp4">no broadcast mp4</div>'
    else:
        media = ""

    chips_html = render_predicate_chips(item.get("predicates_summary", {}))
    boost_html = ""
    if boosts:
        boost_html = "<div class='boosts'>" + " · ".join(html.escape(b) for b in boosts) + "</div>"

    return dedent(f"""
        <div class='card'>
          <div class='card-head'>
            <span class='rank'>#{rank}</span>
            <span class='wid' title='{html.escape(wid)}'>{html.escape(wid)}</span>
            <span class='conf conf-{conf}'>{conf}</span>
          </div>
          {media}
          <div class='chips'>{chips_html}</div>
          <div class='score'>score {score:.4f}</div>
          {boost_html}
        </div>
    """).strip()


# ---------------------------------------------------------------------------
# Banner / shared chrome
# ---------------------------------------------------------------------------
def banner_html() -> str:
    return dedent("""
        <div class='banner'>
          <div class='banner-line'><b>Candidate tactical moments, not exhaustive retrieval.</b></div>
          <div class='banner-line'><b>Internal audit page, not the deployed demo.</b>
            v9c canonical demo, BEST_CHECKPOINT, <code>/query/</code>, and reranker_v0 unchanged.</div>
          <div class='banner-sub'>Query compiler is keyword-based (deterministic, not an LLM).
            Player and team filters are intentionally rejected. Coverage column may include
            windows without broadcast video.</div>
        </div>
    """).strip()


def page_head(title: str, *, depth: int = 0) -> str:
    css = ("../" * depth) + "styles.css"
    return dedent(f"""\
        <!doctype html>
        <html><head><meta charset='utf-8'>
        <title>{html.escape(title)}</title>
        <meta name='viewport' content='width=device-width, initial-scale=1'>
        <link rel='stylesheet' href='{css}'>
        </head><body>
    """)


def page_foot() -> str:
    return "</body></html>\n"


# ---------------------------------------------------------------------------
# Index (landing) page
# ---------------------------------------------------------------------------
def render_landing(results: list[dict]) -> str:
    cards = []
    for i, q in enumerate(results, start=1):
        qid = f"q{i:02d}"
        cq = q["compiled"]
        rejected = cq.get("rejected", False)
        chips = " ".join(_chip(c, "chip-explain") for c in cq.get("explanation_chips", []))
        if not chips:
            chips = "<span class='muted'>no chips parsed</span>"

        if rejected:
            stats = f"<span class='rej'>REJECTED</span> &mdash; {html.escape(cq.get('rejection_reason') or '')}"
            badge_html = "<span class='conf conf-rejected'>rejected</span>"
        else:
            n_total = q["n_candidates_total"]
            n_disp = q["n_candidates_displayable"]
            stats = (f"<b>{n_total}</b> candidates &middot; "
                     f"<b>{n_disp}</b> displayable &middot; "
                     f"{len(cq['filters'])} hard / {len(cq['soft_boosts'])} soft")
            top_conf = (q.get("top_5_coverage") or [{}])[0].get("confidence", "n/a")
            badge_html = f"<span class='conf conf-{top_conf}'>{top_conf}</span>"

        cards.append(dedent(f"""
            <a class='qcard{ ' qcard-rejected' if rejected else ''}' href='{qid}.html'>
              <div class='qcard-head'>
                <span class='qid'>Q{i:02d}</span>
                {badge_html}
              </div>
              <div class='qtext'>{html.escape(q['query'])}</div>
              <div class='qchips'>{chips}</div>
              <div class='qstats'>{stats}</div>
            </a>
        """).strip())

    body = dedent(f"""
        <header class='page-head'>
          <div class='breadcrumb'>/audit/query-predicate/</div>
          <h1>Predicate retrieval &mdash; internal audit</h1>
          <p class='lead'>
            12 curated tactical queries compiled against the SkillCorner predicate
            index v0 (7,306 records, post Stage-3 fix bundle). Static page; one
            detail view per query. Updated 2026-05-10.
          </p>
          {banner_html()}
        </header>

        <section class='qgrid'>
          {''.join(cards)}
        </section>

        <footer class='page-foot'>
          <p>Source: <code>predicate_query_compiler_v0.py</code> &middot;
             results: <code>stage2_query_audit/results.json</code> &middot;
             generator: <code>_generate.py</code></p>
          <p>Sister surfaces: <a href='../predicate/'>/audit/predicate/</a>
             (per-predicate audit) &middot;
             <a href='../../query/'>/query/</a> (deployed LLM demo, unchanged)</p>
        </footer>
    """)

    return page_head("Predicate retrieval \u2014 internal audit") + body + page_foot()


# ---------------------------------------------------------------------------
# Detail page (one per query)
# ---------------------------------------------------------------------------
def render_filter_row(f: dict) -> str:
    val = f.get("value")
    if isinstance(val, list):
        val_str = "[" + ", ".join(repr(v) for v in val) + "]"
    else:
        val_str = repr(val)
    return f"<li><code>{html.escape(f['field'])}</code> <em>{html.escape(f['op'])}</em> <code>{html.escape(val_str)}</code> &mdash; {html.escape(f.get('explanation',''))}</li>"


def render_boost_row(b: dict) -> str:
    val = b.get("value")
    val_str = repr(val) if not isinstance(val, list) else ("[" + ", ".join(repr(v) for v in val) + "]")
    return (f"<li><code>{html.escape(b['field'])}</code> <em>{html.escape(b['op'])}</em> "
            f"<code>{html.escape(val_str)}</code> &mdash; "
            f"<b>+{b.get('boost', 0):.2f}</b> &middot; "
            f"{html.escape(b.get('explanation',''))}</li>")


def render_detail(idx: int, q: dict, prev_qid: str | None, next_qid: str | None) -> str:
    qnum = f"Q{idx:02d}"
    qid = f"q{idx:02d}"
    cq = q["compiled"]
    rejected = cq.get("rejected", False)

    chips_html = " ".join(_chip(c, "chip-explain") for c in cq.get("explanation_chips", []))

    # Hard filters / soft boosts / unavailable predicates
    if cq.get("filters"):
        filters_block = "<ul class='predlist'>" + "".join(render_filter_row(f) for f in cq["filters"]) + "</ul>"
    else:
        filters_block = "<p class='muted'>(no hard filters)</p>"

    if cq.get("soft_boosts"):
        boosts_block = "<ul class='predlist'>" + "".join(render_boost_row(b) for b in cq["soft_boosts"]) + "</ul>"
    else:
        boosts_block = "<p class='muted'>(no soft boosts)</p>"

    if cq.get("unavailable_predicates"):
        unav_chips = " ".join(_chip("unavailable: " + u, "chip-unav") for u in cq["unavailable_predicates"])
        unav_block = f"<div class='chips'>{unav_chips}</div>"
    else:
        unav_block = "<p class='muted'>(none)</p>"

    # Body content depends on rejection
    if rejected:
        result_block = dedent(f"""
            <section class='reject-box'>
              <h2>Query rejected</h2>
              <p class='reject-reason'>{html.escape(cq.get('rejection_reason') or '')}</p>
              <p class='muted'>The compiler intentionally refuses team and player filters
                 (no <code>player_id</code> / <code>team_filter</code> in the predicate index)
                 and refuses queries with no specific tactical predicate. This is the
                 expected behaviour, not a bug.</p>
              {unav_block}
            </section>
        """)
    else:
        n_total = q["n_candidates_total"]
        n_disp = q["n_candidates_displayable"]
        disp_cards = q.get("top_5_displayable") or []
        cov_cards = q.get("top_5_coverage") or []

        if disp_cards:
            disp_html = "<div class='card-grid'>" + "".join(
                render_card(i + 1, c, with_video=True) for i, c in enumerate(disp_cards)
            ) + "</div>"
        else:
            disp_html = ("<p class='muted'>no candidates with broadcast MP4 "
                         "(coverage may still have hits below)</p>")

        if cov_cards:
            cov_html = "<div class='card-grid'>" + "".join(
                render_card(i + 1, c, with_video=False) for i, c in enumerate(cov_cards)
            ) + "</div>"
        else:
            cov_html = "<p class='muted'>no candidates passed all hard filters</p>"

        result_block = dedent(f"""
            <section class='counts'>
              <div class='count-tile'>
                <div class='count-num'>{n_total}</div>
                <div class='count-lbl'>candidate windows<br/><span class='muted'>(any window passing hard filters)</span></div>
              </div>
              <div class='count-tile'>
                <div class='count-num'>{n_disp}</div>
                <div class='count-lbl'>displayable<br/><span class='muted'>(broadcast MP4, high confidence)</span></div>
              </div>
              <div class='count-tile'>
                <div class='count-num'>{len(cq['filters'])} <span class='muted'>/</span> {len(cq['soft_boosts'])}</div>
                <div class='count-lbl'>hard / soft predicates</div>
              </div>
            </section>

            <section class='block'>
              <h2>Top-5 displayable (broadcast MP4)</h2>
              {disp_html}
            </section>

            <section class='block'>
              <h2>Top-5 coverage (any window)</h2>
              <p class='muted'>Coverage includes windows without broadcast video and (where allowed)
                 medium-confidence windows (e.g. match 1953632, no event-derived predicates).</p>
              {cov_html}
            </section>
        """)

    nav_prev = f"<a class='nav-link' href='{prev_qid}.html'>&larr; {prev_qid}</a>" if prev_qid else "<span></span>"
    nav_next = f"<a class='nav-link' href='{next_qid}.html'>{next_qid} &rarr;</a>" if next_qid else "<span></span>"

    body = dedent(f"""
        <header class='page-head'>
          <div class='breadcrumb'>
            <a href='index.html'>/audit/query-predicate/</a> &middot; {qnum}
          </div>
          <h1><span class='qid-large'>{qnum}.</span> {html.escape(q['query'])}</h1>
          <div class='chips chip-row-large'>{chips_html}</div>
          {banner_html()}
        </header>

        <div class='two-col'>
          <section class='block col-left'>
            <h2>Parsed query</h2>
            <h3>Hard filters</h3>
            {filters_block}
            <h3>Soft boosts</h3>
            {boosts_block}
            <h3>Unavailable predicates</h3>
            {unav_block}
          </section>
          <div class='col-right'>
            {result_block}
          </div>
        </div>

        <nav class='nav-row'>
          {nav_prev}
          <a class='nav-link nav-home' href='index.html'>all queries</a>
          {nav_next}
        </nav>
    """)
    return page_head(f"{qnum} \u2014 {q['query']}") + body + page_foot()


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------
STYLES = r"""
* { box-sizing: border-box; }
body {
  font: 14px/1.55 -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  margin: 0; padding: 18px 24px; background: #f5f6f8; color: #222;
  max-width: 1500px; margin: 0 auto;
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
.lead { color: #555; margin: 0 0 14px 0; max-width: 800px; }
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
  display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}
.qcard {
  display: block; background: #fff; border: 1px solid #ddd; border-radius: 6px;
  padding: 12px 14px; color: inherit; transition: box-shadow 0.1s, border-color 0.1s;
}
.qcard:hover { text-decoration: none; border-color: #1a4d8a;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
.qcard-rejected { background: #fff8e1; border-color: #d4a017; }
.qcard-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.qid { font: 11px ui-monospace, Menlo, monospace; background: #1a4d8a; color: #fff;
  padding: 2px 7px; border-radius: 3px; font-weight: 700; }
.qtext { font-size: 14px; font-weight: 500; margin-bottom: 8px; min-height: 2.6em; }
.qchips { margin-bottom: 8px; min-height: 22px; }
.qstats { font-size: 12px; color: #555; }
.qstats b { color: #222; }

/* Detail two-column */
.two-col { display: grid; grid-template-columns: 320px 1fr; gap: 18px; }
.col-left { background: #fff; border: 1px solid #ddd; border-radius: 6px;
  padding: 12px 14px; align-self: start; }
.col-left h2 { margin: 0 0 6px 0; font-size: 14px; }
.col-left h3 { margin: 12px 0 4px 0; font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.5px; color: #888; }
.col-right { display: flex; flex-direction: column; gap: 14px; }
@media (max-width: 800px) {
  .two-col { grid-template-columns: 1fr; }
}

.predlist { margin: 0; padding-left: 18px; font-size: 12.5px; line-height: 1.55; }
.predlist li { margin-bottom: 3px; }
.predlist em { color: #1a7c1a; font-style: normal; font-family: ui-monospace, Menlo, monospace;
  font-size: 11px; }

/* Counts strip */
.counts { display: flex; gap: 10px; }
.count-tile {
  background: #fff; border: 1px solid #ddd; border-radius: 6px;
  padding: 12px 14px; flex: 1;
}
.count-num { font-size: 24px; font-weight: 700; color: #1a4d8a; line-height: 1; }
.count-lbl { font-size: 12px; color: #555; margin-top: 4px; }

/* Result block */
.block { background: #fff; border: 1px solid #ddd; border-radius: 6px;
  padding: 12px 14px; }
.block h2 { margin: 0 0 8px 0; font-size: 14px; }

/* Cards (results) */
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.card { background: #fafbfd; border: 1px solid #e3e7ee; border-radius: 5px; padding: 8px; }
.card-head { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
.rank { background: #1a4d8a; color: #fff; padding: 1px 7px; border-radius: 3px;
  font-weight: 700; font-size: 10px; }
.wid { font: 10px ui-monospace, Menlo, monospace; color: #666; flex: 1;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conf { font-size: 9px; padding: 1px 6px; border-radius: 3px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.3px; }
.conf-high { background: #1a7c1a; color: #fff; }
.conf-medium { background: #d4a017; color: #fff; }
.conf-low { background: #b03030; color: #fff; }
.conf-rejected { background: #b8860b; color: #fff; }
.vid { width: 100%; max-height: 130px; background: #000; border-radius: 3px;
  margin-bottom: 5px; }
.no-mp4 { height: 60px; background: #f0f1f4; display: flex; align-items: center;
  justify-content: center; color: #999; font-size: 11px; font-style: italic;
  border-radius: 3px; margin-bottom: 5px; }
.chips { display: flex; flex-wrap: wrap; gap: 3px; }
.chip { background: #eef2fa; color: #1a4d8a; padding: 1px 6px; border-radius: 3px;
  font-size: 10.5px; }
.chip-pos { background: #dcf3dc; color: #1a7c1a; }
.chip-press { background: #ffe5dc; color: #b8551a; }
.chip-danger { background: #fde0e0; color: #b03030; }
.chip-loss { background: #fff3cd; color: #5a4108; }
.chip-phase { background: #e8e0fc; color: #4a2a8a; }
.chip-explain { background: #eef; color: #1a4d8a; padding: 2px 8px; font-size: 11px; }
.chip-unav { background: #f8e0e0; color: #b03030; }
.chip-row-large { margin-top: 2px; }
.score { font: 10px ui-monospace, Menlo, monospace; color: #999; margin-top: 4px; }
.boosts { font-size: 10px; color: #666; margin-top: 2px; }

/* Reject panel */
.reject-box { background: #fff8e1; border: 1px solid #d4a017; border-radius: 6px;
  padding: 14px 16px; }
.reject-box h2 { margin: 0 0 8px 0; color: #7a5500; }
.reject-reason { font-size: 14px; color: #5a4108; margin: 0 0 10px 0; }

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
"""


def main() -> None:
    results = json.loads(RESULTS.read_text())
    HERE.mkdir(parents=True, exist_ok=True)

    # styles.css
    (HERE / "styles.css").write_text(STYLES.lstrip())

    # README.md
    (HERE / "README.md").write_text(README)

    # index.html
    (HERE / "index.html").write_text(render_landing(results))

    # qNN.html
    n = len(results)
    for i, q in enumerate(results, start=1):
        prev_qid = f"q{i-1:02d}" if i > 1 else None
        next_qid = f"q{i+1:02d}" if i < n else None
        (HERE / f"q{i:02d}.html").write_text(render_detail(i, q, prev_qid, next_qid))

    print(f"wrote {n} detail pages + index.html + styles.css + README.md")


if __name__ == "__main__":
    main()
