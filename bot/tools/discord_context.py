"""Discord History Fetcher - Short-term context from channel."""
from typing import Optional
import discord


# General chat channel for short-term context
GENERAL_CHANNEL_ID = 1466420202563703088


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
            # Include bot messages so GemGem can see her own previous responses
            author_name = msg.author.display_name
            if msg.author.bot:
                author_name = "Astra"  # Label bot messages as Astra
                
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


def format_discord_context(messages: list[dict], max_messages: int = 25) -> str:
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
        # Format: [Username]: message content
        lines.append(f"[{msg['author']}]: {msg['content']}")
    
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
