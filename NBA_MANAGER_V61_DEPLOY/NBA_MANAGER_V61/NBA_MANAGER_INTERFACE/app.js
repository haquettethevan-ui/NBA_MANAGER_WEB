const TOTAL_GAME_MINUTES = 240;
let players = [];
let teams = [];
let selectedUserTeamId = null;
let selectedOpponentTeamId = null;
let matchLocked = false;
let previewTimer = null;
let previewValid = false;
let previewError = "";
let previewGeneration = 0;
let exactRotationDiagnostics = null;

const $ = id => document.getElementById(id);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

async function api(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.message || "Erreur serveur.");
    return data;
}

function getTotalMinutes() {
    return players.reduce((total, p) => total + Number(p.minutes || 0), 0);
}

function getStarterPositionCoverage() {
    const starters = players.filter(p => p.starter);
    if (starters.length !== 5) return false;
    const required = ["PG", "SG", "SF", "PF", "C"];
    const eligible = starters.map(p => p.position.split("/"));
    function search(slot, used) {
        if (slot === required.length) return true;
        for (let i = 0; i < eligible.length; i++) {
            if (used.has(i) || !eligible[i].includes(required[slot])) continue;
            used.add(i);
            if (search(slot + 1, used)) return true;
            used.delete(i);
        }
        return false;
    }
    return search(0, new Set());
}

function renderTeamSelectors() {
    const user = $("userTeamSelect");
    const opponent = $("opponentTeamSelect");
    user.innerHTML = "";
    opponent.innerHTML = "";

    teams.forEach(team => {
        const extra = team.excluded ? `, ${team.excluded} ignoré${team.excluded > 1 ? "s" : ""}` : "";
        const label = team.playable ? `${team.name} (${team.player_count} joueurs${extra})` : `${team.name} — indisponible (${team.player_count} joueurs complets)`;
        const a = new Option(label, team.id);
        const b = new Option(label, team.id);
        a.disabled = !team.playable;
        b.disabled = !team.playable;
        user.add(a); opponent.add(b);
    });

    const firstPlayable = teams.find(t => t.playable);
    const secondPlayable = teams.find(t => t.playable && t.id !== firstPlayable?.id);
    if (firstPlayable) user.value = firstPlayable.id;
    if (secondPlayable) opponent.value = secondPlayable.id;
    selectedUserTeamId = user.value || null;
    selectedOpponentTeamId = opponent.value || null;
}

function updateHeader() {
    const user = teams.find(t => t.id === selectedUserTeamId);
    const opp = teams.find(t => t.id === selectedOpponentTeamId);
    const userName = user?.name || "—";
    const oppName = opp?.name || "—";
    $("teamTitle").textContent = userName;
    $("homeHeader").textContent = userName;
    $("awayHeader").textContent = oppName;
    $("footerTeam").textContent = userName;
    $("footerOpponent").textContent = `Adversaire : ${oppName}`;
    $("rosterTitle").textContent = `Effectif — ${userName}`;
}

function showAvailability(message, error = false) {
    const box = $("teamAvailability");
    box.textContent = message;
    box.classList.remove("hidden", "error", "success");
    box.classList.add(error ? "error" : "success");
}

function renderRotationList() {
    const target = $("rotationList");
    target.innerHTML = "";

    players.forEach(player => {
        const row = document.createElement("div");
        row.className = `rotation-player-row ${Number(player.minutes) === 0 ? "inactive-player" : ""}`;

        const starter = document.createElement("input");
        starter.type = "checkbox";
        starter.className = "starter-checkbox";
        starter.checked = player.starter;
        starter.title = "Titulaire";
        starter.addEventListener("change", () => {
            const current = players.filter(p => p.starter).length;
            if (!starter.checked) {
                player.starter = false;
            } else if (current < 5) {
                player.starter = true;
                if (Number(player.minutes) === 0) player.minutes = 32;
            } else {
                starter.checked = false;
                return;
            }
            exactRotationDiagnostics = null;
            renderRotationList();
            updateTotal();
            schedulePregamePreview();
        });

        const info = document.createElement("div");
        info.innerHTML = `<div class="player-name">${esc(player.name)}</div><div class="player-meta">Ext ${player.outside} · Int ${player.inside} · Ath ${player.athleticism} · Créa ${player.playmaking} · Déf ${player.defense} · Reb ${player.rebounding} · Sta ${player.stamina}</div>`;

        const position = document.createElement("div");
        position.className = "position-pill";
        position.textContent = player.position;

        const profile = document.createElement("div");
        profile.className = "profile-pill";
        profile.textContent = `OVR ${player.overall}`;

        const naturalRole = document.createElement("div");
        naturalRole.className = "role-display";
        naturalRole.textContent = player.role;
        naturalRole.title = "Rôle naturel calculé automatiquement à partir des ratings.";

        const minutes = document.createElement("input");
        minutes.type = "number";
        minutes.min = "0";
        minutes.max = "48";
        minutes.className = "minute-input";
        minutes.value = player.minutes;
        minutes.addEventListener("input", () => {
            let value = Number(minutes.value);
            if (!Number.isFinite(value)) value = 0;
            player.minutes = Math.max(0, Math.min(48, Math.round(value)));
            exactRotationDiagnostics = null;
            minutes.value = player.minutes;
            row.classList.toggle("inactive-player", player.minutes === 0);
            updateTotal();
            schedulePregamePreview();
        });

        row.append(starter, info, position, profile, naturalRole, minutes);
        target.appendChild(row);
    });
}

