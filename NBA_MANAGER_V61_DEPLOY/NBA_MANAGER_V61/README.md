# NBA Manager V39

V39 reconstruit le cœur de simulation autour d’une hiérarchie simple : **ratings joueurs -> lineup/matchup -> énergie -> tactiques**.

## Nouveautés V39
- Nouveau moteur de possession indépendant de l’ancien moteur V38 (`engine_v39.py`).
- Profils de tirs naturels : cercle, mi-distance et 3 points selon les ratings/profils des joueurs.
- Le défenseur direct et son énergie modifient la qualité du tir.
- Usage offensif dérivé du talent : les stars prennent naturellement davantage de possessions.
- Énergie intra-match : baisse sur le terrain, récupération sur le banc, impact progressif sur les performances.
- Rotation automatique réaliste de 10 joueurs ; les autres restent à 0 minute.
- Timeline minute par minute + énergie affichée pendant le match.
- Indicateur de couverture PG/SG/SF/PF/C et validation exacte des 240 minutes.
- Nouveau système tactique : 3 priorités offensives + 3 défensives, avec influence décroissante.
- Les tactiques changent les situations produites (type de tir, transition, rebond, pression...), jamais le score directement.
- `test_engine.py` calibre le box score sur les ordres de grandeur NBA 2025-26.
- `calibration_v39.py` sert à mesurer domination du talent et impact secondaire des tactiques.
- `legacy_main.py` conserve le moteur V38 pour comparaison.

## Lancer
1. Exécuter `INITIALISER_BASE.bat` si nécessaire.
2. Lancer `python server.py`.
3. Ouvrir `http://localhost:8000/NBA_MANAGER_INTERFACE/`.

## Tests
`python test_engine.py 60`

`python calibration_v39.py`

## V40 - calibration de la hiérarchie
- Usage offensif reconstruit autour de la meilleure arme offensive du joueur.
- Ajout de `calibration_hierarchy_v39.py` : tests équipes égales, +3/+5 ratings, superstar, matchups tactiques et rotation courte.
- Cible de conception : talent = facteur principal, tactique = facteur secondaire, fatigue = arbitrage rotation/profondeur.
- Lancer `python calibration_hierarchy_v39.py` après toute modification des coefficients du moteur.

## V41 - rotations / énergie
- Rotation automatique : 10 joueurs actifs par défaut, les autres à 0 minute.
- Validation UI : 8 à 12 joueurs actifs, exactement 5 titulaires et 240 minutes.
- Couverture PG/SG/SF/PF/C calculée à partir des affectations réelles minute par minute.
- Timeline pré-match par joueur sur 48 minutes pour visualiser immédiatement quels joueurs partagent le terrain.
- Séquençage des lineups corrigé pour éviter les très longs stints continus générés par l'ancien regroupement.
- L'énergie baisse sur le terrain selon la stamina et remonte sur le banc ; elle affecte attaque, défense, athlétisme et rebond dans le moteur V39+.
- Test de régression : `python test_rotations_v41.py`.

## V43 - matrice tactique
- Les 3 priorités offensives et défensives sont pondérées 100% / 58% / 30%.
- Une matrice de matchups croise désormais chaque priorité offensive avec les trois priorités défensives adverses.
- Les contres modifient surtout le profil des possessions (zones de tir, qualité, passes, turnovers, rebond et transition), jamais le score directement.
- Les trois priorités d'un même côté doivent être différentes.
- `test_tactics_v42.py` mesure les principaux contres et vérifie qu'un avantage de talent reste dominant.


## V43 — compatibilité tactique / effectif
Les focus offensifs sont désormais modulés par les qualités réelles du cinq présent sur le terrain. L’interface affiche aussi un score de compatibilité pondéré par les minutes de rotation. Une tactique augmente l’intention de créer un type de situation, mais ne crée jamais artificiellement le niveau technique nécessaire pour la convertir.

## V44 — calibration individuelle
- Séparation du créateur de possession et du finisseur : les tirs, pertes de balle et lancers ne sont plus mécaniquement concentrés sur le même joueur.
- Hiérarchie de scoring issue des ratings/profils/minutes, sans quota artificiel de tirs ou de points.
- Création pondérée davantage par le playmaking ; finition pondérée par les armes de scoring et le talent global.
- Nouveau banc `calibration_individual_v44.py` pour contrôler minutes, PTS, FGA, 3PA, FTA, AST, REB et TOV par joueur sur de grandes séries.
- Les tests de rotation V41 restent compatibles.

