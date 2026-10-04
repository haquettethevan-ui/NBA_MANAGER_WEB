from server import *
import os, threading, time, datetime
from multiplayer_db import *
from season_calendar import generate_calendar
from season_runner import simulate_next_day, _load_team_state
from main import OFFENSE_FOCUSES, DEFENSE_FOCUSES, normalize_tactics, perimeter_defense, interior_defense
from engine_v55 import energy_factor_from_value
from finance_rules import SALARY_CAP_2026_27, LUXURY_TAX_2026_27, FIRST_APRON_2026_27, SECOND_APRON_2026_27, salary_for_row, payroll_zone, validate_trade_salary
from http.cookies import SimpleCookie

init_db()

def seed_finances(league_id):
    rows={tid:[{"name":r["name"],"salary":salary_for_row(r)} for r in complete_players(tid)] for tid in [x["id"] for x in TEAM_META]}
    ensure_league_rosters(league_id,rows)

def league_team(league_id,team_id):
    seed_finances(league_id)
    entries=roster_entries(league_id,team_id)
    return build_team(team_id,[x["player_name"] for x in entries])


def _primary_position(row):
    return str(row.get("position") or "").split("/")[0].strip().upper()

def _trade_health_multiplier(state):
    days=int((state or {}).get("injury_days") or 0)
    if days>=60:return 0.62
    if days>=30:return 0.72
    if days>=14:return 0.82
    if days>=7:return 0.90
    return 1.0

def trade_asset_value(row,state=None):
    """Market value = current level + 2K potential; team needs are applied separately."""
    o=float(row.get("overall") or 70)
    pot=float(row.get("potential") or o)
    # Potential is deliberately secondary to current ability, but becomes meaningful
    # for young/high-upside assets. Never punish a player because POT is missing.
    upside=max(0.0,pot-o)
    value=max(1.0,(o-60.0)**2)
    # 2K POT is a ceiling, not an age-adjusted market projection.
    # Convert that ceiling into future trade value only when the player's age
    # makes meaningful development plausible. Missing age stays neutral.
    age=row.get("age")
    age_factor=1.0
    if age is not None:
        age=float(age)
        if age<=21: age_factor=1.35
        elif age<=23: age_factor=1.20
        elif age<=25: age_factor=1.00
        elif age<=27: age_factor=0.70
        elif age<=29: age_factor=0.40
        elif age<=31: age_factor=0.20
        else: age_factor=0.0
    value*=1.0 + min(0.42, upside*0.022*age_factor)
    # Age also matters when POT is already close to OVR: young stars retain
    # more long-term asset value, while older players gradually lose resale value.
    if age is not None:
        if age<=21: value*=1.12
        elif age<=23: value*=1.08
        elif age<=25: value*=1.04
        elif age>=38: value*=0.72
        elif age>=35: value*=0.80
        elif age>=33: value*=0.88
        elif age>=31: value*=0.95
    salary=salary_for_row(row)
    if o<84 and salary>20_000_000:value*=0.88
    value*=_trade_health_multiplier(state)
    if row.get("expiring_2026_27") is True:
        # Expiring contracts are less valuable, but stars retain substantial rental value.
        value*=0.88 if o>=88 else 0.78
    return value

def _position_fit_multiplier(roster_rows,incoming_row,outgoing_names=()):
    """Reward filling a weak position and penalize piling talent onto one position."""
    pos=_primary_position(incoming_row)
    if not pos:return 1.0
    remaining=[r for r in roster_rows if r.get("name") not in set(outgoing_names)]
    same=sorted([float(r.get("overall") or 70) for r in remaining if _primary_position(r)==pos],reverse=True)
    o=float(incoming_row.get("overall") or 70)
    if not same:return 1.12
    if same[0]>=o+2:return 0.86
    if len(same)>=2 and same[1]>=o-2:return 0.78
    if same[0]<=o-5:return 1.08
    return 1.0

def _team_is_top3_league(league_id,team_id):
    rows=standings(league_id)
    if not rows:return False
    ranked=sorted(rows,key=lambda x:(x["w"],x["pf"]-x["pa"]),reverse=True)
    return any(x["team_id"]==team_id for x in ranked[:3])

def _team_is_conference_leader(league_id,team_id):
    rows=standings(league_id)
    if not rows:return False
    meta={x["id"]:x for x in TEAM_META};conf=meta.get(team_id,{}).get("conference")
    same=[x for x in rows if meta.get(x["team_id"],{}).get("conference")==conf]
    same.sort(key=lambda x:(x["w"],x["pf"]-x["pa"]),reverse=True)
    return bool(same) and same[0]["team_id"]==team_id

def _team_need_multiplier(league_id,team_id,roster_rows,incoming_row,outgoing_names=()):
    """Reward a player who directly improves the receiving team's weakest basketball area."""
    attrs=("outside_scoring","inside_scoring","playmaking","defense","rebounding")
    remaining=[r for r in roster_rows if r.get("name") not in set(outgoing_names)]
    core=sorted(remaining,key=lambda r:float(r.get("overall") or 0),reverse=True)[:8]
    if not core:return 1.0
    avgs={a:sum(float(r.get(a) or 0) for r in core)/len(core) for a in attrs}
    weak=min(attrs,key=avgs.get)
    incoming=float(incoming_row.get(weak) or 0)
    improvement=incoming-avgs[weak]
    if improvement<=0:return 1.0
    # A non-leading team is more willing to act when the incoming player fixes
    # its clearest weakness. Conference leaders stay conservative.
    cap=0.16 if not _team_is_conference_leader(league_id,team_id) else 0.07
    return 1.0 + min(cap, improvement*0.008)

