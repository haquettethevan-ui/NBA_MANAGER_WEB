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
    # Continuous game-plan controls (0..100). 50 is neutral.
    "pace": 50,
    "ballMovement": 55,
    "pickAndRoll": 50,
    "postPlay": 40,
    "rimPriority": 55,
    "midPriority": 35,
    "threePriority": 55,
    # One axis: 0 = get back, 100 = crash offensive glass.
    "offensiveGlass": 45,
    "perimeterPressure": 50,
    "rimProtection": 50,
    "helpDefense": 50,
    "switching": 45,
    # One axis: 0 = crash defensive glass, 100 = leak out / transition.
    "defensiveTransition": 50,
}
TACTIC_KEYS = tuple(DEFAULT_TACTICS)

def _legacy_to_continuous(t):
    """Translate old priority saves so existing leagues remain playable."""
    out=DEFAULT_TACTICS.copy()
    if not isinstance(t,dict): return out
    weights=(1.0,.58,.30)
    off_map={
        "Jeu intérieur":{"rimPriority":22,"postPlay":24,"threePriority":-12},
        "Tir extérieur":{"threePriority":25,"rimPriority":-9,"midPriority":-8},
        "Pénétration":{"rimPriority":24,"pace":5},
        "Pick & Roll":{"pickAndRoll":28,"ballMovement":7},
        "Jeu rapide":{"pace":28,"rimPriority":9},
        "Mouvement de balle":{"ballMovement":28},
        "Rebond offensif":{"offensiveGlass":30},
    }
    def_map={
        "Protection du cercle":{"rimProtection":28,"perimeterPressure":-8},
        "Défense extérieure":{"perimeterPressure":27,"rimProtection":-6},
        "Pression porteur":{"perimeterPressure":18,"helpDefense":-4},
        "Zone":{"helpDefense":22,"perimeterPressure":-7},
        "Homme à homme":{"perimeterPressure":8,"switching":-4},
        "Box out":{"defensiveTransition":-24},
        "Repli défensif":{"defensiveTransition":28},
    }
    for side,mapping in (("offense",off_map),("defense",def_map)):
        for w,suffix in zip(weights,("Primary","Secondary","Tertiary")):
            for k,v in mapping.get(t.get(side+suffix),{}).items():
                out[k]+=v*w
    return {k:int(round(_clamp(v,0,100))) for k,v in out.items()}

def normalize_tactics(t):
    if isinstance(t,dict) and any(k in t for k in TACTIC_KEYS):
        return {k:int(round(_clamp(float(t.get(k,v)),0,100))) for k,v in DEFAULT_TACTICS.items()}
    return _legacy_to_continuous(t)

def _n(t,key):
    return (float(t.get(key,DEFAULT_TACTICS[key]))-50.0)/50.0

def _effects(tactics, side):
    """Translate manager intent into situation volume, never direct shot accuracy."""
    t=normalize_tactics(tactics)
    if side=="offense":
        pace=_n(t,"pace"); move=_n(t,"ballMovement"); pnr=_n(t,"pickAndRoll")
        post=_n(t,"postPlay"); glass=_n(t,"offensiveGlass")
        # Shot priorities are relative: maxing rim + three mostly squeezes midrange.
        raw={"rim":max(5.0,t["rimPriority"]),"mid":max(5.0,t["midPriority"]),"three":max(5.0,t["threePriority"])}
        mean=sum(raw.values())/3.0
        return {
            "rim":(raw["rim"]/mean-1)*.22,
            "mid":(raw["mid"]/mean-1)*.18,
            "three":(raw["three"]/mean-1)*.22,
            "transition":pace*.22,
            "assist":move*.10,
            "pnr":max(0,pnr)*.10,
            "post":max(0,post)*.12,
            "oreb":glass*.10,
            "turnover":pace*.006 + max(0,move)*.002,
        }
    pressure=_n(t,"perimeterPressure"); rim=_n(t,"rimProtection"); helpd=_n(t,"helpDefense")
    switching=_n(t,"switching"); trans=_n(t,"defensiveTransition")
    # Defense changes where shots are available and possession outcomes. No
    # perimeter_def/rim_def quality modifier is emitted here.
    return {
        "three_suppress":max(0,pressure)*.14,
        "rim_allow":max(0,pressure)*.08 + max(0,switching)*.025,
        "rim_suppress":max(0,rim)*.14 + max(0,helpd)*.045,
        "three_allow":max(0,rim)*.09 + max(0,helpd)*.055,
        "turnover_force":max(0,pressure)*.007,
        "foul":max(0,pressure)*.004 + max(0,helpd)*.002,
        "transition_def":max(0,trans)*.25,
        "transition_allow":max(0,-trans)*.10,
        "oreb_def":max(0,-trans)*.11,
        "oreb_allow":max(0,trans)*.07,
        "assist_allow":max(0,-helpd)*.035,
    }

