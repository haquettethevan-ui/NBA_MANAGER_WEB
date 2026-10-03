from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json
import random
import hashlib
from itertools import combinations

from main import (
    DEFAULT_TACTICS,
    Player,
    Team,
    simulate_game,
    position_assignment,
    infer_natural_role,
    build_default_rotation_minutes,
    build_feasible_rotation,
    set_rotation_plan,
    REQUIRED_POSITIONS,
    eligible_positions,
    tactic_compatibility,
    normalize_tactics,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

with open(DATA_DIR / "teams.json", encoding="utf-8") as f:
    TEAM_META = json.load(f)["teams"]

with open(DATA_DIR / "players_2k27.json", encoding="utf-8") as f:
    PLAYER_DB = json.load(f)["players"]

REQUIRED_RATINGS = [
    "overall", "outside_scoring", "inside_scoring", "athleticism",
    "playmaking", "defense", "rebounding", "stamina"
]


def complete_players(team_id):
    rows = PLAYER_DB.get(team_id, [])
    return [
        row for row in rows
        if all(row.get(key) is not None for key in REQUIRED_RATINGS)
    ]


def default_role(row):
    return infer_natural_role(
        row.get("position"),
        int(row.get("overall", 0)),
        int(row.get("outside_scoring", 0)),
        int(row.get("inside_scoring", 0)),
        int(row.get("athleticism", 0)),
        int(row.get("playmaking", 0)),
        int(row.get("defense", 0)),
        int(row.get("rebounding", 0)),
        int(row.get("stamina", 0)),
    )


def make_player(row):
    return Player(
        row["name"],
        row["position"],
        default_role(row),
        int(row["overall"]),
        int(row["outside_scoring"]),
        int(row["inside_scoring"]),
        int(row["athleticism"]),
        int(row["playmaking"]),
        int(row["defense"]),
        int(row["rebounding"]),
        int(row["stamina"]),
    )


def choose_starting_five(players):
    ordered = sorted(players, key=lambda p: p.overall, reverse=True)

    def backtrack(index, chosen):
        if len(chosen) == 5:
            if position_assignment(chosen) is not None:
                return chosen[:]
            return None
        if index >= len(ordered):
            return None
        # Try the highest-rated players first, but backtrack if positions don't fit.
        for i in range(index, len(ordered)):
            candidate = ordered[i]
            chosen.append(candidate)
            result = backtrack(i + 1, chosen)
            if result is not None:
                return result
            chosen.pop()
        return None

    result = backtrack(0, [])
    if result is None:
        raise ValueError("Impossible de construire un cinq couvrant PG, SG, SF, PF et C.")
    return result


def build_team(team_id, player_names=None):
    meta = next((team for team in TEAM_META if team["id"] == team_id), None)
    if meta is None:
        raise ValueError(f"Équipe inconnue : {team_id}")

    if player_names is None:
        rows = complete_players(team_id)
    else:
        wanted=set(player_names)
        rows=[row for rows0 in PLAYER_DB.values() for row in rows0 if row.get("name") in wanted and all(row.get(key) is not None for key in REQUIRED_RATINGS)]
    if len(rows) < 5:
        raise ValueError(
            f"L'effectif de {meta['name']} n'est pas encore disponible dans la base locale "
            f"({len(rows)} joueurs complets, 5 minimum)."
        )

    # IMPORTANT : on conserve tout l'effectif complet. Il n'y a plus de limite à 10 joueurs.
    rows = sorted(rows, key=lambda row: int(row["overall"]), reverse=True)
    players = [make_player(row) for row in rows]
    starters = choose_starting_five(players)
    starter_names = {p.name for p in starters}
    bench = [p for p in players if p.name not in starter_names]
    return Team(meta["name"], starters, bench), players


def team_catalog():
    result = []
    for team in TEAM_META:
        rows = complete_players(team["id"])
        excluded = len(PLAYER_DB.get(team["id"], [])) - len(rows)
        result.append({
            "id": team["id"],
            "name": team["name"],
            "slug": team["slug"],
            "player_count": len(rows),
            "excluded": excluded,
            "playable": len(rows) >= 5,
        })
    return result


def clone_rotation_plan_for(team, starter_players, bench_players, starter_minutes=30):
    """Construit puis valide un plan minutes à partir d'un cinq + banc choisis."""
    minutes = {p.name: 0 for p in team.roster}
    for p in starter_players:
        minutes[p.name] = starter_minutes
    bench_minutes_total = 240 - starter_minutes * len(starter_players)
    if bench_minutes_total < 0 or not bench_players:
        return None
    base = bench_minutes_total // len(bench_players)
    remainder = bench_minutes_total % len(bench_players)
    for i, p in enumerate(bench_players):
        minutes[p.name] = base + (1 if i < remainder else 0)
    return minutes



def _schedule_based_auto_rotation(team, max_active=10):
    """Construit une rotation à partir de 48 cinq réellement valides.

    Contrairement à l'ancien générateur, le banc n'a pas besoin de couvrir à
    lui seul PG/SG/SF/PF/C. Les titulaires et remplaçants se partagent les
    postes, comme dans une vraie rotation NBA.
    """
    players = sorted(list(team.roster), key=lambda p: p.overall, reverse=True)
    if len(players) < 5:
        raise ValueError("Il faut au moins 5 joueurs disponibles.")

    starters = choose_starting_five(players)
    starter_names = {p.name for p in starters}
    bench = [p for p in players if p.name not in starter_names]
    active = starters + bench[:max(0, max_active - 5)]

    # Toutes les compositions de 5 qui couvrent réellement les cinq postes.
    valid_lineups = []
    for combo in combinations(active, 5):
        if position_assignment(list(combo)) is not None:
            valid_lineups.append(list(combo))
    if not valid_lineups:
        raise ValueError("Aucun cinq valide ne peut couvrir PG, SG, SF, PF et C.")

    # Cibles réalistes. Elles guident la sélection mais ne sont pas imposées :
    # un joueur occupant un poste rare peut jouer davantage si nécessaire.
    starter_targets = [35, 34, 32, 30, 29]
    bench_targets = [22, 19, 16, 14, 9]
    target = {p.name: 0 for p in players}
    for p, m in zip(sorted(starters, key=lambda x: x.overall, reverse=True), starter_targets):
        target[p.name] = m
    for p, m in zip(sorted(active[5:], key=lambda x: x.overall, reverse=True), bench_targets):
        target[p.name] = m

    # Si moins de 10 joueurs sont disponibles, répartit les minutes restantes
    # sur les joueurs actifs en privilégiant les meilleurs.
    missing = 240 - sum(target.values())
    ranked_active = sorted(active, key=lambda p: p.overall, reverse=True)
    i = 0
    while missing > 0:
        p = ranked_active[i % len(ranked_active)]
        if target[p.name] < 48:
            target[p.name] += 1
            missing -= 1
        i += 1

    used = {p.name: 0 for p in players}
    schedule = []
    # Le premier cinq est bien le cinq titulaire choisi.
    schedule.append(list(starters))
    for p in starters:
        used[p.name] += 1

    for minute in range(1, 48):
        best = None
        best_key = None
        for lineup in valid_lineups:
            # Besoin restant : favorise les joueurs sous leur cible.
            need = sum(target[p.name] - used[p.name] for p in lineup)
            # Évite les stints absurdes sans rendre la contrainte rigide.
            continuity = len({p.name for p in schedule[-1]} & {p.name for p in lineup})
            quality = sum(p.overall for p in lineup)
            key = (need, continuity * 0.35, quality * 0.01)
            if best_key is None or key > best_key:
                best_key = key
                best = lineup
        schedule.append(best)
        for p in best:
            used[p.name] += 1

    minutes = {p.name: used[p.name] for p in players}
    team.starters = starters
    team.bench = [p for p in players if p.name not in starter_names]
    team.rotation_plan = minutes

    # Validation finale par le moteur exact. Puisque les minutes proviennent
    # elles-mêmes de 48 cinq valides, elles doivent être réalisables.
    build_feasible_rotation(team)
    return starters, minutes


def build_auto_rotation_minutes(team):
    return _schedule_based_auto_rotation(team, max_active=min(10, len(team.roster)))


AI_STARTER_MINUTES = [35, 33, 31, 30, 29]
AI_BENCH_MINUTES = [22, 19, 16, 14, 11]


def build_ai_rotation(team):
    _, minutes = _schedule_based_auto_rotation(team, max_active=min(10, len(team.roster)))
    return minutes


def _ai_league_baselines():
    """League distributions for roster-relative AI identities.

    Raw 2K category scales are not directly comparable (outside scoring is
    structurally higher than some other categories), so tactical identity uses
    league-relative z-scores instead of raw rating gaps.
    """
    attrs=("outside_scoring","inside_scoring","playmaking","defense","rebounding","athleticism")
    profiles=[]
    for rows in PLAYER_DB.values():
        valid=[r for r in rows if all(r.get(a) is not None for a in attrs)]
        core=sorted(valid,key=lambda r:int(r.get("overall") or 0),reverse=True)[:8]
        if not core: continue
        profiles.append({a:sum(float(r[a]) for r in core)/len(core) for a in attrs})
    out={}
    for a in attrs:
        vals=[p[a] for p in profiles]
        mean=sum(vals)/len(vals)
        var=sum((x-mean)**2 for x in vals)/max(1,len(vals)-1)
        out[a]=(mean,max(var**.5,1.0))
    return out

_AI_BASELINES=_ai_league_baselines()

def ai_tactics(team, opponent=None):
    """Choose a varied NBA-style plan from league-relative roster strengths.

    Player ratings and shot calibration are untouched. Only the CPU's tactical
    selection is normalized, so a high raw outside-scoring scale no longer
    forces almost every team into 'Tir extérieur'.
    """
    core=sorted(team.roster,key=lambda p:getattr(p,"overall",0),reverse=True)[:8]
    opp_core=sorted(opponent.roster,key=lambda p:getattr(p,"overall",0),reverse=True)[:8] if opponent else []
    def avg(players,attr,default=70.0):
        return sum(float(getattr(p,attr,default) or default) for p in players)/max(1,len(players))
    def z(players,attr):
        mean,sd=_AI_BASELINES[attr]
        return (avg(players,attr)-mean)/sd
    outside=z(core,"outside_scoring"); inside=z(core,"inside_scoring")
    play=z(core,"playmaking"); defense=z(core,"defense")
    rebound=z(core,"rebounding"); athletic=z(core,"athleticism")
    # Identity dominates. Scores are deliberately on the same normalized scale.
    off_scores={
        "Tir extérieur":1.00*outside+.12*play,
        "Jeu intérieur":.88*inside+.22*rebound,
        "Pénétration":.58*inside+.55*athletic+.12*play,
        "Pick & Roll":.72*play+.22*outside+.16*inside,
        "Jeu rapide":.66*athletic+.38*play,
        "Mouvement de balle":.88*play+.12*outside,
        "Rebond offensif":.82*rebound+.20*inside,
        "Équilibré":.20-0.12*max(abs(outside),abs(inside),abs(play),abs(athletic))}
    def_scores={
        "Homme à homme":.72*defense+.28*athletic,
        "Pression porteur":.58*defense+.50*athletic,
        "Protection du cercle":.70*defense+.42*rebound,
        "Défense extérieure":.82*defense+.20*athletic,
        "Box out":1.00*rebound+.10*defense,
        "Repli défensif":.68*athletic+.30*defense,
        "Zone":.58*defense+.38*rebound-.18,
        "Équilibré":.18}
    if opp_core:
        # Matchup adjustment is intentionally modest (~20-25% of a typical
        # identity score) so the CPU adapts without becoming a perfect counter.
        oo=z(opp_core,"outside_scoring"); oi=z(opp_core,"inside_scoring")
        op=z(opp_core,"playmaking"); od=z(opp_core,"defense"); ore=z(opp_core,"rebounding")
        off_scores["Tir extérieur"] += max(-.32,min(.32,-od*.20))
        off_scores["Pénétration"] += max(-.32,min(.32,-(.72*od+.28*ore)*.20))
        off_scores["Jeu intérieur"] += max(-.30,min(.30,-(.68*od+.32*ore)*.18))
        off_scores["Rebond offensif"] += max(-.28,min(.28,-ore*.18))
        # Apply matchup information to every offensive family. Previously P&R,
        # transition and ball movement were effectively roster-only choices.
        off_scores["Pick & Roll"] += max(-.32,min(.32,-(.58*od+.42*op)*.20))
        off_scores["Jeu rapide"] += max(-.30,min(.30,-(.55*od+.45*ore)*.18))
        off_scores["Mouvement de balle"] += max(-.30,min(.30,-(.72*od+.28*op)*.18))
        off_scores["Équilibré"] += max(-.16,min(.16,-od*.10))

        def_scores["Défense extérieure"] += max(-.34,min(.34,oo*.22))
        def_scores["Protection du cercle"] += max(-.34,min(.34,oi*.22))
        def_scores["Pression porteur"] += max(-.32,min(.32,op*.20))
        def_scores["Box out"] += max(-.28,min(.28,ore*.17))
        # Defensive choices also react to the opponent's likely creation style.
        def_scores["Homme à homme"] += max(-.24,min(.24,(.45*op+.30*oi+.25*oo)*.12))
        def_scores["Repli défensif"] += max(-.28,min(.28,z(opp_core,"athleticism")*.18))
        def_scores["Zone"] += max(-.24,min(.24,(oi-oo)*.14))
        def_scores["Équilibré"] += max(-.12,min(.12,(abs(oo)+abs(oi)+abs(op))*.035))
    def top3(scores):
        return [k for k,_ in sorted(scores.items(),key=lambda kv:(kv[1],kv[0]),reverse=True)[:3]]
    off=top3(off_scores); deff=top3(def_scores)
    return normalize_tactics({
        "offensePrimary":off[0],"offenseSecondary":off[1],"offenseTertiary":off[2],
        "defensePrimary":deff[0],"defenseSecondary":deff[1],"defenseTertiary":deff[2]})



def _replace_ai_primary(plan, side, focus, pool):
    out=dict(plan)
    keys=[side+"Primary",side+"Secondary",side+"Tertiary"]
    out[keys[0]]=focus
    used=[]
    for key in keys:
        if out[key] in used:
            out[key]=next(x for x in pool if x not in used)
        used.append(out[key])
    return normalize_tactics(out)


def ai_tactics_engine_guided(team, opponent, trials=4):
    """CPU plan: roster/matchup heuristic, then a cheap engine tie-break.

    The heuristic keeps the team's basketball identity. The engine only tests
    the three most plausible primaries, with common random seeds, so CPU teams
    adapt to the actual engine without exhaustive/perfect search.
    """
    base=ai_tactics(team,opponent)
    if opponent is None:
        return base
    offense_pool=["Équilibré","Jeu intérieur","Tir extérieur","Pénétration","Pick & Roll","Jeu rapide","Mouvement de balle","Rebond offensif"]
    defense_pool=["Équilibré","Homme à homme","Pression porteur","Protection du cercle","Défense extérieure","Box out","Repli défensif","Zone"]
    opponent_plan=ai_tactics(opponent,team)
    # Keep the shortlist tied to team identity. The previous forced P&R /
    # balanced challengers increased benchmark regret by admitting candidates
    # that did not actually fit some rosters.
    off_candidates=[base["offensePrimary"],base["offenseSecondary"],base["offenseTertiary"]]
    def_candidates=[base["defensePrimary"],base["defenseSecondary"],base["defenseTertiary"]]
    seed_key=(team.name+"|"+opponent.name).encode("utf-8")
    seed0=int.from_bytes(hashlib.sha256(seed_key).digest()[:4],"big")
    saved=random.getstate()

    def score(plan):
        margins=[]
        for i in range(max(1,trials)):
            random.seed(seed0+i)
            # Rebuild fresh teams so benchmark games cannot leak fatigue/stats.
            tid=next(x["id"] for x in TEAM_META if x["name"]==team.name)
            oid=next(x["id"] for x in TEAM_META if x["name"]==opponent.name)
            a,_=build_team(tid); b,_=build_team(oid)
            result=simulate_game(a,b,build_ai_rotation(a),build_ai_rotation(b),
                                 tactics1=plan,tactics2=opponent_plan)
            margins.append(result["team1"]["stats"]["points"]-result["team2"]["stats"]["points"])
        return sum(margins)/len(margins)

    try:
        # Common random numbers make candidate comparisons much less noisy.
        # Require a small, repeatable advantage before overriding the heuristic
        # primary; close calls stay with the team's natural identity.
        off_base=score(base)
        off_rank=sorted(
            ((score(_replace_ai_primary(base,"offense",x,offense_pool)),x) for x in off_candidates),
            reverse=True)
        off_best_score,off_best=off_rank[0]
        chosen=base
        if off_best != base["offensePrimary"] and off_best_score >= off_base + 1.5:
            chosen=_replace_ai_primary(base,"offense",off_best,offense_pool)

        def_base=score(chosen)
        def_rank=sorted(
            ((score(_replace_ai_primary(chosen,"defense",x,defense_pool)),x) for x in def_candidates),
            reverse=True)
        def_best_score,def_best=def_rank[0]
        if def_best != chosen["defensePrimary"] and def_best_score >= def_base + 1.5:
            chosen=_replace_ai_primary(chosen,"defense",def_best,defense_pool)
        return chosen
    finally:
        random.setstate(saved)


def roster_timeline_from_team(team):
    """Retourne la timeline de pré-match issue du plan de rotation validé."""
    if len(getattr(team, "rotation_schedule", [])) != 48 or len(getattr(team, "rotation_position_schedule", [])) != 48:
        set_rotation_plan(team, team.rotation_plan)
    timeline = []
    for minute, assignment in enumerate(team.rotation_position_schedule):
        timeline.append({
            "minute": minute + 1,
            "quarter": minute // 12 + 1,
            "minute_in_quarter": minute % 12 + 1,
            "players": [
                {"position": pos, "name": assignment[pos].name, "role": assignment[pos].role}
                for pos in ["PG", "SG", "SF", "PF", "C"]
            ],
        })
    return timeline


def serialize_roster(team_id):
    rows = complete_players(team_id)
    rows = sorted(rows, key=lambda row: int(row["overall"]), reverse=True)
    if len(rows) < 5:
        return {"success": False, "message": f"Effectif insuffisant : {len(rows)} joueurs complets (5 minimum)."}
    players = [make_player(row) for row in rows]
    starters = choose_starting_five(players)
    starter_names = {p.name for p in starters}
    active_bench = []
    for pos in REQUIRED_POSITIONS:
        choices = [p for p in players if p.name not in starter_names and pos in p.position.split("/") and p not in active_bench]
        if choices:
            active_bench.append(max(choices, key=lambda p: p.overall))
    for p in sorted(players, key=lambda x: x.overall, reverse=True):
        if p.name not in starter_names and p not in active_bench and len(active_bench) < 5:
            active_bench.append(p)
    remaining = 90
    plan = {p.name: 0 for p in players}
    for p in starters:
        plan[p.name] = 30
    if active_bench:
        base = remaining // len(active_bench)
        for i, p in enumerate(active_bench):
            plan[p.name] = base + (1 if i < remaining % len(active_bench) else 0)
    output = []
    for row in rows:
        output.append({
            "name": row["name"], "position": row["position"], "overall": row["overall"],
            "outside": row["outside_scoring"], "inside": row["inside_scoring"],
            "athleticism": row["athleticism"], "playmaking": row["playmaking"],
            "defense": row["defense"], "rebounding": row["rebounding"], "stamina": row["stamina"],
            "role": default_role(row), "minutes": plan[row["name"]], "starter": row["name"] in starter_names,
        })
    return {"success": True, "players": output, "roster_size": len(output)}

def rotation_preview(team_id, rotation_rows, player_names=None):
    """Construit une projection minute par minute avant le match.

    Cette projection utilise exactement le même générateur de rotations que le
    moteur : les minutes saisies par le manager déterminent les lineups possibles.
    Elle sert à visualiser qui devrait jouer ensemble ; les événements du match
    peuvent toutefois provoquer des ajustements exceptionnels (fautes).
    """
    team, _ = build_team(team_id, player_names)
    by_name = {p.name: p for p in team.roster}
    rotation = {}
    starter_names = []
    for row in rotation_rows:
        name = row.get("name")
        if name not in by_name:
            raise ValueError(f"Joueur inconnu dans la rotation : {name}")
        rotation[name] = int(row.get("minutes", 0))
        if bool(row.get("starter")):
            starter_names.append(name)
    if set(rotation) != set(by_name):
        raise ValueError("La projection doit contenir tout l'effectif.")
    if len(starter_names) != 5:
        raise ValueError("Il faut exactement 5 titulaires.")
    team.starters = [by_name[n] for n in starter_names]
    team.bench = [p for p in team.roster if p.name not in set(starter_names)]
    if position_assignment(team.starters) is None:
        raise ValueError("Le cinq majeur doit couvrir PG, SG, SF, PF et C.")
    set_rotation_plan(team, rotation)
    timeline = []
    for minute, lineup in enumerate(team.rotation_schedule):
        assignment = team.rotation_position_schedule[minute]
        timeline.append({
            "minute": minute + 1,
            "quarter": minute // 12 + 1,
            "minute_in_quarter": minute % 12 + 1,
            "players": [
                {"position": pos, "name": assignment[pos].name, "role": assignment[pos].role}
                for pos in ["PG", "SG", "SF", "PF", "C"]
            ]
        })
    return timeline


def rotation_diagnostics(team):
    """Diagnostic basé sur l'affectation réelle des 240 slots, pas une capacité théorique."""
    coverage = {pos: 0 for pos in REQUIRED_POSITIONS}
    player_minutes = {p.name: 0 for p in team.roster}
    for assignment in team.rotation_position_schedule:
        for pos in REQUIRED_POSITIONS:
            coverage[pos] += 1 if assignment.get(pos) is not None else 0
            if assignment.get(pos) is not None:
                player_minutes[assignment[pos].name] += 1
    active = [name for name, mins in player_minutes.items() if mins > 0]
    return {
        "coverage": coverage,
        "active_count": len(active),
        "active_players": active,
        "player_minutes": player_minutes,
        "total_minutes": sum(player_minutes.values()),
        "valid": all(v == 48 for v in coverage.values()) and sum(player_minutes.values()) == 240,
    }


class Server(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/version":
            self.send_json(200, {"success": True, "version": "V43"})
            return
        if parsed.path == "/api/teams":
            self.send_json(200, {"success": True, "teams": team_catalog()})
            return

        if parsed.path == "/api/roster":
            team_id = parse_qs(parsed.query).get("team_id", [None])[0]
            if not team_id:
                self.send_json(400, {"success": False, "message": "team_id manquant."})
                return
            payload = serialize_roster(team_id)
            self.send_json(200 if payload["success"] else 400, payload)
            return

        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/auto-rotation":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                team_id = payload.get("team_id")
                team, _ = build_team(team_id)
                starters, rotation = build_auto_rotation_minutes(team)
                starter_names = {p.name for p in starters}
                for p in team.roster:
                    p.role = infer_natural_role(
                        p.position, p.overall, p.outside_scoring, p.inside_scoring,
                        p.athleticism, p.playmaking, p.defense, p.rebounding, p.stamina
                    )
                set_rotation_plan(team, rotation)
                rows = []
                for p in team.roster:
                    rows.append({
                        "name": p.name,
                        "position": p.position,
                        "overall": p.overall,
                        "outside": p.outside_scoring,
                        "inside": p.inside_scoring,
                        "athleticism": p.athleticism,
                        "playmaking": p.playmaking,
                        "defense": p.defense,
                        "rebounding": p.rebounding,
                        "stamina": p.stamina,
                        "role": p.role,
                        "minutes": rotation[p.name],
                        "starter": p.name in starter_names,
                    })
                self.send_json(200, {
                    "success": True,
                    "players": rows,
                    "timeline": roster_timeline_from_team(team),
                    "rotation_diagnostics": rotation_diagnostics(team),
                })
            except Exception as error:
                self.send_json(400, {"success": False, "message": str(error)})
            return

        if self.path == "/api/rotation-preview":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                team_id = payload.get("team_id")
                timeline = rotation_preview(team_id, payload.get("rotation", []))
                # Reconstruit la même rotation afin de fournir la couverture réelle par poste.
                team, _ = build_team(team_id)
                by_name = {p.name: p for p in team.roster}
                rows = payload.get("rotation", [])
                team.starters = [by_name[r["name"]] for r in rows if r.get("starter")]
                team.bench = [p for p in team.roster if p not in team.starters]
                set_rotation_plan(team, {r["name"]: int(r.get("minutes", 0)) for r in rows})
                self.send_json(200, {"success": True, "timeline": timeline, "rotation_diagnostics": rotation_diagnostics(team)})
            except Exception as error:
                self.send_json(400, {"success": False, "message": str(error)})
            return

        if self.path != "/rotation":
            self.send_json(404, {"success": False, "message": "Route inconnue."})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))

            user_team_id = payload.get("team1_id")
            opponent_team_id = payload.get("team2_id")
            if not user_team_id or not opponent_team_id:
                raise ValueError("Les deux équipes doivent être sélectionnées.")
            if user_team_id == opponent_team_id:
                raise ValueError("Les deux équipes doivent être différentes.")

            user_team, _ = build_team(user_team_id)
            opponent_team, _ = build_team(opponent_team_id)

            rotation1 = {
                player["name"]: int(player["minutes"])
                for player in payload["rotation1"]
            }
            starter_names1 = [
                player["name"]
                for player in payload["rotation1"]
                if bool(player.get("starter"))
            ]
            role_map1 = None
            tactics1 = payload.get("tactics1", {})

            opponent_players = opponent_team.roster
            rotation2 = build_ai_rotation(opponent_team)
            starter_names2 = [player.name for player in opponent_team.starters]
            role_map2 = None
            tactics2 = ai_tactics(opponent_team)

            print()
            print("========================================")
            print(f"PLAN DE MATCH - {user_team.name}")
            print("========================================")
            print(f"Adversaire : {opponent_team.name}")
            print("5 majeur :", ", ".join(starter_names1))
            print("Minutes :")
            for name, minutes in rotation1.items():
                print(f"  {name} -> {minutes} min")
            print("Tactiques :", tactics1)
            print()
            print("Simulation en cours...")

            result = simulate_game(
                user_team,
                opponent_team,
                rotation1,
                rotation2,
                starter_names1,
                starter_names2,
                role_map1,
                role_map2,
                tactics1,
                tactics2,
            )

            print(
                "Match terminé :",
                result["team1"]["score"],
                "-",
                result["team2"]["score"],
            )

            self.send_json(
                200,
                {
                    "success": True,
                    "message": "Match terminé.",
                    "result": result,
                },
            )

        except Exception as error:
            print("❌ ERREUR :", error)
            self.send_json(400, {"success": False, "message": str(error)})


def main():
    server = ThreadingHTTPServer(("localhost", 8000), Server)
    server.daemon_threads = True

    print("========================================")
    print("NBA MANAGER V39 - SERVEUR")
    print("========================================")
    print()
    playable = [t for t in team_catalog() if t["playable"]]
    print(f"{len(playable)}/30 équipes jouables (effectif local complet).")
    print("Données joueurs : 2KRatings NBA 2K27")
    print("Ouvre : http://localhost:8000/NBA_MANAGER_INTERFACE/")
    print()
    server.serve_forever()


if __name__ == "__main__":
    main()
