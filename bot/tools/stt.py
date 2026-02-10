"""
Speech-to-Text Handler for Astra
Tries Gemini cloud STT first, falls back to local faster-whisper server.
"""

import asyncio
import aiohttp
import google.generativeai as genai


# --- Cloud STT (Gemini - primary) ---
STT_MODEL = "gemini-2.5-flash"
STT_PROMPT = (
    "Transcribe this audio exactly as spoken. "
    "Return ONLY the spoken words, nothing else. "
    "If the audio is silence or unintelligible noise, return exactly: [silence]"
)

# --- Local STT (faster-whisper fallback) ---
LOCAL_STT_URL = "http://host.docker.internal:8200/transcribe"
LOCAL_STT_TIMEOUT = 10  # seconds


async def transcribe(wav_bytes: bytes) -> str | None:
    """
    Transcribe WAV audio bytes to text.
    Tries Gemini cloud first, falls back to local faster-whisper.
    """
    # Try cloud STT first
    result = await _transcribe_cloud(wav_bytes)
    if result is not None:
        return result

    # Fall back to local STT
    return await _transcribe_local(wav_bytes)


async def _transcribe_cloud(wav_bytes: bytes) -> str | None:
    """Transcribe via Gemini cloud API (primary)."""
    try:
        model = genai.GenerativeModel(STT_MODEL)

        response = await model.generate_content_async(
            [
                STT_PROMPT,
                {"mime_type": "audio/wav", "data": wav_bytes},
            ]
        )

        text = response.text.strip()

        if not text or text.lower() in ("[silence]", "silence", ""):
            return None

        print(f'🎙️ [STT-Cloud] Transcribed: "{text[:80]}{"..." if len(text) > 80 else ""}"')
        return text

    except Exception as e:
        print(f"⚠️ [STT-Cloud] Failed ({type(e).__name__}), falling back to local")
        return None


async def _transcribe_local(wav_bytes: bytes) -> str | None:
    """Transcribe via local faster-whisper server (fallback)."""
    try:
        timeout = aiohttp.ClientTimeout(total=LOCAL_STT_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            form = aiohttp.FormData()
            form.add_field("file", wav_bytes, filename="audio.wav", content_type="audio/wav")

            async with session.post(LOCAL_STT_URL, data=form) as resp:
                if resp.status != 200:
                    print(f"❌ [STT-Local] Server error: {resp.status}")
                    return None

                data = await resp.json()
                text = data.get("text", "").strip()

                if not text or text.lower() in ("[silence]", "silence", ""):
                    return None

                proc_time = data.get("processing_time", "?")
                print(f'🎙️ [STT-Local] Transcribed ({proc_time}s): "{text[:80]}{"..." if len(text) > 80 else ""}"')
                return text

    except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as e:
        print(f"❌ [STT-Local] Server unavailable ({type(e).__name__})")
        return None
