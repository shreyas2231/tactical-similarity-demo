// Investor demo — typable-query wiring.
// Hits the live FastAPI backend behind a cloudflared quick tunnel.
// If the tunnel URL rotates, update BACKEND_URL below and re-deploy.

const BACKEND_URL = "https://handles-attempted-cio-summer.trycloudflare.com";

function setQ(t) {
  document.getElementById("qinput").value = t;
  runQuery(new Event("submit"));
  return false;
}

// V2 football-correct vocabulary — surface with a distinct class so they stand
// out visually from v1 lane/zone chips. Backend (_predicate_chips) emits these
// strings; matching here decides chip style.
const V2_CHIP_PREFIXES = [
  "block: ", "through ball", "line-breaking pass", "between lines",
  "diagonal switch", "past last line", "reception: ", "counter-press: ",
  "carry (v2)", "box-entry: ", "tracking-only",
];

function chipClassFor(text) {
  for (const p of V2_CHIP_PREFIXES) {
    if (text.startsWith(p) || text === p.trim()) return "chip-explain chip-v2";
  }
  return "chip-explain";
}

function chip(text, cls) {
  const safe = String(text).replace(/[<>&"']/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;",'"':"&quot;","'":"&#39;"}[c]));
  const finalCls = cls ? cls : chipClassFor(String(text));
  return `<span class="chip ${finalCls}">${safe}</span>`;
}

function mediaTile(r) {
  const url = r.media_url;
  if (!url) return `<div class="no-mp4">no media</div>`;
  // Relative paths (animations) are served from the backend; absolute (broadcast Vercel blob) are absolute already.
  const full = url.startsWith("http") ? url : (BACKEND_URL + url);
  const kind = r.media_kind || "";
  const tagLabel = kind === "broadcast" ? "🟢 BROADCAST" : "🟣 PITCH ANIMATION";
  const tagCls = kind === "broadcast" ? "tag-broadcast" : "tag-anim";
  const videoCls = kind === "broadcast" ? "vid" : "vid vid-anim";
  return `<video src="${full}" controls preload="none" muted class="${videoCls}"></video>
          <div class="media-tag ${tagCls}">${tagLabel}</div>`;
}

function renderPredicateCard(r, rank) {
  const chips = (r.predicate_chips || []).map(c => chip(c, "chip-explain")).join(" ");
  return `<div class="card">
    <div class="card-head"><span class="rank">#${rank}</span>
      <span class="wid" title="${r.window_id}">${r.window_id}</span>
      <span class="conf conf-${r.confidence||"medium"}">${r.confidence||"medium"}</span></div>
    ${mediaTile(r)}
    <div class="chips">${chips}</div>
    <div class="score">score ${r.score.toFixed(3)}</div>
  </div>`;
}

function renderRudyCard(r, rank) {
  const chips = (r.rudy_chips || []).map(c => chip(c, "chip-explain")).join(" ");
  const tier = r.confidence_tier || "unknown";
  return `<div class="card">
    <div class="card-head"><span class="rank">#${rank}</span>
      <span class="wid" title="${r.window_id}">${r.window_id}</span>
      <span class="conf conf-tier-${tier}">${tier}</span></div>
    ${mediaTile(r)}
    <div class="chips">${chips}</div>
    <div class="score">final ${r.score.toFixed(3)} · v9c ${r.v9c_score.toFixed(2)} · v11p ${r.v11p_score.toFixed(2)}</div>
  </div>`;
}

function renderPanel(title, panel, renderCard, kind) {
  if (panel.rejected) {
    return `<div class="dyn-panel"><h3>${title}</h3>
      <div class="reject-box"><b>REJECTED</b> — ${panel.rejection_reason||"unknown"}</div></div>`;
  }
  const items = panel.top_k || [];
  if (!items.length) {
    return `<div class="dyn-panel"><h3>${title}</h3><p class="muted">no candidates</p></div>`;
  }
  const cards = items.map((r, i) => renderCard(r, i+1)).join("");
  const meta = (panel.intent_chips || []).map(c => chip(c, "chip-explain")).join(" ");
  const stats = panel.n_candidates_total != null
    ? `<span class="muted">${panel.n_candidates_total} candidates total</span>`
    : "";
  const anchorLine = (panel.anchors||[]).length
    ? `<div class="muted small">anchors: ${(panel.anchors||[]).map(a => `<code>${a.window_id.split(':').slice(-1)[0]}</code> (${a.v1_category||a.primary_mechanism||""})`).join(" · ")}</div>`
    : "";
  return `<div class="dyn-panel"><h3>${title}</h3>
    <div class="dyn-meta">${meta} ${stats}</div>
    ${anchorLine}
    <div class="card-grid">${cards}</div>
  </div>`;
}

async function runQuery(e) {
  e.preventDefault();
  const q = document.getElementById("qinput").value.trim();
  if (!q) return false;
  const status = document.getElementById("qstatus");
  const out = document.getElementById("qresult");
  const btn = document.getElementById("qbtn");
  btn.disabled = true;
  status.textContent = `Searching for: ${q} ...`;
  out.innerHTML = "";
  try {
    const t0 = performance.now();
    const resp = await fetch(BACKEND_URL + "/api/query", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({query: q, top_k: 5})
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const dt = Math.round(performance.now() - t0);
    const intentChips = Object.entries(data.intent)
      .filter(([k,v]) => v && v !== "any" && !["raw_query","unsupported","confidence"].includes(k))
      .map(([k,v]) => chip(`${k}: ${Array.isArray(v)?v.join("/"):v}`, "chip-explain")).join(" ");
    status.innerHTML = `<b>${q}</b> &mdash; ${dt} ms &middot; intent: ${intentChips || "<span class='muted'>no signal</span>"}`;
    out.innerHTML = `<div class="two-col">
        ${renderPanel("Predicate Search", data.predicate, renderPredicateCard, "predicate")}
        ${renderPanel("Rudy Tactical Similarity", data.rudy, renderRudyCard, "rudy")}
      </div>`;
  } catch (err) {
    status.innerHTML = `<span class="rej">error: ${String(err).replace(/</g,"&lt;")}</span>`;
  } finally {
    btn.disabled = false;
  }
  return false;
}
