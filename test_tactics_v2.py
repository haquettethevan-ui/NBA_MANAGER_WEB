"""V2 tactical stress test. Writes data/tactics_v2_test_report.json."""
import json, random, statistics as st
import server
from main import DEFAULT_TACTICS, simulate_game

N=50
T1,T2="PHI","SAS"
def tac(**kw):
    x=dict(DEFAULT_TACTICS); x.update(kw); return x
SCENARIOS={
 "neutral":tac(),
 "rim_100":tac(rimPriority=100,midPriority=5,threePriority=20),
 "three_100":tac(rimPriority=20,midPriority=5,threePriority=100),
 "mid_100":tac(rimPriority=10,midPriority=100,threePriority=10),
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
open("data/tactics_v2_test_report.json","w",encoding="utf-8").write(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps(report,indent=2,ensure_ascii=False))
