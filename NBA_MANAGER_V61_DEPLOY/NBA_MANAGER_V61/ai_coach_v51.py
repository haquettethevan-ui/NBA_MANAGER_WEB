"""V51 AI coach: stable team identity with limited opponent adaptation."""
import random
ATTRS=("overall","outside_scoring","inside_scoring","playmaking","defense","rebounding","athleticism")
def rotation_metrics(team, minutes):
    ps=[p for p in team.roster if minutes.get(p.name,0)>0]; den=sum(minutes[p.name] for p in ps) or 1
    return {k:sum(getattr(p,k)*minutes[p.name] for p in ps)/den for k in ATTRS}
def _scores(a,o,adapt=.30):
    # Base identity from own personnel; opponent terms are deliberately capped.
    c=lambda x:max(-5,min(5,x))*adapt
    off={
      "Tir extérieur":a["outside_scoring"]+c((o["inside_scoring"]-o["outside_scoring"])*.8),
      "Jeu intérieur":a["inside_scoring"]+c((o["outside_scoring"]-o["inside_scoring"])*.8),
      "Pénétration":.58*a["inside_scoring"]+.42*a["athleticism"]+c((78-o["defense"])*.6),
      "Pick & Roll":.62*a["playmaking"]+.23*a["inside_scoring"]+.15*a["outside_scoring"]+c((o["defense"]-75)*.35),
      "Jeu rapide":.62*a["athleticism"]+.23*a["playmaking"]+.15*a["overall"]+c((78-o["athleticism"])*.5),
      "Mouvement de balle":.72*a["playmaking"]+.28*a["outside_scoring"]+c((o["defense"]-75)*.4),
      "Rebond offensif":.78*a["rebounding"]+.22*a["athleticism"]+c((75-o["rebounding"])*.7)}
    de={
      "Protection du cercle":.62*a["defense"]+.38*a["rebounding"]+c((o["inside_scoring"]-75)*.9),
      "Défense extérieure":.78*a["defense"]+.22*a["athleticism"]+c((o["outside_scoring"]-75)*.9),
      "Pression porteur":.55*a["defense"]+.45*a["athleticism"]+c((o["playmaking"]-75)*.6),
      "Zone":.72*a["defense"]+.28*a["rebounding"]+c((o["inside_scoring"]-o["outside_scoring"])*.45),
      "Homme à homme":.78*a["defense"]+.22*a["athleticism"],
      "Box out":.70*a["rebounding"]+.30*a["defense"]+c((o["rebounding"]-75)*.9),
      "Repli défensif":.60*a["athleticism"]+.40*a["defense"]+c((o["athleticism"]-75)*.9)}
    return off,de
def choose_tactics(team,minutes,opp,opp_minutes,rng=None,adapt=.30):
    rng=rng or random.Random(); a=rotation_metrics(team,minutes);o=rotation_metrics(opp,opp_minutes)
    off,de=_scores(a,o,adapt)
    # Small coaching uncertainty, far below V50's full reactive noise.
    O=sorted(off,key=lambda k:off[k]+rng.gauss(0,0.65),reverse=True)[:3]
    D=sorted(de,key=lambda k:de[k]+rng.gauss(0,0.65),reverse=True)[:3]
    return {"offensePrimary":O[0],"offenseSecondary":O[1],"offenseTertiary":O[2],
            "defensePrimary":D[0],"defenseSecondary":D[1],"defenseTertiary":D[2]}
