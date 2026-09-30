import datetime, random

def season_pairs(team_ids):
    """82 games/team: every opponent home+away (58), plus 12 opponents twice more (24)."""
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

def generate_calendar(team_ids,start_date="2026-10-20",seed=56):
    """Balanced 82-game calendar with one game/team per round and NBA-like rest spacing."""
    start=datetime.date.fromisoformat(start_date);rng=random.Random(seed)
    games=season_pairs(team_ids);rng.shuffle(games)
    # Edge-color greedily into conflict-free rounds.
    rounds=[]
    for game in games:
        h,a=game;placed=False
        order=list(range(len(rounds)));rng.shuffle(order)
        for idx in order:
            used=rounds[idx][1]
            if h not in used and a not in used:
                rounds[idx][0].append(game);used|={h,a};placed=True;break
        if not placed:rounds.append(([game],{h,a}))
    # Sort denser rounds first, then assign one round every 1-3 calendar days.
    rounds.sort(key=lambda x:len(x[0]),reverse=True)
    rows=[];date=start
    for i,(slate,_) in enumerate(rounds):
        if i:
            # Mostly one rest day (2-day gap), with occasional B2B and 2 rest days.
            x=rng.random()
            gap=1 if x<.10 else (3 if x>.88 else 2)
            date+=datetime.timedelta(days=gap)
        for h,a in slate:rows.append((date.isoformat(),h,a))
    return rows
