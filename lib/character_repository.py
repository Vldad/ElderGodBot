import aiomysql
from typing import Optional
from datetime import date
from .character import Character

class CharacterRepository:
    """
    Repository pattern for Character database operations
    Handles all SQL queries related to characters
    """
    def __init__(self, pg_pool: aiomysql.Pool):
        self.pg_pool = pg_pool
    
    async def get_character(self, discord_id: int) -> Optional[Character]:
        """
        Load character from database by Discord ID
        Returns None if character doesn't exist
        """
        try:
            async with self.pg_pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        '''SELECT discord_id, level, last_attempt, last_successful_levelup 
                           FROM egb_characters 
                           WHERE discord_id = %s''',
                        (discord_id,)
                    )
                    data = await cursor.fetchone()
            
            if data:
                return Character(
                    discord_id=data['discord_id'],
                    level=data['level'],
                    last_attempt=data['last_attempt'],
                    last_successful_levelup=data['last_successful_levelup']
                )
            return None
        except Exception as e:
            print(f"Error loading character {discord_id}: {e}")
            return None
    
    async def create_character(self, discord_id: int) -> Character:
        """
        Create a new character in the database
        """
        try:
            async with self.pg_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        '''INSERT INTO egb_characters (discord_id, level, last_attempt, last_successful_levelup)
                           VALUES (%s, 1, NULL, NULL)''',
                        (discord_id,)
                    )
            return Character(discord_id=discord_id)
        except Exception as e:
            print(f"Error creating character {discord_id}: {e}")
            raise
    
    async def save_character(self, character: Character) -> bool:
        """
        Save character state to database
        Uses INSERT ... ON DUPLICATE KEY UPDATE for upsert
        """
        try:
            async with self.pg_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        '''INSERT INTO egb_characters (discord_id, level, last_attempt, last_successful_levelup)
                           VALUES (%s, %s, %s, %s)
                           ON DUPLICATE KEY UPDATE
                               level = %s,
                               last_attempt = %s,
                               last_successful_levelup = %s''',
                        (character.get_discord_id(),
                         character.get_level(),
                         character.get_last_attempt(),
                         character.get_last_successful_levelup(),
                         character.get_level(),
                         character.get_last_attempt(),
                         character.get_last_successful_levelup())
                    )
            return True
        except Exception as e:
            print(f"Error saving character {character.get_discord_id()}: {e}")
            return False
    
    async def get_top_characters(self, limit: int = 10) -> list[Character]:
        """
        Get top characters by level for leaderboard
        """
        try:
            async with self.pg_pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        '''SELECT discord_id, level, last_attempt, last_successful_levelup
                           FROM egb_characters
                           ORDER BY level DESC, last_successful_levelup ASC
                           LIMIT %s''',
                        (limit,)
                    )
                    rows = await cursor.fetchall()
            
            return [
                Character(
                    discord_id=row['discord_id'],
                    level=row['level'],
                    last_attempt=row['last_attempt'],
                    last_successful_levelup=row['last_successful_levelup']
                )
                for row in rows
            ]
        except Exception as e:
            print(f"Error getting top characters: {e}")
            return []
    
    async def character_exists(self, discord_id: int) -> bool:
        """
        Check if character exists in database
        """
        try:
            async with self.pg_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        'SELECT COUNT(1) FROM egb_characters WHERE discord_id = %s',
                        (discord_id,)
                    )
                    result = await cursor.fetchone()
                    return result[0] > 0
        except Exception as e:
            print(f"Error checking character existence {discord_id}: {e}")
            return False
