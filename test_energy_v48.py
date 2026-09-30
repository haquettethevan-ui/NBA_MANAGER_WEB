
import random, statistics
import server, main
LEVELS=(100,85,75,65)
def play(team_id, tired, seed):
    random.seed(seed)
    a,_=server.build_team(team_id); b,_=server.build_team(team_id)
    ra=server.build_ai_rotation(a); rb=server.build_ai_rotation(b)
    for p in a.roster: p.energy=float(tired)
    for p in b.roster: p.energy=100.0
    x=main.simulate_game(a,b,ra,rb)
    A=x["team1"]["stats"]; B=x["team2"]["stats"]
    return A["points"]-B["points"], A["fg_pct"]-B["fg_pct"], A["turnovers"]-B["turnovers"], A["rebounds"]-B["rebounds"]
for level in LEVELS:
    rows=[]
    for i,m in enumerate(server.TEAM_META):
        for s in range(2):
            rows.append(play(m["id"],level,88000+i*100+s))
    print(level, "margin",round(statistics.mean(x[0] for x in rows),2),
          "win%",round(100*sum(x[0]>0 for x in rows)/len(rows),1),
          "FGdiff",round(statistics.mean(x[1] for x in rows),3),
          "TOVdiff",round(statistics.mean(x[2] for x in rows),2),
          "REBdiff",round(statistics.mean(x[3] for x in rows),2))
