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
    """Choose a legal starting five and, where available, five positional backups.

    Players with the highest composite scoring/defense ratings are preferred.
    Each chosen player plays 24 minutes if two distinct fives are possible.
    Otherwise a legal five plays all 48 minutes (explicit benchmark fallback).
    """
    rank=sorted(range(len(roster)),key=lambda i:(
        -(roster[i].three_point+roster[i].close_shot+roster[i].perimeter_defense+
          roster[i].interior_defense),i))
    def find_five(excluded):
        selected=[None]*5
        def search(slot,used):
            if slot==5:
                return True
            for i in rank:
                if i in excluded or i in used:
                    continue
                positions={x.strip().upper() for x in roster[i].position.replace("-","/").split("/")}
                if POSITIONS[slot] not in positions:
                    continue
                selected[slot]=i
                if search(slot+1,used|{i}):
                    return True
            return False
        return list(selected) if search(0,set()) else None
    first=find_five(set())
    if first is None:
        raise ValueError("No legal starting five from recorded positions")
    second=find_five(set(first))
    rotation=[first[:] for _ in range(48)] if second is None else [
        (first if minute%12<6 else second)[:] for minute in range(48)]
    validate_rotation(roster,rotation)
    return rotation,second is not None

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
                "score":r["score"],"home_bench":hbench,"away_bench":abench,
                "minutes_total":[sum(x) for x in r["minutes"]],
                "energy_start":[trace[0] for trace in r["on_court_energy_by_minute"]],
                "energy_end":[trace[-1] for trace in r["on_court_energy_by_minute"]],
                "stats":r["stats"]})
    return results

if __name__=="__main__":
    result=benchmark()
    print(json.dumps({"games":len(result),"results":result},indent=2))