function getEligiblePositions(player) {
    return String(player.position || "").split("/").map(x => x.trim());
}

function getPositionMinuteCapacity(position) {
    return players.reduce((sum, p) => {
        return sum + (getEligiblePositions(p).includes(position) ? Number(p.minutes || 0) : 0);
    }, 0);
}

function getRotationDiagnostics() {
    const total = getTotalMinutes();
    const starterCount = players.filter(p => p.starter).length;
    const required = ["PG", "SG", "SF", "PF", "C"];
    const positionCapacity = Object.fromEntries(required.map(pos => [pos, getPositionMinuteCapacity(pos)]));
    const deficits = required
        .filter(pos => positionCapacity[pos] < 48)
        .map(pos => ({ position: pos, missing: 48 - positionCapacity[pos] }));
    return { total, starterCount, positionCapacity, deficits };
}

function updateTotal() {
    setTimeout(renderTacticCompatibility, 0);
    const diagnostics = getRotationDiagnostics();
    const { total, starterCount, positionCapacity, deficits } = diagnostics;
    const activeCount = players.filter(p => Number(p.minutes) > 0).length;
    const badge = $("minuteTotal");
    const warning = $("rotationWarning");
    const button = $("launchButton");
    const coverage = $("positionCoverage");

    badge.textContent = `${total} / ${TOTAL_GAME_MINUTES} min`;
    badge.classList.remove("valid", "invalid");
    warning.classList.remove("hidden", "error", "success");
    coverage.innerHTML = ["PG", "SG", "SF", "PF", "C"].map(pos => {
        const exact = exactRotationDiagnostics?.coverage?.[pos];
        const value = exact != null ? exact : Math.min(48, positionCapacity[pos]);
        const ok = exact != null ? value === 48 : value >= 48;
        const suffix = exact != null ? "réelles" : "capacité";
        return `<div class="position-coverage-item ${ok ? "ok" : "bad"}"><div class="position-coverage-label"><strong>${pos}</strong><span>${value}/48 min</span></div><div class="position-coverage-bar"><span style="width:${Math.min(100, value / 48 * 100)}%"></span></div><small>${suffix}</small></div>`;
    }).join("");

    if (!selectedUserTeamId || !selectedOpponentTeamId) {
        button.disabled = true;
        return;
    }

    const messages = [];
    if (starterCount !== 5) messages.push(`⚠️ Il faut exactement 5 titulaires (${starterCount}/5).`);
    if (activeCount < 8) messages.push(`⚠️ Rotation trop courte : ${activeCount} joueurs actifs. Utilise normalement 8 à 12 joueurs.`);
    if (activeCount > 12) messages.push(`⚠️ Rotation trop large : ${activeCount} joueurs actifs. Maximum recommandé : 12.`);
    if (starterCount === 5 && !getStarterPositionCoverage()) messages.push("⚠️ Le cinq majeur doit couvrir PG, SG, SF, PF et C.");
    if (total < TOTAL_GAME_MINUTES) messages.push(`⏱️ Il manque ${TOTAL_GAME_MINUTES - total} minutes.`);
    if (total > TOTAL_GAME_MINUTES) messages.push(`⏱️ Il y a ${total - TOTAL_GAME_MINUTES} minutes en trop.`);

    if (deficits.length) {
        const details = deficits.map(d => `${d.position}: ${d.missing} min manquantes (capacité ${positionCapacity[d.position]}/48)`).join(" · ");
        messages.push(`❌ Rotation impossible : ${details}`);
    }

    if (messages.length) {
        previewValid = false;
        previewError = messages.join(" ");
        badge.classList.add("invalid");
        warning.innerHTML = messages.map(m => `<div>${m}</div>`).join("");
        warning.classList.add("error");
        button.disabled = true;
        return;
    }

    badge.classList.add("valid");
    if (!previewValid) {
        warning.innerHTML = previewError
            ? `<div>❌ ${previewError}</div>`
            : `<div>⏳ Vérification de la rotation en cours…</div>`;
        warning.classList.add(previewError ? "error" : "success");
        button.disabled = true;
        return;
    }

    warning.innerHTML = `✅ ${players.length} joueurs dans l'effectif · ${players.filter(p => Number(p.minutes) > 0).length} dans la rotation · 5 titulaires · 240 minutes valides · projection réalisable.`;
    warning.classList.add("success");
    button.disabled = matchLocked;
}

