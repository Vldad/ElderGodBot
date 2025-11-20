# Eldergod


## Installation 


Script SQL `db_setup.sql`

Ce script permet de :
- changer toutes les occurences de "your_database_name" par le nom de la db où les tables seront installées
- changer "your_password_here" par le mot de passe que tu veux donner au user db utilisé par le bot
- changer "nosgoth_dbuser" par le compte que tu veux créer. Ce compte aura les accès total sur toutes les tables préfixées "egb_" et uniquement celles là.

Le fichier d'environnement `.env`
- contient toutes les variables d'environnement
- `GUILD_ID` : contient déjà l'id du serveur du Royaume. Ne pas toucher
- `TEST_CHANNEL_ID` : contient déjà l'id du clavardeur. Ne pas toucher

## Mariadb db Configuration

```mysql
DB_MDB=nosgoth
DB_MDB_HOST=localhost
DB_MDB_PORT=3306
DB_MDB_USER=nosgoth_dbuser
DB_MDB_USER_PWD=??????????
```

il faut changer les id de connexion à la db avec ceux paramétrés dans le script sql précédent.

## Configuration python, 

il nécessite 3 libs :

```shell
pip install discord.py
pip install aiomysql
pip install python-dotenv
```

## Exécution

```shell
python egb.py
```

En cas de succès le script devrait exécuter ces commandes :

```shell
[2025-11-16 23:29:33] [INFO    ] discord.client: logging in using static token
Setting up database connection...
Database connected successfully!
[2025-11-16 23:29:34] [INFO    ] discord.gateway: Shard ID None has connected to Gateway (Session ID: b99f65747b0c2581decb879275de1a1a).
Synced 11 commands globally
Loaded 11 characters for autocomplete
eldergod is up and ready!
```


