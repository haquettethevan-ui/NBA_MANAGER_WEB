"""Tests for detailed 2KRatings import (no network calls)."""
import unittest
from scrape_2kratings import parse_detailed_attributes, DETAILED_LABELS

class DetailedRatingsTests(unittest.TestCase):
    def test_label_first(self):
        text=("Outside Scoring 78 Three-Point Shot 86 Mid-Range Shot 70 "
              "Shot IQ 60 Playmaking 66 Pass IQ 75 Pass Accuracy 55 "
              "Defense 80 Help Defense IQ 91 Perimeter Defense 83 "
              "Athleticism 83 Speed 86 Speed with Ball 79 "
              "Inside Scoring 57 Layup 81 Driving Dunk 25")
        a=parse_detailed_attributes(text)
        for key,value in {"three_point":86,"mid_range":70,"shot_iq":60,
                          "pass_iq":75,"pass_accuracy":55,"help_defense_iq":91,
                          "perimeter_defense":83,"speed":86,"speed_with_ball":79,
                          "driving_layup":81,"driving_dunk":25}.items():
            self.assertEqual(a[key],value,key)
        self.assertIsNone(a["block"])

    def test_reverse_layout(self):
        a=parse_detailed_attributes("84 Pass IQ 92 Shot IQ 55 Block")
        self.assertEqual(a["pass_iq"],84)
        self.assertEqual(a["shot_iq"],92)
        self.assertEqual(a["block"],55)

    def test_no_fabricated_values(self):
        a=parse_detailed_attributes("No player ratings here")
        self.assertEqual(len(a),len(DETAILED_LABELS))
        self.assertTrue(all(v is None for v in a.values()))

if __name__=="__main__":
    unittest.main()
