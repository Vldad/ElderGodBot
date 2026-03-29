import aiomysql
from typing import Optional
import sys


class PactManager:
    """
    Manages blood pact state between players.
    A pact links two players for 24h: effects (bless, curse, steal, devour, swim)
    are mirrored to the partner at creation time, and any successful levelup
    propagates a free level to the partner.
    """

    def __init__(self, pool: aiomysql.Pool):
        self.pool = pool

    async def get_active_pact_partner(self, discord_id: int) -> Optional[int]:
        """
        Returns the partner's discord_id if this player is in an active pact, else None.
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        '''SELECT requester_id, target_id FROM egb_pacts
                           WHERE status = 'active' AND expires_at > NOW()
                           AND (requester_id = %s OR target_id = %s)
                           LIMIT 1''',
                        (discord_id, discord_id)
                    )
                    row = await cursor.fetchone()

            if not row:
                return None
            return row['target_id'] if row['requester_id'] == discord_id else row['requester_id']
        except Exception as e:
            print(f"Error getting pact partner for {discord_id}: {e}", file=sys.stderr)
            return None

    async def create_pact(self, requester_id: int, target_id: int) -> 'datetime':
        """
        Insert an active pact into egb_pacts. Returns the expiry datetime.
        Cooldown recording (egb_ability_usage) is handled by the caller via AbilityManager.
        """
        from datetime import datetime, timedelta
        expires_at = datetime.now() + timedelta(hours=24)
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    '''INSERT INTO egb_pacts (requester_id, target_id, status, accepted_at, expires_at)
                       VALUES (%s, %s, 'active', NOW(), %s)''',
                    (requester_id, target_id, expires_at)
                )
                await conn.commit()
        return expires_at
