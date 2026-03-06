"""
Speech-to-Text Handler for Astra
Tries local faster-whisper server first, falls back to Gemini cloud STT.
"""

import asyncio
import aiohttp
import os
from google import genai
from google.genai import types


# Initialize Gemini client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --- Local STT (faster-whisper - primary) ---
LOCAL_STT_URL = "http://host.docker.internal:8200/transcribe"
LOCAL_STT_TIMEOUT = 10  # seconds

# --- Cloud STT (Gemini - fallback) ---
STT_MODEL = "gemini-2.5-flash"
STT_PROMPT = (
    "Transcribe this audio exactly as spoken. "
    "Return ONLY the spoken words, nothing else. "
    "If the audio is silence or unintelligible noise, return exactly: [silence]"
)


async def transcribe(wav_bytes: bytes) -> str | None:
    """
    Transcribe WAV audio bytes to text.
    Tries local faster-whisper first, falls back to Gemini cloud.
    """
    # Try local STT first
    result = await _transcribe_local(wav_bytes)
    if result is not None:
        return result

    # Fall back to cloud STT
    return await _transcribe_cloud(wav_bytes)


async def _transcribe_cloud(wav_bytes: bytes) -> str | None:
    """Transcribe via Gemini cloud API (fallback)."""
    if not client:
        return None

    try:
        # Run sync Gemini API call in executor to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=STT_MODEL,
                contents=[
                    types.Part.from_text(text=STT_PROMPT),
                    types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                ]
            )
        )

        text = response.text.strip()

        if not text or text.lower() in ("[silence]", "silence", ""):
            return None

        print(f'🎙️ [STT-Cloud] ✓ Fallback transcribed: "{text[:80]}{"..." if len(text) > 80 else ""}"')
        return text

    except Exception as e:
        print(f"❌ [STT-Cloud] Failed ({type(e).__name__}: {e})")
        import traceback
        traceback.print_exc()
        return None


async def _transcribe_local(wav_bytes: bytes) -> str | None:
    """Transcribe via local faster-whisper server (primary)."""
    try:
        timeout = aiohttp.ClientTimeout(total=LOCAL_STT_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            form = aiohttp.FormData()
            form.add_field("file", wav_bytes, filename="audio.wav", content_type="audio/wav")

            async with session.post(LOCAL_STT_URL, data=form) as resp:
                if resp.status != 200:
                    print(f"⚠️ [STT-Local] Server error: {resp.status}, falling back to cloud")
                    return None

                data = await resp.json()
                text = data.get("text", "").strip()

                if not text or text.lower() in ("[silence]", "silence", ""):
                    return None

                proc_time = data.get("processing_time", "?")
                print(f'🎙️ [STT-Local] ✓ Transcribed ({proc_time}s): "{text[:80]}{"..." if len(text) > 80 else ""}"')
                return text

    except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as e:
        print(f"⚠️ [STT-Local] Unavailable ({type(e).__name__}), falling back to cloud")
        return None