def _focuses(tactics, side):
    # Compatibility helper retained for API callers; new tactics are continuous.
    return []

def _matchup_effects(offense_tactics, defense_tactics):
    # V2 has no rock-paper-scissors make-percentage table.
    return {}


def _clamp(v, lo, hi): return max(lo, min(hi, v))
def _sigmoid(x): return 1.0 / (1.0 + math.exp(-x))
def _pick(items, weights): return random.choices(items, weights=[max(.001,w) for w in weights], k=1)[0]


def energy_factor_from_value(energy, stat="skill"):
    """Shared fatigue curve: 80-100 is fully fresh; penalties accelerate below 80."""
    e = _clamp(float(energy), 45.0, 100.0)
    if e >= 80.0:
        return 1.0
    # At 70/60/50/45 energy, skill is roughly 98/95/91/88%.
    deficit = 80.0 - e
    base_loss = .0015 * deficit + .000075 * deficit * deficit
    stat_mult = {"skill": 1.0, "athletic": 1.16, "defense": 1.10}.get(stat, 1.0)
    return max(.78, 1.0 - base_loss * stat_mult)


def _energy_factor(p, stat="skill"):
    return energy_factor_from_value(getattr(p, "energy", 100.0), stat)


def _offense_rating(p):
    return (.34*p.outside_scoring + .32*p.inside_scoring + .22*p.playmaking + .08*p.athleticism + .04*p.overall) * _energy_factor(p)


def _creator_weight(p):
    """Who initiates a possession. Elite playmakers should clearly own more creation."""
    creation = .68*p.playmaking + .12*p.overall + .09*max(p.inside_scoring,p.outside_scoring) + .06*p.athleticism + .05*p.outside_scoring
    return math.exp((creation-72.0)/9.2) * _energy_factor(p)

def _finisher_weight(p, creator=None):
    """Who finishes a possession after the advantage has been created."""
    primary=max(p.inside_scoring,p.outside_scoring); secondary=min(p.inside_scoring,p.outside_scoring)
    scoring=.52*primary+.15*secondary+.17*p.overall+.09*p.athleticism+.07*p.playmaking
    w=math.exp((scoring-72.0)/10.5)*_energy_factor(p)
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

def _lineup_execution_factors(lineup):
    """Real lineup abilities used to scale collective tactical situations.

    These are not bonuses: 1.0 is an ordinary NBA lineup. A weak transition or
    rebounding unit simply cannot create the same volume of those situations as
    an elite one.
    """
    if not lineup:
        return {"transition":1.0,"oreb":1.0,"drive":1.0}
    avg=lambda attr: sum(getattr(p,attr) for p in lineup)/len(lineup)
    ath,play,inside,reb=(avg(x) for x in ("athleticism","playmaking","inside_scoring","rebounding"))
    transition=.68*ath+.32*play
    drive=.50*inside+.32*ath+.18*play
    glass=.76*reb+.24*ath
    # Wider than a cosmetic modifier, but bounded so tactics never disappear.
    scale=lambda skill: _clamp(.62+(skill-62.0)/26.0*.62,.62,1.24)
    return {"transition":scale(transition),"drive":scale(drive),"oreb":scale(glass)}


