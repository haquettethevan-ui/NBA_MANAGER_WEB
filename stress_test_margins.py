import random, statistics as st
from collections import defaultdict
import server
from main import simulate_game

TEAMS=[x["id"] for x in server.TEAM_META]
CONF={x["id"]:x.get("conference","") for x in server.TEAM_META}

def play(aid,bid,seed):
    random.seed(seed)
    a,_=server.build_team(aid); b,_=server.build_team(bid)
    ar=server.build_ai_rotation(a); br=server.build_ai_rotation(b)
    g=simulate_game(a,b,ar,br,tactics1=server.ai_tactics(a),tactics2=server.ai_tactics(b))
    return g["team1"]["stats"]["points"],g["team2"]["stats"]["points"]

scores=[]; margins=[]; leaders=[]; extreme20=extreme30=extreme40=0
for sim in range(20):
    rng=random.Random(88000+sim)
    diff=defaultdict(int)
    for rnd in range(4):
        order=TEAMS[:]; rng.shuffle(order)
        for i in range(0,30,2):
            a,b=order[i],order[i+1]
            sa,sb=play(a,b,sim*10000+rnd*100+i)
            scores += [sa,sb]
            m=abs(sa-sb); margins.append(m)
            extreme20 += m>=20; extreme30 += m>=30; extreme40 += m>=40
            diff[a]+=sa-sb; diff[b]+=sb-sa
    confmax={}
    for conf in ("East","West"):
        vals=[diff[t] for t in TEAMS if CONF.get(t)==conf]
        confmax[conf]=max(vals)
    leaders += list(confmax.values())
games=len(margins)
print("ENGINE_MARGIN_STRESS")
print("games",games)
print("avg_team_score",round(st.mean(scores),2))
print("avg_margin",round(st.mean(margins),2))
print("median_margin",round(st.median(margins),2))
for q in (0.75,0.9,0.95,0.99):
    arr=sorted(margins); print("margin_p"+str(int(q*100)),arr[min(len(arr)-1,int(q*len(arr))-1)])
print("pct_margin_20plus",round(100*extreme20/games,2))
print("pct_margin_30plus",round(100*extreme30/games,2))
print("pct_margin_40plus",round(100*extreme40/games,2))
print("conference_leader_diff_after_4_mean",round(st.mean(leaders),2))
print("conference_leader_diff_after_4_median",round(st.median(leaders),2))
print("conference_leader_diff_after_4_max",max(leaders))
print("conference_leader_diff_after_4_p90",sorted(leaders)[int(.9*len(leaders))-1])
print("leaders_80plus",sum(x>=80 for x in leaders),"of",len(leaders))
