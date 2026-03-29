# EldergodBot — CLAUDE.md

## Overview
Bot Discord Python pour un serveur RPG thématique Legacy of Kain (vampires, clans, progression de niveau).
Stack : discord.py, aiomysql, MariaDB, python-dotenv

## Entry Points
- `start_egb.py` : wrapper de lancement — redirige stdout/stderr vers `out/output_TIMESTAMP.txt` et `out/error_TIMESTAMP.txt`, puis appelle `egb.py` via subprocess
- `egb.py` : valide les variables d'env, configure les intents Discord (message_content + members), instancie `ElderGod` et lance le bot

## Architecture
```
eldergod.py              # Classe principale ElderGod(commands.Bot)
lib/
  character.py           # Modèle métier Character (logique pure, pas de BDD)
  character_repository.py # Accès MariaDB pour les personnages (pattern Repository)
  ability_manager.py     # Gestion des cooldowns d'abilities (table egb_ability_usage)
  ability_commands.py    # Toutes les commandes slash d'abilities (enregistrées via AbilityCommands.register_commands(bot))
  clan_system.py         # Définition des clans, progression, déblocage d'abilities
assets/
  welcome.png            # Image envoyée à l'arrivée d'un nouveau membre
out/                     # Logs générés automatiquement au démarrage
```

## Database — MariaDB
Pool de connexion : `aiomysql.create_pool` (host/port/user/password/db depuis .env, autocommit=True)
Attribut du bot : `self.mdb_con`

Tables principales :
- `egb_characters` — discord_id, level, last_attempt, last_successful_levelup
- `egb_character_bonuses` — discord_id, devour_bonus, swim_active, leader_curse_until, oppression_malus, oppression_until, shield_until (effets à source unique)
- `egb_character_effects` — id, discord_id, source_discord_id, effect_type (bless|curse|steal_bonus|steal_malus), amount (positif), created_at (effets multi-sources, une ligne par interaction, supprimés après /levelup)
- `egb_pacts` — id, requester_id, target_id, status (active|expired|declined), accepted_at, expires_at
- `egb_ability_usage` — discord_id, ability_name, last_used (PK composite, cooldown_id=-1 pour global)
- `egb_quotes` — citations LoK (jointure sur egb_dim_characters)
- `egb_dim_characters` — personnages LoK (name_fr, name_en)
- `egb_log` — DiscordId, LogTime, Action

## Environment Variables
```
DISCORD_TOKEN
DB_MDB          # nom de la base
DB_MDB_HOST     # défaut: localhost
DB_MDB_PORT     # défaut: 3306
DB_MDB_USER
DB_MDB_USER_PWD
TEST_CHANNEL_ID  # channel pour le message de bienvenue
DEFAULT_LANGUAGE # 'fr' ou 'en'
GUILD_ID

# Paramètres de levelup
BASE_LEVELUP_CHANCE   # défaut: 20
BONUS_PER_HOUR        # défaut: 5
MAX_LEVELUP_CHANCE    # défaut: 80
LEVELUP_COOLDOWN_HOURS # défaut: 1

# Rôles Discord (noms configurables)
ROLE_PLAYER   # défaut: 'Joueur'
ROLE_WINGS    # défaut: 'Ailes'
CLAN_FLEDGLING / CLAN_MELCHAHIM / CLAN_ZEPHONIM / CLAN_DUMAHIM
CLAN_RAHABIM / CLAN_TURELIM / CLAN_RAZIELIM / CLAN_ELDER
COLOR_FLEDGLING / COLOR_MELCHAHIM / ... (hex, ex: #8B0000)
```

## Clans & Progression
| Niveau | Clan        | Titre          |
|--------|-------------|----------------|
| 1–4    | Fledgling   | Humain         |
| 5–9    | Melchahim   | Mangeur de Peau|
| 10–14  | Zephonim    | Grimpeur       |
| 15–19  | Dumahim     | Croisé         |
| 20–24  | Rahabim     | Noyé           |
| 25–29  | Turelim     | Loyal          |
| 30–39  | Razielim    | Banni (ailes)  |
| 40+    | Elder       | Ancien         |

## Commandes Slash disponibles
| Commande     | Niveau requis | Cooldown         | Notes |
|--------------|---------------|------------------|-------|
| /levelup     | 1             | 1h entre tentatives, 1 succès/jour | Chance: 20–80% selon temps d'attente |
| /stats       | 1             | —                | Voir son niveau, clan, cooldowns, bonus actifs |
| /profile     | 1             | —                | Profil public d'un joueur (sans détails privés) |
| /chaussette  | 5             | 7 jours/joueur   | Level up gratuit garanti |
| /devour      | 5             | 1 jour/joueur    | +3–8% cumulatif au prochain levelup |
| /bless       | 1             | 7 jours/joueur   | Donne +3–8% à un autre joueur |
| /curse       | 10            | 7 jours/joueur   | Malus sur un autre joueur |
| /entomb      | 10            | 7 jours GLOBAL   | Bloque le leader 1–2 jours |
| /swim        | 20            | 7 jours/joueur   | Bypass le cooldown de levelup |
| /pact        | 20            | 24h/joueur       | Pacte de Sang 24h avec un autre joueur — partage bonus/malus et free level sur succès |
| /evolve      | 30            | —                | Obtenir le rôle cosmétique Ailes |
| /spectral    | 30            | —                | Voir le royaume spectral |
| /oppress     | Leader only   | 7 jours GLOBAL   | Malus –20 à –50% à tous les autres |
| /steal       | 40            | 24h/joueur       | Siphonner 5–10% de chance d'un joueur |
| /shield      | 50            | 7 jours/joueur   | Bouclier 24h absorbant le prochain malus (curse, steal, entomb) — transmis via pacte |
| /quote       | —             | —                | Citation aléatoire LoK (autocomplete) |

## Patterns importants
- Les admins/owners ne peuvent pas recevoir de rôle via le bot → DM envoyé à la place (`_send_admin_dm`)
- Cooldown global : `discord_id = -1` dans `egb_ability_usage`
- Pacte actif : vérifié via `PactManager.get_active_pact_partner()` — les effets (bless, curse, steal, devour, swim, entomb, shield) sont mirrorés au partenaire au moment de leur création ; un level up réussi donne un niveau gratuit au partenaire via `_apply_pact_level()` ; chaque mirroring envoie un DM au partenaire
- Bouclier (`shield_until`) : absorbe le prochain malus (curse, steal_malus, entomb) — pact mirror vérifie aussi le bouclier du partenaire ; si bouclier actif sur un pact mirror de /shield, la durée est rafraîchie
- `egb_character_bonuses` est lu à chaque `/levelup` pour appliquer tous les bonus/malus actifs
- Toutes les réponses bot sont `ephemeral=True`
- Logging systématique dans `egb_log` après chaque commande

## Lancement
```bash
python start_egb.py
```