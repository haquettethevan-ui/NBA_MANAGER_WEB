"""V43 smoke tests: tactical intent must respect roster skill."""
import random, statistics as st
import server
from main import simulate_game, DEFAULT_TACTICS, tactic_compatibility

def tactic(primary):
    t=dict(DEFAULT_TACTICS)
    rest=[x for x in ("Mouvement de balle","Pick & Roll","Jeu rapide","Rebond offensif","Jeu intérieur","Tir extérieur","Pénétration","Équilibré") if x != primary]
    t.update(offensePrimary=primary, offenseSecondary=rest[0], offenseTertiary=rest[1])
    return t

def run(n=16):
    poor=[]; normal=[]
    for i in range(n):
        random.seed(93000+i)
        a,_=server.build_team('PHI'); b,_=server.build_team('PHI')
        for p in a.roster: p.outside_scoring=max(55,p.outside_scoring-20)
        sa,ra=server.build_auto_rotation_minutes(a); sb,rb=server.build_auto_rotation_minutes(b)
        g=simulate_game(a,b,ra,rb,[p.name for p in sa],[p.name for p in sb],None,None,tactic('Tir extérieur'),tactic('Tir extérieur'))
        poor.append(g['team1']['stats']['three_attempted']); normal.append(g['team2']['stats']['three_attempted'])
    assert st.mean(normal) > st.mean(poor)+5, (st.mean(poor),st.mean(normal))
    team,_=server.build_team('PHI'); starters,rot=server.build_auto_rotation_minutes(team)
    c=tactic_compatibility(tactic('Tir extérieur'),team.roster,rot)
    assert 0 <= c['overall'] <= 100 and len(c['offense']) == 3
    print('V43 roster/tactics tests: OK')
    print('Poor shooting 3PA:',round(st.mean(poor),1),'Normal shooting 3PA:',round(st.mean(normal),1))
    print('Compatibility:',c)
if __name__=='__main__': run()
