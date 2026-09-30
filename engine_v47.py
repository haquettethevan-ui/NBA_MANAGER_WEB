"""NBA Manager V44 match engine.

Design hierarchy: player talent/profile -> lineup/matchup -> energy -> tactics.
Tactics alter the situations created; they do not add points directly.
"""
import math
import random
from legacy_main import (
    build_feasible_rotation, set_rotation_plan, configure_team_for_match,
    reset_game_stats, position_assignment, primary_position, eligible_positions,
    perimeter_defense, interior_defense, audit_team_stats, team_result,
)

OFFENSE_FOCUSES = (
    "Équilibré", "Jeu intérieur", "Tir extérieur", "Pénétration",
    "Pick & Roll", "Jeu rapide", "Mouvement de balle", "Rebond offensif",
)
DEFENSE_FOCUSES = (
    "Équilibré", "Protection du cercle", "Défense extérieure", "Pression porteur",
    "Zone", "Homme à homme", "Box out", "Repli défensif",
)
DEFAULT_TACTICS = {
    "offensePrimary": "Équilibré", "offenseSecondary": "Mouvement de balle", "offenseTertiary": "Jeu rapide",
    "defensePrimary": "Équilibré", "defenseSecondary": "Homme à homme", "defenseTertiary": "Box out",
}
PRIORITY = (1.0, .58, .30)

# Positive = offense creates this situation more often; negative = defense suppresses it.
OFFENSE_PROFILE = {
    "Équilibré": {},
    "Jeu intérieur": {"rim": .20, "mid": .05, "three": -.14, "post": .18},
    "Tir extérieur": {"three": .22, "rim": -.09, "mid": -.08},
    "Pénétration": {"rim": .20, "three": -.06, "drive": .20},
    "Pick & Roll": {"rim": .10, "three": .07, "pnr": .22, "mid": .02},
    "Jeu rapide": {"rim": .10, "three": .05, "transition": .25, "turnover": .025},
    "Mouvement de balle": {"assist": .18, "three": .05, "turnover": -.012},
    "Rebond offensif": {"oreb": .18, "transition_defense": -.10},
}
DEFENSE_PROFILE = {
    "Équilibré": {},
    "Protection du cercle": {"rim_def": .16, "three_allow": .08},
    "Défense extérieure": {"perimeter_def": .15, "rim_allow": .06},
    "Pression porteur": {"turnover_force": .05, "foul": .025, "drive_allow": .04},
    "Zone": {"rim_def": .08, "three_allow": .07, "oreb_allow": .08, "assist_allow": .05},
    "Homme à homme": {"perimeter_def": .05, "rim_def": .03},
    "Box out": {"oreb_def": .20, "transition_allow": .05},
    "Repli défensif": {"transition_def": .22, "oreb_allow": .03},
}

# Interactions between an offensive idea and the opponent's defensive idea.
# Values are deliberately small: tactics change the situations created, while
# player ratings still decide whether those situations are converted.
TACTIC_MATCHUPS = {
    ("Jeu intérieur", "Protection du cercle"): {"rim": -.12, "rim_quality": -.018},
    ("Jeu intérieur", "Défense extérieure"): {"rim": .08, "rim_quality": .010},
    ("Jeu intérieur", "Zone"): {"rim": -.05, "assist": .04},
    ("Jeu intérieur", "Box out"): {"oreb": -.04},

    ("Tir extérieur", "Défense extérieure"): {"three": -.12, "three_quality": -.020, "rim": .035},
    ("Tir extérieur", "Protection du cercle"): {"three": .10, "three_quality": .012},
    ("Tir extérieur", "Zone"): {"three": .06, "three_quality": .006, "assist": .04},

    ("Pénétration", "Protection du cercle"): {"rim": -.10, "rim_quality": -.017},
    ("Pénétration", "Défense extérieure"): {"rim": .06, "rim_quality": .008},
    ("Pénétration", "Pression porteur"): {"turnover": .010, "rim": .035},
    ("Pénétration", "Zone"): {"rim": -.05, "assist": .055},

    ("Pick & Roll", "Homme à homme"): {"rim": .045, "three": .035, "assist": .035},
    ("Pick & Roll", "Pression porteur"): {"rim": .045, "turnover": -.006},
    ("Pick & Roll", "Zone"): {"rim": -.035, "three": .035, "assist": .045},

    ("Jeu rapide", "Repli défensif"): {"transition": -.18, "rim": -.045},
    ("Jeu rapide", "Box out"): {"transition": .08, "rim": .035},
    ("Jeu rapide", "Pression porteur"): {"transition": .035, "turnover": .008},

    ("Mouvement de balle", "Zone"): {"assist": .09, "three": .045, "three_quality": .007},
    ("Mouvement de balle", "Homme à homme"): {"assist": .035},
    ("Mouvement de balle", "Pression porteur"): {"turnover": -.010, "assist": .025},

    ("Rebond offensif", "Zone"): {"oreb": .11},
    ("Rebond offensif", "Box out"): {"oreb": -.15},
    ("Rebond offensif", "Repli défensif"): {"oreb": .045},
}


