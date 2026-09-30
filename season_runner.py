import datetime
from multiplayer_db import *
from server import build_team,build_ai_rotation,ai_tactics
from engine_v55 import simulate_game,recover_between_games,available_for_game

def _load_team_state(league_id,team_id,game_date):
    team,_=build_team(team_id);states=player_states(league_id,team_id)
    previous=None
    for p in team.roster:
        st=states.get(p.name)
        if st:
            p.energy=st["energy"];p.workload=st["workload"];p.injury_days=st["injury_days"];p.injury_label=st["injury_label"]
            if st["last_game_date"]:previous=st["last_game_date"] if previous is None else max(previous,st["last_game_date"])
    if previous:
        gap=(datetime.date.fromisoformat(game_date)-datetime.date.fromisoformat(previous)).days
        recover_between_games(team,max(0,gap-1))
    return team

def _human_rotation(league_id,team_id,team):
    saved=load_rotation(league_id,team_id)
    if not saved:return None,None
    payload=saved["payload"];rotation={x["name"]:int(x.get("minutes",0)) for x in payload.get("rotation",[])}
    # Injured human players must be handled by the manager.
    bad=[p.name for p in team.roster if rotation.get(p.name,0)>0 and not available_for_game(p)]
    if bad:raise ValueError(team_id+" : rotation à modifier, joueur(s) blessé(s) : "+", ".join(bad))
    starters=[x["name"] for x in payload.get("rotation",[]) if x.get("starter")]
    return rotation,payload.get("tactics") or None,starters

def _ai_rotation(team):
    # Remove unavailable players before asking the existing AI rotation builder.
    unavailable=[p for p in team.roster if not available_for_game(p)]
    if not unavailable:return build_ai_rotation(team)
    original=list(team.roster);team.roster=[p for p in original if available_for_game(p)]
    try:return build_ai_rotation(team)
    finally:team.roster=original

def simulate_next_day(league_id):
    date=next_scheduled_date(league_id)
    if not date:return {"date":None,"games":[],"complete":True}
    slate=games_on_date(league_id,date);members={x["team_id"]:x for x in league_members(league_id) if x["team_id"]}
    # Preflight every human team: never simulate half a day then discover an invalid human rotation.
    prepared={}
    for g in slate:
        for tid in (g["home_team"],g["away_team"]):
            if tid not in prepared:
                team=_load_team_state(league_id,tid,date)
                if tid in members:
                    hr=_human_rotation(league_id,tid,team)
                    if hr[0] is None:raise ValueError(tid+" : aucune rotation sauvegardée.")
                    rotation,tactics,starters=hr
                else:rotation,tactics,starters=_ai_rotation(team),ai_tactics(team),None
                prepared[tid]=(team,rotation,tactics,starters)
    results=[]
    for g in slate:
        ht,hr,htac,hs5=prepared[g["home_team"]];at,ar,atac,as5=prepared[g["away_team"]]
        result=simulate_game(ht,at,hr,ar,starter_names1=hs5,starter_names2=as5,tactics1=htac,tactics2=atac)
        hs=result["team1"]["stats"]["points"];as_=result["team2"]["stats"]["points"]
        update_game_result(g["id"],hs,as_,result)
        save_player_states(league_id,g["home_team"],ht,date);save_player_states(league_id,g["away_team"],at,date)
        results.append({"game_id":g["id"],"home":g["home_team"],"away":g["away_team"],"home_score":hs,"away_score":as_,"injuries":result.get("injuries",{})})
    return {"date":date,"games":results,"complete":False}
