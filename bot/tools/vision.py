"""Gemini Vision Integration - Gemini 3.0 Flash for all image analysis.

Uses Gemini 3.0 Flash exclusively for image descriptions.
Text Attribution Prompt: treats text in images as character dialogue/thoughts.
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


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Vision model - Gemini 3.0 Flash
GEMINI_VISION_MODEL = "gemini-3-flash-preview"

# Short-term image cache (last 5 images)
# Stores: {"username": str, "description": str, "timestamp": str, "user_context": str}
_recent_images = deque(maxlen=5)


async def describe_image(image_url: str = None, image_data: bytes = None, user_context: str = "", mime_type: str = "image/jpeg") -> str:
    """
    Describe an image using Gemini 3.0 Flash.
    Returns a text description that can be passed to Astra.
    """
    # Get image data if URL provided
    if image_url and not image_data:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        return None
                    mime_type = resp.headers.get('Content-Type', mime_type)
                    image_data = await resp.read()
        except Exception as e:
            print(f"[Vision] Failed to fetch image: {e}")
            return None
    
    if not image_data:
        return None
    
    if not GEMINI_API_KEY:
        print("[Vision] No Gemini API key configured")
        return None
    
    try:
        description_prompt = """Analyze this image for character expression and any visible text. Treat text within the image as the character's dialogue, internal thoughts, or a message they are reacting to. Use the visual mood to determine the tone of the text.

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

        # Add user context if provided (Make vision aware of the question/comment)
        if user_context:
            description_prompt += f"\n\n**USER CONTEXT/QUESTION:**\nThe user said this about the image: '{user_context}'\n(Answer this question or address this context specifically in your description if relevant)"
        
        # Add character recognition - Gemini can visually compare
        character_context = get_character_context_for_vision()
        if character_context:
            description_prompt += f"""

**CHARACTER MATCHING (compare to these people visually):**
{character_context}

**STRICT RULES for matching:**
- **CRITICAL DISTINCTION:** Do NOT confuse Astra (mature style, PURPLE eyes, STAR necklace) with GemGem (RAINBOW eyes, GEMS/PLANETS in hair).
- If the character has **RAINBOW/PINK** eyes or is chibi/cute/sticker style -> It is **GemGem**.
- If the character has **PURPLE-VIOLET** eyes and looks mature/composed -> It is **Astra (you)**.
- If **BOTH** are present, identify BOTH separately.
- ONLY match if MOST key features are clearly visible (hair color + style + distinctive features)
- If you're not confident, just describe by appearance without naming anyone
- Do NOT force matches on random anime girls
- If you recognize someone, just use their name naturally in the description
- Do NOT list who is or isn't in the image """
        
        model = genai.GenerativeModel(GEMINI_VISION_MODEL)
        
        response = await model.generate_content_async(
            [
                {"mime_type": mime_type, "data": image_data},
                description_prompt
            ],
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 800
            },
            safety_settings={
                genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
                genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
            }
        )
        
        description = response.text.strip()
        
        # Strip any "Characters identified:" line so Astra doesn't echo negative matches
        import re
        description = re.sub(r'\\n*Characters identified:.*$', '', description, flags=re.IGNORECASE | re.MULTILINE).strip()
        
        print(f"[Vision] Gemini 3.0 Flash: {description[:80]}...")
        return description
                
    except Exception as e:
        print(f"[Vision] Gemini vision failed: {e}")
        return None


async def analyze_image(image_url: str, user_prompt: str = "", conversation_context: str = "", username: str = "") -> str:
    """
    Two-step image analysis:
    1. Gemini describes the image
    2. Astra (Qwen3) comments on the description
    
    Also stores in short-term cache and RAG for recall.
    """
    from ai.router import process_message
    from memory.rag import store_image_knowledge
    
    # Step 1: Get Gemini's objective description WITH user context
    description = await describe_image(image_url=image_url, user_context=user_prompt)
    
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
    
    # Step 3: Skip RAG storage for images — descriptions pollute fact pool
    # Images are already in the 5-minute short-term cache above
    # (Previous behavior stored image descriptions as permanent "facts" which
    #  caused Astra to say "that's me" on every message)
    
    return f"[IMAGE ANALYSIS DATA]: {description}"


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
    """Check if vision is available."""
    return bool(GEMINI_API_KEY)
