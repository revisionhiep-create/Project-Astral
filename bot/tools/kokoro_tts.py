"""
Kokoro TTS integration for Astra - STREAMING VERSION
Uses local Kokoro Docker API server for anime-style voice
Voice: jf_tebukuro (Japanese female anime voice)
"""

import aiohttp
import asyncio
import os
import re


class KokoroTTS:
    """Kokoro TTS client for anime-style voices - with streaming support"""

    def __init__(self, api_url="http://192.168.1.16:8000", voice="jf_tebukuro"):
        """
        Initialize Kokoro TTS client

        Args:
            api_url: URL to Kokoro Docker API (desktop server)
            voice: Voice to use (default: jf_tebukuro - anime-like)
        """
        self.api_url = api_url
        self.voice = voice
        self.speed = 1.2  # Slightly faster for energetic/cute effect
        self.max_chunk_size = 200  # Smaller chunks = faster first sound!

    async def generate_audio_streaming(self, text, base_output_path="output.wav"):
        """
        Generate TTS audio chunks - yields each chunk as it's ready for INSTANT playback!

        Args:
            text: Text to convert to speech
            base_output_path: Base path for chunk files

        Yields:
            Path to each audio chunk as it's generated
        """
        # Clean markdown formatting before TTS
        text = self._clean_markdown(text)

        # Short text - return immediately
        if len(text) <= self.max_chunk_size:
            result = await self._generate_single(text, base_output_path)
            if result:
                yield result
            return

        # Long text - split and yield each chunk as it's ready
        chunks = self._split_text(text)

        for i, chunk in enumerate(chunks):
            # Use zero-padded numbers for proper sorting (chunk00, chunk01, ... chunk10)
            chunk_path = f"{base_output_path}.chunk{i:02d}.wav"
            result = await self._generate_single(chunk, chunk_path)
            if result:
                yield result

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

        # Clean up multiple spaces and newlines
        text = re.sub(r"\n\s*\n", ". ", text)  # Double newlines become periods
        text = re.sub(r"\s+", " ", text)  # Multiple spaces become single

        return text.strip()

    def _split_text(self, text):
        """Split text into chunks at sentence boundaries"""
        # Split on sentence endings, keeping punctuation
        sentences = re.split(r"([.!?]+\s+)", text)

        chunks = []
        current_chunk = ""

        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            punctuation = sentences[i + 1] if i + 1 < len(sentences) else ""
            full_sentence = sentence + punctuation

            # Check if adding this sentence would exceed chunk size
            if len(current_chunk) + len(full_sentence) > self.max_chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = full_sentence
            else:
                current_chunk += full_sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text[: self.max_chunk_size]]

    async def _generate_single(self, text, output_path):
        """Generate TTS for a single chunk of text"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "text": text,
                    "voice": self.voice,
                    "speed": self.speed,
                    "lang": "en-us",
                }

                async with session.post(
                    f"{self.api_url}/tts",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        audio_data = await resp.read()

                        # Save to file
                        with open(output_path, "wb") as f:
                            f.write(audio_data)

                        return output_path
                    else:
                        error_text = await resp.text()
                        print(
                            f"❌ Kokoro TTS failed ({resp.status}): {error_text[:200]}"
                        )
                        return None

        except aiohttp.ClientConnectorError:
            print(
                f"❌ Kokoro TTS connection error: Could not connect to {self.api_url}"
            )
            return None
        except asyncio.TimeoutError:
            print(f"❌ Kokoro TTS timeout: Request took longer than 30 seconds")
            return None
        except Exception as e:
            print(f"❌ Kokoro TTS error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def change_voice(self, new_voice):
        """Change voice (jf_tebukuro, jf_alpha, af_bella, etc.)"""
        self.voice = new_voice
        print(f"✅ Voice changed to: {new_voice}")

    def set_speed(self, new_speed):
        """Change speech speed (1.0 = normal, 1.2 = slightly faster)"""
        self.speed = new_speed
        print(f"✅ Speed changed to: {new_speed}")
