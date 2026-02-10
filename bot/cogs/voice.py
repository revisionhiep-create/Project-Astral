"""
Voice Commands Cog for Astra
Provides /join, /leave commands for voice channel control
"""

import discord
from discord import app_commands
from discord.ext import commands
from tools.voice_handler import get_voice_handler


class VoiceCommands(commands.Cog):
    """Voice channel commands"""

    def __init__(self, bot):
        self.bot = bot
        self.voice_handler = get_voice_handler(bot)

    @app_commands.command(name="join", description="Astra joins your voice channel")
    async def join_voice(self, interaction: discord.Interaction):
        """Join the user's voice channel"""

        # Check if user is in a voice channel
        if not interaction.user.voice:
            await interaction.response.send_message(
                "❌ You need to be in a voice channel first! Join one and try again.",
                ephemeral=True,
            )
            return

        voice_channel = interaction.user.voice.channel

        # Defer the response since connection might take a moment
        await interaction.response.defer()

        # Join voice channel
        voice_client = await self.voice_handler.join_voice_channel(voice_channel)

        if voice_client:
            await interaction.followup.send(
                f"🎤 Joined **{voice_channel.name}**! I'll speak my responses here now! ✨"
            )

            # Greet in voice
            await self.voice_handler.speak_text(
                interaction.guild, "Hey! I'm here, let's chat!"
            )
        else:
            await interaction.followup.send(
                "❌ Couldn't join the voice channel. Something went wrong!",
                ephemeral=True,
            )

    @app_commands.command(name="leave", description="Astra leaves the voice channel")
    async def leave_voice(self, interaction: discord.Interaction):
        """Leave the current voice channel"""

        if not self.voice_handler.is_in_voice(interaction.guild):
            await interaction.response.send_message(
                "❌ I'm not in a voice channel!", ephemeral=True
            )
            return

        # Say goodbye in voice first
        if (
            interaction.guild.voice_client
            and interaction.guild.voice_client.is_connected()
        ):
            await self.voice_handler.speak_text(
                interaction.guild, "Alright, catch you later! Bye!"
            )
            # Wait for goodbye to finish
            import asyncio
            await asyncio.sleep(2)

        await self.voice_handler.leave_voice_channel(interaction.guild)

        await interaction.response.send_message(
            "👋 Left the voice channel! Call me back with `/join` anytime!"
        )


async def setup(bot):
    """Setup function for loading the cog"""
    await bot.add_cog(VoiceCommands(bot))
