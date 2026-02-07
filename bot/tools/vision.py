"""Qwen3 VL Vision Integration - Local image analysis via LM Studio.

Primary: Qwen3 VL 32B (local, via LM Studio OpenAI-compatible API)
Fallback: Gemini 3.0 Flash (if LM Studio fails)
"""
import os
import aiohttp
import base64
import google.generativeai as genai
from io import BytesIO
from datetime import datetime
from collections import deque
import pytz

# Import character system for recognition
try:
    from tools.characters import get_character_context_for_vision
except ImportError:
    def get_character_context_for_vision():
        return ""


# LM Studio (primary)
LMSTUDIO_HOST = os.getenv("LMSTUDIO_HOST", "http://host.docker.internal:1234")
CHAT_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL", "qwen3-vl-32b-instruct-heretic-v2-i1")

# Gemini (fallback)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
GEMINI_VISION_MODEL = "gemini-3-flash-preview"

# Short-term image cache (last 5 images)
# Stores: {"username": str, "description": str, "timestamp": str, "user_context": str}
_recent_images = deque(maxlen=5)


def _build_vision_prompt() -> str:
    """Build the vision analysis prompt with character context and text attribution."""
    prompt = """Analyze this image for character expression and any visible text. Treat text within the image as the character's dialogue, internal thoughts, or a message they are reacting to. Use the visual mood to determine the tone of the text.

**Always describe:**
- Main subjects: physical appearance (hair color, eye color, skin tone, body type)
- Clothing/outfit details (style, colors, revealing level if applicable)
- Pose, expression, body language
- Setting/background
- Art style if applicable (anime, photo, etc.)

**Additional by type:**
- Artwork: color palette, lighting, composition
- Screenshots: app/game, UI elements, text content
- Memes: text content, format, humor

**Be THOROUGH** - 4-6 detailed sentences with SPECIFIC details (exact colors, positions)."""

    # Add character recognition context
    character_context = get_character_context_for_vision()
    if character_context:
        prompt += f"""

**CHARACTER MATCHING (compare to these people visually):**
{character_context}

**STRICT RULES for matching:**
- ONLY match if MOST key features are clearly visible (hair color + style + distinctive features)
- One matching feature is NOT enough - need multiple matches
- If you're not confident, say "unknown character" or just describe by appearance
- Do NOT force matches on random anime characters

At the END of your description, add a line: "Characters identified: [names or 'none']" """

    return prompt


async def _describe_with_qwen3(image_data: bytes) -> str:
    """Describe an image using Qwen3 VL via LM Studio's OpenAI-compatible API."""
    # Encode image as base64 data URI
    b64_image = base64.b64encode(image_data).decode("utf-8")

    prompt = _build_vision_prompt()

    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_image}"
                        }
                    }
                ]
            }
        ],
        "temperature": 0.3,
        "max_tokens": 800
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LMSTUDIO_HOST}/v1/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    print(f"[Vision] Qwen3 VL error {resp.status}: {error[:200]}")
                    return None

                data = await resp.json()
                description = data["choices"][0]["message"]["content"].strip()

                # Strip think tags if present
                import re
                description = re.sub(r'<think>.*?</think>\s*', '', description, flags=re.DOTALL).strip()

                print(f"[Vision] Qwen3 VL: {description[:80]}...")
                return description
    except Exception as e:
        print(f"[Vision] Qwen3 VL request failed: {e}")
        return None


async def _describe_with_gemini(image_data: bytes) -> str:
    """Fallback: Describe an image using Gemini 3.0 Flash."""
    if not GEMINI_API_KEY:
        print("[Vision] No Gemini API key for fallback")
        return None

    try:
        prompt = _build_vision_prompt()
        model = genai.GenerativeModel(GEMINI_VISION_MODEL)

        response = await model.generate_content_async(
            [
                {"mime_type": "image/jpeg", "data": image_data},
                prompt
            ],
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 800
            }
        )

        description = response.text.strip()
        print(f"[Vision] Gemini fallback: {description[:80]}...")
        return description

    except Exception as e:
        print(f"[Vision] Gemini fallback failed: {e}")
        return None