def _apply_lineup_execution(oe, lineup):
    factors=_lineup_execution_factors(lineup)
    out=dict(oe)
    # Only situation volume is scaled. Shot/rebound conversion is still resolved
    # from the participating players' ratings against the defense.
    if out.get("transition",0)>0: out["transition"]*=factors["transition"]
    if out.get("drive",0)>0:
        out["drive"]*=factors["drive"]
        # Penetration's rim-volume component should also depend on actual drivers.
        out["rim"] = out.get("rim",0) * (.72+.28*factors["drive"])
    if out.get("oreb",0)>0: out["oreb"]*=factors["oreb"]
    return out


def _roster_fit_effects(tactics, lineup):
    """Compatibility is diagnostic only; it must not manufacture efficiency.

    The selected tactic creates situations. The players' real ratings determine
    whether those situations are good for this lineup.
    """
    fits=[(focus,_lineup_focus_fit(lineup,focus),weight)
          for focus,weight in _focuses(tactics,"offense")]
    return {}, fits


def _tactical_finisher_weight(p, creator, oe):
    """Route tactical opportunities toward players whose real skills fit them.

    This changes *who gets the situation*, never the make probability. Once the
    shooter is selected, _shot_probability uses his actual scoring rating versus
    the actual defender.
    """
    w=_finisher_weight(p,creator)
    three=max(-.25,min(.40,oe.get("three",0)))
    rim=max(-.25,min(.45,oe.get("rim",0)))
    pnr=max(0.0,oe.get("pnr",0))
    transition=max(0.0,oe.get("transition",0))
    movement=max(0.0,oe.get("assist",0))

    # Center ratings around ordinary NBA ability so specialists are naturally
    # targeted by the system they suit, while weak fits are not magically fixed.
    outside=(p.outside_scoring-75.0)/15.0
    inside=(p.inside_scoring-75.0)/15.0
    athletic=(p.athleticism-75.0)/15.0
    play=(p.playmaking-75.0)/15.0

    intent = (
        three * outside * 1.30
        + rim * (.78*inside + .22*athletic) * 1.15
        + pnr * (.52*play + .28*inside + .20*outside) * .70
        + transition * (.62*athletic + .23*play + .15*inside) * .42
        + movement * (.68*play + .32*outside) * .55
    )
    return w * math.exp(_clamp(intent,-.75,.75))

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


def _best_defender(def_team, attacker, area, oe=None):
    """Choose the defender from the basketball situation, not a random best-defender roll.

    Normal half-court possessions keep the positional matchup. Pick & Roll can
    create a switch; transition can create a cross-match. These are exceptions,
    not the default defensive assignment.
    """
    oe = oe or {}
    candidates = [p for p in def_team.on_court if p.fouls < 6] or list(def_team.on_court)
    apos = getattr(attacker, "current_position", primary_position(attacker))

    # Default: the player currently occupying the same lineup position.
    natural = [d for d in candidates if getattr(d, "current_position", primary_position(d)) == apos]
    natural_def = natural[0] if natural else None

    # Transition possessions are less organized and may create a cross-match.
    transition_level = max(0.0, oe.get("transition", 0))
    crossmatch_p = min(.20, .035 + transition_level * .22)

    # Pick & Roll is the main source of switches. The switch defender should be
    # positionally adjacent (guard/wing or forward/big), not any random player.
    pnr_level = max(0.0, oe.get("pnr", 0))
    switch_p = min(.32, .045 + pnr_level * .65)

    roll = random.random()
    if roll < switch_p:
        order = ["PG","SG","SF","PF","C"]
        if apos in order:
            idx = order.index(apos)
            adjacent = {order[j] for j in (idx-1, idx+1) if 0 <= j < len(order)}
            switchers = [d for d in candidates
                         if getattr(d, "current_position", primary_position(d)) in adjacent]
            if switchers:
                # Among realistic switch candidates, defensive ability matters.
                key = perimeter_defense if area in ("three","mid") else interior_defense
                return max(switchers, key=lambda d: key(d) * _energy_factor(d,"defense"))

    if roll < switch_p + crossmatch_p:
        # Broken transition: nearest compatible defender, mildly favoring quality.
        pool = [d for d in candidates if d is not natural_def] or candidates
        key = perimeter_defense if area in ("three","mid") else interior_defense
        weights = [max(1.0, key(d) * _energy_factor(d,"defense")) for d in pool]
        return _pick(pool, weights)

    if natural_def is not None:
        return natural_def

    # Emergency fallback for unusual lineups/foul-outs.
    compatible = [d for d in candidates if apos in eligible_positions(d)]
    pool = compatible or candidates
    key = perimeter_defense if area in ("three","mid") else interior_defense
    return max(pool, key=lambda d: key(d) * _energy_factor(d,"defense"))


