"""Calibration of V42 tactical interactions.
Identical teams are used so measured margins come from tactical choices, not talent.
"""
import random, statistics as st
import server
from main import simulate_game, DEFAULT_TACTICS

def tac(off=None, defense=None):
    t=dict(DEFAULT_TACTICS)
    if off:
        vals=[off]+[x for x in ("Mouvement de balle","Pick & Roll","Jeu rapide","Rebond offensif","Jeu intérieur","Tir extérieur","Pénétration") if x!=off]
        t.update(offensePrimary=vals[0],offenseSecondary=vals[1],offenseTertiary=vals[2])
    if defense:
        vals=[defense]+[x for x in ("Homme à homme","Box out","Protection du cercle","Défense extérieure","Pression porteur","Zone","Repli défensif") if x!=defense]
        t.update(defensePrimary=vals[0],defenseSecondary=vals[1],defenseTertiary=vals[2])
    return t

def game(seed, ta, tb, boost=0):
    random.seed(seed)
    a,_=server.build_team('PHI'); b,_=server.build_team('PHI')
    if boost:
        for p in a.roster:
            for k in ('overall','outside_scoring','inside_scoring','athleticism','playmaking','defense','rebounding'):
                setattr(p,k,min(99,getattr(p,k)+boost))
    sa,ra=server.build_auto_rotation_minutes(a); sb,rb=server.build_auto_rotation_minutes(b)
    return simulate_game(a,b,ra,rb,[p.name for p in sa],[p.name for p in sb],None,None,ta,tb)

def series(ta,tb,n=120,boost=0):
    ms=[]; three=[]; oreb=[]
    for i in range(n):
        g=game(42000+i,ta,tb,boost); ms.append(g['team1']['score']-g['team2']['score'])
        t=g['team1']['stats']; three.append(t['three_attempted']); oreb.append(t['rebounds'])
    return round(sum(x>0 for x in ms)/n,3),round(st.mean(ms),2),round(st.mean(three),1),round(st.mean(oreb),1)

if __name__=='__main__':
    cases=[
      ('Outside vs perimeter',tac('Tir extérieur'),tac(defense='Défense extérieure')),
      ('Outside vs paint',tac('Tir extérieur'),tac(defense='Protection du cercle')),
      ('Inside vs rim protection',tac('Jeu intérieur'),tac(defense='Protection du cercle')),
      ('Inside vs perimeter',tac('Jeu intérieur'),tac(defense='Défense extérieure')),
      ('OREB vs boxout',tac('Rebond offensif'),tac(defense='Box out')),
      ('OREB vs zone',tac('Rebond offensif'),tac(defense='Zone')),
      ('Fast vs transition D',tac('Jeu rapide'),tac(defense='Repli défensif')),
    ]
    for name,a,b in cases: print(name,series(a,b))
    print('+5 talent despite counter',series(tac('Tir extérieur'),tac(defense='Défense extérieure'),boost=5))
