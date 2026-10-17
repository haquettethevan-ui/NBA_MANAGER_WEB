"""Deterministic smoke and sensitivity checks for the independent V2 prototype.
Run: python -m unittest discover -s experimental -p 'test_engine_v2.py'
"""
import unittest
import random
from engine_v2 import Player, GameMemory, defender_pressure, execute_pass, simulate_possession, simulate_game

def lineup(prefix, **ratings):
    return [Player(f"{prefix}{i}", position=("PG","SG","SF","PF","C")[i], **ratings)
            for i in range(5)]

class EngineV2Tests(unittest.TestCase):
    def test_deterministic_possession(self):
        a,b=lineup("A"),lineup("B")
        x=simulate_possession(a,b,random.Random(4))
        y=simulate_possession(a,b,random.Random(4))
        self.assertEqual(x,y)
        self.assertIn(x.outcome,("made","miss","turnover","foul"))
        self.assertTrue(0<=x.points<=4)

    def test_pressure_delay_and_fatigue(self):
        a=Player("attacker")
        d=Player("defender")
        p=defender_pressure(a,d,"three",0)
        self.assertLess(defender_pressure(a,d,"three",60),p)
        d.energy=45
        self.assertLess(defender_pressure(a,d,"three",0),p)
        self.assertGreater(defender_pressure(a,d,"rim",0),defender_pressure(a,d,"three",0))

    def test_pass_accuracy_affects_execution(self):
        target=Player("receiver")
        low=Player("low",pass_accuracy=40)
        high=Player("high",pass_accuracy=99)
        successes=[]
        for passer in (low,high):
            count=sum(execute_pass(random.Random(i),passer,target,60,0,[])[0] for i in range(1500))
            successes.append(count)
        self.assertGreater(successes[1],successes[0])

    def test_game_smoke(self):
        result=simulate_game(lineup("A"),lineup("B"),seed=8,possessions_per_team=30)
        self.assertEqual(len(result["score"]),2)
        self.assertTrue(all(s>=0 for s in result["score"]))

    def test_invalid_lineup(self):
        with self.assertRaises(ValueError):
            simulate_possession(lineup("A")[:4],lineup("B"))

class OffensiveDefensiveActionTests(unittest.TestCase):
    def test_action_and_reaction_events(self):
        from engine_v2_actions import ACTIONS, REACTIONS
        self.assertTrue({"screen","cut","handoff","post","drive"}.issubset(ACTIONS))
        self.assertTrue({"contain","help","switch","rotate","steal","block"}.issubset(REACTIONS))
        events=[]
        a,b=lineup("A"),lineup("B")
        for seed in range(1200):
            result=simulate_possession(a,b,random.Random(seed))
            events.extend(result.events)
        text=" | ".join(events)
        for phrase in ("offense: screen","offense: dribble handoff",
                       "offense: beat primary defender","defense: help",
                       "defense: contain drive","defense: switch",
                       "defense: rotate","offense:"):
            self.assertIn(phrase,text)

    def test_action_limit(self):
        a,b=lineup("A"),lineup("B")
        for seed in range(300):
            r=simulate_possession(a,b,random.Random(seed),max_actions=2)
            self.assertIn(r.outcome,("made","miss","turnover","foul"))
            self.assertLessEqual(sum(e.startswith("offense: ") and len(e.split())==3 and e.split()[2] in {"three","mid","drive","post","pass","screen","cut","handoff"} and e.split()[1] not in {"dribble"} for e in r.events),2)

class RulesTests(unittest.TestCase):
    def test_rebound_and_free_throws(self):
        from engine_v2_rules import rebound, free_throws
        a,b=lineup("A"),lineup("B")
        outcomes=[rebound(random.Random(i),a,b,[]) for i in range(200)]
        self.assertTrue(any(x[0] for x in outcomes))
        self.assertTrue(any(not x[0] for x in outcomes))
        self.assertTrue(all(0<=x[1]<5 for x in outcomes))
        self.assertTrue(0<=free_throws(random.Random(2),a[0],3,[])<=3)

    def test_foul_and_rebound_stats_are_consistent(self):
        a,b=lineup("A"),lineup("B")
        found={"foul":False,"rebound":False}
        for seed in range(2000):
            r=simulate_possession(a,b,random.Random(seed))
            self.assertLessEqual(r.free_throws_made,r.free_throws_attempted)
            self.assertGreaterEqual(r.offensive_rebounds,0)
            found["foul"] |= r.fouls_drawn>0
            found["rebound"] |= r.offensive_rebounds>0
        self.assertTrue(all(found.values()))

class AdditionalRulesTests(unittest.TestCase):
    def test_free_throw_last_attempt(self):
        from engine_v2_rules import free_throws
        p=Player("shooter")
        for seed in range(100):
            made,last=free_throws(random.Random(seed),p,3,[],return_last=True)
            self.assertTrue(0<=made<=3)
            self.assertIsInstance(last,bool)

    def test_offensive_foul_and_last_ft_rebound_events(self):
        a,b=lineup("A"),lineup("B")
        events=[]
        for seed in range(2500):
            r=simulate_possession(a,b,random.Random(seed))
            events.extend(r.events)
            self.assertLessEqual(r.free_throws_made,r.free_throws_attempted)
            self.assertEqual(r.offensive_fouls, sum("rules: offensive foul" in e for e in r.events))
        self.assertTrue(any("rules: offensive foul" in e for e in events))
        self.assertTrue(any("rules: shot clock reset to 14 after missed free throw" in e for e in events))

class DetailedAttributesTests(unittest.TestCase):
    def test_all_2kratings_fields_are_supported(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from scrape_2kratings import DETAILED_LABELS
        p=Player("full", **{key:65 for key in DETAILED_LABELS})
        self.assertEqual(len(DETAILED_LABELS),36)
        self.assertTrue(all(getattr(p,key)==65 for key in DETAILED_LABELS))

    def test_real_free_throw_rating_changes_outcomes(self):
        from engine_v2_rules import free_throws
        low=Player("low",free_throw=40)
        high=Player("high",free_throw=99)
        a=sum(free_throws(random.Random(i),low,2,[]) for i in range(1000))
        b=sum(free_throws(random.Random(i),high,2,[]) for i in range(1000))
        self.assertGreater(b,a)

    def test_loader_rejects_missing_detailed_attributes(self):
        import json
        import tempfile
        from pathlib import Path
        from engine_v2_rosters import load_rosters
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"rosters.json"
            p.write_text(json.dumps({"players":{"ATL":[{"name":"Incomplete","attributes":{"three_point":80}}]}}))
            with self.assertRaises(ValueError):
                load_rosters(p)

if __name__=="__main__":
    unittest.main()
