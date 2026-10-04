import sqlite3, hashlib, secrets, datetime, os
from pathlib import Path

DATA_ROOT=Path(os.environ.get("NBA_MANAGER_DATA_DIR", Path(__file__).resolve().parent/"data"))
DATA_ROOT.mkdir(parents=True,exist_ok=True)
DB_PATH=DATA_ROOT/"nba_manager.db"

def connect():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); return c

def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          salt TEXT NOT NULL,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(
          token TEXT PRIMARY KEY,user_id INTEGER NOT NULL,created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS leagues(
          id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,invite_code TEXT UNIQUE NOT NULL,
          owner_id INTEGER NOT NULL,created_at TEXT NOT NULL,
          FOREIGN KEY(owner_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS league_members(
          league_id INTEGER NOT NULL,user_id INTEGER NOT NULL,team_id TEXT,
          PRIMARY KEY(league_id,user_id),UNIQUE(league_id,team_id),
          FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS saved_rotations(
          league_id INTEGER NOT NULL,team_id TEXT NOT NULL,payload TEXT NOT NULL,
          updated_at TEXT NOT NULL,PRIMARY KEY(league_id,team_id));
        CREATE TABLE IF NOT EXISTS games(
          id INTEGER PRIMARY KEY AUTOINCREMENT,league_id INTEGER NOT NULL,
          game_date TEXT NOT NULL,home_team TEXT NOT NULL,away_team TEXT NOT NULL,
          home_score INTEGER,away_score INTEGER,status TEXT NOT NULL DEFAULT 'scheduled',
          result_json TEXT,FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS player_season_state(
          league_id INTEGER NOT NULL,team_id TEXT NOT NULL,player_name TEXT NOT NULL,
          energy REAL NOT NULL DEFAULT 100,workload REAL NOT NULL DEFAULT 0,
          injury_days INTEGER NOT NULL DEFAULT 0,injury_label TEXT NOT NULL DEFAULT '',
          last_game_date TEXT,PRIMARY KEY(league_id,team_id,player_name));
        CREATE TABLE IF NOT EXISTS league_rosters(
          league_id INTEGER NOT NULL,team_id TEXT NOT NULL,player_name TEXT NOT NULL,
          salary INTEGER NOT NULL DEFAULT 0,original_team_id TEXT NOT NULL,
          PRIMARY KEY(league_id,player_name));
        CREATE TABLE IF NOT EXISTS trade_offers(
          id INTEGER PRIMARY KEY AUTOINCREMENT,league_id INTEGER NOT NULL,
          from_team TEXT NOT NULL,to_team TEXT NOT NULL,send_json TEXT NOT NULL,receive_json TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,
          FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS league_daily_runs(
          league_id INTEGER NOT NULL,run_date TEXT NOT NULL,created_at TEXT NOT NULL,
          PRIMARY KEY(league_id,run_date),FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS league_ready(
          league_id INTEGER NOT NULL,user_id INTEGER NOT NULL,ready INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL,PRIMARY KEY(league_id,user_id),
          FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS transaction_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,league_id INTEGER NOT NULL,event_type TEXT NOT NULL,
          team_a TEXT NOT NULL,team_b TEXT NOT NULL,players_a_json TEXT NOT NULL,players_b_json TEXT NOT NULL,
          created_at TEXT NOT NULL,FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE);
        """)
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def _hash(password,salt): return hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),200000).hex()
def create_user(username,password):
    username=username.strip()
    if len(username)<3 or len(password)<6: raise ValueError("Pseudo ≥ 3 caractères et mot de passe ≥ 6 caractères.")
    salt=secrets.token_hex(16)
    with connect() as c:
        try:
            cur=c.execute("INSERT INTO users(username,password_hash,salt,created_at) VALUES(?,?,?,?)",(username,_hash(password,salt),salt,now()))
        except sqlite3.IntegrityError: raise ValueError("Ce pseudo existe déjà.")
        return cur.lastrowid
def login(username,password):
    with connect() as c:
        u=c.execute("SELECT * FROM users WHERE username=?",(username.strip(),)).fetchone()
        if not u or _hash(password,u["salt"])!=u["password_hash"]: raise ValueError("Identifiants incorrects.")
        token=secrets.token_urlsafe(32);c.execute("INSERT INTO sessions VALUES(?,?,?)",(token,u["id"],now()))
        return token,dict(u)
def user_from_token(token):
    if not token:return None
    with connect() as c:
        r=c.execute("""SELECT u.id,u.username FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?""",(token,)).fetchone()
        return dict(r) if r else None
def create_league(user_id,name):
    code=secrets.token_hex(3).upper()
    with connect() as c:
        cur=c.execute("INSERT INTO leagues(name,invite_code,owner_id,created_at) VALUES(?,?,?,?)",(name.strip() or "Ma ligue",code,user_id,now()))
        lid=cur.lastrowid;c.execute("INSERT INTO league_members(league_id,user_id) VALUES(?,?)",(lid,user_id))
        return lid,code
def join_league(user_id,code):
    with connect() as c:
        l=c.execute("SELECT id FROM leagues WHERE invite_code=?",(code.strip().upper(),)).fetchone()
        if not l: raise ValueError("Code de ligue inconnu.")
        c.execute("INSERT OR IGNORE INTO league_members(league_id,user_id) VALUES(?,?)",(l["id"],user_id));return l["id"]
def choose_team(user_id,league_id,team_id):
    with connect() as c:
        member=c.execute("SELECT team_id FROM league_members WHERE league_id=? AND user_id=?",(league_id,user_id)).fetchone()
        if not member: raise ValueError("Tu n'appartiens pas à cette ligue.")
        if member["team_id"]:
            if member["team_id"]==team_id:return
            raise ValueError("Ton équipe est verrouillée pour cette ligue.")
        try:c.execute("UPDATE league_members SET team_id=? WHERE league_id=? AND user_id=?",(team_id,league_id,user_id))
        except sqlite3.IntegrityError:raise ValueError("Cette équipe est déjà prise dans cette ligue.")
def leagues_for(user_id):
    with connect() as c:
        return [dict(r) for r in c.execute("""SELECT l.*,lm.team_id FROM leagues l JOIN league_members lm ON lm.league_id=l.id WHERE lm.user_id=? ORDER BY l.id DESC""",(user_id,))]

def membership(user_id,league_id):
    with connect() as c:
        r=c.execute("""SELECT lm.*,l.name,l.invite_code,l.owner_id FROM league_members lm JOIN leagues l ON l.id=lm.league_id WHERE lm.user_id=? AND lm.league_id=?""",(user_id,league_id)).fetchone()
        return dict(r) if r else None

def save_rotation(league_id,team_id,payload):
    import json
    with connect() as c:
        c.execute("""INSERT INTO saved_rotations(league_id,team_id,payload,updated_at) VALUES(?,?,?,?)
        ON CONFLICT(league_id,team_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at""",
        (league_id,team_id,json.dumps(payload,ensure_ascii=False),now()))

def load_rotation(league_id,team_id):
    import json
    with connect() as c:
        r=c.execute("SELECT payload,updated_at FROM saved_rotations WHERE league_id=? AND team_id=?",(league_id,team_id)).fetchone()
        if not r:return None
        return {"payload":json.loads(r["payload"]),"updated_at":r["updated_at"]}

def clear_games(league_id):
    with connect() as c:c.execute("DELETE FROM games WHERE league_id=?",(league_id,))

def insert_games(league_id,rows):
    with connect() as c:
        c.executemany("INSERT INTO games(league_id,game_date,home_team,away_team,status) VALUES(?,?,?,?,?)",
                      [(league_id,*r,"scheduled") for r in rows])

def games_for(league_id):
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM games WHERE league_id=? ORDER BY game_date,id",(league_id,))]

def league_members(league_id):
    with connect() as c:
        return [dict(r) for r in c.execute("""SELECT lm.user_id,lm.team_id,u.username FROM league_members lm JOIN users u ON u.id=lm.user_id WHERE lm.league_id=?""",(league_id,))]

def player_states(league_id,team_id):
    with connect() as c:
        return {r["player_name"]:dict(r) for r in c.execute("SELECT * FROM player_season_state WHERE league_id=? AND team_id=?",(league_id,team_id))}

def save_player_states(league_id,team_id,team,game_date):
    with connect() as c:
        for p in team.roster:
            c.execute("""INSERT INTO player_season_state(league_id,team_id,player_name,energy,workload,injury_days,injury_label,last_game_date)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(league_id,team_id,player_name) DO UPDATE SET
            energy=excluded.energy,workload=excluded.workload,injury_days=excluded.injury_days,
            injury_label=excluded.injury_label,last_game_date=excluded.last_game_date""",
            (league_id,team_id,p.name,float(getattr(p,"energy",100)),float(getattr(p,"workload",0)),
             int(getattr(p,"injury_days",0)),getattr(p,"injury_label",""),game_date))

def update_game_result(game_id,home_score,away_score,result):
    import json
    with connect() as c:c.execute("UPDATE games SET home_score=?,away_score=?,status='played',result_json=? WHERE id=?",
        (home_score,away_score,json.dumps(result,ensure_ascii=False),game_id))

def next_scheduled_date(league_id):
    with connect() as c:
        r=c.execute("SELECT MIN(game_date) d FROM games WHERE league_id=? AND status='scheduled'",(league_id,)).fetchone()
        return r["d"] if r and r["d"] else None

def games_on_date(league_id,date):
    with connect() as c:return [dict(r) for r in c.execute("SELECT * FROM games WHERE league_id=? AND game_date=? AND status='scheduled' ORDER BY id",(league_id,date))]

def standings(league_id):
    with connect() as c:
        games=[dict(r) for r in c.execute("SELECT home_team,away_team,home_score,away_score FROM games WHERE league_id=? AND status='played'",(league_id,))]
    d={}
    for g in games:
        for t in (g["home_team"],g["away_team"]):d.setdefault(t,{"team_id":t,"w":0,"l":0,"pf":0,"pa":0})
        h,a=g["home_team"],g["away_team"];hs,as_=g["home_score"],g["away_score"]
        d[h]["pf"]+=hs;d[h]["pa"]+=as_;d[a]["pf"]+=as_;d[a]["pa"]+=hs
        win,lose=(h,a) if hs>as_ else (a,h);d[win]["w"]+=1;d[lose]["l"]+=1
    return sorted(d.values(),key=lambda x:(x["w"],x["pf"]-x["pa"]),reverse=True)

def team_recent_games(league_id,team_id,limit=3):
    with connect() as c:
        return [dict(r) for r in c.execute("""SELECT * FROM games WHERE league_id=? AND status='played'
        AND (home_team=? OR away_team=?) ORDER BY game_date DESC,id DESC LIMIT ?""",(league_id,team_id,team_id,limit))]

def injury_events(league_id,limit=80):
    import json
    with connect() as c:
        rows=[dict(r) for r in c.execute("""SELECT game_date,home_team,away_team,result_json FROM games
        WHERE league_id=? AND status='played' AND result_json IS NOT NULL ORDER BY game_date DESC,id DESC""",(league_id,))]
    events=[]
    seen=set()
    for g in rows:
        try: result=json.loads(g["result_json"])
        except Exception: continue
        injuries=result.get("injuries",{})
        for team_id,items in ((g["home_team"],injuries.get("team1",[])),(g["away_team"],injuries.get("team2",[]))):
            for item in items or []:
                key=(g["game_date"],team_id,item.get("name"))
                if key in seen:continue
                seen.add(key)
                events.append({"date":g["game_date"],"team_id":team_id,"name":item.get("name",""),"label":item.get("type","Blessure"),"days":item.get("days",0)})
                if len(events)>=limit:return events
    return events


def ensure_league_rosters(league_id, team_rows):
    """Seed a league-specific roster once. team_rows: {team_id:[{name,salary}, ...]}."""
    with connect() as c:
        existing=c.execute("SELECT COUNT(*) n FROM league_rosters WHERE league_id=?",(league_id,)).fetchone()["n"]
        if existing:
            # Keep trades/team assignments intact and refresh contract values.
            # The master player database can gain players after a league was created:
            # add only names that are genuinely absent from this league, using their
            # current master team. Never move an existing player back to his original
            # team, otherwise completed trades would be overwritten.
            current={r["player_name"] for r in c.execute(
                "SELECT player_name FROM league_rosters WHERE league_id=?",(league_id,)
            )}
            for team_id,rows in team_rows.items():
                for row in rows:
                    player_name=row["name"]; salary=int(row.get("salary",0))
                    if player_name in current:
                        c.execute("UPDATE league_rosters SET salary=? WHERE league_id=? AND player_name=?",
                                  (salary,league_id,player_name))
                    else:
                        c.execute("""INSERT OR IGNORE INTO league_rosters
                            (league_id,team_id,player_name,salary,original_team_id)
                            VALUES(?,?,?,?,?)""",
                            (league_id,team_id,player_name,salary,team_id))
                        current.add(player_name)
            return
        for team_id,rows in team_rows.items():
            for row in rows:
                c.execute("INSERT OR IGNORE INTO league_rosters(league_id,team_id,player_name,salary,original_team_id) VALUES(?,?,?,?,?)",
                          (league_id,team_id,row["name"],int(row.get("salary",0)),team_id))

def roster_entries(league_id,team_id):
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM league_rosters WHERE league_id=? AND team_id=? ORDER BY salary DESC,player_name",(league_id,team_id))]

def league_roster_map(league_id):
    with connect() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM league_rosters WHERE league_id=?",(league_id,))]
    out={}
    for r in rows:out.setdefault(r["team_id"],[]).append(r)
    return out

def execute_trade(league_id,team_a,players_a,team_b,players_b):
    if not players_a or not players_b:raise ValueError("Chaque équipe doit envoyer au moins un joueur.")
    current=league_roster_map(league_id)
    after_a=len(current.get(team_a,[]))-len(set(players_a))+len(set(players_b))
    after_b=len(current.get(team_b,[]))-len(set(players_b))+len(set(players_a))
    if after_a<10 or after_b<10:
        raise ValueError(f"Trade refusé : chaque équipe doit conserver au moins 10 joueurs (après échange : {team_a} {after_a}, {team_b} {after_b}).")
    with connect() as c:
        def owned(team,names):
            q="SELECT player_name,salary FROM league_rosters WHERE league_id=? AND team_id=? AND player_name IN ("+",".join("?"*len(names))+")"
            rows=[dict(r) for r in c.execute(q,(league_id,team,*names))]
            if len(rows)!=len(set(names)):raise ValueError("Un joueur sélectionné n'appartient plus à cette équipe.")
            return rows
        a=owned(team_a,players_a);b=owned(team_b,players_b)
        for n in players_a:c.execute("UPDATE league_rosters SET team_id=? WHERE league_id=? AND team_id=? AND player_name=?",(team_b,league_id,team_a,n))
        for n in players_b:c.execute("UPDATE league_rosters SET team_id=? WHERE league_id=? AND team_id=? AND player_name=?",(team_a,league_id,team_b,n))
        c.execute("DELETE FROM saved_rotations WHERE league_id=? AND team_id IN (?,?)",(league_id,team_a,team_b))
        import json
        c.execute("INSERT INTO transaction_events(league_id,event_type,team_a,team_b,players_a_json,players_b_json,created_at) VALUES(?,?,?,?,?,?,?)",
                  (league_id,"trade",team_a,team_b,json.dumps(players_a,ensure_ascii=False),json.dumps(players_b,ensure_ascii=False),now()))
        return {"sent_a":sum(x["salary"] for x in a),"sent_b":sum(x["salary"] for x in b)}


def create_trade_offer(league_id,from_team,to_team,send_names,receive_names,reason=""):
    import json
    with connect() as c:
        exists=c.execute("SELECT id FROM trade_offers WHERE league_id=? AND from_team=? AND to_team=? AND status='pending'",(league_id,from_team,to_team)).fetchone()
        if exists:return None
        cur=c.execute("INSERT INTO trade_offers(league_id,from_team,to_team,send_json,receive_json,status,reason,created_at) VALUES(?,?,?,?,?,'pending',?,?)",
            (league_id,from_team,to_team,json.dumps(send_names,ensure_ascii=False),json.dumps(receive_names,ensure_ascii=False),reason,now()))
        return cur.lastrowid

def pending_trade_offers(league_id,to_team):
    import json
    with connect() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM trade_offers WHERE league_id=? AND to_team=? AND status='pending' ORDER BY id DESC",(league_id,to_team))]
    for r in rows:
        r["send"]=json.loads(r.pop("send_json"));r["receive"]=json.loads(r.pop("receive_json"))
    return rows

def trade_offer(offer_id):
    import json
    with connect() as c:r=c.execute("SELECT * FROM trade_offers WHERE id=?",(offer_id,)).fetchone()
    if not r:return None
    r=dict(r);r["send"]=json.loads(r.pop("send_json"));r["receive"]=json.loads(r.pop("receive_json"));return r

def set_trade_offer_status(offer_id,status):
    with connect() as c:c.execute("UPDATE trade_offers SET status=? WHERE id=?",(status,offer_id))


def transaction_events(league_id,limit=80):
    import json
    with connect() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM transaction_events WHERE league_id=? ORDER BY id DESC LIMIT ?",(league_id,limit))]
    for r in rows:
        r["players_a"]=json.loads(r.pop("players_a_json"));r["players_b"]=json.loads(r.pop("players_b_json"))
    return rows


def set_ready(league_id,user_id,ready=True):
    with connect() as c:
        c.execute("""INSERT INTO league_ready(league_id,user_id,ready,updated_at) VALUES(?,?,?,?)
        ON CONFLICT(league_id,user_id) DO UPDATE SET ready=excluded.ready,updated_at=excluded.updated_at""",
        (league_id,user_id,1 if ready else 0,now()))

def ready_status(league_id):
    members=league_members(league_id)
    with connect() as c:
        rows={r["user_id"]:bool(r["ready"]) for r in c.execute("SELECT user_id,ready FROM league_ready WHERE league_id=?",(league_id,))}
    active=[m for m in members if m.get("team_id")]
    return {"ready_count":sum(1 for m in active if rows.get(m["user_id"],False)),"total_count":len(active),
            "members":[{"user_id":m["user_id"],"username":m["username"],"team_id":m["team_id"],"ready":rows.get(m["user_id"],False)} for m in active]}

def reset_ready(league_id):
    with connect() as c:c.execute("UPDATE league_ready SET ready=0,updated_at=? WHERE league_id=?",(now(),league_id))

def all_ready(league_id):
    s=ready_status(league_id)
    return s["total_count"]>0 and s["ready_count"]==s["total_count"]

def all_league_ids():
    with connect() as c:return [r["id"] for r in c.execute("SELECT id FROM leagues")]


def daily_run_due(league_id,run_date):
    with connect() as c:return c.execute("SELECT 1 FROM league_daily_runs WHERE league_id=? AND run_date=?",(league_id,run_date)).fetchone() is None

def mark_daily_run(league_id,run_date):
    with connect() as c:c.execute("INSERT OR IGNORE INTO league_daily_runs(league_id,run_date,created_at) VALUES(?,?,?)",(league_id,run_date,now()))


def delete_league(league_id,user_id):
    with connect() as c:
        row=c.execute("SELECT owner_id FROM leagues WHERE id=?",(league_id,)).fetchone()
        if not row:raise ValueError("Ligue introuvable.")
        if row["owner_id"]!=user_id:raise PermissionError("Seul le propriétaire peut supprimer cette ligue.")
        c.execute("DELETE FROM leagues WHERE id=?",(league_id,))
