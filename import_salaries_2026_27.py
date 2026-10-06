from __future__ import annotations
import html, json, re, time, unicodedata
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
DB=ROOT/"data"/"players_2k27.json"
REPORT=ROOT/"data"/"salary_import_report.json"
TEAM_IDS=["ATL","BOS","BKN","CHA","CHI","CLE","DAL","DEN","DET","GSW","HOU","IND","LAC","LAL","MEM","MIA","MIL","MIN","NOP","NYK","OKC","ORL","PHI","PHX","POR","SAC","SAS","TOR","UTA","WAS"]
URL="https://www.basketball-reference.com/contracts/{team}.html"
BREF_TEAM_ID={"PHX":"PHO","CHA":"CHO","BKN":"BRK"}

def fetch(url):
    req=Request(url,headers={"User-Agent":"Mozilla/5.0","Accept-Language":"en-US,en;q=0.9"})
    with urlopen(req,timeout=30) as r:return r.read().decode("utf-8","replace")

def clean_text(s):
    s=re.sub(r"<[^>]+>"," ",s); return " ".join(html.unescape(s).replace("\xa0"," ").split())

def norm(s):
    s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().lower()
    s=s.replace("’","'").replace("‘","'")
    s=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",s)
    return re.sub(r"[^a-z0-9]","",s)

def parse_team(team,doc):
    rows=[]
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>",doc,re.S|re.I):
        pm=re.search(r'data-stat="player"[^>]*>(.*?)</t[hd]>',tr,re.S|re.I)
        sm=re.search(r'data-stat="y1"[^>]*>(.*?)</t[hd]>',tr,re.S|re.I)
        if not pm or not sm: continue
        name=clean_text(pm.group(1)); salary_txt=clean_text(sm.group(1))
        digits=re.sub(r"[^0-9]","",salary_txt)
        if name and digits: rows.append({"name":name,"salary":int(digits),"team":team})
    return rows

db=json.loads(DB.read_text(encoding="utf-8"))
source=[]
errors=[]
for team in TEAM_IDS:
    try:
        source_team=BREF_TEAM_ID.get(team,team)
        rows=parse_team(team,fetch(URL.format(team=source_team)))
        if not rows: raise RuntimeError("no contract rows parsed")
        source.extend(rows); print(team,len(rows),flush=True); time.sleep(0.35)
    except Exception as e:
        errors.append({"team":team,"error":repr(e)}); print("ERROR",team,e,flush=True)

if errors:
    REPORT.write_text(json.dumps({"status":"failed","errors":errors},indent=2),encoding="utf-8")
    raise SystemExit("Salary import aborted: source fetch incomplete")

by_key={}
for r in source: by_key.setdefault(norm(r["name"]),[]).append(r)
matched=[]; unmatched=[]; ambiguous=[]
for team,players in db["players"].items():
    for p in players:
        candidates=by_key.get(norm(p["name"]),[])
        exact_team=[r for r in candidates if r["team"]==team]
        chosen=exact_team[0] if len(exact_team)==1 else (candidates[0] if len(candidates)==1 else None)
        if chosen:
            p["salary_2026_27"]=chosen["salary"]
            matched.append({"team":team,"name":p["name"],"source_name":chosen["name"],"salary_2026_27":chosen["salary"],"source_team":chosen["team"]})
        elif candidates:
            ambiguous.append({"team":team,"name":p["name"],"candidates":candidates})
        else:
            unmatched.append({"team":team,"name":p["name"]})

# Hard safety checks: never publish a suspicious scrape.
checks={"Stephen Curry":62587158,"Nikola Jokic":59033114,"Jayson Tatum":58456566}
flat={p["name"]:p for ps in db["players"].values() for p in ps}
for name,want in checks.items():
    got=flat.get(name,{}).get("salary_2026_27")
    if got!=want: raise SystemExit(f"Safety check failed for {name}: {got} != {want}")
if len(matched)<400: raise SystemExit(f"Safety check failed: only {len(matched)} players matched")

db["salary_source"]="Basketball-Reference 2026-27 contracts"
db["salary_season"]="2026-27"
DB.write_text(json.dumps(db,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
REPORT.write_text(json.dumps({"status":"ok","source_contracts":len(source),"matched":len(matched),"unmatched_count":len(unmatched),"ambiguous_count":len(ambiguous),"unmatched":unmatched,"ambiguous":ambiguous,"sample":matched[:20]},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("MATCHED",len(matched),"UNMATCHED",len(unmatched),"AMBIGUOUS",len(ambiguous),flush=True)

# Workflow trigger: salary data refresh