## V45 - Pre-season engine lock
- `main.py` now explicitly loads `engine_v45.py` and exposes `ACTIVE_ENGINE_VERSION = "V45"`.
- Creator selection is more strongly driven by playmaking.
- Assisted-shot generation now differentiates elite creators without assigning fixed assist quotas.
- `test_preseason_v45.py` is the fast non-regression gate for engine wiring and NBA-like team box-score ranges.
- V41 rotation validation remains the reference gate for 240 minutes / 48 minutes at each position.


## V47 — mouvement de balle et moteur actif
- `main.py` pointe explicitement vers `engine_v47.py` (`ACTIVE_ENGINE_VERSION = V47`).
- Mouvement de balle agit davantage sur la création d'un tir par une passe et sur la probabilité qu'un panier soit assisté; aucune assist n'est ajoutée directement.
- Audit 30 équipes, 5 matchs appariés: Mouvement de balle vs Zone = +1.49 AST en moyenne, 26/30 équipes dans le sens attendu.
- `test_causal_tactics_v47.py` et `test_preseason_v47.py` ajoutés.


## V48 — énergie réellement influente
- Le moteur ne remet plus automatiquement une équipe fatiguée à 100 au coup d'envoi.
- Courbe de fatigue progressive: 95-100 quasi neutre, 80-85 léger, 70-75 important, <70 sévère.
- La fatigue affecte adresse/création, défense, athlétisme, rebond et risque de turnover.
- Test 30 équipes à roster miroir: énergie 75 ≈ -6.7 pts et ~30% de victoires; énergie 65 ≈ -10 pts.
- Les tests pré-saison, rotations et causalité tactique restent valides.


## V49 — rééquilibrage tactique
- Les tactiques offensives redistribuent davantage les types d'actions au lieu d'accorder un bonus de points implicite.
- Tir extérieur, Mouvement de balle et Rebond offensif ont été ramenés vers la neutralité.
- Jeu rapide a été renforcé et son coût en turnovers réduit.
- Test miroir 30 équipes: écarts moyens vs plan neutre compris environ entre -1.0 et +1.3 pt selon le focus (contre ~-3.6 à +3.9 auparavant).
- Les signatures tactiques restent visibles: 3PA, points dans la raquette, assists, rebonds et possessions évoluent dans les directions attendues.


## V50 — rééquilibrage défensif
- Audit défensif corrigé avec protocole miroir propre.
- Pression porteur: pression/turnovers réduits et contreparties recalibrées.
- Repli défensif: protection transition renforcée, coût rebond réduit.
- Homme à homme et Box out: bonus génériques réduits.
- Défense extérieure et Zone: compromis périmètre/raquette recalibrés.
- Protection du cercle conserve son identité: moins de peinture, davantage de tirs extérieurs concédés.


## V51 — coaching adaptatif contrôlé
- Les 23 interactions attaque/défense sont conservées mais leur amplitude est réduite de 30 %.
- Nouvelle IA ai_coach_v51.py : identité du roster dominante, adaptation adverse plafonnée (~30 %).
- L'IA réordonne ses priorités selon l'adversaire sans reconstruire complètement son identité.
- Incertitude de coaching réduite pour éviter les changements arbitraires.


## V52 — équilibre superstar / défense collective
- Hiérarchie créateur/finisseur légèrement renforcée pour mieux valoriser les joueurs élites.
- Overall davantage pris en compte dans la finition sans imposer artificiellement des tirs aux stars.
- Assignation défensive moins parfaite à chaque possession (variation de matchup accrue).
- Impact direct de la défense sur chaque tir légèrement réduit, sans neutraliser la défense.
- Recalibrage global du rythme, de l'adresse et des turnovers après ces changements.
- Les tactiques et l'IA de coaching V51 restent inchangées.


## V53 — matchups défensifs contextuels
- Défenseur naturel du même poste utilisé par défaut.
- Suppression du tirage aléatoire ±12 pour choisir le défenseur.
- Pick & Roll : possibilité contrôlée de switch vers un poste adjacent.
- Transition : possibilité contrôlée de cross-match/mismatch.
- Lineups atypiques et joueurs sortis pour fautes disposent d'un fallback compatible.
- Aucun changement aux ratings, tactiques ou calibration de tir de V52.


## V54 — hiérarchie de talent renforcée
- Les écarts attaque/défense influencent davantage la réussite des tirs.
- La qualité du créateur influence davantage les pertes de balle.
- Les écarts de rebond ont davantage d'effet possession par possession.
- Le playmaking élite convertit légèrement mieux les passes en tirs assistés.
- Aucun bonus artificiel accordé à l'équipe ayant le meilleur overall.
- Matchups défensifs contextuels V53 conservés.


