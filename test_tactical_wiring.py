"""Fast tactical wiring regression checks. No match-engine calibration changes."""
import random
import server
from main import DEFAULT_TACTICS, simulate_game, tactic_compatibility
from engine_v55 import _effects, _focuses, _best_defender
def tac(**kwargs):
    t=dict(DEFAULT_TACTICS);t.update(kwargs);return t
assert _effects(tac(postPlay=100),"offense")["post"]>_effects(tac(postPlay=0),"offense")["post"]
assert _focuses(tac(threePriority=100),"offense")
assert _focuses(tac(postPlay=100),"offense")
team,_=server.build_team("PHI")
assert tactic_compatibility(tac(threePriority=100),team.roster)["offense"]
a,_=server.build_team("PHI"); b,_=server.build_team("SAS")
s,r1=server.build_auto_rotation_minutes(a);r2=server.build_ai_rotation(b)
def play(seed,t1,t2):
    random.seed(seed)
    a,_=server.build_team("PHI");b,_=server.build_team("SAS")
    s,r1=server.build_auto_rotation_minutes(a);r2=server.build_ai_rotation(b)
    g=simulate_game(a,b,r1,r2,[p.name for p in s],[p.name for p in b.starters],None,None,t1,t2)
    return g["team1"]["score"]-g["team2"]["score"],g["team1"]["stats"]["three_attempted"]
for label,attack,defense in [
 ("neutral",tac(),tac()),("post_high",tac(postPlay=100),tac()),
 ("post_low",tac(postPlay=0),tac()),("switch_high",tac(),tac(switching=100)),
 ("switch_low",tac(),tac(switching=0))]:
    rows=[play(830000+i,attack,defense) for i in range(25)]
    print(label,{"point_diff":round(sum(r[0] for r in rows)/len(rows),2),
                 "three_attempted":round(sum(r[1] for r in rows)/len(rows),2)})
print("TACTICAL_WIRING_TESTS_PASSED")

# Compatibility should be driven by roster specialization and active minutes.
a,_=server.build_team("PHI")
base=tactic_compatibility(tac(threePriority=100),a.roster)
assert 0 <= base["overall"] <= 100
assert base["offense"] and all(0 <= x["score"] <= 100 for x in base["offense"])
first=a.roster[0]
limited={p.name:(36 if p is first else 0) for p in a.roster}
weighted=tactic_compatibility(tac(threePriority=100),a.roster,limited)
assert 0 <= weighted["overall"] <= 100
assert tactic_compatibility(tac(),[],None)["overall"] == 50
print("COMPATIBILITY_REGRESSION_PASSED",base["overall"],weighted["overall"])
