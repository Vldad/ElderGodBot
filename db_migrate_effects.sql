-- ============================================================
-- Migration: Introduce egb_character_effects table
-- Replaces bless_bonus/bless_bonus_from and curse_penalty/curse_penalty_from
-- with a unified effects table supporting full per-source attribution.
-- Also prepares the schema for /steal (steal_bonus / steal_malus).
-- ============================================================

USE nosgoth_egb;

-- ============================================================
-- Step 1: Create egb_character_effects
-- ============================================================

CREATE TABLE IF NOT EXISTS egb_character_effects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    discord_id BIGINT NOT NULL,
    source_discord_id BIGINT NOT NULL,   -- -1 = source unknown (legacy migrated data)
    effect_type ENUM('bless', 'curse', 'steal_bonus', 'steal_malus') NOT NULL,
    amount INT NOT NULL,                 -- always positive; sign is implied by effect_type
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_effects_discord_id (discord_id),
    INDEX idx_effects_source (source_discord_id),
    INDEX idx_effects_discord_type (discord_id, effect_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Step 2: Migrate existing bless data
-- ============================================================

-- Known source
INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
SELECT discord_id, bless_bonus_from, 'bless', bless_bonus
FROM egb_character_bonuses
WHERE bless_bonus > 0 AND bless_bonus_from IS NOT NULL;

-- Unknown source (legacy rows where bless_bonus_from was never set)
INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
SELECT discord_id, -1, 'bless', bless_bonus
FROM egb_character_bonuses
WHERE bless_bonus > 0 AND bless_bonus_from IS NULL;

-- ============================================================
-- Step 3: Migrate existing curse data
-- curse_penalty is stored as a negative int (e.g. -5).
-- amount in egb_character_effects is always positive.
-- ============================================================

-- Known source
INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
SELECT discord_id, curse_penalty_from, 'curse', ABS(curse_penalty)
FROM egb_character_bonuses
WHERE curse_penalty < 0 AND curse_penalty_from IS NOT NULL;

-- Unknown source
INSERT INTO egb_character_effects (discord_id, source_discord_id, effect_type, amount)
SELECT discord_id, -1, 'curse', ABS(curse_penalty)
FROM egb_character_bonuses
WHERE curse_penalty < 0 AND curse_penalty_from IS NULL;

-- ============================================================
-- Step 4: Drop obsolete columns from egb_character_bonuses
-- ============================================================

ALTER TABLE egb_character_bonuses
    DROP COLUMN bless_bonus,
    DROP COLUMN bless_bonus_from,
    DROP COLUMN curse_penalty,
    DROP COLUMN curse_penalty_from;

-- ============================================================
-- Verify
-- ============================================================

SELECT 'egb_character_effects rows' AS label, COUNT(*) AS count FROM egb_character_effects;
SELECT 'egb_character_bonuses columns' AS label, COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'egb_character_bonuses'
ORDER BY ORDINAL_POSITION;
