import json, pathlib, urllib.request, datetime

OUT=pathlib.Path("data/nba_schedule_2026_27.json")
TEAMS={"ATL","BOS","BKN","CHA","CHI","CLE","DAL","DEN","DET","GSW","HOU","IND","LAC","LAL","MEM","MIA","MIL","MIN","NOP","NYK","OKC","ORL","PHI","PHX","POR","SAC","SAS","TOR","UTA","WAS"}

def fetch_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)

def from_espn():
    games=[];d=datetime.date(2026,10,20);end=datetime.date(2027,4,11)
    while d<=end:
        data=fetch_json("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?limit=100&dates="+d.strftime("%Y%m%d"))
        for ev in data.get("events",[]):
            comp=(ev.get("competitions") or [{}])[0];home=away=None
            for x in comp.get("competitors",[]):
                abbr=x.get("team",{}).get("abbreviation")
                if x.get("homeAway")=="home":home=abbr
                elif x.get("homeAway")=="away":away=abbr
            if home in TEAMS and away in TEAMS:games.append({"date":d.isoformat(),"home":home,"away":away})
        d+=datetime.timedelta(days=1)
    return games

games=from_espn()
games=list({(g["date"],g["home"],g["away"]):g for g in games}.values());games.sort(key=lambda g:(g["date"],g["home"],g["away"]))
if len(games)<1150:raise RuntimeError(f"Schedule looks incomplete: {len(games)} known games")
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps({"season":"2026-27","source":"cached NBA schedule","games":games},ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")
print(f"Saved {len(games)} known regular-season games to {OUT}")
