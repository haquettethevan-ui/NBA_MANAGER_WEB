
import random,statistics
import server,engine_v50 as eng
def T(f):
 pool=[x for x in ("Protection du cercle","Défense extérieure","Zone") if x!=f]
 return {"offensePrimary":"Équilibré","offenseSecondary":"Mouvement de balle","offenseTertiary":"Jeu rapide","defensePrimary":f,"defenseSecondary":pool[0],"defenseTertiary":pool[1]}
# compare each focus against Équilibré primary, same secondary/tertiary where possible
for f in [x for x in eng.DEFENSE_FOCUSES if x!="Équilibré"]:
 vals=[]
 for i,m in enumerate(server.TEAM_META):
  for q in range(2):
   random.seed(440000+i*100+q);a,_=server.build_team(m["id"]);b,_=server.build_team(m["id"]);ra=server.build_ai_rotation(a);rb=server.build_ai_rotation(b)
   tf=T(f); base=dict(tf); base["defensePrimary"]="Équilibré"
   # If equilibré duplicates nothing, legal.
   if q%2==0:x=eng.simulate_game(a,b,ra,rb,tactics1=tf,tactics2=base);D=x["team1"]["stats"];O=x["team2"]["stats"]
   else:x=eng.simulate_game(a,b,ra,rb,tactics1=base,tactics2=tf);D=x["team2"]["stats"];O=x["team1"]["stats"]
   vals.append(O["points"]-D["points"])
 print(f,round(statistics.mean(vals),2))
