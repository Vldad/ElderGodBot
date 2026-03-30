import aiomysql
from datetime import datetime, timedelta
from typing import Optional
import sys

class AbilityManager:
    """
    Manages ability cooldowns and usage tracking
    """
    def __init__(self, mdb_pool: aiomysql.Pool):
        self.mdb_pool = mdb_pool

    async def can_use_ability(self, discord_id: int, ability_name: str, cooldown_days: int = 7, short_version: bool = False) -> tuple[bool, Optional[str]]:
        """
        Check if user can use an ability based on cooldown
        Returns: (can_use: bool, message: Optional[str])
        """
        try:
            async with self.mdb_pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    if discord_id == -1:
                        await cursor.execute(
                        'SELECT max(last_used) as last_used FROM egb_ability_usage WHERE ability_name = %s',
                        (ability_name,)
                        )
                    else:
                        await cursor.execute(
                            'SELECT last_used FROM egb_ability_usage WHERE discord_id = %s AND ability_name = %s',
                            (discord_id, ability_name)
                        )
                    result = await cursor.fetchone()

            if not result:
                return True, "Disponible"

            last_used = result['last_used']
            cooldown = timedelta(days=cooldown_days)
            time_since_use = datetime.now() - last_used

            if time_since_use < cooldown:
                remaining = cooldown - time_since_use
                days = remaining.days
                hours = remaining.seconds // 3600

                if days > 0:
                    if short_version:
                        if hours != 0:
                            return False, f"{days} jour(s) et {hours}h"
                        else:
                            mins = remaining.seconds // 60
                            return False, f"{days} jour(s) et {mins} minutes"
                    else:
                        return False, f"Disponible dans {days} jour(s) et {hours}h"
                else:
                    if short_version:
                        if hours != 0:
                            return False, f"{hours}h"
                        else:
                            mins = remaining.seconds // 60
                            return False, f"{mins} minutes"
                    else:
                        if hours != 0:
                            return False, f"Disponible dans {hours}h"
                        else:
                            mins = remaining.seconds // 60
                            return False, f"Disponible dans {mins} minutes"

            return True, "Disponible"

        except Exception as e:
            print(f"Error checking ability cooldown: {e}", file=sys.stderr)
            return True, None

    async def use_ability(self, discord_id: int, ability_name: str) -> bool:
        """
        Mark an ability as used (update last_used timestamp)
        """
        try:
            async with self.mdb_pool.acquire() as conn:
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