async function applyAutomaticMinutes() {
    if (!selectedUserTeamId || players.length < 5) return;

    const button = $("autoMinutesButton");
    const warning = $("rotationWarning");
    button.disabled = true;
    button.textContent = "⏳ Génération...";
    previewValid = false;
    previewError = "";
    warning.className = "warning success";
    warning.classList.remove("hidden");
    warning.innerHTML = "⏳ Le moteur cherche une rotation réellement réalisable sur les 48 minutes...";

    try {
        const data = await api("/api/auto-rotation", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ team_id: selectedUserTeamId })
        });
        players = data.players;
        exactRotationDiagnostics = data.rotation_diagnostics || null;
        renderRotationList();
        renderRoster();
        previewValid = true;
        previewError = "";
        exactRotationDiagnostics = data.rotation_diagnostics || null;
        renderPregameTimeline(data.timeline);
        updateTotal();
    } catch (error) {
        previewValid = false;
        previewError = error.message;
        updateTotal();
        $("pregameTimeline").innerHTML = `<div class="timeline-empty error">❌ ${error.message}</div>`;
    } finally {
        button.disabled = false;
        button.textContent = "↺ Répartition auto";
    }
}

function schedulePregamePreview() {
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(() => {
        refreshPregameTimeline();
    }, 300);
}

function shortName(name) {
    const parts = String(name).split(" ");
    if (parts.length === 1) return esc(parts[0]);
    return esc(parts.length > 2 ? `${parts[0][0]}. ${parts[parts.length - 1]}` : `${parts[0][0]}. ${parts[1]}`);
}

function samePlannedLineup(a, b) {
    if (!a || !b) return false;
    const get = x => x.players.map(p => `${p.position}:${p.name}`).join("|");
    return get(a) === get(b);
}

