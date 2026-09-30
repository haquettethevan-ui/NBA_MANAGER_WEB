"""Regression tests for V41 rotations. Run: python test_rotations_v41.py"""
from legacy_main import Player, Team, set_rotation_plan
import server

POSITIONS=['PG','SG','SF','PF','C','PG/SG','SG/SF','SF/PF','PF/C','PG/SG','SG/SF','SF/PF','PF/C','PG','C']

def synthetic_team():
    players=[Player(f'P{i+1}',pos,'',94-i,78,76,78,77,76,75,82) for i,pos in enumerate(POSITIONS)]
    return Team('Rotation Test',players[:5],players[5:])

def longest_stint(player, schedule):
    best=cur=0
    for lineup in schedule:
        cur=cur+1 if player in lineup else 0
        best=max(best,cur)
    return best

def main():
    team=synthetic_team()
    starters,rotation=server.build_auto_rotation_minutes(team)
    set_rotation_plan(team,rotation)
    diag=server.rotation_diagnostics(team)
    assert sum(rotation.values()) == 240
    assert 8 <= diag['active_count'] <= 12
    assert all(v == 48 for v in diag['coverage'].values())
    assert all(rotation[p.name] > 0 for p in starters)
    active=[p for p in team.roster if rotation[p.name] > 0]
    assert max(longest_stint(p,team.rotation_schedule) for p in active) <= 12
    assert all(rotation[p.name] == 0 for p in team.roster if p not in active)
    print('V41 rotation tests: OK')
    print('Active players:',diag['active_count'])
    print('Minutes:',sorted((rotation[p.name] for p in active),reverse=True))
    print('Longest stints:',{p.name:longest_stint(p,team.rotation_schedule) for p in active})
    print('Position coverage:',diag['coverage'])

if __name__ == '__main__': main()
