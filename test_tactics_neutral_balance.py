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
        st=r["team1"]["stats"]
        vals.append((st["points"]-r["team2"]["stats"]["points"],st.get("three_attempted",st.get("threeAttempts",0)),st.get("shots_attempted",st.get("fieldGoalsAttempted",0))))
    return statistics.mean(x[0] for x in vals)

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


# Explicit shot-diet regression: interior priorities must materially reduce 3PA
# versus an exterior-first plan for the same teams and random seeds.
for tid,oid in pairs[:10]:
    team,_=server.build_team(tid); opp,_=server.build_team(oid)
    plans={
      "inside": {"offensePrimary":"Jeu intérieur","offenseSecondary":"Pénétration","offenseTertiary":"Mouvement de balle",
                 "defensePrimary":"Équilibré","defenseSecondary":"Homme à homme","defenseTertiary":"Box out"},
      "outside":{"offensePrimary":"Tir extérieur","offenseSecondary":"Mouvement de balle","offenseTertiary":"Pick & Roll",
                 "defensePrimary":"Équilibré","defenseSecondary":"Homme à homme","defenseTertiary":"Box out"},
    }
    rates={}
    for label,plan in plans.items():
        attempts=[]; threes=[]
        for seed in range(8):
            random.seed(770000+seed)
            a,_=server.build_team(tid); b,_=server.build_team(oid)
            rr=main.simulate_game(a,b,server.build_ai_rotation(a),server.build_ai_rotation(b),tactics1=plan,tactics2=NEUTRAL)
            st=rr["team1"]["stats"]
            # Use team-level counters: player serialization does not expose the
            # internal fga/3pa aliases used by older benchmark versions.
            fga=st.get("shots_attempted", st.get("fieldGoalsAttempted", 0))
            tpa=st.get("three_attempted", st.get("threeAttempts", 0))
            attempts.append(fga); threes.append(tpa)
        rates[label]=sum(threes)/max(1,sum(attempts))
    print("SHOT_DIET",tid,"inside",round(rates["inside"],3),"outside",round(rates["outside"],3))
    assert rates["inside"] + .08 < rates["outside"], (tid,rates)


# Roster-fit correlation audit. A tactic should be more valuable to teams whose
# rotation actually possesses the skills needed to execute it.
def corr(xs,ys):
    mx=statistics.mean(xs); my=statistics.mean(ys)
    num=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    den=(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))**.5
    return num/den if den else 0.0

def roster_skill(team,focus):
    rot=server.build_ai_rotation(team)
    active=[p for p in team.roster if rot.get(p.name,0)>0]
    den=sum(rot[p.name] for p in active) or 1
    def avg(attr): return sum(getattr(p,attr)*rot[p.name] for p in active)/den
    outside,inside,play,ath,reb,overall=(avg(x) for x in ("outside_scoring","inside_scoring","playmaking","athleticism","rebounding","overall"))
    return {
      "Équilibré":overall,
      "Jeu intérieur":.70*inside+.18*ath+.12*reb,
      "Tir extérieur":.82*outside+.18*play,
      "Pénétration":.50*inside+.32*ath+.18*play,
      "Pick & Roll":.52*play+.28*inside+.20*outside,
      "Jeu rapide":.68*ath+.32*play,
      "Mouvement de balle":.68*play+.32*outside,
      "Rebond offensif":.76*reb+.24*ath,
    }[focus]

base={}
gains=defaultdict(list); skills=defaultdict(list)
for a,b in pairs:
    base[a]=margin(a,b,"offense","Équilibré",seeds=12)
    for focus in OFF:
        if focus=="Équilibré": continue
        team,_=server.build_team(a)
        skills[focus].append(roster_skill(team,focus))
        gains[focus].append(margin(a,b,"offense",focus,seeds=12)-base[a])
print("FIT_SAMPLE_SEEDS",12)
print("FIT_CORRELATIONS",{f:round(corr(skills[f],gains[f]),3) for f in gains})
print("FIT_GAINS_LOW_HIGH",{
 f:(round(statistics.mean([g for _,g in sorted(zip(skills[f],gains[f]))[:10]]),2),
    round(statistics.mean([g for _,g in sorted(zip(skills[f],gains[f]))[-10:]]),2))
 for f in gains})
