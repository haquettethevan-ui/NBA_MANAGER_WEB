"""Benchmark CPU tactical advice against the actual match engine.

Run manually: python test_ai_tactics_optimality.py
Uses common random seeds so every candidate tactic sees the same game noise.
"""
import random
import statistics
import server
import main

OFFENSE = ["Équilibré","Jeu intérieur","Tir extérieur","Pénétration","Pick & Roll","Jeu rapide","Mouvement de balle","Rebond offensif"]
DEFENSE = ["Équilibré","Homme à homme","Pression porteur","Protection du cercle","Défense extérieure","Box out","Repli défensif","Zone"]

def replace_primary(plan, side, focus, pool):
    out=dict(plan)
    keys=[side+"Primary",side+"Secondary",side+"Tertiary"]
    out[keys[0]]=focus
    used=[]
    for key in keys:
        if out[key] in used:
            out[key]=next(x for x in pool if x not in used)
        used.append(out[key])
    return out

def evaluate(team_id, opponent_id, side="offense", samples=8):
    team,_=server.build_team(team_id)
    opp,_=server.build_team(opponent_id)
    cpu=server.ai_tactics(team,opp)
    opponent_plan=server.ai_tactics(opp,team)
    pool=OFFENSE if side=="offense" else DEFENSE
    key=side+"Primary"
    scores={}
    for focus in pool:
        diffs=[]
        for seed in range(samples):
            random.seed(700000+seed)
            a,_=server.build_team(team_id)
            b,_=server.build_team(opponent_id)
            result=main.simulate_game(
                a,b,server.build_ai_rotation(a),server.build_ai_rotation(b),
                tactics1=replace_primary(cpu,side,focus,pool),
                tactics2=opponent_plan,
            )
            diffs.append(result["team1"]["stats"]["points"]-result["team2"]["stats"]["points"])
        scores[focus]=statistics.mean(diffs)
    best=max(scores,key=scores.get)
    chosen=cpu[key]
    return chosen,best,scores[best]-scores[chosen],scores

if __name__=="__main__":
    ids=[x["id"] for x in server.TEAM_META]
    pairs=[(ids[i],ids[(i*7+11)%len(ids)]) for i in range(min(12,len(ids)))]
    for side in ("offense","defense"):
        rows=[]
        for a,b in pairs:
            chosen,best,regret,_=evaluate(a,b,side)
            rows.append((chosen,best,regret))
            print(side,a,b,"AI=",chosen,"BEST=",best,"REGRET=",round(regret,2))
        top1=sum(chosen==best for chosen,best,_ in rows)/len(rows)
        regret=statistics.mean(x[2] for x in rows)
        print(side.upper(),"TOP1=",round(top1*100,1),"%","AVG_REGRET=",round(regret,2))
