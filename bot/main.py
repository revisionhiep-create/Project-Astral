"""GemGem Discord Bot - Entry Point"""
import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables")


# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    description="Astra - your friend in the chat"
)


@bot.event
async def on_ready():
    """Called when bot is ready."""
    print(f"✨ Astra is online as {bot.user}")
    print(f"📡 Connected to {len(bot.guilds)} servers")
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"⚡ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
    
    # Check search system
    searxng_url = os.getenv("SEARXNG_URL", "http://searxng:8080")
    print(f"🔍 Search system: {searxng_url}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Called when bot joins a new server."""
    print(f"🎉 Joined new server: {guild.name} (id: {guild.id})")


async def load_cogs():
    """Load all cogs."""
    cog_files = ["cogs.admin", "cogs.chat", "cogs.draw", "cogs.voice"]
    
    for cog in cog_files:
        try:
            await bot.load_extension(cog)
            print(f"✅ Loaded {cog}")
        except Exception as e:
            print(f"❌ Failed to load {cog}: {e}")


async def main():
    """Main entry point."""
    async with bot:
        await load_cogs()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
