import aiomysql
from datetime import datetime, timedelta
from typing import Optional

class AbilityManager:
    """
    Manages ability cooldowns and usage tracking
    """
    def __init__(self, pg_pool: aiomysql.Pool):
        self.pg_pool = pg_pool

    async def can_use_ability(self, discord_id: int, ability_name: str, cooldown_days: int = 7) -> tuple[bool, Optional[str]]:
        """
        Check if user can use an ability based on cooldown
        Returns: (can_use: bool, message: Optional[str])
        """
        try:
            async with self.pg_pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        'SELECT last_used FROM egb_ability_usage WHERE discord_id = %s AND ability_name = %s',
                        (discord_id, ability_name)
                    )
                    result = await cursor.fetchone()

            if not result:
                return True, None

            last_used = result['last_used']
            cooldown = timedelta(days=cooldown_days)
            time_since_use = datetime.now() - last_used

            if time_since_use < cooldown:
                remaining = cooldown - time_since_use
                days = remaining.days
                hours = remaining.seconds // 3600

                if days > 0:
                    return False, f"Disponible dans {days} jour(s) et {hours}h"
                else:
                    return False, f"Disponible dans {hours}h"

            return True, None

        except Exception as e:
            print(f"Error checking ability cooldown: {e}", file=sys.stderr)
            return True, None

    async def use_ability(self, discord_id: int, ability_name: str) -> bool:
        """
        Mark an ability as used (update last_used timestamp)
        """
        try:
            async with self.pg_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        '''INSERT INTO egb_ability_usage (discord_id, ability_name, last_used)
                           VALUES (%s, %s, %s)
                           ON DUPLICATE KEY UPDATE last_used = %s''',
                        (discord_id, ability_name, datetime.now(), datetime.now())
                    )
            return True
        except Exception as e:
            print(f"Error marking ability as used: {e}", file=sys.stderr)
            return False

    async def get_ability_cooldown_info(self, discord_id: int, ability_name: str) -> Optional[datetime]:
        """
        Get last used timestamp for an ability
        """
        try:
            async with self.pg_pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        'SELECT last_used FROM egb_ability_usage WHERE discord_id = %s AND ability_name = %s',
                        (discord_id, ability_name)
                    )
                    result = await cursor.fetchone()

            return result['last_used'] if result else None
        except Exception as e:
            print(f"Error getting ability cooldown info: {e}", file=sys.stderr)
            return None