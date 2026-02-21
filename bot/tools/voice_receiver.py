"""
Voice Receiver for Astra
Captures per-user audio from Discord voice channels using discord-ext-voice-recv.
Implements VAD (Voice Activity Detection) via silence gap detection,
buffers audio per-user, and emits complete utterances as WAV bytes.
Includes a watchdog to auto-restart the listener on PacketRouter crashes.
"""

import io
import struct
import asyncio
import time
from typing import Callable, Awaitable

import discord

try:
    from discord.ext import voice_recv
    VOICE_RECV_AVAILABLE = True
except ImportError:
    VOICE_RECV_AVAILABLE = False
    print("⚠️ discord-ext-voice-recv not installed — voice listening disabled")


# --- Audio constants ---
SAMPLE_RATE = 48000   # Discord Opus default
CHANNELS = 2          # Stereo from Discord
BYTES_PER_SAMPLE = 2  # 16-bit PCM
FRAME_SIZE = 3840     # 20ms frame at 48kHz stereo (960 samples * 2 channels * 2 bytes)

# --- VAD settings ---
SILENCE_THRESHOLD_SEC = 2.0   # Seconds of silence to consider utterance complete
MIN_UTTERANCE_SEC = 1.5       # Minimum utterance length to process (reject tiny fragments)
MAX_UTTERANCE_SEC = 30        # Maximum utterance length before force-flush

# --- Output WAV format ---
OUT_SAMPLE_RATE = 16000  # Downsample for STT
OUT_CHANNELS = 1         # Mono for STT


