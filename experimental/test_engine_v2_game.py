"""Functional tests for experimental full-game orchestration."""
import unittest
from engine_v2 import Player
from engine_v2_game import TeamState, simulate_regulation_game

def roster(prefix):
    positions=("PG","SG","SF","PF","C")
    return [Player(f"{prefix}{i}",position=positions[i%5]) for i in range(10)]

class GameLayerTests(unittest.TestCase):
    def test_game_periods_and_clock(self):
        a,b=roster("A"),roster("B")
        r=simulate_regulation_game(a,b,seed=12)
        self.assertGreaterEqual(r["periods"],4)
        self.assertEqual(r["overtimes"],r["periods"]-4)
        self.assertEqual(len(r["score"]),2)
        self.assertTrue(all(v>=0 for v in r["score"]))
        self.assertEqual(len([e for e in r["timeline"] if e[2]=="period end"]),r["periods"])

    def test_bench_plays_and_fatigue_recovers(self):
        a,b=roster("A"),roster("B")
        r=simulate_regulation_game(a,b,seed=3)
        for side in (0,1):
            played=r["minutes"][side]
            self.assertGreaterEqual(sum(v>0 for v in played.values()),6)
            self.assertTrue(all(35<=v<=100 for v in r["energy"][side].values()))

    def test_foul_out_excluded(self):
        team=TeamState(roster("T"))
        team.fouls["T0"]=6
        self.assertNotIn("T0",[p.name for p in team.substitute()])

    def test_deterministic(self):
        x=simulate_regulation_game(roster("A"),roster("B"),seed=91)
        y=simulate_regulation_game(roster("A"),roster("B"),seed=91)
        self.assertEqual(x,y)

if __name__=="__main__":
    unittest.main()