def normalize_tactics(t):
    out = DEFAULT_TACTICS.copy()
    if isinstance(t, dict):
        for k in out:
            if k in t and t[k]: out[k] = t[k]
    offense=[out["offensePrimary"],out["offenseSecondary"],out["offenseTertiary"]]
    defense=[out["defensePrimary"],out["defenseSecondary"],out["defenseTertiary"]]
    if any(x not in OFFENSE_FOCUSES for x in offense) or any(x not in DEFENSE_FOCUSES for x in defense):
        raise ValueError("Focus tactique inconnu.")
    if len(set(offense)) != 3 or len(set(defense)) != 3:
        raise ValueError("Les trois priorités offensives et les trois priorités défensives doivent être différentes.")
    return out


def _effects(tactics, side):
    table = OFFENSE_PROFILE if side == "offense" else DEFENSE_PROFILE
    keys = ("offensePrimary","offenseSecondary","offenseTertiary") if side == "offense" else ("defensePrimary","defenseSecondary","defenseTertiary")
    result = {}
    seen = set()
    for weight, key in zip(PRIORITY, keys):
        focus = tactics.get(key, "Équilibré")
        if focus in seen: continue
        seen.add(focus)
        for stat, value in table.get(focus, {}).items(): result[stat] = result.get(stat, 0.0) + value * weight
    return result


def _focuses(tactics, side):
    keys = ("offensePrimary","offenseSecondary","offenseTertiary") if side == "offense" else ("defensePrimary","defenseSecondary","defenseTertiary")
    result=[]; seen=set()
    for weight,key in zip(PRIORITY,keys):
        focus=tactics.get(key,"Équilibré")
        if focus in seen: continue
        seen.add(focus); result.append((focus,weight))
    return result

def _matchup_effects(offense_tactics, defense_tactics):
    result={}
    # Cross all priorities. Primary-v-primary matters most; tertiary counters are
    # useful but cannot overwhelm a talent gap. The 0.72 factor is the global
    # tactical-strength cap for matchup interactions.
    for of,ow in _focuses(offense_tactics,"offense"):
        for df,dw in _focuses(defense_tactics,"defense"):
            for stat,value in TACTIC_MATCHUPS.get((of,df),{}).items():
                result[stat]=result.get(stat,0.0)+value*ow*dw*.72
    return result


def _clamp(v, lo, hi): return max(lo, min(hi, v))
def _sigmoid(x): return 1.0 / (1.0 + math.exp(-x))
def _pick(items, weights): return random.choices(items, weights=[max(.001,w) for w in weights], k=1)[0]


def _energy_factor(p, stat="skill"):
    e = getattr(p, "energy", 100.0)
    # Almost no penalty above 82; increasingly meaningful below it.
    loss = max(0.0, 82.0 - e)
    scale = {"skill": .0028, "athletic": .0045, "defense": .0040}.get(stat, .003)
    return max(.78, 1.0 - loss * scale)


