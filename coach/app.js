// Match Prep — investor-facing coach brief app.
// Drill-down UX: pick team → see 4-6 recommendations → expand any → see
// the stat that justifies it → click a proof clip → modal video playback.

const BACKEND_URL = "https://handles-attempted-cio-summer.trycloudflare.com";

const $ = (id) => document.getElementById(id);
const teamGrid = $("teamGrid");
const briefSec = $("brief");
const briefTitle = $("briefTitle");
const briefSub = $("briefSub");
const briefMeta = $("briefMeta");
const recList = $("recList");
const emptyState = $("emptyState");

// modal state
const modal = $("clipModal");
const modalVid = $("modalVideo");
const modalCap = $("modalCaption");
const modalChips = $("modalChips");
const modalPos = $("modalPos");
let modalClips = [];     // current set of clips
let modalIdx = 0;
let modalContext = "";   // recommendation title for caption

// ---------- helpers ----------
function esc(s) {
  return String(s || "").replace(/[<>&"']/g, c =>
    ({"<":"&lt;",">":"&gt;","&":"&amp;",'"':"&quot;","'":"&#39;"}[c]));
}

function deltaChip(teamPct, leaguePct) {
  if (leaguePct == null || leaguePct <= 0 || teamPct == null) return "";
  const ratio = teamPct / leaguePct;
  const sign = ratio >= 1 ? "+" : "";
  const pct = Math.round((ratio - 1) * 100);
  const cls = ratio >= 1.15 ? "delta-up" : (ratio <= 0.85 ? "delta-down" : "delta-flat");
  return `<span class="delta ${cls}">${sign}${pct}% vs league</span>`;
}

function statBar(label, teamPct, leaguePct) {
  const w = Math.max(2, Math.round((teamPct || 0) * 100));
  const baseline = (leaguePct != null && leaguePct > 0)
    ? `<span class="stat-baseline" style="left:${Math.round(leaguePct*100)}%" title="league avg ${(leaguePct*100).toFixed(0)}%"></span>` : "";
  return `<div class="stat-row">
    <div class="stat-track">
      <span class="stat-fill" style="width:${w}%"></span>${baseline}
    </div>
    <div class="stat-numbers">
      <span>${(teamPct*100).toFixed(0)}%</span>
      ${deltaChip(teamPct, leaguePct)}
    </div>
  </div>
  <div class="stat-name">${esc(label)}</div>`;
}

function mediaUrl(clip) {
  if (!clip.media_url) return null;
  return clip.media_url.startsWith("http") ? clip.media_url : (BACKEND_URL + clip.media_url);
}

function clipTagHtml(clip) {
  if (clip.media_kind === "broadcast") {
    return `<span class="proof-clip-tag is-broadcast">broadcast</span>`;
  }
  const rec = clip.pattern_recurrence;
  if (rec && rec.is_recurring) {
    return `<span class="proof-clip-tag is-recurring">repeats ×${rec.occurrences}</span>`;
  }
  return `<span class="proof-clip-tag">animation</span>`;
}

function proofClipCard(clip, index) {
  const url = mediaUrl(clip);
  if (!url) {
    return `<div class="proof-clip" data-idx="${index}">
      <div class="proof-clip-play" style="background:#1a1a1c;color:#888;font-size:12px;display:grid;place-items:center">no media</div>
    </div>`;
  }
  return `<div class="proof-clip" data-idx="${index}">
    <video src="${esc(url)}#t=0.5" preload="metadata" muted></video>
    <div class="proof-clip-play"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div>
    ${clipTagHtml(clip)}
  </div>`;
}

// ---------- render team picker ----------
async function loadTeams() {
  try {
    const r = await fetch(BACKEND_URL + "/api/teams");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    teamGrid.innerHTML = data.teams
      .sort((a, b) => b.n_attacking_windows - a.n_attacking_windows)
      .map(t => `
        <button class="team-card" data-team="${t.team_id}">
          <span class="team-id">Team ${t.team_id}</span>
          <span class="team-windows">${t.n_attacking_windows.toLocaleString()} possessions analysed</span>
        </button>
      `).join("");
    teamGrid.querySelectorAll(".team-card").forEach(btn => {
      btn.addEventListener("click", () => {
        teamGrid.querySelectorAll(".team-card").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        loadBrief(btn.dataset.team);
      });
    });
  } catch (err) {
    teamGrid.innerHTML = `<div class="team-loading" style="color:#b03030">Couldn't load teams: ${esc(err)}</div>`;
  }
}

// ---------- render brief ----------
async function loadBrief(teamId) {
  emptyState.hidden = true;
  briefSec.hidden = false;
  recList.innerHTML = `<div class="proof-empty">Generating brief…</div>`;
  briefTitle.textContent = "—";
  briefSub.textContent = "—";
  briefMeta.textContent = "";

  try {
    const r = await fetch(BACKEND_URL + "/api/coach_brief/" + encodeURIComponent(teamId));
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const brief = await r.json();
    renderBrief(brief);
    // scroll the brief into view
    briefSec.scrollIntoView({behavior: "smooth", block: "start"});
  } catch (err) {
    recList.innerHTML = `<div class="proof-empty" style="color:#b03030">Couldn't generate brief: ${esc(err)}</div>`;
  }
}

function renderBrief(brief) {
  briefTitle.textContent = brief.hero.title;
  briefSub.textContent = brief.hero.subtitle;
  briefMeta.textContent = `${brief.recommendations.length} key decisions`;

  recList.innerHTML = brief.recommendations.map((rec, i) => `
    <article class="rec tone-${esc(rec.tone)}" data-rec-id="${esc(rec.id)}" data-idx="${i}">
      <button class="rec-trigger" aria-expanded="false">
        <div class="rec-icon">${rec.icon || "•"}</div>
        <div class="rec-title-block">
          <div class="rec-title">${esc(rec.title)}</div>
          <div class="rec-sub">${esc(rec.subtitle)}</div>
        </div>
        <span class="rec-chev">▾</span>
      </button>
      <div class="rec-body">
        <div class="rec-body-inner">
          ${renderEvidence(rec)}
          ${renderProof(rec, i)}
        </div>
      </div>
    </article>
  `).join("");

  // Wire expand
  recList.querySelectorAll(".rec").forEach(el => {
    const trigger = el.querySelector(".rec-trigger");
    trigger.addEventListener("click", () => {
      const open = el.classList.toggle("open");
      trigger.setAttribute("aria-expanded", String(open));
    });
  });

  // Wire proof-clip clicks → modal
  recList.querySelectorAll(".rec").forEach((el, ri) => {
    const rec = brief.recommendations[ri];
    el.querySelectorAll(".proof-clip").forEach(card => {
      card.addEventListener("click", (e) => {
        e.stopPropagation();
        const idx = parseInt(card.dataset.idx, 10);
        openModal(rec.proof_clips || [], idx, rec.title);
      });
    });
  });
}

function renderEvidence(rec) {
  if (!rec.evidence || !rec.evidence.length) return "";
  return rec.evidence.map(e => `
    <div class="evidence">
      <div class="evidence-label">The evidence</div>
      <div class="evidence-headline-row">
        <div class="interpretation">${esc(e.interpretation || "")}</div>
        <div>
          ${statBar(e.label, e.team_pct, e.league_pct)}
        </div>
      </div>
    </div>
  `).join("");
}

function renderProof(rec, recIdx) {
  const clips = rec.proof_clips || [];
  const head = `<div class="proof-header">
    <span class="proof-title">${esc(rec.proof_explainer || "Proof clips")}</span>
    <span class="proof-count">${clips.length} clip${clips.length === 1 ? "" : "s"} — click to play</span>
  </div>`;
  if (!clips.length) {
    return head + `<div class="proof-empty">No direct proof clips for this recommendation in the current corpus.</div>`;
  }
  const grid = clips.map((c, i) => proofClipCard(c, i)).join("");
  return head + `<div class="proof-grid">${grid}</div>`;
}

// ---------- modal ----------
function openModal(clips, idx, contextTitle) {
  if (!clips.length) return;
  modalClips = clips;
  modalIdx = idx;
  modalContext = contextTitle || "";
  showModalClip();
  modal.hidden = false;
  document.body.style.overflow = "hidden";
}

function showModalClip() {
  const c = modalClips[modalIdx];
  if (!c) return;
  const url = mediaUrl(c);
  modalVid.src = url || "";
  modalVid.load();
  modalVid.play().catch(() => {});
  modalCap.textContent = modalContext
    ? `${modalContext} — ${c.window_id.split(":").slice(-2).join(":")}`
    : c.window_id;
  // chips
  modalChips.innerHTML = (c.predicate_chips || []).slice(0, 6)
    .map(chip => `<span class="modal-chip">${esc(chip)}</span>`).join("");
  modalPos.textContent = `${modalIdx + 1} / ${modalClips.length}`;
  $("prevClip").disabled = modalIdx === 0;
  $("nextClip").disabled = modalIdx === modalClips.length - 1;
}

function closeModal() {
  modal.hidden = true;
  modalVid.pause();
  modalVid.removeAttribute("src");
  modalVid.load();
  document.body.style.overflow = "";
}

modal.addEventListener("click", (e) => {
  if (e.target && e.target.dataset && e.target.dataset.close === "1") closeModal();
});
document.addEventListener("keydown", (e) => {
  if (modal.hidden) return;
  if (e.key === "Escape") closeModal();
  else if (e.key === "ArrowLeft" && modalIdx > 0) { modalIdx--; showModalClip(); }
  else if (e.key === "ArrowRight" && modalIdx < modalClips.length - 1) { modalIdx++; showModalClip(); }
});
$("prevClip").addEventListener("click", () => { if (modalIdx > 0) { modalIdx--; showModalClip(); } });
$("nextClip").addEventListener("click", () => { if (modalIdx < modalClips.length - 1) { modalIdx++; showModalClip(); } });

// ---------- boot ----------
loadTeams();
