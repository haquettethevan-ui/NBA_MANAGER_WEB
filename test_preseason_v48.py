"""Fast pre-season regression gate for the stable V45 match engine."""
import random, statistics as st
import main, server

def assert_engine():
    assert getattr(main, 'ACTIVE_ENGINE_VERSION', None) == 'V48'
    assert main.simulate_game.__module__ == 'engine_v48'

def sample(n=24, team_id='PHI'):
    boxes=[]
    for i in range(n):
        random.seed(45000+i)
        a,_=server.build_team(team_id); b,_=server.build_team(team_id)
        sa,ra=server.build_auto_rotation_minutes(a); sb,rb=server.build_auto_rotation_minutes(b)
        g=main.simulate_game(a,b,ra,rb,[p.name for p in sa],[p.name for p in sb],None,None,main.DEFAULT_TACTICS,main.DEFAULT_TACTICS)
        boxes += [g['team1'],g['team2']]
    return boxes

def avg(boxes,key): return st.mean(b['stats'][key] for b in boxes)

def run():
    assert_engine(); boxes=sample()
    metrics={k:avg(boxes,k) for k in ['points','possessions','shots_attempted','three_attempted','free_throws_attempted','assists','rebounds','turnovers']}
    ranges={'points':(105,125),'possessions':(94,105),'shots_attempted':(82,94),'three_attempted':(30,44),'free_throws_attempted':(17,29),'assists':(21,31),'rebounds':(39,50),'turnovers':(10,18)}
    for k,(lo,hi) in ranges.items(): assert lo <= metrics[k] <= hi,(k,metrics[k])
    print('V48 PRE-SEASON GATE: OK'); print({k:round(v,2) for k,v in metrics.items()})
if __name__=='__main__': run()