## V55 — fatigue de saison et blessures
- L'énergie d'un joueur reste persistante entre les matchs.
- `recover_between_games(team, rest_days)` récupère l'énergie selon les jours de repos.
- Une charge récente `workload` persiste et diminue avec le repos.
- Les grosses minutes + énergie basse + charge élevée augmentent progressivement le risque de blessure.
- Risque indicatif par match : ~0,15 % frais/28 min, ~0,48 % à 38 min chargé, ~1,14 % très fatigué/40 min, ~1,87 % en situation extrême.
- Blessures mineures : 2–7 jours ; modérées : 8–21 ; importantes : 22–45.
- Un joueur blessé ne peut pas recevoir de minutes : la rotation doit être reconstruite.
- Les matchups, tirs et calibration de talent V54 sont conservés.


## V56 — fondation multijoueur
Lancer `python server_v56.py`, puis ouvrir :
`http://localhost:8000/NBA_MANAGER_INTERFACE/multiplayer.html`

Première fondation :
- comptes persistants SQLite et mots de passe PBKDF2 salés ;
- sessions par token ;
- création de ligues et codes d'invitation ;
- plusieurs managers dans une même ligue ;
- choix d'équipe exclusif par ligue ;
- tables persistantes prévues pour rotations et matchs ;
- premier portail : Connexion / Ligue / Effectif / Calendrier / Résultats ;
- ancien écran de simulation conservé ;
- serveur écoute sur `0.0.0.0` afin d'être compatible avec un futur hébergement.


## V57 — équipe persistante et calendrier
Lancer `python server_v57.py`.
- Effectif de l'équipe choisie visible depuis le portail.
- Rotation enregistrée par équipe et par ligue (validation 240 minutes).
- Base prête à conserver les tactiques avec la rotation.
- Génération persistante de 1 230 matchs : exactement 82 par équipe.
- Aucun club ne joue deux fois le même jour.
- Calendrier réparti d'octobre à avril, avec environ 3–6 back-to-backs par équipe dans ce générateur.
- Les tables de matchs stockent date, statut, score et résultat JSON pour l'historique futur.


## V58 — boucle de saison
Lancer `python server_v58.py`.
- Le bouton "Simuler la prochaine journée" joue tous les matchs de la prochaine date.
- État physique persistant par joueur : énergie, workload, blessure et date du dernier match.
- Récupération V55 automatiquement calculée à partir du calendrier.
- Les équipes humaines utilisent leur rotation sauvegardée.
- Une rotation humaine contenant un blessé bloque proprement toute la journée avant simulation.
- Les équipes IA reconstruisent leur rotation en excluant les joueurs indisponibles.
- Scores et résultat JSON sont enregistrés dans SQLite.
- Calendrier affiche matchs à venir et résultats.
- Classement W-L et différentiel de points calculés depuis les matchs joués.
- Test end-to-end validé sur deux journées : 30 équipes, 535 états joueurs persistants.


## V59 — préparation du match
Lancer `python server_v59.py`.
- Écran Mon équipe enrichi : 5 titulaires, minutes, énergie, workload et blessures.
- Validation : exactement 5 titulaires et 240 minutes.
- Validation moteur de la couverture PG/SG/SF/PF/C avant sauvegarde.
- Tactiques attaque et défense avec priorités primaire, secondaire et tertiaire.
- Rotation, titulaires et tactiques persistants par ligue.
- La boucle de saison V58 utilise maintenant les titulaires sauvegardés du manager.
- Joueurs blessés désactivés dans l'éditeur.
- Test end-to-end validé avec Boston contrôlé par un manager humain contre les équipes IA.


## V60 — dashboard manager
Lancer `python server_v60.py`.
- Refonte complète du portail multijoueur en dashboard de management.
- Accueil : bilan W-L, différentiel, prochain match, dernier résultat, blessures et joueurs fatigués.
- Navigation : Accueil / Effectif / Tactiques / Calendrier / Résultats / Classement / Ligue.
- Effectif et rotation dans une vue dédiée.
- Tactiques attaque/défense dans une vue dédiée, tout en sauvegardant un plan de match unique.
- Calendrier, simulation de journée, résultats et classement intégrés au même portail.
- Interface responsive pour ordinateur et mobile.
- Backend V59/V55 conservé : aucune modification de calibration du moteur.


## V61 — prête pour hébergement
- `server_v61.py` lit le port fourni par l'hébergeur via `PORT`.
- `/health` pour le health-check.
- `/` redirige directement vers le portail multijoueur.
- `NBA_MANAGER_DATA_DIR` permet de placer SQLite sur un volume persistant.
- Dockerfile + railway.toml inclus.
- Configuration cible Railway : volume `/data`, variable `NBA_MANAGER_DATA_DIR=/data`.
- Test production local validé : health-check OK, redirection OK, base créée sur le volume externe.
