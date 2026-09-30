
import random,statistics,collections
import server,engine_v50 as eng
def dtac(f):
 sec="Homme à homme" if f!="Homme à homme" else "Box out"; ter="Repli défensif" if f not in ("Repli défensif",sec) else "Défense extérieure"
 return {"offensePrimary":"Équilibré","offenseSecondary":"Mouvement de balle","offenseTertiary":"Jeu rapide","defensePrimary":f,"defenseSecondary":sec,"defenseTertiary":ter}
neutral={"offensePrimary":"Équilibré","offenseSecondary":"Mouvement de balle","offenseTertiary":"Jeu rapide","defensePrimary":"Équilibré","defenseSecondary":"Homme à homme","defenseTertiary":"Repli défensif"}
for f in [x for x in eng.DEFENSE_FOCUSES if x!="Équilibré"]:
 vals=[]; tov=[]; paint=[]; th=[]; reb=[]
 for i,m in enumerate(server.TEAM_META):
  mm=[]
  for q in range(4):
   random.seed(910000+i*100+q);a,_=server.build_team(m["id"]);b,_=server.build_team(m["id"]);ra=server.build_ai_rotation(a);rb=server.build_ai_rotation(b)
   if q%2==0:x=eng.simulate_game(a,b,ra,rb,tactics1=dtac(f),tactics2=neutral);D=x["team1"]["stats"];O=x["team2"]["stats"]
   else:x=eng.simulate_game(a,b,ra,rb,tactics1=neutral,tactics2=dtac(f));D=x["team2"]["stats"];O=x["team1"]["stats"]
   mm.append(O["points"]-D["points"]);tov.append(O["turnovers"]-D["turnovers"]);paint.append(O["points_in_paint"]-D["points_in_paint"]);th.append(O["three_attempted"]-D["three_attempted"]);reb.append(O["rebounds"]-D["rebounds"])
  vals.append(statistics.mean(mm))
 print(f,round(statistics.mean(vals),2),sum(x>0 for x in vals),"/30","TOV",round(statistics.mean(tov),2),"PAINT",round(statistics.mean(paint),2),"3PA",round(statistics.mean(th),2),"REB",round(statistics.mean(reb),2))
