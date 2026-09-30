"""V39 hierarchy calibration: talent, stars, tactics and fatigue.
Run this after any engine coefficient change.
"""
import random, statistics as st
import server
from main import simulate_game, DEFAULT_TACTICS

RATING_KEYS=('overall','outside_scoring','inside_scoring','athleticism','playmaking','defense','rebounding')

def setup(boost_team=0, star_boost=0, shallow=False):
    a,_=server.build_team('PHI'); b,_=server.build_team('PHI')
    for p in a.roster:
        for k in RATING_KEYS: setattr(p,k,max(40,min(99,getattr(p,k)+boost_team)))
    if star_boost:
        star=max(a.roster,key=lambda p:p.overall)
        for k in ('overall','outside_scoring','inside_scoring','playmaking','athleticism'):
            setattr(star,k,max(40,min(99,getattr(star,k)+star_boost)))
    sa,ra=server.build_auto_rotation_minutes(a); sb,rb=server.build_auto_rotation_minutes(b)
    if shallow:
        # Concentrate minutes on the starters/first reserves while keeping a legal 240-min plan.
        active=sorted([p for p in a.roster if ra.get(p.name,0)>0],key=lambda p:ra[p.name],reverse=True)
        target=[38,37,36,35,34,18,15,12,8,7]
        trial={p.name:0 for p in a.roster}
        for p,m in zip(active,target): trial[p.name]=m
        try:
            from legacy_main import set_rotation_plan
            set_rotation_plan(a,trial); ra=trial
        except Exception: pass
    return a,b,sa,ra,sb,rb

def one(seed,boost_team=0,star_boost=0,ta=None,tb=None,shallow=False):
    random.seed(seed)
    a,b,sa,ra,sb,rb=setup(boost_team,star_boost,shallow)
    return simulate_game(a,b,ra,rb,[p.name for p in sa],[p.name for p in sb],None,None,ta or DEFAULT_TACTICS,tb or DEFAULT_TACTICS)

def summarize(games):
    margins=[g['team1']['score']-g['team2']['score'] for g in games]
    wins=sum(x>0 for x in margins)/len(margins)
    fga_shares=[]; point_shares=[]; top4_fga=[]
    for g in games:
        ps=g['team1']['players']; total_fga=max(1,sum(p['shots_attempted'] for p in ps)); total_pts=max(1,g['team1']['score'])
        ranked=sorted(ps,key=lambda p:p['overall'],reverse=True)
        fga_shares.append(ranked[0]['shots_attempted']/total_fga)
        point_shares.append(ranked[0]['points']/total_pts)
        top4_fga.append(sum(p['shots_attempted'] for p in ranked[:4])/total_fga)
    return {'win_pct':round(wins,3),'margin':round(st.mean(margins),2),'top_player_fga_share':round(st.mean(fga_shares),3),'top_player_pts_share':round(st.mean(point_shares),3),'top4_fga_share':round(st.mean(top4_fga),3)}

def series(n=80,**kw): return summarize([one(10000+i,**kw) for i in range(n)])

if __name__=='__main__':
    print('Equal:',series())
    print('+3 team:',series(boost_team=3))
    print('+5 team:',series(boost_team=5))
    print('One star +8 offense:',series(star_boost=8))
    outside={**DEFAULT_TACTICS,'offensePrimary':'Tir extérieur'}
    perim={**DEFAULT_TACTICS,'defensePrimary':'Défense extérieure'}
    paint={**DEFAULT_TACTICS,'defensePrimary':'Protection du cercle'}
    print('Outside vs perimeter:',series(ta=outside,tb=perim))
    print('Outside vs paint:',series(ta=outside,tb=paint))
    print('Shallow rotation:',series(shallow=True))
