"""Targeted paired-seed tactical confirmation. Engine remains untouched."""
import json, random, statistics as st
import server
from main import DEFAULT_TACTICS, simulate_game

GAMES_PER_MATCHUP=50
MATCHUPS=[
 ("PHI","SAS"),("HOU","SAS"),("HOU","PHI"),("HOU","SAC"),("HOU","UTA"),
 ("SAS","TOR"),("SAS","UTA"),("UTA","WAS"),("PHX","POR"),("PHX","TOR"),
 ("GSW","TOR"),("GSW","UTA"),("DEN","TOR"),("IND","SAS"),("IND","TOR"),
 ("BOS","CLE"),("BOS","SAS"),("ATL","DAL"),("ATL","NOP"),("DET","LAC"),
]
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

def avg(x): return round(st.mean(x),2)
agg={p:{k:[] for k in KEYS}|{"opp_points":[],"wins":[]} for p in PLANS}
rows=[]
for mi,(a,b) in enumerate(MATCHUPS):
    seed0=900000+mi*1000
    plan_games={}
    for pn,pt in PLANS.items():
        gs=[game(seed0+j,a,b,pt,PLANS["neutral"]) for j in range(GAMES_PER_MATCHUP)]
        plan_games[pn]=gs
        for g in gs:
            x,y=g["team1"],g["team2"]
            for k in KEYS: agg[pn][k].append(x["score"] if k=="points" else x["stats"][k])
            agg[pn]["opp_points"].append(y["score"]); agg[pn]["wins"].append(x["score"]>y["score"])
    row={"matchup":f"{a}-{b}"}
    neutral=[g["team1"]["score"]-g["team2"]["score"] for g in plan_games["neutral"]]
    for pn,gs in plan_games.items():
        margins=[g["team1"]["score"]-g["team2"]["score"] for g in gs]
        row[pn]={"diff":avg(margins),"win_pct":round(100*sum(x>0 for x in margins)/len(margins),1)}
        if pn!="neutral":
            paired=[x-y for x,y in zip(margins,neutral)]
            row[pn]["delta_vs_neutral"]=avg(paired)
            row[pn]["better_seed_pct"]=round(100*sum(x>0 for x in paired)/len(paired),1)
    rows.append(row)

summary={}
for pn,d in agg.items():
    summary[pn]={k:avg(v) for k,v in d.items() if k!="wins"}
    summary[pn]["point_diff"]=round(summary[pn]["points"]-summary[pn]["opp_points"],2)
    summary[pn]["win_pct"]=round(100*sum(d["wins"])/len(d["wins"]),1)

report={"engine_frozen":True,"paired_seeds":True,"test":"targeted_confirmation",
        "matchups":len(MATCHUPS),"games_per_matchup_per_plan":GAMES_PER_MATCHUP,
        "total_games":len(MATCHUPS)*len(PLANS)*GAMES_PER_MATCHUP,
        "plans":summary,"matchup_results":rows}
print(json.dumps(report,indent=2,ensure_ascii=False))
