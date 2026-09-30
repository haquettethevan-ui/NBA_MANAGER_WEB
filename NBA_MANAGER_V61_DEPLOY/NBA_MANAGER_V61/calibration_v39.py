"""Calibration V39: realism, talent dominance, tactical secondary impact."""
import random, statistics as st
import server
from main import simulate_game, DEFAULT_TACTICS


def game(seed, boost_a=0, tactics_a=None, tactics_b=None):
    random.seed(seed)
    a,_=server.build_team('PHI'); b,_=server.build_team('PHI')
    for p in a.roster:
        for k in ('overall','outside_scoring','inside_scoring','athleticism','playmaking','defense','rebounding'):
            setattr(p,k,max(40,min(99,getattr(p,k)+boost_a)))
        p._tendency_cache=None
    sa,ra=server.build_auto_rotation_minutes(a); sb,rb=server.build_auto_rotation_minutes(b)
    return simulate_game(a,b,ra,rb,[p.name for p in sa],[p.name for p in sb],None,None,tactics_a or DEFAULT_TACTICS,tactics_b or DEFAULT_TACTICS)


def series(n=40, boost=0, ta=None, tb=None):
    gs=[game(i,boost,ta,tb) for i in range(n)]
    wins=sum(g['team1']['score']>g['team2']['score'] for g in gs)
    margin=st.mean(g['team1']['score']-g['team2']['score'] for g in gs)
    return wins/n, margin

if __name__=='__main__':
    print('V39 calibration')
    print('Equal teams:', series())
    print('+5 ratings vs baseline:', series(boost=5))
    outside={**DEFAULT_TACTICS,'offensePrimary':'Tir extérieur'}
    perimeter={**DEFAULT_TACTICS,'defensePrimary':'Défense extérieure'}
    paint={**DEFAULT_TACTICS,'defensePrimary':'Protection du cercle'}
    print('Outside offense vs perimeter defense:', series(ta=outside,tb=perimeter))
    print('Outside offense vs paint defense:', series(ta=outside,tb=paint))
