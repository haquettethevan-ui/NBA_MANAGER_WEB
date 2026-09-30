from server import *
import os, threading, time, datetime
from multiplayer_db import *
from season_calendar import generate_calendar
from season_runner import simulate_next_day, _load_team_state
from main import OFFENSE_FOCUSES, DEFENSE_FOCUSES, normalize_tactics
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
    """Context-free player value. Team fit is applied separately."""
    o=float(row.get("overall") or 70)
    value=max(1.0,(o-60.0)**2)
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

def _team_is_top5(league_id,team_id):
    rows=standings(league_id)
    if not rows:return False
    meta={x["id"]:x for x in TEAM_META};conf=meta.get(team_id,{}).get("conference")
    same=[x for x in rows if meta.get(x["team_id"],{}).get("conference")==conf]
    same.sort(key=lambda x:(x["w"],x["pf"]-x["pa"]),reverse=True)
    return any(x["team_id"]==team_id for x in same[:5])

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
        incoming+=trade_asset_value(row,None)*_position_fit_multiplier(roster,row,send_names)
    if outgoing<=0 or incoming<=0:raise ValueError("Selection de trade invalide.")
    required=1.0
    if _team_is_top5(league_id,ai_team):required=1.12
    # Trading away a star requires a premium even when aggregate raw value is similar.
    best_out=max([float(by_name[n].get("overall") or 0) for n in send_names if n in by_name] or [0])
    if best_out>=90:required=max(required,1.15)
    elif best_out>=86:required=max(required,1.08)
    if incoming < outgoing*required:
        gap=round((outgoing*required-incoming)/(outgoing*required)*100)
        reason="équipe Top 5, donc plus réticente à modifier son effectif" if _team_is_top5(league_id,ai_team) else "valeur sportive insuffisante"
        raise ValueError(f"Trade refuse par l'IA : {reason} (écart estimé {gap} %).")
    return {"offered_value":round(incoming,1),"requested_value":round(outgoing,1),"required_ratio":required,"top5":_team_is_top5(league_id,ai_team)}

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
        if self.path=="/api/game-config":
            return self.send_json(200,{"success":True,"offense":list(OFFENSE_FOCUSES),"defense":list(DEFENSE_FOCUSES)})
        parsed=urlparse(self.path); q=parse_qs(parsed.query)
        if parsed.path in ("/api/league/roster","/api/league/rotation","/api/league/calendar","/api/league/results","/api/league/standings","/api/league/dashboard","/api/league/finances","/api/league/trade-offers","/api/league/ready-status"):
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
                    projected={p.name:{"energy":p.energy,"workload":p.workload,"injury_days":p.injury_days,"injury_label":p.injury_label} for p in pt.roster}
                row=next((x for x in st if x["team_id"]==tid),{"w":0,"l":0,"pf":0,"pa":0})
                injuries=[{"name":n,"days":x.get("injury_days",0),"label":x.get("injury_label","")} for n,x in projected.items() if x.get("injury_days",0)>0]
                tired=sorted([{"name":n,"energy":round(x.get("energy",100),1),"workload":round(x.get("workload",0),1)} for n,x in projected.items()],key=lambda x:x["energy"])[:5]
                opponent=None
                if next_game and tid:
                    oid=next_game["away_team"] if next_game["home_team"]==tid else next_game["home_team"]
                    os=player_states(lid,oid)
                    opponent={"team_id":oid,"last_results":team_recent_games(lid,oid,3),"injuries":[{"name":n,"days":x["injury_days"],"label":x["injury_label"]} for n,x in os.items() if x["injury_days"]>0]}
                return self.send_json(200,{"success":True,"team_id":tid,"record":row,"next_game":next_game,"last_game":played[-1] if played else None,"injuries":injuries,"tired":tired,"opponent":opponent,"events":injury_events(lid),"transactions":transaction_events(lid),"league_name":m["name"],"invite_code":m["invite_code"]})
            if not m.get("team_id"):return self.send_json(400,{"success":False,"message":"Choisis d'abord ton équipe."})
            team,_=league_team(lid,m["team_id"])
            if parsed.path=="/api/league/roster":
                saved=load_rotation(lid,m["team_id"]);states=player_states(lid,m["team_id"])
                ng=next((g for g in games_for(lid) if g["status"]=="scheduled" and m["team_id"] in (g["home_team"],g["away_team"])),None)
                if ng:
                    team=_load_team_state(lid,m["team_id"],ng["game_date"])
                    states={p.name:{"energy":p.energy,"workload":p.workload,"injury_days":p.injury_days,"injury_label":p.injury_label} for p in team.roster}
                return self.send_json(200,{"success":True,"team_id":m["team_id"],"next_game_date":ng["game_date"] if ng else None,"players":[{"name":x.name,"position":x.position,"overall":x.overall,"role":x.role,"outside":x.outside_scoring,"inside":x.inside_scoring,"playmaking":x.playmaking,"defense":x.defense,"rebounding":x.rebounding,"stamina":x.stamina,"energy":round(states.get(x.name,{}).get("energy",100),1),"workload":round(states.get(x.name,{}).get("workload",0),1),"injury_days":states.get(x.name,{}).get("injury_days",0),"injury_label":states.get(x.name,{}).get("injury_label","")} for x in team.roster],"saved":saved})

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
            if self.path=="/api/league/ready":
                u=self.auth()
                if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
                b=self.body();lid=int(b.get("league_id",0));m=membership(u["id"],lid)
                if not m or not m.get("team_id"):return self.send_json(403,{"success":False,"message":"Choisis d'abord ton équipe."})
                if not any(g["status"]=="scheduled" for g in games_for(lid)):raise ValueError("Aucun prochain match n'est programmé.")
                set_ready(lid,u["id"],True);s=ready_status(lid)
                simulated=False;result=None
                if all_ready(lid):
                    result=advance_league_day(lid);simulated=True;s=ready_status(lid)
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
                return self.send_json(200,{"success":True,"games":len(rows)})
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