def validate_ai_trade(league_id,ai_team,send_names,receive_names):
    by_name={r["name"]:r for rows in PLAYER_DB.values() for r in rows}
    rm=league_roster_map(league_id)
    roster_names=[x["player_name"] for x in rm.get(ai_team,[])]
    roster=[by_name[n] for n in roster_names if n in by_name]
    states=player_states(league_id,ai_team)
    outgoing=sum(trade_asset_value(by_name[n],states.get(n)) for n in send_names if n in by_name)
    incoming=0.0
    for n in receive_names:
        if n not in by_name:continue
        row=by_name[n]
        incoming+=trade_asset_value(row,None)*_position_fit_multiplier(roster,row,send_names)*_team_need_multiplier(league_id,ai_team,roster,row,send_names)
    if outgoing<=0 or incoming<=0:raise ValueError("Selection de trade invalide.")
    required=1.0
    elite_record=_team_is_top3_league(league_id,ai_team) or _team_is_conference_leader(league_id,ai_team)
    if elite_record:required=1.12
    # Trading away a star requires a premium even when aggregate raw value is similar.
    best_out=max([float(by_name[n].get("overall") or 0) for n in send_names if n in by_name] or [0])
    if best_out>=90:required=max(required,1.15)
    elif best_out>=86:required=max(required,1.08)
    # Young high-upside cornerstone assets require a real premium too.
    # 2K POT alone is not enough: age gates the protection.
    cornerstone=False
    for n in send_names:
        row=by_name.get(n,{})
        age=row.get("age")
        pot=float(row.get("potential") or row.get("overall") or 0)
        o=float(row.get("overall") or 0)
        if age is not None and float(age)<=23 and pot>=92 and o>=82:
            cornerstone=True
            break
    if cornerstone:required=max(required,1.18)
    if incoming < outgoing*required:
        gap=round((outgoing*required-incoming)/(outgoing*required)*100)
        reason="équipe Top 3 NBA ou leader de conférence, donc plus réticente à modifier son effectif" if elite_record else "valeur sportive insuffisante"
        raise ValueError(f"Trade refuse par l'IA : {reason} (écart estimé {gap} %).")
    return {"offered_value":round(incoming,1),"requested_value":round(outgoing,1),"required_ratio":required,"top3_league":_team_is_top3_league(league_id,ai_team),"conference_leader":_team_is_conference_leader(league_id,ai_team)}

def rotation_coach_advice(league_id,team_id):
    """Compare current minutes with projected energy-adjusted player quality and suggest conservative minute transfers."""
    team,_=league_team(league_id,team_id)
    saved=load_rotation(league_id,team_id)
    payload=(saved or {}).get("payload",{}) if isinstance(saved,dict) else {}
    rotation=payload.get("rotation",[]) or []
    minutes={x.get("name"):int(x.get("minutes",0) or 0) for x in rotation}
    ng=next((g for g in games_for(league_id) if g["status"]=="scheduled" and team_id in (g["home_team"],g["away_team"])),None)
    if ng: team=_load_team_state(league_id,team_id,ng["game_date"])
    states=player_states(league_id,team_id)
    rows=[]
    for p in team.roster:
        st=states.get(p.name,{})
        energy=float(getattr(p,"energy",st.get("energy",100)) or 100)
        injury=int(getattr(p,"injury_days",st.get("injury_days",0)) or 0)
        mins=minutes.get(p.name,0)
        # Energy-adjusted effective OVR: fatigue matters enough to make a fresh backup preferable in real cases.
        effective=float(p.overall)*energy_factor_from_value(energy)
        rows.append({"name":p.name,"position":p.position,"overall":p.overall,"energy":round(energy,1),"minutes":mins,"effective":round(effective,1),"injury_days":injury,"player":p})
    suggestions=[]
    active=[x for x in rows if not x["injury_days"]]
    def positions(x):
        try:return set(eligible_positions(x["player"].position))
        except Exception:return {z.strip() for z in str(x["position"]).replace("-","/").split("/") if z.strip()}
    # Flag overworked players only when a compatible backup is now effectively better or very close and much fresher.
    for x in sorted(active,key=lambda z:z["minutes"],reverse=True):
        if x["minutes"]<26:continue
        backups=[b for b in active if b["name"]!=x["name"] and b["minutes"]<x["minutes"] and positions(x)&positions(b)]
        if not backups:continue
        b=max(backups,key=lambda z:z["effective"])
        gap=b["effective"]-x["effective"]; fresh=b["energy"]-x["energy"]
        if gap>=0 or (x["energy"]<80 and gap>=-2.0 and fresh>=10):
            delta=min(6,max(2,int(round((max(0,gap)+max(0,fresh)/8)))))
            delta=min(delta,x["minutes"]-20,48-b["minutes"])
            if delta>=2:suggestions.append({"type":"reduce","from":x["name"],"to":b["name"],"minutes":delta,"reason":f"{x['name']} est à {x['energy']:.0f}% d'énergie (OVR effectif {x['effective']:.1f}) contre {b['name']} à {b['energy']:.0f}% (OVR effectif {b['effective']:.1f}). Le backup peut prendre une partie de ses minutes sans dégrader la rotation."})
    # Also reward underused fresh talent even when the starter is not critically tired.
    for b in sorted(active,key=lambda z:(z["effective"],z["energy"]),reverse=True):
        if b["minutes"]>=24 or b["energy"]<88:continue
        donors=[x for x in active if x["name"]!=b["name"] and x["minutes"]>=24 and positions(x)&positions(b) and x["effective"]<=b["effective"]+1.0]
        if donors:
            x=min(donors,key=lambda z:(z["effective"],z["energy"]))
            delta=min(4,x["minutes"]-20,28-b["minutes"])
            if delta>=2:suggestions.append({"type":"increase","from":x["name"],"to":b["name"],"minutes":delta,"reason":f"{b['name']} est frais ({b['energy']:.0f}%) et son niveau projeté ({b['effective']:.1f}) est comparable ou supérieur à {x['name']} ({x['effective']:.1f}). Il peut prendre davantage de responsabilités."})
    # Deduplicate player pairs and keep advice readable.
    out=[];seen=set()
    for s in suggestions:
        sig=(s["from"],s["to"])
        if sig in seen:continue
        seen.add(sig);out.append(s)
        if len(out)>=4:break
    return {"players":[{k:v for k,v in x.items() if k!="player"} for x in rows],"suggestions":out,"has_saved_rotation":bool(rotation),"next_game_date":ng["game_date"] if ng else None}

