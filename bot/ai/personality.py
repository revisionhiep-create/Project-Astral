"""Astra Personality System - Qwen3-VL LoRA Optimized.

v3.0.0: LoRA Optimization.
- Removed extensive personality/style instructions (handled by LoRA).
- Removed static appearance descriptions (handled by LoRA).
- Removed few-shot examples (handled by LoRA).
- Preserved: Dynamic character loading, SEARCH/HONESTY rules.
- Preserved: <think> tag suppression.
"""

import os
import json


def _load_character_context() -> str:
    """Load character descriptions from characters.json for the system prompt."""
    try:
        # In Docker, this is /app/data/characters.json
        json_path = os.getenv("CHARACTERS_FILE", "/app/data/characters.json")

        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                characters = data.get("characters", {})

                lines = []
                for name, info in characters.items():
                    if name.lower() == "astra":
                        continue  # Skip self
                    desc = info.get("description", "")[:150]
                    # Get aliases from keywords
                    aliases = info.get("keywords", [])
                    alias_str = f" ({', '.join(aliases[:2])})" if aliases else ""
                    lines.append(f"- {name.title()}{alias_str}: {desc}")

                return "\n".join(lines)
    except Exception as e:
        print(f"[Personality] Error loading characters: {e}")

    # Fallback if file not found
    return """- Liddo: Male, cute chibi with brown hair, red bunny hood
- Tei (Melon): Male, cute kawaii cactus in a terracotta pot
- Hiep (Revision): Male, chibi with long lavender hair, purple crystals
- Jason (ShiftStep): Male, green and white mech/robot with pink flames
- GemGem: Female, your sister bot - galaxy blue hair, cosmic aesthetic"""


# Minimal template for LoRA - relies on model training for personality/style
_ASTRA_TEMPLATE = """You are Astra (she/her), 22, part of this Discord server. GemGem is your sister bot.

PEOPLE YOU KNOW
{character_context}

SEARCH PRIORITY (CRITICAL)
- The [CONTEXT] section contains real-time search results.
- You MUST use this information to answer factual questions.
- Synthesize an answer from the [CONTEXT] sources.
- Only if the [CONTEXT] is empty or irrelevant, say "couldn't find that".

HONESTY RULE (CRITICAL)
- Never fabricate quotes.
- If confused, admit it.
- Don't guess.
"""


def get_astra_prompt() -> str:
    """Build the full Astra prompt with dynamically loaded characters."""
    character_context = _load_character_context()
    return _ASTRA_TEMPLATE.format(character_context=character_context)


# For compatibility - this now dynamically loads characters
ASTRA_PROMPT = get_astra_prompt()
GEMGEM_PROMPT = ASTRA_PROMPT  # Legacy alias


def build_system_prompt(
    search_context: str = "", memory_context: str = "", current_speaker: str = None
) -> str:
    """Build system prompt with optional context."""
    # Reload characters each time for freshness
    prompt_parts = [get_astra_prompt()]

    # Qwen3 Instruction: Suppress internal thought output
    prompt_parts.append(
        "\n[SYSTEM NOTE]\nDo not output internal thoughts or <think> tags. Output only the dialogue response."
    )

    # CRITICAL: Speaker identity goes in system prompt for highest priority
    if current_speaker:
        prompt_parts.append(
            f"\n>>> YOU ARE RESPONDING TO: {current_speaker} <<<\nThis person is talking to you RIGHT NOW. Address {current_speaker} specifically in your reply."
        )

    if search_context:
        prompt_parts.append(f"\n[CONTEXT]\n{search_context}")

    if memory_context:
        prompt_parts.append(f"\n[MEMORY]\n{memory_context}")

    return "\n".join(prompt_parts)
