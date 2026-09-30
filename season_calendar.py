import datetime, json, random, urllib.request

NBA_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"

def season_pairs(team_ids):
    ids=list(team_ids); pairs=[]
    for i in range(len(ids)):
        for j in range(i+1,len(ids)):
            pairs.extend([(ids[i],ids[j]),(ids[j],ids[i])])
    extra=set()
    for i in range(len(ids)):
        for d in range(1,7):
            extra.add(tuple(sorted((ids[i],ids[(i+d)%len(ids)]))))
    for a,b in sorted(extra):
        pairs.extend([(a,b),(b,a)])
    return pairs

def _official_calendar(team_ids):
    """Charge le calendrier NBA publié. Retourne uniquement la saison régulière 2026-27."""
    req=urllib.request.Request(NBA_SCHEDULE_URL,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=12) as response:
        data=json.load(response)
    allowed=set(team_ids); rows=[]
    for day in data.get("leagueSchedule",{}).get("gameDates",[]):
        for game in day.get("games",[]):
            home=game.get("homeTeam",{}).get("teamTricode")
            away=game.get("awayTeam",{}).get("teamTricode")
            date=(game.get("gameDateEst") or day.get("gameDate") or "")[:10]
            if home not in allowed or away not in allowed or not date:
                continue
            # La saison régulière 2026-27 va du 20/10/2026 au 12/04/2027.
            if "2026-10-20" <= date <= "2027-04-12":
                rows.append((date,home,away))
    # Une vraie saison régulière doit contenir 1230 matchs.
    unique=list(dict.fromkeys(rows))
    if len(unique) < 1200:
        raise ValueError("Calendrier NBA officiel incomplet.")
    return sorted(unique)

def _fallback_calendar(team_ids,start_date="2026-10-20",seed=56):
    start=datetime.date.fromisoformat(start_date);rng=random.Random(seed)
    games=season_pairs(team_ids);rng.shuffle(games);rounds=[]
    for game in games:
        h,a=game;placed=False
        order=list(range(len(rounds)));rng.shuffle(order)
        for idx in order:
            used=rounds[idx][1]
            if h not in used and a not in used:
                rounds[idx][0].append(game);used|={h,a};placed=True;break
        if not placed:rounds.append(([game],{h,a}))
    rounds.sort(key=lambda x:len(x[0]),reverse=True)
    rows=[];date=start
    for i,(slate,_) in enumerate(rounds):
        if i:
            x=rng.random();gap=1 if x<.10 else (3 if x>.88 else 2)
            date+=datetime.timedelta(days=gap)
        for h,a in slate:rows.append((date.isoformat(),h,a))
    return rows

def generate_calendar(team_ids,start_date="2026-10-20",seed=56):
    try:
        return _official_calendar(team_ids)
    except Exception:
        return _fallback_calendar(team_ids,start_date,seed)
