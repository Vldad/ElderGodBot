import discord
import aiomysql
from discord import app_commands
from datetime import datetime
from .clan_system import ClanSystem
import random

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
                await bot._send_error_embed(interaction, "Vous devez avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                # Check level requirement
                if character.get_level() < 5:
                    await bot._send_error_embed(
                        interaction,
                        "Vous devez être niveau 5 minimum pour utiliser cette capacité."
                    )
                    return
                
                # Check cooldown (once per week)
                can_use, msg = await bot.ability_manager.can_use_ability(
                    interaction.user.id, 
                    'chaussette', 
                    cooldown_days=7
                )
                
                if not can_use:
                    await bot._send_error_embed(interaction, f"Capacité en cooldown. {msg}")
                    return

                # Level up !
                character._level += 1
                character._lastSuccessfulLevelup = __import__('datetime').date.today()
                await bot.character_repo.save_character(character)

                # Check for bonuses/penalties
                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor(aiomysql.DictCursor) as cursor:
                        await cursor.execute(
                            'SELECT devour_bonus, curse_penalty, guaranteed_levelup, swim_active FROM egb_character_bonuses WHERE discord_id = %s',
                            (interaction.user.id,)
                        )
                        bonuses = await cursor.fetchone()

                # Clear bonuses after use
                if bonuses:
                    await bot.mdb_con.execute(
                        '''UPDATE egb_character_bonuses 
                           SET devour_bonus = 0, curse_penalty = 0, guaranteed_levelup = FALSE 
                           WHERE discord_id = %s''',
                        interaction.user.id
                    )

                await bot.ability_manager.use_ability(interaction.user.id, 'chaussette')
                
                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="🧦 CHAUSSETTE !",
                    description=f"Vous avez crié CHAUSSETTE et automatiquement gagné **1 niveau** !",
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
                            value=f"Vous êtes devenu **{new_clan['title']}** du clan **{new_clan['name']}** !",
                            inline=False
                        )
                    else:
                        # User is admin/owner, send DM
                        embed.add_field(
                            name="🦇 Évolution !",
                            value=f"Vous êtes devenu **{new_clan['title']}** du clan **{new_clan['name']}** !",
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
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                await bot.log(interaction.user.id, datetime.now(), f'chaussette')
                
            except Exception as e:
                print(f"Error in chaussette command: {e}")
                await bot._send_error_embed(interaction, "Une erreur est survenue.")

        # ===== DEVOUR (Level 5+) =====
        @bot.tree.command(name="devour", description="Dévorer les âmes pour un bonus d'XP")
        async def devour(interaction: discord.Interaction):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Vous devez avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                # Check level requirement
                if character.get_level() < 5:
                    await bot._send_error_embed(
                        interaction,
                        "Vous devez être niveau 5 minimum pour utiliser cette capacité."
                    )
                    return
                
                # Check cooldown (once per day)
                can_use, msg = await bot.ability_manager.can_use_ability(
                    interaction.user.id, 
                    'devour', 
                    cooldown_days=1
                )
                
                if not can_use:
                    await bot._send_error_embed(interaction, f"Capacité en cooldown. {msg}")
                    return
                
                # Devour gives a small bonus to next levelup chance
                bonus = random.randint(3, 8)
                
                # Store bonus in character
                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            '''INSERT INTO egb_character_bonuses (discord_id, devour_bonus)
                               VALUES (%s, %s)
                               ON DUPLICATE KEY UPDATE devour_bonus = devour_bonus + %s''',
                            (character.get_discord_id(), bonus, bonus)
                        )
                
                await bot.ability_manager.use_ability(interaction.user.id, 'devour')
                
                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="🩸 Dévoration d'Âme",
                    description=f"Vous avez dévoré une âme et gagné **+{bonus}%** pour votre prochaine tentative de level up !",
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
                await bot._send_error_embed(interaction, "Vous devez avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                if character.get_level() < 20:
                    await bot._send_error_embed(
                        interaction,
                        "Vous devez être niveau 20 minimum pour utiliser cette capacité."
                    )
                    return
                
                # Check if already leveled up today
                can_attempt, msg = character.can_attempt_levelup()
                if can_attempt:
                    await bot._send_error_embed(
                        interaction,
                        "Vous n'avez pas encore réussi de level up aujourd'hui. Utilisez `/levelup` normalement."
                    )
                    return
                
                # Check weekly cooldown
                can_use, cooldown_msg = await bot.ability_manager.can_use_ability(
                    interaction.user.id,
                    'swim',
                    cooldown_days=7
                )
                
                if not can_use:
                    await bot._send_error_embed(interaction, f"Capacité en cooldown. {cooldown_msg}")
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
                
                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="🌊 Nage dans les Abysses",
                    description="Vous avez contourné les limites ! Votre prochaine tentative ignorera le cooldown horaire et la limite quotidienne.",
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
                await bot._send_error_embed(interaction, "Vous devez avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                if character.get_level() < 10:
                    await bot._send_error_embed(
                        interaction,
                        "Vous devez être niveau 10 minimum pour utiliser cette capacité."
                    )
                    return
                
                # Can't curse yourself
                if target.id == interaction.user.id:
                    await bot._send_error_embed(interaction, "Vous ne pouvez pas vous maudire vous-même !")
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
                    await bot._send_error_embed(interaction, f"Capacité en cooldown. {cooldown_msg}")
                    return
                
                # Apply curse
                curse_amount = -5
                async with bot.mdb_con.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            '''INSERT INTO egb_character_bonuses (discord_id, curse_penalty)
                               VALUES (%s, %s)
                               ON DUPLICATE KEY UPDATE curse_penalty = curse_penalty + %s''',
                            (target.id, curse_amount, curse_amount)
                        )
                
                await bot.ability_manager.use_ability(interaction.user.id, 'curse')
                
                clan_info = bot.get_clan_info_for_user(character.get_level())
                embed = discord.Embed(
                    title="💀 Malédiction",
                    description=f"Vous avez maudit {target.mention} !\n\nIls subiront **-5%** de chance sur leur prochaine tentative de level up.",
                    color=clan_info['color']
                )
                
                # Notify target via DM
                try:
                    target_embed = discord.Embed(
                        title="💀 Malédiction !",
                        description=f"{interaction.user.display_name} vous a maudit avec **curse** !\n\nVotre prochaine tentative de level up aura **-5%** de chance.",
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
        
        # ===== SWAP (Level 15+) =====
        @bot.tree.command(name="swap", description="Échanger des niveaux avec un autre joueur consentant")
        @app_commands.describe(target="Le joueur avec qui échanger")
        async def swap(interaction: discord.Interaction, target: discord.Member):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Vous devez avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                if character.get_level() < 15:
                    await bot._send_error_embed(
                        interaction,
                        "Vous devez être niveau 15 minimum pour utiliser cette capacité."
                    )
                    return
                
                if target.id == interaction.user.id:
                    await bot._send_error_embed(interaction, "Vous ne pouvez pas échanger avec vous-même !")
                    return
                
                if not await bot._has_player_role(target):
                    await bot._send_error_embed(interaction, f"{target.display_name} n'a pas le rôle **Joueur**.")
                    return
                
                target_character = await bot.get_or_create_character(target.id)
                
                clan_info = bot.get_clan_info_for_user(character.get_level())
                
                # Create confirmation view
                class SwapView(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=60)
                        self.value = None
                    
                    @discord.ui.button(label="Accepter", style=discord.ButtonStyle.green)
                    async def accept(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                        if button_interaction.user.id != target.id:
                            await button_interaction.response.send_message(
                                "Seul le joueur ciblé peut accepter !",
                                ephemeral=True
                            )
                            return
                        self.value = True
                        self.stop()
                    
                    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.red)
                    async def decline(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                        if button_interaction.user.id != target.id:
                            await button_interaction.response.send_message(
                                "Seul le joueur ciblé peut refuser !",
                                ephemeral=True
                            )
                            return
                        self.value = False
                        self.stop()
                
                view = SwapView()
                
                embed = discord.Embed(
                    title="🔄 Proposition d'Exil",
                    description=f"{interaction.user.mention} (Niveau **{character.get_level()}**) propose d'échanger son niveau avec {target.mention} (Niveau **{target_character.get_level()}**).\n\n{target.mention}, acceptez-vous ?",
                    color=clan_info['color']
                )
                
                await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
                
                # Wait for response
                await view.wait()
                
                if view.value is None:
                    timeout_embed = discord.Embed(
                        title="⏱️ Temps écoulé",
                        description="La proposition d'échange a expiré.",
                        color=discord.Color.orange()
                    )
                    await interaction.edit_original_response(embed=timeout_embed, view=None)
                    return
                
                if not view.value:
                    declined_embed = discord.Embed(
                        title="❌ Refusé",
                        description=f"{target.mention} a refusé l'échange.",
                        color=discord.Color.red()
                    )
                    await interaction.edit_original_response(embed=declined_embed, view=None)
                    return
                
                # Perform the exchange
                temp_level = character.get_level()
                character._level = target_character.get_level()
                target_character._level = temp_level
                
                await bot.character_repo.save_character(character)
                await bot.character_repo.save_character(target_character)
                
                # Update roles
                new_clan_initiator = bot.get_clan_info_for_user(character.get_level())
                new_clan_target = bot.get_clan_info_for_user(target_character.get_level())
                
                await bot._assign_clan_role(interaction.user, new_clan_initiator)
                await bot._assign_clan_role(target, new_clan_target)
                
                success_embed = discord.Embed(
                    title="✅ Échange Réussi !",
                    description=f"{interaction.user.mention} est maintenant niveau **{character.get_level()}**\n{target.mention} est maintenant niveau **{target_character.get_level()}**",
                    color=discord.Color.green()
                )
                
                await interaction.edit_original_response(embed=success_embed, view=None)
                await bot.log(interaction.user.id, datetime.now(), f'swap with {target.id}')
                await bot.log(target.id, datetime.now(), f'swap with {interaction.user.id}')
                
            except Exception as e:
                print(f"Error in swap command: {e}")
                await bot._send_error_embed(interaction, "Une erreur est survenue.")
                
        # ===== EVOLVE (Level 30+) =====
        @bot.tree.command(name="evolve", description="Obtenir les ailes de Raziel (rôle cosmétique)")
        async def evolve(interaction: discord.Interaction):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Vous devez avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                if character.get_level() < 30:
                    await bot._send_error_embed(
                        interaction,
                        "Vous devez être niveau 30 minimum pour utiliser cette capacité."
                    )
                    return
                
                import os
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
                        "Vous avez déjà les ailes de Raziel !"
                    )
                    return
                
                try:
                    await interaction.user.add_roles(wings_role)
                    
                    clan_info = bot.get_clan_info_for_user(character.get_level())
                    embed = discord.Embed(
                        title="👼 Évolution Céleste",
                        description=f"Vos ailes se déploient majestueusement !\n\nVous avez obtenu le rôle {wings_role.mention} !",
                        color=clan_info['color']
                    )
                    embed.set_image(url="https://i.imgur.com/raziel_wings.gif")  # Replace with actual image if desired
                    
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    await bot.log(interaction.user.id, datetime.now(), 'evolve (obtained wings)')
                    
                except discord.Forbidden:
                    await bot._send_error_embed(
                        interaction,
                        f"Je ne peux pas vous attribuer le rôle. Veuillez vous attribuer manuellement le rôle **{wings_role_name}**."
                    )
                
            except Exception as e:
                print(f"Error in evolve command: {e}")
                await bot._send_error_embed(interaction, "Une erreur est survenue.")
        
        # ===== SPECTRAL (Level 30+) =====
        @bot.tree.command(name="spectral", description="Voir le royaume spectral (classement caché)")
        async def spectral(interaction: discord.Interaction):
            if not await bot._has_player_role(interaction.user):
                await bot._send_error_embed(interaction, "Vous devez avoir le rôle **Joueur**.")
                return
            
            try:
                character = await bot.get_or_create_character(interaction.user.id)
                
                if character.get_level() < 30:
                    await bot._send_error_embed(
                        interaction,
                        "Vous devez être niveau 30 minimum pour utiliser cette capacité."
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
                    description="*Vous percevez les âmes des vampires les plus puissants...*",
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
                        import os
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