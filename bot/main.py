"""GemGem Discord Bot - Entry Point"""
import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime
import re

from memory.shared_memory import SharedMemoryManager
from tools.admin import whitelist

# Load environment variables
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables")

# Initialize shared memory manager
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
shared_memory = SharedMemoryManager(DATA_DIR)


# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

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


@bot.event
async def on_message(message: discord.Message):
    """
    GemGem Conversation Listener (Cross-bot Context Awareness)

    Records the full GemGem conversation (user's @mention + GemGem's reply)
    to shared_memory.json so Astral has context of what users discuss with GemGem.
    """
    # Don't record our own messages (Chat cog handles that)
    if message.author == bot.user:
        await bot.process_commands(message)
        return

    GEMGEM_BOT_ID = 1458550716225425560

    # === GEMGEM CONVERSATION LISTENER ===

    # GemGem's reply
    if message.author.id == GEMGEM_BOT_ID:
        content = message.content.strip()
        if content:
            shared_memory.append_message(
                role="user",
                content=content,
                username="GemGem"
            )
            print(f"[SharedMemory] Recorded GemGem response: {content[:50]}...")
        await bot.process_commands(message)
        return

    # User's message directed at GemGem (not mentioning Astral)
    if (any(m.id == GEMGEM_BOT_ID for m in message.mentions)
            and not bot.user.mentioned_in(message)
            and whitelist.is_authorized(message.author.id)):
        content = re.sub(rf'<@!?{GEMGEM_BOT_ID}>', '', message.content).strip()
        if content:
            shared_memory.append_message(
                role="user",
                content=content,
                username=message.author.display_name
            )
            print(f"[SharedMemory] Recorded user->GemGem: [{message.author.display_name}] {content[:50]}...")
        await bot.process_commands(message)
        return
    # === END GEMGEM LISTENER ===

    # Process commands normally
    await bot.process_commands(message)


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
