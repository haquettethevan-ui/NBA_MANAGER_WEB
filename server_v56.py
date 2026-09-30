from server import *
from multiplayer_db import *
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
        return super().do_GET()
    def do_POST(self):
        try:
            if self.path=="/api/register":
                b=self.body();uid=create_user(b.get("username",""),b.get("password",""));token,u=login(b["username"],b["password"])
                return self.send_json(200,{"success":True,"token":token,"user":{"id":uid,"username":b["username"]}})
            if self.path=="/api/login":
                b=self.body();token,u=login(b.get("username",""),b.get("password",""))
                return self.send_json(200,{"success":True,"token":token,"user":{"id":u["id"],"username":u["username"]}})
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
    print("NBA MANAGER V56 — serveur multijoueur")
    print("Local : http://localhost:8000/NBA_MANAGER_INTERFACE/")
    print("Réseau : écoute sur 0.0.0.0:8000")
    httpd.serve_forever()
if __name__=="__main__":main()
