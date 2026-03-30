import os
import discord
import aiomysql
from discord import app_commands
from datetime import datetime
from datetime import timedelta
from .clan_system import ClanSystem
import random
import sys

class AbilityCommands:
    """
    Contains all ability command implementations
    """
    
    @staticmethod
    def register_commands(bot):
        """Register all ability commands to the bot"""
        
        # ===== CHAUSSETTE (Level 5+) =====
        @bot.tree.command(name="chaussette", description="Crier CHAUSSETTE pour un level gratuit par semaine")
        async def chaussette(interaction: discord.Interaction):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                # Check level requirement
                if character.get_level() < 5:
                    await bot._send_error_embed(
                        interaction,
                        "Tu dois être niveau 5 minimum pour utiliser cette capacité."
                    )
                    return
                
                # Check cooldown (once per week)
                can_use, msg = await bot.ability_manager.can_use_ability(
                    interaction.user.id, 
                    'chaussette', 
                    cooldown_days=7
                )
                
                if not can_use:
                    await bot._send_cd_msg_embed(interaction, f"Capacité en cooldown. {msg}")
                    return

                # Level up !
                character._level_up()
                await bot.character_repo.save_character(character)
                bot._discord_characters[character.get_discord_id()] = character

                # Clear bonuses after use
                async with bot.mdb_con.acquire() as conn:
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

                await bot.ability_manager.use_ability(interaction.user.id, 'chaussette')
                
                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="🧦 CHAUSSETTE !",
                    description=f"Tu as crié CHAUSSETTE et automatiquement gagné **1 niveau** !",
                    color=clan_info['color']
                )

                # Check if clan changed
                if ClanSystem.has_clan_changed(character.get_level()-1, character.get_level()):
                    old_clan = ClanSystem.get_clan_by_level(character.get_level()-1)
                    new_clan = ClanSystem.get_clan_by_level(character.get_level())
                    
                    # Assign new roles
                    role_assigned = await bot._assign_clan_role(interaction.user, new_clan)
                    
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
                        await bot._send_admin_dm(interaction.user, new_clan)
                    
                    # Check for new abilities
                    new_abilities = [a for a in new_clan['abilities'] if a['level'] == character.get_level()]
                    if new_abilities:
                        abilities_text = "\n".join([f"• {a['command']} - {a['description']}" for a in new_abilities])
                        embed.add_field(
                            name="✨ Nouvelles Capacités Débloquées",
                            value=abilities_text,
                            inline=False
                        )
                
                await bot._apply_pact_level(interaction.user, embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await bot.log(interaction.user.id, datetime.now(), f'chaussette')
                
            except Exception as e:
                print(f"Error in chaussette command: {e}")
                await bot._send_error_embed(interaction, "Une erreur est survenue.")

        # ===== DEVOUR (Level 5+) =====
        @bot.tree.command(name="devour", description="Dévorer les âmes pour un bonus d'XP")
        async def devour(interaction: discord.Interaction):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                # Check level requirement
                if character.get_level() < 5:
                    await bot._send_error_embed(
                        interaction,
                        "Tu dois être niveau 5 minimum pour utiliser cette capacité."
                    )
                    return
                
                # Check cooldown (once per day)
                can_use, msg = await bot.ability_manager.can_use_ability(
                    interaction.user.id, 
                    'devour', 
                    cooldown_days=1
                )
                
                if not can_use:
                    await bot._send_cd_msg_embed(interaction, f"Capacité en cooldown. {msg}")
                    return
                
                # Devour gives a small bonus to next levelup chance
                bonus = random.randint(3, 8)
                
                # Store bonus in character
                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            '''INSERT INTO egb_character_bonuses (discord_id, devour_bonus)
                               VALUES (%s, %s)
                               ON DUPLICATE KEY UPDATE 
                               devour_bonus = devour_bonus + %s''',
                            (character.get_discord_id(), bonus, bonus)
                        )
                
                await bot.ability_manager.use_ability(interaction.user.id, 'devour')

                partner_id = await bot.pact_manager.get_active_pact_partner(interaction.user.id)
                if partner_id:
                    async with bot.mdb_con.acquire() as conn:
                        async with conn.cursor() as cursor:
                            await cursor.execute(
                                '''INSERT INTO egb_character_bonuses (discord_id, devour_bonus)
                                   VALUES (%s, %s)
                                   ON DUPLICATE KEY UPDATE devour_bonus = devour_bonus + %s''',
                                (partner_id, bonus, bonus)
                            )
                            await conn.commit()
                    try:
                        partner_user = await bot.fetch_user(partner_id)
                        await partner_user.send(embed=discord.Embed(
                            title="🩸 Pacte de Sang — Dévoration",
                            description=f"Ton pacte avec **{interaction.user.display_name}** t'a transmis un bonus de dévoration (**+{bonus}%**) pour ton prochain levelup !",
                            color=discord.Color.dark_red()
                        ))
                    except Exception:
                        pass

                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="🩸 Dévoration d'Âme",
                    description=f"Tu as dévoré une âme et gagné **+{bonus}%** pour ta prochaine tentative de level up !",
                    color=clan_info['color']
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await bot.log(interaction.user.id, datetime.now(), f'devour (+{bonus}%)')
                
            except Exception as e:
                print(f"Error in devour command: {e}")
                await bot._send_error_embed(interaction, "Une erreur est survenue.")
        
        # ===== SWIM (Level 20+) =====
        @bot.tree.command(name="swim", description="Contourner le cooldown quotidien une fois par semaine")
        async def swim(interaction: discord.Interaction):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                if character.get_level() < 20:
                    await bot._send_error_embed(
                        interaction,
                        "Tu dois être niveau 20 minimum pour utiliser cette capacité."
                    )
                    return
                
                # Check if already leveled up today
                can_attempt, msg = character.can_attempt_levelup()
                if can_attempt:
                    await bot._send_error_embed(
                        interaction,
                        "Tu n'as pas encore réussi de level up aujourd'hui. Utilisez `/levelup` normalement."
                    )
                    return
                
                # Check weekly cooldown
                can_use, cooldown_msg = await bot.ability_manager.can_use_ability(
                    interaction.user.id,
                    'swim',
                    cooldown_days=7
                )
                
                if not can_use:
                    await bot._send_cd_msg_embed(interaction, f"Capacité en cooldown. {cooldown_msg}")
                    return
                
                # Grant swim bonus (bypasses cooldowns on next attempt)
                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            '''INSERT INTO egb_character_bonuses (discord_id, swim_active)
                               VALUES (%s, TRUE)
                               ON DUPLICATE KEY UPDATE swim_active = TRUE''',
                            (character.get_discord_id(),)
                        )
                
                await bot.ability_manager.use_ability(interaction.user.id, 'swim')

                partner_id = await bot.pact_manager.get_active_pact_partner(interaction.user.id)
                if partner_id:
                    async with bot.mdb_con.acquire() as conn:
                        async with conn.cursor() as cursor:
                            await cursor.execute(
                                '''INSERT INTO egb_character_bonuses (discord_id, swim_active)
                                   VALUES (%s, TRUE)
                                   ON DUPLICATE KEY UPDATE swim_active = TRUE''',
                                (partner_id,)
                            )
                            await conn.commit()
                    try:
                        partner_user = await bot.fetch_user(partner_id)
                        await partner_user.send(embed=discord.Embed(
                            title="🌊 Pacte de Sang — Nage",
                            description=f"Ton pacte avec **{interaction.user.display_name}** t'a transmis le bonus de nage !\nTu peux contourner le cooldown de levelup sur ta prochaine tentative.",
                            color=discord.Color.blue()
                        ))
                    except Exception:
                        pass

                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="🌊 Nage dans les Abysses",
                    description="Tu as contourné les limites ! Ta prochaine tentative ignorera la limite quotidienne.",
                    color=clan_info['color']
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await bot.log(interaction.user.id, datetime.now(), 'swim (bypass cooldown)')
                
            except Exception as e:
                print(f"Error in swim command: {e}")
                await bot._send_error_embed(interaction, "Une erreur est survenue.")
            
        # ===== CURSE (Level 10+) =====
        @bot.tree.command(name="curse", description="Maudire un autre joueur (-5% sur sa prochaine tentative)")
        @app_commands.describe(target="Le joueur à maudire")
        async def curse(interaction: discord.Interaction, target: discord.Member):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                if character.get_level() < 10:
                    await bot._send_error_embed(
                        interaction,
                        "Tu dois être niveau 10 minimum pour utiliser cette capacité."
                    )
                    return
                
                # Can't curse yourself
                if target.id == interaction.user.id:
                    await bot._send_error_embed(interaction, "Tu ne peux pas te maudire toi-même !")
                    return
                
                # Target must have player role
                if not await bot._has_player_role(target):
                    await bot._send_error_embed(interaction, f"{target.display_name} n'a pas le rôle **Joueur**.")
                    return
                
                # Check cooldown (once per week)
                can_use, cooldown_msg = await bot.ability_manager.can_use_ability(
                    interaction.user.id,
                    'curse',
                    cooldown_days=7
                )
                
                if not can_use:
                    await bot._send_cd_msg_embed(interaction, f"Capacité en cooldown. {cooldown_msg}")
                    return
                
                # Check target's shield
                if await bot._check_and_consume_shield(target.id):
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="🛡️ Bouclier !",
                            description=f"**{target.display_name}** est protégé par un bouclier mystique ! Ta malédiction est absorbée.",
                            color=discord.Color.blue()
                        ),
                        ephemeral=True
                    )
                    try:
                        await target.send(embed=discord.Embed(
                            title="🛡️ Bouclier Activé !",
                            description=f"Ton bouclier a absorbé la malédiction de **{interaction.user.display_name}** !",
                            color=discord.Color.blue()
                        ))
                    except Exception:
                        pass
                    return

                # Apply curse
                curse_amount = 5
                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            '''INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
                               VALUES (%s, %s, 'curse', %s)''',
                            (target.id, interaction.user.id, curse_amount)
                        )
                        await conn.commit()

                await bot.ability_manager.use_ability(interaction.user.id, 'curse')

                target_partner_id = await bot.pact_manager.get_active_pact_partner(target.id)
                if target_partner_id:
                    partner_blocked = await bot._check_and_consume_shield(target_partner_id)
                    if not partner_blocked:
                        async with bot.mdb_con.acquire() as conn:
                            async with conn.cursor() as cursor:
                                await cursor.execute(
                                    '''INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
                                       VALUES (%s, %s, 'curse', %s)''',
                                    (target_partner_id, interaction.user.id, curse_amount)
                                )
                                await conn.commit()
                        try:
                            partner_user = await bot.fetch_user(target_partner_id)
                            await partner_user.send(embed=discord.Embed(
                                title="💀 Pacte de Sang — Malédiction",
                                description=f"**{interaction.user.display_name}** a maudit ton partenaire de pacte **{target.display_name}** !\nGrâce au pacte, tu subis également **-{curse_amount}%** pour ton prochain levelup.",
                                color=discord.Color.dark_red()
                            ))
                        except Exception:
                            pass
                    else:
                        try:
                            partner_user = await bot.fetch_user(target_partner_id)
                            await partner_user.send(embed=discord.Embed(
                                title="🛡️ Bouclier Activé !",
                                description=f"Ton bouclier a absorbé la malédiction de **{interaction.user.display_name}** (transmise via le pacte de **{target.display_name}**) !",
                                color=discord.Color.blue()
                            ))
                        except Exception:
                            pass

                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="💀 Malédiction",
                    description=f"Tu as maudit {target.mention} !\n\nIls subiront **-{curse_amount}%** de chance sur leur prochaine tentative de level up.",
                    color=clan_info['color']
                )
                
                # Notify target via DM
                try:
                    target_embed = discord.Embed(
                        title="💀 Malédiction !",
                        description=f"{interaction.user.display_name} t'a maudit avec **curse** !\nTa prochaine tentative de level up aura **-{curse_amount}%** de chance.",
                        color=discord.Color.dark_red()
                    )
                    await target.send(embed=target_embed)
                except:
                    pass  # User has DMs disabled
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await bot.log(interaction.user.id, datetime.now(), f'curse on {target.id}')
                
            except Exception as e:
                print(f"Error in curse command: {e}")
                await bot._send_error_embed(interaction, "Une erreur est survenue.")
                      
        # ===== EVOLVE (Level 30+) =====
        @bot.tree.command(name="evolve", description="Obtenir les ailes de Raziel (rôle cosmétique)")
        async def evolve(interaction: discord.Interaction):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                if character.get_level() < 30:
                    await bot._send_error_embed(
                        interaction,
                        "Tu dois être niveau 30 minimum pour utiliser cette capacité."
                    )
                    return
                
                wings_role_name = os.getenv('ROLE_WINGS', 'Ailes')
                wings_role = discord.utils.get(interaction.guild.roles, name=wings_role_name)
                
                if not wings_role:
                    wings_role = await interaction.guild.create_role(
                        name=wings_role_name,
                        color=discord.Color.purple(),
                        reason="Razielim wings"
                    )
                
                if wings_role in interaction.user.roles:
                    await bot._send_error_embed(
                        interaction,
                        "Tu as déjà les ailes de Raziel !"
                    )
                    return
                
                try:
                    await interaction.user.add_roles(wings_role)
                    
                    clan_info = bot.get_clan_info_for_user(character.get_level())
                    embed = discord.Embed(
                        title="👼 Évolution Céleste",
                        description=f"Tes ailes se déploient majestueusement !\n\Tu as obtenu le rôle {wings_role.mention} !",
                        color=clan_info['color']
                    )
                    embed.set_image(url="https://i.imgur.com/raziel_wings.gif")  # Replace with actual image if desired
                    
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    await bot.log(interaction.user.id, datetime.now(), 'evolve (obtained wings)')
                    
                except discord.Forbidden:
                    await bot._send_error_embed(
                        interaction,
                        f"Je ne peux pas t'attribuer le rôle. Tu dois t'attribuer manuellement le rôle **{wings_role_name}**."
                    )
                
            except Exception as e:
                print(f"Error in evolve command: {e}")
                await bot._send_error_embed(interaction, "Une erreur est survenue.")
        
        # ===== SPECTRAL (Level 30+) =====
        @bot.tree.command(name="spectral", description="Voir le royaume spectral (classement caché)")
        async def spectral(interaction: discord.Interaction):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                if character.get_level() < 30:
                    await bot._send_error_embed(
                        interaction,
                        "Tu dois être niveau 30 minimum pour utiliser cette capacité."
                    )
                    return
                
                # Get top characters with additional hidden stats
                top_characters = await bot.character_repo.get_top_characters(limit=10)
                
                if not top_characters:
                    await bot._send_error_embed(interaction, "Aucun personnage trouvé.")
                    return
                
                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="👁️ Royaume Spectral",
                    description="*Tu perçois les âmes des vampires les plus puissants...*",
                    color=clan_info['color']
                )
                
                for idx, char in enumerate(top_characters, 1):
                    try:
                        user = await bot.fetch_user(char.get_discord_id())
                        char_clan = bot.get_clan_info_for_user(char.get_level())
                        
                        # Show hidden stats
                        last_attempt = char.get_last_attempt()
                        last_attempt_str = last_attempt.strftime("%d/%m %H:%M") if last_attempt else "Jamais"
                        
                        # Calculate their current success chance
                        base = int(os.getenv('BASE_LEVELUP_CHANCE', '20'))
                        bonus = int(os.getenv('BONUS_PER_HOUR', '5'))
                        max_c = int(os.getenv('MAX_LEVELUP_CHANCE', '80'))
                        success_chance = char.calculate_success_chance(base, bonus, max_c)
                        
                        embed.add_field(
                            name=f"{idx}. {user.display_name}",
                            value=f"**Niveau {char.get_level()}** - {char_clan['name']}\nDernière tentative: {last_attempt_str}\nChance actuelle: {success_chance:.1f}%",
                            inline=False
                        )
                    except:
                        pass
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await bot.log(interaction.user.id, datetime.now(), 'spectral (view leaderboard)')
                
            except Exception as e:
                print(f"Error in spectral command: {e}")
                await bot._send_error_embed(interaction, "Une erreur est survenue.")

        # ===== entomb (Level 10+) =====
        @bot.tree.command(name="entomb", description="Condamner le leader à ne pas pouvoir levelup pendant 1-2 jours")
        async def entomb(interaction: discord.Interaction):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                # Check level requirement
                if character.get_level() < 10:
                    await bot._send_error_embed(
                        interaction,
                        "Tu dois être niveau 10 minimum pour utiliser cette capacité."
                    )
                    return
                
                # Check cooldown (once per week)
                can_use, msg = await bot.ability_manager.can_use_ability(
                    -1, 
                    'entomb', 
                    cooldown_days=7
                )
                
                if not can_use:
                    await bot._send_cd_msg_embed(interaction, f"Cette commande a un cooldown global au serveur. {msg}")
                    return
                
                # Get the top player (highest level, earliest if tied)
                top_characters = await bot.character_repo.get_top_characters(limit=1)
                
                if not top_characters:
                    await bot._send_error_embed(interaction, "Aucun joueur trouvé.")
                    return
                
                leader = top_characters[0]
                leader_id = leader.get_discord_id()
                
                # Don't let them entomb themselves
                if leader_id == interaction.user.id:
                    await bot._send_error_embed(
                        interaction,
                        "Tu es le leader ! Tu ne peux pas te condamner toi-même."
                    )
                    return
                
                # Check if leader is already cursed
                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(
                            'SELECT leader_curse_until FROM egb_character_bonuses WHERE discord_id = %s',
                            (leader_id,)
                        )
                        result = await cursor.fetchone()
                        
                        if result and result['leader_curse_until']:
                            curse_until = result['leader_curse_until']
                            if curse_until > datetime.now():
                                await bot._send_error_embed(
                                    interaction,
                                    f"⚠️ Le leader est déjà sous l'effet d'une condamnation jusqu'au {curse_until.strftime('%d/%m/%Y à %H:%M')} !"
                                )
                                return
                
                # Check leader's shield
                if await bot._check_and_consume_shield(leader_id):
                    try:
                        leader_user = await bot.fetch_user(leader_id)
                        await leader_user.send(embed=discord.Embed(
                            title="🛡️ Bouclier Activé !",
                            description=f"Ton bouclier a absorbé la condamnation de **{interaction.user.display_name}** !",
                            color=discord.Color.blue()
                        ))
                    except Exception:
                        pass
                    clan_info = bot.get_clan_info_for_user(character.get_level())
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="🛡️ Bouclier !",
                            description=f"**Le leader** est protégé par un bouclier mystique ! Ta condamnation est absorbée.",
                            color=discord.Color.blue()
                        ),
                        ephemeral=True
                    )
                    return

                # Apply the curse - random 1-2 days
                curse_days = random.choice([1, 2])
                curse_until = datetime.now() + timedelta(days=curse_days)

                # Fetch leader_user before pact mirror (needed for DM text)
                try:
                    leader_user = await bot.fetch_user(leader_id)
                except Exception:
                    leader_user = None
                leader_display = leader_user.display_name if leader_user else f"#{leader_id}"

                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            '''INSERT INTO egb_character_bonuses (discord_id, leader_curse_until)
                               VALUES (%s, %s)
                               ON DUPLICATE KEY UPDATE leader_curse_until = %s''',
                            (leader_id, curse_until, curse_until)
                        )
                        await conn.commit()

                # Mark ability as used
                await bot.ability_manager.use_ability(interaction.user.id, 'entomb')

                # Mirror entomb to leader's pact partner if any
                leader_partner_id = await bot.pact_manager.get_active_pact_partner(leader_id)
                if leader_partner_id:
                    partner_blocked = await bot._check_and_consume_shield(leader_partner_id)
                    if not partner_blocked:
                        async with bot.mdb_con.acquire() as conn:
                            async with conn.cursor() as cursor:
                                await cursor.execute(
                                    '''INSERT INTO egb_character_bonuses (discord_id, leader_curse_until)
                                       VALUES (%s, %s)
                                       ON DUPLICATE KEY UPDATE leader_curse_until = %s''',
                                    (leader_partner_id, curse_until, curse_until)
                                )
                                await conn.commit()
                        try:
                            partner_user = await bot.fetch_user(leader_partner_id)
                            partner_dm = discord.Embed(
                                title="⚡ Condamnation Divine !",
                                description=f"Ton pacte avec **{leader_display}** t'entraîne dans sa condamnation !\nTu ne pourras pas monter de niveau pendant **{curse_days} jour(s)** !",
                                color=discord.Color.dark_red()
                            )
                            partner_dm.add_field(name="Levée de la condamnation", value=curse_until.strftime('%d/%m/%Y à %H:%M'), inline=False)
                            await partner_user.send(embed=partner_dm)
                        except Exception:
                            pass
                    else:
                        try:
                            partner_user = await bot.fetch_user(leader_partner_id)
                            await partner_user.send(embed=discord.Embed(
                                title="🛡️ Bouclier Activé !",
                                description=f"Ton bouclier a absorbé la condamnation de **{interaction.user.display_name}** (transmise via le pacte de **{leader_display}**) !",
                                color=discord.Color.blue()
                            ))
                        except Exception:
                            pass

                # Try to notify the leader
                if leader_user:
                    try:
                        dm_embed = discord.Embed(
                            title="⚡ Condamnation Divine !",
                            description=f"L'Ancien t'a condamné ! Tu ne pourras pas monter de niveau pendant **{curse_days} jour(s)** !",
                            color=discord.Color.dark_red()
                        )
                        dm_embed.add_field(
                            name="Levée de la condamnation",
                            value=curse_until.strftime('%d/%m/%Y à %H:%M'),
                            inline=False
                        )
                        dm_embed.set_footer(text=f"Condamné par {interaction.user.display_name}")
                        await leader_user.send(embed=dm_embed)
                    except Exception:
                        pass

                # Send success message
                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="⚡ Condamnation Lancée !",
                    description=f"Tu as entomb **{leader_display}** (Niveau {leader.get_level()}) !\n\nIls ne pourront pas monter de niveau pendant **{curse_days} jour(s)** !",
                    color=clan_info['color']
                )
                embed.add_field(
                    name="Fin de la condamnation",
                    value=curse_until.strftime('%d/%m/%Y à %H:%M'),
                    inline=False
                )
                
                await bot._send_public(interaction, embed)
                await bot.log(interaction.user.id, datetime.now(), f'entomb {leader_id}')
                
            except Exception as e:
                print(f"Error in entomb command: {e}", file=sys.stderr)
                await bot._send_error_embed(interaction, "Une erreur est survenue.")
        
        # ===== BLESS (All levels) =====
        @bot.tree.command(name="bless", description="Bénir un joueur pour lui donner un bonus de 3-8% au prochain levelup")
        @app_commands.describe(target="Le joueur à bénir")
        async def bless(interaction: discord.Interaction, target: discord.Member):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return
            
            try:
                # Check if target has player role
                if not await bot._has_player_role(target):
                    await bot._send_error_embed(
                        interaction,
                        f"**{target.display_name}** n'a pas le rôle **Joueur**."
                    )
                    return
                
                # Can't bless yourself
                if target.id == interaction.user.id:
                    await bot._send_error_embed(
                        interaction,
                        "Tu ne peux pas te bénir toi-même !"
                    )
                    return
                
                # Check cooldown (once per week)
                can_use, msg = await bot.ability_manager.can_use_ability(
                    interaction.user.id, 
                    'bless', 
                    cooldown_days=7
                )
                
                if not can_use:
                    await bot._send_cd_msg_embed(interaction, f"Capacité en cooldown. {msg}")
                    return
                
                # Give random 3-8% bonus (cumulative)
                bonus = random.randint(3, 8)
                
                # Store bless effect
                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            '''INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
                               VALUES (%s, %s, 'bless', %s)''',
                            (target.id, interaction.user.id, bonus)
                        )
                        await conn.commit()
                
                # Mark ability as used
                await bot.ability_manager.use_ability(interaction.user.id, 'bless')

                target_partner_id = await bot.pact_manager.get_active_pact_partner(target.id)
                if target_partner_id:
                    async with bot.mdb_con.acquire() as conn:
                        async with conn.cursor() as cursor:
                            await cursor.execute(
                                '''INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
                                   VALUES (%s, %s, 'bless', %s)''',
                                (target_partner_id, interaction.user.id, bonus)
                            )
                            await conn.commit()
                    try:
                        partner_user = await bot.fetch_user(target_partner_id)
                        await partner_user.send(embed=discord.Embed(
                            title="✨ Pacte de Sang — Bénédiction",
                            description=f"**{interaction.user.display_name}** a béni ton partenaire de pacte **{target.display_name}** !\nGrâce au pacte, tu reçois également **+{bonus}%** pour ton prochain levelup !",
                            color=discord.Color.gold()
                        ))
                    except Exception:
                        pass

                # Get target's character
                target_character = await bot.get_or_create_character(target.id)
                
                # Try to notify the target
                try:
                    target_clan = bot.get_clan_info_for_user(target_character.get_level())
                    dm_embed = discord.Embed(
                        title="✨ Bénédiction Reçue !",
                        description=f"{interaction.user.display_name} t'a béni(e) !\nTu as reçu **+{bonus}%** de chance pour ton prochain levelup !",
                        color=discord.Color.gold()
                    )
                    dm_embed.set_footer(text="Cette bénédiction est cumulative avec d'autres bonus")
                    
                    await target.send(embed=dm_embed)
                except:
                    pass  # If we can't DM them, that's okay
                
                # Send success message
                character = await bot.get_or_create_character(interaction.user.id)
                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="✨ Bénédiction Accordée !",
                    description=f"Tu as béni **{target.display_name}** !\n\nIls ont reçu **+{bonus}%** de chance pour leur prochain levelup.",
                    color=clan_info['color']
                )
                embed.set_footer(text="Les bénédictions sont cumulatives")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await bot.log(interaction.user.id, datetime.now(), f'bless {target.id} (+{bonus}%)')
                
            except Exception as e:
                print(f"Error in bless command: {e}", file=sys.stderr)
                await bot._send_error_embed(interaction, "Une erreur est survenue.")

        @bot.tree.command(name="oppress", description="[LEADER ONLY] Infliger un malus à tous les autres joueurs pour la journée")
        async def oppress(interaction: discord.Interaction):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                # Get the top player (leader)
                top_characters = await bot.character_repo.get_top_characters(limit=1)
                
                if not top_characters:
                    await bot._send_error_embed(interaction, "Aucun leader trouvé.")
                    return
                
                leader = top_characters[0]
                leader_id = leader.get_discord_id()
                
                # Check if user is the leader
                if interaction.user.id != leader_id :
                    await bot._send_error_embed(
                        interaction,
                        "⚠️ Seul le **Leader** peut utiliser cette capacité !"
                    )
                    return
                
                # Check cooldown (once per week) - GLOBAL cooldown
                can_use, msg = await bot.ability_manager.can_use_ability(
                    -1,  # Global key, not per-user
                    'oppress', 
                    cooldown_days=7
                )
                
                if not can_use:
                    await bot._send_cd_msg_embed(interaction, f"Capacité en cooldown. {msg}")
                    return
                
                # Calculate malus percentage (20-50%)
                malus_percent = random.randint(20, 50)*-1
                
                # Calculate end of day (midnight tonight)
                now = datetime.now()
                end_of_day = datetime.combine(now.date(), datetime.max.time())
                
                # Apply malus to all players except the leader
                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor() as cursor:
                        # Apply to all existing players
                        await cursor.execute(
                            '''INSERT INTO egb_character_bonuses (discord_id, oppression_malus, oppression_until)
                            SELECT discord_id, %s, %s FROM egb_characters WHERE discord_id != %s
                            ON DUPLICATE KEY UPDATE 
                                oppression_malus = VALUES(oppression_malus),
                                oppression_until = VALUES(oppression_until)''',
                            (malus_percent, end_of_day, leader_id)
                        )
                        affected_count = cursor.rowcount
                        await conn.commit()
                
                # Mark ability as used
                await bot.ability_manager.use_ability(leader_id, 'oppress')
                
                # Send success message
                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="👑 Oppression du Leader !",
                    description=f"Tu as infligé un malus de **{malus_percent}%** XP à tous les autres joueurs !",
                    color=clan_info['color']
                )
                embed.add_field(
                    name="⏰ Durée",
                    value=f"Jusqu'à minuit ({end_of_day.strftime('%d/%m/%Y à %H:%M')})",
                    inline=False
                )
                embed.add_field(
                    name="👥 Joueurs affectés",
                    value=f"{affected_count} joueur(s)",
                    inline=False
                )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await bot.log(interaction.user.id, datetime.now(), f'oppress {malus_percent}% until {end_of_day}')
                
            except Exception as e:
                import sys
                print(f"Error in oppress command: {e}", file=sys.stderr)
                await bot._send_error_embed(interaction, "Une erreur est survenue.")

        # ===== STEAL (Level 40+) =====
        @bot.tree.command(name="steal", description="Siphonner 5-10% de chance du prochain levelup d'un joueur")
        @app_commands.describe(target="Le joueur dont tu veux siphonner la chance")
        async def steal(interaction: discord.Interaction, target: discord.Member):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return

            try:
                character = await bot.get_or_create_character(interaction.user.id)

                if character.get_level() < 40:
                    await bot._send_error_embed(
                        interaction,
                        "Tu dois être niveau 40 minimum pour utiliser cette capacité."
                    )
                    return

                if target.id == interaction.user.id:
                    await bot._send_error_embed(interaction, "Tu ne peux pas te voler toi-même !")
                    return

                if not await bot._has_player_role(target):
                    await bot._send_error_embed(interaction, f"**{target.display_name}** n'a pas le rôle **Joueur**.")
                    return

                # Check cooldown (rolling 24h)
                can_use, msg = await bot.ability_manager.can_use_ability(
                    interaction.user.id,
                    'steal',
                    cooldown_days=1
                )

                if not can_use:
                    await bot._send_cd_msg_embed(interaction, f"Capacité en cooldown. {msg}")
                    return

                amount = random.randint(5, 10)

                # Check target's shield — blocks the entire steal
                if await bot._check_and_consume_shield(target.id):
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="🛡️ Bouclier !",
                            description=f"**{target.display_name}** est protégé par un bouclier mystique ! Ton siphonage est bloqué.",
                            color=discord.Color.blue()
                        ),
                        ephemeral=True
                    )
                    try:
                        await target.send(embed=discord.Embed(
                            title="🛡️ Bouclier Activé !",
                            description=f"Ton bouclier a bloqué le siphonage de **{interaction.user.display_name}** !",
                            color=discord.Color.blue()
                        ))
                    except Exception:
                        pass
                    return

                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            '''INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
                               VALUES (%s, %s, 'steal_bonus', %s)''',
                            (interaction.user.id, target.id, amount)
                        )
                        await cursor.execute(
                            '''INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
                               VALUES (%s, %s, 'steal_malus', %s)''',
                            (target.id, interaction.user.id, amount)
                        )
                        await conn.commit()

                await bot.ability_manager.use_ability(interaction.user.id, 'steal')

                # Mirror steal_bonus to thief's pact partner
                thief_partner_id = await bot.pact_manager.get_active_pact_partner(interaction.user.id)
                if thief_partner_id:
                    async with bot.mdb_con.acquire() as conn:
                        async with conn.cursor() as cursor:
                            await cursor.execute(
                                '''INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
                                   VALUES (%s, %s, 'steal_bonus', %s)''',
                                (thief_partner_id, target.id, amount)
                            )
                            await conn.commit()
                    try:
                        partner_user = await bot.fetch_user(thief_partner_id)
                        await partner_user.send(embed=discord.Embed(
                            title="🩸 Pacte de Sang — Vol d'Essence",
                            description=f"Ton pacte avec **{interaction.user.display_name}** t'a transmis un vol sur **{target.display_name}** (**+{amount}%**) pour ton prochain levelup !",
                            color=discord.Color.dark_red()
                        ))
                    except Exception:
                        pass

                # Mirror steal_malus to victim's pact partner
                victim_partner_id = await bot.pact_manager.get_active_pact_partner(target.id)
                if victim_partner_id:
                    partner_blocked = await bot._check_and_consume_shield(victim_partner_id)
                    if not partner_blocked:
                        async with bot.mdb_con.acquire() as conn:
                            async with conn.cursor() as cursor:
                                await cursor.execute(
                                    '''INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
                                       VALUES (%s, %s, 'steal_malus', %s)''',
                                    (victim_partner_id, interaction.user.id, amount)
                                )
                                await conn.commit()
                        try:
                            partner_user = await bot.fetch_user(victim_partner_id)
                            await partner_user.send(embed=discord.Embed(
                                title="🩸 Pacte de Sang — Siphonage",
                                description=f"Ton partenaire de pacte **{target.display_name}** s'est fait siphonner par **{interaction.user.display_name}** !\nGrâce au pacte, tu subis également **-{amount}%** pour ton prochain levelup.",
                                color=discord.Color.dark_red()
                            ))
                        except Exception:
                            pass
                    else:
                        try:
                            partner_user = await bot.fetch_user(victim_partner_id)
                            await partner_user.send(embed=discord.Embed(
                                title="🛡️ Bouclier Activé !",
                                description=f"Ton bouclier a absorbé le siphonage de **{interaction.user.display_name}** (transmis via le pacte de **{target.display_name}**) !",
                                color=discord.Color.blue()
                            ))
                        except Exception:
                            pass

                try:
                    target_embed = discord.Embed(
                        title="🩸 Essence Siphonnée !",
                        description=f"**{interaction.user.display_name}** t'a siphonné **{amount}%** de chance pour ton prochain levelup !",
                        color=discord.Color.dark_red()
                    )
                    await target.send(embed=target_embed)
                except Exception:
                    pass

                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="🩸 Vol d'Essence !",
                    description=f"Tu as siphonné **+{amount}%** de chance à **{target.display_name}** !\nCe bonus s'appliquera à ta prochaine tentative de levelup.",
                    color=clan_info['color']
                )

                await interaction.response.send_message(embed=embed, ephemeral=True)
                await bot.log(interaction.user.id, datetime.now(), f'steal {amount}% from {target.id}')

            except Exception as e:
                print(f"Error in steal command: {e}", file=sys.stderr)
                await bot._send_error_embed(interaction, "Une erreur est survenue.")

        # ===== PACT (Level 20+) =====
        @bot.tree.command(name="pact", description="Sceller un Pacte de Sang avec un autre joueur pour 24h")
        @app_commands.describe(target="Le joueur avec qui sceller le pacte")
        async def pact(interaction: discord.Interaction, target: discord.Member):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return

            try:
                character = await bot.get_or_create_character(interaction.user.id)

                if character.get_level() < 20:
                    await bot._send_error_embed(
                        interaction,
                        "Tu dois être niveau 20 minimum pour sceller un Pacte de Sang."
                    )
                    return

                if target.id == interaction.user.id:
                    await bot._send_error_embed(interaction, "Tu ne peux pas sceller un pacte avec toi-même !")
                    return

                if not await bot._has_player_role(target):
                    await bot._send_error_embed(interaction, f"**{target.display_name}** n'a pas le rôle **Joueur**.")
                    return

                # Check requester cooldown (24h)
                can_use, msg = await bot.ability_manager.can_use_ability(
                    interaction.user.id, 'pact', cooldown_days=1
                )
                if not can_use:
                    await bot._send_cd_msg_embed(interaction, f"Pacte en cooldown. {msg}")
                    return

                # Check target cooldown (24h)
                can_target, _ = await bot.ability_manager.can_use_ability(
                    target.id, 'pact', cooldown_days=1
                )
                if not can_target:
                    await bot._send_error_embed(
                        interaction,
                        f"**{target.display_name}** a déjà scellé un pacte récemment et ne peut pas en former un nouveau."
                    )
                    return

                # Check requester has no pending or active pact
                if interaction.user.id in bot.pending_pacts:
                    await bot._send_error_embed(interaction, "Tu as déjà une proposition de pacte en attente !")
                    return

                existing_partner_id = await bot.pact_manager.get_active_pact_partner(interaction.user.id)
                if existing_partner_id:
                    existing = interaction.guild.get_member(existing_partner_id)
                    name = existing.display_name if existing else f"#{existing_partner_id}"
                    await bot._send_error_embed(
                        interaction,
                        f"Tu es déjà lié par un Pacte de Sang avec **{name}** !"
                    )
                    return

                # Check target has no pending or active pact
                if target.id in bot.pending_pacts:
                    await bot._send_error_embed(
                        interaction,
                        f"**{target.display_name}** a déjà une proposition de pacte en attente !"
                    )
                    return

                target_partner_id = await bot.pact_manager.get_active_pact_partner(target.id)
                if target_partner_id:
                    other = interaction.guild.get_member(target_partner_id)
                    name = other.display_name if other else f"#{target_partner_id}"
                    await bot._send_error_embed(
                        interaction,
                        f"**{target.display_name}** a déjà scellé un pacte avec **{name}** !"
                    )
                    return

                clan_info = bot.get_clan_info_for_user(character.get_level())
                prompt_embed = discord.Embed(
                    title="🩸 Pacte de Sang",
                    description=(
                        f"**{interaction.user.display_name}** te propose un **Pacte de Sang** !\n\n"
                        f"Pendant 24h, vous partagerez bonus et malus.\n"
                        f"Chaque level up réussi vous accordera un niveau à tous les deux.\n\n"
                        f"Tu as **1 heure** pour accepter ou refuser."
                    ),
                    color=clan_info['color']
                )

                view = PactView(
                    bot=bot,
                    requester=interaction.user,
                    target=target,
                    timeout=3600
                )

                try:
                    pact_msg = await target.send(embed=prompt_embed, view=view)
                    view.message = pact_msg
                    bot.pending_pacts.add(interaction.user.id)
                    bot.pending_pacts.add(target.id)
                    await interaction.response.send_message(
                        f"Proposition de pacte envoyée à **{target.display_name}** en message privé !",
                        ephemeral=True
                    )
                except discord.Forbidden:
                    await bot._send_error_embed(
                        interaction,
                        f"Impossible d'envoyer un message privé à **{target.display_name}**. Leurs DMs sont peut-être fermés."
                    )

            except Exception as e:
                print(f"Error in pact command: {e}", file=sys.stderr)
                await bot._send_error_embed(interaction, "Une erreur est survenue.")


        # ===== SHIELD (Level 50+) =====
        @bot.tree.command(name="shield", description="Activer un bouclier mystique qui absorbe le prochain malus reçu (24h)")
        async def shield(interaction: discord.Interaction):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Tu dois avoir le rôle **Joueur**.")
                return

            try:
                character = await bot.get_or_create_character(interaction.user.id)

                if character.get_level() < 50:
                    await bot._send_error_embed(
                        interaction,
                        "Tu dois être niveau 50 minimum pour utiliser cette capacité."
                    )
                    return

                # Check cooldown (7 days)
                can_use, msg = await bot.ability_manager.can_use_ability(
                    interaction.user.id, 'shield', cooldown_days=7
                )
                if not can_use:
                    await bot._send_cd_msg_embed(interaction, f"Capacité en cooldown. {msg}")
                    return

                shield_until = datetime.now() + timedelta(hours=24)

                # Check if already has active shield
                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(
                            'SELECT shield_until FROM egb_character_bonuses WHERE discord_id = %s',
                            (interaction.user.id,)
                        )
                        existing = await cursor.fetchone()

                already_shielded = existing and existing.get('shield_until') and existing['shield_until'] > datetime.now()

                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            '''INSERT INTO egb_character_bonuses (discord_id, shield_until)
                               VALUES (%s, %s)
                               ON DUPLICATE KEY UPDATE shield_until = %s''',
                            (interaction.user.id, shield_until, shield_until)
                        )
                        await conn.commit()

                await bot.ability_manager.use_ability(interaction.user.id, 'shield')

                clan_info = bot.get_clan_info_for_user(character.get_level())
                if already_shielded:
                    desc = f"Tu avais déjà un bouclier actif. Sa durée a été rafraîchie jusqu'au **{shield_until.strftime('%d/%m/%Y à %H:%M')}**."
                else:
                    desc = (
                        f"Tu es protégé par un bouclier mystique jusqu'au **{shield_until.strftime('%d/%m/%Y à %H:%M')}** !\n"
                        f"Le prochain malus que tu reçois (malédiction, siphonage, condamnation) sera absorbé."
                    )

                embed = discord.Embed(
                    title="🛡️ Bouclier Mystique !",
                    description=desc,
                    color=clan_info['color']
                )

                # Mirror to pact partner
                partner_id = await bot.pact_manager.get_active_pact_partner(interaction.user.id)
                if partner_id:
                    async with bot.mdb_con.acquire() as conn:
                        async with conn.cursor(aiomysql.DictCursor) as cursor:
                            await cursor.execute(
                                'SELECT shield_until FROM egb_character_bonuses WHERE discord_id = %s',
                                (partner_id,)
                            )
                            partner_existing = await cursor.fetchone()

                    partner_already_shielded = (
                        partner_existing
                        and partner_existing.get('shield_until')
                        and partner_existing['shield_until'] > datetime.now()
                    )

                    async with bot.mdb_con.acquire() as conn:
                        async with conn.cursor() as cursor:
                            await cursor.execute(
                                '''INSERT INTO egb_character_bonuses (discord_id, shield_until)
                                   VALUES (%s, %s)
                                   ON DUPLICATE KEY UPDATE shield_until = %s''',
                                (partner_id, shield_until, shield_until)
                            )
                            await conn.commit()

                    try:
                        partner_user = await bot.fetch_user(partner_id)
                        if partner_already_shielded:
                            partner_dm = discord.Embed(
                                title="🛡️ Bouclier Rafraîchi !",
                                description=f"Ton pacte avec **{interaction.user.display_name}** a rafraîchi ton bouclier jusqu'au **{shield_until.strftime('%d/%m/%Y à %H:%M')}** !",
                                color=discord.Color.blue()
                            )
                        else:
                            partner_dm = discord.Embed(
                                title="🛡️ Pacte de Sang — Bouclier Transmis !",
                                description=f"Ton pacte avec **{interaction.user.display_name}** t'a transmis un bouclier mystique !\nTu es protégé jusqu'au **{shield_until.strftime('%d/%m/%Y à %H:%M')}**.",
                                color=discord.Color.blue()
                            )
                        await partner_user.send(embed=partner_dm)
                    except Exception:
                        pass

                    partner_member = interaction.guild.get_member(partner_id)
                    partner_name = partner_member.display_name if partner_member else f"#{partner_id}"
                    partner_note = "rafraîchi" if partner_already_shielded else "transmis"
                    embed.add_field(
                        name="🩸 Pacte de Sang",
                        value=f"Ton bouclier a été {partner_note} à **{partner_name}** via le pacte.",
                        inline=False
                    )

                await interaction.response.send_message(embed=embed, ephemeral=True)
                await bot.log(interaction.user.id, datetime.now(), f'shield (until {shield_until})')

            except Exception as e:
                print(f"Error in shield command: {e}", file=sys.stderr)
                await bot._send_error_embed(interaction, "Une erreur est survenue.")

        # ===== RULES (Accessible à tous) =====
        RULES_PAGES = [
            discord.Embed(
                title="📜 Règles & Commandes — EldergodBot",
                description=(
                    "Bienvenue dans le système RPG Legacy of Kain !\n\n"
                    "**Prérequis :** Tu dois posséder le rôle **Joueur** pour participer.\n\n"
                    "**Progression**\n"
                    "• Utilise `/levelup` pour tenter de monter de niveau.\n"
                    "• Chaque tentative a une chance de base de **20%**, qui augmente de **+5%** par heure d'attente (max **80%**).\n"
                    "• Tu ne peux tenter qu'**une fois par heure**, et réussir qu'**une fois par jour**.\n"
                    "• En montant de niveau tu changes de clan et débloques de nouvelles capacités.\n\n"
                    "**Clans & niveaux**\n"
                    "```\n"
                    "Niv 1–4   → Fledgling  (Humain)\n"
                    "Niv 5–9   → Melchahim  (Mangeur de Peau)\n"
                    "Niv 10–14 → Zephonim   (Grimpeur)\n"
                    "Niv 15–19 → Dumahim    (Croisé)\n"
                    "Niv 20–24 → Rahabim    (Noyé)\n"
                    "Niv 25–29 → Turelim    (Loyal)\n"
                    "Niv 30–39 → Razielim   (Banni) 🪶\n"
                    "Niv 40+   → Elder      (Ancien)\n"
                    "```"
                ),
                color=discord.Color.dark_red()
            ),
            discord.Embed(
                title="🧛 Niveau 1 — Fledgling (Humain)",
                color=discord.Color.dark_grey()
            ),
            discord.Embed(
                title="🩸 Niveau 5 — Melchahim (Mangeur de Peau)",
                color=discord.Color(0x8B4513)
            ),
            discord.Embed(
                title="🕷️ Niveau 10 — Zephonim (Grimpeur)",
                color=discord.Color(0x228B22)
            ),
            discord.Embed(
                title="⚔️ Niveau 15 — Dumahim (Croisé)",
                color=discord.Color(0xFFD700)
            ),
            discord.Embed(
                title="🌊 Niveau 20 — Rahabim (Noyé)",
                color=discord.Color(0x4169E1)
            ),
            discord.Embed(
                title="🪶 Niveau 30 — Razielim (Banni)",
                color=discord.Color(0x9370DB)
            ),
            discord.Embed(
                title="👑 Niveau 40 — Elder (Ancien)",
                color=discord.Color(0xB8860B)
            ),
            discord.Embed(
                title="🛡️ Niveau 50 — Elder (Ancien) — suite",
                color=discord.Color(0xB8860B)
            ),
        ]

        RULES_PAGES[1].add_field(name="/levelup", inline=False, value=(
            "Tente de monter de niveau.\n"
            "• Chance de base : **20%** (+5%/heure d'attente, max 80%)\n"
            "• Cooldown : **1h** entre chaque tentative\n"
            "• Limite : **1 succès par jour**\n"
            "• Les bonus/malus actifs s'appliquent au moment du jet\n"
            "• En cas de succès, le partenaire de pacte gagne également un niveau"
        ))
        RULES_PAGES[1].add_field(name="/stats", inline=False, value=(
            "Affiche ton profil privé.\n"
            "• Niveau, clan, rôle\n"
            "• Cooldowns de toutes tes capacités\n"
            "• Tous les effets actifs (bless, curse, devour, steal, oppression, bouclier, nage)\n"
            "• Chance de succès actuelle au prochain `/levelup`"
        ))
        RULES_PAGES[1].add_field(name="/profile [@joueur]", inline=False, value=(
            "Affiche le profil **public** d'un joueur (ou le tien si aucun joueur mentionné).\n"
            "• Niveau et clan visibles par tous\n"
            "• Sans les détails privés (effets actifs, cooldowns)"
        ))
        RULES_PAGES[1].add_field(name="/bless @joueur", inline=False, value=(
            "Bénit un joueur pour lui donner un bonus sur son prochain `/levelup`.\n"
            "• Bonus : **+3 à +8%** (aléatoire, cumulatif)\n"
            "• Cooldown : **7 jours** par lanceur\n"
            "• Le joueur ciblé reçoit un DM\n"
            "• Si la cible a un pacte, son partenaire reçoit le même bonus\n"
            "• Impossible de se bénir soi-même"
        ))
        RULES_PAGES[1].add_field(name="/quote [personnage]", inline=False, value=(
            "Affiche une citation aléatoire de l'univers Legacy of Kain.\n"
            "• Autocomplétion sur le nom du personnage\n"
            "• Paramètre optionnel `lang` : `fr` ou `en`\n"
            "• Accessible à tous, sans cooldown"
        ))

        RULES_PAGES[2].add_field(name="/devour", inline=False, value=(
            "Dévore une âme pour obtenir un bonus sur ton prochain `/levelup`.\n"
            "• Bonus : **+3 à +8%** (cumulatif)\n"
            "• Cooldown : **1 jour**\n"
            "• Si tu as un pacte, ton partenaire reçoit le même bonus automatiquement"
        ))
        RULES_PAGES[2].add_field(name="/chaussette", inline=False, value=(
            "Crie CHAUSSETTE pour obtenir un **level up gratuit garanti**.\n"
            "• Aucun jet de dés — le niveau est accordé directement\n"
            "• Cooldown : **7 jours**\n"
            "• Efface tous tes bonus/malus actifs après utilisation\n"
            "• Si tu as un pacte, ton partenaire gagne également un niveau"
        ))

        RULES_PAGES[3].add_field(name="/curse @joueur", inline=False, value=(
            "Maudit un joueur pour réduire ses chances au prochain `/levelup`.\n"
            "• Malus : **-5%** (cumulatif)\n"
            "• Cooldown : **7 jours** par lanceur\n"
            "• Le joueur ciblé reçoit un DM\n"
            "• Si la cible a un pacte, son partenaire subit également la malédiction\n"
            "• Bloqué par le **bouclier** de la cible\n"
            "• Impossible de se maudire soi-même"
        ))
        RULES_PAGES[3].add_field(name="/entomb", inline=False, value=(
            "Condamne le joueur avec le niveau le plus élevé (le leader).\n"
            "• Durée : **1 ou 2 jours** (aléatoire) — le leader ne peut pas faire `/levelup`\n"
            "• Cooldown : **7 jours GLOBAL** (partagé par tout le serveur)\n"
            "• Le leader et son partenaire de pacte reçoivent un DM\n"
            "• Si le leader a un pacte, son partenaire est également condamné\n"
            "• Bloqué par le **bouclier** du leader\n"
            "• Impossible si une condamnation est déjà active ou si tu es le leader"
        ))

        RULES_PAGES[4].add_field(name="(aucune nouvelle capacité)", inline=False, value=(
            "Le clan Dumahim ne débloque pas de nouvelles commandes.\n"
            "Tu conserves toutes les capacités acquises et continues ta progression vers le clan Rahabim."
        ))

        RULES_PAGES[5].add_field(name="/swim", inline=False, value=(
            "Contourne le cooldown quotidien de `/levelup` une fois.\n"
            "• Permet de tenter un level up même si tu as déjà réussi aujourd'hui\n"
            "• Ne contourne pas le cooldown d'1 heure entre tentatives\n"
            "• Cooldown : **7 jours**\n"
            "• Si tu as un pacte, ton partenaire reçoit également le bonus de nage"
        ))
        RULES_PAGES[5].add_field(name="/pact @joueur", inline=False, value=(
            "Scelle un **Pacte de Sang** avec un autre joueur pendant 24h.\n"
            "• Le joueur ciblé reçoit une demande en DM avec **1 heure** pour accepter ou refuser\n"
            "• Effets du pacte :\n"
            "  — Tous les effets (bless, curse, devour, swim, steal, entomb, shield) sont **mirrorés** au partenaire\n"
            "  — Chaque `/levelup` réussi donne **un niveau gratuit** au partenaire\n"
            "• Cooldown : **24h** par joueur\n"
            "• Un seul pacte actif à la fois — les deux joueurs doivent être niveau 20+\n"
            "• Impossible de se pacifier soi-même"
        ))

        RULES_PAGES[6].add_field(name="/evolve", inline=False, value=(
            "Obtiens le rôle cosmétique **Ailes** de Raziel.\n"
            "• Rôle décoratif uniquement, aucun effet en jeu\n"
            "• Utilisable une seule fois — pas de cooldown"
        ))
        RULES_PAGES[6].add_field(name="/spectral", inline=False, value=(
            "Révèle le **Royaume Spectral** : classement des 10 joueurs les plus puissants.\n"
            "• Affiche : niveau, clan, dernière tentative, chance de succès actuelle\n"
            "• Informations normalement cachées — pas de cooldown"
        ))

        RULES_PAGES[7].add_field(name="/steal @joueur", inline=False, value=(
            "Siphonne une partie de la chance d'un joueur pour te l'approprier.\n"
            "• Montant : **5 à 10%** (aléatoire)\n"
            "• La cible perd ce % sur son prochain levelup, tu le gagnes sur le tien\n"
            "• Cooldown : **24h** par lanceur\n"
            "• La cible reçoit un DM\n"
            "• Si tu as un pacte, ton partenaire reçoit également le bonus de vol\n"
            "• Si la cible a un pacte, son partenaire subit également le malus\n"
            "• Bloqué par le **bouclier** de la cible\n"
            "• Impossible de se voler soi-même"
        ))
        RULES_PAGES[7].add_field(name="/oppress  ⚠️ Leader uniquement", inline=False, value=(
            "Inflige un malus massif à **tous les autres joueurs** jusqu'à minuit.\n"
            "• Malus : **-20 à -50%** (aléatoire, appliqué à tous sauf le leader)\n"
            "• Cooldown : **7 jours GLOBAL**\n"
            "• Réservé au joueur avec le niveau le plus élevé\n"
            "• Non bloqué par le bouclier"
        ))

        RULES_PAGES[8].add_field(name="/shield", inline=False, value=(
            "Active un **bouclier mystique** qui absorbe le prochain malus reçu.\n"
            "• Durée : **24h** (ou jusqu'à absorption d'un malus)\n"
            "• Protège contre : `/curse`, `/steal` (malus), `/entomb`\n"
            "• Ne protège **pas** contre `/oppress`\n"
            "• Cooldown : **7 jours** par lanceur\n"
            "• Si tu as un pacte, ton partenaire reçoit également un bouclier\n"
            "• Si le partenaire a déjà un bouclier, sa durée est **rafraîchie**\n"
            "• Attaquant notifié que l'attaque a été absorbée"
        ))
        RULES_PAGES[8].add_field(name="📌 Rappel général", inline=False, value=(
            "• Toutes les réponses du bot sont **privées** sauf `/profile` et `/entomb`\n"
            "• Les effets (bless, curse, devour, steal) sont **effacés après chaque `/levelup`**\n"
            "• `/stats` affiche tous tes effets actifs et leurs sources\n"
            "• En cas de problème, contacte un administrateur"
        ))

        for i, page in enumerate(RULES_PAGES):
            page.set_footer(text=f"Page {i + 1}/{len(RULES_PAGES)}")

        @bot.tree.command(name="rules", description="Afficher les règles et commandes du bot")
        async def rules(interaction: discord.Interaction):
            try:
                view = RulesView(pages=RULES_PAGES, author_id=interaction.user.id)
                await interaction.response.send_message(embed=RULES_PAGES[0], view=view, ephemeral=True)
            except Exception as e:
                print(f"Error in rules command: {e}", file=sys.stderr)
                await interaction.response.send_message("Une erreur est survenue.", ephemeral=True)


