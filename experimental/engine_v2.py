"""Independent possession-based NBA engine prototype. No imports from the legacy engine.

All ratings are 0..100. Spatial state is abstract: pressure, advantage and
individual defensive recovery delays. Coefficients are hypotheses, not calibration.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import Counter
import math
import random

def clamp(x, a=0., b=100.):
    return max(a, min(b, x))

def chance(rng, p):
    return rng.random() < clamp(p, 0, 1)

@dataclass
class Player:
    name: str
    position: str = "SG"
    three_point: float = 75
    mid_range: float = 75
    close_shot: float = 75
    driving_layup: float = 75
    driving_dunk: float = 70
    post_control: float = 70
    ball_handle: float = 75
    pass_iq: float = 75
    pass_accuracy: float = 75
    shot_iq: float = 75
    speed: float = 75
    acceleration: float = 75
    strength: float = 75
    vertical: float = 75
    perimeter_defense: float = 75
    interior_defense: float = 75
    defensive_iq: float = 75
    offensive_rebound: float = 75
    defensive_rebound: float = 75
    stamina: float = 75
    # Remaining 2KRatings detailed attributes (all 36 represented).
    free_throw: float = 75
    offensive_consistency: float = 75
    agility: float = 75
    hustle: float = 75
    overall_durability: float = 75
    standing_dunk: float = 75
    post_hook: float = 75
    post_fade: float = 75
    draw_foul: float = 75
    hands: float = 75
    speed_with_ball: float = 75
    pass_vision: float = 75
    block: float = 75
    steal: float = 75
    pass_perception: float = 75
    defensive_consistency: float = 75
    help_defense_iq: float = 75
    intangibles: float = 75
    energy: float = 100

    def __post_init__(self):
        for key, value in vars(self).items():
            if key not in ("name", "position") and not 0 <= value <= 100:
                raise ValueError(f"{self.name}.{key} must be 0..100")

@dataclass
class DefenseState:
    delay: dict = field(default_factory=dict)  # defender index -> recovery delay 0..100
    matchups: dict = field(default_factory=lambda: {i:i for i in range(5)})
    help_count: int = 0

@dataclass
class PossessionResult:
    points: int = 0
    outcome: str = "turnover"
    shooter: str | None = None
    passer: str | None = None
    assists: int = 0
    turnovers: int = 0
    offensive_rebounds: int = 0
    offensive_fouls: int = 0
    fouls_drawn: int = 0
    fouled_by: str | None = None
    free_throws_attempted: int = 0
    free_throws_made: int = 0
    events: list = field(default_factory=list)

@dataclass
class GameMemory:
    # team-scoped history: (offense id, player index, action) -> occurrences
    actions: Counter = field(default_factory=Counter)
    counters: Counter = field(default_factory=Counter)

def skill_raw(p, attr):
    return getattr(p, attr)

def skill(p, attr):
    # Fatigue reduces athletic performance first, then execution and decisions.
    loss = max(0, 80 - p.energy) / 35 * (1 - (skill_raw(p,"overall_durability") - 75) * .003)
    factor = 1 - loss * (.15 if attr in ("speed","acceleration","speed_with_ball","agility","vertical") else .095)
    return getattr(p, attr) * factor

def weighted_choice(rng, items, weights):
    return rng.choices(items, weights=[max(.001, x) for x in weights], k=1)[0]

def select_creator(rng, team):
    return weighted_choice(rng, list(range(5)), [
        math.exp((.26*skill(p,"ball_handle")+.27*skill(p,"pass_iq")+.12*skill(p,"pass_vision")
                  +.20*skill(p,"shot_iq")+.15*skill(p,"pass_accuracy")-75)/12)
        for p in team])

def choose_action(rng, p, pressure, rim_open, memory, key, tactics):
    # Shot IQ makes a player more likely to recognize an unfavorable shot.
    vision = skill(p,"shot_iq")
    three = max(.05, .26+(skill(p,"three_point")-75)*.006+(vision-75)*.002-pressure*.003)
    drive = max(.05, .26+(skill(p,"ball_handle")-75)*.004
                +(skill(p,"acceleration")-75)*.003+(vision-75)*.001
                +(rim_open-50)*.002)
    post = max(.02, .11+(skill(p,"post_control")-75)*.006
               +(skill(p,"strength")-75)*.002)
    passing = max(.05, .27+(skill(p,"pass_iq")-75)*.006+pressure*.002)
    mid = max(.02, .10+(skill(p,"mid_range")-75)*.005)
    weights = [three, drive, post, passing, mid]
    # Tactical preference changes action selection, not shooting percentage.
    for idx, name in enumerate(("three","drive","post","pass","mid")):
        weights[idx] *= clamp(tactics.get(name,1.0),.3,2.5)
        # Repetition gives the defense an anticipatory advantage; IQ can counter.
        repeats = memory.actions[(key,name)]
        weights[idx] *= max(.60,1-.025*min(12,repeats)*(vision/100))
    return weighted_choice(rng, ["three","drive","post","pass","mid"], weights)

def defender_pressure(attacker, defender, zone, delay, anticipated=False):
    base = {"three":28, "mid":49, "rim":64}[zone]
    quality = (skill(defender,"perimeter_defense") if zone=="three" else
               skill(defender,"interior_defense") if zone=="rim" else
               .5*(skill(defender,"perimeter_defense")+skill(defender,"interior_defense")))
    fatigue = (100-defender.energy)*.19
    return clamp(base + (quality-75)*.44 + (skill(defender,"defensive_iq")-75)*.08 + (skill(defender,"defensive_consistency")-75)*.06
                 - delay*.68 - fatigue + (11 if anticipated else 0))

def execute_pass(rng, passer, target, pressure, delay, events):
    difficulty = pressure*.30 + max(0, 65-skill(passer,"pass_iq"))*.15
    execution = .985 - difficulty*.0024 + (skill(passer,"pass_accuracy")-75)*.0021 + (skill(target,"hands")-75)*.00055
    if not chance(rng,execution):
        events.append("pass intercepted or lost")
        return False, 0
    # Slower/inaccurate deliveries give defenders time to recover.
    recovered = clamp(13+(100-skill(passer,"pass_accuracy"))*.28
                      +(100-skill(passer,"pass_iq"))*.11, 5, 55)
    events.append(f"pass to {target.name}, defense recovers {recovered:.0f}")
    return True, recovered

def resolve_shot(rng, p, defender, zone, delay, events, anticipated=False):
    pressure = defender_pressure(p,defender,zone,delay,anticipated)
    if zone=="three":
        rating = skill(p,"three_point"); base=.355
    elif zone=="mid":
        rating = skill(p,"mid_range"); base=.435
    else:
        rating = .42*skill(p,"close_shot")+.40*skill(p,"driving_layup") + .18*skill(p,"driving_dunk")
        base=.60
    # Post hooks/fades, standing dunks and finishing touch matter at the rim.
    if zone=="rim":
        rating = (.36*skill(p,"close_shot")+.30*skill(p,"driving_layup")
                  +.12*skill(p,"driving_dunk")+.08*skill(p,"standing_dunk")
                  +.07*skill(p,"post_hook")+.07*skill(p,"post_fade"))
    composure = .6*skill(p,"offensive_consistency")+.4*skill(p,"intangibles")
    probability = clamp(base + (rating-75)*.0042 - (pressure-40)*.0034
                        + (composure-75)*.00045, .07, .88)
    made = chance(rng,probability)
    events.append(f"{p.name} {zone} pressure={pressure:.0f} p={probability:.3f} made={made}")
    return made, 3 if zone=="three" else 2

def choose_help(rng, defenders, on_ball, memory, key, drive_threat, tactics):
    # More dangerous penetration creates more help; high IQ improves rotations.
    candidates=[j for j in range(5) if j!=on_ball]
    helper=max(candidates,key=lambda j: .6*skill(defenders[j],"interior_defense")
               +.4*skill(defenders[j],"defensive_iq"))
    d=defenders[helper]
    propensity = .18 + (drive_threat-70)*.006 + (skill(d,"defensive_iq")-75)*.002
    propensity *= clamp(tactics.get("help",1),.3,2)
    return helper if chance(rng,propensity) else None

def simulate_possession(offense, defense, rng=None, memory=None,
                        offense_id="home", offense_tactics=None, defense_tactics=None,
                        max_actions=6):
    if len(offense)!=5 or len(defense)!=5:
        raise ValueError("Exactly five offensive and five defensive players required")
    rng=rng or random.Random()
    memory=memory if memory is not None else GameMemory()
    ot=offense_tactics or {}
    dt=defense_tactics or {}
    result=PossessionResult()
    state=DefenseState()
    holder=select_creator(rng,offense)
    last_passer=None
    advantage=0.
    for step in range(max_actions):
        p=offense[holder]
        defender=defense[state.matchups[holder]]
        key=(offense_id,holder)
        anticipation=min(.85, memory.actions[(key,"drive")]*.035)
        pressure=defender_pressure(p,defender,"three",state.delay.get(holder,0))
        action=choose_action(rng,p,pressure,advantage,memory,key,ot)
        memory.actions[(key,action)]+=1
        result.events.append(f"{p.name}: {action}")
        if action=="drive":
            ability=.32*skill(p,"ball_handle")+.22*skill(p,"speed")+.22*skill(p,"acceleration")+.14*skill(p,"strength")+.10*skill(p,"shot_iq")
            resistance=.55*skill(defender,"perimeter_defense")+.25*skill(defender,"speed")+.20*skill(defender,"defensive_iq")
            p_drive=clamp(.49+(ability-resistance)*.012-anticipation*.20,.06,.89)
            if not chance(rng,p_drive):
                result.events.append("drive contained")
                advantage=-15
                if chance(rng,.10+(pressure/100)*.09):
                    result.turnovers=1;result.outcome="turnover";return result
                continue
            result.events.append("defender beaten")
            advantage=40
            helper=choose_help(rng,defense,state.matchups[holder],memory,key,ability,dt)
            if helper is not None:
                state.help_count+=1
                result.events.append(f"help by {defense[helper].name}")
                # The helper abandons the player they were guarding.
                freed=next((i for i,j in state.matchups.items() if j==helper),None)
                if freed is not None:
                    d=defense[helper]
                    state.delay[freed]=clamp(48+(100-skill(d,"speed"))*.30
                        +(100-skill(d,"defensive_iq"))*.18+(100-d.energy)*.20)
                # Help raises pressure on the driver, lowering rim efficiency.
                help_pressure=22
            else:
                help_pressure=0
            # IQ governs recognition of the open teammate, accuracy executes.
            open_targets=[i for i in state.delay if i!=holder and state.delay[i]>22]
            see_open=bool(open_targets) and chance(rng,clamp(.24+skill(p,"pass_iq")*.006,0,.95))
            if see_open:
                target=max(open_targets,key=lambda i: state.delay[i]+(skill(offense[i],"three_point")-75)*.35)
                ok,recovered=execute_pass(rng,p,offense[target],pressure+help_pressure,
                                          state.delay[target],result.events)
                if not ok:
                    result.turnovers=1;result.outcome="turnover";return result
                state.delay[target]=max(0,state.delay[target]-recovered)
                last_passer=p.name;holder=target
                # Receiver gets immediate opportunity before defense fully recovers.
                zone="three" if skill(offense[target],"three_point")>=skill(offense[target],"mid_range") else "mid"
                made,pts=resolve_shot(rng,offense[target],defense[state.matchups[target]],
                                      zone,state.delay[target],result.events)
                result.shooter=offense[target].name
                if made:
                    result.points=pts;result.outcome="made";result.assists=1;result.passer=last_passer
                else:
                    result.outcome="miss"
                return result
            # Interior shot: successful penetration reduces primary pressure, help adds it back.
            primary_delay=clamp(50-help_pressure)
            made,pts=resolve_shot(rng,p,defender,"rim",primary_delay,result.events)
            if helper is not None:
                # Extra rim contest by helper, independent of primary defender.
                if made and chance(rng,clamp(.06+(skill(defense[helper],"interior_defense")-75)*.002,0,.20)):
                    made=False;result.events.append("help contest changed shot")
            result.shooter=p.name;result.points=pts if made else 0
            result.outcome="made" if made else "miss"
            return result
        if action=="pass":
            candidates=[i for i in range(5) if i!=holder]
            # Pass IQ finds better opportunities, but never guarantees the best one.
            scores=[(skill(offense[i],"three_point")*.35+skill(offense[i],"shot_iq")*.20
                     +state.delay.get(i,0)*.45) for i in candidates]
            awareness=skill(p,"pass_iq")/100
            target=weighted_choice(rng,candidates,[math.exp((v-55)*awareness/18) for v in scores])
            ok,recovered=execute_pass(rng,p,offense[target],pressure,
                                      state.delay.get(target,0),result.events)
            if not ok:
                result.turnovers=1;result.outcome="turnover";return result
            state.delay[target]=max(0,state.delay.get(target,0)-recovered)
            holder=target;last_passer=p.name
        else:
            zone={"three":"three","mid":"mid","post":"rim"}[action]
            # Post control and strength must earn an interior position.
            delay=state.delay.get(holder,0)
            if action=="post":
                contest=.55*skill(defender,"interior_defense")+.45*skill(defender,"strength")
                post_ability=.65*skill(p,"post_control")+.35*skill(p,"strength")
                delay=clamp((post_ability-contest)*1.2-10,0,65)
            made,pts=resolve_shot(rng,p,defender,zone,delay,result.events,
                                  anticipated=memory.actions[(key,action)]>5)
            result.shooter=p.name
            result.points=pts if made else 0
            result.outcome="made" if made else "miss"
            if made and last_passer and last_passer!=p.name:
                result.assists=1;result.passer=last_passer
            return result
        # Passing consumes time: defenders recover, and the next action has less space.
        for i in state.delay:
            state.delay[i]=max(0,state.delay[i]-12)
    result.events.append("shot clock violation")
    result.turnovers=1
    return result

def simulate_game(home, away, seed=0, possessions_per_team=100, tactics=None):
    """Alternating possessions; compact prototype, not yet NBA-calibrated."""
    rng=random.Random(seed)
    memory=GameMemory()
    scores=[0,0]
    stats=[Counter(),Counter()]
    teams=[home,away]
    for _ in range(possessions_per_team):
        for side in (0,1):
            off,defense=teams[side],teams[1-side]
            r=simulate_possession(off,defense,rng,memory,str(side),
                (tactics or {}).get(side,{}).get("offense",{}),
                (tactics or {}).get(1-side,{}).get("defense",{}))
            scores[side]+=r.points
            stats[side][r.outcome]+=1
            stats[side]["assists"]+=r.assists
            stats[side]["turnovers"]+=r.turnovers
            stats[side]["offensive_rebounds"]+=r.offensive_rebounds
            stats[side]["fouls_drawn"]+=r.fouls_drawn
            stats[side]["offensive_fouls"]+=r.offensive_fouls
            stats[side]["free_throws_attempted"]+=r.free_throws_attempted
            stats[side]["free_throws_made"]+=r.free_throws_made
            # Fatigue depends on actual actions and stamina; recovery is outside scope.
            for p in off+defense:
                p.energy=clamp(p.energy-(.12+(100-p.stamina)*.001),45,100)
    return {"score":tuple(scores),"stats":tuple(dict(s) for s in stats)}

# V2 action/reaction layer supersedes the initial simple possession resolver.
# Import after all shared types/helpers to avoid circular initialization issues.
from engine_v2_actions import simulate_possession  # noqa: E402,F811
