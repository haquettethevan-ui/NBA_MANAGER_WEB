"""Audit the isolated 2KRatings V2 candidate; do not change production data."""
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scrape_2kratings import DETAILED_LABELS, CATEGORY_LABELS

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "data/players_2k27_v2_candidate.json"
out = ROOT / "data/audit_2kratings_v2.json"
if not source.exists():
    raise SystemExit("No candidate scrape file: scraping did not complete")
data = json.loads(source.read_text(encoding="utf-8"))
teams = data.get("players", {})
expected = json.loads((ROOT / "data/teams.json").read_text(encoding="utf-8"))
expected_ids = {t["id"] for t in expected["teams"]}
missing = []
duplicates = []
inconsistent = []
seen_urls = defaultdict(list)
seen_names = defaultdict(list)
counts = Counter()
by_team = {}
for team, players in teams.items():
    team_complete = 0
    local_names = Counter()
    for player in players:
        counts["players"] += 1
        name = player.get("name", "")
        url = player.get("url", "")
        local_names[name.casefold()] += 1
        if url: seen_urls[url].append((team, name))
        seen_names[name.casefold()].append((team, name))
        attrs = player.get("attributes") or {}
        absent = [k for k in DETAILED_LABELS if attrs.get(k) is None]
        bad = {k: v for k, v in attrs.items() if not isinstance(v, int) or not 0 <= v <= 100}
        general_missing = [k for k in CATEGORY_LABELS if player.get(k) is None]
        if not absent: team_complete += 1; counts["complete_detailed"] += 1
        if absent or general_missing or player.get("detail_error"):
            missing.append({"team":team,"name":name,"missing_detailed":absent,"missing_general":general_missing,"error":player.get("detail_error")})
        if bad: inconsistent.append({"team":team,"name":name,"invalid_attributes":bad})
        if player.get("overall") is not None and not 0 <= player["overall"] <= 100:
            inconsistent.append({"team":team,"name":name,"invalid_overall":player["overall"]})
        if not name or not url:
            inconsistent.append({"team":team,"name":name,"missing_identity":True})
    by_team[team] = {"players":len(players),"complete_detailed":team_complete}
    for name, count in local_names.items():
        if count > 1: duplicates.append({"type":"same_team_name","team":team,"name":name,"count":count})
for url, entries in seen_urls.items():
    if len(entries)>1: duplicates.append({"type":"same_url","url":url,"entries":entries})
for name, entries in seen_names.items():
    if len(entries)>1: duplicates.append({"type":"same_name_across_teams","name":name,"entries":entries})
result = {
    "expected_teams":len(expected_ids),"teams_present":len(teams),
    "missing_teams":sorted(expected_ids-set(teams)),
    "unexpected_teams":sorted(set(teams)-expected_ids),
    "totals":dict(counts),"by_team":by_team,
    "players_with_missing_values":missing,
    "duplicates":duplicates,"inconsistencies":inconsistent,
    "complete":len(teams)==30 and all(by_team[t]["players"]>0 for t in expected_ids if t in by_team) and not missing and not duplicates and not inconsistent
}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in result.items() if k not in ("players_with_missing_values","duplicates","inconsistencies","by_team")},indent=2))
print("Missing player records:",len(missing),"duplicates:",len(duplicates),"inconsistencies:",len(inconsistent))
