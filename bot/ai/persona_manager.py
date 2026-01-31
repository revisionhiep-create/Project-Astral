"""Dynamic Persona Manager - Evolves Astra's personality based on conversations.

Uses Gemini Flash to analyze recent messages and update persona state.
Three layers tracked: Vibe (short-term), Bond (long-term), Story (episodic).
"""
import os
import json
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional


# Gemini Flash for persona analysis
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# Persona state file (persisted via Docker volume)
PERSONA_FILE = os.getenv("PERSONA_FILE", "/app/data/persona_state.json")

# How often to update (every N messages)
UPDATE_INTERVAL = 10

# Message counter (reset on restart, that's fine)
_message_count = 0


def get_default_persona() -> dict:
    """Default persona state for Astra."""
    return {
        "group_vibe": {
            "current_mood": "chill",
            "energy_level": "relaxed",
            "current_obsession": None,
            "last_updated": datetime.now().isoformat()
        },
        "relationships": {
            "stage": "friendly acquaintances",
            "intimacy_level": 50,
            "shared_vocabulary": [],
            "inside_jokes": [],
            "trust_level": 50
        },
        "memory_bank": {
            "short_term_events": [],
            "long_term_facts": [],
            "user_preferences": {}
        },
        "update_count": 0
    }


def load_persona() -> dict:
    """Load persona state from file."""
    try:
        if os.path.exists(PERSONA_FILE):
            with open(PERSONA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[Persona] Error loading: {e}")
    
    return get_default_persona()


def save_persona(state: dict) -> None:
    """Save persona state to file."""
    try:
        os.makedirs(os.path.dirname(PERSONA_FILE), exist_ok=True)
        with open(PERSONA_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        print(f"[Persona] Saved state (update #{state.get('update_count', 0)})")
    except Exception as e:
        print(f"[Persona] Error saving: {e}")


def format_messages_for_analysis(messages: list) -> str:
    """Format recent messages for Gemini analysis."""
    lines = []
    for msg in messages[-20:]:  # Last 20 messages max
        author = msg.get('author', 'Unknown')
        content = msg.get('content', '')[:300]
        lines.append(f"{author}: {content}")
    return "\n".join(lines)


async def analyze_and_update(recent_messages: list) -> Optional[dict]:
    """
    Send recent messages to Gemini Flash for persona analysis.
    Updates persona_state.json with evolved personality.
    """
    global _message_count
    
    if not GEMINI_API_KEY:
        print("[Persona] No Gemini API key, skipping analysis")
        return None
    
    if not recent_messages:
        return None
    
    current_state = load_persona()
    chat_log = format_messages_for_analysis(recent_messages)
    
    # The Memory Manager prompt from Gemini Pro's suggestion
    analysis_prompt = f"""### SYSTEM INSTRUCTION
You are the "Memory Manager" for an AI companion named Astra. Your goal is to update Astra's internal perception of the group based on recent conversation.

### INPUT DATA
1. **Current Persona State:**
{json.dumps(current_state, indent=2)}

2. **Recent Chat Logs:**
{chat_log}

### YOUR TASK
Analyze the chat logs and UPDATE the Persona State JSON.
1. **Mood Tracking:** Did the group's mood change? (e.g., from "Chill" to "Excited" or "Stressed").
2. **Interest Evolution:** Did they mention a new game/tech/topic? If they moved on from an old interest, update current_obsession.
3. **Relationship Dynamic:** Did they share personal info? Increase intimacy_level. Did they joke around? Add jokes to shared_vocabulary.
4. **Active Storylines:** Is there an event they are waiting for? Add it to short_term_events.
5. **User Preferences:** Note any preferences mentioned (likes, dislikes, habits).

### OUTPUT FORMAT
Return ONLY the updated JSON. No markdown, no explanations. Use this schema:

{{
  "group_vibe": {{
    "current_mood": "chill/excited/stressed/playful",
    "energy_level": "relaxed/energetic/tired",
    "current_obsession": "what the group is into right now or null",
    "last_updated": "{datetime.now().isoformat()}"
  }},
  "relationships": {{
    "stage": "strangers/acquaintances/friends/close friends/family",
    "intimacy_level": 0-100,
    "shared_vocabulary": ["phrases you guys use"],
    "inside_jokes": ["jokes only this group gets"],
    "trust_level": 0-100
  }},
  "memory_bank": {{
    "short_term_events": ["things happening soon"],
    "long_term_facts": ["permanent things to remember"],
    "user_preferences": {{"username": "their preferences"}}
  }},
  "update_count": {current_state.get('update_count', 0) + 1}
}}"""

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "contents": [{"parts": [{"text": analysis_prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 1500
                }
            }
            
            async with session.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status != 200:
                    print(f"[Persona] Gemini API error: {resp.status}")
                    return None
                
                data = await resp.json()
                response_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                
                # Clean up response (remove markdown if present)
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                
                # Parse and save
                new_state = json.loads(response_text)
                save_persona(new_state)
                
                print(f"[Persona] Updated! Intimacy: {new_state.get('relationships', {}).get('intimacy_level', '?')}, "
                      f"Mood: {new_state.get('group_vibe', {}).get('current_mood', '?')}")
                
                return new_state
                
    except json.JSONDecodeError as e:
        print(f"[Persona] JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"[Persona] Analysis error: {e}")
        return None


def should_update() -> bool:
    """Check if we should trigger a persona update."""
    global _message_count
    _message_count += 1
    
    if _message_count >= UPDATE_INTERVAL:
        _message_count = 0
        return True
    return False


def get_persona_context() -> str:
    """
    Get formatted persona context for injection into Astra's system prompt.
    This is what makes her feel 'alive'.
    """
    state = load_persona()
    
    vibe = state.get("group_vibe", {})
    rel = state.get("relationships", {})
    mem = state.get("memory_bank", {})
    
    context_parts = []
    
    # Current vibe
    mood = vibe.get("current_mood", "chill")
    obsession = vibe.get("current_obsession")
    context_parts.append(f"The group is currently feeling {mood}.")
    if obsession:
        context_parts.append(f"Everyone's been into {obsession} lately.")
    
    # Relationship
    stage = rel.get("stage", "acquaintances")
    trust = rel.get("trust_level", 50)
    context_parts.append(f"You're {stage} with this group.")
    
    if trust >= 80:
        context_parts.append("You can be pretty blunt and roast them without apology.")
    elif trust >= 60:
        context_parts.append("You can be sarcastic and tease them.")
    elif trust <= 30:
        context_parts.append("You're still warming up to them, be a bit more reserved.")
    
    # Inside jokes
    jokes = rel.get("inside_jokes", [])
    if jokes:
        context_parts.append(f"Inside jokes you share: {', '.join(jokes[:3])}")
    
    # Shared vocabulary
    vocab = rel.get("shared_vocabulary", [])
    if vocab:
        context_parts.append(f"Phrases you guys use: {', '.join(vocab[:5])}")
    
    # Short-term events
    events = mem.get("short_term_events", [])
    if events:
        context_parts.append(f"Things happening: {', '.join(events[:3])}")
    
    # User preferences
    prefs = mem.get("user_preferences", {})
    if prefs:
        pref_list = [f"{user} {pref}" for user, pref in list(prefs.items())[:3]]
        context_parts.append(f"Things to remember: {', '.join(pref_list)}")
    
    return "\n".join(context_parts)


def reset_message_counter():
    """Reset the message counter (useful for testing)."""
    global _message_count
    _message_count = 0
