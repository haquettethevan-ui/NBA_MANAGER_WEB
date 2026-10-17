"""Load scraped 2KRatings V2 rosters into the independent experimental engine.

Explicit proxies are temporary; do not silently invent missing values.
"""
import json
from pathlib import Path
from engine_v2 import Player

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "players_2k27_v2_candidate.json"
DIRECT = (
    "three_point", "mid_range", "close_shot", "driving_layup",
    "driving_dunk", "post_control", "ball_handle", "pass_iq",
    "pass_accuracy", "shot_iq", "speed", "strength", "vertical",
    "perimeter_defense", "interior_defense", "offensive_rebound",
    "defensive_rebound", "stamina",
    "free_throw", "offensive_consistency", "agility", "hustle",
    "overall_durability", "standing_dunk", "post_hook", "post_fade",
    "draw_foul", "hands", "speed_with_ball", "pass_vision", "block",
    "steal", "pass_perception", "defensive_consistency",
    "help_defense_iq", "intangibles",
)
# The current V2 Player schema names these differently from 2KRatings.
PROXIES = {"acceleration": "speed_with_ball", "defensive_iq": "help_defense_iq"}

def load_rosters(path=DATA_FILE):
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"V2 import missing: {source}. Run Audit 2KRatings V2.")
    doc = json.loads(source.read_text(encoding="utf-8"))
    rosters = {}
    for team, records in doc["players"].items():
        converted = []
        for record in records:
            attrs = record.get("attributes") or {}
            mapping = {key: attrs.get(key) for key in DIRECT}
            mapping.update({key: attrs.get(source_key) for key, source_key in PROXIES.items()})
            missing = [key for key, value in mapping.items() if value is None]
            if missing:
                raise ValueError(f"{team} / {record.get('name')}: missing {missing}")
            converted.append(Player(name=record["name"],
                position=(record.get("position") or "SG"),
                **mapping))
        rosters[team] = converted
    return rosters
