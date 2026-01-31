"""Gemini Vision Integration - Image analysis with Astra personality and character recognition."""
import os
import aiohttp
import google.generativeai as genai
from io import BytesIO

# Import centralized personality
from ai.personality import ASTRA_PROMPT

# Import character system for recognition
try:
    from tools.characters import get_character_context_for_vision
except ImportError:
    def get_character_context_for_vision():
        return ""


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Vision model
VISION_MODEL = "gemini-2.0-flash"


async def analyze_image(image_url: str, user_prompt: str = "", conversation_context: str = "", username: str = "") -> str:
    """
    Analyze an image using Gemini Vision and return Astra-styled commentary.
    Now includes character recognition for known friends/avatars.
    
    Args:
        image_url: URL of the image to analyze
        user_prompt: Optional user question about the image
        conversation_context: Recent chat history for context
        username: Name of the person who sent the image
    
    Returns:
        Astra's response about the image
    """
    if not GEMINI_API_KEY:
        return "can't see images rn, my vision is broken lol"
    
    try:
        # Download image
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return "couldn't load that image, try a different one?"
                
                image_data = await resp.read()
        
        # Build the vision prompt using centralized personality
        vision_prompt = f"""{ASTRA_PROMPT}

You're looking at an image someone shared. Keep it brief (1-3 sentences unless the image needs more explanation).
"""
        
        # Add character recognition context
        character_context = get_character_context_for_vision()
        if character_context:
            vision_prompt += f"""
{character_context}
If you recognize any of these characters in the image, mention them naturally by name!
"""
        
        # Add who sent it
        if username:
            vision_prompt += f"\n{username} just shared this image with you."
        
        # Add conversation context
        if conversation_context:
            vision_prompt += f"\n\nRecent chat for context:\n{conversation_context[-1500:]}"
        
        if user_prompt:
            vision_prompt += f"\n\n{username if username else 'They'} asked: {user_prompt}"
        else:
            vision_prompt += "\n\nGive a casual reaction/comment about this image."
        
        # Create vision model
        model = genai.GenerativeModel(VISION_MODEL)
        
        # Generate response
        response = model.generate_content(
            [
                {"mime_type": "image/jpeg", "data": image_data},
                vision_prompt
            ],
            generation_config={
                "temperature": 0.85,
                "max_output_tokens": 500
            }
        )
        
        return response.text
        
    except Exception as e:
        print(f"[Vision Error] {e}")
        return "something broke when i tried to look at that lol"


async def can_see_images() -> bool:
    """Check if vision is available."""
    return bool(GEMINI_API_KEY)