def trade_coach_advice(league_id,team_id,max_suggestions=4):
    """Return only trades that pass the exact salary, roster and AI-acceptance checks used by /api/league/trade."""
    seed_finances(league_id)
    rm=league_roster_map(league_id)
    by_name={r["name"]:r for rows in PLAYER_DB.values() for r in rows}
    mine=[by_name[x["player_name"]] for x in rm.get(team_id,[]) if x["player_name"] in by_name]
    if not mine:return {"weakness":None,"suggestions":[]}
    attrs={"outside":"outside_scoring","inside":"inside_scoring","playmaking":"playmaking","defense":"defense","rebounding":"rebounding","athleticism":"athleticism"}
    labels={"outside":"tir extérieur","inside":"finition intérieure","playmaking":"création","defense":"défense","rebounding":"rebond","athleticism":"athlétisme"}
    def profile(rows):
        core=sorted(rows,key=lambda r:float(r.get("overall") or 0),reverse=True)[:8]
        return {k:sum(float(r.get(a) or 0) for r in core)/max(1,len(core)) for k,a in attrs.items()}
    myp=profile(mine)
    league=[]
    for tm in TEAM_META:
        rows=[by_name[x["player_name"]] for x in rm.get(tm["id"],[]) if x["player_name"] in by_name]
        if rows:league.append(profile(rows))
    pct={k:100*sum(p[k]<=myp[k] for p in league)/max(1,len(league)) for k in attrs}
    weak=min(attrs,key=lambda k:pct[k])
    # Recent poor results increase urgency, but do not invent a different weakness without box-score evidence.
    recent=team_recent_games(league_id,team_id,5); wins=losses=0
    for g in recent:
        try:
            r=g.get("result") or {}; hs=float(r.get("home_score",r.get("score_home",0)) or 0); aws=float(r.get("away_score",r.get("score_away",0)) or 0)
            if not hs and not aws:continue
            scored=hs if g.get("home_team")==team_id else aws; allowed=aws if g.get("home_team")==team_id else hs
            wins+=scored>allowed;losses+=scored<=allowed
        except Exception:pass
    candidates=[]
    humans=_human_team_ids(league_id)
    before_a=sum(x["salary"] for x in rm.get(team_id,[]))
    # Search 1-for-1 first: every displayed proposal is executable by the current engine.
    send_pool=sorted(mine,key=lambda r:(float(r.get(attrs[weak]) or 0),float(r.get("overall") or 0)))[:10]
    for tm in TEAM_META:
        other=tm["id"]
        if other==team_id or other in humans:continue
        theirs=[by_name[x["player_name"]] for x in rm.get(other,[]) if x["player_name"] in by_name]
        before_b=sum(x["salary"] for x in rm.get(other,[]))
        targets=sorted(theirs,key=lambda r:(float(r.get(attrs[weak]) or 0),float(r.get("overall") or 0)),reverse=True)[:10]
        for give in send_pool:
            for get in targets:
                improvement=float(get.get(attrs[weak]) or 0)-float(give.get(attrs[weak]) or 0)
                if improvement<4:continue
                try:
                    sa=next(x["salary"] for x in rm.get(team_id,[]) if x["player_name"]==give["name"])
                    sb=next(x["salary"] for x in rm.get(other,[]) if x["player_name"]==get["name"])
                    validate_trade_salary(before_a,sa,sb,1);validate_trade_salary(before_b,sb,sa,1)
                    ev=validate_ai_trade(league_id,other,[get["name"]],[give["name"]])
                    names_a=[x["player_name"] for x in rm.get(team_id,[]) if x["player_name"]!=give["name"]]+[get["name"]]
                    names_b=[x["player_name"] for x in rm.get(other,[]) if x["player_name"]!=get["name"]]+[give["name"]]
                    build_team(team_id,names_a);build_team(other,names_b)
                    score=improvement+max(0,float(get.get("overall") or 0)-float(give.get("overall") or 0))*.5
                    candidates.append((score,{"other_team":other,"send":[give["name"]],"receive":[get["name"]],"target":labels[weak],"improvement":round(improvement,1),"reason":f"{get['name']} améliore directement ton {labels[weak]} ({float(get.get(attrs[weak]) or 0):.0f}) par rapport à {give['name']} ({float(give.get(attrs[weak]) or 0):.0f}). Ce trade respecte les règles salariales et passe l'évaluation actuelle de l'IA."}))
                except Exception:continue
    candidates.sort(key=lambda x:x[0],reverse=True)
    picked=[];seen=set()
    for _,x in candidates:
        sig=(x["other_team"],tuple(x["send"]),tuple(x["receive"]))
        if sig in seen:continue
        seen.add(sig);picked.append(x)
        if len(picked)>=max_suggestions:break
    return {"weakness":{"key":weak,"label":labels[weak],"rating":round(myp[weak],1),"percentile":round(pct[weak],1)},"recent_form":{"games":wins+losses,"wins":wins,"losses":losses},"suggestions":picked}


def _human_team_ids(league_id):
    return {x["team_id"] for x in league_members(league_id) if x.get("team_id")}

