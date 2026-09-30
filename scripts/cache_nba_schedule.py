import json, pathlib, urllib.request

URL="https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
OUT=pathlib.Path("data/nba_schedule_2026_27.json")
TEAMS={"ATL","BOS","BKN","CHA","CHI","CLE","DAL","DEN","DET","GSW","HOU","IND","LAC","LAL","MEM","MIA","MIL","MIN","NOP","NYK","OKC","ORL","PHI","PHX","POR","SAC","SAS","TOR","UTA","WAS"}

req=urllib.request.Request(URL,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json","Referer":"https://www.nba.com/"})
with urllib.request.urlopen(req,timeout=30) as r:data=json.load(r)
games=[]
for day in data.get("leagueSchedule",{}).get("gameDates",[]):
    for g in day.get("games",[]):
        home=g.get("homeTeam",{}).get("teamTricode");away=g.get("awayTeam",{}).get("teamTricode")
        date=(g.get("gameDateEst") or day.get("gameDate") or "")[:10]
        if home in TEAMS and away in TEAMS and "2026-10-20"<=date<="2027-04-11":
            games.append({"date":date,"home":home,"away":away})
games=list({(g["date"],g["home"],g["away"]):g for g in games}.values())
games.sort(key=lambda g:(g["date"],g["home"],g["away"]))
if len(games)<1150:raise RuntimeError(f"Schedule looks incomplete: {len(games)} known games")
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps({"season":"2026-27","source":"NBA official schedule","games":games},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(f"Saved {len(games)} known regular-season games to {OUT}")
