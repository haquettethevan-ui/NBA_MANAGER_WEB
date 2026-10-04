"""Regression checks for starter and position rules."""
import server
from legacy_main import set_rotation_plan, eligible_positions

for meta in server.TEAM_META:
    team,_=server.build_team(meta["id"])
    starters,rotation=server.build_auto_rotation_minutes(team)
    team.starters=list(starters)
    set_rotation_plan(team,rotation)

    expected={p.name for p in starters}
    actual={p.name for p in team.rotation_schedule[0]}
    assert actual==expected,(meta["id"],"starters",expected,actual)

    for minute,assignment in enumerate(team.rotation_position_schedule):
        for pos,p in assignment.items():
            assert pos in eligible_positions(p),(meta["id"],minute,pos,p.name,p.position)

print("OK: all teams start selected five and use only declared positions")
