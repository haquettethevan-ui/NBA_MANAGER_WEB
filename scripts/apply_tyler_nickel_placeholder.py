"""Apply an explicit user-approved placeholder for Tyler Nickel only, in isolated V2 candidate data."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scrape_2kratings import DETAILED_LABELS,CATEGORY_LABELS
path=ROOT/"data/players_2k27_v2_candidate.json"
data=json.loads(path.read_text(encoding="utf-8"))
matches=[p for team,roster in data["players"].items() for p in roster if p.get("name","").casefold()=="tyler nickel"]
if len(matches)!=1:
    raise SystemExit(f"Expected exactly one Tyler Nickel, found {len(matches)}")
p=matches[0]
p["attributes"]={key:65 for key in DETAILED_LABELS}
for key in CATEGORY_LABELS: p[key]=65
for key in ("overall","three_point","dunk"): p[key]=65
p["attributes_missing"]=[]
p["attributes_status"]="placeholder"
p["general_category_status"]="placeholder"
p["rating_override_reason"]="User-approved provisional rating of 65 for Tyler Nickel; not sourced from 2KRatings"
path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
print("Applied 65 placeholder to Tyler Nickel: 36 detailed, 7 general, OVR, 3PT, dunk")
