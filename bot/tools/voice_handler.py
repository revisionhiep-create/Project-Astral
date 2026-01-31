"""
Voice Handler for Astra
Uses Kokoro TTS API for text-to-speech with Hannah voice (af_heart)
"""

import discord
import asyncio
import aiohttp
import os
from pathlib import Path
from typing import Optional


class VoiceHandler:
    """Manages voice channel connections and TTS playback"""

    def __init__(self, bot):
        self.bot = bot
        self.kokoro_url = os.getenv("KOKORO_TTS_URL", "http://localhost:8000")
        self.default_voice = "af_heart"  # Hannah voice
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

        except Exception as e:
            print(f"❌ Failed to leave voice channel: {e}")

    async def generate_tts(self, text: str, output_path: str) -> bool:
        """Generate TTS audio using Kokoro API"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "text": text,
                    "voice": self.default_voice,
                    "speed": 1.0,
                    "lang": "en-us"
                }
                async with session.post(
                    f"{self.kokoro_url}/tts",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        with open(output_path, 'wb') as f:
                            f.write(await response.read())
                        return True
                    else:
                        print(f"❌ TTS API error: {response.status}")
                        return False
        except Exception as e:
            print(f"❌ TTS generation failed: {e}")
            return False

    async def speak_text(self, guild, text: str):
        """
        Convert text to speech and play in voice channel

        Args:
            guild: discord.Guild where bot is connected
            text: Text to speak
        """
        if not guild.voice_client:
            print("❌ Not connected to voice channel")
            return

        try:
            # Generate TTS audio
            audio_path = self.temp_audio_dir / f"astra_tts_{guild.id}_{asyncio.get_event_loop().time()}.wav"
            
            success = await self.generate_tts(text, str(audio_path))
            if not success:
                return

            # Add to queue and start playback
            if guild.id not in self.voice_queues:
                self.voice_queues[guild.id] = []
                self.currently_playing[guild.id] = False

            self.voice_queues[guild.id].append(str(audio_path))

            # Start playback if not already playing
            if not self.currently_playing[guild.id]:
                asyncio.create_task(self._process_queue(guild))

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

                # Play audio using FFmpeg
                audio_source = discord.FFmpegPCMAudio(
                    audio_path, options="-vn"
                )

                # Wait for audio to finish
                done_event = asyncio.Event()
                loop = asyncio.get_event_loop()

                def after_playback(error):
                    if error:
                        print(f"❌ Playback error: {error}")
                    loop.call_soon_threadsafe(done_event.set)

                voice_client.play(audio_source, after=after_playback)
                await done_event.wait()

                # Clean up temp file
                try:
                    Path(audio_path).unlink()
                except:
                    pass

                # Small delay between clips
                await asyncio.sleep(0.1)

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
