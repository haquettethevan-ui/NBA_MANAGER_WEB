"""V2 offensive/defensive action layer (experimental, independent of production).

Abstract spacing, no player coordinates. This module is imported by engine_v2
after Player, GameMemory and utility functions have been defined.
"""
from dataclasses import dataclass, field
from engine_v2_rules import shooting_foul, free_throws, rebound
import math
from engine_v2 import (
    clamp, chance, skill, weighted_choice, select_creator, defender_pressure,
    resolve_shot, execute_pass, PossessionResult, GameMemory,
)

ACTIONS = ("three", "mid", "drive", "post", "pass", "screen", "cut", "handoff")
REACTIONS = ("contain", "help", "switch", "rotate", "contest", "steal", "block")

@dataclass
class CourtState:
    matchups: dict = field(default_factory=lambda: {i:i for i in range(5)})
    delays: dict = field(default_factory=lambda: {i:0. for i in range(5)})
    # Defender temporarily providing help on the ball, and his original matchup.
    helper: int | None = None
    ball_pressure: float = 0.
    advantage: float = 0.
    screen_bonus: float = 0.
    paint_access: bool = False
    last_passer: str | None = None
    last_receiver: int | None = None
    possession_clock: int = 24

def defender_for(state, offense_index):
    return state.matchups[offense_index]

def _decay(state, defense, ticks=2):
    state.possession_clock -= ticks
    for i in range(5):
        d=defense[state.matchups[i]]
        recovery=4.5 + skill(d,"speed")*.085 + skill(d,"defensive_iq")*.05
        state.delays[i]=max(0.,state.delays[i]-recovery*ticks/2)
    state.screen_bonus=max(0,state.screen_bonus-9*ticks/2)

def _pressure(state, offense, defense, holder, zone="three", anticipated=False):
    d=defense[defender_for(state,holder)]
    value=defender_pressure(offense[holder],d,zone,state.delays[holder],anticipated)
    if state.helper is not None and zone=="rim":
        value+=18+(skill(defense[state.helper],"interior_defense")-75)*.12
    return clamp(value)

def _pick_action(rng,p,pressure,state,tactics,memory,key):
    # IQ helps players avoid contested shots and spot open teammates.
    vision=skill(p,"shot_iq")
    free=max(state.delays.values())
    weights={
        "three":.22+(skill(p,"three_point")-75)*.005-(pressure-30)*.0025,
        "mid":.12+(skill(p,"mid_range")-75)*.004-(pressure-30)*.001,
        "drive":.22+(skill(p,"ball_handle")-75)*.004+(skill(p,"acceleration")-75)*.003,
        "post":.10+(skill(p,"post_control")-75)*.004,
        "pass":.20+(skill(p,"pass_iq")-75)*.004+free*.003,
        "screen":.10+(skill(p,"pass_iq")-75)*.001,
        "cut":.10+(skill(p,"speed")-75)*.002,
        "handoff":.07+(skill(p,"pass_accuracy")-75)*.002,
    }
    if state.paint_access:
        weights["drive"]*=.25
        weights["pass"]*=1.5
    for action in ACTIONS:
        repeats=memory.actions[(key,action)]
        weights[action]=max(.012,weights[action])
        weights[action]*=clamp(tactics.get(action,1),.2,3)
        weights[action]*=max(.65,1-.018*min(15,repeats))
    return weighted_choice(rng,ACTIONS,[weights[a] for a in ACTIONS])

def _anticipation(memory,key,action,defender):
    repeats=memory.actions[(key,action)]
    return clamp(repeats*.028*(skill(defender,"defensive_iq")/75),0,.38)

def _choose_help(rng,state,defense,holder,tactics):
    available=[j for j in range(5) if j!=defender_for(state,holder)]
    # Prioritize help defender who protects the rim, while preserving a tradeoff.
    j=max(available,key=lambda k:.55*skill(defense[k],"interior_defense")
          +.45*skill(defense[k],"defensive_iq"))
    d=defense[j]
    p=clamp(.30+(skill(d,"defensive_iq")-75)*.003,0,.8)
    p*=clamp(tactics.get("help",1),.2,2.0)
    if not chance(rng,p):
        return None
    state.helper=j
    freed=next(i for i,k in state.matchups.items() if k==j)
    state.delays[freed]=clamp(state.delays[freed]+48+(100-skill(d,"speed"))*.17)
    return freed