def _shot_probability(shooter, defender, area, assisted, oe, de, mx):
    if area == "three":
        skill = shooter.outside_scoring
        defense = perimeter_defense(defender) * _energy_factor(defender,"defense")
        # League calibration: keep 3PA volume/tactical effects intact while
        # bringing simulated 3P% down from ~40.8% toward the NBA 36-37% range.
        base = .312
        matchup = (skill-defense)*.00365
        context = -de.get("perimeter_def",0)*.075 + de.get("three_allow",0)*.055 + mx.get("three_quality",0)
    elif area == "mid":
        skill = .72*shooter.outside_scoring + .28*shooter.inside_scoring
        defense = .65*perimeter_defense(defender)+.35*interior_defense(defender)
        base = .427; matchup=(skill-defense)*.00335; context=-de.get("perimeter_def",0)*.035
    else:
        skill = .72*shooter.inside_scoring + .28*shooter.athleticism
        defense = interior_defense(defender) * _energy_factor(defender,"defense")
        base = .567; matchup=(skill-defense)*.00365
        context = -de.get("rim_def",0)*.075 + de.get("rim_allow",0)*.055 + de.get("drive_allow",0)*.025 + mx.get("rim_quality",0)
    energy = (_energy_factor(shooter)-1)*.45
    assist_bonus = .022 if assisted else 0
    return _clamp(base + matchup + context + energy + assist_bonus, .20, .78)


