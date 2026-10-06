"""PHI/SAS matchup audit. No games are simulated."""
import json
import server
from legacy_main import perimeter_defense, interior_defense

TEAMS=("PHI","SAS")

def weighted(players, minutes, fn):
    den=sum(minutes.get(p.name,0) for p in players) or 1
    return round(sum(fn(p)*minutes.get(p.name,0) for p in players)/den,2)

def audit(team_id):
    team,_=server.build_team(team_id)
    starters,minutes=server.build_auto_rotation_minutes(team)
    active=[p for p in team.roster if minutes.get(p.name,0)>0]
    metrics={}
    attrs=("overall","outside_scoring","inside_scoring","athleticism","playmaking","defense","rebounding","stamina")
    for a in attrs:
        metrics[a]=weighted(active,minutes,lambda p,a=a:getattr(p,a))
    metrics["perimeter_defense"]=weighted(active,minutes,perimeter_defense)
    metrics["interior_defense"]=weighted(active,minutes,interior_defense)
    players=[]
    for p in sorted(active,key=lambda x:minutes[x.name],reverse=True):
        players.append({
            "name":p.name,"pos":p.position,"role":p.role,"minutes":minutes[p.name],
            "overall":p.overall,"outside":p.outside_scoring,"inside":p.inside_scoring,
            "playmaking":p.playmaking,"athleticism":p.athleticism,
            "perimeter_defense":round(perimeter_defense(p),1),
            "interior_defense":round(interior_defense(p),1),
            "rebounding":p.rebounding,
        })
    return {"starters":[p.name for p in starters],"metrics":metrics,"rotation":players}

report={"note":"No simulations. Metrics use the same auto rotation and defense functions as the match engine.","teams":{}}
for t in TEAMS: report["teams"][t]=audit(t)
p=report["teams"]["PHI"]["metrics"]; s=report["teams"]["SAS"]["metrics"]
report["matchup_edges"]={
    "PHI_outside_vs_SAS_perimeter_def":round(p["outside_scoring"]-s["perimeter_defense"],2),
    "PHI_inside_vs_SAS_interior_def":round(p["inside_scoring"]-s["interior_defense"],2),
    "SAS_outside_vs_PHI_perimeter_def":round(s["outside_scoring"]-p["perimeter_defense"],2),
    "SAS_inside_vs_PHI_interior_def":round(s["inside_scoring"]-p["interior_defense"],2),
}
open("data/phi_sas_audit.json","w",encoding="utf-8").write(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps(report,indent=2,ensure_ascii=False))