def _offense_rating(p):
    return (.34*p.outside_scoring + .32*p.inside_scoring + .22*p.playmaking + .08*p.athleticism + .04*p.overall) * _energy_factor(p)


def _creator_weight(p):
    """Who initiates a possession. Elite playmakers should clearly own more creation."""
    creation = .68*p.playmaking + .12*p.overall + .09*max(p.inside_scoring,p.outside_scoring) + .06*p.athleticism + .05*p.outside_scoring
    return math.exp((creation-72.0)/9.8) * _energy_factor(p)

def _finisher_weight(p, creator=None):
    """Who finishes a possession after the advantage has been created."""
    primary=max(p.inside_scoring,p.outside_scoring); secondary=min(p.inside_scoring,p.outside_scoring)
    scoring=.54*primary+.16*secondary+.12*p.overall+.10*p.athleticism+.08*p.playmaking
    w=math.exp((scoring-72.0)/11.3)*_energy_factor(p)
    if creator is p: w*=1.22
    return w

def _usage_weight(p):
    # Usage is driven by the player's BEST scoring weapon, not by an average that
    # punishes specialists (elite shooters or dominant interior scorers). Overall
    # and playmaking act as proxies for on-ball responsibility. No hard-coded
    # "star gets X shots" rule: the hierarchy emerges from ratings.
    primary_scoring = max(p.inside_scoring, p.outside_scoring)
    secondary_scoring = min(p.inside_scoring, p.outside_scoring)
    creation = (.44*primary_scoring + .14*secondary_scoring + .20*p.playmaking
                + .14*p.overall + .08*p.athleticism)
    return math.exp((creation - 72.0) / 11.8) * _energy_factor(p)


def _shot_profile(p):
    pos = primary_position(p)
    rim = 0.34 + (p.inside_scoring-p.outside_scoring)/180 + (p.athleticism-75)/500
    three = 0.34 + (p.outside_scoring-p.inside_scoring)/165
    if pos == "C": rim += .16; three -= .10
    elif pos == "PF": rim += .07; three -= .03
    elif pos in ("PG","SG"): three += .04
    rim = _clamp(rim, .18, .62); three = _clamp(three, .14, .58)
    mid = max(.10, 1-rim-three)
    total = rim+mid+three
    return {"rim":rim/total,"mid":mid/total,"three":three/total}



# How well each offensive focus fits the actual players on court.  A tactic can
# change intent, but cannot manufacture a skill the lineup does not possess.
def _lineup_focus_fit(lineup, focus):
    if not lineup:
        return 0.5
    avg=lambda fn: sum(fn(p) for p in lineup)/len(lineup)
    outside=avg(lambda p:p.outside_scoring)
    inside=avg(lambda p:p.inside_scoring)
    play=avg(lambda p:p.playmaking)
    ath=avg(lambda p:p.athleticism)
    reb=avg(lambda p:p.rebounding)
    overall=avg(lambda p:p.overall)
    # 0.0 = very poor fit, 1.0 = elite fit. Values around 75 are deliberately
    # neutral so ordinary NBA lineups do not receive a hidden penalty.
    skill={
        "Équilibré": overall,
        "Jeu intérieur": .70*inside+.18*ath+.12*reb,
        "Tir extérieur": .82*outside+.18*play,
        "Pénétration": .58*inside+.27*ath+.15*play,
        "Pick & Roll": .52*play+.24*inside+.24*outside,
        "Jeu rapide": .62*ath+.23*play+.15*overall,
        "Mouvement de balle": .72*play+.18*outside+.10*overall,
        "Rebond offensif": .72*reb+.28*ath,
    }.get(focus, overall)
    return _clamp((skill-62.0)/26.0, 0.0, 1.0)