def _rotate(rng,state,defense,freed,tactics,events):
    # A third defender can rotate to the open man, exposing his own assignment.
    if freed is None or not chance(rng,clamp(.23*tactics.get("rotate",1),0,.75)):
        return
    candidates=[i for i in range(5) if i!=freed and state.matchups[i]!=state.helper]
    cover=max(candidates,key=lambda i:skill(defense[state.matchups[i]],"defensive_iq"))
    defender=defense[state.matchups[cover]]
    quality=(skill(defender,"defensive_iq")+skill(defender,"speed"))/2
    if not chance(rng,clamp(.38+(quality-75)*.006,.08,.85)):
        events.append("defense: rotation late")
        return
    state.delays[freed]=max(0,state.delays[freed]-31)
    state.delays[cover]=clamp(state.delays[cover]+40)
    events.append(f"defense: rotate to {freed}, leave {cover} exposed")

def _pass_target(rng,offense,state,holder,passer):
    choices=[i for i in range(5) if i!=holder]
    iq=skill(passer,"pass_iq")
    # Low IQ approaches random; high IQ prefers useful space and a capable receiver.
    weights=[]
    for i in choices:
        receiver=offense[i]
        quality=state.delays[i]*.9 + .15*max(skill(receiver,"three_point"),
                    skill(receiver,"mid_range"),skill(receiver,"close_shot"))
        weights.append(math.exp((quality-18)*(iq/100)/22))
    return weighted_choice(rng,choices,weights)

def _steal(rng,defender,handler,pressure,events):
    prob=clamp(.012+(skill(defender,"perimeter_defense")-75)*.0006
               +(skill(defender,"defensive_iq")-75)*.00035
               +(pressure-35)*.00035-(skill(handler,"ball_handle")-75)*.0004,0,.12)
    if chance(rng,prob):
        events.append(f"defense: steal by {defender.name}")
        return True
    return False

def _shot(rng,offense,defense,state,holder,zone,result,memory,key):
    attacker=offense[holder]
    defender=defense[defender_for(state,holder)]
    anticipated=_anticipation(memory,key,zone,defender)>.15
    delay=state.delays[holder]+(state.advantage if zone=="rim" else 0)
    made,points=resolve_shot(rng,attacker,defender,zone,clamp(delay),result.events,anticipated)
    helper=defense[state.helper] if state.helper is not None and zone=="rim" else None
    if helper is not None:
        block_p=clamp(.035+(skill(helper,"interior_defense")-75)*.0015
                      +(skill(helper,"vertical")-75)*.0007,0,.14)
        if made and chance(rng,block_p):
            made=False
            result.events.append(f"defense: block by {helper.name}")
    result.shooter=attacker.name
    # Foul is resolved independently of shot success (and-one possible).
    foul=shooting_foul(rng,attacker,defender,helper,zone,result.events)
    if foul:
        result.fouls_drawn+=1
        result.fouled_by=foul
        attempts=1 if made else (3 if zone=="three" else 2)
        result.free_throws_attempted+=attempts
        ft=free_throws(rng,attacker,attempts,result.events)
        result.free_throws_made+=ft
        result.points=(points if made else 0)+ft
        result.outcome="made" if made else "foul"
        if made and state.last_passer and state.last_passer!=attacker.name:
            result.assists=1
            result.passer=state.last_passer
        # Missed last free throw rebounds deferred to complete match rules.
        return result
    if made:
        result.points=points
        result.outcome="made"
        if state.last_passer and state.last_passer!=attacker.name:
            result.assists=1
            result.passer=state.last_passer
        return result
    # A missed field goal is not a completed possession until rebound.
    for second_chance in range(2):
        offensive,boarder=rebound(rng,offense,defense,result.events)
        if not offensive:
            result.outcome="miss"
            return result
        result.offensive_rebounds+=1
        rebounder=offense[boarder]
        # Reset shot clock to 14 on an offensive rebound.
        state.possession_clock=14
        state.last_passer=None
        result.events.append("rules: shot clock reset to 14")
        # Quick putback vs defense; no direct bonus to field goal rating.
        defender2=defense[defender_for(state,boarder)]
        putback,pts=resolve_shot(rng,rebounder,defender2,"rim",20,result.events)
        result.shooter=rebounder.name
        if putback:
            result.points=pts
            result.outcome="made"
            return result
    # Cap consecutive putbacks to keep the prototype bounded.
    rebound(rng,offense,defense,result.events)
    result.outcome="miss"
    return result