def _rebound(att, dfn, shooter, oe, de):
    aw = sum((p.rebounding*.72+p.athleticism*.28)*_energy_factor(p,"athletic") for p in att.on_court)
    dw = sum((p.rebounding*.76+p.athleticism*.24)*_energy_factor(p,"athletic") for p in dfn.on_court)
    p_oreb = .235 + (aw-dw)*.00105 + oe.get("oreb",0)*.12 + de.get("oreb_allow",0)*.10 - de.get("oreb_def",0)*.13
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
    oe = _apply_lineup_execution(oe, lineup)

    # Separate possession creator from finisher. This avoids forcing the same
    # player to own shots, turnovers and free throws on every possession.
    creator = _pick(lineup, [_creator_weight(p) for p in lineup])

    if random.random() < .075 + de.get("foul", 0)*.12:
        foul_def = random.choice([p for p in dfn.on_court if p.fouls < 6] or list(dfn.on_court))
        foul_def.fouls += 1

    handler_quality = .74*creator.playmaking + .18*creator.overall + .08*creator.athleticism
    tov = .126 + (75-handler_quality)*.00175 + oe.get("turnover",0) + de.get("turnover_force",0) + mx.get("turnover",0) + max(0.0, 88.0-creator.energy)*.00075
    if random.random() < _clamp(tov,.070,.205):
        creator.turnovers += 1
        return 0, False

    # Better creators generate a little more offense for teammates, while elite
    # scorers can still self-create and remain high-usage finishers.
    pass_intent = _clamp(.34 + (creator.playmaking-70)*.010 + oe.get("assist",0)*.34 + mx.get("assist",0)*.24, .16, .78)
    if random.random() < pass_intent:
        candidates=[p for p in lineup if p is not creator]
        shooter=_pick(candidates,[_tactical_finisher_weight(p,creator,oe) for p in candidates]) if candidates else creator
        potential_assist=True
    else:
        shooter=_pick(lineup,[_tactical_finisher_weight(p,creator,oe) for p in lineup])
        potential_assist=(shooter is not creator and random.random()<.72)

    profile = _shot_profile(shooter)

    # Tactics must change shot DIET, not merely shot efficiency.  Convert the
    # weighted tactical intent into strong but bounded multipliers.  A manager
    # stacking Jeu intérieur + Pénétration should visibly trade threes for rim
    # attempts; Tir extérieur does the inverse. Player profile still supplies
    # the baseline, so Curry-like players remain more perimeter-oriented than
    # centers even inside the same system.
    rim_intent = oe.get("rim",0) + mx.get("rim",0)
    mid_intent = oe.get("mid",0) + mx.get("mid",0)
    three_intent = oe.get("three",0) + mx.get("three",0)
    profile["rim"] *= _clamp(1 + rim_intent*2.35, .52, 1.85)
    profile["mid"] *= _clamp(1 + mid_intent*1.75, .62, 1.55)
    profile["three"] *= _clamp(1 + three_intent*2.55, .42, 1.85)

    if de.get("rim_def",0): profile["rim"] *= 1-de["rim_def"]*.30
    if de.get("perimeter_def",0): profile["three"] *= 1-de["perimeter_def"]*.24
    area = _pick(["rim","mid","three"], [profile["rim"],profile["mid"],profile["three"]])
    defender = _best_defender(dfn, shooter, area, oe)

    assisted = potential_assist and random.random() < _clamp(.71 + (creator.playmaking-75)*.0105 + oe.get("assist",0)*.34 + de.get("assist_allow",0)*.16 + mx.get("assist",0)*.28,.30,.92)
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
            # Slightly slower in-game drain: normal starter minutes should not
            # automatically push a fresh player deep into the fatigue penalty zone.
            drain = 1.42 + (82-p.stamina)*.012
            p.energy=max(45.0,p.energy-drain); p.minutes_played += 1
        else:
            p.energy=min(100.0,p.energy+3.10+(p.stamina-75)*.012)


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
    return _clamp(random.gauss(102.0,3.2)+(tr1+tr2)*5.0,92,108)


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



# --- V55: season fatigue, recovery and injury layer -------------------------
def prepare_player_season_state(player):
    """Initialize persistent season state without resetting existing values."""
    player.energy = _clamp(getattr(player, "energy", 100.0), 45.0, 100.0)
    player.workload = _clamp(getattr(player, "workload", 0.0), 0.0, 100.0)
    player.injury_days = max(0, int(getattr(player, "injury_days", 0)))
    player.injury_label = getattr(player, "injury_label", "")

def recover_between_games(team, elapsed_days):
    """Advance season state to the next game.

    Injury duration follows real elapsed calendar days. Energy/workload recovery
    uses only full days without a game: a next-day back-to-back has zero rest days.
    """
    elapsed_days=max(0,int(elapsed_days))
    rest_days=max(0,elapsed_days-1)
    for p in team.roster:
        prepare_player_season_state(p)
        if p.injury_days > 0:
            p.injury_days=max(0,p.injury_days-elapsed_days)
            if p.injury_days == 0:
                p.injury_label=""
        if rest_days:
            stamina_bonus=(p.stamina-75)*.040
            recovery=14.0 + max(0,rest_days-1)*13.0 + stamina_bonus*rest_days
            p.energy=_clamp(p.energy+recovery,45.0,100.0)
            p.workload=_clamp(p.workload-(8.0+max(0,rest_days-1)*12.0),0.0,100.0)

