"""Query Enhancement - Uses conversation context to build better search queries."""
import re


def extract_topic_from_history(conversation_history: list[dict], limit: int = 5) -> str:
    """
    Extract the main topic being discussed from recent USER messages only.
    Returns the topic name or empty string if none found.
    """
    if not conversation_history:
        return ""
    
    # Only look at USER messages (not assistant responses) to find topics
    recent = conversation_history[-limit:]
    
    # Words to skip (common words that aren't topics)
    skip_words = {"i", "i'm", "i'll", "the", "a", "an", "is", "are", "was", "were",
                  "what", "who", "where", "when", "how", "why", "do", "does", "did",
                  "can", "could", "would", "should", "will", "have", "has", "had",
                  "you", "your", "her", "him", "she", "he", "it", "they", "we",
                  "this", "that", "these", "those", "about", "been", "being",
                  "gemgem", "lab", "hey", "hi", "hello", "oh", "yes", "no", "yeah"}
    
    for msg in reversed(recent):
        # Only look at user messages
        if msg.get("role") != "user":
            continue
            
        content = msg.get("content", "")
        
        # Look for capitalized words that are likely proper nouns
        words = content.split()
        for word in words:
            # Clean the word of punctuation
            clean_word = re.sub(r'[^\w]', '', word)
            
            if (len(clean_word) > 2 and 
                clean_word[0].isupper() and 
                clean_word.lower() not in skip_words):
                return clean_word
    
    return ""


def enhance_query(user_message: str, conversation_history: list[dict]) -> str:
    """
    Enhance a vague query by prepending the topic if one exists in history.
    
    SIMPLIFIED VERSION: Just prepend topic, don't try to replace pronouns.
    This avoids the bug where "her" gets replaced with wrong words.
    """
    # Check if message has pronouns that might need context
    message_lower = user_message.lower()
    has_pronouns = any(p in message_lower for p in [" her ", " him ", " them ", " it ", " she ", " he "])
    
    if not has_pronouns:
        # No pronouns, query is specific enough
        return user_message
    
    # Extract topic from conversation history
    topic = extract_topic_from_history(conversation_history)
    
    if not topic:
        # No topic found, return original
        return user_message
    
    # Check if topic is already in the message
    if topic.lower() in message_lower:
        return user_message
    
    # Prepend topic to the query (safer than pronoun replacement)
    enhanced = f"{topic} {user_message}"
    print(f"[Query Enhancement] '{user_message}' -> '{enhanced}'")
    return enhanced


def should_search(user_message: str, conversation_history: list[dict]) -> bool:
    """
    Determine if a search should be performed.
    Default: ALWAYS search unless it's clearly casual small talk.
    """
    message_lower = user_message.lower().strip()
    
    # Only skip search for very short casual greetings
    skip_patterns = [
        "hi", "hey", "hello", "yo", "sup",
        "thanks", "thank you", "ty",
        "ok", "okay", "k", "kk",
        "lol", "lmao", "haha",
        "bye", "goodbye", "gn", "cya"
    ]
    
    # If message is just one of these casual words, skip search
    if message_lower.strip("!?.") in skip_patterns:
        return False
    
    # Everything else: SEARCH
    return True
