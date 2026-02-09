"""Discord History Fetcher - Short-term context from channel."""
from typing import Optional
import discord
import re


# General chat channel for short-term context
GENERAL_CHANNEL_ID = 1466420202563703088

# Known bot IDs for proper labeling
GEMGEM_BOT_ID = 1458550716225425560

# Pattern to strip citation markers from bot messages in context
# Matches [🔍1], [💡2], [1], [2] etc.
_CITATION_RE = re.compile(r'\s*\[(?:🔍|💡)?\d+\]')

# Pattern to match standalone ✨ emoji (with optional surrounding whitespace)
_SPARKLE_RE = re.compile(r'\s*\[?✨\]?\s*')

# Pattern to match bare "mhm" responses (case-insensitive, with optional punctuation)
_MHM_RE = re.compile(r'^\s*mhm[.!?]*\s*$', re.IGNORECASE)


async def fetch_recent_messages(
    bot: discord.Client, 
    channel_id: int = None,
    limit: int = 50
) -> list[dict]:
    """
    Fetch last N messages from a channel for short-term context.
    
    Args:
        bot: Discord bot client
        channel_id: Channel to fetch from (defaults to general)
        limit: Number of messages to fetch
    
    Returns:
        List of message dicts with author, content, timestamp
    """
    target_channel = channel_id or GENERAL_CHANNEL_ID
    channel = bot.get_channel(target_channel)
    
    if not channel:
        print(f"[Discord Context] Channel {target_channel} not found")
        return []
    
    messages = []
    try:
        async for msg in channel.history(limit=limit):
            # Determine author name
            author_name = msg.author.display_name
            
            if msg.author.bot:
                # Distinguish between known bots
                if msg.author.id == GEMGEM_BOT_ID:
                    author_name = "GemGem"  # Label GemGem's messages
                elif msg.author.id == bot.user.id:
                    author_name = "Astra"  # Label our own messages as Astra
                else:
                    author_name = msg.author.display_name  # Other bots keep their name
                
            messages.append({
                "author": author_name,
                "user_id": str(msg.author.id),
                "content": msg.content[:500],  # Truncate long messages
                "timestamp": msg.created_at.isoformat(),
                "is_bot": msg.author.bot
            })
        
        # Return in chronological order (oldest first)
        return list(reversed(messages))
    
    except discord.Forbidden:
        print(f"[Discord Context] No permission to read channel {target_channel}")
        return []
    except Exception as e:
        print(f"[Discord Context Error] {e}")
        return []


def _strip_citations(text: str) -> str:
    """Strip citation markers like [🔍1], [💡2], [1] from text."""
    return _CITATION_RE.sub('', text)


def _clean_astra_context(text: str) -> str:
    """
    Clean Astra's own messages before injecting into context.
    Strips citations, ✨ emoji, and replaces bare 'mhm' responses
    so the model doesn't see and reinforce these patterns.
    """
    # Strip citations
    cleaned = _strip_citations(text)
    # Strip ✨ emoji (the signature tic)
    cleaned = _SPARKLE_RE.sub(' ', cleaned).strip()
    # If the entire message is just "mhm", replace it so model doesn't loop
    if _MHM_RE.match(cleaned):
        cleaned = "(acknowledged)"
    return cleaned


def format_discord_context(messages: list[dict], max_messages: int = 50) -> str:
    """
    Format messages for LLM context injection.
    
    Args:
        messages: List of message dicts
        max_messages: Max messages to include (most recent)
    
    Returns:
        Formatted string for context
    """
    if not messages:
        return ""
    
    # Take most recent messages
    recent = messages[-max_messages:]
    
    lines = []
    for msg in recent:
        content = msg['content']
        # Strip citations, ✨, and mhm patterns from Astra's own messages so she doesn't copy them
        if msg['author'] == 'Astra':
            content = _clean_astra_context(content)
        # Format: [Time] [Username]: message content
        time = msg.get('time', '')
        if time:
            lines.append(f"[{time}] [{msg['author']}]: {content}")
        else:
            lines.append(f"[{msg['author']}]: {content}")
    
    return "\n".join(lines)


async def fetch_dm_history(
    channel: discord.DMChannel,
    limit: int = 20
) -> list[dict]:
    """Fetch DM history for context."""
    messages = []
    try:
        async for msg in channel.history(limit=limit):
            messages.append({
                "author": "User" if not msg.author.bot else "Astra",
                "content": msg.content[:500],
                "timestamp": msg.created_at.isoformat()
            })
        return list(reversed(messages))
    except Exception as e:
        print(f"[DM Context Error] {e}")
        return []
