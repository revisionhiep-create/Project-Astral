"""
Shared Memory Manager Module

Handles all conversation memory persistence using a SINGLE SHARED FILE:
- Single source of truth: shared_memory.json
- 100 message rolling window across ALL users (Astral, GemGem, users)
- Timestamps and usernames attached to each message
- Cross-bot context awareness (Astral sees GemGem conversations)
"""

import os
import json
import re
from datetime import datetime
from typing import Optional


class SharedMemoryManager:
    """Manages persistent conversation memory for all users and bots in a single file."""

    MAX_HISTORY = 100  # Maximum messages total (rolling window)
    MEMORY_FILE = "shared_memory.json"
    SUMMARY_FILE = "shared_summary.txt"

    def __init__(self, data_dir: str):
        """
        Initialize the memory manager.

        Args:
            data_dir: Base data directory (usually bot/data)
        """
        self.memory_dir = os.path.join(data_dir, "memory")
        if not os.path.exists(self.memory_dir):
            os.makedirs(self.memory_dir)
        self.memory_file = os.path.join(self.memory_dir, self.MEMORY_FILE)
        self.summary_file = os.path.join(self.memory_dir, self.SUMMARY_FILE)

    def load_memory(self) -> list[dict]:
        """
        Load shared conversation history.

        Returns:
            list: Conversation history (list of message dicts with 'role', 'parts', 'username', 'timestamp')
        """
        history = []

        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception as e:
                print(f"[SharedMemory] Failed to load: {e}")

        # Apply rolling window (keep last MAX_HISTORY messages)
        if len(history) > self.MAX_HISTORY:
            history = history[-self.MAX_HISTORY:]

        return history

    def save_memory(self, history: list[dict]) -> bool:
        """
        Save shared conversation history.

        Args:
            history: Conversation history to save

        Returns:
            bool: True if saved successfully, False otherwise
        """
        # Apply rolling window before saving
        if len(history) > self.MAX_HISTORY:
            history = history[-self.MAX_HISTORY:]

        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
            return True
        except Exception as e:
            print(f"[SharedMemory] Failed to save: {e}")
            return False

    def format_for_router(self, history: list[dict], include_summary: bool = True) -> tuple[list[dict], str]:
        """
        Format history for Astral's router (convert from shared_memory format to router format).

        In shared_memory.json:
        - User messages (from actual users or GemGem): role="user", username=name
        - Astral's responses: role="model", no username

        For the router, everything becomes role="user" with [Name]: prefix format.

        Returns:
            tuple: (formatted_history, summary_context)
                - formatted_history: List of {role, content} dicts for router
                - summary_context: Summary text to inject into system prompt (empty if no summary)
        """
        formatted = []
        summary_context = ""

        # Load summary if available
        if include_summary and os.path.exists(self.summary_file):
            with open(self.summary_file, "r", encoding="utf-8") as f:
                summary = f.read().strip()

            if summary:
                summary_context = f"[PREVIOUS CONTEXT SUMMARY - READ THIS FIRST]:\n{summary}"

                # Truncate history to last 30 messages (since we have summary)
                if len(history) > 30:
                    history = history[-30:]

        for msg in history:
            original_content = msg["parts"][0] if msg["parts"] else ""

            if msg["role"] == "user" and msg.get("username"):
                # User message (from human or GemGem)
                username = msg["username"]
                formatted_content = f"[{username}]: {original_content}"
                formatted.append({
                    "role": "user",
                    "content": formatted_content
                })
            elif msg["role"] == "model":
                # Astral's response (stored as "model" in shared memory)
                # Strip citation markers and footers from Astral's responses
                cleaned_content = original_content
                if isinstance(cleaned_content, str):
                    # Strip Astral citation markers: [🔍1], [💡2], [✨], etc.
                    cleaned_content = re.sub(r'\[🔍\d*\]', '', cleaned_content)
                    cleaned_content = re.sub(r'\[💡\d*\]', '', cleaned_content)
                    cleaned_content = re.sub(r'\[✨\]', '', cleaned_content)
                    # Strip Astral speed footer: 🚗24.1 T/s
                    cleaned_content = re.sub(r'\s*🚗[\d.]+ T/s', '', cleaned_content)
                    # Strip footer line: 💡2 🔍3
                    cleaned_content = re.sub(r'\n\n[💡🔍]\d+(?:\s[💡🔍]\d+)*$', '', cleaned_content)

                formatted.append({
                    "role": "user",  # Router expects all as "user" role
                    "content": f"[Astral]: {cleaned_content}"
                })
            else:
                # Unknown format - preserve as-is
                formatted.append({
                    "role": "user",
                    "content": original_content
                })

        return formatted, summary_context

    def append_message(self, role: str, content: str, username: Optional[str] = None) -> list[dict]:
        """
        Append a single message to history.

        Args:
            role: "user" or "model"
            content: Message content
            username: Display name (for user messages, None for model)

        Returns:
            Updated history
        """
        history = self.load_memory()

        message = {
            "role": role,
            "parts": [content],
            "timestamp": datetime.now().isoformat()
        }

        if username:
            message["username"] = username

        history.append(message)
        self.save_memory(history)

        return history

    def append_conversation_turn(
        self,
        user_message: str,
        bot_response: str,
        username: str = "Unknown"
    ) -> list[dict]:
        """
        Append a complete conversation turn (user + bot response).

        Args:
            user_message: User's message text
            bot_response: Bot's response text
            username: Display name of the user

        Returns:
            Updated history
        """
        history = self.load_memory()
        timestamp = datetime.now().isoformat()

        new_turns = [
            {
                "role": "user",
                "parts": [user_message],
                "username": username,
                "timestamp": timestamp
            },
            {
                "role": "model",
                "parts": [bot_response],
                "timestamp": timestamp
            },
        ]
        history.extend(new_turns)
        self.save_memory(history)

        return history

    def get_message_count(self) -> int:
        """Get total number of messages in shared memory."""
        history = self.load_memory()
        return len(history)

    def load_summary(self) -> Optional[str]:
        """Load conversation summary if it exists."""
        if os.path.exists(self.summary_file):
            try:
                with open(self.summary_file, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                print(f"[SharedMemory] Failed to load summary: {e}")
        return None

    def save_summary(self, summary: str) -> bool:
        """Save conversation summary."""
        try:
            with open(self.summary_file, "w", encoding="utf-8") as f:
                f.write(summary)
            return True
        except Exception as e:
            print(f"[SharedMemory] Failed to save summary: {e}")
            return False