def generate_ai_trade_offers(league_id,max_offers=1):
    """Generate a small number of conservative AI-initiated offers per simulated day."""
    import random
    seed_finances(league_id)
    humans=_human_team_ids(league_id)
    rm=league_roster_map(league_id)
    by_name={r["name"]:r for rows in PLAYER_DB.values() for r in rows}
    ai_teams=[x["id"] for x in TEAM_META if x["id"] not in humans]
    random.shuffle(ai_teams)
    created=[]
    for ai in ai_teams:
        if len(created)>=max_offers:break
        own=[by_name[x["player_name"]] for x in rm.get(ai,[]) if x["player_name"] in by_name]
        if not own:continue
        # Prefer moving a player from a crowded primary position.
        counts={}
        for r in own:counts[_primary_position(r)]=counts.get(_primary_position(r),0)+1
        movable=sorted(own,key=lambda r:(counts.get(_primary_position(r),0),-float(r.get("overall") or 0)),reverse=True)
        targets=list(humans)
        random.shuffle(targets)
        for human in targets:
            theirs=[by_name[x["player_name"]] for x in rm.get(human,[]) if x["player_name"] in by_name]
            if not theirs:continue
            candidates=[]
            for give in movable[:8]:
                for want in theirs:
                    if _primary_position(want)==_primary_position(give):continue
                    try:
                        before_ai=sum(x["salary"] for x in rm.get(ai,[]));before_h=sum(x["salary"] for x in rm.get(human,[]))
                        sg=salary_for_row(give);sw=salary_for_row(want)
                        validate_trade_salary(before_ai,sg,sw,1);validate_trade_salary(before_h,sw,sg,1)
                        ai_eval=validate_ai_trade(league_id,ai,[give["name"]],[want["name"]])
                        # Human side gets the same sanity check so AI cannot dump bad value.
                        human_eval=validate_ai_trade(league_id,human,[want["name"]],[give["name"]])
                        candidates.append((ai_eval["offered_value"]/max(1,ai_eval["requested_value"]),give,want))
                    except Exception:continue
            if candidates:
                _,give,want=max(candidates,key=lambda x:x[0])
                reason=f"{ai} cherche à rééquilibrer son effectif au poste de {_primary_position(want)}."
                oid=create_trade_offer(league_id,ai,human,[give["name"]],[want["name"]],reason)
                if oid:
                    created.append({"id":oid,"from_team":ai,"to_team":human,"send":[give["name"]],"receive":[want["name"]],"reason":reason})
                    break
    return created


_SIM_LOCK=threading.Lock()

def advance_league_day(league_id):
    with _SIM_LOCK:
        if not any(g["status"]=="scheduled" for g in games_for(league_id)):
            raise ValueError("Aucun match programmé à simuler.")
        result=simulate_next_day(league_id)
        result["trade_offers"]=generate_ai_trade_offers(league_id,1)
        reset_ready(league_id)
        return result

def _daily_scheduler():
    from zoneinfo import ZoneInfo
    paris=ZoneInfo("Europe/Paris")
    while True:
        try:
            nowp=datetime.datetime.now(paris)
            if nowp.hour>=18:
                for lid in all_league_ids():
                    if any(g["status"]=="scheduled" for g in games_for(lid)) and daily_run_due(lid,nowp.date().isoformat()):
                        try:
                            advance_league_day(lid)
                            mark_daily_run(lid,nowp.date().isoformat())
                        except Exception as e:print("Daily simulation error",lid,e)
        except Exception as e:print("Scheduler error",e)
        time.sleep(60)

