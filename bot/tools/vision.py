"""Gemini Vision Integration - Two-step flow: Gemini describes, Astra comments."""
import os
import aiohttp
import google.generativeai as genai
from io import BytesIO

# Import character system for recognition
try:
    from tools.characters import get_character_context_for_vision
except ImportError:
    def get_character_context_for_vision():
        return ""


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Vision model for description only
VISION_MODEL = "gemini-2.0-flash"


async def describe_image(image_url: str = None, image_data: bytes = None) -> str:
    """
    Step 1: Gemini describes what it sees objectively.
    Returns a text description that can be passed to Astra.
    """
    if not GEMINI_API_KEY:
        return None
    
    try:
        # Get image data if URL provided
        if image_url and not image_data:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        return None
                    image_data = await resp.read()
        
        if not image_data:
            return None
        
        # Build objective description prompt
        description_prompt = """Describe this image objectively and thoroughly.
Include:
- Main subjects (people, characters, objects)
- Colors, art style, composition
- Actions, poses, expressions
- Background and setting
- Any text visible in the image

Be factual and detailed but concise (3-5 sentences).
Do NOT add personality or commentary - just describe what you see."""
        
        # Add character recognition context
        character_context = get_character_context_for_vision()
        if character_context:
            description_prompt += f"""

Known characters to identify if present:
{character_context}
If you recognize any of these characters, mention them by name."""
        
        model = genai.GenerativeModel(VISION_MODEL)
        
        response = await model.generate_content_async(
            [
                {"mime_type": "image/jpeg", "data": image_data},
                description_prompt
            ],
            generation_config={
                "temperature": 0.3,  # Low for accuracy
                "max_output_tokens": 400
            }
        )
        
        description = response.text.strip()
        print(f"[Vision] Description: {description[:80]}...")
        return description
        
    except Exception as e:
        print(f"[Vision Error] {e}")
        return None


async def analyze_image(image_url: str, user_prompt: str = "", conversation_context: str = "", username: str = "") -> str:
    """
    Two-step image analysis:
    1. Gemini describes the image
    2. Astra (Mistral) comments on the description
    
    This lets Astra's real personality respond, not Gemini pretending.
    """
    from ai.router import process_message
    
    # Step 1: Get Gemini's objective description
    description = await describe_image(image_url=image_url)
    
    if not description:
        return "couldn't see that image, try again?"
    
    # Step 2: Build context for Astra
    image_context = f"[Image shared by {username}]: {description}"
    
    # What should Astra respond to?
    if user_prompt:
        astra_prompt = f"{username} shared an image and asked: {user_prompt}"
    else:
        astra_prompt = f"{username} shared an image with you"
    
    # Step 3: Let Astra respond naturally through her normal chat flow
    response = await process_message(
        user_message=astra_prompt,
        search_context=image_context,
        conversation_history=None,
        memory_context=""
    )
    
    return response


async def can_see_images() -> bool:
    """Check if vision is available."""
    return bool(GEMINI_API_KEY)
