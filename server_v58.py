from server import *
from multiplayer_db import *
from season_calendar import generate_calendar
from season_runner import simulate_next_day
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
        if self.path=="/api/me":
            u=self.auth()
            if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
            return self.send_json(200,{"success":True,"user":u,"leagues":leagues_for(u["id"])})
        if self.path=="/api/teams":
            return self.send_json(200,{"success":True,"teams":team_catalog()})
        parsed=urlparse(self.path); q=parse_qs(parsed.query)
        if parsed.path in ("/api/league/roster","/api/league/rotation","/api/league/calendar","/api/league/standings"):
            u=self.auth()
            if not u:return self.send_json(401,{"success":False,"message":"Non connecté."})
            lid=int(q.get("league_id",[0])[0]);m=membership(u["id"],lid)
            if not m:return self.send_json(403,{"success":False,"message":"Tu n'appartiens pas à cette ligue."})
            if parsed.path=="/api/league/calendar":
                return self.send_json(200,{"success":True,"games":games_for(lid),"members":league_members(lid)})
            if parsed.path=="/api/league/standings":
                return self.send_json(200,{"success":True,"standings":standings(lid)})
            if not m.get("team_id"):return self.send_json(400,{"success":False,"message":"Choisis d'abord ton équipe."})
            team,_=build_team(m["team_id"])
            if parsed.path=="/api/league/roster":
                saved=load_rotation(lid,m["team_id"]);states=player_states(lid,m["team_id"])
                return self.send_json(200,{"success":True,"team_id":m["team_id"],"players":[{"name":x.name,"position":x.position,"overall":x.overall,"role":x.role,"outside":x.outside_scoring,"inside":x.inside_scoring,"playmaking":x.playmaking,"defense":x.defense,"rebounding":x.rebounding,"stamina":x.stamina,"energy":round(states.get(x.name,{}).get("energy",100),1),"workload":round(states.get(x.name,{}).get("workload",0),1),"injury_days":states.get(x.name,{}).get("injury_days",0),"injury_label":states.get(x.name,{}).get("injury_label","")} for x in team.roster],"saved":saved})
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
                    payload={"rotation":b.get("rotation",[]),"tactics":b.get("tactics",{})}
                    total=sum(int(x.get("minutes",0)) for x in payload["rotation"])
                    if total!=240:raise ValueError("La rotation doit totaliser exactement 240 minutes.")
                    save_rotation(lid,m["team_id"],payload);return self.send_json(200,{"success":True,"message":"Rotation sauvegardée."})
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
    httpd=ThreadingHTTPServer(("0.0.0.0",8000),MultiplayerServer);httpd.daemon_threads=True
    print("NBA MANAGER V58 — serveur multijoueur")
    print("Local : http://localhost:8000/NBA_MANAGER_INTERFACE/")
    print("Réseau : écoute sur 0.0.0.0:8000")
    httpd.serve_forever()
if __name__=="__main__":main()