class MultiplayerServer(Server):
    def auth(self):
        h=self.headers.get("Authorization","")
        token=h[7:] if h.startswith("Bearer ") else ""
        return user_from_token(token)
    def body(self):
        n=int(self.headers.get("Content-Length","0"));return json.loads(self.rfile.read(n).decode("utf-8") or "{}")
    def do_GET(self):
        parsed=urlparse(self.path); q=parse_qs(parsed.query)
        if self.path=="/health":
            return self.send_json(200,{"status":"ok","version":"V61"})
        if self.path=="/":
            self.send_response(302);self.send_header("Location","/NBA_MANAGER_INTERFACE/multiplayer.html");self.end_headers();return
        if self.path=="/api/me":
            u=self.auth()
            if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
            return self.send_json(200,{"success":True,"user":u,"leagues":leagues_for(u["id"])})
        if self.path=="/api/teams":
            return self.send_json(200,{"success":True,"teams":team_catalog()})
        if parsed.path=="/api/players":
            u=self.auth()
            if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
            lid=int(parse_qs(parsed.query).get("league_id",[0])[0] or 0)
            current_team={}
            if lid:
                seed_finances(lid)
                for tid,entries in league_roster_map(lid).items():
                    for e in entries:current_team[e["player_name"]]=tid
            players=[]
            for original_team,rows in PLAYER_DB.items():
                for r in rows:
                    if not all(r.get(key) is not None for key in REQUIRED_RATINGS):continue
                    players.append({
                        "name":r.get("name"),"team_id":current_team.get(r.get("name"),original_team),
                        "position":r.get("position"),"overall":r.get("overall"),
                        "potential":r.get("potential"),"potential_grade":r.get("potential_grade"),
                        "outside":r.get("outside_scoring"),"inside":r.get("inside_scoring"),
                        "athleticism":r.get("athleticism"),"playmaking":r.get("playmaking"),
                        "defense":r.get("defense"),"rebounding":r.get("rebounding"),"stamina":r.get("stamina")
                    })
            players.sort(key=lambda x:(-(float(x.get("overall") or 0)),x.get("name") or ""))
            return self.send_json(200,{"success":True,"players":players})
        if self.path=="/api/game-config":
            return self.send_json(200,{"success":True,"offense":list(OFFENSE_FOCUSES),"defense":list(DEFENSE_FOCUSES)})
        if parsed.path in ("/api/league/roster","/api/league/rotation","/api/league/calendar","/api/league/results","/api/league/standings","/api/league/dashboard","/api/league/finances","/api/league/rotation-coach","/api/league/trade-coach","/api/league/trade-offers","/api/league/ready-status"):
            u=self.auth()
            if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
            lid=int(q.get("league_id",[0])[0]);m=membership(u["id"],lid)
            if not m:return self.send_json(403,{"success":False,"message":"Tu n'appartiens pas à cette ligue."})
            seed_finances(lid)
            if parsed.path=="/api/league/ready-status":
                s=ready_status(lid);s["me_ready"]=next((x["ready"] for x in s["members"] if x["user_id"]==u["id"]),False)
                return self.send_json(200,{"success":True,**s})
            if parsed.path=="/api/league/trade-offers":
                tid=m.get("team_id")
                if not tid:return self.send_json(400,{"success":False,"message":"Choisis d’abord ton équipe."})
                return self.send_json(200,{"success":True,"offers":pending_trade_offers(lid,tid)})
            if parsed.path=="/api/league/rotation-coach":
                tid=m.get("team_id")
                if not tid:return self.send_json(400,{"success":False,"message":"Choisis d'abord ton équipe."})
                return self.send_json(200,{"success":True,**rotation_coach_advice(lid,tid)})
            if parsed.path=="/api/league/trade-coach":
                tid=m.get("team_id")
                if not tid:return self.send_json(400,{"success":False,"message":"Choisis d'abord ton équipe."})
                return self.send_json(200,{"success":True,**trade_coach_advice(lid,tid)})
            if parsed.path=="/api/league/finances":
                tid=m.get("team_id")
                if not tid:return self.send_json(400,{"success":False,"message":"Choisis d'abord ton équipe."})
                rm=league_roster_map(lid);allrows={r["name"]:r for rows0 in PLAYER_DB.values() for r in rows0}
                def pack(team_id):
                    entries=rm.get(team_id,[]);payroll=sum(x["salary"] for x in entries)
                    players=[{"name":e["player_name"],"salary":e["salary"],"overall":allrows.get(e["player_name"],{}).get("overall",0),"position":allrows.get(e["player_name"],{}).get("position","")} for e in entries]
                    return {"team_id":team_id,"payroll":payroll,"cap_space":max(0,SALARY_CAP_2026_27-payroll),"over_cap":payroll>SALARY_CAP_2026_27,"payroll_zone":payroll_zone(payroll),"players":players}
                return self.send_json(200,{"success":True,"salary_cap":SALARY_CAP_2026_27,"luxury_tax":LUXURY_TAX_2026_27,"first_apron":FIRST_APRON_2026_27,"second_apron":SECOND_APRON_2026_27,"my_team":pack(tid),"teams":[pack(x["id"]) for x in TEAM_META if x["id"]!=tid]})
            if parsed.path=="/api/league/calendar":
                games=games_for(lid)
                # result_json contient le box score complet. On ne l'envoie que
                # pour les matchs du manager afin de garder les autres résultats légers.
                import json
                tid=m.get("team_id")
                for g in games:
                    if g["status"]=="played" and tid in (g["home_team"],g["away_team"]) and g.get("result_json"):
                        try:g["result"]=json.loads(g["result_json"])
                        except Exception:g["result"]=None
                    g.pop("result_json",None)
                return self.send_json(200,{"success":True,"games":games,"members":league_members(lid)})
            if parsed.path=="/api/league/results":
                import json
                tid=m.get("team_id"); mine=[]; others=[]
                for g in games_for(lid):
                    if g["status"]!="played":continue
                    row={k:v for k,v in g.items() if k!="result_json"}
                    if tid and tid in (g["home_team"],g["away_team"]):
                        try:row["result"]=json.loads(g["result_json"]) if g.get("result_json") else None
                        except Exception:row["result"]=None
                        mine.append(row)
                    else:others.append(row)
                mine.reverse();others.reverse()
                return self.send_json(200,{"success":True,"team_id":tid,"my_games":mine,"other_games":others[:100]})
            if parsed.path=="/api/league/standings":
                rows=standings(lid);meta={x["id"]:x for x in TEAM_META};return self.send_json(200,{"success":True,"standings":[{**x,"conference":meta.get(x["team_id"],{}).get("conference","")} for x in rows]})
            if parsed.path=="/api/league/dashboard":
                games=games_for(lid);st=standings(lid);tid=m.get("team_id")
                played=[g for g in games if g["status"]=="played" and tid in (g["home_team"],g["away_team"])] if tid else []
                upcoming=[g for g in games if g["status"]=="scheduled" and tid in (g["home_team"],g["away_team"])] if tid else []
                states=player_states(lid,tid) if tid else {};next_game=upcoming[0] if upcoming else None
                projected=states
                if tid and next_game:
                    pt=_load_team_state(lid,tid,next_game["game_date"])
                    projected={p.name:{"energy":getattr(p,"energy",100),"workload":getattr(p,"workload",0),"injury_days":getattr(p,"injury_days",0),"injury_label":getattr(p,"injury_label","")} for p in pt.roster}
                row=next((x for x in st if x["team_id"]==tid),{"w":0,"l":0,"pf":0,"pa":0})
                injuries=[{"name":n,"days":x.get("injury_days",0),"label":x.get("injury_label","")} for n,x in projected.items() if x.get("injury_days",0)>0]
                tired=sorted([{"name":n,"energy":round(x.get("energy",100),1),"workload":round(x.get("workload",0),1)} for n,x in projected.items()],key=lambda x:x["energy"])[:5]
                opponent=None
                if next_game and tid:
                    oid=next_game["away_team"] if next_game["home_team"]==tid else next_game["home_team"]
                    os=player_states(lid,oid)
                    ot,_=league_team(lid,oid)
                    mt,_=league_team(lid,tid)
                    # Keep offensive and defensive scouting strictly separate.
                    # Our offense attacks THEIR defensive weaknesses; our defense counters THEIR offensive strengths.
                    off_keys=("outside","inside","playmaking")
                    def_keys=("perimeter_def","interior_def","rebounding")
                    labels={"outside":"tir extérieur","inside":"jeu intérieur","playmaking":"création",
                            "perimeter_def":"défense extérieure","interior_def":"protection intérieure","rebounding":"rebond défensif"}
                    def team_profile(team):
                        core=sorted(team.roster,key=lambda p:getattr(p,"overall",0),reverse=True)[:8]
                        n=max(1,len(core))
                        return {
                            "outside":sum(float(getattr(p,"outside_scoring",0) or 0) for p in core)/n,
                            "inside":sum(float(getattr(p,"inside_scoring",0) or 0) for p in core)/n,
                            "playmaking":sum(float(getattr(p,"playmaking",0) or 0) for p in core)/n,
                            "perimeter_def":sum(float(perimeter_defense(p)) for p in core)/n,
                            "interior_def":sum(float(interior_defense(p)) for p in core)/n,
                            "rebounding":sum(float(getattr(p,"rebounding",0) or 0) for p in core)/n}
                    opp_base=team_profile(ot); my_base=team_profile(mt)
                    league_profiles=[]
                    for meta_team in TEAM_META:
                        try:
                            lt,_=league_team(lid,meta_team["id"]); league_profiles.append(team_profile(lt))
                        except Exception: pass
                    def percentile(k,v):
                        vals=sorted(x[k] for x in league_profiles)
                        return 100.0*sum(x<=v for x in vals)/max(1,len(vals))
                    pct={k:percentile(k,opp_base[k]) for k in (*off_keys,*def_keys)}
                    recent=team_recent_games(lid,oid,5)
                    rw=rl=0; pf=pa=0.0; rn=0
                    for rg in recent:
                        try:
                            res=rg.get("result") or {}
                            hs=float(res.get("home_score",res.get("score_home",0)) or 0); aws=float(res.get("away_score",res.get("score_away",0)) or 0)
                            if not hs and not aws: continue
                            home=rg.get("home_team")==oid; scored=hs if home else aws; allowed=aws if home else hs
                            pf+=scored;pa+=allowed;rn+=1
                            if scored>allowed: rw+=1
                            else: rl+=1
                        except Exception: pass
                    recent_net=(pf-pa)/rn if rn else 0.0
                    injury_names=[p.name for p in ot.roster if os.get(p.name,{}).get("injury_days",0)>0]
                    # Offensive recommendation: choose the opponent's weakest DEFENSIVE area,
                    # with a small bonus when our own corresponding attack is strong.
                    attack_fit={
                        "perimeter_def":my_base["outside"],
                        "interior_def":max(my_base["inside"],my_base["playmaking"]*.92),
                        "rebounding":sum(float(getattr(p,"rebounding",0) or 0) for p in sorted(mt.roster,key=lambda p:getattr(p,"overall",0),reverse=True)[:8])/max(1,len(sorted(mt.roster,key=lambda p:getattr(p,"overall",0),reverse=True)[:8]))}
                    def_vulnerability={k:(100.0-pct[k])+.20*max(-20.0,min(20.0,(attack_fit[k]-opp_base[k])*2.0)) for k in def_keys}
                    weak_def=max(def_vulnerability,key=def_vulnerability.get)
                    off_map={"perimeter_def":"Tir extérieur","interior_def":"Pénétration","rebounding":"Rebond offensif"}
                    off_rec=off_map[weak_def]
                    # Defensive recommendation: identify the opponent's strongest OFFENSIVE area only.
                    strength_off=max(off_keys,key=lambda k:pct[k])
                    def_map={"outside":"Défense extérieure","inside":"Protection du cercle","playmaking":"Pression porteur"}
                    def_rec=def_map[strength_off]
                    rank=lambda k:1+sum(x[k]>opp_base[k] for x in league_profiles)
                    injury_txt=(f" Absences importantes prises en compte : {', '.join(injury_names[:3])}." if injury_names else "")
                    form_txt=(f" Sur les {rn} derniers matchs : {rw}V-{rl}D, différentiel moyen {recent_net:+.1f} pts." if rn else " Pas encore assez de matchs récents pour pondérer la forme.")
                    metrics={k:round(opp_base[k],1) for k in (*off_keys,*def_keys)}
                    advisor={"metrics":metrics,
                        "strength":{"key":strength_off,"label":labels[strength_off],"value":round(opp_base[strength_off],1)},
                        "weakness":{"key":weak_def,"label":labels[weak_def],"value":round(opp_base[weak_def],1)},
                        "offense":{"tactic":off_rec,"reason":f"Faiblesse défensive ciblée : {labels[weak_def]}. L'adversaire est classé {rank(weak_def)}e/{len(league_profiles)} dans ce secteur défensif (percentile {pct[weak_def]:.0f}). Le conseil offensif vise uniquement une faiblesse défensive adverse.{form_txt}{injury_txt}"},
                        "defense":{"tactic":def_rec,"reason":f"Force offensive à contenir : {labels[strength_off]}. L'adversaire est classé {rank(strength_off)}e/{len(league_profiles)} offensivement dans ce secteur (percentile {pct[strength_off]:.0f}). Le conseil défensif vise uniquement une force offensive adverse.{injury_txt}"},
                        "league_percentiles":{k:round(v,1) for k,v in pct.items()},
                        "vulnerability":{k:round(v,1) for k,v in def_vulnerability.items()},
                        "matchup":{k:round(v,1) for k,v in def_vulnerability.items()},
                        "recent_form":{"games":rn,"wins":rw,"losses":rl,"net_rating_proxy":round(recent_net,1)}}
                    opponent={"team_id":oid,"last_results":recent,"injuries":[{"name":n,"days":x["injury_days"],"label":x["injury_label"]} for n,x in os.items() if x["injury_days"]>0],"advisor":advisor}
                return self.send_json(200,{"success":True,"team_id":tid,"record":row,"next_game":next_game,"last_game":played[-1] if played else None,"injuries":injuries,"tired":tired,"opponent":opponent,"events":injury_events(lid),"transactions":transaction_events(lid),"league_name":m["name"],"invite_code":m["invite_code"]})
            if not m.get("team_id"):return self.send_json(400,{"success":False,"message":"Choisis d'abord ton équipe."})
            team,_=league_team(lid,m["team_id"])
            if parsed.path=="/api/league/roster":
                if not m.get("team_id"):return self.send_json(400,{"success":False,"message":"Choisis d’abord ton équipe."})
                team,_=league_team(lid,m["team_id"])
                saved=load_rotation(lid,m["team_id"]);states=player_states(lid,m["team_id"])
                ng=next((g for g in games_for(lid) if g["status"]=="scheduled" and m["team_id"] in (g["home_team"],g["away_team"])),None)
                if ng:
                    team=_load_team_state(lid,m["team_id"],ng["game_date"])
                    states={p.name:{"energy":getattr(p,"energy",100),"workload":getattr(p,"workload",0),"injury_days":getattr(p,"injury_days",0),"injury_label":getattr(p,"injury_label","")} for p in team.roster}
                allrows={r["name"]:r for rows0 in PLAYER_DB.values() for r in rows0}
                return self.send_json(200,{"success":True,"team_id":m["team_id"],"next_game_date":ng["game_date"] if ng else None,"players":[{"name":x.name,"position":x.position,"overall":x.overall,"potential":allrows.get(x.name,{}).get("potential"),"potential_grade":allrows.get(x.name,{}).get("potential_grade"),"role":x.role,"outside":x.outside_scoring,"inside":x.inside_scoring,"playmaking":x.playmaking,"defense":x.defense,"rebounding":x.rebounding,"stamina":x.stamina,"energy":round(states.get(x.name,{}).get("energy",100),1),"workload":round(states.get(x.name,{}).get("workload",0),1),"injury_days":states.get(x.name,{}).get("injury_days",0),"injury_label":states.get(x.name,{}).get("injury_label","")} for x in team.roster],"saved":saved})

            return self.send_json(200,{"success":True,"saved":load_rotation(lid,m["team_id"])})
        return super().do_GET()
    def do_POST(self):
        try:
            if self.path in ("/api/auto-rotation","/api/rotation-preview"):
                u=self.auth()
                if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
                b=self.body();lid=int(b.get("league_id",0));m=membership(u["id"],lid)
                if not m or not m.get("team_id"):return self.send_json(403,{"success":False,"message":"Ligue ou équipe invalide."})
                team,_=league_team(lid,m["team_id"])
                if self.path=="/api/auto-rotation":
                    starters,rotation=build_auto_rotation_minutes(team);starter_names={p.name for p in starters};set_rotation_plan(team,rotation)
                    rows=[{"name":p.name,"position":p.position,"overall":p.overall,"role":p.role,"minutes":rotation[p.name],"starter":p.name in starter_names} for p in team.roster]
                    return self.send_json(200,{"success":True,"players":rows,"timeline":roster_timeline_from_team(team),"rotation_diagnostics":rotation_diagnostics(team)})
                timeline=rotation_preview(m["team_id"],b.get("rotation",[]),[p.name for p in team.roster])
                return self.send_json(200,{"success":True,"timeline":timeline})
            if self.path=="/api/leagues/delete":
                u=self.auth()
                if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
                b=self.body();lid=int(b.get("league_id",0));m=membership(u["id"],lid)
                if not m or m.get("owner_id")!=u["id"]:return self.send_json(403,{"success":False,"message":"Seul le propriétaire peut supprimer cette ligue."})
                delete_league(lid,u["id"])
                return self.send_json(200,{"success":True,"message":"Ligue supprimée."})
            if self.path=="/api/league/ready":
                u=self.auth()
                if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
                b=self.body();lid=int(b.get("league_id",0));m=membership(u["id"],lid)
                if not m or not m.get("team_id"):return self.send_json(403,{"success":False,"message":"Choisis d'abord ton équipe."})
                if not any(g["status"]=="scheduled" for g in games_for(lid)):raise ValueError("Aucun prochain match n'est programmé.")
                set_ready(lid,u["id"],True);s=ready_status(lid)
                simulated=False;result=None
                if all_ready(lid):
                    try:
                        result=advance_league_day(lid);simulated=True;s=ready_status(lid)
                    except Exception as sim_ex:
                        # Do not leave the league stuck at N/N ready after a failed simulation.
                        reset_ready(lid)
                        print("Ready simulation error",lid,repr(sim_ex),flush=True)
                        raise
                return self.send_json(200,{"success":True,"message":"Tous les managers étaient prêts : la journée a été simulée." if simulated else "Tu es prêt pour la prochaine journée.","simulated":simulated,"result":result,**s})
            if self.path in ("/api/league/trade-offer/accept","/api/league/trade-offer/reject"):
                u=self.auth()
                if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
                b=self.body();offer=trade_offer(int(b.get("offer_id",0)))
                if not offer:return self.send_json(404,{"success":False,"message":"Offre introuvable."})
                m=membership(u["id"],offer["league_id"])
                if not m or m.get("team_id")!=offer["to_team"]:return self.send_json(403,{"success":False,"message":"Cette offre ne t'est pas destinée."})
                if offer["status"]!="pending":raise ValueError("Cette offre n'est plus disponible.")
                if self.path.endswith("/reject"):
                    set_trade_offer_status(offer["id"],"rejected");return self.send_json(200,{"success":True,"message":"Offre refusée."})
                seed_finances(offer["league_id"]);rm=league_roster_map(offer["league_id"])
                a=offer["from_team"];bteam=offer["to_team"];pa=offer["send"];pb=offer["receive"]
                before_a=sum(x["salary"] for x in rm.get(a,[]));before_b=sum(x["salary"] for x in rm.get(bteam,[]))
                sa=sum(x["salary"] for x in rm.get(a,[]) if x["player_name"] in pa);sb=sum(x["salary"] for x in rm.get(bteam,[]) if x["player_name"] in pb)
                validate_trade_salary(before_a,sa,sb,len(pa));validate_trade_salary(before_b,sb,sa,len(pb))
                validate_ai_trade(offer["league_id"],a,pa,pb)
                names_a=[x["player_name"] for x in rm.get(a,[]) if x["player_name"] not in pa]+pb
                names_b=[x["player_name"] for x in rm.get(bteam,[]) if x["player_name"] not in pb]+pa
                build_team(a,names_a);build_team(bteam,names_b)
                result=execute_trade(offer["league_id"],a,pa,bteam,pb);set_trade_offer_status(offer["id"],"accepted")
                return self.send_json(200,{"success":True,"message":"Trade accepté.","trade":result})
            if self.path=="/api/league/trade":
                u=self.auth()
                if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
                b=self.body();lid=int(b.get("league_id",0));m=membership(u["id"],lid)
                if not m or not m.get("team_id"):return self.send_json(403,{"success":False,"message":"Accès refusé."})
                seed_finances(lid);a=m["team_id"];other=str(b.get("other_team",""))
                if not other or other==a:raise ValueError("Choisis une autre équipe.")
                pa=list(dict.fromkeys(b.get("send",[])));pb=list(dict.fromkeys(b.get("receive",[])))
                rm=league_roster_map(lid)
                before_a=sum(x["salary"] for x in rm.get(a,[]));before_b=sum(x["salary"] for x in rm.get(other,[]))
                sa=sum(x["salary"] for x in rm.get(a,[]) if x["player_name"] in pa);sb=sum(x["salary"] for x in rm.get(other,[]) if x["player_name"] in pb)
                validate_trade_salary(before_a,sa,sb,len(pa));validate_trade_salary(before_b,sb,sa,len(pb))
                ai_eval=validate_ai_trade(lid,other,pb,pa)
                names_a=[x["player_name"] for x in rm.get(a,[]) if x["player_name"] not in pa]+pb
                names_b=[x["player_name"] for x in rm.get(other,[]) if x["player_name"] not in pb]+pa
                build_team(a,names_a);build_team(other,names_b)
                result=execute_trade(lid,a,pa,other,pb)
                return self.send_json(200,{"success":True,"message":"Trade validé. Les rotations des deux équipes ont été réinitialisées.","trade":result,"evaluation":ai_eval})
            if self.path=="/api/register":
                b=self.body();uid=create_user(b.get("username",""),b.get("password",""));token,u=login(b["username"],b["password"])
                return self.send_json(200,{"success":True,"token":token,"user":{"id":uid,"username":b["username"]}})
            if self.path=="/api/login":
                b=self.body();token,u=login(b.get("username",""),b.get("password",""))
                return self.send_json(200,{"success":True,"token":token,"user":{"id":u["id"],"username":u["username"]}})
            if self.path=="/api/league/simulate-next":
                u=self.auth()
                if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
                b=self.body();lid=int(b.get("league_id",0));m=membership(u["id"],lid)
                if not m or m["owner_id"]!=u["id"]:return self.send_json(403,{"success":False,"message":"Seul l'hôte peut avancer la saison."})
                result=advance_league_day(lid);return self.send_json(200,{"success":True,**result})
            if self.path in ("/api/league/rotation/save","/api/league/calendar/generate"):
                u=self.auth()
                if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
                b=self.body();lid=int(b.get("league_id",0));m=membership(u["id"],lid)
                if not m:return self.send_json(403,{"success":False,"message":"Accès refusé."})
                if self.path.endswith("rotation/save"):
                    if not m.get("team_id"):raise ValueError("Choisis d'abord ton équipe.")
                    payload={"rotation":b.get("rotation",[]),"tactics":normalize_tactics(b.get("tactics",{}))}
                    total=sum(int(x.get("minutes",0)) for x in payload["rotation"])
                    if total!=240:raise ValueError("La rotation doit totaliser exactement 240 minutes.")
                    team,_=league_team(lid,m["team_id"]);by={p.name:p for p in team.roster}
                    starters=[x["name"] for x in payload["rotation"] if x.get("starter")]
                    if len(starters)!=5:raise ValueError("Il faut exactement 5 titulaires.")
                    if any(n not in by for n in starters):raise ValueError("Titulaire inconnu.")
                    team.starters=[by[n] for n in starters];team.bench=[x for x in team.roster if x not in team.starters]
                    rotation_rows=[{"name":x["name"],"minutes":int(x.get("minutes",0)),"starter":bool(x.get("starter"))} for x in payload["rotation"]]
                    # Exact validation with the same minute-by-minute rotation engine used by the preview.
                    rotation_preview(m["team_id"],rotation_rows,[p.name for p in team.roster])
                    set_rotation_plan(team,{x["name"]:int(x.get("minutes",0)) for x in payload["rotation"]})
                    diag=rotation_diagnostics(team)
                    if not diag.get("valid"):raise ValueError("Rotation impossible : la couverture PG/SG/SF/PF/C n'est pas valide sur 48 minutes.")
                    save_rotation(lid,m["team_id"],payload);return self.send_json(200,{"success":True,"message":"Rotation et tactiques sauvegardées.","rotation_diagnostics":diag})
                if m["owner_id"]!=u["id"]:return self.send_json(403,{"success":False,"message":"Seul le créateur de la ligue peut générer le calendrier."})
                rows=generate_calendar([x["id"] for x in TEAM_META],b.get("start_date","2026-10-20"),lid)
                clear_games(lid);insert_games(lid,rows)
                return self.send_json(200,{"success":True,"games":len(rows),"source":getattr(generate_calendar,"last_source","")})
            if self.path in ("/api/leagues/create","/api/leagues/join","/api/leagues/team"):
                u=self.auth()
                if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
                b=self.body()
                if self.path.endswith("/create"):
                    lid,code=create_league(u["id"],b.get("name",""));return self.send_json(200,{"success":True,"league_id":lid,"invite_code":code})
                if self.path.endswith("/join"):
                    lid=join_league(u["id"],b.get("code",""));return self.send_json(200,{"success":True,"league_id":lid})
                choose_team(u["id"],int(b["league_id"]),b["team_id"]);return self.send_json(200,{"success":True})
            return super().do_POST()
        except Exception as ex:return self.send_json(400,{"success":False,"message":str(ex)})

def main():
    port=int(os.environ.get("PORT","8000"))
    httpd=ThreadingHTTPServer(("0.0.0.0",port),MultiplayerServer);httpd.daemon_threads=True
    print("NBA MANAGER V61 — production-ready server")
    print(f"Listening on 0.0.0.0:{port}")
    httpd.serve_forever()
threading.Thread(target=_daily_scheduler,daemon=True).start()

if __name__=="__main__":main()
