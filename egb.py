import os
import discord
from dotenv import load_dotenv
from eldergod import ElderGod

def main():
    """
    Main entry point for the Discord bot
    """
    # Load environment variables
    load_dotenv()
    
    # Validate required environment variables
    required_vars = [
        'DISCORD_TOKEN',
        'DB_MDB',
        'DB_MDB_USER',
        'DB_MDB_USER_PWD',
        'TEST_CHANNEL_ID',
        'DEFAULT_LANGUAGE',
        'GUILD_ID'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"ERROR: Missing required environment variables: {', '.join(missing_vars)}")
        return
    
    # Setup intents
    intents = discord.Intents.default()
    intents.message_content = True  # For reading messages
    intents.members = True          # For member join events
    
    # Create and run bot
    bot = ElderGod(command_prefix='/', intents=intents)
    
    try:
        bot.run(os.getenv('DISCORD_TOKEN'))
    except discord.LoginFailure:
        print("ERROR: Invalid Discord token")
    except Exception as e:
        print(f"ERROR: Bot crashed - {e}")

if __name__ == "__main__":
    main()