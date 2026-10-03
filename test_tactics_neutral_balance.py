"""Balance benchmark: player tactics versus a truly neutral CPU."""
import random, statistics
from collections import Counter, defaultdict
import server, main

OFF=list(main.OFFENSE_FOCUSES)
DEF=list(main.DEFENSE_FOCUSES)
NEUTRAL=server.CPU_NEUTRAL_TACTICS.copy()

def plan_with(side, focus):
    p=NEUTRAL.copy()
    pool=OFF if side=="offense" else DEF
    keys=[side+"Primary",side+"Secondary",side+"Tertiary"]
    p[keys[0]]=focus
    used=[]
    for k in keys:
        if p[k] in used:
            p[k]=next(x for x in pool if x not in used)
        used.append(p[k])
    return main.normalize_tactics(p)

def margin(team_id, opp_id, side, focus, seeds=6):
    vals=[]
    for seed in range(seeds):
        random.seed(910000+seed)
        a,_=server.build_team(team_id); b,_=server.build_team(opp_id)
        r=main.simulate_game(a,b,server.build_ai_rotation(a),server.build_ai_rotation(b),
            tactics1=plan_with(side,focus), tactics2=NEUTRAL)
        vals.append(r["team1"]["stats"]["points"]-r["team2"]["stats"]["points"])
    return statistics.mean(vals)

ids=[x["id"] for x in server.TEAM_META]
pairs=[(ids[i],ids[(i*7+11)%len(ids)]) for i in range(len(ids))]
for side,pool in (("offense",OFF),("defense",DEF)):
    wins=Counter(); global_scores=defaultdict(list); spreads=[]
    for a,b in pairs:
        scores={f:margin(a,b,side,f) for f in pool}
        best=max(scores,key=scores.get); wins[best]+=1
        for f,v in scores.items(): global_scores[f].append(v)
        ordered=sorted(scores.items(),key=lambda kv:kv[1],reverse=True)
        spreads.append(ordered[0][1]-ordered[-1][1])
        print(side,a,b,"BEST",best,"MARGINS",",".join(f"{k}:{v:.1f}" for k,v in ordered))
    print(side.upper(),"BEST_COUNTS",dict(wins))
    print(side.upper(),"AVG_MARGINS",{k:round(statistics.mean(v),2) for k,v in global_scores.items()})
    print(side.upper(),"AVG_BEST_WORST_SPREAD",round(statistics.mean(spreads),2))
