"""Check whether deterministic CPU tactics are coherent across the league."""
from collections import Counter, defaultdict
import server

OFF=["offensePrimary","offenseSecondary","offenseTertiary"]
DEF=["defensePrimary","defenseSecondary","defenseTertiary"]

ids=[x["id"] for x in server.TEAM_META]
plans={}
off=Counter(); deff=Counter(); changed=0; total=0
team_choices=defaultdict(set)

for i,tid in enumerate(ids):
    team,_=server.build_team(tid)
    for j,oid in enumerate(ids):
        if tid==oid: continue
        opp,_=server.build_team(oid)
        p=server.ai_tactics(team,opp)
        assert len({p[k] for k in OFF})==3, (tid,oid,"duplicate offense",p)
        assert len({p[k] for k in DEF})==3, (tid,oid,"duplicate defense",p)
        off[p["offensePrimary"]]+=1
        deff[p["defensePrimary"]]+=1
        team_choices[tid].add((p["offensePrimary"],p["defensePrimary"]))
        total+=1
    # compare first two different opponents to detect adaptation
    opponents=[x for x in ids if x!=tid]
    if len(opponents)>=2:
        a,_=server.build_team(opponents[0]); b,_=server.build_team(opponents[-1])
        pa=server.ai_tactics(team,a); pb=server.ai_tactics(team,b)
        if (pa["offensePrimary"],pa["defensePrimary"]) != (pb["offensePrimary"],pb["defensePrimary"]):
            changed+=1

print("MATCHUPS",total)
print("OFFENSE",dict(off))
print("DEFENSE",dict(deff))
print("TEAMS_ADAPTING_SAMPLE",changed,"/",len(ids))
print("AVG_DISTINCT_PRIMARY_PAIRS_PER_TEAM",round(sum(map(len,team_choices.values()))/len(team_choices),2))
print("MAX_OFF_SHARE",round(max(off.values())/total*100,1),"%")
print("MAX_DEF_SHARE",round(max(deff.values())/total*100,1),"%")
print("TEAMS_WITH_ONE_PAIR",sum(len(v)==1 for v in team_choices.values()))
for tid in ids:
    print("TEAM",tid,"DISTINCT",len(team_choices[tid]),"SAMPLE",list(sorted(team_choices[tid]))[:8])
