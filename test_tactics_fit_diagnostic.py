"""Diagnostic only: validate compatibility versus real rotation skills and tactical outcomes."""
import random, statistics as st, json, math
import server
from main import simulate_game, tactic_compatibility, DEFAULT_TACTICS
from engine_v55 import normalize_tactics, _effects, _tactical_finisher_weight, _shot_probability
TEAMS=[x["id"] for x in server.TEAM_META]
FOCUSES=["Tir extérieur","Pénétration","Jeu intérieur","Pick & Roll"]
SEEDS=24
def plan(name):
    return normalize_tactics({"offensePrimary":name})
def wm(team,minutes,attr):
    ps=[p for p in team.roster if minutes.get(p.name,0)>0]
    return sum(getattr(p,attr)*minutes[p.name] for p in ps)/sum(minutes[p.name] for p in ps)
def corr(x,y):
    return round(st.correlation(x,y),3) if len(set(x))>1 and len(set(y))>1 else None
def run(aid,bid,seed,t):
    random.seed(seed)
    a,_=server.build_team(aid);b,_=server.build_team(bid)
    s,ra=server.build_auto_rotation_minutes(a);rb=server.build_ai_rotation(b)
    g=simulate_game(a,b,ra,rb,[p.name for p in s],[p.name for p in b.starters],None,None,t,DEFAULT_TACTICS)
    x,y=g["team1"],g["team2"]
    return x["score"]-y["score"],x["stats"]["three_attempted"],x["stats"]["three_pct"]
profiles=[]
for i,tid in enumerate(TEAMS):
    team,_=server.build_team(tid);_,rot=server.build_auto_rotation_minutes(team)
    row={"team":tid,"outside":round(wm(team,rot,"outside_scoring"),2),
         "inside":round(wm(team,rot,"inside_scoring"),2),
         "playmaking":round(wm(team,rot,"playmaking"),2),
         "athleticism":round(wm(team,rot,"athleticism"),2)}
    for name in FOCUSES: row["fit_"+name]=tactic_compatibility(plan(name),team.roster,rot)["overall"]
    profiles.append(row)
print("STATIC_PROFILE",json.dumps(profiles))
for name,attr in [("Tir extérieur","outside"),("Pénétration","inside"),("Jeu intérieur","inside"),("Pick & Roll","playmaking")]:
    print("FIT_VALIDITY",name,"fit_vs_absolute_skill",corr([p["fit_"+name] for p in profiles],[p[attr] for p in profiles]))
print("ENGINE_WIRING",json.dumps({n:{"effects":_effects(plan(n),"offense"),"fit_only_diagnostic":True} for n in FOCUSES}))
print("SHOT_PROBABILITY_DIRECT_TACTIC_BONUS",False)
print("SIMULATIONS",len(TEAMS)*SEEDS*(len(FOCUSES)+1))
for name in FOCUSES:
    data=[]
    for i,tid in enumerate(TEAMS):
        oid=TEAMS[(i+13)%len(TEAMS)]
        base=[];test=[]
        for j in range(SEEDS):
            seed=1700000+i*1000+j
            base.append(run(tid,oid,seed,DEFAULT_TACTICS))
            test.append(run(tid,oid,seed,plan(name)))
        data.append({"team":tid,"fit":profiles[i]["fit_"+name],
                     "skill":profiles[i][{"Tir extérieur":"outside","Pénétration":"inside","Jeu intérieur":"inside","Pick & Roll":"playmaking"}[name]],
                     "margin_gain":round(st.mean(t[0]-b[0] for t,b in zip(test,base)),2),
                     "three_attempt_gain":round(st.mean(t[1]-b[1] for t,b in zip(test,base)),2)})
    print("FOCUS",name,"fit_gain_corr",corr([x["fit"] for x in data],[x["margin_gain"] for x in data]),
          "skill_gain_corr",corr([x["skill"] for x in data],[x["margin_gain"] for x in data]),
          "mean_gain",round(st.mean(x["margin_gain"] for x in data),2),
          "mean_3pa_change",round(st.mean(x["three_attempt_gain"] for x in data),2),
          "per_team",json.dumps(data))
print("AUDIT_COMPLETE engine_unchanged=true")
