"""
Qwen3-TTS streaming integration for Astra - Namaka Voice Clone
Uses local Qwen3-TTS Docker API server with streaming WAV chunks.
Voice: namaka
"""

import aiohttp
import asyncio
import re
import struct


class KokoroTTS:
    """Qwen3-TTS streaming client (class name kept for import compatibility)"""

    def __init__(self, api_url="http://host.docker.internal:8880", voice="raiden"):
        self.api_url = api_url
        self.voice = voice

    async def generate_audio_streaming(self, text, base_output_path="output.wav"):
        """
        Generate TTS audio via streaming - yields each chunk path as soon as it arrives.

        Sends the full text to the server, which streams back length-prefixed WAV chunks.
        Each chunk is saved to disk and yielded immediately for playback.

        Args:
            text: Text to convert to speech
            base_output_path: Base path for chunk files

        Yields:
            Path to each audio chunk as it arrives from the server
        """
        text = self._clean_markdown(text)

        if not text.strip():
            return

        print(f"[Qwen3 TTS] Streaming: {text[:80]}...")

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "text": text,
                    "language": "English",
                    "voice": self.voice,
                }

                async with session.post(
                    f"{self.api_url}/tts",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        print(f"Qwen3 TTS failed ({resp.status}): {error_text[:200]}")
                        return

                    chunk_idx = 0
                    while True:
                        # Read 4-byte length header
                        header = await resp.content.readexactly(4)
                        length = struct.unpack(">I", header)[0]

                        # Zero length = end of stream
                        if length == 0:
                            break

                        # Read the WAV chunk
                        wav_data = await resp.content.readexactly(length)

                        # Save to numbered file
                        chunk_path = f"{base_output_path}.chunk{chunk_idx:02d}.wav"
                        with open(chunk_path, "wb") as f:
                            f.write(wav_data)

                        print(f"[Qwen3 TTS] Chunk {chunk_idx}: {chunk_path} ({len(wav_data)} bytes)")
                        chunk_idx += 1
                        yield chunk_path

                    print(f"[Qwen3 TTS] Stream complete: {chunk_idx} chunks")

        except aiohttp.ClientConnectorError:
            print(f"Qwen3 TTS connection error: Could not connect to {self.api_url}")
            print(f"  Make sure qwen3-tts Docker container is running")
        except asyncio.IncompleteReadError:
            print(f"Qwen3 TTS: Server closed connection unexpectedly")
        except asyncio.TimeoutError:
            print(f"Qwen3 TTS timeout: Request took longer than 120 seconds")
        except Exception as e:
            print(f"Qwen3 TTS error: {e}")
            import traceback
            traceback.print_exc()

    def _clean_markdown(self, text):
        """Remove markdown formatting for TTS"""
        # Remove headers (### Header)
        text = re.sub(r"^#{1,6}\s+(.+?)$", r"\1", text, flags=re.MULTILINE)

        # Remove bold (**text** or __text__)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)

        # Remove italics (*text* or _text_)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"_(.+?)_", r"\1", text)

        # Remove strikethrough (~~text~~)
        text = re.sub(r"~~(.+?)~~", r"\1", text)

        # Remove code blocks (```text```)
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

        # Remove inline code (`text`)
        text = re.sub(r"`(.+?)`", r"\1", text)

        # Remove URLs [text](url)
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)

        # Remove emotion stickers [laugh], [cool], [comfy], etc.
        text = re.sub(r"\[\w+\]", "", text)

        # Remove Discord emotes :joy:, :fire:, :skull:, etc.
        text = re.sub(r":\w+:", "", text)

        # Remove Unicode emoji (actual emoji characters)
        text = re.sub(r"[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001FA00-\U0001FAFF]", "", text)

        # Clean up multiple spaces and newlines
        text = re.sub(r"\n\s*\n", ". ", text)  # Double newlines become periods
        text = re.sub(r"\s+", " ", text)  # Multiple spaces become single

        return text.strip()

    def change_voice(self, new_voice):
        """Change voice"""
        self.voice = new_voice
        print(f"Voice changed to: {new_voice}")
