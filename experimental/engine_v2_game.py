"""Experimental V2 regulation-game orchestration.

Uses the existing possession simulator. No changes to the legacy engine.
A time-based game with five positions, bench substitutions, recovery, team
foul bonus, foul-outs and overtime. Probabilities are not calibrated.
"""
from dataclasses import dataclass, field
from collections import Counter
import random
from engine_v2 import clamp, GameMemory
from engine_v2_actions import simulate_possession
from engine_v2_rules import free_throws

POSITIONS=("PG","SG","SF","PF","C")
PERIOD_SECONDS=720

@dataclass
class TeamState:
    roster: list
    # Desired court minutes for each player, optionally specified by player name.
    target_minutes: dict = field(default_factory=dict)
    fouls: Counter = field(default_factory=Counter)
    team_fouls: int = 0
    score: int = 0
    stats: Counter = field(default_factory=Counter)
    seconds_played: Counter = field(default_factory=Counter)
    active: list = field(default_factory=list)

    def __post_init__(self):
        if len(self.roster)<5:
            raise ValueError("At least five players required")
        if len({p.name for p in self.roster})!=len(self.roster):
            raise ValueError("Player names must be unique within a team")
        self.active=self._lineup()

    def _lineup(self):
        eligible=[p for p in self.roster if self.fouls[p.name]<6]
        if len(eligible)<5:
            # NBA rules permit a disqualified player to stay with technical
            # penalties when no legal substitute remains; not modeled here.
            raise ValueError("Fewer than five eligible players; emergency foul-out rule not modeled")
        selected=[]
        for pos in POSITIONS:
            candidates=[p for p in eligible if p not in selected]
            def priority(p):
                target=self.target_minutes.get(p.name,32)
                remaining=target*60-self.seconds_played[p.name]
                position_bonus=1500 if p.position==pos else 0
                return remaining+position_bonus+p.energy*3
            selected.append(max(candidates,key=priority))
        return selected

    def substitute(self):
        self.active=self._lineup()
        return self.active

    def rest(self,seconds):
        on={p.name for p in self.active}
        for p in self.roster:
            if p.name not in on:
                p.energy=clamp(p.energy+seconds*.07,0,100)

    def play(self,seconds):
        for p in self.active:
            self.seconds_played[p.name]+=seconds
            p.energy=clamp(p.energy-seconds*(.013+(100-p.stamina)*.00008),35,100)

def _period_bonus(team,period,remaining):
    # Regulation: 5th team foul; last 2 minutes: second team foul.
    # Overtime: 4th team foul; last 2 minutes: second team foul.
    threshold=4 if period<=4 else 3
    return team.team_fouls>=threshold or (remaining<=120 and team.team_fouls>=1)

def simulate_regulation_game(home,away,seed=0,home_minutes=None,away_minutes=None,
                             home_tactics=None,away_tactics=None,max_overtimes=5):
    """Play 4 x 12 minutes and optional 5-minute overtimes.

    The simulator advances a possession by its abstract action count, capped
    by the remaining period time. Rotation uses requested target minutes as a
    heuristic, not an exact per-minute lineup timeline.
    """
    rng=random.Random(seed)
    teams=[TeamState(list(home),home_minutes or {}),TeamState(list(away),away_minutes or {})]
    memory=GameMemory()
    timeline=[]
    period=0
    while period<4 or (teams[0].score==teams[1].score and period<4+max_overtimes):
        period+=1
        remaining=PERIOD_SECONDS if period<=4 else 300
        for t in teams:
            t.team_fouls=0
            t.substitute()
        offense=(period-1)%2
        while remaining>0:
            attacking=teams[offense]
            defending=teams[1-offense]
            attacking.substitute()
            defending.substitute()
            tactics=(home_tactics or {}) if offense==0 else (away_tactics or {})
            defensive_tactics=(away_tactics or {}) if offense==0 else (home_tactics or {})
            result=simulate_possession(attacking.active,defending.active,rng,memory,
                 offense_id=str(offense),offense_tactics=tactics.get("offense",{}),
                 defense_tactics=defensive_tactics.get("defense",{}))
            # Possession duration is estimated from events until a richer
            # clock integration is available.
            action_count=sum(e.startswith("offense: ") and e.split()[-1] in
                ("three","mid","drive","post","pass","screen","cut","handoff")
                for e in result.events)
            elapsed=min(remaining,max(3,min(24,4+action_count*3)))
            remaining-=elapsed
            attacking.play(elapsed)
            defending.play(elapsed)
            attacking.score+=result.points
            attacking.stats[result.outcome]+=1
            attacking.stats["assists"]+=result.assists
            attacking.stats["turnovers"]+=result.turnovers
            attacking.stats["offensive_rebounds"]+=result.offensive_rebounds
            attacking.stats["free_throws_attempted"]+=result.free_throws_attempted
            attacking.stats["free_throws_made"]+=result.free_throws_made
            attacking.stats["offensive_fouls"]+=result.offensive_fouls
            if result.fouled_by:
                defending.fouls[result.fouled_by]+=1
                defending.team_fouls+=1
                defending.stats["personal_fouls"]+=1
                if defending.fouls[result.fouled_by]==6:
                    timeline.append((period,remaining,"foul out",result.fouled_by))
            if result.offensive_fouls:
                attacking.team_fouls+=result.offensive_fouls
                attacking.stats["personal_fouls"]+=result.offensive_fouls
            # Bonus free throws on non-shooting defensive fouls will be added
            # once off-ball defensive fouls exist; no invented fouls here.
            timeline.append((period,remaining,offense,result.points,result.outcome))
            attacking.rest(elapsed)
            defending.rest(elapsed)
            offense=1-offense
        timeline.append((period,0,"period end",tuple(t.score for t in teams)))
    return {
        "score":tuple(t.score for t in teams),
        "periods":period,
        "overtimes":max(0,period-4),
        "stats":tuple(dict(t.stats) for t in teams),
        "minutes":tuple({p.name:round(t.seconds_played[p.name]/60,2) for p in t.roster} for t in teams),
        "fouls":tuple(dict(t.fouls) for t in teams),
        "energy":tuple({p.name:round(p.energy,1) for p in t.roster} for t in teams),
        "timeline":timeline,
    }
