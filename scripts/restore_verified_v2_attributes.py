"""Restore previously verified ratings when a fresh 2KRatings page is incomplete.

Never invent ratings. Only restore individual attributes from a prior record
with matching player URL and an explicit verified status.
"""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scrape_2kratings import DETAILED_LABELS
candidate=ROOT/"data/players_2k27_v2_candidate.json"
baseline=ROOT/"data/players_2k27_v2_baseline.json"

def restore(previous, fresh):
    verified={}
    for team,roster in previous.get("players",{}).items():
        for p in roster:
            attrs=p.get("attributes") or {}
            if p.get("attributes_status") in ("verified","restored_from_previous_verified") and p.get("url") and all(
                isinstance(attrs.get(k),int) and 0<=attrs[k]<=100 for k in DETAILED_LABELS
            ):
                verified[(team,p["url"])]=p
    restored=[]
    for team,roster in fresh.get("players",{}).items():
        for p in roster:
            attrs=p.get("attributes") or {}
            missing=[k for k in DETAILED_LABELS if attrs.get(k) is None]
            old=verified.get((team,p.get("url")))
            if not missing or old is None:
                continue
            p["attributes"]={**old["attributes"],**{k:v for k,v in attrs.items() if v is not None}}
            p["attributes_missing"]=[k for k in DETAILED_LABELS if p["attributes"].get(k) is None]
            p["attributes_status"]="restored_from_previous_verified"\n            p["rating_provenance"]="Prior verified 2KRatings snapshot; values may be older than current scrape"
            p["detail_error"]=None\n            for key in ("outside_scoring","inside_scoring","athleticism","playmaking","defense","rebounding","stamina"):\n                if p.get(key) is None and old.get(key) is not None:\n                    p[key]=old[key]\n            if all(p.get(key) is not None for key in ("outside_scoring","inside_scoring","athleticism","playmaking","defense","rebounding","stamina")):\n                p["general_category_status"]="restored_from_previous_verified"
            p["attributes_restored_keys"]=missing
            restored.append({"team":team,"name":p.get("name"),"count":len(missing)})
    return restored

if __name__=="__main__":
    if not baseline.exists():
        print("No prior baseline available; cannot restore incomplete ratings")
    else:
        old=json.loads(baseline.read_text(encoding="utf-8"))
        new=json.loads(candidate.read_text(encoding="utf-8"))
        restored=restore(old,new)
        candidate.write_text(json.dumps(new,ensure_ascii=False,indent=2),encoding="utf-8")
        print("Restored previously verified attributes:",json.dumps(restored))
