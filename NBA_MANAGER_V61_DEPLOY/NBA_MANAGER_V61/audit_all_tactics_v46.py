import server, main, engine_v46 as eng, statistics, random

def tac(off='Équilibré', defense='Équilibré'):
    off_order=[off]+[x for x in eng.OFFENSE_FOCUSES if x!=off]
    def_order=[defense]+[x for x in eng.DEFENSE_FOCUSES if x!=defense]
    return {'offensePrimary':off_order[0],'offenseSecondary':off_order[1],'offenseTertiary':off_order[2],
            'defensePrimary':def_order[0],'defenseSecondary':def_order[1],'defenseTertiary':def_order[2]}

checks=[
 ('Tir extérieur','Protection du cercle','Défense extérieure','three_attempted',1),
 ('Jeu intérieur','Défense extérieure','Protection du cercle','points_in_paint',1),
 ('Pénétration','Défense extérieure','Protection du cercle','points_in_paint',1),
 ('Mouvement de balle','Zone','Homme à homme','assists',1),
 ('Rebond offensif','Zone','Box out','rebounds',1),
]
print('30-team tactical audit')
for off,fav,counter,metric,sign in checks:
    diffs=[]
    for meta in server.TEAM_META:
        samples=[]
        for defense in (fav,counter):
            values=[]
            for seed in range(1):
                random.seed(seed+1701)
                a,_=server.build_team(meta['id']); b,_=server.build_team(meta['id'])
                ra=server.build_ai_rotation(a); rb=server.build_ai_rotation(b)
                x=main.simulate_game(a,b,ra,rb,tactics1=tac(off,'Équilibré'),tactics2=tac('Équilibré',defense))
                values.append(x['team1']['stats'][metric])
            samples.append(statistics.mean(values))
        diffs.append(samples[0]-samples[1])
    print(off, metric, 'delta=',round(statistics.mean(diffs),2),'teams expected=',sum(d*sign>0 for d in diffs),'/30')
# transition: test the mechanic it is intended to control (pace), not guaranteed score.
diffs=[]
for meta in server.TEAM_META:
    samples=[]
    for defense in ('Box out','Repli défensif'):
        values=[]
        for seed in range(1):
            random.seed(seed+2701)
            a,_=server.build_team(meta['id']); b,_=server.build_team(meta['id'])
            ra=server.build_ai_rotation(a); rb=server.build_ai_rotation(b)
            x=main.simulate_game(a,b,ra,rb,tactics1=tac('Jeu rapide','Équilibré'),tactics2=tac('Équilibré',defense))
            values.append(x['team1']['stats']['possessions'])
        samples.append(statistics.mean(values))
    diffs.append(samples[0]-samples[1])
print('Jeu rapide possessions delta=',round(statistics.mean(diffs),2),'teams expected=',sum(d>0 for d in diffs),'/30')