def _postgame_workload(team):
    """Convert game minutes and end-game energy into persistent recent workload."""
    for p in team.roster:
        prepare_player_season_state(p)
        mins=getattr(p,"minutes_played",0)
        if mins <= 0:
            p.workload=max(0.0,p.workload-4.0)
            continue
        load=max(0.0,mins-18)*1.00 + max(0.0,76.0-p.energy)*.30
        p.workload=_clamp(p.workload*.68+load,0.0,100.0)

def _injury_probability(player):
    """Per-game injury probability; fatigue/workload raise risk smoothly."""
    prepare_player_season_state(player)
    mins=max(0,getattr(player,"minutes_played",0))
    if mins <= 0 or player.injury_days > 0:
        return 0.0
    # Healthy baseline is deliberately small. Risk rises with low energy,
    # recent workload and especially heavy minutes while already fatigued.
    risk=.0010
    risk += max(0.0,mins-30)*.00010
    risk += max(0.0,78.0-player.energy)*.00016
    risk += max(0.0,player.workload-45.0)*.00008
    risk += max(0.0,mins-36)*max(0.0,72.0-player.energy)*.000010
    return _clamp(risk,.0,.035)

def _roll_postgame_injuries(team):
    injuries=[]
    for p in team.roster:
        prob=_injury_probability(p)
        if prob and random.random() < prob:
            # Mostly minor injuries, occasional medium absence, rare long absence.
            x=random.random()
            if x < .74:
                days=random.randint(2,6); label="Blessure mineure"
            elif x < .96:
                days=random.randint(7,18); label="Blessure modérée"
            else:
                days=random.randint(19,40); label="Blessure importante"
            p.injury_days=days; p.injury_label=label
            injuries.append({"name":p.name,"days":days,"type":label,
                             "energy":round(p.energy,1),"workload":round(p.workload,1)})
    return injuries

def available_for_game(player):
    prepare_player_season_state(player)
    return player.injury_days <= 0

def simulate_game(team1, team2, rotation1, rotation2=None, starter_names1=None, starter_names2=None, role_map1=None, role_map2=None, tactics1=None, tactics2=None):
    t1,t2=normalize_tactics(tactics1),normalize_tactics(tactics2)
    configure_team_for_match(team1,starter_names1,None); configure_team_for_match(team2,starter_names2,None)
    if rotation2 is None: raise ValueError("Une rotation adverse est requise en V39.")
    for team,rotation in ((team1,rotation1),(team2,rotation2)):
        injured=[p.name for p in team.roster if rotation.get(p.name,0)>0 and not available_for_game(p)]
        if injured:
            raise ValueError("Rotation invalide : joueur(s) blessé(s) avec des minutes attribuées : "+", ".join(injured))
    set_rotation_plan(team1,rotation1); set_rotation_plan(team2,rotation2)
    reset_game_stats(team1); reset_game_stats(team2)
    for team in (team1,team2):
        team._quarter_scores=[0,0,0,0]
        for p in team.roster:
            # Preserve season/pregame energy when present. Fresh exhibition players
            # still default to 100, but a tired roster no longer gets silently reset.
            p.energy = _clamp(getattr(p, "energy", 100.0), 45.0, 100.0)
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
    _postgame_workload(team1); _postgame_workload(team2)
    injuries1=_roll_postgame_injuries(team1); injuries2=_roll_postgame_injuries(team2)
    return {"team1":team_result(team1,score[0]),"team2":team_result(team2,score[1]),"overtime":period>4,"periods":period,"rotation_timeline":timeline,
            "injuries":{"team1":injuries1,"team2":injuries2}}
