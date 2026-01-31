"""GemGem Discord Bot - Slash Commands"""
import discord
from discord.ext import commands
from discord import app_commands

from tools.search import search_and_format
from tools.time_utils import get_current_time


class CommandsCog(commands.Cog):
    """Slash commands for GemGem."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="search", description="Search the web")
    @app_commands.describe(query="What to search for")
    async def search(self, interaction: discord.Interaction, query: str):
        """Search the web using SearXNG."""
        await interaction.response.defer()
        
        results = await search_and_format(query, num_results=5)
        
        if results:
            embed = discord.Embed(
                title=f"🔍 Search: {query[:100]}",
                description=results[:4000],
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("couldn't find anything for that, try different words?")
    
    @app_commands.command(name="time", description="Get current time")
    @app_commands.describe(timezone="Timezone (e.g., America/New_York)")
    async def time(self, interaction: discord.Interaction, timezone: str = "America/Los_Angeles"):
        """Get current time in specified timezone."""
        time_str = get_current_time(timezone)
        await interaction.response.send_message(f"🕐 {time_str}")
    
    @app_commands.command(name="ping", description="Check if GemGem is alive")
    async def ping(self, interaction: discord.Interaction):
        """Simple ping command."""
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"yep im here lol ({latency}ms)")
    
    @app_commands.command(name="clear", description="Clear conversation history")
    async def clear(self, interaction: discord.Interaction):
        """Clear conversation history for this channel."""
        # Get chat cog and clear history
        chat_cog = self.bot.get_cog("ChatCog")
        if chat_cog and interaction.channel.id in chat_cog.history:
            chat_cog.history[interaction.channel.id] = []
        
        await interaction.response.send_message("cleared my memory of this chat 🧹")


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandsCog(bot))