function renderPregameTimeline(timeline) {
    const target = $("pregameTimeline");
    if (!timeline || !timeline.length) {
        target.innerHTML = `<div class="timeline-empty">Configure les minutes pour afficher la projection.</div>`;
        return;
    }

    const positions = ["PG", "SG", "SF", "PF", "C"];
    let segments = [];
    let start = 0;
    for (let i = 1; i <= timeline.length; i++) {
        if (i === timeline.length || !samePlannedLineup(timeline[i - 1], timeline[i])) {
            segments.push({ start: timeline[start].minute, end: timeline[i - 1].minute, slot: timeline[start] });
            start = i;
        }
    }

    let html = `<div class="pregame-rotation-summary"><strong>${segments.length} compositions prévues</strong><span>${segments.length > 1 ? `${segments.length - 1} changements de cinq` : "aucun changement"}</span></div>`;
    html += `<div class="pregame-segments">`;
    segments.forEach((segment, index) => {
        const playersHtml = positions.map(pos => {
            const player = segment.slot.players.find(p => p.position === pos);
            return `<span class="pregame-segment-player"><b>${pos}</b>${player ? shortName(player.name) : "—"}</span>`;
        }).join("");
        const q1 = Math.floor((segment.start - 1) / 12) + 1;
        const q2 = Math.floor((segment.end - 1) / 12) + 1;
        const label = segment.start === segment.end ? `Min ${segment.start}` : `Min ${segment.start}–${segment.end}`;
        html += `<div class="pregame-segment"><div class="pregame-segment-time"><strong>${label}</strong><span>${q1 === q2 ? `Q${q1}` : `Q${q1} → Q${q2}`}${index > 0 ? " · CHANGEMENT" : " · DÉPART"}</span></div><div class="pregame-segment-lineup">${playersHtml}</div></div>`;
    });
    html += `</div>`;

    // Vue joueur x minute : deux joueurs ayant des blocs alignés sont réellement ensemble sur le terrain.
    const playerMap = new Map();
    timeline.forEach(slot => slot.players.forEach(p => {
        if (!playerMap.has(p.name)) playerMap.set(p.name, { name:p.name, minutes:0 });
        playerMap.get(p.name).minutes += 1;
    }));
    const activePlayers = [...playerMap.values()].sort((a,b) => b.minutes - a.minutes);
    html += `<div class="pregame-grid-wrap"><div class="pregame-player-grid" style="--rotation-rows:${activePlayers.length}">`;
    html += `<div class="pregame-corner">JOUEUR</div>`;
    timeline.forEach(slot => {
        const cls = slot.minute_in_quarter === 1 ? " minute-start-quarter" : "";
        html += `<div class="pregame-minute-header${cls}" title="Q${slot.quarter}, minute ${slot.minute_in_quarter}">${slot.minute}</div>`;
    });
    activePlayers.forEach(item => {
        html += `<div class="pregame-player-label"><strong>${shortName(item.name)}</strong><span>${item.minutes} min</span></div>`;
        timeline.forEach(slot => {
            const on = slot.players.find(p => p.name === item.name);
            const qstart = slot.minute_in_quarter === 1 ? " quarter-start" : "";
            html += `<div class="pregame-player-cell${on ? " on-court" : ""}${qstart}" title="${on ? `${esc(item.name)} · ${on.position} · minute ${slot.minute}` : `Banc · minute ${slot.minute}`}">${on ? on.position : ""}</div>`;
        });
    });
    html += `</div></div>`;
    html += `<div class="pregame-quarter-labels"><span>Q1 · 1–12</span><span>Q2 · 13–24</span><span>Q3 · 25–36</span><span>Q4 · 37–48</span></div>`;
    target.innerHTML = html;
}

async function refreshPregameTimeline() {
    const generation = ++previewGeneration;
    previewValid = false;
    previewError = "";
    updateTotal();

    if (!selectedUserTeamId || players.length === 0) return false;
    if (players.filter(p => p.starter).length !== 5 || getTotalMinutes() !== TOTAL_GAME_MINUTES || !getStarterPositionCoverage()) {
        $("pregameTimeline").innerHTML = `<div class="timeline-empty">La timeline apparaîtra quand les 5 titulaires, les postes et les 240 minutes seront valides.</div>`;
        return false;
    }

    $("pregameTimeline").innerHTML = `<div class="timeline-empty">⏳ Validation réelle de la rotation minute par minute…</div>`;
    try {
        const data = await api("/api/rotation-preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                team_id: selectedUserTeamId,
                rotation: players.map(p => ({
                    name: p.name,
                    minutes: Number(p.minutes || 0),
                    starter: Boolean(p.starter)
                }))
            })
        });
        if (generation !== previewGeneration) return false;
        previewValid = true;
        previewError = "";
        exactRotationDiagnostics = data.rotation_diagnostics || null;
        renderPregameTimeline(data.timeline);
        updateTotal();
        return true;
    } catch (error) {
        if (generation !== previewGeneration) return false;
        previewValid = false;
        previewError = error.message;
        $("pregameTimeline").innerHTML = `<div class="timeline-empty error">❌ Rotation refusée par le moteur : ${error.message}</div>`;
        updateTotal();
        return false;
    }
}

function renderRoster() {
    const body = $("rosterTable");
    body.innerHTML = players.map(p => `<tr><td><strong>${esc(p.name)}</strong></td><td>${esc(p.position)}</td><td><strong>${p.overall}</strong></td><td>${p.outside}</td><td>${p.inside}</td><td>${p.athleticism}</td><td>${p.playmaking}</td><td>${p.defense}</td><td>${p.rebounding}</td><td>${p.stamina}</td><td>${esc(p.role)}</td></tr>`).join("");
}