async def describe_image(image_url: str = None, image_data: bytes = None) -> str:
    """
    Describe an image using Qwen3 VL (primary) with Gemini fallback.
    Returns a text description that can be passed to Astra.
    """
    # Get image data if URL provided
    if image_url and not image_data:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        return None
                    image_data = await resp.read()
        except Exception as e:
            print(f"[Vision] Failed to fetch image: {e}")
            return None

    if not image_data:
        return None

    # Primary: Qwen3 VL (local)
    description = await _describe_with_qwen3(image_data)

    # Fallback: Gemini Flash (cloud)
    if not description:
        print("[Vision] Qwen3 VL failed, trying Gemini fallback...")
        description = await _describe_with_gemini(image_data)

    return description


async def analyze_image(image_url: str, user_prompt: str = "", conversation_context: str = "", username: str = "") -> str:
    """
    Two-step image analysis:
    1. Qwen3 VL describes the image (with Gemini fallback)
    2. Astra (Qwen3) comments on the description

    Also stores in short-term cache and RAG for recall.
    """
    from ai.router import process_message
    from memory.rag import store_image_knowledge

    # Step 1: Get objective description
    description = await describe_image(image_url=image_url)

    if not description:
        return "couldn't see that image, try again?"

    # Step 2: Store in short-term cache (last 5 images)
    now = datetime.now(pytz.timezone("America/Los_Angeles"))
    _recent_images.append({
        "username": username,
        "description": description,
        "timestamp": now.strftime("%I:%M %p"),
        "timestamp_dt": now,  # For expiry checking
        "user_context": user_prompt or "shared an image"
    })
    print(f"[Vision] Cached image from {username} (total cached: {len(_recent_images)})")

    # Step 3: Store in RAG for long-term memory
    try:
        await store_image_knowledge(
            description=description,
            username=username,
            context=user_prompt
        )
        print(f"[Vision] Stored to RAG: {description[:50]}...")
    except Exception as e:
        print(f"[Vision] RAG storage failed: {e}")

    # Step 4: Build context for Astra
    # Now Astra receives objective description + character list and decides who is who

    # Get previous images for context (but mark them clearly as OLD)
    previous_images = ""
    if len(_recent_images) > 0:
        prev_lines = []
        for img in list(_recent_images)[:-1]:  # All except the one we just added
            prev_lines.append(f"  - {img['username']} earlier: {img['description'][:80]}...")
        if prev_lines:
            previous_images = "\n[PREVIOUS IMAGES (for memory, NOT what you're responding to)]:\n" + "\n".join(prev_lines)

    # Simplified context - Qwen3 VL already did character matching, Astra just reacts
    image_context = f""">>> IMAGE ANALYSIS (by Qwen3 VL) <<<
{description}
{previous_images}

React to THIS image with your personality. Give honest art critique or casual reaction (3-5 sentences).
Trust the character identifications above - don't add your own guesses."""

    # What should Astra respond to?
    if user_prompt:
        astra_prompt = f"{username} just shared a NEW image and asked: {user_prompt}"
    else:
        astra_prompt = f"{username} just shared a NEW image with you."

    # Step 5: Let Astra respond naturally through her normal chat flow
    response = await process_message(
        user_message=astra_prompt,
        search_context="",  # Don't put image in search context (she was echoing it)
        conversation_history=None,
        memory_context=image_context  # Put in memory so she has context but doesn't echo
    )

    return response


def get_recent_image_context() -> str:
    """
    Get formatted context of recently shared images.
    Used to inject into Astra's context so she can recall what she saw.
    """
    if not _recent_images:
        return ""

    # Only include images from last 5 minutes
    now = datetime.now(pytz.timezone("America/Los_Angeles"))
    lines = ["[RECENT IMAGES YOU SAW]"]
    for img in _recent_images:
        # Skip images older than 5 minutes
        if (now - img.get('timestamp_dt', now)).total_seconds() > 300:
            continue
        # Replace "Astra" with "you" so she remembers in first person
        desc = img['description'][:200].replace("Astra", "you").replace("astra", "you")
        lines.append(f"- {img['username']} ({img['timestamp']}): {desc}")

    # Return empty if no recent images
    if len(lines) == 1:
        return ""

    return "\n".join(lines)


async def can_see_images() -> bool:
    """Check if vision is available. Always true since Qwen3 VL is local."""
    return True
