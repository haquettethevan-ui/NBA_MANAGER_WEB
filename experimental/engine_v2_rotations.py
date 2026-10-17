"""Pre-match 48-minute rotation and stamina simulation for the isolated V2 engine.

Rotation is a list of 48 minute-long lineups, each containing five roster indices
in PG, SG, SF, PF, C order. No substitutions are decided during the match.
"""
from collections import Counter
import random
from engine_v2 import GameMemory, clamp, simulate_possession

POSITIONS = ("PG", "SG", "SF", "PF", "C")
MINUTES = 48

def validate_rotation(roster, rotation):
    if len(roster) < 5:
        raise ValueError("At least five players required")
    if len(rotation) != MINUTES:
        raise ValueError("Rotation must cover exactly 48 minutes")
    for minute, lineup in enumerate(rotation):
        if len(lineup) != 5 or len(set(lineup)) != 5:
            raise ValueError(f"Minute {minute}: exactly five distinct players required")
        for slot, index in enumerate(lineup):
            if not isinstance(index, int) or not 0 <= index < len(roster):
                raise ValueError(f"Minute {minute}: invalid roster index {index}")
            eligible = {p.strip().upper() for p in roster[index].position.replace("-", "/").split("/")}
            if POSITIONS[slot] not in eligible:
                raise ValueError(f"Minute {minute}: {roster[index].name} cannot play {POSITIONS[slot]}")
    return True

def rotation_from_minutes(roster, minutes):
    """Build a valid fixed rotation from exact player minute targets.

    Player minutes are an integer list totalling 240. A player may occupy only
    eligible positions. Greedy per-minute assignments are backtracked when needed.
    """
    if len(minutes) != len(roster) or any(type(m) is not int or m < 0 or m > 48 for m in minutes):
        raise ValueError("Provide one integer target in [0,48] per player")
    if sum(minutes) != 240:
        raise ValueError("Player minutes must total 240")
    eligible = [
        {p.strip().upper() for p in player.position.replace("-", "/").split("/")}
        for player in roster
    ]
    # Flow network: source -> player (minutes) -> position (eligible) -> sink (48).
    # Integral max flow yields exact per-position minute allocations.
    n=len(roster)
    source=n+5; sink=source+1
    capacity={}
    adjacency=[set() for _ in range(sink+1)]
    def edge(a,b,cap):
        capacity[a,b]=cap; capacity[b,a]=0
        adjacency[a].add(b); adjacency[b].add(a)
    for i,m in enumerate(minutes):
        edge(source,i,m)
        for j,pos in enumerate(POSITIONS):
            if pos in eligible[i]:
                edge(i,n+j,48)
    for j in range(5):
        edge(n+j,sink,48)
    flow=0
    while True:
        parent={source:None}
        queue=[source]
        for node in queue:
            for nxt in sorted(adjacency[node]):
                if nxt not in parent and capacity[node,nxt]>0:
                    parent[nxt]=node
                    queue.append(nxt)
            if sink in parent: break
        if sink not in parent: break
        bottleneck=10**9; node=sink
        while parent[node] is not None:
            prev=parent[node]; bottleneck=min(bottleneck,capacity[prev,node]); node=prev
        node=sink
        while parent[node] is not None:
            prev=parent[node]; capacity[prev,node]-=bottleneck
            capacity[node,prev]+=bottleneck
            node=prev
        flow+=bottleneck
    if flow!=240:
        raise ValueError("Minute targets cannot cover all five positions")
    # Each position has 48 assigned minutes. Construct a minute-by-minute
    # schedule without placing one player twice in the same minute.
    allocations=[[capacity[n+j,i] if (n+j,i) in capacity else 0 for j in range(5)] for i in range(n)]
    rotation=[]
    for minute in range(48):
        used=set(); lineup=[]
        for slot in range(5):
            candidates=[i for i in range(n) if i not in used and allocations[i][slot]>0]
            if not candidates:
                raise ValueError("Minute allocation cannot form distinct five-player lineups")
            i=max(candidates,key=lambda k:(allocations[k][slot],-k))
            lineup.append(i);used.add(i);allocations[i][slot]-=1
        rotation.append(lineup)
    validate_rotation(roster,rotation)
    return rotation

def simulate_rotated_game(home,away,home_rotation,away_rotation,seed=0,possessions_per_team=100,tactics=None):
    """Simulate a full 48-minute match with scheduled lineups and bench recovery.

    Does not mutate the input rosters' energy. Match pacing is approximate;
    possession-level action times are not yet coupled to the game clock.
    """
    validate_rotation(home,home_rotation)
    validate_rotation(away,away_rotation)
    from dataclasses import replace
    teams=[[replace(p) for p in home],[replace(p) for p in away]]
    schedules=[home_rotation,away_rotation]
    rng=random.Random(seed);memory=GameMemory()
    scores=[0,0];stats=[Counter(),Counter()]
    played=[[0]*len(team) for team in teams]
    energy_trace=[[],[]]
    for minute in range(48):
        active=[set(schedules[s][minute]) for s in (0,1)]
        # Continuous on-court exertion and bench recovery each minute.
        for s in (0,1):
            for i,p in enumerate(teams[s]):
                if i in active[s]:
                    played[s][i]+=1
                    p.energy=clamp(p.energy-(1.15+(100-p.stamina)*.018),35,100)
                else:
                    p.energy=clamp(p.energy+(1.6+p.stamina*.014),35,100)
            energy_trace[s].append(round(sum(teams[s][i].energy for i in active[s])/5,2))
        # Distribute all possessions deterministically across the 48 minutes.
        begin=minute*possessions_per_team//48
        end=(minute+1)*possessions_per_team//48
        for _ in range(begin,end):
            for s in (0,1):
                off=[teams[s][i] for i in schedules[s][minute]]
                defense=[teams[1-s][i] for i in schedules[1-s][minute]]
                result=simulate_possession(off,defense,rng,memory,str(s),
                    (tactics or {}).get(s,{}).get("offense",{}),
                    (tactics or {}).get(1-s,{}).get("defense",{}))
                scores[s]+=result.points
                stats[s][result.outcome]+=1
                for field in ("assists","turnovers","offensive_rebounds","fouls_drawn",
                              "offensive_fouls","free_throws_attempted","free_throws_made"):
                    stats[s][field]+=getattr(result,field)
    return {"score":tuple(scores),"stats":tuple(dict(x) for x in stats),
            "minutes":tuple(tuple(x) for x in played),
            "final_energy":tuple(tuple(round(p.energy,2) for p in team) for team in teams),
            "on_court_energy_by_minute":tuple(energy_trace)}
