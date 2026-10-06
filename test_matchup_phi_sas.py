"""Focused PHI vs SAS tactical matchup test. 50 games per plan."""
import json, random, statistics as st
import server
from main import DEFAULT_TACTICS, simulate_game

N=50
T1,T2="PHI","SAS"

def tac(**kw):
    x=dict(DEFAULT_TACTICS); x.update(kw); return x

# Hypotheses fixed BEFORE simulation:
# adapted: use PHI perimeter creation, ball movement and P&R; avoid over-attacking Wembanyama.
# neutral: engine defaults.
# bad_matchup: deliberately force rim attempts into SAS's strongest interior defender.
PLANS={
    "adapted_perimeter_creation": tac(
        threePriority=72, rimPriority=42, midPriority=28,
        ballMovement=70, pickAndRoll=68
    ),
    "neutral": tac(),
    "bad_force_rim": tac(
        rimPriority=90, threePriority=28, midPriority=22,
        ballMovement=45, pickAndRoll=42
    ),
}

def one(seed,t1,t2):
    random.seed(seed)
    a,_=server.build_team(T1); b,_=server.build_team(T2)
    s,r1=server.build_auto_rotation_minutes(a); r2=server.build_ai_rotation(b)
    return simulate_game(a,b,r1,r2,[p.name for p in s],
        [p.name for p in b.starters],None,None,t1,t2)

def summary(games):
    teams=[g["team1"] for g in games]; opp=[g["team2"] for g in games]
    def av(arr,key):
        vals=[x["score"] if key=="points" else x["stats"][key] for x in arr]
        return round(st.mean(vals),2)
    out={k:av(teams,k) for k in [
        "points","fg_pct","three_attempted","three_pct","shots_attempted",
        "free_throws_attempted","rebounds","assists","turnovers","fouls","possessions"
    ]}
    out["opp_points"]=av(opp,"points")
    out["point_diff"]=round(out["points"]-out["opp_points"],2)
    out["win_pct"]=round(100*sum(g["team1"]["score"]>g["team2"]["score"] for g in games)/len(games),1)
    return out

report={
    "matchup":"PHI vs SAS",
    "games_per_plan":N,
    "total_games":N*len(PLANS),
    "hypothesis":{
        "PHI_strengths":"elite versatile creation/scoring: Maxey, Brown, LeBron, Embiid",
        "SAS_strength":"Wembanyama interior defense/rebounding",
        "expected_order":"adapted_perimeter_creation > neutral > bad_force_rim"
    },
    "plans":{}
}
# Common random numbers: each plan receives the same seed sequence.
for name,t in PLANS.items():
    games=[one(610000+j,t,tac()) for j in range(N)]
    report["plans"][name]=summary(games)

path="data/matchup_phi_sas_report.json"
open(path,"w",encoding="utf-8").write(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps(report,indent=2,ensure_ascii=False))
