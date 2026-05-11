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

// ---- Team-focus rendering (Fire 2: answers "how does team X press / build / progress / leave space") ----
// Q labels (CTO list ↔ proof_clips routes)
const TEAM_Q_LABELS = {
  lateral_preference:    "Which side do they attack more often?",
  press_style:           "How do they press?",
  build_up_fragility:    "Where is their build-up fragile?",
  midfield_progression:  "How do they progress through midfield?",
  box_entry_method:      "How do they enter the box?",
  space_between_lines:   "Where do they leave space between lines?",
  press_break_received:  "When does their press get broken?",
};

function pctBar(pct, label) {
  const w = Math.max(2, Math.round(pct * 100));
  return `<div class="bar-row"><span class="bar-lbl">${label}</span>
    <span class="bar-track"><span class="bar-fill" style="width:${w}%"></span></span>
    <span class="bar-pct">${(pct*100).toFixed(0)}%</span></div>`;
}

function distBlock(title, distObj) {
  if (!distObj || !distObj.pct) return "";
  const entries = Object.entries(distObj.pct).sort((a,b) => b[1]-a[1]).filter(([k,v]) => v > 0);
  if (!entries.length) return "";
  const bars = entries.map(([k,v]) => pctBar(v, String(k))).join("");
  return `<div class="dist-block"><h4>${title} <span class="muted">(n=${distObj.n})</span></h4>${bars}</div>`;
}

function teamProofRow(qid, clips) {
  if (!clips || !clips.length) {
    return `<div class="team-q-row team-q-empty">
      <h4>${TEAM_Q_LABELS[qid] || qid} <span class="qid-tag">${qid}</span></h4>
      <p class="muted">no clips matched — pattern not present in this corpus</p></div>`;
  }
  const cards = clips.slice(0,5).map((r, i) => {
    const chipsHtml = (r.predicate_chips || []).slice(0,5).map(c => chip(c)).join(" ");
    const media = mediaTile(r);
    return `<div class="card">
      <div class="card-head"><span class="rank">#${i+1}</span>
        <span class="wid" title="${r.window_id}">${r.window_id}</span></div>
      ${media}
      <div class="chips">${chipsHtml}</div>
    </div>`;
  }).join("");
  return `<div class="team-q-row">
    <h4>${TEAM_Q_LABELS[qid] || qid} <span class="qid-tag">${qid}</span>
      <span class="muted small">— ${clips.length} matched, top-5 shown</span></h4>
    <div class="card-grid">${cards}</div>
  </div>`;
}

function renderTeamPanel(data) {
  const a = data.attacking || {};
  const d = data.defending || {};
  const dists = `<div class="team-dists">
    ${distBlock("Attacking — modal lane",       a.modal_lane_distribution)}
    ${distBlock("Attacking — midfield progression type", a.progression_type_in_middle_third)}
    ${distBlock("Attacking — box entry method",  a.box_entry_method_distribution)}
    ${distBlock("Defending — block type",        d.block_type_distribution)}
    ${distBlock("Defending — counter-press outcomes", d.counter_press_distribution)}
  </div>`;
  const proofRows = Object.keys(TEAM_Q_LABELS)
    .map(qid => teamProofRow(qid, (data.proof_clips || {})[qid]))
    .join("");
  return `<div class="team-panel">
    <div class="team-header">
      <h2>Team focus: <code>${data.team_id}</code></h2>
      <div class="muted">attacking windows: <b>${data.n_attacking_windows}</b> &middot;
        defending windows: <b>${data.n_defending_windows}</b> &middot;
        matches attacking: ${data.matches_attacking.length} &middot; matches defending: ${data.matches_defending.length}</div>
    </div>
    ${dists}
    <div class="team-proofs"><h3>Proof clips per analyst question</h3>${proofRows}</div>
  </div>`;
}

// Extract a team_id from a free-form query — match either bare 4-digit numbers
// or "team <id>" patterns. Returns first match or null.
function extractTeamId(q) {
  const m = q.match(/\bteam[\s_-]+(\d{3,4})\b/i) || q.match(/\b(\d{4})\b/);
  return m ? m[1] : null;
}

async function runTeamQuery(teamId, status, out) {
  status.textContent = `Loading team focus for ${teamId} ...`;
  try {
    const t0 = performance.now();
    const resp = await fetch(BACKEND_URL + "/api/team/" + encodeURIComponent(teamId));
    if (!resp.ok) {
      if (resp.status === 404) {
        // Fetch the list of valid teams so we can show them
        const listResp = await fetch(BACKEND_URL + "/api/teams");
        const list = listResp.ok ? await listResp.json() : null;
        const validIds = list ? list.teams.map(t => t.team_id).join(", ") : "(unavailable)";
        status.innerHTML = `<span class="rej">team_id ${teamId} not found.</span> Valid team_ids: <code>${validIds}</code>`;
        return;
      }
      throw new Error(`HTTP ${resp.status}`);
    }
    const data = await resp.json();
    const dt = Math.round(performance.now() - t0);
    status.innerHTML = `<b>Team focus: ${teamId}</b> &mdash; ${dt} ms &middot;
      <span class="muted">7 analyst questions answered + 5 proof clips each</span>`;
    out.innerHTML = renderTeamPanel(data);
  } catch (err) {
    status.innerHTML = `<span class="rej">error: ${String(err).replace(/</g,"&lt;")}</span>`;
  }
}

async function runQuery(e) {
  e.preventDefault();
  const q = document.getElementById("qinput").value.trim();
  if (!q) return false;
  const status = document.getElementById("qstatus");
  const out = document.getElementById("qresult");
  const btn = document.getElementById("qbtn");
  btn.disabled = true;
  out.innerHTML = "";

  // Detect team-focus queries: if the query contains a team_id, switch modes.
  const teamId = extractTeamId(q);
  if (teamId) {
    await runTeamQuery(teamId, status, out);
    btn.disabled = false;
    return false;
  }

  status.textContent = `Searching for: ${q} ...`;
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

// Surface team-focus example links so investors discover the feature.
function setTeam(id) {
  document.getElementById("qinput").value = "team " + id;
  runQuery(new Event("submit"));
  return false;
}
