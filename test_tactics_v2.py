"""League-wide tactical diagnostic. Engine remains untouched."""
import json, random, statistics as st
import server
from main import DEFAULT_TACTICS, simulate_game

GAMES_PER_MATCHUP=6
TEAMS=[t["id"] for t in server.TEAM_META]
KEYS=["points","fg_pct","three_attempted","three_pct","shots_attempted",
      "free_throws_attempted","rebounds","assists","turnovers","fouls","possessions"]

def tac(**kw):
    x=dict(DEFAULT_TACTICS); x.update(kw); return x

PLANS={
 "neutral":tac(),
 "rim":tac(rimPriority=90,threePriority=28,midPriority=22),
 "perimeter":tac(threePriority=72,rimPriority=42,midPriority=28,ballMovement=70,pickAndRoll=68),
}

def game(seed,a_id,b_id,t1,t2):
    random.seed(seed)
    a,_=server.build_team(a_id); b,_=server.build_team(b_id)
    s,r1=server.build_auto_rotation_minutes(a); r2=server.build_ai_rotation(b)
    return simulate_game(a,b,r1,r2,[p.name for p in s],[p.name for p in b.starters],None,None,t1,t2)

def avg(xs): return round(st.mean(xs),2) if xs else 0
agg={p:{k:[] for k in KEYS} | {"opp_points":[],"wins":[]} for p in PLANS}
team_results={p:{t:{"diff":[],"wins":[]} for t in TEAMS} for p in PLANS}
matchups=[]
seed=700000
for ai,a in enumerate(TEAMS):
    for b in TEAMS[ai+1:]:
        row={"matchup":f"{a}-{b}"}
        for pn,pt in PLANS.items():
            # Common random numbers: every tactical plan gets the exact same
            # seed sequence for this matchup, isolating the tactical effect.
            matchup_seed=700000 + ai*10000 + TEAMS.index(b)*100
            gs=[game(matchup_seed+j,a,b,pt,PLANS["neutral"]) for j in range(GAMES_PER_MATCHUP)]
            for g in gs:
                x,y=g["team1"],g["team2"]
                for k in KEYS:
                    agg[pn][k].append(x["score"] if k=="points" else x["stats"][k])
                agg[pn]["opp_points"].append(y["score"])
                w=x["score"]>y["score"]; agg[pn]["wins"].append(w)
                team_results[pn][a]["diff"].append(x["score"]-y["score"]); team_results[pn][a]["wins"].append(w)
            row[pn]={"diff":avg([g["team1"]["score"]-g["team2"]["score"] for g in gs]),
                     "win_pct":round(100*sum(g["team1"]["score"]>g["team2"]["score"] for g in gs)/len(gs),1)}
        matchups.append(row)

summary={}
for pn,d in agg.items():
    summary[pn]={k:avg(v) for k,v in d.items() if k!="wins"}
    summary[pn]["point_diff"]=round(summary[pn]["points"]-summary[pn]["opp_points"],2)
    summary[pn]["win_pct"]=round(100*sum(d["wins"])/len(d["wins"]),1)

per_team={}
for pn,td in team_results.items():
    per_team[pn]={t:{"point_diff":avg(v["diff"]),"win_pct":round(100*sum(v["wins"])/len(v["wins"]),1)}
                  for t,v in td.items() if v["diff"]}

report={"engine_frozen":True,"paired_seeds":True,"teams":len(TEAMS),"games_per_matchup_per_plan":GAMES_PER_MATCHUP,
        "matchups":len(matchups),"total_games":len(matchups)*len(PLANS)*GAMES_PER_MATCHUP,
        "plans":summary,"per_team":per_team,"matchup_results":matchups}
print(json.dumps(report,indent=2,ensure_ascii=False))