function readTactics() {
    const ids = ["offensePrimary","offenseSecondary","offenseTertiary","defensePrimary","defenseSecondary","defenseTertiary"];
    const tactics = Object.fromEntries(ids.map(id => [id, $(id).value]));
    const offense = [tactics.offensePrimary,tactics.offenseSecondary,tactics.offenseTertiary];
    const defense = [tactics.defensePrimary,tactics.defenseSecondary,tactics.defenseTertiary];
    if (new Set(offense).size !== 3 || new Set(defense).size !== 3) {
        throw new Error("Choisis trois priorités différentes en attaque et trois priorités différentes en défense.");
    }
    return tactics;
}

function tacticCompatibilityScore(focus) {
    const active = players.filter(p => Number(p.minutes || 0) > 0);
    if (!active.length) return 50;
    const total = active.reduce((n,p) => n + Number(p.minutes || 0), 0) || active.length;
    const avg = key => active.reduce((n,p) => n + Number(p[key] || 0) * Number(p.minutes || 0), 0) / total;
    const outside=avg("outside"), inside=avg("inside"), play=avg("playmaking"), ath=avg("athleticism"), reb=avg("rebounding"), overall=avg("overall");
    const skill = ({
      "Équilibré": overall, "Jeu intérieur": .70*inside+.18*ath+.12*reb,
      "Tir extérieur": .82*outside+.18*play, "Pénétration": .58*inside+.27*ath+.15*play,
      "Pick & Roll": .52*play+.24*inside+.24*outside, "Jeu rapide": .62*ath+.23*play+.15*overall,
      "Mouvement de balle": .72*play+.18*outside+.10*overall, "Rebond offensif": .72*reb+.28*ath
    })[focus] ?? overall;
    return Math.round(100 * Math.max(0, Math.min(1, (skill - 62) / 26)));
}
function renderTacticCompatibility() {
    if (!$('compatibilityScore')) return;
    let t; try { t=readTactics(); } catch(e) { $('compatibilityScore').textContent='—'; $('compatibilityLabel').textContent='Priorités en doublon'; $('compatibilityDetails').innerHTML=''; return; }
    const fs=[t.offensePrimary,t.offenseSecondary,t.offenseTertiary], ws=[1,.58,.30];
    const scores=fs.map(tacticCompatibilityScore); const overall=Math.round(scores.reduce((n,x,i)=>n+x*ws[i],0)/ws.reduce((a,b)=>a+b,0));
    const label=overall>=80?'Excellente':overall>=67?'Bonne':overall>=52?'Moyenne':'Faible';
    $('compatibilityScore').textContent=`${overall}/100`; $('compatibilityLabel').textContent=label;
    $('compatibilityDetails').innerHTML=fs.map((f,i)=>`<div><span>P${i+1} · ${esc(f)}</span><strong>${scores[i]}</strong><i><b style="width:${scores[i]}%"></b></i></div>`).join('');
}

function playerStatsTable(team) {
    return `<div class="result-team-section"><h3>${esc(team.name)}</h3><div class="team-stats-grid"><div><span>PTS</span><strong>${team.stats.points}</strong></div><div><span>REB</span><strong>${team.stats.rebounds}</strong></div><div><span>AST</span><strong>${team.stats.assists}</strong></div><div><span>TOV</span><strong>${team.stats.turnovers}</strong></div><div><span>Fautes</span><strong>${team.stats.fouls}</strong></div><div><span>LF</span><strong>${team.stats.free_throws_made}/${team.stats.free_throws_attempted}</strong></div><div><span>FG%</span><strong>${team.stats.fg_pct}%</strong></div><div><span>3P%</span><strong>${team.stats.three_pct}%</strong></div><div><span>POSS</span><strong>${team.stats.possessions}</strong></div><div><span>PEINTURE</span><strong>${team.stats.points_in_paint}</strong></div></div><div class="result-table-wrap"><table class="result-table"><thead><tr><th>Joueur</th><th>Min</th><th>Pts</th><th>Reb</th><th>Ast</th><th>TOV</th><th>Fautes</th><th>LF</th><th>FG</th><th>3PT</th></tr></thead><tbody>${team.players.map(p => `<tr><td><strong>${esc(p.name)}</strong><small>${esc(p.position)} · OVR ${p.overall}</small></td><td>${p.minutes}</td><td>${p.points}</td><td>${p.rebounds}</td><td>${p.assists}</td><td>${p.turnovers}</td><td>${p.fouls}</td><td>${p.free_throws_made}/${p.free_throws_attempted}</td><td>${p.shots_made}/${p.shots_attempted}</td><td>${p.three_made}/${p.three_attempted}</td></tr>`).join("")}</tbody></table></div></div>`;
}

