"""Comprehensive V2 tactical diagnostic. Does NOT modify the engine."""
import json, random, statistics as st
import server
from main import DEFAULT_TACTICS, simulate_game

N=100
T1,T2="PHI","SAS"
KEYS=["points","fg_pct","three_attempted","three_pct","shots_attempted",
      "free_throws_attempted","rebounds","assists","turnovers","fouls","possessions"]

def tac(**kw):
    x=dict(DEFAULT_TACTICS); x.update(kw); return x

def one(seed,t1,t2,team1="PHI",team2="SAS"):
    random.seed(seed)
    a,_=server.build_team(team1); b,_=server.build_team(team2)
    s,r1=server.build_auto_rotation_minutes(a); r2=server.build_ai_rotation(b)
    return simulate_game(a,b,r1,r2,[p.name for p in s],[p.name for p in b.starters],None,None,t1,t2)

def summary(games):
    a=[g["team1"] for g in games]; b=[g["team2"] for g in games]
    def av(arr,key):
        vals=[x["score"] if key=="points" else x["stats"][key] for x in arr]
        return round(st.mean(vals),2)
    out={k:av(a,k) for k in KEYS}
    out.update({"opp_"+k:av(b,k) for k in KEYS})
    out["point_diff"]=round(out["points"]-out["opp_points"],2)
    out["win_pct"]=round(100*sum(g["team1"]["score"]>g["team2"]["score"] for g in games)/len(games),1)
    return out

neutral=tac()
scenarios={
 "neutral":neutral,
 "all_100":{k:100 for k in DEFAULT_TACTICS},
 "all_0":{k:0 for k in DEFAULT_TACTICS},
 "rim_100":tac(rimPriority=100,midPriority=5,threePriority=20),
 "three_100":tac(rimPriority=20,midPriority=5,threePriority=100),
 "rim_three_100":tac(rimPriority=100,midPriority=5,threePriority=100),
 "mid_100":tac(rimPriority=10,midPriority=100,threePriority=10),
 "pace_100":tac(pace=100),"pace_0":tac(pace=0),
 "movement_100":tac(ballMovement=100),"movement_0":tac(ballMovement=0),
 "pnr_100":tac(pickAndRoll=100),"pnr_0":tac(pickAndRoll=0),
 "post_100":tac(postPlay=100),"post_0":tac(postPlay=0),
 "glass_100":tac(offensiveGlass=100),"glass_0":tac(offensiveGlass=0),
 "pressure_100":tac(perimeterPressure=100),"pressure_0":tac(perimeterPressure=0),
 "rim_def_100":tac(rimProtection=100),"rim_def_0":tac(rimProtection=0),
 "help_100":tac(helpDefense=100),"help_0":tac(helpDefense=0),
 "switch_100":tac(switching=100),"switch_0":tac(switching=0),
 "transition_def_100":tac(defensiveTransition=100),"transition_def_0":tac(defensiveTransition=0),
}
report={"games_per_scenario":N,"total_games":0,"engine_frozen":True,"scenarios":{},"cross_tests":{}}
for i,(name,t) in enumerate(scenarios.items()):
    games=[one(100000+i*1000+j,t,neutral) for j in range(N)]
    report["scenarios"][name]=summary(games); report["total_games"]+=N

cross={
 "rim_attack_vs_rim_def":(scenarios["rim_100"],scenarios["rim_def_100"]),
 "three_attack_vs_pressure":(scenarios["three_100"],scenarios["pressure_100"]),
 "rim_three_vs_neutral":(scenarios["rim_three_100"],neutral),
 "all100_vs_neutral":(scenarios["all_100"],neutral),
}
for i,(name,(ta,tb)) in enumerate(cross.items()):
    games=[one(900000+i*1000+j,ta,tb) for j in range(N)]
    report["cross_tests"][name]=summary(games); report["total_games"]+=N

open("data/tactics_v2_test_report.json","w",encoding="utf-8").write(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps(report,indent=2,ensure_ascii=False))