def _roster_fit_effects(tactics, lineup):
    result={}
    fits=[]
    for focus,weight in _focuses(tactics,"offense"):
        fit=_lineup_focus_fit(lineup,focus)
        fits.append((focus,fit,weight))
        # Poor fit reduces the extra situations requested by the tactic; great
        # fit slightly improves their quality. This remains much smaller than
        # the player's own shot/defense ratings.
        signed=(fit-.5)*2.0
        if focus=="Tir extérieur":
            result["three"] = result.get("three",0)+signed*.075*weight
            result["three_quality"] = result.get("three_quality",0)+signed*.008*weight
        elif focus in ("Jeu intérieur","Pénétration"):
            result["rim"] = result.get("rim",0)+signed*.065*weight
            result["rim_quality"] = result.get("rim_quality",0)+signed*.007*weight
        elif focus=="Pick & Roll":
            result["assist"] = result.get("assist",0)+signed*.050*weight
            result["rim"] = result.get("rim",0)+signed*.030*weight
        elif focus=="Jeu rapide":
            result["transition"] = result.get("transition",0)+signed*.070*weight
            result["rim"] = result.get("rim",0)+signed*.025*weight
        elif focus=="Mouvement de balle":
            result["assist"] = result.get("assist",0)+signed*.070*weight
            result["turnover"] = result.get("turnover",0)-signed*.004*weight
        elif focus=="Rebond offensif":
            result["oreb"] = result.get("oreb",0)+signed*.080*weight
    return result, fits

def tactic_compatibility(tactics, players, minutes=None):
    """Public 0-100 compatibility scores, minute-weighted for the rotation."""
    tactics=normalize_tactics(tactics)
    minutes=minutes or {p.name:1 for p in players}
    active=[p for p in players if minutes.get(p.name,0)>0] or list(players)
    weights=[max(0,minutes.get(p.name,0)) for p in active]
    if not any(weights): weights=[1]*len(active)
    def avg(attr):
        den=sum(weights) or 1
        return sum(getattr(p,attr)*w for p,w in zip(active,weights))/den
    outside,inside,play,ath,reb,overall=(avg(x) for x in ("outside_scoring","inside_scoring","playmaking","athleticism","rebounding","overall"))
    def focus_skill(focus):
        return {
          "Équilibré":overall,"Jeu intérieur":.70*inside+.18*ath+.12*reb,
          "Tir extérieur":.82*outside+.18*play,"Pénétration":.58*inside+.27*ath+.15*play,
          "Pick & Roll":.52*play+.24*inside+.24*outside,"Jeu rapide":.62*ath+.23*play+.15*overall,
          "Mouvement de balle":.72*play+.18*outside+.10*overall,"Rebond offensif":.72*reb+.28*ath,
        }.get(focus,overall)
    details=[]; weighted=0; den=0
    for focus,priority in _focuses(tactics,"offense"):
        score=round(100*_clamp((focus_skill(focus)-62)/26,0,1))
        details.append({"focus":focus,"score":score,"priority_weight":priority})
        weighted+=score*priority; den+=priority
    overall_score=round(weighted/den) if den else 50
    label="Excellente" if overall_score>=80 else "Bonne" if overall_score>=67 else "Moyenne" if overall_score>=52 else "Faible"
    return {"overall":overall_score,"label":label,"offense":details}


def _best_defender(def_team, attacker, area):
    candidates = [p for p in def_team.on_court if p.fouls < 6] or list(def_team.on_court)
    apos = getattr(attacker, "current_position", primary_position(attacker))
    natural = [d for d in candidates if getattr(d, "current_position", primary_position(d)) == apos]
    pool = natural or [d for d in candidates if apos in eligible_positions(d)] or candidates
    def score(d):
        base = perimeter_defense(d) if area in ("three","mid") else interior_defense(d)
        return base*_energy_factor(d,"defense") + random.uniform(-5,5)
    return max(pool, key=score)


