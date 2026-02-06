"""Gemini Vision Integration - Gemini 3.0 Flash for all image analysis.

Uses Gemini 3.0 Flash exclusively for image descriptions.
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


async def describe_image(image_url: str = None, image_data: bytes = None) -> str:
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
        description_prompt = """Analyze this image THOROUGHLY and OBJECTIVELY.

**Always describe:**
- Main subjects: physical appearance (hair color, eye color, skin tone, body type)
- Clothing/outfit details (style, colors, revealing level if applicable)  
- Pose, expression, body language
- Setting/background
- Art style if applicable (anime, photo, etc.)

**Additional by type:**
- Artwork: color palette, lighting, composition
- Screenshots: app/game, UI elements, text
- Memes: text content, format

**Be THOROUGH** - 4-6 detailed sentences with SPECIFIC details (exact colors, positions)."""
        
        # Add character recognition - Gemini can visually compare
        character_context = get_character_context_for_vision()
        if character_context:
            description_prompt += f"""

**CHARACTER MATCHING (compare to these people visually):**
{character_context}

**STRICT RULES for matching:**
- ONLY match if MOST key features are clearly visible (hair color + style + distinctive features)
- One matching feature is NOT enough - need multiple matches
- If you're not confident, say "unknown character" or just describe by appearance
- Do NOT force matches on random anime characters

At the END of your description, add a line: "Characters identified: [names or 'none']" """
        
        model = genai.GenerativeModel(GEMINI_VISION_MODEL)
        
        response = await model.generate_content_async(
            [
                {"mime_type": "image/jpeg", "data": image_data},
                description_prompt
            ],
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 800
            }
        )
        
        description = response.text.strip()
        print(f"[Vision] Gemini 3.0 Flash: {description[:80]}...")
        return description
                
    except Exception as e:
        print(f"[Vision] Gemini vision failed: {e}")
        return None


async def analyze_image(image_url: str, user_prompt: str = "", conversation_context: str = "", username: str = "") -> str:
    """
    Two-step image analysis:
    1. Gemini describes the image
    2. Astra (Mistral) comments on the description
    
    Also stores in short-term cache and RAG for recall.
    """
    from ai.router import process_message
    from memory.rag import store_image_knowledge
    
    # Step 1: Get Gemini's objective description
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
    
    # Simplified context - Gemini already did character matching, Astra just reacts
    image_context = f""">>> IMAGE ANALYSIS (by Gemini) <<<
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
    """Check if vision is available."""
    return bool(GEMINI_API_KEY)
