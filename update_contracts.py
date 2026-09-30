#!/usr/bin/env python3
"""Import verified NBA 2026-27 salaries into data/players_2k27.json.\n\nDesigned for the monthly GitHub Actions refresh.

Primary source: HoopsHype current salary table.
Fallback/verification source: Basketball-Reference contracts table.
Only exact/explicit alias matches are written. Unknown players keep no verified salary.
"""
from __future__ import annotations
import html, json, re, unicodedata, urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
PLAYERS=ROOT/"data"/"players_2k27.json"
REPORT=ROOT/"data"/"contracts_2026_27_report.json"
HH="https://hoops-hype-us-east1-664912083968.us-east1.run.app/salaries/players/"
BR="https://www.basketball-reference.com/contracts/players.html"
UA="Mozilla/5.0 NBA_MANAGER_WEB contract updater"

ALIASES={
 "g antetokounmpo":"giannis antetokounmpo",
 "nikola jokic":"nikola jokic",
 "cj mccollum":"cj mccollum",
 "c j mccollum":"cj mccollum",
 "pj washington":"pj washington",
 "p j washington":"pj washington",
 "dennis schroder":"dennis schroder",
 "kristaps porzingis":"kristaps porzingis",
 "r j barrett":"rj barrett",
 "nicolas claxton":"nic claxton",
 "v j edgecombe":"vj edgecombe",
 "royce o neale":"royce o neale",
 "day ron sharpe":"day ron sharpe",
 "de aaron fox":"de aaron fox",
 "de anthony melton":"de anthony melton",
 "de andre hunter":"de andre hunter",
 "ja kobe walter":"ja kobe walter",
 "g g jackson":"gg jackson",
 "bobby portis jr":"bobby portis",
 "bronny james jr":"bronny james",
}

def norm(s):
    s=unicodedata.normalize("NFKD",s or "").encode("ascii","ignore").decode().lower()
    s=s.replace("’","'").replace("."," ")
    s=re.sub(r"[^a-z0-9 ]+"," ",s)
    s=re.sub(r"\s+"," ",s).strip()
    return ALIASES.get(s,s)

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode("utf-8","ignore")

def clean(cell):
    cell=re.sub(r"<script.*?</script>|<style.*?</style>","",cell,flags=re.S|re.I)
    cell=re.sub(r"<[^>]+>"," ",cell)
    return re.sub(r"\s+"," ",html.unescape(cell)).strip()

def money(s):
    m=re.search(r"\$\s*([0-9][0-9,]*)",s or "")
    return int(m.group(1).replace(",","")) if m else None

def rows_from_html(doc):
    out=[]
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>",doc,flags=re.S|re.I):
        cells=[clean(x) for x in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>",tr,flags=re.S|re.I)]
        if len(cells)>=2: out.append(cells)
    return out

def parse_hoopshype(doc):
    contracts={}
    for cells in rows_from_html(doc):
        # rank may be first column; find first cell containing a player-like string before salaries
        salary_idx=next((i for i,x in enumerate(cells) if money(x) is not None),None)
        if salary_idx is None or salary_idx<1: continue
        name=cells[salary_idx-1]
        if name.lower() in {"player","2026-27"}: continue
        vals=[money(x) for x in cells[salary_idx:salary_idx+4]]
        if not vals or vals[0] is None: continue
        flags=[]
        for x in cells[salary_idx:salary_idx+4]:
            m=re.search(r"\b(P|T|Q|TW)\b",x)
            flags.append(m.group(1) if m else None)
        contracts[norm(name)]={"source_name":name,"salary_2026_27":vals[0],
            "salary_2027_28":vals[1] if len(vals)>1 else None,
            "salary_2028_29":vals[2] if len(vals)>2 else None,
            "salary_2029_30":vals[3] if len(vals)>3 else None,
            "contract_options":flags,"salary_source":"HoopsHype"}
    return contracts

def parse_bref(doc):
    contracts={}
    years=["2026_27","2027_28","2028_29","2029_30","2030_31","2031_32"]
    for cells in rows_from_html(doc):
        if len(cells)<4: continue
        # BR: rank, player, team, 2026-27, 2027-28 ... 2031-32, guaranteed.
        vals=[money(cells[3+i]) if len(cells)>3+i else None for i in range(len(years))]
        if vals[0] is None: continue
        name=cells[1]
        row={"source_name":name,"team":cells[2],"salary_source":"Basketball-Reference"}
        for y,v in zip(years,vals): row["salary_"+y]=v
        active=[i for i,v in enumerate(vals) if v is not None]
        row["contract_end_season"]=f"{2026+max(active)}-{str(27+max(active)).zfill(2)}" if active else None
        row["contract_years_remaining"]=len(active)
        row["expiring_2026_27"]=bool(vals[0] is not None and all(v is None for v in vals[1:]))
        contracts[norm(name)]=row
    return contracts

def main():
    data=json.loads(PLAYERS.read_text(encoding="utf-8"))
    hh={}; br={}; errors=[]
    try: hh=parse_hoopshype(fetch(HH))
    except Exception as e: errors.append("HoopsHype: "+repr(e))
    try: br=parse_bref(fetch(BR))
    except Exception as e: errors.append("Basketball-Reference: "+repr(e))
    if not hh and not br:
        raise SystemExit("No contract source could be loaded: "+"; ".join(errors))

    matched=[]; unmatched=[]; disagreements=[]
    for team,players in data["players"].items():
        for p in players:
            key=norm(p.get("name"))
            h=hh.get(key); b=br.get(key)
            chosen=h or b
            if h and b and h["salary_2026_27"]!=b["salary_2026_27"]:
                disagreements.append({"player":p["name"],"hoopshype":h["salary_2026_27"],"basketball_reference":b["salary_2026_27"]})
                # Prefer current HoopsHype table, but preserve disagreement for review.
            if chosen:
                for k,v in chosen.items():
                    if k.startswith("salary_") or k in {"contract_options","salary_source","contract_end_season","contract_years_remaining","expiring_2026_27"}: p[k]=v
                p["salary_verified"]=True
                p["salary_checked_at"]=datetime.now(timezone.utc).date().isoformat()
                matched.append({"player":p["name"],"team_2k":team,"salary":p["salary_2026_27"],"source":p["salary_source"]})
            else:
                for k in ["salary_2026_27","salary_2027_28","salary_2028_29","salary_2029_30","salary_2030_31","salary_2031_32","contract_options","salary_source","salary_checked_at","contract_end_season","contract_years_remaining","expiring_2026_27"]:
                    p.pop(k,None)
                p["salary_verified"]=False
                unmatched.append({"player":p["name"],"team_2k":team,"overall":p.get("overall")})

    data["contracts_updated_at"]=datetime.now(timezone.utc).isoformat()
    data["contracts_sources"]=[HH,BR]
    PLAYERS.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report={"updated_at":data["contracts_updated_at"],"matched":len(matched),"unmatched":len(unmatched),
      "source_counts":{"hoopshype":len(hh),"basketball_reference":len(br)},
      "errors":errors,"disagreements":disagreements,
      "unmatched_over_75":sorted([x for x in unmatched if int(x.get("overall") or 0)>75],key=lambda x:-int(x.get("overall") or 0)),
      "unmatched":unmatched}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ["matched","unmatched","source_counts","errors"]},ensure_ascii=False))
    print("Unmatched OVR >75:",len(report["unmatched_over_75"]))

if __name__=="__main__": main()