def _shot_probability(shooter, defender, area, assisted, oe, de, mx):
    if area == "three":
        skill = shooter.outside_scoring
        defense = perimeter_defense(defender) * _energy_factor(defender,"defense")
        base = .337
        matchup = (skill-defense)*.0030
        context = -de.get("perimeter_def",0)*.075 + de.get("three_allow",0)*.055 + mx.get("three_quality",0)
    elif area == "mid":
        skill = .72*shooter.outside_scoring + .28*shooter.inside_scoring
        defense = .65*perimeter_defense(defender)+.35*interior_defense(defender)
        base = .432; matchup=(skill-defense)*.0027; context=-de.get("perimeter_def",0)*.035
    else:
        skill = .72*shooter.inside_scoring + .28*shooter.athleticism
        defense = interior_defense(defender) * _energy_factor(defender,"defense")
        base = .565; matchup=(skill-defense)*.0030
        context = -de.get("rim_def",0)*.075 + de.get("rim_allow",0)*.055 + de.get("drive_allow",0)*.025 + mx.get("rim_quality",0)
    energy = (_energy_factor(shooter)-1)*.45
    assist_bonus = .022 if assisted else 0
    return _clamp(base + matchup + context + energy + assist_bonus, .20, .78)


def _rebound(att, dfn, shooter, oe, de):
    aw = sum((p.rebounding*.72+p.athleticism*.28)*_energy_factor(p,"athletic") for p in att.on_court)
    dw = sum((p.rebounding*.76+p.athleticism*.24)*_energy_factor(p,"athletic") for p in dfn.on_court)
    p_oreb = .235 + (aw-dw)*.0008 + oe.get("oreb",0)*.12 + de.get("oreb_allow",0)*.10 - de.get("oreb_def",0)*.13
    offense = random.random() < _clamp(p_oreb,.13,.36)
    team = att if offense else dfn
    rebounder = _pick(team.on_court, [(p.rebounding*.8+p.athleticism*.2)*_energy_factor(p,"athletic") for p in team.on_court])
    rebounder.rebounds += 1
    return offense


def _free_throws(shooter, n):
    pct = _clamp(.72 + (shooter.outside_scoring-60)*.0035 + (shooter.playmaking-75)*.0006, .65, .94)
    made=0
    for _ in range(n):
        shooter.free_throws_attempted += 1
        if random.random()<pct: shooter.free_throws_made += 1; shooter.points += 1; made += 1
    return made


def _play_possession(att, dfn, tactics_a, tactics_d):
    oe, de = _effects(tactics_a,"offense"), _effects(tactics_d,"defense")
    mx = _matchup_effects(tactics_a, tactics_d)
    lineup = [p for p in att.on_court if p.fouls < 6] or list(att.on_court)
    fit_effects, _ = _roster_fit_effects(tactics_a, lineup)
    for stat,value in fit_effects.items():
        (mx if stat.endswith("_quality") else oe)[stat] = (mx if stat.endswith("_quality") else oe).get(stat,0)+value

    # Separate possession creator from finisher. This avoids forcing the same
    # player to own shots, turnovers and free throws on every possession.
    creator = _pick(lineup, [_creator_weight(p) for p in lineup])

    if random.random() < .075 + de.get("foul", 0)*.12:
        foul_def = random.choice([p for p in dfn.on_court if p.fouls < 6] or list(dfn.on_court))
        foul_def.fouls += 1

    handler_quality = .74*creator.playmaking + .18*creator.overall + .08*creator.athleticism
    tov = .132 + (75-handler_quality)*.0012 + oe.get("turnover",0) + de.get("turnover_force",0) + mx.get("turnover",0)
    if random.random() < _clamp(tov,.070,.205):
        creator.turnovers += 1
        return 0, False

    # Better creators generate a little more offense for teammates, while elite
    # scorers can still self-create and remain high-usage finishers.
    pass_intent = _clamp(.34 + (creator.playmaking-70)*.010 + oe.get("assist",0)*.34 + mx.get("assist",0)*.24, .16, .78)
    if random.random() < pass_intent:
        candidates=[p for p in lineup if p is not creator]
        shooter=_pick(candidates,[_finisher_weight(p,creator) for p in candidates]) if candidates else creator
        potential_assist=True
    else:
        shooter=_pick(lineup,[_finisher_weight(p,creator) for p in lineup])
        potential_assist=(shooter is not creator and random.random()<.72)

    profile = _shot_profile(shooter)
    profile["rim"] *= 1+oe.get("rim",0)+mx.get("rim",0); profile["mid"] *= 1+oe.get("mid",0)+mx.get("mid",0); profile["three"] *= 1+oe.get("three",0)+mx.get("three",0)
    if de.get("rim_def",0): profile["rim"] *= 1-de["rim_def"]*.30
    if de.get("perimeter_def",0): profile["three"] *= 1-de["perimeter_def"]*.24
    area = _pick(["rim","mid","three"], [profile["rim"],profile["mid"],profile["three"]])
    defender = _best_defender(dfn, shooter, area)

    assisted = potential_assist and random.random() < _clamp(.64 + (creator.playmaking-75)*.009 + oe.get("assist",0)*.34 + de.get("assist_allow",0)*.16 + mx.get("assist",0)*.28,.26,.89)
    passer = creator if assisted and creator is not shooter else None

    foul = (.145 if area=="rim" else .075) + de.get("foul",0)*.22 + (shooter.inside_scoring-75)*.0011
    if random.random() < _clamp(foul,.02,.19):
        foul_player = defender
        if defender.fouls >= 5 and random.random() < .72:
            alternatives = [p for p in dfn.on_court if p is not defender and p.fouls < 5]
            if alternatives: foul_player = random.choice(alternatives)
        foul_player.fouls += 1
        attempts = 3 if area=="three" else 2
        return _free_throws(shooter, attempts), False

    shooter.shots_attempted += 1
    if area=="three": shooter.three_attempted += 1
    made = random.random() < _shot_probability(shooter,defender,area,assisted,oe,de,mx)
    if made:
        pts=3 if area=="three" else 2
        shooter.shots_made += 1; shooter.points += pts
        if area=="three": shooter.three_made += 1
        if area=="rim": att._points_in_paint += 2
        if passer is not None: passer.assists += 1
        return pts, False
    oe_reb=dict(oe); oe_reb["oreb"]=oe_reb.get("oreb",0)+mx.get("oreb",0)
    return 0, _rebound(att,dfn,shooter,oe_reb,de)

