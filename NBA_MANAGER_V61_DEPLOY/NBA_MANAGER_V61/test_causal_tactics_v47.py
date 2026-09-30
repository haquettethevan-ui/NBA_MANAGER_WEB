
import random, statistics
import server, main, engine_v47 as eng
def tac(off="Équilibré", defense="Équilibré"):
    oo=[off]+[x for x in eng.OFFENSE_FOCUSES if x!=off]
    dd=[defense]+[x for x in eng.DEFENSE_FOCUSES if x!=defense]
    return {"offensePrimary":oo[0],"offenseSecondary":oo[1],"offenseTertiary":oo[2],
            "defensePrimary":dd[0],"defenseSecondary":dd[1],"defenseTertiary":dd[2]}
def check(off,fav,counter,metric,n=2,base=10000):
    diffs=[]
    for i,meta in enumerate(server.TEAM_META):
        a1=[];a2=[]
        for s in range(n):
            for defense,dest in ((fav,a1),(counter,a2)):
                random.seed(base+i*100+s)
                a,_=server.build_team(meta["id"]); b,_=server.build_team(meta["id"])
                ra=server.build_ai_rotation(a); rb=server.build_ai_rotation(b)
                x=main.simulate_game(a,b,ra,rb,tactics1=tac(off),tactics2=tac("Équilibré",defense))
                dest.append(x["team1"]["stats"][metric])
        diffs.append((meta["id"],statistics.mean(a1)-statistics.mean(a2)))
    return diffs
if __name__=="__main__":
    assert main.ACTIVE_ENGINE_VERSION=="V47"
    cases=[
      ("Tir extérieur","Protection du cercle","Défense extérieure","three_attempted"),
      ("Jeu intérieur","Défense extérieure","Protection du cercle","points_in_paint"),
      ("Pénétration","Défense extérieure","Protection du cercle","points_in_paint"),
      ("Mouvement de balle","Zone","Homme à homme","assists"),
      ("Rebond offensif","Zone","Box out","rebounds"),
      ("Jeu rapide","Box out","Repli défensif","possessions"),
    ]
    for j,c in enumerate(cases):
        d=check(*c,n=2,base=10000+j*10000)
        vals=[x[1] for x in d]
        print(c[0],c[3],"delta",round(statistics.mean(vals),2),"positive",sum(v>0 for v in vals),"/30")
