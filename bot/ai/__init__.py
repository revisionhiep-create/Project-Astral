# AI module - personality and routing
from ai.personality import build_system_prompt
from ai.router import process_message, generate_response

__all__ = [
    "build_system_prompt",
    "process_message",
    "generate_response",
]
