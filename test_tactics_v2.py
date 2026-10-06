"""V2 tactical stress test. Writes data/tactics_v2_test_report.json."""
import json, random, statistics as st
import server
from main import DEFAULT_TACTICS, simulate_game

N=320
T1,T2="PHI","SAS"
def tac(**kw):
    x=dict(DEFAULT_TACTICS); x.update(kw); return x
SCENARIOS={
 "neutral":tac(),
 "all_100":{k:100 for k in DEFAULT_TACTICS},
 "rim_100":tac(rimPriority=100,midPriority=5,threePriority=20),
 "three_100":tac(rimPriority=20,midPriority=5,threePriority=100),
 "rim_three_100":tac(rimPriority=100,midPriority=5,threePriority=100),
 "mid_100":tac(rimPriority=10,midPriority=100,threePriority=10),
 "pace_100":tac(pace=100),
 "pace_0":tac(pace=0),
 "movement_100":tac(ballMovement=100),
 "pnr_100":tac(pickAndRoll=100),
 "glass_100":tac(offensiveGlass=100),
 "pressure_100":tac(perimeterPressure=100),
 "rim_def_100":tac(rimProtection=100),
 "help_100":tac(helpDefense=100),
 "transition_def_100":tac(defensiveTransition=100),
}
def one(seed,t1,t2):
 random.seed(seed); a,_=server.build_team(T1); b,_=server.build_team(T2)
 s,r1=server.build_auto_rotation_minutes(a); r2=server.build_ai_rotation(b)
 return simulate_game(a,b,r1,r2,[p.name for p in s],[p.name for p in b.starters],None,None,t1,t2)
def summary(games):
 teams=[g["team1"] for g in games]
 opp=[g["team2"] for g in games]
 def av(arr,key):
  vals=[x["score"] if key=="points" else x["stats"][key] for x in arr]
  return round(st.mean(vals),2)
 return {k:av(teams,k) for k in ["points","fg_pct","three_attempted","three_pct","shots_attempted","free_throws_attempted","rebounds","assists","turnovers","fouls","possessions"]}|{"opp_points":av(opp,"points"),"win_pct":round(100*sum(g["team1"]["score"]>g["team2"]["score"] for g in games)/len(games),1)}
report={"games_per_scenario":N,"total_games":0,"scenarios":{},"sweeps":{},"cross_tests":{}}
neutral=tac()
for i,(name,t) in enumerate(SCENARIOS.items()):
 games=[one(100000*i+j,t,neutral) for j in range(N)]
 report["scenarios"][name]=summary(games)
 report["total_games"] += len(games)
# Five-point sensitivity sweeps: verify monotonicity, strength and extreme-value exploits.
SWEEP_KEYS=["pace","ballMovement","pickAndRoll","offensiveGlass","perimeterPressure","rimProtection","helpDefense","defensiveTransition"]
for si,key in enumerate(SWEEP_KEYS):
 report["sweeps"][key]={}
 for value in [0,25,50,75,100]:
  t=tac(**{key:value})
  games=[one(2000000+si*200000+value*1000+j,t,neutral) for j in range(N)]
  report["sweeps"][key][str(value)]=summary(games)
  report["total_games"] += len(games)

# Direct cross-tests for counters, tradeoffs and exploit candidates.
pairs={
 "rim_attack_vs_rim_def":(SCENARIOS["rim_100"],SCENARIOS["rim_def_100"]),
 "three_attack_vs_pressure":(SCENARIOS["three_100"],SCENARIOS["pressure_100"]),
 "rim_three_vs_neutral":(SCENARIOS["rim_three_100"],neutral),
 "all100_vs_neutral":(SCENARIOS["all_100"],neutral),
}
for i,(name,(a,b)) in enumerate(pairs.items()):
 games=[one(900000+10000*i+j,a,b) for j in range(N)]
 report["cross_tests"][name]=summary(games)
 report["total_games"] += len(games)
open("data/tactics_v2_test_report.json","w",encoding="utf-8").write(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps(report,indent=2,ensure_ascii=False))