function periodLabels(count) {
    return Array.from({ length: count }, (_, i) => i < 4 ? `Q${i + 1}` : (count - 4 > 1 ? `OT${i - 3}` : "OT"));
}

function quarterTable(game) {
    const labels = periodLabels(game.team1.quarter_scores.length);
    const row = t => `<tr><td><strong>${esc(t.name)}</strong></td>${t.quarter_scores.map(v => `<td>${v}</td>`).join("")}<td><strong>${t.score}</strong></td></tr>`;
    return `<div class="result-table-wrap quarter-table"><table class="result-table"><thead><tr><th>Score par période</th>${labels.map(l => `<th>${l}</th>`).join("")}<th>Total</th></tr></thead><tbody>${row(game.team1)}${row(game.team2)}</tbody></table></div>`;
}

function renderTimeline(timeline, team1Name, team2Name) {
    const target = $("timelineContent");
    if (!timeline || !timeline.length) {
        target.innerHTML = `<div class="timeline-empty">Aucune donnée de rotation disponible.</div>`;
        return;
    }
    let html = `<div class="timeline-header"><div><strong>${esc(team1Name)}</strong><span>équipe gérée</span></div><div><strong>${esc(team2Name)}</strong><span>adversaire</span></div></div>`;
    let lastQuarter = 0;
    const totalOvertimes = Math.max(0, ...timeline.map(slot => slot.overtime || 0));
    timeline.forEach(slot => {
        if (slot.quarter !== lastQuarter) {
            const title = slot.overtime ? (totalOvertimes > 1 ? `PROLONGATION ${slot.overtime}` : "PROLONGATION") : `QUARTER ${slot.quarter}`;
            html += `<div class="quarter-divider">${title}</div>`;
            lastQuarter = slot.quarter;
        }
        const home = slot.team1.map(p => `<span class="timeline-player"><b>${esc(p.position)}</b>${esc(p.name)}${p.energy != null ? `<small>⚡ ${p.energy}%</small>` : ""}</span>`).join("");
        const away = slot.team2.map(p => `<span class="timeline-player"><b>${esc(p.position)}</b>${esc(p.name)}${p.energy != null ? `<small>⚡ ${p.energy}%</small>` : ""}</span>`).join("");
        html += `<div class="timeline-row"><div class="timeline-minute"><strong>${slot.minute_in_quarter}</strong><small>${slot.clock_start}–${slot.clock_end}</small></div><div class="timeline-lineup">${home}</div><div class="timeline-lineup">${away}</div></div>`;
    });
    target.innerHTML = html;
}

async function loadRoster(teamId) {
    const data = await api(`/api/roster?team_id=${encodeURIComponent(teamId)}`);
    players = data.players;
    exactRotationDiagnostics = null;
    renderRotationList();
    renderRoster();
    updateTotal();
    schedulePregamePreview();
    renderTacticCompatibility();
}

async function onUserTeamChange() {
    selectedUserTeamId = $("userTeamSelect").value;
    if (selectedUserTeamId === selectedOpponentTeamId) {
        const alternative = teams.find(t => t.playable && t.id !== selectedUserTeamId);
        if (alternative) { selectedOpponentTeamId = alternative.id; $("opponentTeamSelect").value = alternative.id; }
    }
    updateHeader();
    const meta = teams.find(t => t.id === selectedUserTeamId);
    if (!meta?.playable) { players = []; renderRotationList(); renderRoster(); $("pregameTimeline").innerHTML = `<div class="timeline-empty">Cet effectif n'est pas encore complet dans la base locale.</div>`; showAvailability("Cet effectif n'est pas encore complet dans la base locale.", true); updateTotal(); return; }
    try { await loadRoster(selectedUserTeamId); showAvailability("✅ Effectif chargé. Tu peux préparer ton match."); }
    catch (e) { showAvailability(e.message, true); }
}

function onOpponentChange() {
    selectedOpponentTeamId = $("opponentTeamSelect").value;
    if (selectedOpponentTeamId === selectedUserTeamId) {
        const alternative = teams.find(t => t.playable && t.id !== selectedUserTeamId);
        if (alternative) { selectedOpponentTeamId = alternative.id; $("opponentTeamSelect").value = alternative.id; }
    }
    updateHeader(); updateTotal();
}

