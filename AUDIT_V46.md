# Audit V46 - 30 équipes

- 30 rosters présents, 536 joueurs.
- 535/536 joueurs ont toutes les catégories. Tyler Nickel (NYK) manque seulement `rebounding`; il est exclu par `complete_players` tant que la donnée manque.
- Rotation IA corrigée: 30/30 équipes génèrent exactement 10 joueurs actifs, 240 minutes et une affectation PG/SG/SF/PF/C valide.
- Bug V45 corrigé: `transition_def`, `transition_allow` et les interactions de transition sont maintenant intégrés au calcul du rythme.
- Tests de non-régression V45 et rotations V41 passent après les corrections.

Audit tactique multi-rosters (direction moyenne):
- Tir extérieur: davantage de 3PA contre Protection du cercle que Défense extérieure.
- Jeu intérieur: davantage de production dans la raquette contre Défense extérieure que Protection du cercle.
- Pénétration: davantage de production dans la raquette contre Défense extérieure que Protection du cercle.
- Mouvement de balle: davantage d'assists contre Zone que Homme à homme (effet volontairement modéré).
- Rebond offensif: avantage contre Zone, réduit par Box out.
- Jeu rapide: davantage de possessions lorsque la défense privilégie Box out que lorsqu'elle privilégie Repli défensif.

Les résultats d'un match individuel restent variables: les tactiques changent les situations et probabilités, elles ne garantissent jamais un résultat.
