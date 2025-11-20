-- ============================================
-- Elder God Bot - Complete Database Setup
-- ============================================

USE your_database_name;

-- Step 1: Create User
-- MANUAL STEP: Replace 'your_password_here' with your desired password
CREATE USER IF NOT EXISTS 'nosgoth_dbuser'@'localhost' IDENTIFIED BY 'your_password_here';

-- Step 2: Grant Privileges on all egb_* tables
GRANT ALL PRIVILEGES ON your_database_name.egb_* TO 'nosgoth_dbuser'@'localhost';
FLUSH PRIVILEGES;

-- ============================================
-- Step 3: Create Tables
-- ============================================

-- Set character set
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- Table: egb_characters
CREATE TABLE IF NOT EXISTS egb_characters (
    discord_id BIGINT PRIMARY KEY,
    level INT DEFAULT 1 NOT NULL,
    last_attempt DATETIME NULL,
    last_successful_levelup DATE NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    INDEX idx_characters_level (level DESC, last_successful_levelup ASC),
    INDEX idx_characters_discord_id (discord_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: egb_log
CREATE TABLE IF NOT EXISTS egb_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    DiscordId BIGINT NOT NULL,
    LogTime DATETIME NOT NULL,
    Action TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    INDEX idx_log_discord_id (DiscordId),
    INDEX idx_log_time (LogTime DESC),
    INDEX idx_log_discord_time (DiscordId, LogTime DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: egb_ability_usage
CREATE TABLE IF NOT EXISTS egb_ability_usage (
    discord_id BIGINT NOT NULL,
    ability_name VARCHAR(50) NOT NULL,
    last_used DATETIME NOT NULL,
    PRIMARY KEY (discord_id, ability_name),
    INDEX idx_ability_usage_discord_id (discord_id),
    INDEX idx_ability_usage_ability (ability_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: egb_character_bonuses
CREATE TABLE IF NOT EXISTS egb_character_bonuses (
    discord_id BIGINT PRIMARY KEY,
    devour_bonus INT DEFAULT 0,
    curse_penalty INT DEFAULT 0,
    guaranteed_levelup BOOLEAN DEFAULT FALSE,
    swim_active BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    INDEX idx_character_bonuses_discord_id (discord_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: egb_dim_characters
CREATE TABLE IF NOT EXISTS egb_dim_characters (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    name_en VARCHAR(255) NOT NULL,
    name_fr VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_dim_characters_name_en (name_en),
    INDEX idx_dim_characters_name_fr (name_fr)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: egb_quotes
CREATE TABLE IF NOT EXISTS egb_quotes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    character_id INT NOT NULL,
    quote_en TEXT NOT NULL,
    quote_fr TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_quotes_character_id (character_id),
    FOREIGN KEY (character_id) REFERENCES egb_dim_characters(Id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- Step 4: Insert Data into egb_dim_characters
-- ============================================

INSERT INTO egb_dim_characters (name_en, name_fr) VALUES
('Kain', 'Kain'),
('Raziel', 'Raziel'),
('ElderGod', 'Ancien'),
('Moebius', 'Moébius'),
('Melchiah', 'Melchiah'),
('Zephon', 'Zephon'),
('Vorador', 'Vorador'),
('Janos Audron', 'Janos Audron'),
('Dumah', 'Dumah'),
('Rahab', 'Rahab'),
('Turel', 'Turel');

-- ============================================
-- Step 5: Insert Data into egb_quotes
-- ============================================

INSERT INTO egb_quotes (character_id, quote_en, quote_fr) VALUES
(2, 'History abhors a paradox', 'L''histoire a horreur des paradoxes'),
(7, 'Call your dogs! They can feast on your corpses!', 'Appelez vos chiens ! Qu''ils viennent se repaître de vos cadavres !'),
(1, 'Vae Victis - suffering to the conquered', 'Vae Victis - malheur aux vaincus'),
(3, 'Raziel... you are worthy', 'Raziel... tu es valeureux')
;

-- ============================================
-- Verify Installation
-- ============================================

-- Show all tables
SHOW TABLES LIKE 'egb_%';

-- Show inserted characters
SELECT * FROM egb_dim_characters;

-- Show inserted quotes with character names
SELECT q.id, c.name_en, c.name_fr, q.quote_en, q.quote_fr 
FROM egb_quotes q 
INNER JOIN egb_dim_characters c ON c.Id = q.character_id;

-- Show grants for nosgoth_dbuser
SHOW GRANTS FOR 'nosgoth_dbuser'@'localhost';