def simulate_possession(offense,defense,rng=None,memory=None,offense_id="home",
                        offense_tactics=None,defense_tactics=None,max_actions=9):
    if len(offense)!=5 or len(defense)!=5:
        raise ValueError("Exactly five offensive and five defensive players required")
    import random
    rng=rng if rng is not None else random.Random()
    memory=memory if memory is not None else GameMemory()
    ot=offense_tactics or {}
    dt=defense_tactics or {}
    result=PossessionResult()
    state=CourtState()
    holder=select_creator(rng,offense)
    for _ in range(max_actions):
        if state.possession_clock<=0:
            break
        p=offense[holder]
        defender=defense[defender_for(state,holder)]
        key=(offense_id,holder)
        pressure=_pressure(state,offense,defense,holder)
        action=_pick_action(rng,p,pressure,state,ot,memory,key)
        memory.actions[(key,action)]+=1
        result.events.append(f"offense: {p.name} {action}")
        _decay(state,defense,2)
        if _steal(rng,defender,p,pressure,result.events):
            result.turnovers=1;result.outcome="turnover";return result
        if action in ("three","mid"):
            return _shot(rng,offense,defense,state,holder,action,result,memory,key)
        if action=="drive":
            attack=(.32*skill(p,"ball_handle")+.22*skill(p,"speed")
                    +.21*skill(p,"acceleration")+.15*skill(p,"strength")
                    +.10*skill(p,"shot_iq"))
            stop=(.52*skill(defender,"perimeter_defense")+.23*skill(defender,"speed")
                  +.25*skill(defender,"defensive_iq"))
            anticipated=_anticipation(memory,key,"drive",defender)
            success=clamp(.49+(attack-stop)*.012-anticipated*.27
                          +state.screen_bonus*.004,.06,.90)
            if not chance(rng,success):
                result.events.append("defense: contain drive")
                state.advantage=0
                if chance(rng,clamp(.045+(pressure-25)*.0015,0,.18)):
                    result.events.append("offense: lost handle")
                    result.turnovers=1;result.outcome="turnover";return result
                continue
            result.events.append("offense: beat primary defender")
            state.paint_access=True
            state.advantage=42
            freed=_choose_help(rng,state,defense,holder,dt)
            if freed is not None:
                result.events.append(f"defense: help by {defense[state.helper].name}")
                _rotate(rng,state,defense,freed,dt,result.events)
                # Smart handler reads help, but can choose to finish.
                target=_pass_target(rng,offense,state,holder,p)
                pass_value=state.delays[target]*.7+(skill(p,"pass_iq")-75)*.3
                if chance(rng,clamp(.18+pass_value*.007,.06,.85)):
                    ok,recovery=execute_pass(rng,p,offense[target],
                                              pressure+15,state.delays[target],result.events)
                    if not ok:
                        result.turnovers=1;result.outcome="turnover";return result
                    state.delays[target]=max(0,state.delays[target]-recovery)
                    state.last_passer=p.name
                    holder=target
                    state.paint_access=False
                    state.advantage=0
                    state.helper=None
                    continue
            return _shot(rng,offense,defense,state,holder,"rim",result,memory,key)
        if action=="post":
            post=.65*skill(p,"post_control")+.35*skill(p,"strength")
            contest=.55*skill(defender,"interior_defense")+.45*skill(defender,"strength")
            gain=clamp((post-contest)*1.4+state.screen_bonus*.3,0,65)
            if chance(rng,clamp(.50+(post-contest)*.012,.06,.88)):
                state.advantage=gain+15
                state.paint_access=True
                freed=_choose_help(rng,state,defense,holder,dt)
                if freed is not None:
                    result.events.append("defense: help on post")
                    _rotate(rng,state,defense,freed,dt,result.events)
                return _shot(rng,offense,defense,state,holder,"rim",result,memory,key)
            result.events.append("defense: deny post position")
            continue
        if action=="screen":
            screener=max((i for i in range(5) if i!=holder),
                         key=lambda i:skill(offense[i],"strength"))
            setter=offense[screener]
            opponent=defense[defender_for(state,screener)]
            success=clamp(.52+(skill(setter,"strength")-skill(opponent,"defensive_iq"))*.008,.1,.85)
            if chance(rng,success):
                state.screen_bonus=clamp(state.screen_bonus+32)
                state.delays[holder]=clamp(state.delays[holder]+25)
                result.events.append(f"offense: screen set by {setter.name}")
                switch_p=clamp(.25+(skill(defender,"defensive_iq")-75)*.004,.05,.7)
                switch_p*=clamp(dt.get("switch",1),.2,2)
                if chance(rng,switch_p):
                    state.matchups[holder],state.matchups[screener]=(
                        state.matchups[screener],state.matchups[holder])
                    state.delays[holder]=max(0,state.delays[holder]-18)
                    result.events.append("defense: switch screen")
            else:
                result.events.append("defense: navigate screen")
            continue
        if action=="cut":
            cutter=max((i for i in range(5) if i!=holder),
                       key=lambda i:.55*skill(offense[i],"speed")
                           +.45*skill(offense[i],"acceleration"))
            receiver=offense[cutter]
            d=defense[defender_for(state,cutter)]
            chance_open=clamp(.42+(skill(receiver,"speed")-skill(d,"speed"))*.009
                              +(skill(p,"pass_iq")-75)*.003,.07,.86)
            if chance(rng,chance_open):
                state.delays[cutter]=clamp(state.delays[cutter]+42)
                result.events.append(f"offense: {receiver.name} cuts open")
                ok,recovery=execute_pass(rng,p,receiver,pressure,state.delays[cutter],result.events)
                if not ok:
                    result.turnovers=1;result.outcome="turnover";return result
                state.delays[cutter]=max(0,state.delays[cutter]-recovery)
                state.last_passer=p.name
                holder=cutter
                state.paint_access=True
                state.advantage=28
                # A cut creates access to the rim, not a guaranteed basket.
                freed=_choose_help(rng,state,defense,holder,dt)
                if freed is not None:
                    result.events.append("defense: help on cutter")
                    _rotate(rng,state,defense,freed,dt,result.events)
                return _shot(rng,offense,defense,state,holder,"rim",result,memory,key)
            result.events.append("defense: deny cut")
            continue
        if action in ("pass","handoff"):
            target=_pass_target(rng,offense,state,holder,p)
            receiver=offense[target]
            if action=="handoff":
                state.delays[target]=clamp(state.delays[target]+18)
                result.events.append("offense: dribble handoff")
                # A switch can neutralize the handoff.
                if chance(rng,clamp(.18*dt.get("switch",1),0,.65)):
                    state.matchups[holder],state.matchups[target]=(
                        state.matchups[target],state.matchups[holder])
                    state.delays[target]=max(0,state.delays[target]-13)
                    result.events.append("defense: switch handoff")
            ok,recovery=execute_pass(rng,p,receiver,pressure,state.delays[target],result.events)
            if not ok:
                result.turnovers=1;result.outcome="turnover";return result
            state.delays[target]=max(0,state.delays[target]-recovery)
            state.last_passer=p.name
            state.paint_access=False
            state.advantage=0
            state.helper=None
            holder=target
            continue
    result.events.append("offense: shot clock violation")
    result.turnovers=1
    result.outcome="turnover"
    return result