def _set_minute_lineup(team, minute):
    lineup = team.rotation_schedule[minute]
    # Foul-out fallback: use best legal positional five when possible.
    if any(p.fouls>=6 for p in lineup):
        legal=[p for p in team.roster if p.fouls<6]
        legal.sort(key=lambda p: p.overall*_energy_factor(p), reverse=True)
        found=None
        from itertools import combinations
        for combo in combinations(legal[:11],5):
            if position_assignment(combo) is not None: found=list(combo); break
        if found: lineup=found
    team.on_court=list(lineup); team.bench=[p for p in team.roster if p not in team.on_court]
    assign=position_assignment(team.on_court)
    if assign:
        for pos,p in assign.items(): p.current_position=pos


def _energy_tick(team):
    for p in team.roster:
        if p in team.on_court:
            drain = 2.15 + (82-p.stamina)*.018
            p.energy=max(45.0,p.energy-drain); p.minutes_played += 1
        else:
            p.energy=min(100.0,p.energy+3.15+(p.stamina-75)*.012)


def _pace(t1,t2):
    # Natural NBA pace. Transition offense is now resolved against the
    # opponent's transition defense; V45 defined those effects but did not use them.
    a=_effects(t1,"offense"); b=_effects(t2,"offense")
    d1=_effects(t1,"defense"); d2=_effects(t2,"defense")
    mx12=_matchup_effects(t1,t2); mx21=_matchup_effects(t2,t1)
    tr1=(a.get("transition",0)+mx12.get("transition",0)
         +d2.get("transition_allow",0)-d2.get("transition_def",0))
    tr2=(b.get("transition",0)+mx21.get("transition",0)
         +d1.get("transition_allow",0)-d1.get("transition_def",0))
    return _clamp(random.gauss(99.3,3.4)+(tr1+tr2)*5.0,92,108)


