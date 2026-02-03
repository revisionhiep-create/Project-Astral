"""
Voice Handler for Astra
Uses Kokoro TTS API with streaming chunks for long text
Voice: jf_tebukuro (Japanese female anime voice)
"""

import discord
import asyncio
import os
from pathlib import Path
from typing import Optional

from tools.kokoro_tts import KokoroTTS


class VoiceHandler:
    """Manages voice channel connections and TTS playback"""

    def __init__(self, bot):
        self.bot = bot
        self.tts = KokoroTTS(
            api_url=os.getenv("KOKORO_TTS_URL", "http://192.168.1.16:8000"),
            voice="jf_tebukuro"
        )
        self.voice_queues = {}  # Guild ID -> list of audio files to play
        self.currently_playing = {}  # Guild ID -> bool
        self.temp_audio_dir = Path(__file__).parent.parent / "temp_audio"
        self.temp_audio_dir.mkdir(exist_ok=True)

    async def join_voice_channel(self, voice_channel) -> Optional[discord.VoiceClient]:
        """
        Join a voice channel

        Args:
            voice_channel: discord.VoiceChannel to join

        Returns:
            discord.VoiceClient or None if failed
        """
        try:
            # Check if already connected in this guild
            if voice_channel.guild.voice_client:
                # Move to new channel if different
                if voice_channel.guild.voice_client.channel != voice_channel:
                    await voice_channel.guild.voice_client.move_to(voice_channel)
                return voice_channel.guild.voice_client

            # Connect to voice channel
            voice_client = await voice_channel.connect()
            print(f"✅ Joined voice channel: {voice_channel.name}")

            # Initialize queue for this guild
            if voice_channel.guild.id not in self.voice_queues:
                self.voice_queues[voice_channel.guild.id] = []
                self.currently_playing[voice_channel.guild.id] = False

            return voice_client

        except Exception as e:
            print(f"❌ Failed to join voice channel: {e}")
            return None

    async def leave_voice_channel(self, guild):
        """
        Leave voice channel in a guild

        Args:
            guild: discord.Guild to leave voice from
        """
        try:
            if guild.voice_client:
                await guild.voice_client.disconnect()
                print(f"✅ Left voice channel in {guild.name}")

                # Clear queue
                if guild.id in self.voice_queues:
                    self.voice_queues[guild.id].clear()
                    self.currently_playing[guild.id] = False

                # Clean up any orphaned temp audio files
                self.cleanup_temp_audio()

        except Exception as e:
            print(f"❌ Failed to leave voice channel: {e}")

    async def speak_text(self, guild, text: str):
        """
        Convert text to speech and play in voice channel - STREAMING VERSION

        Args:
            guild: discord.Guild where bot is connected
            text: Text to speak
        """
        if not guild.voice_client:
            print("❌ Not connected to voice channel")
            return

        try:
            # Generate TTS audio - STREAMING VERSION with background generation
            base_filename = f"astra_tts_{guild.id}_{asyncio.get_event_loop().time()}"
            base_path = self.temp_audio_dir / base_filename

            # Initialize queue if needed
            if guild.id not in self.voice_queues:
                self.voice_queues[guild.id] = []
                self.currently_playing[guild.id] = False

            # Start background task to generate all chunks
            async def generate_chunks():
                try:
                    async for chunk_path in self.tts.generate_audio_streaming(
                        text, str(base_path)
                    ):
                        # Add to queue
                        self.voice_queues[guild.id].append(chunk_path)

                        # Start playback if not already playing
                        if not self.currently_playing[guild.id]:
                            asyncio.create_task(self._process_queue(guild))
                except Exception as e:
                    print(f"❌ Background chunk generation failed: {e}")
                    import traceback
                    traceback.print_exc()

            # Run generation in background (don't await - let it run independently!)
            asyncio.create_task(generate_chunks())

        except Exception as e:
            print(f"❌ Failed to speak text: {e}")
            import traceback
            traceback.print_exc()

    async def _process_queue(self, guild):
        """Process the audio queue for a guild"""
        voice_client = guild.voice_client

        if not voice_client:
            print("❌ No voice client found")
            return

        self.currently_playing[guild.id] = True

        while self.voice_queues[guild.id]:
            audio_path = self.voice_queues[guild.id].pop(0)

            try:
                # Verify file exists
                if not Path(audio_path).exists():
                    print(f"❌ Audio file doesn't exist: {audio_path}")
                    continue

                # Play audio using FFmpeg with Discord-compatible options
                audio_source = discord.FFmpegPCMAudio(
                    audio_path, executable="ffmpeg", options="-vn"
                )

                # Wait for audio to finish
                done_event = asyncio.Event()
                loop = asyncio.get_event_loop()

                def after_playback(error):
                    if error:
                        print(f"❌ Playback error: {error}")
                    # Schedule the event.set() on the event loop thread
                    loop.call_soon_threadsafe(done_event.set)

                voice_client.play(audio_source, after=after_playback)
                await done_event.wait()

                # Clean up temp file
                try:
                    Path(audio_path).unlink()
                except:
                    pass

                # Minimal delay for smooth chunk transitions
                await asyncio.sleep(0.05)

            except Exception as e:
                print(f"❌ Error playing audio: {e}")
                import traceback
                traceback.print_exc()

        # Queue processing complete
        self.currently_playing[guild.id] = False

    def is_in_voice(self, guild) -> bool:
        """Check if bot is in a voice channel in this guild"""
        return guild.voice_client is not None

    def cleanup_temp_audio(self):
        """Clean up old temporary audio files"""
        try:
            for file in self.temp_audio_dir.glob("*.wav"):
                try:
                    file.unlink()
                except:
                    pass
        except Exception as e:
            print(f"⚠️ Error cleaning up temp audio: {e}")


# Global voice handler instance
voice_handler = None


def get_voice_handler(bot):
    """Get or create voice handler instance"""
    global voice_handler
    if voice_handler is None:
        voice_handler = VoiceHandler(bot)
    return voice_handler