class VoiceReceiver:
    """
    Receives audio from Discord voice and detects speech utterances.
    Uses discord-ext-voice-recv's BasicSink.
    """

    def __init__(
        self,
        voice_client: discord.VoiceClient,
        on_utterance: Callable[[discord.User, bytes, discord.Guild], Awaitable[None]],
        guild: discord.Guild,
    ):
        self.voice_client = voice_client
        self.on_utterance = on_utterance
        self.guild = guild

        # Per-user audio buffers: user_id -> list of PCM bytes
        self.buffers: dict[int, list[bytes]] = {}
        # Per-user last-audio timestamp
        self.last_audio_time: dict[int, float] = {}
        # User ID -> discord.User mapping
        self.users: dict[int, discord.User] = {}
        # Flush check task
        self._flush_task: asyncio.Task | None = None
        # Watchdog task
        self._watchdog_task: asyncio.Task | None = None
        self._running = False

    def start(self):
        """Start listening for audio."""
        if not VOICE_RECV_AVAILABLE:
            print("❌ Cannot start voice receiver — discord-ext-voice-recv not available")
            return False

        self._running = True

        def callback(user: discord.User, data: voice_recv.VoiceData) -> None:
            if user is None:
                return
            pcm = data.pcm
            if pcm:
                self._handle_audio(user, pcm)

        self.voice_client.listen(voice_recv.BasicSink(callback))
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        print(f"✅ [VoiceRecv] Started listening in {self.guild.name}")
        return True

    def stop(self):
        """Stop listening for audio."""
        self._running = False
        try:
            if self.voice_client.is_listening():
                self.voice_client.stop_listening()
        except Exception:
            pass

        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
        if self._watchdog_task:
            self._watchdog_task.cancel()
            self._watchdog_task = None

        self.buffers.clear()
        self.last_audio_time.clear()
        self.users.clear()
        print(f"🔇 [VoiceRecv] Stopped listening in {self.guild.name}")

    def _handle_audio(self, user: discord.User, pcm: bytes) -> None:
        """Called for each audio packet received."""
        uid = user.id
        now = time.monotonic()

        if uid not in self.buffers:
            self.buffers[uid] = []
            self.users[uid] = user

        self.buffers[uid].append(pcm)
        self.last_audio_time[uid] = now

    async def _flush_loop(self) -> None:
        """Periodically check for completed utterances (silence gap detection)."""
        try:
            while self._running:
                await asyncio.sleep(0.3)
                now = time.monotonic()

                for uid in list(self.last_audio_time.keys()):
                    last_time = self.last_audio_time.get(uid, now)
                    silence_duration = now - last_time
                    buffer = self.buffers.get(uid, [])

                    if not buffer:
                        continue

                    total_bytes = sum(len(b) for b in buffer)
                    duration_sec = total_bytes / (SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE)

                    # Force flush if too long
                    if duration_sec >= MAX_UTTERANCE_SEC:
                        await self._emit_utterance(uid)
                        continue

                    # Flush on silence gap
                    if silence_duration >= SILENCE_THRESHOLD_SEC and duration_sec >= MIN_UTTERANCE_SEC:
                        await self._emit_utterance(uid)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"❌ [VoiceRecv] Flush loop error: {e}")

    async def _watchdog_loop(self) -> None:
        """Monitor the PacketRouter thread and restart if it dies."""
        try:
            while self._running:
                await asyncio.sleep(3)

                if not self._running:
                    break

                if not self.voice_client.is_connected():
                    break

                if not self.voice_client.is_listening():
                    print("⚠️ [VoiceRecv] Router died — restarting listener...")
                    await asyncio.sleep(1)

                    if not self._running or not self.voice_client.is_connected():
                        break

                    try:
                        def callback(user: discord.User, data: voice_recv.VoiceData) -> None:
                            if user is None:
                                return
                            pcm = data.pcm
                            if pcm:
                                self._handle_audio(user, pcm)

                        self.voice_client.listen(voice_recv.BasicSink(callback))
                        print("✅ [VoiceRecv] Listener restarted successfully")
                    except Exception as e:
                        print(f"❌ [VoiceRecv] Failed to restart listener: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"❌ [VoiceRecv] Watchdog error: {e}")

    async def _emit_utterance(self, uid: int) -> None:
        """Process and emit a complete utterance for a user."""
        buffer = self.buffers.pop(uid, [])
        self.last_audio_time.pop(uid, None)
        user = self.users.get(uid)

        if not buffer or not user:
            return

        # Combine PCM chunks
        raw_pcm = b"".join(buffer)

        # Downsample: 48kHz stereo -> 16kHz mono
        mono_16k = self._downsample(raw_pcm)

        # Wrap in WAV
        wav_bytes = self._make_wav(mono_16k)

        duration = len(mono_16k) / (OUT_SAMPLE_RATE * BYTES_PER_SAMPLE)
        print(f"🔊 [VoiceRecv] Utterance from {user.display_name}: {duration:.1f}s")

        # Fire callback
        try:
            await self.on_utterance(user, wav_bytes, self.guild)
        except Exception as e:
            print(f"❌ [VoiceRecv] Utterance callback error: {e}")

    def _downsample(self, pcm_48k_stereo: bytes) -> bytes:
        """Downsample from 48kHz stereo to 16kHz mono."""
        samples = struct.unpack(f"<{len(pcm_48k_stereo) // 2}h", pcm_48k_stereo)

        # Stereo to mono (average L+R)
        mono = []
        for i in range(0, len(samples), 2):
            if i + 1 < len(samples):
                mono.append((samples[i] + samples[i + 1]) // 2)
            else:
                mono.append(samples[i])

        # 48kHz -> 16kHz (take every 3rd sample)
        downsampled = mono[::3]

        return struct.pack(f"<{len(downsampled)}h", *downsampled)

    def _make_wav(self, pcm_16k_mono: bytes) -> bytes:
        """Wrap raw PCM in a WAV header."""
        buf = io.BytesIO()
        data_size = len(pcm_16k_mono)

        # WAV header
        buf.write(b"RIFF")
        buf.write(struct.pack("<I", 36 + data_size))
        buf.write(b"WAVE")
        buf.write(b"fmt ")
        buf.write(struct.pack("<I", 16))  # chunk size
        buf.write(struct.pack("<H", 1))  # PCM format
        buf.write(struct.pack("<H", OUT_CHANNELS))
        buf.write(struct.pack("<I", OUT_SAMPLE_RATE))
        buf.write(struct.pack("<I", OUT_SAMPLE_RATE * OUT_CHANNELS * BYTES_PER_SAMPLE))
        buf.write(struct.pack("<H", OUT_CHANNELS * BYTES_PER_SAMPLE))
        buf.write(struct.pack("<H", BYTES_PER_SAMPLE * 8))
        buf.write(b"data")
        buf.write(struct.pack("<I", data_size))
        buf.write(pcm_16k_mono)

        return buf.getvalue()
