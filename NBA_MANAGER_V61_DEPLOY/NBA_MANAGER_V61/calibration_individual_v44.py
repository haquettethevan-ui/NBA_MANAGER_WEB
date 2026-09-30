"""V44 individual-stat calibration. Run after changes to possession/player logic."""
import random, statistics as st
import server
from main import simulate_game, DEFAULT_TACTICS

STAT_KEYS=("minutes","points","shots_attempted","three_attempted","free_throws_attempted","assists","rebounds","turnovers")

def run(team_id="PHI", n=120):
    rows={}; team_box=[]
    for i in range(n):
        random.seed(44000+i)
        a,_=server.build_team(team_id); b,_=server.build_team(team_id)
        sa,ra=server.build_auto_rotation_minutes(a); sb,rb=server.build_auto_rotation_minutes(b)
        g=simulate_game(a,b,ra,rb,[p.name for p in sa],[p.name for p in sb],None,None,DEFAULT_TACTICS,DEFAULT_TACTICS)
        team_box.append(g["team1"])
        for p in g["team1"]["players"]:
            d=rows.setdefault(p["name"],{"overall":p["overall"], **{k:[] for k in STAT_KEYS}})
            for k in STAT_KEYS:d[k].append(p[k])
    out=[]
    for name,d in rows.items():
        r={"name":name,"overall":d["overall"]}
        for k in STAT_KEYS:r[k]=round(st.mean(d[k]),2)
        out.append(r)
    out.sort(key=lambda r:r["minutes"],reverse=True)
    return out

if __name__=="__main__":
    for r in run(): print(r)
