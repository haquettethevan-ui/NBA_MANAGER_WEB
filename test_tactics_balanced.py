"""Balanced paired-seed tactical audit: 30 teams x 8 seeds x 16 plans (3840 games).
Engine is not modified. Each team is used once as attacking home side.
"""
import math, random, statistics as st
import server
from main import DEFAULT_TACTICS, simulate_game, tactic_compatibility
from engine_v55 import normalize_tactics

PAIRS=list(zip(
 "ATL BOS BKN CHA CHI CLE DAL DEN DET GSW HOU IND LAC LAL MEM MIA MIL MIN NOP NYK OKC ORL PHI PHX POR SAC SAS TOR UTA WAS".split(),
 "IND NOP SAC BKN GSW MIL PHX ATL DEN MEM ORL UTA CLE LAC NYK SAS CHA HOU MIN POR BOS DET MIA PHI WAS DAL LAL OKC TOR CHI".split()))
SEEDS=8
OFF=["Équilibré","Jeu intérieur","Tir extérieur","Pénétration","Pick & Roll","Jeu rapide","Mouvement de balle","Rebond offensif"]
DEF=["Équilibré","Protection du cercle","Défense extérieure","Pression porteur","Zone","Homme à homme","Box out","Repli défensif"]
def tactic(side,name):
    if name=="Équilibré": return dict(DEFAULT_TACTICS)
    return normalize_tactics({side+"Primary":name})
def game(aid,bid,seed,t1,t2):
    random.seed(seed)
    a,_=server.build_team(aid);b,_=server.build_team(bid)
    starters,r1=server.build_auto_rotation_minutes(a);r2=server.build_ai_rotation(b)
    g=simulate_game(a,b,r1,r2,[p.name for p in starters],
                    [p.name for p in b.starters],None,None,t1,t2)
    return g["team1"]["score"]-g["team2"]["score"],g["team1"]["stats"]["three_attempted"]
def mean(xs): return st.mean(xs)
def corr(x,y):
    if len(set(x))<2 or len(set(y))<2:return None
    return round(st.correlation(x,y),3)
def evaluate(side,names):
    by_name={name:[] for name in names}
    per_matchup={name:[] for name in names}
    fits={name:[] for name in names}
    for i,(aid,bid) in enumerate(PAIRS):
        a,_=server.build_team(aid)
        results={}
        for name in names:
            t=tactic(side,name)
            attack=t if side=="offense" else dict(DEFAULT_TACTICS)
            defense=t if side=="defense" else dict(DEFAULT_TACTICS)
            rows=[game(aid,bid,770000+i*1000+j,attack,defense) for j in range(SEEDS)]
            results[name]=rows
            if side=="offense":
                fits[name].append(tactic_compatibility(t,a.roster)["overall"])
        base=results["Équilibré"]
        for name in names:
            paired=[results[name][j][0]-base[j][0] for j in range(SEEDS)]
            by_name[name].extend(paired)
            per_matchup[name].append(mean(paired))
    print("\\n"+side.upper()+" TESTS "+str(len(PAIRS)*SEEDS*len(names)))
    for name in names:
        x=by_name[name]; clusters=per_matchup[name]
        # Matchup-level uncertainty avoids pretending games are independent across teams.
        se=st.stdev(clusters)/math.sqrt(len(clusters)) if len(clusters)>1 else 0
        print(name, "paired_delta",round(mean(x),2),"CI95_matchup",[
            round(mean(x)-1.96*se,2),round(mean(x)+1.96*se,2)],
            "positive_matchups",sum(v>0 for v in clusters),"/",len(clusters),
            "fit_corr",corr(fits[name],clusters) if side=="offense" else "n/a")
evaluate("offense",OFF)
evaluate("defense",DEF)
print("TEST_COMPLETE games=",len(PAIRS)*SEEDS*(len(OFF)+len(DEF)))
