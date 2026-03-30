import os
import aiomysql
import sys
from datetime import datetime
import discord
from discord.ext import commands
from discord import app_commands
import typing
from typing import Optional
from lib.character import Character
from lib.character_repository import CharacterRepository
from lib.clan_system import ClanSystem
from lib.ability_manager import AbilityManager
from lib.ability_commands import AbilityCommands
from lib.pact_manager import PactManager

class ElderGod(commands.Bot):
    """
    Main Discord bot class
    Handles commands and coordinates between Discord API and business logic
    """

    ALLOWED_LANGUAGES = ['en', 'fr']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mdb_con = None
        self.character_repo = None
        self.ability_manager = None
        self.pact_manager = None
        self.pending_pacts: set[int] = set()
        self.add_commands()
        self.characters = []  # Cache for autocomplete
        self._discord_characters = {}  # In-memory cache of Character objects

    async def on_member_join(self, member):
        """Event handler when a new member joins the server"""
        try:
            channel_id = int(os.getenv('CLAVARDEUR_ID'))
            channel = self.get_channel(channel_id)

            if channel:
                # Chemin relatif vers l'image (depuis la racine du projet)
                image_path = os.path.join(os.path.dirname(__file__), "assets", "welcome.png")

                file = discord.File(image_path, filename="welcome.png")
                await channel.send(f"Bienvenue, {member.mention} !", file=file)
        except FileNotFoundError:
            print(f"Image not found at path: {image_path}", file=sys.stderr)
        except Exception as e:
            print(f"Error in on_member_join: {e}", file=sys.stderr)

    async def setup_hook(self):
        """Initialize database connection and repository"""
        if not self.mdb_con:
            print("Setting up database connection...", file=sys.stdout)
            try:
                self.mdb_con = await aiomysql.create_pool(
                    host = os.getenv('DB_MDB_HOST', 'localhost'),
                    port=int(os.getenv('DB_MDB_PORT', '3306')),
                    user=os.getenv('DB_MDB_USER'),
                    password=os.getenv('DB_MDB_USER_PWD'),
                    db=os.getenv('DB_MDB'),
                    autocommit=True
                )
                self.character_repo = CharacterRepository(self.mdb_con)
                self.ability_manager = AbilityManager(self.mdb_con)
                self.pact_manager = PactManager(self.mdb_con)
                print("Database connected successfully!", file=sys.stdout)
            except Exception as e:
                print(f"Error setting up database: {e}", file=sys.stderr)
                raise

        @self.tree.error
        async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            if isinstance(error, app_commands.NoPrivateMessage):
                try:
                    await interaction.response.send_message(
                        "❌ Cette commande ne peut être utilisée que dans un serveur.",
                        ephemeral=True
                    )
                except Exception:
                    pass
                return
            print(f"Unhandled tree error: {error}", file=sys.stderr)

    async def on_ready(self):
        """Event handler when bot is ready"""
        try:
            sc = await self.tree.sync()
            print(f"Synced {len(sc)} commands globally", file=sys.stdout)
        except Exception as e:
            print(f"Error syncing commands: {e}", file=sys.stderr)

        await self.get_all_characters()
        print(f"{__name__} is up and ready!", file=sys.stdout)

    def add_commands(self):
        """Register all slash commands"""

        # Register ability commands
        AbilityCommands.register_commands(self)

        # ===== QUOTE COMMAND =====
        @app_commands.guild_only()
        @self.tree.command(name="quote", description="Affiche une citation aléatoire de l'univers LoK")
        @app_commands.describe(character="Qui l'a dit ?")
        @app_commands.describe(lang=f"Langue de la citation : en | fr. Par défaut : {os.getenv('DEFAULT_LANGUAGE', 'fr')}")
        async def quote(interaction: discord.Interaction, character: str, lang: Optional[str] = None):
            try:
                lang = self._validate_language(lang)

                if await self.lok_character_exists(character, lang):
                    q = await self.get_random_quote(character, lang)
                    if q:
                        clan_info = await self._get_user_clan_info(interaction.user.id)
                        embed = discord.Embed(
                            description=f'{q}\n\n*— {character}*',
                            color=clan_info['color']
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                    else:
                        await self._send_error_embed(
                            interaction,
                            f'Aucune citation pour **{character}**'
                        )
                else:
                    await self._send_error_embed(
                        interaction,
                        f'Personnage **{character}** introuvable'
                    )

                await self.log(interaction.user.id, datetime.now(), f'quote {character}')
            except ValueError as e:
                await self._send_error_embed(interaction, str(e))
            except Exception as e:
                print(f"Error in quote command: {e}", file=sys.stderr)
                await self._send_error_embed(
                    interaction,
                    "Une erreur est survenue lors de la récupération de la citation"
                )

        @quote.autocomplete("character")
        async def quote_autocompletion(
            interaction: discord.Interaction,
            current: str
        ) -> typing.List[app_commands.Choice[str]]:
            data = []
            for char in self.characters:
                if current.lower() in char.lower():
                    data.append(app_commands.Choice(name=char, value=char))
            return data[:25]

        # ===== LEVELUP COMMAND =====
        @app_commands.guild_only()
        @self.tree.command(name="levelup", description="Tenter de monter de niveau")
        async def levelup(interaction: discord.Interaction):
            # Check if user has "Joueur" role
            if not await self._has_player_role(interaction.user):
                await self._send_error_embed(
                    interaction,
                    "Tu dois avoir le rôle **Joueur** pour utiliser ce système RPG."
                )
                return

            try:
                await interaction.response.defer(ephemeral=True)

                character = await self.get_or_create_character(interaction.user.id)
                old_level = character.get_level()

                # Get config from env
                base_chance = int(os.getenv('BASE_LEVELUP_CHANCE', '20'))
                bonus_per_hour = int(os.getenv('BONUS_PER_HOUR', '5'))
                max_chance = int(os.getenv('MAX_LEVELUP_CHANCE', '80'))
                cooldown_hours = int(os.getenv('LEVELUP_COOLDOWN_HOURS', '1'))

                # Check for bonuses/penalties
                async with self.mdb_con.acquire() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(
                            'SELECT devour_bonus, swim_active, leader_curse_until, oppression_malus, oppression_until FROM egb_character_bonuses WHERE discord_id = %s',
                            (interaction.user.id,)
                        )
                        bonuses = await cursor.fetchone()

                async with self.mdb_con.acquire() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(
                            '''SELECT effect_type, SUM(amount) as total
                               FROM egb_character_effects
                               WHERE discord_id = %s
                               GROUP BY effect_type''',
                            (interaction.user.id,)
                        )
                        effects_rows = await cursor.fetchall()
                effects = {row['effect_type']: int(row['total']) for row in (effects_rows or [])}

                # Check for leader curse
                if bonuses and bonuses.get('leader_curse_until'):
                    curse_until = bonuses['leader_curse_until']
                    if curse_until > datetime.now():
                        await self._send_error_embed(
                            interaction,
                            f"⚡ Tu es sous l'effet d'une condamnation jusqu'au {curse_until.strftime('%d/%m/%Y à %H:%M')} !\n\nTu ne peux pas monter de niveau tant que la condamnation est active.",
                            followup=True
                        )
                        return

                # Apply bonuses
                total_bonus = 0
                has_swim = False

                if bonuses:
                    if bonuses.get('devour_bonus'):
                        total_bonus += bonuses['devour_bonus']
                    if bonuses.get('swim_active'):
                        has_swim = True
                    if bonuses.get('oppression_malus') and bonuses.get('oppression_until'):
                        ou = bonuses['oppression_until']
                        if ou > datetime.now():
                            total_bonus += bonuses['oppression_malus']

                total_bonus += effects.get('bless', 0)
                total_bonus -= effects.get('curse', 0)
                total_bonus += effects.get('steal_bonus', 0)
                total_bonus -= effects.get('steal_malus', 0)

                success, message, probability = character.attempt_to_levelup(
                    base_chance, bonus_per_hour, max_chance, total_bonus, cooldown_hours, has_swim
                )

                await self.character_repo.save_character(character)
                self._discord_characters[character.get_discord_id()] = character

                # Clear bonuses after use
                async with self.mdb_con.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            'UPDATE egb_character_bonuses SET devour_bonus = 0, swim_active = FALSE WHERE discord_id = %s',
                            (interaction.user.id,)
                        )
                        await cursor.execute(
                            'DELETE FROM egb_character_effects WHERE discord_id = %s',
                            (interaction.user.id,)
                        )
                        await conn.commit()

                clan_info = ClanSystem.get_clan_by_level(character.get_level())
                embed = discord.Embed(
                    title="🎲 Tentative de Level Up",
                    description=message,
                    color=clan_info['color']
                )

                if success:
                    new_level = character.get_level()
                    embed.add_field(
                        name="Nouveau Niveau",
                        value=f"**{new_level}**",
                        inline=True
                    )

                    # Check if clan changed
                    if ClanSystem.has_clan_changed(old_level, new_level):
                        old_clan = ClanSystem.get_clan_by_level(old_level)
                        new_clan = ClanSystem.get_clan_by_level(new_level)

                        # Assign new roles
                        role_assigned = await self._assign_clan_role(interaction.user, new_clan)

                        if role_assigned:
                            embed.add_field(
                                name="🦇 Évolution !",
                                value=f"Tu es devenu **{new_clan['title']}** du clan **{new_clan['name']}** !",
                                inline=False
                            )
                        else:
                            # User is admin/owner, send DM
                            embed.add_field(
                                name="🦇 Évolution !",
                                value=f"Tu es devenu **{new_clan['title']}** du clan **{new_clan['name']}** !",
                                inline=False
                            )
                            await self._send_admin_dm(interaction.user, new_clan)

                        # Check for new abilities
                        new_abilities = [a for a in new_clan['abilities'] if a['level'] == new_level]
                        if new_abilities:
                            abilities_text = "\n".join([f"• {a['command']} - {a['description']}" for a in new_abilities])
                            embed.add_field(
                                name="✨ Nouvelles Capacités Débloquées",
                                value=abilities_text,
                                inline=False
                            )
                if success:
                    embed.add_field(
                        name="Probabilité",
                        value=f"{probability:.1f}%",
                        inline=True
                    )

                    if total_bonus != 0:
                        bonus_text = f"+{total_bonus}%" if total_bonus > 0 else f"{total_bonus}%"
                        embed.add_field(
                            name="Bonus/Malus",
                            value=bonus_text,
                            inline=True
                        )

                if success:
                    await self._apply_pact_level(interaction.user, embed)

                await interaction.followup.send(embed=embed, ephemeral=True)
                await self.log(
                    interaction.user.id,
                    datetime.now(),
                    f'levelup attempt ({"success" if success else "fail"})'
                )
            except Exception as e:
                print(f"Error in levelup command: {e}", file=sys.stderr)
                await self._send_error_embed(
                    interaction,
                    "Une erreur est survenue lors de la tentative de level up",
                    followup=True
                )

        # ===== STATS COMMAND =====
        @app_commands.guild_only()
        @self.tree.command(name="stats", description="Voir vos statistiques de personnage")
        async def stats(interaction: discord.Interaction):
            if not await self._has_player_role(interaction.user):
                await self._send_error_embed(
                    interaction,
                    "Tu dois avoir le rôle **Joueur** pour utiliser ce système RPG."
                )
                return

            try:
                character = await self.get_or_create_character(interaction.user.id)
                clan_info = ClanSystem.get_clan_by_level(character.get_level())
                has_bonusmalus = False

                embed = discord.Embed(
                    title=f"🦇 {interaction.user.display_name}",
                    description=f"**{clan_info['title']}** du clan **{clan_info['name']}**\n\n*{clan_info['description']}*",
                    color=clan_info['color']
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)

                embed.add_field(name="Niveau", value=f"**{character.get_level()}**", inline=True)

                # Show clan role
                clan_role = discord.utils.get(interaction.guild.roles, name=clan_info['name'])
                if clan_role and clan_role in interaction.user.roles:
                    embed.add_field(name="Rôle du Clan", value=clan_role.mention, inline=True)

                # Show wings role if Razielim
                if clan_info['has_wings']:
                    wings_role_name = os.getenv('ROLE_WINGS', 'Ailes')
                    wings_role = discord.utils.get(interaction.guild.roles, name=wings_role_name)
                    if wings_role and wings_role in interaction.user.roles:
                        embed.add_field(name="✨ Ailes", value=wings_role.mention, inline=True)

                # Last attempt info
                if character.get_last_attempt():
                    embed.add_field(
                        name="Dernière Tentative",
                        value=character.get_last_attempt().strftime("%d/%m/%Y à %H:%M"),
                        inline=True
                    )

                if character.get_last_successful_levelup():
                    embed.add_field(
                        name="Dernier Level Up Réussi",
                        value=character.get_last_successful_levelup().strftime("%d/%m/%Y"),
                        inline=True
                    )

                # Status and success chance
                can_attempt, msg = character.can_attempt_levelup()
                base_chance = int(os.getenv('BASE_LEVELUP_CHANCE', '20'))
                bonus_per_hour = int(os.getenv('BONUS_PER_HOUR', '5'))
                max_chance = int(os.getenv('MAX_LEVELUP_CHANCE', '80'))
                success_chance = character.calculate_success_chance(base_chance, bonus_per_hour, max_chance)

                # Get bonuses/penalties
                async with self.mdb_con.acquire() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(
                            'SELECT devour_bonus, swim_active, leader_curse_until, oppression_malus, oppression_until, shield_until FROM egb_character_bonuses WHERE discord_id = %s',
                            (interaction.user.id,)
                        )
                        bonuses = await cursor.fetchone()

                async with self.mdb_con.acquire() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(
                            '''SELECT effect_type, amount, source_discord_id
                               FROM egb_character_effects
                               WHERE discord_id = %s
                               ORDER BY effect_type, created_at''',
                            (interaction.user.id,)
                        )
                        effects_rows = await cursor.fetchall()

                has_swim = bonuses and bonuses.get('swim_active')
                if has_swim and not can_attempt:
                    status_text = "🌊 Nage active — cooldown contourné !\nChance de succès : {:.1f}%".format(success_chance)
                else:
                    status_text = f"{msg}\nChance de succès : {success_chance:.1f}%"

                # Display bonuses/penalties
                total_bonus = 0
                bonus_details = []
                leader_cursed = False
                has_bonusmalus = False

                if bonuses:
                    if bonuses.get('shield_until') and bonuses['shield_until'] > datetime.now():
                        bonus_details.append(f"🛡️ Bouclier actif jusqu'au {bonuses['shield_until'].strftime('%d/%m/%Y à %H:%M')}")
                        has_bonusmalus = True
                    if bonuses.get('swim_active'):
                        bonus_details.append("🌊 Nage active (cooldown contourné)")
                        has_bonusmalus = True
                    if bonuses.get('devour_bonus'):
                        total_bonus += bonuses['devour_bonus']
                        bonus_details.append(f"Devour: +{bonuses['devour_bonus']}%")
                        has_bonusmalus = True

                    if bonuses.get('oppression_until'):
                        oppression_until = bonuses['oppression_until']
                        if oppression_until > datetime.now():
                            total_bonus += bonuses['oppression_malus']
                            bonus_details.append(f"Oppression: {bonuses['oppression_malus']}%")
                            has_bonusmalus = True

                    if bonuses.get('leader_curse_until'):
                        curse_until = bonuses['leader_curse_until']
                        if curse_until > datetime.now():
                            bonus_details.append(f"⚡ Condamné jusqu'au {curse_until.strftime('%d/%m/%Y %H:%M:%S')}")
                            leader_cursed = True
                            has_bonusmalus = True

                if effects_rows:
                    effects_by_type = {}
                    for row in effects_rows:
                        et = row['effect_type']
                        if et not in effects_by_type:
                            effects_by_type[et] = []
                        effects_by_type[et].append(row)

                    def get_member_name(source_id):
                        if source_id == -1:
                            return "Inconnu"
                        member = interaction.guild.get_member(source_id)
                        return member.display_name if member else f"#{source_id}"

                    if 'bless' in effects_by_type:
                        parts = [f"{get_member_name(r['source_discord_id'])} (+{r['amount']}%)" for r in effects_by_type['bless']]
                        bless_total = sum(r['amount'] for r in effects_by_type['bless'])
                        total_bonus += bless_total
                        bonus_details.append(f"Béni par: {', '.join(parts)} → **+{bless_total}%**")
                        has_bonusmalus = True

                    if 'curse' in effects_by_type:
                        parts = [f"{get_member_name(r['source_discord_id'])} (-{r['amount']}%)" for r in effects_by_type['curse']]
                        curse_total = sum(r['amount'] for r in effects_by_type['curse'])
                        total_bonus -= curse_total
                        bonus_details.append(f"Maudit par: {', '.join(parts)} → **-{curse_total}%**")
                        has_bonusmalus = True

                    if 'steal_bonus' in effects_by_type:
                        parts = [f"volé sur {get_member_name(r['source_discord_id'])} (+{r['amount']}%)" for r in effects_by_type['steal_bonus']]
                        steal_bonus_total = sum(r['amount'] for r in effects_by_type['steal_bonus'])
                        total_bonus += steal_bonus_total
                        bonus_details.append(f"Vol: {', '.join(parts)} → **+{steal_bonus_total}%**")
                        has_bonusmalus = True

                    if 'steal_malus' in effects_by_type:
                        parts = [f"par {get_member_name(r['source_discord_id'])} (-{r['amount']}%)" for r in effects_by_type['steal_malus']]
                        steal_malus_total = sum(r['amount'] for r in effects_by_type['steal_malus'])
                        total_bonus -= steal_malus_total
                        bonus_details.append(f"Siphonné: {', '.join(parts)} → **-{steal_malus_total}%**")
                        has_bonusmalus = True

                if leader_cursed:
                    total_bonus = success_chance * -1

                if bonus_details:
                    status_text += "\n\n**Effets actifs:**\n" + "\n".join(bonus_details)

                if has_bonusmalus:
                    status_text += f"\n**Chance totale: {max(min((success_chance + total_bonus), 100.0), 0.0):.1f}%**"

                # Show bonus/maledictions
                embed.add_field(
                    name="📊 Statut",
                    value=status_text,
                    inline=False
                )

                # Show unlocked abilities
                abilities = ClanSystem.get_unlocked_abilities(character.get_level())
                if abilities:
                    top_chars = await self.character_repo.get_top_characters(limit=1)
                    leader_id = top_chars[0].get_discord_id() if top_chars else None
                    is_leader = leader_id == interaction.user.id

                    abilities_list = []
                    for a in abilities:
                        if a['command'] == '/oppress' and not is_leader:
                            continue
                        user_id = -1 if a['is_cooldown_global'] else interaction.user.id
                        result = await self.ability_manager.can_use_ability(
                            user_id,
                            a['command'].replace('/',''),
                            a['cooldown_days'],
                            True
                        )
                        cooldown_text = result[1]  # Get the second value from tuple
                        abilities_list.append(f"• {a['command']} - {a['description']} (⌛ {cooldown_text})")

                    abilities_text = "\n".join(abilities_list)
                    embed.add_field(
                        name="🗡️ Capacités Débloquées",
                        value=abilities_text,
                        inline=False
                    )

                # Show next unlock
                next_unlock = ClanSystem.get_next_unlock(character.get_level())
                if next_unlock:
                    embed.add_field(
                        name="🔒 Prochain Déblocage",
                        value=f"Niveau {next_unlock['level']}: {next_unlock['command']} - {next_unlock['description']}",
                        inline=False
                    )

                await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                print(f"Error in stats command: {e}", file=sys.stderr)
                await self._send_error_embed(
                    interaction,
                    "Une erreur est survenue lors de la récupération des statistiques"
                )

        # ===== PROFILE COMMAND (public version of stats) =====
        @app_commands.guild_only()
        @self.tree.command(name="profile", description="Voir le profil public d'un joueur")
        @app_commands.describe(user="Le joueur dont tu veux voir le profil")
        async def profile(interaction: discord.Interaction, user: Optional[discord.Member] = None):
            try:
                target_user = user if user else interaction.user

                if not await self._has_player_role(target_user):
                    await self._send_error_embed(
                        interaction,
                        f"**{target_user.display_name}** n'a pas le rôle **Joueur**."
                    )
                    return

                character = await self.character_repo.get_character(target_user.id)
                if not character:
                    await self._send_error_embed(
                        interaction,
                        f"**{target_user.display_name}** n'a pas encore de personnage."
                    )
                    return

                clan_info = ClanSystem.get_clan_by_level(character.get_level())

                embed = discord.Embed(
                    title=f"🦇 {target_user.display_name}",
                    description=f"**{clan_info['title']}** du clan **{clan_info['name']}**",
                    color=clan_info['color']
                )
                embed.set_thumbnail(url=target_user.display_avatar.url)

                embed.add_field(name="Niveau", value=f"**{character.get_level()}**", inline=True)

                # Show clan role
                clan_role = discord.utils.get(interaction.guild.roles, name=clan_info['name'])
                if clan_role and clan_role in target_user.roles:
                    embed.add_field(name="Rôle du Clan", value=clan_role.mention, inline=True)

                # Show wings if applicable
                if clan_info['has_wings']:
                    wings_role_name = os.getenv('ROLE_WINGS', 'Ailes')
                    wings_role = discord.utils.get(interaction.guild.roles, name=wings_role_name)
                    if wings_role and wings_role in target_user.roles:
                        embed.add_field(name="✨ Ailes", value=wings_role.mention, inline=True)

                await self._send_public(interaction, embed)
            except Exception as e:
                print(f"Error in profile command: {e}", file=sys.stderr)
                await self._send_error_embed(
                    interaction,
                    "Une erreur est survenue lors de la récupération du profil"
                )

    # ===== PACT LEVEL PROPAGATION =====
    async def _apply_pact_level(self, member: discord.Member, requester_embed: discord.Embed):
        """
        If the member is in an active pact, give the partner a free level.
        Also updates the requester's embed to mention the pact partner got a level.
        """
        partner_id = await self.pact_manager.get_active_pact_partner(member.id)
        if not partner_id:
            return

        partner = member.guild.get_member(partner_id)
        if not partner:
            return

        partner_char = await self.get_or_create_character(partner_id)
        old_level = partner_char.get_level()
        partner_char._level_up()
        await self.character_repo.save_character(partner_char)
        self._discord_characters[partner_char.get_discord_id()] = partner_char
        new_level = partner_char.get_level()

        # Handle clan change for partner
        if ClanSystem.has_clan_changed(old_level, new_level):
            new_clan = ClanSystem.get_clan_by_level(new_level)
            role_assigned = await self._assign_clan_role(partner, new_clan)
            if not role_assigned:
                await self._send_admin_dm(partner, new_clan)

            # Notify partner of clan change + free level via DM
            try:
                dm_embed = discord.Embed(
                    title="🩸 Pacte de Sang — Niveau Gagné !",
                    description=f"Grâce à ton pacte avec **{member.display_name}**, tu es passé au niveau **{new_level}** !\nTu rejoins le clan **{new_clan['name']}** — **{new_clan['title']}** !",
                    color=new_clan['color']
                )
                await partner.send(embed=dm_embed)
            except Exception:
                pass
        else:
            # Notify partner of free level via DM
            clan_info = ClanSystem.get_clan_by_level(new_level)
            try:
                dm_embed = discord.Embed(
                    title="🩸 Pacte de Sang — Niveau Gagné !",
                    description=f"Grâce à ton pacte avec **{member.display_name}**, tu es passé au niveau **{new_level}** !",
                    color=clan_info['color']
                )
                await partner.send(embed=dm_embed)
            except Exception:
                pass

        requester_embed.add_field(
            name="🩸 Pacte de Sang",
            value=f"**{partner.display_name}** gagne également le niveau **{new_level}** !",
            inline=False
        )

        await self.log(partner_id, datetime.now(), f'pact levelup from {member.id} (now level {new_level})')

    # ===== CHARACTER MANAGEMENT =====
    async def get_or_create_character(self, discord_id: int) -> Character:
        """Get character from cache or database, create if doesn't exist"""
        if discord_id in self._discord_characters:
            return self._discord_characters[discord_id]

        character = await self.character_repo.get_character(discord_id)

        if not character:
            character = await self.character_repo.create_character(discord_id)

        self._discord_characters[discord_id] = character
        return character

    # ===== ROLE MANAGEMENT =====
    async def _assign_clan_role(self, member: discord.Member, clan_info: dict) -> bool:
        """
        Assign clan role and wings role if applicable
        Returns True if successful, False if user is admin/owner
        """
        try:
            guild = member.guild

            # Get or create clan role
            clan_role = discord.utils.get(guild.roles, name=clan_info['name'])
            if not clan_role:
                clan_role = await guild.create_role(
                    name=clan_info['name'],
                    color=clan_info['color'],
                    reason="Vampire clan progression"
                )

            # Remove old clan roles
            old_clan_roles = ClanSystem.get_all_clan_role_names()
            for old_role_name in old_clan_roles:
                old_role = discord.utils.get(guild.roles, name=old_role_name)
                if old_role and old_role in member.roles and old_role != clan_role:
                    await member.remove_roles(old_role)

            # Add new clan role
            await member.add_roles(clan_role)

            # Handle wings role for Razielim
            wings_role_name = os.getenv('ROLE_WINGS', 'Ailes')
            wings_role = discord.utils.get(guild.roles, name=wings_role_name)

            if clan_info['has_wings']:
                # Add wings if Razielim or higher
                if not wings_role:
                    wings_role = await guild.create_role(
                        name=wings_role_name,
                        color=discord.Color.purple(),
                        reason="Razielim wings"
                    )
                if wings_role not in member.roles:
                    await member.add_roles(wings_role)
            else:
                # Remove wings if not Razielim
                if wings_role and wings_role in member.roles:
                    await member.remove_roles(wings_role)

            return True

        except discord.Forbidden:
            print(f"⚠️ Cannot assign role to {member.id} (insufficient permissions)", file=sys.stderr)
            return False

    async def _send_admin_dm(self, user: discord.Member, clan_info: dict):
        """Send DM to admin/owner when bot can't assign role"""
        try:
            embed = discord.Embed(
                title="🦇 Évolution de Clan !",
                description=f"Félicitations ! Tu es devenu **{clan_info['title']}** du clan **{clan_info['name']}** !",
                color=clan_info['color']
            )
            embed.add_field(
                name="⚠️ Attribution de Rôle",
                value=f"En raison de tes permissions élevées sur le serveur, je ne peux pas t'attribuer automatiquement le rôle **{clan_info['name']}**.\n\Il faut que tu te l'attribues manuellement si tu le souhaites.",
                inline=False
            )

            # Add wings info if applicable
            if clan_info['has_wings']:
                wings_role_name = os.getenv('ROLE_WINGS', 'Ailes')
                embed.add_field(
                    name="✨ Ailes",
                    value=f"N'oublie pas de t'attribuer également le rôle **{wings_role_name}** !",
                    inline=False
                )

            await user.send(embed=embed)
        except discord.Forbidden:
            print(f"Cannot send DM to {user.name}", file=sys.stderr)
        except Exception as e:
            print(f"Error sending admin DM: {e}", file=sys.stderr)

    async def _check_and_consume_shield(self, target_id: int) -> bool:
        """Check if target has an active shield and consume it. Returns True if blocked."""
        async with self.mdb_con.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(
                    'SELECT shield_until FROM egb_character_bonuses WHERE discord_id = %s',
                    (target_id,)
                )
                row = await cursor.fetchone()
        if row and row.get('shield_until') and row['shield_until'] > datetime.now():
            async with self.mdb_con.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        'UPDATE egb_character_bonuses SET shield_until = NULL WHERE discord_id = %s',
                        (target_id,)
                    )
                    await conn.commit()
            return True
        return False

    async def _send_public(self, interaction: discord.Interaction, embed: discord.Embed):
        """
        Send a public embed. If COMMANDS_CHANNEL_ID is set, posts to that channel
        and acknowledges the interaction ephemerally. Otherwise sends publicly in place.
        """
        commands_channel_id = os.getenv('COMMANDS_CHANNEL_ID', '').strip()
        if commands_channel_id:
            channel = interaction.guild.get_channel(int(commands_channel_id))
            if channel:
                await channel.send(embed=embed)
                await interaction.response.send_message("✅", ephemeral=True, delete_after=1)
                return
        await interaction.response.send_message(embed=embed, ephemeral=False)

    async def _has_player_role(self, member: discord.Member) -> bool:
        """Check if user has the 'Joueur' role"""
        player_role_name = os.getenv('ROLE_PLAYER', 'Joueur')
        player_role = discord.utils.get(member.guild.roles, name=player_role_name)
        return player_role and player_role in member.roles

    async def _get_user_clan_info(self, discord_id: int) -> dict:
        """Get clan info for a user (for embed colors)"""
        try:
            character = await self.character_repo.get_character(discord_id)
            if character:
                return ClanSystem.get_clan_by_level(character.get_level())
        except:
            pass

        # Default to fledgling color
        return ClanSystem.get_clan_by_level(1)

    async def _send_cd_msg_embed(self, interaction: discord.Interaction, message: str, followup: bool = False):
        """Send an error message as an embed"""
        clan_info = await self._get_user_clan_info(interaction.user.id)
        embed = discord.Embed(
            title="Le temps est un cercle",
            description=message,
            color=clan_info['color']
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1332652541909143654.png")

        if followup:
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


    async def _send_error_embed(self, interaction: discord.Interaction, message: str, followup: bool = False):
        """Send an error message as an embed"""
        clan_info = await self._get_user_clan_info(interaction.user.id)
        embed = discord.Embed(
            title="❌ Erreur",
            description=message,
            color=clan_info['color']
        )

        if followup:
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # ===== LOK CHARACTER/QUOTE DATABASE METHODS =====
    async def lok_character_exists(self, character: str, lang: str) -> bool:
        """Check if a LoK character exists in the database"""
        try:
            lang = self._validate_language(lang)

            async with self.mdb_con.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        f'SELECT COUNT(1) FROM egb_dim_characters WHERE name_{lang} = %s',
                        (character,)
                    )
                    result = await cursor.fetchone()
                    return result[0] > 0
        except Exception as e:
            print(f"Error checking character existence: {e}", file=sys.stderr)
            return False

    async def get_all_characters(self):
        """Load all character names for autocomplete"""
        try:
            lang = os.getenv('DEFAULT_LANGUAGE', 'fr').lower()
            lang = self._validate_language(lang)

            async with self.mdb_con.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        f'SELECT DISTINCT name_{lang} FROM egb_dim_characters ORDER BY name_{lang}'
                    )
                    resultset = await cursor.fetchall()

            self.characters = [row[0] for row in resultset]
            print(f"Loaded {len(self.characters)} characters for autocomplete")
        except Exception as e:
            print(f"Error loading characters: {e}", file=sys.stderr)

    async def get_random_quote(self, character: str, lang: str) -> Optional[str]:
        """Get a random quote from a specific character"""
        try:
            lang = self._validate_language(lang)

            async with self.mdb_con.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        f'''SELECT q.quote_{lang}
                            FROM egb_quotes q
                            INNER JOIN egb_dim_characters c ON c.Id = q.character_id
                            WHERE c.name_{lang} = %s
                            ORDER BY RAND()
                            LIMIT 1''',
                        (character,)
                    )
                    result = await cursor.fetchone()

            return result[0] if result else None
        except Exception as e:
            print(f"Error fetching quote: {e}", file=sys.stderr)
            return None

    # ===== UTILITY METHODS =====
    async def log(self, user_id: int, time: datetime, action: str):
        """Log user action to database"""
        try:
            async with self.mdb_con.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        'INSERT INTO egb_log(DiscordId, LogTime, Action) VALUES (%s, %s, %s)',
                        (user_id, time, action)
                    )
        except Exception as e:
            print(f"Error logging action: {e}", file=sys.stderr)

    def _validate_language(self, lang: Optional[str]) -> str:
        """Validate and normalize language parameter"""
        if lang is None:
            lang = os.getenv('DEFAULT_LANGUAGE', 'fr')

        lang = lang.lower()

        if lang not in self.ALLOWED_LANGUAGES:
            raise ValueError(f'Langue "{lang}" non supportée. Utilisez : {", ".join(self.ALLOWED_LANGUAGES)}')

        return lang

    def get_config(self, key: str, default: str) -> str:
        """Get configuration value from environment"""
        return os.getenv(key, default)

    def get_clan_info_for_user(self, level: int) -> dict:
        """Get clan information for a given level"""
        return ClanSystem.get_clan_by_level(level)

    def has_clan_changed(self, old_level: int, new_level: int) -> bool:
        """Check if clan changed between levels"""
        return ClanSystem.has_clan_changed(old_level, new_level)