def _overtime_lineup(team):
    legal=[p for p in team.roster if p.fouls<6]
    legal.sort(key=lambda p: p.overall*_energy_factor(p), reverse=True)
    from itertools import combinations
    for combo in combinations(legal[:11],5):
        if position_assignment(combo) is not None:
            team.on_court=list(combo); team.bench=[p for p in team.roster if p not in combo]
            assign=position_assignment(combo)
            for pos,p in assign.items(): p.current_position=pos
            return


def simulate_game(team1, team2, rotation1, rotation2=None, starter_names1=None, starter_names2=None, role_map1=None, role_map2=None, tactics1=None, tactics2=None):
    t1,t2=normalize_tactics(tactics1),normalize_tactics(tactics2)
    configure_team_for_match(team1,starter_names1,None); configure_team_for_match(team2,starter_names2,None)
    if rotation2 is None: raise ValueError("Une rotation adverse est requise en V39.")
    set_rotation_plan(team1,rotation1); set_rotation_plan(team2,rotation2)
    reset_game_stats(team1); reset_game_stats(team2)
    for team in (team1,team2):
        team._quarter_scores=[0,0,0,0]
        for p in team.roster: p.energy=100.0
    score=[0,0]; timeline=[]; attack=random.randrange(2)
    target_possessions=round(_pace(t1,t2))
    # Distribute each team's target possessions across the 48 regulation minutes.
    poss_per_min=[0]*48
    slots=[i for i in range(48) for _ in range(2)]
    extra=max(0,target_possessions-96)
    chosen=set(random.sample(range(48), min(extra,48))) if extra else set()
    # Base ~2 possessions per team per minute, randomly skip enough to hit target.
    total_events=round(target_possessions*2.22)
    minute_events=[4]*48
    remove=max(0, 192-total_events)
    while remove>0:
        i=random.randrange(48)
        if minute_events[i]>2: minute_events[i]-=1; remove-=1
    add=max(0, total_events-192)
    while add>0:
        i=random.randrange(48); minute_events[i]+=1; add-=1

    teams=(team1,team2); tacs=(t1,t2)
    for minute in range(48):
        for team in teams: _set_minute_lineup(team,minute)
        q=minute//12
        timeline.append({"minute":minute+1,"quarter":q+1,"overtime":0,"minute_in_quarter":minute%12+1,"clock_start":f"{12-minute%12:02d}:00","clock_end":f"{11-minute%12:02d}:00",
            "team1":[{"name":p.name,"position":p.current_position,"role":p.role,"energy":round(p.energy)} for p in team1.on_court],
            "team2":[{"name":p.name,"position":p.current_position,"role":p.role,"energy":round(p.energy)} for p in team2.on_court]})
        for _ in range(minute_events[minute]):
            a,d=attack,1-attack
            pts,oreb=_play_possession(teams[a],teams[d],tacs[a],tacs[d])
            score[a]+=pts; teams[a]._quarter_scores[q]+=pts
            if not oreb:
                teams[a]._possessions += 1; attack=d
        for team in teams: _energy_tick(team)

    period=4
    while score[0]==score[1]:
        for team in teams: team._quarter_scores.append(0); _overtime_lineup(team)
        for m in range(5):
            timeline.append({"minute":49+(period-4)*5+m,"quarter":period+1,"overtime":period-3,"minute_in_quarter":m+1,"clock_start":f"{5-m:02d}:00","clock_end":f"{4-m:02d}:00",
                "team1":[{"name":p.name,"position":p.current_position,"role":p.role,"energy":round(p.energy)} for p in team1.on_court],"team2":[{"name":p.name,"position":p.current_position,"role":p.role,"energy":round(p.energy)} for p in team2.on_court]})
            for _ in range(4):
                a,d=attack,1-attack; pts,oreb=_play_possession(teams[a],teams[d],tacs[a],tacs[d]); score[a]+=pts; teams[a]._quarter_scores[period]+=pts
                if not oreb: teams[a]._possessions+=1; attack=d
            for team in teams: _energy_tick(team)
        period+=1
    return {"team1":team_result(team1,score[0]),"team2":team_result(team2,score[1]),"overtime":period>4,"periods":period,"rotation_timeline":timeline}