class RulesView(discord.ui.View):
    """Previous/Next pagination buttons for /rules (ephemeral — each user gets their own instance)."""

    def __init__(self, pages: list, author_id: int):
        super().__init__(timeout=300)
        self.pages = pages
        self.author_id = author_id
        self.current = 0
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.current == 0
        self.next_button.disabled = self.current == len(self.pages) - 1

    @discord.ui.button(label="◀ Précédent", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Suivant ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)


class PactView(discord.ui.View):
    """Ephemeral accept/decline buttons sent to the public channel."""

    def __init__(self, bot, requester: discord.Member, target: discord.Member, timeout: int):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.requester = requester
        self.target = target
        self.message = None  # set after send so we can edit it on timeout

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "Seul le joueur ciblé peut répondre à cette proposition.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.success, emoji="🩸")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        try:
            expires_at = await self.bot.pact_manager.create_pact(self.requester.id, self.target.id)
            await self.bot.ability_manager.use_ability(self.requester.id, 'pact')
            await self.bot.ability_manager.use_ability(self.target.id, 'pact')

            req_clan = self.bot.get_clan_info_for_user(
                (await self.bot.get_or_create_character(self.requester.id)).get_level()
            )
            embed = discord.Embed(
                title="🩸 Pacte de Sang Scellé !",
                description=(
                    f"**{self.requester.display_name}** et **{self.target.display_name}** "
                    f"sont désormais liés par le sang !\n\n"
                    f"Le pacte expire le **{expires_at.strftime('%d/%m/%Y à %H:%M')}**."
                ),
                color=req_clan['color']
            )
            self.bot.pending_pacts.discard(self.requester.id)
            self.bot.pending_pacts.discard(self.target.id)
            await interaction.response.edit_message(embed=embed, view=None)
            try:
                await self.requester.send(embed=embed)
            except Exception:
                pass
            await self.bot.log(self.target.id, datetime.now(), f'pact accepted with {self.requester.id}')
        except Exception as e:
            print(f"Error accepting pact: {e}", file=sys.stderr)
            await interaction.response.edit_message(content="Une erreur est survenue.", embed=None, view=None)

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger, emoji="💀")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        self.bot.pending_pacts.discard(self.requester.id)
        self.bot.pending_pacts.discard(self.target.id)
        embed = discord.Embed(
            title="💀 Pacte Refusé",
            description=f"**{self.target.display_name}** a refusé ton Pacte de Sang.",
            color=discord.Color.dark_grey()
        )
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="💀 Pacte Refusé",
                description=f"Tu as refusé le Pacte de Sang de **{self.requester.display_name}**.",
                color=discord.Color.dark_grey()
            ),
            view=None
        )
        try:
            await self.requester.send(embed=embed)
        except Exception:
            pass
        await self.bot.log(self.target.id, datetime.now(), f'pact declined from {self.requester.id}')

    async def on_timeout(self):
        self.bot.pending_pacts.discard(self.requester.id)
        self.bot.pending_pacts.discard(self.target.id)
        if self.message:
            try:
                await self.message.edit(
                    embed=discord.Embed(
                        title="⌛ Pacte Expiré",
                        description=f"Tu n'as pas répondu à temps. La proposition de **{self.requester.display_name}** est annulée.",
                        color=discord.Color.dark_grey()
                    ),
                    view=None
                )
            except Exception:
                pass
        try:
            await self.requester.send(
                embed=discord.Embed(
                    title="⌛ Pacte Expiré",
                    description=f"**{self.target.display_name}** n'a pas répondu à temps. Le pacte est annulé.",
                    color=discord.Color.dark_grey()
                )
            )
        except Exception:
            pass