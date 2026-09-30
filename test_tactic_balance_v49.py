
import random,statistics
import server,main,engine_v49 as eng
def tac(f):
    sec="Mouvement de balle" if f!="Mouvement de balle" else "Pick & Roll"
    ter="Jeu rapide" if f!="Jeu rapide" and sec!="Jeu rapide" else "Pénétration"
    return {"offensePrimary":f,"offenseSecondary":sec,"offenseTertiary":ter,
      "defensePrimary":"Homme à homme","defenseSecondary":"Box out","defenseTertiary":"Repli défensif"}
base={"offensePrimary":"Équilibré","offenseSecondary":"Mouvement de balle","offenseTertiary":"Jeu rapide",
"defensePrimary":"Homme à homme","defenseSecondary":"Box out","defenseTertiary":"Repli défensif"}
for j,f in enumerate(x for x in eng.OFFENSE_FOCUSES if x!="Équilibré"):
    ds=[]
    for i,m in enumerate(server.TEAM_META):
      mm=[]
      for q in range(2):
        random.seed(30000+i*100+q)
        a,_=server.build_team(m["id"]);b,_=server.build_team(m["id"])
        x=main.simulate_game(a,b,server.build_ai_rotation(a),server.build_ai_rotation(b),tactics1=tac(f),tactics2=base)
        mm.append(x["team1"]["stats"]["points"]-x["team2"]["stats"]["points"])
      ds.append(statistics.mean(mm))
    print(f,round(statistics.mean(ds),2),sum(x>0 for x in ds),"/30")