function lockControls() {
    document.querySelectorAll("input, select, .tab").forEach(el => el.disabled = true);
    document.querySelectorAll(".tab").forEach(el => el.style.pointerEvents = "none");
}
function unlockControls() {
    document.querySelectorAll("input, select").forEach(el => el.disabled = false);
    document.querySelectorAll(".tab").forEach(el => { el.disabled = false; el.style.pointerEvents = "auto"; });
}

document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => {
    if (matchLocked) return;
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.remove("active"));
    tab.classList.add("active"); $(tab.dataset.tab).classList.add("active");
}));

$("autoMinutesButton").addEventListener("click", applyAutomaticMinutes);
$("refreshPreviewButton").addEventListener("click", refreshPregameTimeline);
$("userTeamSelect").addEventListener("change", onUserTeamChange);
$("opponentTeamSelect").addEventListener("change", onOpponentChange);
document.querySelectorAll("#tactiques select").forEach(el => el.addEventListener("change", renderTacticCompatibility));

document.querySelectorAll(".result-tab").forEach(tab => tab.addEventListener("click", () => {
    document.querySelectorAll(".result-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".result-panel").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    $(tab.dataset.resultTab).classList.add("active");
}));

$("launchButton").addEventListener("click", async () => {
    if (getTotalMinutes() !== TOTAL_GAME_MINUTES || players.filter(p => p.starter).length !== 5 || !getStarterPositionCoverage()) return;
    const ok = await refreshPregameTimeline();
    if (!ok) {
        alert("Impossible de lancer le match : la rotation affichée n'est pas réalisable par le moteur. Le détail est affiché sous la timeline.");
        return;
    }
    matchLocked = true;
    $("launchButton").disabled = true;
    $("launchButton").textContent = "SIMULATION...";
    lockControls();
    try {
        const data = await api("/rotation", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ team1_id: selectedUserTeamId, team2_id: selectedOpponentTeamId, rotation1: players, tactics1: readTactics() })
        });
        const game = data.result;
        $("homeTeamName").textContent = game.team1.name.toUpperCase();
        $("homeScore").textContent = game.team1.score;
        $("awayTeamName").textContent = game.team2.name.toUpperCase();
        $("awayScore").textContent = game.team2.score;
        $("resultsContent").innerHTML = quarterTable(game) + playerStatsTable(game.team1) + playerStatsTable(game.team2);
        document.querySelector(".locked-banner").textContent = game.overtime ? `🔒 MATCH TERMINÉ après prolongation (${game.periods - 4} OT) — Résultats` : "🔒 MATCH TERMINÉ — Résultats";
        renderTimeline(game.rotation_timeline, game.team1.name, game.team2.name);
        document.querySelectorAll(".result-tab").forEach(t => t.classList.remove("active"));
        document.querySelectorAll(".result-panel").forEach(p => p.classList.remove("active"));
        document.querySelector('.result-tab[data-result-tab="summaryResult"]').classList.add("active");
        $("summaryResult").classList.add("active");
        $("matchOverlay").classList.remove("hidden");
    } catch (error) {
        console.error(error); alert("Erreur pendant la simulation : " + error.message); matchLocked = false; unlockControls();
    } finally {
        $("launchButton").textContent = "▶ LANCER LE MATCH";
        updateTotal();
    }
});

$("closeMatch").addEventListener("click", () => {
    $("matchOverlay").classList.add("hidden"); matchLocked = false; unlockControls(); updateTotal();
});

(async function init() {
    try {
        const data = await api("/api/teams");
        teams = data.teams;
        renderTeamSelectors();
        updateHeader();
        await loadRoster(selectedUserTeamId);
        const unavailable = teams.filter(t => !t.playable).length;
        const ignored = teams.filter(t => t.playable).reduce((n, t) => n + (t.excluded || 0), 0);
        showAvailability(unavailable ? `✅ ${teams.filter(t => t.playable).length}/30 équipes jouables (effectif local complet). ${unavailable} à importer via INITIALISER_BASE.bat.${ignored ? ` ${ignored} joueur(s) ignoré(s) faute de notes 2K.` : ""}` : "✅ Les 30 effectifs sont disponibles.");
    } catch (e) {
        showAvailability(e.message, true);
    }
})();
