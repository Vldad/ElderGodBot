import os
import discord

class ClanSystem:
    """
    Manages vampire clan progression and abilities
    """
    
    # Clan definitions with level ranges and unlocked abilities
    CLANS = {
        'fledgling': {
            'name_key': 'CLAN_FLEDGLING',
            'level_range': (1, 4),
            'title': 'Novice',
            'color_key': 'COLOR_FLEDGLING',
            'description': 'Un jeune vampire, encore faible et inexpérimenté.',
            'abilities': []
        },
        'melchahim': {
            'name_key': 'CLAN_MELCHAHIM',
            'level_range': (5, 9),
            'title': 'Mangeur de Peau',
            'color_key': 'COLOR_MELCHAHIM',
            'description': 'Membre du clan de Melchiah, les dévoreurs.',
            'abilities': [
                {'level': 5, 'command': '/devour', 'description': 'Dévorer les âmes'},
                {'level': 5, 'command': '/chaussette', 'description': 'Crier CHAUSSETTE pour un level gratuit par semaine'}
            ]
        },
        'zephonim': {
            'name_key': 'CLAN_ZEPHONIM',
            'level_range': (10, 14),
            'title': 'Grimpeur',
            'color_key': 'COLOR_ZEPHONIM',
            'description': 'Membre du clan de Zephon, les grimpeurs de murs.',
            'abilities': [
                {'level': 5, 'command': '/devour', 'description': 'Dévorer les âmes'},
                {'level': 5, 'command': '/chaussette', 'description': 'Crier CHAUSSETTE pour un level gratuit par semaine'},
                {'level': 10, 'command': '/curse', 'description': 'Maudire un autre joueur'}
            ]
        },
        'dumahim': {
            'name_key': 'CLAN_DUMAHIM',
            'level_range': (15, 19),
            'title': 'Croisé',
            'color_key': 'COLOR_DUMAHIM',
            'description': 'Membre du clan de Dumah, les impitoyables.',
            'abilities': [
                {'level': 5, 'command': '/devour', 'description': 'Dévorer les âmes'},
                {'level': 5, 'command': '/chaussette', 'description': 'Crier CHAUSSETTE pour un level gratuit par semaine'},
                {'level': 10, 'command': '/curse', 'description': 'Maudire un autre joueur'},
                {'level': 15, 'command': '/swap', 'description': 'Échanger des niveaux avec un autre joueur'}
            ]
        },
        'rahabim': {
            'name_key': 'CLAN_RAHABIM',
            'level_range': (20, 24),
            'title': 'Noyé',
            'color_key': 'COLOR_RAHABIM',
            'description': 'Membre du clan de Rahab, les habitants des eaux.',
            'abilities': [
                {'level': 5, 'command': '/devour', 'description': 'Dévorer les âmes'},
                {'level': 5, 'command': '/chaussette', 'description': 'Crier CHAUSSETTE pour un level gratuit par semaine'},
                {'level': 10, 'command': '/curse', 'description': 'Maudire un autre joueur'},
                {'level': 15, 'command': '/swap', 'description': 'Échanger des niveaux avec un autre joueur'},
                {'level': 20, 'command': '/swim', 'description': 'Contourner le cooldown une fois par semaine'}
            ]
        },
        'turelim': {
            'name_key': 'CLAN_TURELIM',
            'level_range': (25, 29),
            'title': 'Loyal',
            'color_key': 'COLOR_TURELIM',
            'description': 'Membre du clan de Turel, les bannis.',
            'abilities': [
                {'level': 5, 'command': '/devour', 'description': 'Dévorer les âmes'},
                {'level': 5, 'command': '/chaussette', 'description': 'Crier CHAUSSETTE pour un level gratuit par semaine'},
                {'level': 10, 'command': '/curse', 'description': 'Maudire un autre joueur'},
                {'level': 15, 'command': '/swap', 'description': 'Échanger des niveaux avec un autre joueur'},
                {'level': 20, 'command': '/swim', 'description': 'Contourner le cooldown une fois par semaine'}
            ]
        },

        'razielim': {
            'name_key': 'CLAN_RAZIELIM',
            'level_range': (30, 39),
            'title': 'Banni',
            'color_key': 'COLOR_RAZIELIM',
            'has_wings': True,
            'description': 'Membre du clan de Raziel, les élus.',
            'abilities': [
                {'level': 5, 'command': '/devour', 'description': 'Dévorer les âmes'},
                {'level': 5, 'command': '/chaussette', 'description': 'Crier CHAUSSETTE pour un level gratuit par semaine'},
                {'level': 10, 'command': '/curse', 'description': 'Maudire un autre joueur'},
                {'level': 15, 'command': '/swap', 'description': 'Échanger des niveaux avec un autre joueur'},
                {'level': 20, 'command': '/swim', 'description': 'Contourner le cooldown une fois par semaine'},
                {'level': 30, 'command': '/evolve', 'description': 'Obtenir des ailes (rôle cosmétique)'},
                {'level': 30, 'command': '/spectral', 'description': 'Voir le royaume spectral'}
            ]
        },
        'elder': {
            'name_key': 'CLAN_ELDER',
            'level_range': (40, 999),
            'title': 'Ancien',
            'color_key': 'COLOR_ELDER',
            'description': 'Un vampire ancien, d\'une puissance immense.',
            'abilities': [
                {'level': 5, 'command': '/devour', 'description': 'Dévorer les âmes'},
                {'level': 5, 'command': '/chaussette', 'description': 'Crier CHAUSSETTE pour un level gratuit par semaine'},
                {'level': 10, 'command': '/curse', 'description': 'Maudire un autre joueur'},
                {'level': 15, 'command': '/swap', 'description': 'Échanger des niveaux avec un autre joueur'},
                {'level': 20, 'command': '/swim', 'description': 'Contourner le cooldown une fois par semaine'},
                {'level': 30, 'command': '/evolve', 'description': 'Obtenir des ailes (rôle cosmétique)'},
                {'level': 30, 'command': '/spectral', 'description': 'Voir le royaume spectral'}
            ]
        }
    }
    
    @staticmethod
    def get_clan_by_level(level: int) -> dict:
        """Get clan information based on character level"""
        for clan_key, clan_data in ClanSystem.CLANS.items():
            min_level, max_level = clan_data['level_range']
            if min_level <= level <= max_level:
                # Get role name from env
                role_name = os.getenv(clan_data['name_key'], clan_key.capitalize())
                color_hex = os.getenv(clan_data['color_key'], '#808080')
                
                return {
                    'key': clan_key,
                    'name': role_name,
                    'title': clan_data['title'],
                    'color': discord.Color(int(color_hex.replace('#', ''), 16)),
                    'description': clan_data['description'],
                    'abilities': clan_data['abilities'],
                    'has_wings': clan_data.get('has_wings', False),
                    'level_range': clan_data['level_range']
                }
        
        # Fallback (should never happen)
        return ClanSystem.get_clan_by_level(1)
    
    @staticmethod
    def get_unlocked_abilities(level: int) -> list:
        """Get all abilities unlocked up to this level"""
        clan_info = ClanSystem.get_clan_by_level(level)
        return [ability for ability in clan_info['abilities'] if ability['level'] <= level]
    
    @staticmethod
    def get_next_unlock(level: int) -> dict:
        """Get the next ability to be unlocked"""
        # Find all abilities across all clans
        all_abilities = []
        for clan_data in ClanSystem.CLANS.values():
            for ability in clan_data['abilities']:
                if ability['level'] > level and ability not in all_abilities:
                    all_abilities.append(ability)
        
        if all_abilities:
            # Sort by level and return the first one
            all_abilities.sort(key=lambda x: x['level'])
            return all_abilities[0]
        
        return None
    
    @staticmethod
    def has_clan_changed(old_level: int, new_level: int) -> bool:
        """Check if leveling up changed the clan"""
        old_clan = ClanSystem.get_clan_by_level(old_level)
        new_clan = ClanSystem.get_clan_by_level(new_level)
        return old_clan['key'] != new_clan['key']
    
    @staticmethod
    def get_all_clan_role_names() -> list[str]:
        """Get all clan role names from environment"""
        role_names = []
        for clan_data in ClanSystem.CLANS.values():
            role_name = os.getenv(clan_data['name_key'], clan_data['name_key'])
            role_names.append(role_name)
        return role_names