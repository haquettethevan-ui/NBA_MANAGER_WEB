"""Deterministic real-roster V2 smoke benchmark; no production imports.

Run: PYTHONPATH=experimental python experimental/test_real_games_v2.py
"""
import json
import random
from collections import Counter
from engine_v2_rosters import load_rosters
from engine_v2_rotations import POSITIONS, validate_rotation, simulate_rotated_game

MATCHUPS=(("BOS","NYK"),("OKC","DEN"),("LAL","GSW"),("PHI","SAS"),("CHI","ATL"))
SEEDS=(11,29,47)

def rotation_for(roster):
    """Plan staggered pre-match substitutions with real primary/secondary positions.

    Evaluate legal five-player lineups every three minutes, preferring stronger
    players but penalizing accumulated playing time and consecutive shifts.
    No substitutions occur in response to events during the simulated game.
    """
    eligible=[{p.strip().upper() for p in player.position.replace("-","/").split("/")}
              for player in roster]
    quality=[(p.three_point+p.close_shot+p.perimeter_defense+p.interior_defense)/4
             for p in roster]
    rank=sorted(range(len(roster)),key=lambda i:(-quality[i],i))
    # Limit the candidate pool but retain enough depth at each position.
    pool=set(rank[:12])
    for pos in POSITIONS:
        pool.update(i for i in rank if pos in eligible[i]][:3])
    candidates=[[i for i in rank if i in pool and pos in eligible[i]] for pos in POSITIONS]
    if any(not slot for slot in candidates):
        raise ValueError("Missing a legal player for a required position")
    played=[0]*len(roster)
    consecutive=[0]*len(roster)
    rotation=[]
    for minute in range(0,48,3):
        # Exhaustive five-position assignment (small roster), with explicit
        # one-player-per-slot constraint. Score is evaluated for this block.
        best=None
        best_score=float("-inf")
        def assign(slot,lineup,used,score):
            nonlocal best,best_score
            if slot==5:
                key=tuple(lineup)
                if score>best_score or (score==best_score and (best is None or key<tuple(best))):
                    best_score=score
                    best=list(lineup)
                return
            for i in candidates[slot]:
                if i in used:
                    continue
                # Penalize heavy minutes and long uninterrupted stints.
                value=quality[i]*0.12-played[i]*0.75-consecutive[i]*1.8
                assign(slot+1,lineup+[i],used|{i},score+value)
        assign(0,[],set(),0.0)
        if best is None:
            raise ValueError("No legal five-player lineup")
        rotation.extend([best[:] for _ in range(3)])
        active=set(best)
        for i in range(len(roster)):
            consecutive[i]=consecutive[i]+3 if i in active else 0
            if i in active:
                played[i]+=3
    validate_rotation(roster,rotation)
    used=sum(m>0 for m in played)
    return rotation,used>=8

def benchmark(rosters=None,seeds=SEEDS,matchups=MATCHUPS,possessions=100):
    rosters=rosters if rosters is not None else load_rosters()
    results=[]
    for home,away in matchups:
        h=rosters[home];a=rosters[away]
        hr,hbench=rotation_for(h);ar,abench=rotation_for(a)
        for seed in seeds:
            r=simulate_rotated_game(h,a,hr,ar,seed=seed,possessions_per_team=possessions)
            expected_h=Counter(i for minute in hr for i in minute)
            expected_a=Counter(i for minute in ar for i in minute)
            assert all(r["minutes"][0][i]==expected_h[i] for i in range(len(h)))
            assert all(r["minutes"][1][i]==expected_a[i] for i in range(len(a)))
            assert all(35<=v<=100 for side in r["final_energy"] for v in side)
            assert all(len(trace)==48 for trace in r["on_court_energy_by_minute"])
            results.append({"home":home,"away":away,"seed":seed,
                "score":r["score"],"home_bench":hbench,"away_bench":abench,\n                "home_players_used":sum(m>0 for m in r["minutes"][0]),\n                "away_players_used":sum(m>0 for m in r["minutes"][1]),\n                "home_max_minutes":max(r["minutes"][0]),\n                "away_max_minutes":max(r["minutes"][1]),
                "minutes_total":[sum(x) for x in r["minutes"]],
                "energy_start":[trace[0] for trace in r["on_court_energy_by_minute"]],
                "energy_end":[trace[-1] for trace in r["on_court_energy_by_minute"]],
                "stats":r["stats"]})
    return results

if __name__=="__main__":
    result=benchmark()
    print(json.dumps({"games":len(result),"results":result},indent=2))
