"""
Voice Commands Cog for Astra
Provides /join, /leave, /listen commands for voice channel control and STT
"""

import re
import discord
from discord import app_commands
from discord.ext import commands
from tools.voice_handler import get_voice_handler
from tools import stt


class VoiceMessage:
    """
    Fake message wrapper so voice utterances can be processed
    through the same on_message pipeline as text messages.
    """

    def __init__(self, user: discord.User, content: str, guild: discord.Guild, text_channel: discord.TextChannel, bot_user):
        self.author = user
        self.content = f"<@{bot_user.id}> {content}"  # Prepend mention so on_message picks it up
        self.guild = guild
        self.channel = text_channel
        self.attachments = []
        self.mentions = [bot_user]  # Simulate bot being mentioned
        self.id = None
        self.created_at = discord.utils.utcnow()


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
            # Auto-start listening
            listening_started = self.voice_handler.start_listening(
                interaction.guild, self._on_utterance
            )

            if listening_started:
                await interaction.followup.send(
                    f"🎤 Joined **{voice_channel.name}** and started listening! 🎧 I'm all ears! ✨"
                )
            else:
                await interaction.followup.send(
                    f"🎤 Joined **{voice_channel.name}**! (Note: Listening couldn't be auto-started, try `/listen` manually)"
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

        # Stop listening if active
        if self.voice_handler.is_listening(interaction.guild):
            self.voice_handler.stop_listening(interaction.guild)

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



    async def _on_utterance(self, user: discord.User, wav_bytes: bytes, guild: discord.Guild):
        """
        Called when a complete utterance is detected from a user.
        Transcribes via local whisper (or cloud fallback), then feeds into Astra's chat pipeline.
        """
        try:
            # Transcribe
            text = await stt.transcribe(wav_bytes)
            if not text:
                return

            # Reject too-short transcripts (fragments from VAD splits)
            if len(text.split()) < 3:
                print(f"🔇 [Voice] Dropping short fragment: \"{text}\"")
                return

            # Find a text channel to send the response (use first text channel)
            text_channel = None
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    text_channel = channel
                    break

            if not text_channel:
                print("❌ [Voice] No text channel found for voice response")
                return

            # Create a fake message and dispatch it through the bot's on_message
            voice_msg = VoiceMessage(user, text, guild, text_channel, self.bot.user)

            # Dispatch to the chat cog via the bot's event system
            self.bot.dispatch("message", voice_msg)

        except Exception as e:
            print(f"❌ [Voice] Utterance processing error: {e}")
            import traceback
            traceback.print_exc()


async def setup(bot):
    """Setup function for loading the cog"""
    await bot.add_cog(VoiceCommands(bot))
