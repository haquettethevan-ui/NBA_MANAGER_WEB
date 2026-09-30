from server import *
import os
from multiplayer_db import *
from season_calendar import generate_calendar
from season_runner import simulate_next_day, _load_team_state
from main import OFFENSE_FOCUSES, DEFENSE_FOCUSES, normalize_tactics
from http.cookies import SimpleCookie

init_db()

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
        if parsed.path in ("/api/league/roster","/api/league/rotation","/api/league/calendar","/api/league/standings","/api/league/dashboard"):
            u=self.auth()
            if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
            lid=int(q.get("league_id",[0])[0]);m=membership(u["id"],lid)
            if not m:return self.send_json(403,{"success":False,"message":"Tu n'appartiens pas à cette ligue."})
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
                return self.send_json(200,{"success":True,"team_id":tid,"record":row,"next_game":next_game,"last_game":played[-1] if played else None,"injuries":injuries,"tired":tired,"opponent":opponent,"events":injury_events(lid),"league_name":m["name"],"invite_code":m["invite_code"]})
            if not m.get("team_id"):return self.send_json(400,{"success":False,"message":"Choisis d'abord ton équipe."})
            team,_=build_team(m["team_id"])
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
                return self.send_json(200,{"success":True,**simulate_next_day(lid)})
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
                    team,_=build_team(m["team_id"]);by={p.name:p for p in team.roster}
                    starters=[x["name"] for x in payload["rotation"] if x.get("starter")]
                    if len(starters)!=5:raise ValueError("Il faut exactement 5 titulaires.")
                    if any(n not in by for n in starters):raise ValueError("Titulaire inconnu.")
                    team.starters=[by[n] for n in starters];team.bench=[x for x in team.roster if x not in team.starters]
                    rotation_rows=[{"name":x["name"],"minutes":int(x.get("minutes",0)),"starter":bool(x.get("starter"))} for x in payload["rotation"]]
                    # Exact validation with the same minute-by-minute rotation engine used by the preview.
                    rotation_preview(m["team_id"],rotation_rows)
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
if __name__=="__main__":main()
