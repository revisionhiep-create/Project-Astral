"""Character Reference System - Manages known characters for drawing and vision."""
import os
import json
from typing import Optional
import PIL.Image


# Path to character data (relative to bot container)
CHARACTERS_FILE = os.getenv("CHARACTERS_FILE", "/app/data/characters.json")
ASSETS_DIR = os.getenv("ASSETS_DIR", "/app/data/assets")

# Cache for character data
_character_cache = None


def _load_characters() -> dict:
    """Load character data from JSON file."""
    global _character_cache
    
    if _character_cache is not None:
        return _character_cache
    
    try:
        with open(CHARACTERS_FILE, 'r') as f:
            data = json.load(f)
            _character_cache = data.get("characters", {})
            print(f"[Characters] Loaded {len(_character_cache)} characters")
            return _character_cache
    except FileNotFoundError:
        print(f"[Characters] File not found: {CHARACTERS_FILE}")
        return {}
    except json.JSONDecodeError as e:
        print(f"[Characters] JSON parse error: {e}")
        return {}


def get_all_characters() -> dict:
    """Get all character data."""
    return _load_characters()


def detect_characters(text: str) -> list[dict]:
    """
    Detect character mentions in text.
    
    Args:
        text: User message or prompt
        
    Returns:
        List of matched character dicts with name, description, file
    """
    characters = _load_characters()
    matched = []
    text_lower = text.lower()
    
    for name, data in characters.items():
        keywords = data.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in text_lower:
                matched.append({
                    "name": name,
                    "description": data.get("description", ""),
                    "file": data.get("file", ""),
                    "keyword_matched": keyword
                })
                break  # Only match once per character
    
    return matched


def load_character_image(character_name: str) -> Optional[PIL.Image.Image]:
    """
    Load a character's reference image.
    
    Args:
        character_name: Name of the character (e.g., "gemgem", "liddo")
        
    Returns:
        PIL Image or None if not found
    """
    characters = _load_characters()
    
    if character_name not in characters:
        return None
    
    filename = characters[character_name].get("file")
    if not filename:
        return None
    
    image_path = os.path.join(ASSETS_DIR, filename)
    
    try:
        img = PIL.Image.open(image_path)
        print(f"[Characters] Loaded reference: {filename}")
        return img
    except FileNotFoundError:
        print(f"[Characters] Reference image not found: {image_path}")
        return None
    except Exception as e:
        print(f"[Characters] Error loading image: {e}")
        return None


def get_character_description(character_name: str) -> Optional[str]:
    """Get the visual description for a character."""
    characters = _load_characters()
    if character_name in characters:
        return characters[character_name].get("description")
    return None


def get_character_context_for_vision() -> str:
    """
    Build a context string for vision analysis.
    Helps GemGem recognize people she knows in images.
    """
    characters = _load_characters()
    
    if not characters:
        return ""
    
    context = "People/Characters you know:\n"
    for name, data in characters.items():
        desc = data.get("description", "")
        context += f"- {name.title()}: {desc[:150]}...\n" if len(desc) > 150 else f"- {name.title()}: {desc}\n"
    
    return context


def get_all_character_descriptions() -> str:
    """
    Get formatted descriptions of all known characters.
    Used for prompt enhancement context.
    """
    characters = _load_characters()
    
    if not characters:
        return ""
    
    descriptions = []
    for name, data in characters.items():
        desc = data.get("description", "")
        if desc:
            descriptions.append(f"- **{name.title()}**: {desc}")
    
    return "\n".join(descriptions)


def reload_characters():
    """Force reload of character data (useful after updates)."""
    global _character_cache
    _character_cache = None
    return _load_characters()
