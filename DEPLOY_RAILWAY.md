# Déploiement Railway — NBA Manager V61

Configuration prévue :
- service web construit avec `Dockerfile`;
- commande : `python server_v61.py`;
- port lu automatiquement depuis `PORT`;
- health check : `/health`;
- URL racine redirigée vers le portail multijoueur;
- SQLite stocké dans `NBA_MANAGER_DATA_DIR`.

Dans Railway :
1. Déployer ce dépôt.
2. Ajouter un Volume au service.
3. Monter le Volume sur `/data`.
4. Ajouter la variable `NBA_MANAGER_DATA_DIR=/data`.
5. Dans Networking, générer un domaine public.

La base `/data/nba_manager.db` persistera alors entre les redéploiements.
